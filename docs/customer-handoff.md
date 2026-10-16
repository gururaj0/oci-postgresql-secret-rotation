# Customer handoff and acceptance

Status: application-role implementation live-tested, 2026-10-15. Approved demo testing created a private versioned journal bucket and rotated `demo` on PostgreSQL 17 through Vault CURRENT version 4. Admin was unchanged. A later approved Console deployment created the Function, IAM, NSGs and logs; direct callbacks advanced CURRENT to 5. Native Console/API orchestration remains unresolved; no schedule was enabled. Customer identifiers and evidence stay in `.local/` outside this reusable package. See [validation](validation.md).

| PRD acceptance area | Evidence / remaining gate |
|---|---|
| Read-only discovery, region coverage | Exercised default profile, region subscriptions, accessible compartments and DB listing across Ashburn/Chicago; full inventory may contain explicit endpoint-access errors. |
| Interactive selection | Guided CLI implemented; operator selected the discovered PostgreSQL 17 target in chat. Role, database, CA and Vault secret configured for local demo testing; Function image/deployment settings remain pending. |
| App/manual rotation, repeated runs | Repeated approved live demo rotations passed; final CURRENT version 5 authenticates through the deployed Function. |
| Scheduled rotation | Vault protocol and duplicate-callback tests pass; deployed direct callbacks pass; native Rotate stops after VERIFY_CONNECTION with scheduling either enabled or disabled. The approved temporary-enable test was reverted; automatic rotation remains disabled. Periodic scheduling remains untested. |
| Active secret authentication | Fresh TLS authentication with real Vault CURRENT passed, including the integration test. |
| Concurrency and partial failure | Real lock contention and injected promotion interruption/recovery passed; other failure cases covered locally. |
| Timeout recovery | Persistent-lock behavior and same-operation resume tested; hard-kill a real Function during acceptance and drill controlled unlock. |
| Credential exposure | Source guards and metadata/log assertions pass; complete database logging and image/state inspection in acceptance. |
| Application refresh | Existing session and refreshed new connection passed; actual customer application/pool test still required. |
| Dependency/security scan | Source guards and resolved dependency audit passed with no known vulnerabilities; container scan completed with unresolved OS-package findings (44 HIGH); production security acceptance remains open. |
| Clean installation/provider validation | Clean hashed-lock/package installation and locked OCI provider 9.9.0 validation passed. |
| Administrator/alternating-user | Disabled; separate implementations and recovery/approval tests required before enablement. |

## Approved acceptance drill

Use a nonproduction DB, dedicated application role/secret/journal bucket and application replica first. Review the plan and explicit rotation approval. Run dry-run, manually rotate twice, prove CURRENT opens new TLS sessions and the application refreshes correctly. Enable a one-day Vault schedule and observe a full scheduled run, correct stage progression and its next scheduled time.

Run concurrent invocations and assert only one owns the role lock. Revoke Vault update permission after the database changes, confirm CURRENT stays old and the journal stays recoverable, restore access and reconcile. Kill a Function after SQL commit but before journal advancement, verify the lock remains and follow the stopped-invocation recovery drill. Test denied Vault reads before update, database unavailability, rejected ALTER, invalid pending login, monitoring failure and overdue/heartbeat notifications. Compare journal versions and OCI audit evidence; no new credential may be generated while an incomplete operation exists.

Record test date, operator, target, operation IDs, image/dependency/provider digests, actual versus expected results and recovery duration. Inspect captured application/Function/database logs and Terraform state for credential content using secure local tools. Complete application-specific connection-pool and secret-cache validation. Production scheduling requires customer signoff of all applicable gates.

The customer assigns named owners for deployment/IAM, Vault/key lifecycle, Function upgrades, monitoring/on-call, application refresh and recovery. Engineering handoff is limited to the agreed implementation scope. Customer operations, product SLA and support arrangements are not implicitly transferred to Oracle Engineering.
