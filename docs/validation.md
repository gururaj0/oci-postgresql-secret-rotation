# Implementation validation — 2026-10-15

Approved demo testing targeted DemoPostgreSQL 17 in Ashburn, database `postgres`, application role `demo`. A private versioned journal bucket was created. Admin was unchanged. No Function or automatic schedule was deployed.

## Passed

- 34 tests in the clean installed environment, including the real TLS/database integration test; no skips.
- Exact runtime SDK 2.188.0, resolved transitive hash lock installation and package/CLI installation in a fresh virtual environment.
- Ruff, source security guards, Python compilation, configuration checks and shell syntax checks.
- Terraform formatting and provider schema validation with locked OCI provider 9.9.0.
- Dependency audit of the resolved lock: no known vulnerabilities found. This does not replace container scanning.
- Repeated real application-role rotation through Vault versions 1 → 2 → 3 → 4. Final state COMPLETE; a separate fresh TLS login with CURRENT version 4 passed.
- Seven live acceptance checks: dry-run without mutation; competing lock rejected; database updated while Vault promotion was deliberately interrupted; existing database session survives; recovery reuses the same operation and pending version; refreshed CURRENT opens a new connection; journal contains neither tested password.

Promotion interruption was injected in the local adapter, not by modifying remote IAM. The recovery operation completed in about 17 seconds. Live service behavior also exposed asynchronous Vault updates and throttling; bounded lifecycle polling and HTTP 429 retries were added and tested. Unknown write outcomes are still reconciled rather than blindly retried.

Sanitized customer-specific evidence is outside the reusable package in `.local/live-acceptance.json`, `.local/live-test-summary.json` and `.local/dependency-audit.json`. The temporary SSH tunnel was closed after final verification. The initial demo password is no longer current; retrieve credentials from Vault.

## Remaining gates

Deploy and test the OCI Function with resource-principal IAM and private networking; exercise native Vault scheduling, monitoring and notification delivery; hard-kill a real Function and drill controlled lock recovery; build/scan the container; validate the customer's actual application pool/cache refresh. Administrator and alternating-user strategies remain disabled and require separate implementation. This validates the application-role path, not the entire PRD or production readiness.

## Console deployment follow-up — 2026-10-15

Deployed `pg-rotation-demo17` in Demo/Ashburn as an ARM Function with a private OCIR image, dedicated Function/database NSGs, secret-scoped dynamic groups/policy and invocation logging. Attached the database NSG without replacing existing access rules. Linked the secret to the Function with periodic rotation disabled.

Resource-principal validation and all four directly invoked Function callbacks passed: CURRENT advanced from 4 to 5, with a COMPLETE journal and verified database authentication. Two native Rotate API requests were accepted, invoked VERIFY_CONNECTION successfully, then returned to NOT_ENABLED without advancing CURRENT. Console orchestration acceptance remains unresolved; direct callback success is not equivalent to native rotation success.

Fixed OCI's separate image/digest API fields, the Monitoring SDK endpoint assignment and callback-stage diagnostics. The updated local suite has 35 tests (34 pass, one private-network integration skip); the deployed Function supplies additional real private-network validation. The final image was scanned: 44 HIGH, 58 MEDIUM, 61 LOW and one UNKNOWN OS-package findings, no CRITICAL findings or listed fixes; no Python-package findings. Production security acceptance remains open.

Deployment plans/state, image digests, scan results and sanitized callback evidence are in `.local/console-deployment/`. Preserve this directory to manage the deployed resources. No automatic rotation or monitoring schedule was created.

## Approved temporary-enable test — 2026-10-15

Temporarily enabled automatic rotation with a 360-day interval, submitted one native Rotate request, and restored the original 30-day interval with automatic rotation disabled in cleanup. The service accepted the request (HTTP 202), completed VERIFY_CONNECTION, and returned to SCHEDULED without creating a pending version or advancing CURRENT. After cleanup, automatic rotation was disabled and CURRENT remained 5. The enablement flag does not explain the observed behavior; native Console orchestration remains unresolved with either setting. Evidence: `.local/console-deployment/native-enabled-test.json`.
