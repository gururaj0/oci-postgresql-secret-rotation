# Operations

The customer owns deployment, rotation intervals, image patching, IAM, Vault administration, monitoring, application refresh and incident response. This is a customer-operated integration. Record on-call contacts, approved maintenance windows and recovery authority before scheduling.

Use `rotate --dry-run` for read-only TLS/current-login checks. `rotate --confirm` starts or resumes one operation. `status` reads the durable state, Vault current version and next scheduled rotation. Each mutation displays tenancy, region, DB and role; confirm them against the change record. Manual CLI rotation must run from the private network and shares the Function's journal bucket.

The Function logs operation UUID and state transitions. Never enable SDK wire logging or SQL statement logging in this process. An independent hourly monitor action posts state, last-success timestamp, next schedule, duration, failure count, pending age, verification failure and reconciliation-required metrics. Overdue means last success (or initial secret creation before the first success) exceeds the configured interval by one hour. Failure and overdue alarms require a Notifications topic; a missing-heartbeat alarm catches a broken monitor. Review per-DB/role metric dimensions when serving multiple deployments. Topic subscription and delivery acceptance are customer responsibilities.

Applications should retrieve the Vault bundle at stage `CURRENT`, decode JSON in memory and refresh both connection factory credentials and cached secret values. On a new-connection authentication error, invalidate the cached secret, fetch CURRENT again and retry with a bounded backoff. Keep existing healthy pool connections; do not terminate sessions just to rotate. Ensure refresh completes after promotion and test application-specific retry bounds during the short update/promotion gap.

Validate refresh with a real application: warm a pool, rotate in acceptance, force a new physical connection, assert a normal query succeeds, and verify the application's cached version equals Vault CURRENT. Repeat with stale cached credentials, pool recycling and transient Vault failures. No zero-downtime claim is made until this passes for the customer's application.

Vault version quotas need maintenance. Retain current, previous and any operation-referenced pending versions. Archive journal versions under the customer's audit policy. Delete only approved deprecated Vault versions after confirming no incomplete operation references them. Cleanup is intentionally not automatic.

Upgrade by disabling rotation, confirming no live operation, reviewing new dependency/provider/image locks, running failure tests and acceptance, and deploying the approved immutable image. Re-enable schedules after a recovery drill. If a new image fails, redeploy the prior image with the same journal/config; never reset the journal to make a rotation appear complete.
