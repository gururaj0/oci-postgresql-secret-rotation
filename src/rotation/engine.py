import logging
import secrets
import string
import uuid

from rotation.model import Database, Operation, ReconciliationRequired, RotationError, Store, Vault, now

LOG = logging.getLogger("pg_rotation")
STATES = ["PRECHECK", "PREPARED", "DATABASE_UPDATED", "VERIFIED", "VAULT_PROMOTED", "COMPLETE"]


def password() -> str:
    alphabet = string.ascii_letters + string.digits + "_-!@#%+=."
    # Explicit complexity as well as entropy; SQL quoting remains mandatory.
    while True:
        value = "".join(secrets.choice(alphabet) for _ in range(40))
        if all(any(c in group for c in value) for group in (string.ascii_lowercase,
               string.ascii_uppercase, string.digits, "_-!@#%+=.")):
            return value


class Engine:
    def __init__(self, vault: Vault, db: Database, store: Store, target: str, role: str):
        self.vault, self.db, self.store = vault, db, store
        self.target, self.role = target, role

    def validate(self) -> dict:
        current = self.vault.current()
        self.db.preflight(self.vault.password(current))
        return {"current_version": current, "tls": "verify-full", "strategy": "application-self"}

    def run(self, stop: str = "COMPLETE", expected: int | None = None,
            reconcile: bool = False) -> Operation:
        if stop not in STATES:
            raise RotationError("Unsupported rotation stage")
        owner = str(uuid.uuid4())
        self.store.acquire(owner)
        op = None
        try:
            op = self.store.load()
            if op and (op.target != self.target or op.role != self.role):
                raise RotationError("Operation target mismatch")
            if op and op.state == "COMPLETE" and expected == op.current:
                return op  # Vault callback retry for the same base version.
            if not op or op.state == "COMPLETE":
                if reconcile:
                    if op:
                        return op
                    raise RotationError("No incomplete operation to reconcile")
                current = self.vault.current()
                if expected is not None and expected != current:
                    raise RotationError("Stale callback currentVersionNo")
                self.db.preflight(self.vault.password(current))
                op = Operation(owner, self.target, self.role, current, started_at=now(),
                               last_success=op.last_success if op else None)
                self.store.save(op)
            else:
                if expected is not None and expected != op.current:
                    raise RotationError("Callback conflicts with active operation")
                op.retries += 1
                self.store.save(op)

            def advance(state: str):
                op.state, op.error = state, None
                self.store.save(op)
                LOG.info("operation=%s state=%s", op.operation_id, state)

            if STATES.index(op.state) >= STATES.index(stop):
                return op
            if op.state == "PRECHECK":
                # Deterministic version name recovers a lost Vault update response.
                op.pending = self.vault.prepare(op.operation_id, password())
                advance("PREPARED")
                if stop == op.state:
                    return op
            if op.pending is None:
                raise ReconciliationRequired("Missing pending version reference")
            pending = self.vault.password(op.pending)
            if op.state == "PREPARED":
                if self.vault.current() not in (op.current, op.pending):
                    raise ReconciliationRequired("Vault CURRENT changed externally; no database update performed")
                # Probe pending first: the previous invocation may have committed ALTER ROLE.
                if not self.db.verify(pending):
                    current = self.vault.password(op.current)
                    if not self.db.verify(current):
                        raise ReconciliationRequired("Neither recorded credential authenticates; follow recovery runbook")
                    self.db.change(current, pending)
                advance("DATABASE_UPDATED")
            if op.state == "DATABASE_UPDATED":
                if not self.db.verify(pending):
                    raise ReconciliationRequired("Pending authentication failed after update; no promotion performed")
                advance("VERIFIED")
                if stop in ("DATABASE_UPDATED", "VERIFIED"):
                    return op
            if op.state == "VERIFIED":
                # Re-verify on every resume, including promotion-only callbacks.
                if not self.db.verify(pending):
                    raise ReconciliationRequired("Pending no longer authenticates; investigate external changes")
                self.vault.promote(op.pending, op.current)
                advance("VAULT_PROMOTED")
                if stop == op.state:
                    return op
            if op.state == "VAULT_PROMOTED":
                if self.vault.current() != op.pending or not self.db.verify(pending):
                    raise ReconciliationRequired("Active Vault version and database require reconciliation")
                op.completed_at = op.last_success = now()
                op.consecutive_failures = 0
                advance("COMPLETE")
            return op
        except Exception as exc:
            if op and op.state != "COMPLETE":
                # Classification only: SDK/SQL exception strings can contain credentials.
                op.error = "RECONCILIATION_REQUIRED" if isinstance(exc, ReconciliationRequired) else "DEPENDENCY_FAILURE"
                op.consecutive_failures += 1
                self.store.save(op)
                LOG.error("operation=%s state=%s error=%s cause=%s status=%s",
                          op.operation_id, op.state, op.error, type(exc).__name__, getattr(exc, "status", None))
            if isinstance(exc, RotationError):
                raise
            raise RotationError("Rotation interrupted; inspect status and reconcile recorded versions") from None
        finally:
            self.store.release()
