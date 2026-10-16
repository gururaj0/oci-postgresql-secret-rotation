# Testing guide

## Local tests without cloud access

From the repository root, install the runtime and development dependencies:

```bash
./install.sh
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
PYTHONPATH=src python -m unittest discover -v
ruff check src functions tests scripts
python scripts/security-check.py
terraform fmt -check -recursive terraform
terraform -chdir=terraform init -backend=false
terraform -chdir=terraform validate
```

The current suite contains 37 tests. Without private-network configuration, 36 pass and one live integration test skips. Coverage includes state transitions, concurrent locking, interrupted updates/promotion, deterministic version reuse, Vault lifecycle polling and throttling, pagination, callback validation and the metrics ingestion endpoint.

Failure-injection tests deliberately emit sanitized error logs; use the test runner's final result to determine success. Source guards are not a substitute for dependency or container vulnerability scanning.

## Read-only live integration

Use a private-network host and a configured application role, Vault secret, CA and journal bucket:

```bash
PG_ROTATION_INTEGRATION_CONFIG="$PWD/rotation.yaml" \
  PYTHONPATH=src python -m unittest tests.integration.test_customer -v
pg-vault-rotation --config rotation.yaml rotate --dry-run
```

This verifies the selected system and a fresh TLS login with Vault CURRENT. It does not change the password. Do not commit the local configuration or service credentials.

## Approved rotation and recovery acceptance

The following changes the configured role's password and Vault versions. Run only on an explicitly approved nonproduction target, with no concurrent native rotation:

```bash
pg-vault-rotation --config rotation.yaml rotate --confirm
pg-vault-rotation --config rotation.yaml status
pg-vault-rotation --config rotation.yaml validate

mkdir -p .local
PYTHONPATH=src python scripts/live-acceptance.py \
  --config rotation.yaml --report .local/live-acceptance.json --confirm
```

The acceptance harness checks dry-run nonmutation, lock contention, an injected promotion interruption after database update, surviving existing sessions, recovery using the same operation/version, a fresh CURRENT login and absence of tested passwords from the journal. It uses real services and performs another rotation. Use `reconcile --confirm` and the [recovery runbook](docs/recovery-runbook.md) for an interrupted operation; never reset the journal or delete a needed pending version.

## Deployed Function and Console acceptance

Invoke `{"action":"validate"}` from an authorized operator. Then test the four documented callbacks and confirm the final version authenticates. Direct callback success does not prove Secret Service orchestration.

For native acceptance, record CURRENT, select Rotate in Console, observe the callback logs and require a newer CURRENT, COMPLETE journal and fresh login. Version 0.1.1 passed this native test with scheduling disabled, advancing CURRENT from 5 to 6. Earlier versions returned `currentVersionNo` instead of the required `versionNo` and stalled after VERIFY_CONNECTION; the exact response-field contract is now regression-tested. Periodic execution, a real Function hard-kill recovery drill, notification delivery and the customer's connection-pool refresh still require acceptance.

## Security and release checks

```bash
pip-audit -r requirements.resolved.lock
# Run your approved image scanner against the exact deployed image digest.
```

The runtime dependency audit passed at the recorded test date. The scanned demo image retains OS-package findings without listed fixes; see [SECURITY.md](SECURITY.md). Audit results change over time. Record scanner versions, image digest, test date and sanitized results for each release.

Detailed historical evidence and remaining gates: [validation](docs/validation.md) and [customer handoff](docs/customer-handoff.md).
