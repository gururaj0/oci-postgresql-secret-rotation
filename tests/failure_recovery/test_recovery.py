import unittest

from rotation.engine import Engine
from rotation.model import RotationError
from tests.unit import test_engine


class RecoveryTests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp

    def test_recover_lost_database_commit_response(self):
        self.db.lost_change_response = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.assertEqual(self.store.op.state, "PREPARED")
        result = Engine(self.vault, self.db, self.store, "db-id", "app-role").run(reconcile=True)
        self.assertEqual(result.state, "COMPLETE")
        self.assertEqual(self.db.changes, 1)

    def test_recover_promotion_failure(self):
        self.vault.fail_promote = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.assertEqual(self.store.op.state, "VERIFIED")
        self.assertEqual(self.vault.active, 1)
        self.vault.fail_promote = False
        self.assertEqual(self.engine.run(reconcile=True).state, "COMPLETE")
        self.assertEqual(self.db.changes, 1)

    def test_lost_prepare_response_reuses_version(self):
        self.vault.lost_prepare_response = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.engine.run(reconcile=True)
        self.assertEqual(len(self.vault.versions), 2)

    def test_lost_promote_response(self):
        self.vault.lost_promote_response = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.engine.run(reconcile=True)
        self.assertEqual(len(self.vault.versions), 2)
        self.assertEqual(self.db.changes, 1)

    def test_alter_failure_preserves_current(self):
        self.db.fail_change = True
        with self.assertRaises(RotationError):
            self.engine.run()
        self.assertEqual(self.vault.current(), 1)
        self.assertEqual(self.db.active, "old-password")

    def test_journal_failure_after_update_is_recoverable(self):
        self.store.fail_state = "DATABASE_UPDATED"
        with self.assertRaises(RotationError):
            self.engine.run()
        self.engine.run(reconcile=True)
        self.assertEqual(self.db.changes, 1)

    def test_timeout_lock_requires_controlled_unlock(self):
        self.engine.run(stop="PREPARED")
        self.store.acquire("terminated-function")
        with self.assertRaises(RotationError):
            self.engine.run(reconcile=True)
        self.store.release()  # Operator confirms previous invocation is stopped first.
        self.assertEqual(self.engine.run(reconcile=True).state, "COMPLETE")
