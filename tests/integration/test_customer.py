"""Read-only integration check; rotations require the separate approved acceptance runbook."""
import os
import unittest


@unittest.skipUnless(os.getenv("PG_ROTATION_INTEGRATION_CONFIG"), "Customer private-network configuration required")
class CustomerIntegration(unittest.TestCase):
    def test_vault_current_authenticates_over_verified_tls(self):
        from cli.config import Config
        from cli.runtime import preflight
        result = preflight(Config.load(os.environ["PG_ROTATION_INTEGRATION_CONFIG"]))
        self.assertEqual(result["tls"], "verify-full")
