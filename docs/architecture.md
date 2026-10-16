# Architecture decision: custom Function target

Decision date: 2026-10-15. Use OCI Vault's **FUNCTION** target with customer-owned PostgreSQL logic. Do not use the Autonomous Database target for PostgreSQL. The Vault scheduler invokes four stages; the engine persists its finer-grained states between callbacks. Manual rotations use exactly the same engine, journal and role lock.

```text
Vault native scheduler -> resource-principal Function -> private PostgreSQL
                              |              |
                              v              v
                    Vault pending/current   verified new login
                              |
                     Object Storage CAS journal

Resource Scheduler (15 min) -> Function monitor action -> metrics -> alarms / topic
```

The database credential and Vault promotion cannot commit atomically. The journal records an operation before creating a version, and uses the operation UUID as its version name. It records the pending version before updating PostgreSQL. A retry first probes that exact pending credential, then the old credential. A successful pending login proves an interrupted update completed. Promotion checks the expected Vault current version using an ETag. No automatic password rollback is attempted.

States are `PRECHECK`, `PREPARED`, `DATABASE_UPDATED`, `VERIFIED`, `VAULT_PROMOTED`, `COMPLETE`. Journal entries contain only target/role identifiers, version numbers, timestamps, retry/failure counts and classifications. Object versioning retains earlier snapshots; OCI Logging supplies correlation IDs. A non-expiring conditional-create lock prevents overlapping invocations. Only an operator who has stopped the previous invocation may remove an abandoned lock.

## Public API evidence

Oracle documents the [four Function stages](https://docs.oracle.com/en-us/iaas/Content/secret-management/Concepts/manage-secrets.htm), but its prose and examples use inconsistent version-field names. The [reference Java Function](https://github.com/tstahl/oci-rotate-secret-fn/blob/06b55ddd45daa8e86f5cbdfdf791071721b37099/src/main/java/com/oracle/bmc/ocisms/fn/CustomRotateFunction.java) uses `versionNo` in both input and output. Version 0.1.1 emits `versionNo` in every successful response; it accepts `currentVersionNo` only as an input compatibility alias and rejects conflicting values. The handler pins `secretId` to deployment configuration. Create returns the base version; update returns the verified pending version for promotion. The earlier response field `currentVersionNo` caused native orchestration to stop after VERIFY_CONNECTION. Tests now check the exact serialized response fields and carry `versionNo` into each subsequent request without renaming it.

[UpdateSecret](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/vault/client/oci.vault.VaultsClient.html) creates a version when updating content and promotes a version through `current_version_number`. These are separate updates. [SecretContentDetails](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/vault/models/oci.vault.models.SecretContentDetails.html) supports `PENDING` on updates. Version names let a retry recover a lost create response. [RotationConfig](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/vault/models/oci.vault.models.RotationConfig.html) supports a Function target and `P1D` through `P360D` intervals.

The schedule proposal is a Terraform output; `schedule --confirm` applies it with the SDK. Existing customer secret content is never imported into Terraform state. The monitoring schedule is an actual Terraform-managed [Resource Scheduler Function schedule](https://docs.oracle.com/en-us/iaas/Content/Functions/Tasks/functionsscheduling.htm).

The PostgreSQL managed-administrator API is [ResetMasterUserPassword](https://docs.oracle.com/en-us/iaas/Content/postgresql/reset-db-admin-credentials.htm), exposed by `oci.psql.PostgresqlClient.reset_master_user_password`. It is not enabled here. Production enablement requires Vault-reference password details, asynchronous work-request persistence and polling, an explicitly approved recovery drill and separate acceptance tests. Do not substitute SQL for the managed administrator API.

The SQL adapter uses psycopg's [libpq password encryption](https://www.psycopg.org/psycopg3/docs/api/pq.html) and composable SQL quoting. It authenticates as the application role and changes only its own password, so it needs no broad CREATEROLE privilege. OCI-managed administrator role membership is rejected.

## Availability and boundaries

Existing PostgreSQL sessions are not terminated. A single role's old password stops accepting new connections before Vault promotion, so applications need refresh/retry behavior. Continuous new-connection availability requires a separately validated alternating-user strategy: two equivalent login roles, immutable shared privilege role, a privileged rotation actor, and application refresh of both username and password. That strategy is rejected by this release until its grant-equivalence and recovery tests exist.

Uncoordinated external password/secret updates, changing the journal bucket, deleting versions needed by an operation, or forcibly removing a live lock violate the coordination model. Cloud end-to-end tests must confirm callback behavior, endpoint connectivity, IAM conditions and application integration for each customer region and release.
