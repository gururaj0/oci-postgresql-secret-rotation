# Deployment guide

Deploy the rotation Function and monitoring resources into your OCI tenancy, verify a manual password rotation, then enable automatic password rotation when your application is ready.

The standard Terraform deployment creates the Function, its application, IAM policies, invocation logs, a journal bucket by default, and an active monitoring schedule that runs every 15 minutes. Alarms are included when a Notifications topic is configured. Automatic password rotation is activated separately through OCI Vault in the final step below.

Manual rotation has been tested successfully against PostgreSQL 17. Follow the [testing guide](TESTING.md) and review [security findings](SECURITY.md) before production use.

## Prerequisites

- Python 3.11+ (Function image uses Python 3.12), Terraform 1.6+, OCI CLI/API credentials and Docker or Podman.
- OCI PostgreSQL application LOGIN role and an existing password stored in Vault as JSON containing exactly `username` and `password`.
- Private database connectivity, the certificate's DNS hostname and a trusted PostgreSQL CA bundle.
- A private, versioned Object Storage journal bucket, or approval for Terraform to create one.
- OCIR push access and permission to create Functions, IAM policies/dynamic groups, logs and networking resources.

## Install and configure

```bash
git clone https://github.com/gururaj0/oci-postgresql-secret-rotation.git
cd oci-postgresql-secret-rotation
./install.sh
source .venv/bin/activate
pg-vault-rotation discover
cp config.example.yaml rotation.yaml
```

Replace all example values in `rotation.yaml`, or use `configure` instead of copying the example. Keep passwords in Vault, never in YAML or Terraform. Use an application role rather than the managed administrator. The [installation guide](docs/installation.md) explains secure initial-secret creation.

## Build the Function image

Copy the trusted public database CA into a local `certs/postgresql-ca.pem` file and add this line to the Dockerfile before `USER 10001`:

```dockerfile
COPY certs/postgresql-ca.pem /function/certs/postgresql-ca.pem
```

Build from the repository root, authenticate to OCIR using your own credentials, and push:

```bash
# Replace with your private OCIR repository.
IMAGE='iad.ocir.io/YOUR_NAMESPACE/YOUR_REPOSITORY:0.1.1'
docker build --platform linux/amd64 -f functions/vault_rotation/Dockerfile -t "$IMAGE" .
docker push "$IMAGE"
docker image inspect "$IMAGE" --format '{{index .RepoDigests 0}}'
```

Record the image as `repository:tag@sha256:DIGEST` in configuration. The default Terraform application uses GENERIC_X86, matching the command above. For ARM, build `linux/arm64` and explicitly pass `shape = "GENERIC_ARM"` to the Function module in your Terraform composition.

## Plan and deploy

Maintain two ignored local configurations if needed: `rotation.yaml` for local validation and `rotation.function.yaml` for deployment. The latter must use the real database port (usually 5432), its certificate hostname, and the container CA path `/function/certs/postgresql-ca.pem`. Never deploy a localhost SSH-tunnel port or workstation CA path.

```bash
pg-vault-rotation --config rotation.yaml validate
pg-vault-rotation --config rotation.function.yaml plan
# Inspect the plan, tenancy, database, role, permissions and costs.
pg-vault-rotation --config rotation.function.yaml deploy --confirm
```

Run these commands from the source repository so Terraform files are available. The standard root deployment creates a read-only monitoring schedule, but does not enable password rotation. For an existing bucket, set `create_state_bucket=false` in a local Terraform variable file. Preserve and protect Terraform state.

The existing subnet must provide OCI API access and PostgreSQL connectivity. The Function module accepts `network_security_group_ids`; provision a database ingress rule allowing the Function NSG on TCP/5432 and preserve existing database NSG attachments. The default network module validates the selected private subnet; it does not create database ingress rules.

Set `function_id` from Terraform output and invoke the Function with `{"action":"validate"}` to verify resource-principal access and TLS authentication. Complete the [testing guide](TESTING.md) before enabling automation.

## Enable automatic password rotation

After deployment, record the Function OCID from `terraform output function_id` (run from the `terraform` directory) in the `function_id` field of `rotation.function.yaml`. Set `rotation_days` to your required interval; the CLI accepts 1–360 days.

Complete manual rotation and application credential-refresh testing first. Then run:

```bash
pg-vault-rotation --config rotation.function.yaml schedule --confirm
pg-vault-rotation --config rotation.function.yaml status
```

The schedule command validates the deployed Function, links it to the selected Vault secret and enables OCI Vault's native rotation schedule. Check the reported next scheduled time and observe the first scheduled rotation. This step does not create another Resource Scheduler job: Vault controls the password-rotation interval.

To disable automatic password rotation:

```bash
pg-vault-rotation --config rotation.function.yaml unschedule --confirm
pg-vault-rotation --config rotation.function.yaml status
```

The 15-minute monitoring schedule remains active. To change the password-rotation interval, update `rotation_days` and rerun `schedule --confirm`.

## Rotate on demand

Once the secret is linked to the Function, select **Rotate** on its OCI Console details page. Verify that the secret has a newer CURRENT version and that your application can open a new database connection. See [Console rotation](docs/console-rotation.md) for manual-only configuration and [Testing](TESTING.md) for acceptance checks.

See [recovery](docs/recovery-runbook.md), [operations](docs/operations.md), and [IAM](docs/iam-policies.md) before operational handoff.
