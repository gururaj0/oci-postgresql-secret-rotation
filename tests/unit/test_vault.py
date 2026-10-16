import base64
import importlib.util
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from rotation.model import ReconciliationRequired, RotationError


@unittest.skipUnless(importlib.util.find_spec("oci"), "OCI SDK is required for adapter tests")
class VaultTests(unittest.TestCase):
    def setUp(self):
        import oci
        from vault.client import OciVault
        self.oci = oci
        self.active, self.etag = 1, "1"
        self.lifecycle = "ACTIVE"
        self.versions = [SimpleNamespace(name="initial", version_number=1, stages=["CURRENT"])]
        self.contents = {1: {"username": "app", "password": "initial-password"}}
        self.updates = []
        self.client = OciVault(self, self, "secret", "app")

    def get_secret(self, secret):
        return SimpleNamespace(data=SimpleNamespace(current_version_number=self.active, lifecycle_state=self.lifecycle),
                               headers={"etag": self.etag})

    def list_secret_versions(self, secret, **kwargs):
        return self.oci.response.Response(200, {}, list(self.versions), None)

    def update_secret(self, secret, details, **kwargs):
        self.assertEqual(kwargs["if_match"], self.etag)
        self.updates.append(details)
        if details.secret_content:
            content = details.secret_content
            self.assertEqual(content.stage, "PENDING")
            version = len(self.versions) + 1
            self.versions.append(SimpleNamespace(name=content.name, version_number=version, stages=["PENDING"]))
            self.contents[version] = json.loads(base64.b64decode(content.content))
        else:
            self.active = details.current_version_number
        self.etag = str(int(self.etag) + 1)

    def get_secret_bundle(self, secret, version_number):
        content = base64.b64encode(json.dumps(self.contents[version_number]).encode()).decode()
        return SimpleNamespace(data=SimpleNamespace(secret_bundle_content=SimpleNamespace(content=content)))

    def test_prepare_is_named_pending_and_idempotent(self):
        first = self.client.prepare("operation", "new-password")
        self.assertEqual(self.client.prepare("operation", "different-password"), first)
        self.assertEqual(len(self.updates), 1)
        self.assertEqual(self.client.password(first), "new-password")
        self.assertEqual(self.client.current(), 1)

    def test_foreign_pending_is_not_overwritten(self):
        self.versions.append(SimpleNamespace(name="foreign", version_number=2, stages=["PENDING"]))
        with self.assertRaises(ReconciliationRequired):
            self.client.prepare("operation", "new-password")
        self.assertFalse(self.updates)

    def test_promotion_is_separate_and_checks_base(self):
        version = self.client.prepare("operation", "new-password")
        self.client.promote(version, 1)
        self.assertEqual(self.client.current(), version)
        self.assertIsNone(self.updates[-1].secret_content)
        self.client.promote(version, 1)
        self.assertEqual(len(self.updates), 2)
        self.active = 99
        with self.assertRaises(ReconciliationRequired):
            self.client.promote(version, 1)

    def test_mismatched_username_is_rejected(self):
        self.contents[1]["username"] = "other"
        with self.assertRaises(RotationError):
            self.client.password(1)

    def test_bundle_read_waits_for_asynchronous_update(self):
        self.lifecycle = "UPDATING"
        def complete_update(_):
            self.lifecycle = "ACTIVE"
        with patch("vault.client.time.sleep", side_effect=complete_update) as sleep:
            self.assertEqual(self.client.password(1), "initial-password")
        sleep.assert_called_once()

    def test_failed_secret_does_not_continue(self):
        self.lifecycle = "FAILED"
        with self.assertRaises(RotationError):
            self.client.prepare("operation", "new-password")
        self.assertFalse(self.updates)

    def test_async_timeout_preserves_pending_without_recreating(self):
        self.lifecycle = "UPDATING"
        with patch("vault.client.time.monotonic", side_effect=[0, 61]):
            with self.assertRaises(RotationError):
                self.client.password(1)
        self.assertFalse(self.updates)

    def test_rate_limit_is_retried_with_bounded_backoff(self):
        calls = []
        def limited():
            calls.append(1)
            if len(calls) < 3:
                raise self.oci.exceptions.ServiceError(429, "TooManyRequests", {}, "throttled")
            return "ok"
        with patch("vault.client.time.sleep") as sleep:
            self.assertEqual(self.client._call(limited), "ok")
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [2, 4])

    def test_unknown_write_outcome_is_not_blindly_retried(self):
        calls = []
        def lost_response():
            calls.append(1)
            raise TimeoutError
        with self.assertRaises(TimeoutError):
            self.client._call(lost_response)
        self.assertEqual(len(calls), 1)
