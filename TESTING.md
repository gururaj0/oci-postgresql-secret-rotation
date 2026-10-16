# Testing guide

Use the [deployment task/location table](DEPLOYMENT.md#tasks-and-where-to-run-them) to choose where to run each check. An OCI Compute VM with private database connectivity is the recommended host for live CLI tests. Unit tests can run on a laptop. Console-triggered rotation executes in the deployed Function; verify application credential refresh from the application environment.

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

The current suite contains 46 tests. Without private-network configuration, 45 pass and one live integration test skips. Coverage includes state transitions, concurrent locking, interrupted updates/promotion, deterministic version reuse, Vault lifecycle polling and throttling, pagination, callback validation and the metrics ingestion endpoint.

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

For native acceptance, record CURRENT, select Rotate in Console, observe the callback logs and require a newer CURRENT, COMPLETE journal and fresh login. Manual rotation through OCI Secret Service passed with scheduling disabled: the password and secret were updated and a fresh database login succeeded. Repeat these checks in your own environment. Periodic execution, a real Function hard-kill recovery drill, notification delivery and the customer's connection-pool refresh still require acceptance.

## Security and release checks

```bash
pip-audit -r requirements.resolved.lock
# Run your approved image scanner against the exact deployed image digest.
```

The runtime dependency audit passed at the recorded test date. The scanned demo image retains OS-package findings without listed fixes; see [SECURITY.md](SECURITY.md). Audit results change over time. Record scanner versions, image digest, test date and sanitized results for each release.

Detailed historical evidence and remaining gates: [validation](docs/validation.md) and [customer handoff](docs/customer-handoff.md).

## Resource Manager deployment acceptance

The [browser deployment guide](docs/resource-manager.md) tracks validation of this new path. Helper tests cover packaging isolation, temporary registry-token handling, fresh-login validation before linking, ETag use and refusal to replace a different target.

For end-to-end acceptance, deploy the release ZIP through a new Resource Manager stack against an approved isolated target with automatic rotation disabled. Require a successful image build/push, a digest-pinned Function, read-only Function validation, the correct secret target, invocation logs and a monitor heartbeat. Reapply without changes and confirm no rebuild or duplicate resources. Then perform an approved Console rotation and verify a newer CURRENT plus a fresh application login. Enable scheduled rotation only after those checks pass.

Do not run acceptance against a database role concurrently managed by another rotation integration. A successful local plan or signed OCIR token exchange does not verify authentication and Docker execution on the managed runner.
