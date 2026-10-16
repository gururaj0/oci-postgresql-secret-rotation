import psycopg
from psycopg import sql

from rotation.model import RotationError


class Postgres:
    def __init__(self, config):
        self.config = config

    def connect(self, password):
        c = self.config
        return psycopg.connect(host=c.host, port=c.port, dbname=c.database, user=c.username,
                               password=password, sslmode="verify-full", sslrootcert=c.ca_file,
                               connect_timeout=10, options="-c statement_timeout=15000", autocommit=True)

    def verify(self, password):
        try:
            with self.connect(password) as conn:
                conn.execute("SELECT 1")
            return True
        except psycopg.OperationalError as exc:
            # Only invalid credentials are evidence that a password does not work.
            # Timeouts, DNS, certificate and service errors must stop reconciliation.
            if exc.sqlstate == "28P01" or "password authentication failed for user" in str(exc):
                return False
            raise RotationError("Database connectivity/TLS verification failed; authentication state unknown") from None

    def preflight(self, password):
        with self.connect(password) as conn:
            row = conn.execute("SELECT rolcanlogin FROM pg_roles WHERE rolname = %s",
                               (self.config.username,)).fetchone()
            if not row or not row[0]:
                raise RotationError("Selected PostgreSQL role does not exist or cannot log in")
            managed = conn.execute("SELECT pg_has_role(current_user, oid, 'MEMBER') FROM pg_roles "
                                   "WHERE rolname = 'oci_admin_role'").fetchone()
            if managed and managed[0]:
                raise RotationError("Managed administrator roles require the separate reset API strategy")
            if not conn.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()").fetchone()[0]:
                raise RotationError("TLS is required")

    def change(self, current, pending):
        with self.connect(current) as conn:
            verifier = conn.pgconn.encrypt_password(pending.encode(conn.info.encoding),
                self.config.username.encode(conn.info.encoding), b"scram-sha-256").decode()
            # Self-password change needs no CREATEROLE grant. Both identifier AND literal quoted by psycopg.
            conn.execute(sql.SQL("ALTER ROLE {} PASSWORD {}").format(
                sql.Identifier(self.config.username), sql.Literal(verifier)))
