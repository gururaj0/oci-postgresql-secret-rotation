# OCI PostgreSQL secret rotation

Customer-operated Python CLI, OCI Function, and Terraform modules for application-role credential rotation with OCI Vault. It uses publicly documented interfaces. It is a custom integration, not an Oracle-managed service, and carries no separate Oracle product SLA.

## Documentation

- [Deployment instructions](DEPLOYMENT.md)
- [Testing and acceptance](TESTING.md)
- [Console rotation](docs/console-rotation.md)
- [Security](SECURITY.md) and [recovery](docs/recovery-runbook.md)

**Version 0.1.1:** native Console/API rotation passed end-to-end with scheduling disabled. This remains a prerelease pending scheduled-run, customer application and production security acceptance.

## What is implemented

- Read-only, paginated discovery across subscribed regions and accessible compartments, including partial-access errors.
- Guided resource selection, verified TLS, secure terminal-only credential bootstrap, manual rotation and dry-run validation.
- Pending Vault versions, SQL identifier quoting, client-generated SCRAM verifiers, new-login verification, and conditional promotion.
- Durable Object Storage operation journal and atomic, non-expiring per-role lock, shared by local and Function executions.
- OCI Vault's four-step custom Function protocol and its native 1–360 day scheduler.
- Private Functions, restricted IAM, optional new Vault/key, logs, failure/overdue alarms, and an independent 15-minute monitoring schedule.
- Explicit recovery, failure injection tests, customer acceptance procedures and handoff documentation.

## Quick start

Requires Python 3.11+, OCI CLI default authentication, Terraform 1.6+, an OCI-compatible container build tool, OCIR access, and a deployment host with private connectivity to the database. Python 3.12 is the Function image baseline.

```bash
./install.sh
source .venv/bin/activate
pg-vault-rotation discover
pg-vault-rotation configure
pg-vault-rotation validate
pg-vault-rotation plan
# Review the complete plan and the identified tenancy/database/role first.
pg-vault-rotation deploy --confirm
pg-vault-rotation rotate --dry-run
pg-vault-rotation rotate --confirm
pg-vault-rotation status
```

Global `--config` and `--profile` options precede the subcommand. For example, `pg-vault-rotation --config customer.yaml status`.

Build/push the Function image as described in [installation](docs/installation.md). After deployment set `function_id` from the Terraform output. Validate application credential refresh, then enable the Vault schedule with `pg-vault-rotation schedule --confirm`. Deployment alone does not enable credential rotation.

## Validation and release status

The approved demo application-role rotation passed against OCI PostgreSQL 17 and Vault: repeated rotations, lock contention, interrupted promotion, same-operation recovery, surviving existing sessions and fresh CURRENT logins. The initial 34-test suite passed with live integration enabled. The current 37-test local suite passes with one opt-in private-network integration skip. See [validation evidence](docs/validation.md).

The delivery includes a resolved hashed dependency lock and Terraform provider lock. Clean installation, Ruff, dependency audit (no known vulnerabilities) and Terraform provider validation passed. The demo Function is now deployed and its resource-principal validation and four direct callbacks passed. Native Console/API rotation now passes: the Function returns the required `versionNo` response field, the service completes all four callbacks, and CURRENT authenticates a fresh TLS login. Container scanning retains unresolved OS findings. Periodic scheduled execution, notification delivery, a real Function hard-kill drill and customer application pool refresh remain acceptance gates. See [Console rotation](docs/console-rotation.md).

Administrator rotation is deliberately disabled. The public reset API exists, but it needs separate asynchronous work-request, recovery and production-approval tests. Alternating-user rotation is also gated until role grants and application username refresh are validated. This release supports self-rotation of one application role; it does not promise uninterrupted new connections between password update and secret promotion.

See [architecture and API evidence](docs/architecture.md), [recovery](docs/recovery-runbook.md), [operations](docs/operations.md), and the [customer handoff and acceptance matrix](docs/customer-handoff.md).
