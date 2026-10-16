# CLI deployment guide

For a browser-based deployment with no laptop tools or deployment VM, use the [Resource Manager button and guide](docs/resource-manager.md). The instructions below are the alternative CLI workflow.

Deploy the rotation Function and monitoring resources into your OCI tenancy, verify a manual password rotation, then enable automatic password rotation when your application is ready.

The standard Terraform deployment creates the Function, its application, IAM policies, invocation logs, a journal bucket by default, and an active monitoring schedule that runs every hour. Alarms are included when a Notifications topic is configured. Automatic password rotation is activated separately through OCI Vault in the final step below.

Manual rotation has been tested successfully against PostgreSQL 17. Follow the [testing guide](TESTING.md) and review [security findings](SECURITY.md) before production use.

## Choose your deployment host

**Recommended: an OCI Compute VM with private connectivity to the PostgreSQL database**, in the same VCN or a connected network. SSH to this VM and use it as the deployment host. This keeps live database validation and testing close to the private database without requiring a laptop tunnel.

Prepare this VM separately; this package does not create the deployment host. It needs DNS resolution and access to PostgreSQL on TCP/5432, OCI APIs, OCIR, and the dependency/container registries used during installation and image builds. Configure the prerequisites below, including your authorized OCI API profile and working Docker or Podman engine. Use an x86 host for the default `linux/amd64` image build, or a builder that supports that target architecture.

**Alternative: your laptop.** Run the same commands locally if you have the tools and OCI credentials, plus VPN access or an SSH tunnel for commands that connect to PostgreSQL. A laptop's ability to call OCI APIs alone does not provide private database access. With a tunnel, retain the database certificate's DNS hostname for TLS verification and keep tunnel settings only in your local validation configuration.

Use one deployment host and repository checkout for the initial workflow. After deployment, rotation and monitoring run in OCI, so this host can be stopped. Preserve the Terraform state and local configuration securely for updates or removal. The deployed Function requires its own private database connectivity regardless of which host you choose.

## Tasks and where to run them

| Task | Where to run it | What it does |
|---|---|---|
| Prepare database role, initial Vault secret and network access | OCI Console and an authorized database client with private connectivity | Establish the existing resources and matching initial credentials |
| Clone, install, discover and configure | Deployment host, from the repository root | Install the CLI and select your tenancy resources |
| Download the PostgreSQL CA certificate | OCI Console in your browser; save/transfer the file to the deployment host | Supply the trusted public CA for TLS verification |
| Build and push the Function image | Deployment host with Docker/Podman and OCIR push access | Package the code and CA certificate and publish the image |
| Run `plan` and `deploy --confirm` | Deployment host, from the repository root | Run Terraform locally to provision resources in OCI |
| Run local unit tests | Deployment host or laptop | Check code without connecting to the database |
| Run CLI `validate`, `rotate --dry-run` and live acceptance tests | Deployment host with private database connectivity | Open fresh TLS connections; approved rotation tests also change the password |
| Link the Function and enable/disable rotation scheduling | Deployment host using the CLI and OCI API access | Configure the secret's rotation target and native Vault schedule |
| Select **Rotate** | OCI Console in your browser | Ask Secret Service to invoke the deployed Function |
| Update the password and verify it during hosted rotation | OCI Function, automatically | Connect to PostgreSQL privately and promote the verified Vault version |
| Check automatic rotation and monitoring | OCI Vault and Resource Scheduler, automatically | Vault triggers password rotation; the separate hourly job checks health |
| Verify application credential refresh | Your application's runtime environment | Fetch CURRENT and open a new database connection |

## Prerequisites

- Python 3.11+ (Function image uses Python 3.12), Terraform 1.6+, OCI CLI/API credentials and Docker or Podman.
- OCI PostgreSQL application LOGIN role and an existing password stored in Vault as JSON containing exactly `username` and `password`.
- Private database connectivity, the certificate's DNS hostname and a trusted PostgreSQL CA bundle.
- A private, versioned Object Storage journal bucket, or approval for Terraform to create one.
- OCIR push access and permission to create Functions, IAM policies/dynamic groups, logs and networking resources.

## Install and configure

Run on your chosen deployment host. All shell commands below start from the cloned repository root unless stated otherwise.

```bash
git clone https://github.com/gururaj0/oci-postgresql-secret-rotation.git
cd oci-postgresql-secret-rotation
./install.sh
source .venv/bin/activate
pg-vault-rotation discover
cp config.example.yaml rotation.yaml
```

Replace all example values in `rotation.yaml`, or use `configure` instead of copying the example. Keep passwords in Vault, never in YAML or Terraform. Use an application role rather than the managed administrator. The [installation guide](docs/installation.md) explains secure initial-secret creation.

## Obtain the PostgreSQL CA certificate

The deployment operator downloads the CA certificate supplied by OCI for the selected database system. **Do not generate a new certificate or a private key for this step.** The Function uses this public CA certificate to verify the database server's identity.

1. In OCI Console, open **Databases → PostgreSQL → DB Systems** and select your database system.
2. Under **Connection details**, note the database FQDN and download the CA certificate.
3. On the deployment host, create `certs/` inside the cloned repository and save the downloaded certificate as `certs/postgresql-ca.pem`. If you downloaded it on your laptop, transfer it to this location on the VM.
4. In local `rotation.yaml`, set `ca_file` to the absolute path of that file and use the database's certificate hostname. In `rotation.function.yaml`, use `ca_file: /function/certs/postgresql-ca.pem`.

See Oracle's [database connection instructions](https://docs.oracle.com/en-us/iaas/Content/postgresql/connect-to-db.htm). The local `certs/` directory is ignored by Git; the next step includes the certificate in your Function image. If the trusted database CA changes, update the bundle and rebuild/redeploy the image.

## Build the Function image

Run on the deployment host. Add this line to the Dockerfile before `USER 10001` to include the downloaded CA:

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

**Terraform runs on your deployment host.** The CLI invokes Terraform against this repository's `terraform/` directory and uses your OCI credentials to create the cloud resources. Terraform provisions infrastructure; the deployed Function performs password changes at runtime. Building/pushing the image and enabling native Vault password rotation are separate steps in this guide.

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

The hourly monitoring schedule remains active. To change the password-rotation interval, update `rotation_days` and rerun `schedule --confirm`.

## Rotate on demand

Once the secret is linked to the Function, select **Rotate** on its OCI Console details page. Verify that the secret has a newer CURRENT version and that your application can open a new database connection. See [Console rotation](docs/console-rotation.md) for manual-only configuration and [Testing](TESTING.md) for acceptance checks.

See [recovery](docs/recovery-runbook.md), [operations](docs/operations.md), and [IAM](docs/iam-policies.md) before operational handoff.
