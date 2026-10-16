import json
import unittest

from rotation.engine import Engine, STATES, password
from rotation.model import Busy, ReconciliationRequired, RotationError
from rotation.protocol import callback
from tests.fakes import MemoryDB, MemoryStore, MemoryVault


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.vault, self.db, self.store = MemoryVault(), MemoryDB(), MemoryStore()
        self.engine = Engine(self.vault, self.db, self.store, "db-id", "app-role")

    def test_success_and_repeated_rotation(self):
        first = self.engine.run()
        self.assertEqual(first.state, "COMPLETE")
        self.assertTrue(self.db.verify(self.vault.password(self.vault.current())))
        second = self.engine.run()
        self.assertNotEqual(first.operation_id, second.operation_id)
        self.assertEqual(self.db.changes, 2)
        self.assertEqual(set(r["state"] for r in self.store.history), set(STATES))

    def test_validation_is_read_only(self):
        self.engine.validate()
        self.assertIsNone(self.store.op)
        self.assertFalse(self.store.locked)
        self.assertEqual(self.db.changes, 0)
        self.assertEqual(len(self.vault.versions), 1)

    def test_concurrent_invocation_is_rejected(self):
        self.store.acquire("other")
        with self.assertRaises(Busy):
            self.engine.run()
        self.assertEqual(self.db.changes, 0)
        self.assertTrue(self.store.locked)

    def test_vault_unavailable_does_not_change_database(self):
        self.vault.fail_prepare = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.assertEqual(self.db.active, "old-password")
        self.assertEqual(self.vault.current(), 1)

    def test_password_generation(self):
        values = {password() for _ in range(100)}
        self.assertEqual(len(values), 100)
        self.assertTrue(all(len(v) == 40 for v in values))

    def test_native_protocol_and_duplicates(self):
        secret = "secret-id"
        result = callback(self.engine, secret, {"secretId": secret, "step": "VERIFY_CONNECTION"})
        self.assertEqual(result["currentVersionNo"], 1)
        for step in ("CREATE_PENDING_VERSION", "UPDATE_TARGET_SYSTEM", "PROMOTE_PENDING_VERSION"):
            request = {"secretId": secret, "step": step, "versionNo": result["currentVersionNo"]}
            result = callback(self.engine, secret, request)
            duplicate = callback(self.engine, secret, request)
            self.assertEqual(result, duplicate)
        self.assertEqual(self.db.changes, 1)
        self.assertEqual(result["currentVersionNo"], 2)

    def test_cannot_promote_without_verification(self):
        self.engine.run(stop="PREPARED")
        with self.assertRaises(RotationError):
            callback(self.engine, "s", {"secretId": "s", "step": "PROMOTE_PENDING_VERSION", "versionNo": 2})
        self.assertEqual(self.vault.current(), 1)

    def test_wrong_secret_and_stale_callback(self):
        with self.assertRaises(RotationError):
            callback(self.engine, "s", {"secretId": "other", "step": "VERIFY_CONNECTION"})
        with self.assertRaises(RotationError):
            self.engine.run(expected=99)
        self.assertEqual(self.db.changes, 0)

    def test_metadata_and_logs_exclude_secrets(self):
        with self.assertLogs("pg_rotation", level="INFO") as logs:
            self.engine.run()
        evidence = json.dumps(self.store.history) + "".join(logs.output)
        for value in self.vault.versions.values():
            self.assertNotIn(value, evidence)

    def test_invalid_pending_after_change_never_promoted(self):
        self.db.reject_pending = True
        with self.assertRaises(ReconciliationRequired):
            self.engine.run()
        self.assertEqual(self.vault.current(), 1)
        self.assertEqual(self.store.op.error, "RECONCILIATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
