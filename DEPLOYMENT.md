# Deployment guide

This is an application-role rotation implementation candidate. Local rotation and directly invoked OCI Function callbacks were tested against PostgreSQL 17. Native Secret Service/Console rotation passed end-to-end in version 0.1.1 with periodic scheduling disabled. Complete scheduled-run and application acceptance before enabling unattended rotation. See [validation](docs/validation.md) and [security findings](SECURITY.md).

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

## Console and scheduling

See [Console rotation](docs/console-rotation.md) for Function-target binding and native acceptance checks. Keep automatic rotation disabled until your own native and application acceptance passes. The `schedule --confirm` command enables periodic rotation; `unschedule --confirm` disables it. Do not treat an accepted Rotate request as proof of password rotation: confirm a newer CURRENT version, a COMPLETE journal and a fresh successful database login.

See [recovery](docs/recovery-runbook.md), [operations](docs/operations.md), and [IAM](docs/iam-policies.md) before operational handoff.
