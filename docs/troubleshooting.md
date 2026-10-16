# Troubleshooting

| Symptom | Action |
|---|---|
| Discovery has errors or misses a compartment | Verify profile/region subscription, inspect reported status/classification, ask the IAM owner for specific read access; rerun discovery. Do not infer resource absence from a failed query. |
| Package/registry download times out | Restore DNS/egress to the customer's approved PyPI and Terraform mirrors. Do not bypass TLS. Run release checks after connectivity is restored. |
| TLS hostname or CA error | Use the database certificate hostname, verify private DNS and approved CA path in both local host and image. |
| Database unavailable | Confirm routes/NSGs and health; current working credential is preserved if the update has not committed. Reconcile if state is uncertain. |
| Unrelated pending Vault version | Investigate its owner and database state before proceeding; never overwrite it automatically. |
| Role locked after Function timeout | Follow the stopped-invocation verification in the recovery runbook; locks intentionally do not expire. |
| State VERIFIED but Vault CURRENT old | Pending has been verified; restore Vault access and reconcile to promote that exact version. |
| Secret update returns conflict | Investigate external changes or concurrent operators. Do not retry with a newly generated password. |
| Admin role rejected | Administrator rotation is a separately gated ResetMasterUserPassword strategy, not SQL self-rotation. |
| Heartbeat absent | Check monitor schedule, schedule dynamic group, Function errors, resource-principal access and telemetry egress. |
| New application connections fail | Refresh CURRENT and recreate the connection factory with the returned credentials; test bounded retry and inspect rotation state. |

Safe escalation evidence: release/image digest, OCI request/operation correlation IDs, state/version numbers, timestamps and error classification. Never enable verbose raw exception or wire logging to gather a customer support bundle.
