# Console rotation deployment

For PostgreSQL, configure the secret's rotation target as the deployed custom Function. The Function uses its resource principal, private network access and the same journal bucket as the CLI. A local SSH tunnel is unnecessary for Console rotation.

## Deployment requirements

- Build an image with the database CA at the configured path. Use port 5432 and the database certificate hostname, not the local tunnel port.
- Match the Function application's architecture to the image. The Function Terraform module supports `shape` and `network_security_group_ids`.
- Pin the image with `repository:tag@sha256:digest`. OCI requires the image name and digest as separate API fields; the module separates them.
- Grant the Function access only to the selected secret, journal bucket and monitoring namespace. Permit the selected secret to invoke the Function.
- Use an ingress rule from the Function NSG to a database NSG on TCP/5432; preserve the database's existing NSG attachments.
- Enable invocation logs. Validate the Function with `{"action":"validate"}` before linking the secret.
- Set `rotation_config.target_system_details` to `FunctionTargetSystemDetails(function_id=...)` and `is_scheduled_rotation_enabled=false` for manual-only operation. The package's `schedule` command enables periodic rotation and should not be used for this purpose.

## Manual acceptance

Open the selected secret in OCI Console, confirm its Function target, record CURRENT, then use Rotate. A successful test must create a newer CURRENT version, complete the durable journal and authenticate a fresh database connection with that version. An accepted HTTP 202 alone is not success. Inspect Function stage logs and Secret Service status if the version does not advance.

The Function exposes the four native callbacks: VERIFY_CONNECTION, CREATE_PENDING_VERSION, UPDATE_TARGET_SYSTEM and PROMOTE_PENDING_VERSION. Directly exercising them proves the Function implementation and permissions, but does not by itself prove the Console/Secret Service orchestration path.

Do not run local rotation concurrently with a service-driven rotation. If an invocation is interrupted, inspect the journal and use the recovery runbook; never delete the pending version or reset the journal.

## Current demo acceptance limitation

The deployed Function passes all four directly invoked callbacks. Native Rotate requests currently stop after successful VERIFY_CONNECTION with either automatic-rotation setting. A customer-approved temporary 360-day enablement test did not change that result and was reverted. Treat the Console workflow as an unresolved acceptance item, not a demonstrated end-to-end capability. Automatic rotation remains disabled; CURRENT version 5 and the completed journal remain consistent.
