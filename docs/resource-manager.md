# Deploy from your browser with OCI Resource Manager

Use this stack to deploy the rotation integration into your own tenancy for an **existing PostgreSQL database and Vault credential secret**. Terraform runs on OCI Resource Manager's managed host. You do not install Terraform, Python or Docker on your laptop, create a deployment VM, build an image manually or download a CA certificate.

**Release candidate:** the package passes local Terraform validation, a read-only plan against the demo tenancy, and automated helper tests. The signed OCIR token exchange has been tested. An end-to-end Apply on the managed Resource Manager runner is still required before customer acceptance. Existing native password rotation was tested separately; it does not establish that this new deployment path works end to end.

[![Deploy to Oracle Cloud](https://oci-resourcemanager-plugin.plugins.oci.oraclecloud.com/latest/deploy-to-oracle-cloud.svg)](https://cloud.oracle.com/resourcemanager/stacks/create?zipUrl=https%3A%2F%2Fgithub.com%2Fgururaj0%2Foci-postgresql-secret-rotation%2Freleases%2Fdownload%2Fresource-manager-v0.1.0-rc.1%2Fresource-manager.zip)

## Before you click

Have these existing resources ready in a commercial OCI region:

- An ACTIVE OCI PostgreSQL DB system and an application LOGIN role. The deployment compartment must contain this DB system. Managed-administrator rotation is not supported.
- A source Vault secret in the deployment region, holding JSON with exactly `username` and `password`, matching the application's current database credentials. No password is entered into the stack form.
- A private Function subnet in the database's VCN, with working DNS and routes to the database and OCI services, including OCIR, Vault, Object Storage and Monitoring. Configure service gateway/NAT access as appropriate for your VCN.
- An existing NSG attached to the database. The stack adds its own ingress rule to this NSG, preserving existing rules and attachments.
- An operator allowed to create Resource Manager stacks/jobs, Functions, private OCIR repositories, buckets, NSGs/rules, logs, schedules, dynamic groups and policies. The operator also needs read access to database connection details, secret metadata and tenancy/region information; permission to update the selected secret's rotation settings; and permission to invoke the Function and push the image. IAM resources are created in the tenancy's home region. Have your tenancy administrator review these permissions.
- Optionally, a Notifications topic with confirmed subscriptions for monitoring alarms.

Use a unique deployment name. Do not deploy another independent rotation integration against a role already managed by an active integration. The stack refuses to replace a different Function already linked to the selected secret.

## Customer steps

1. Select **Deploy to Oracle Cloud** above. Sign in to the intended tenancy and select the deployment region. The button opens **Create stack** with the release ZIP selected.
2. Choose Terraform **1.5.x** and name the stack.
3. Complete the form: deployment compartment and name, DB system OCID, database name, application role, existing secret OCID, private subnet OCID and database NSG OCID. The tenancy and region come from Resource Manager.
4. Leave **Enable automatic password rotation** off for initial testing. The separate 15-minute health monitor is deployed and enabled regardless of this setting.
5. Review the selected resources, IAM changes and costs. Select **Run apply** and create the stack, or create it first and review a Plan job before starting Apply.
6. Wait for the Apply job to succeed. The job builds the image, so the first deployment can take several minutes. Review its outputs for the Function OCID, image digest and selected secret.
7. Open the selected Vault secret in OCI Console and select **Rotate**. Confirm a newer CURRENT version and test a fresh application login using that credential. Applications must refresh cached credentials for new connections.
8. After manual and application testing, edit the stack variables, enable automatic rotation, choose the interval and run Apply again. Verify the secret's next scheduled rotation time and observe the first scheduled execution.

Turning automatic rotation off and applying again disables the native Vault schedule. The read-only monitoring schedule remains active. Apply itself does not perform a password rotation; enabling a schedule authorizes subsequent scheduled rotations.

## What runs where

| Task | Execution location |
|---|---|
| Choose resources and start deployment | Customer's browser, OCI Console |
| Terraform plan/apply and managed state | OCI Resource Manager |
| Retrieve the database's public CA certificate | Terraform reads OCI PostgreSQL connection details |
| Build and push the container image | Docker on the Resource Manager job host; private OCIR repository in the customer tenancy |
| Authenticate the image push | Temporary OCIR token obtained using the job's OCI identity; no user auth token input |
| Validate the current password with a fresh TLS login | Deployed OCI Function, inside the private network |
| Link the secret and optionally enable automatic rotation | Apply helper on the Resource Manager host, after Function validation |
| Rotate the database password and promote the Vault version | OCI Function invoked by Secret Service |
| Trigger automatic password rotation | OCI Vault's native schedule |
| Check rotation health every 15 minutes | OCI Resource Scheduler invokes the Function's monitor action |

## Created resources and existing resources

The stack creates a private OCIR repository and image, Functions application and Function, private versioned recovery journal bucket, Function NSG, database ingress rule, IAM policies/dynamic groups, invocation logs and a monitoring schedule. Alarms are optional when a Notifications topic is supplied.

The database, application role, Vault secret, VCN, subnet, routes and attached database NSG remain customer prerequisites. The stack updates only the selected secret's rotation configuration and adds its own database ingress rule. It does not import the database or credential secret into Terraform ownership. Credential values are not placed in Terraform variables, state, job logs or the image; the public CA certificate and resource identifiers are included where needed.

## Updates, recovery and removal

- Keep and reuse the same Resource Manager stack for updates. Its state tracks the deployed resources. Do not create a replacement stack with the same names.
- To refresh the image's base packages, increment **Image rebuild revision** and Apply. Source and CA changes also trigger an image rebuild when applying an updated package. The Function is deployed by image digest.
- If build/push fails, check OCIR permissions, runner authentication and access to Docker Hub/Python package registries. The helper suppresses raw credential-bearing CLI errors. Do not enable debug logging for signed requests.
- If Function validation fails, rotation settings remain unchanged. Inspect Function invocation logs, IAM propagation, routes, NSGs, the CA/hostname and whether the existing secret matches the database role; then Apply again. Helpers only retry read-only validation, not password changes.
- If the final secret update times out, inspect the secret's rotation configuration before reapplying. Updates use the current ETag and refuse a different existing rotation target.
- Changes made directly to the secret outside this stack are not continuously reconciled by Terraform. To re-run linking/validation after an intentional Console change, update the relevant rotation setting or the image rebuild revision, then Apply.
- Before removal, disable automatic rotation and unlink this custom Function from the secret in Console. Preserve the recovery journal until every operation is complete. The journal has `prevent_destroy`, so a normal Destroy job is deliberately blocked. An operator must explicitly resolve journal retention and remove that protection in a reviewed stack update before teardown. The existing database and secret are not deleted by this stack.

Follow [Testing](../TESTING.md), [operations](operations.md), [recovery](recovery-runbook.md) and the existing [security findings](../SECURITY.md) before production use.

## Maintainer packaging and validation

The downloadable ZIP contains a Terraform root, form schema, shared modules, apply helpers and an allowlisted copy of the Function source. Local YAML, credentials, certificates, Terraform state and build caches are excluded.

```bash
python3 scripts/package-resource-manager.py --output dist/resource-manager.zip
# Extract to a clean directory, then run Terraform init, validate and plan there.
PYTHONPATH=src python -m unittest tests.test_resource_manager -v
```

The source under `resource-manager/` is a packaging input; use the assembled ZIP for Resource Manager. This avoids assuming Terraform can access files outside its uploaded configuration.

Oracle references: [Deploy button](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Tasks/deploybutton.htm), [managed host tools](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformhost.htm), [supported Terraform versions](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Reference/terraformversions.htm), [form schemas](https://docs.oracle.com/en-us/iaas/Content/ResourceManager/Concepts/terraformconfigresourcemanager_topic-schema.htm).
