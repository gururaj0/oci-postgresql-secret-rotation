# Validation — 2026-10-15

## Current result: native Console/API rotation passes in 0.1.1

The demo Function was updated with the corrected `versionNo` response field and tested through OCI Vault's native Rotate API, which backs the Console button. Automatic rotation stayed disabled throughout. Secret Service completed the four callbacks; CURRENT advanced from 5 to 6, the journal reached COMPLETE, and a separate Function validation verified a fresh PostgreSQL TLS login with CURRENT. Admin was unchanged. This was an API-level test, not a browser click test.

The root cause was a wire-response mismatch: version 0.1.0 emitted `currentVersionNo`. The [reference Java Function](https://github.com/tstahl/oci-rotate-secret-fn/blob/06b55ddd45daa8e86f5cbdfdf791071721b37099/src/main/java/com/oracle/bmc/ocisms/fn/CustomRotateFunction.java) emits `versionNo`. Our earlier unit test renamed the response field before submitting the next callback, hiding the interoperability defect. Tests now assert the exact response fields and round-trip the native version field without renaming it. The reference's OAuth-specific credential logic was not copied into this PostgreSQL implementation.

## Executed checks

- Version 0.1.1 local suite: 37 tests, 36 pass and one opt-in private-network integration skip. New cases verify the wire response, compatibility input alias and rejection of conflicting version fields.
- Initial configured live suite: all 34 then-existing tests passed, including private-network integration.
- Ruff, source security guards and Terraform formatting passed. Exact SDK 2.188.0, resolved hash-lock clean installation and provider 9.9.0 schema validation passed during initial acceptance.
- Repeated real local rotations, concurrency rejection, injected interrupted-promotion recovery using the same operation/version, surviving existing sessions, refreshed CURRENT login and journal password-exclusion checks passed.
- Deployed resource-principal Function validation and four direct callbacks passed. Version 0.1.1 additionally passed native orchestration with scheduling disabled.
- Runtime dependency audit found no known vulnerabilities at the recorded scan date. Container scanning retains OS findings; see SECURITY.md. These are separate checks.

## Earlier diagnosis, now resolved

Version 0.1.0 native requests stopped after successful VERIFY_CONNECTION. A separately approved temporary 360-day enablement test produced the same result; automatic rotation was immediately disabled again. The successful 0.1.1 test confirms the response-field correction resolves native orchestration without enabling scheduling.

Customer-specific evidence is excluded from the public release. Local evidence includes `.local/console-deployment/native-rotation-0.1.1.json`, deployment plans/state, image digests and scan reports. Preserve the deployment state to manage customer resources.

## Remaining gates

Periodic scheduled execution, notification delivery, hard-kill recovery of a real Function, and customer application connection-pool/cache refresh remain acceptance items. Container OS findings require production security review. Administrator and alternating-user strategies remain disabled and need separate implementation. The application-role path is live-tested; this does not imply complete PRD or production acceptance.

## Resource Manager deployment — 2026-10-15

The release-candidate stack was uploaded to OCI Resource Manager and tested through its managed Plan and Apply APIs, using the same ZIP linked by the deployment button. The public download was independently fetched without authentication and its checksum verified. The Console wizard was not exercised through a browser click.

- Managed Terraform 1.5.x Plan and Apply: passed. Image build and private OCIR push ran on the managed host using temporary registry authentication.
- Native ARM image metadata selected the matching Function shape automatically. The deployed Function authenticated a fresh TLS database connection using Vault CURRENT.
- The secret was temporarily linked to the new Function with automatic password rotation disabled, then its original target was restored. CURRENT stayed at version 6; this deployment test did not rotate the database password.
- The hourly Resource Scheduler monitor executed successfully. Its test window was temporarily advanced, and normal hourly timing was restored afterward.
- The final managed Plan reported **No changes**. The existing database password was absent from successful Apply state and job logs.
- Current automated suite: 46 tests, 45 passed and one opt-in private-network integration skip. Ruff, source guards, Terraform formatting, and Terraform 1.5.7/provider validation passed.

Managed-host testing identified and corrected two deployment assumptions: the runner uses a native ARM builder, and Resource Scheduler's minimum interval is one hour. The stack now selects the Function shape from the published image, uses an hourly monitor, and preserves the scheduler's JSON-text BODY representation to avoid repeat-plan changes. The CLI Terraform path also uses the supported hourly monitor and a two-hour heartbeat alarm window.

This validates infrastructure deployment and a scheduled **read-only health check**. It does not validate periodic password rotation, customer connection-pool refresh, notification delivery or production suitability of the newly built container image. Those remain customer acceptance checks. Native password rotation of the unchanged Function implementation was tested separately as described above.
