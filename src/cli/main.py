import argparse
from dataclasses import asdict
import json
import logging
from pathlib import Path
import subprocess
import sys

import oci

from cli.config import Config
from cli.runtime import clients, preflight, runtime
from discovery.client import discover
from rotation.model import RotationError


def show(value):
    print(json.dumps(value, indent=2, default=str))


def choose(label, values):
    if not values:
        raise RotationError(f"No accessible {label}; adjust region/IAM or provision separately with approval")
    for i, value in enumerate(values, 1):
        print(f"{i}. {value.get('name') or value['id']} ({value['id']})")
    try:
        index = int(input(f"Select {label}: ")) - 1
        if index < 0:
            raise ValueError
        return values[index]
    except (ValueError, IndexError):
        raise RotationError("Select a displayed resource number") from None


def configure(args):
    oc = oci.config.from_file(profile_name=args.profile)
    found = discover(oc)
    show({"tenancy": found["tenancy"], "errors": found["errors"]})
    regions = [{"id": r["region"], "name": r["region"]} for r in found["regions"]]
    region = choose("region", regions)["id"]
    resources = next(r for r in found["regions"] if r["region"] == region)
    db = choose("PostgreSQL DB system", [d for d in resources["databases"] if d["state"] == "ACTIVE"])
    rc = dict(oc, region=region)
    detail = oci.psql.PostgresqlClient(rc).get_db_system(db["id"]).data
    endpoint = getattr(getattr(detail, "network_details", None), "primary_db_endpoint_private_ip", "") or ""
    print("Discovered endpoint:", endpoint or "not available; enter a TLS hostname")
    host = input(f"Confirm database TLS hostname [{endpoint}]: ").strip() or endpoint
    vault = choose("Vault", [v for v in resources["vaults"] if v["state"] == "ACTIVE"])
    control = oci.vault.VaultsClient(rc)
    secrets = [s for s in resources["secrets"] if s["state"] == "ACTIVE" and
               control.get_secret(s["id"]).data.vault_id == vault["id"]]
    secret = choose("existing credential secret", secrets)
    subnet = choose("private Function subnet", [s for s in resources["subnets"] if s["private"]])
    c = Config(tenancy_id=oc["tenancy"], region=region, compartment_id=db["compartment_id"],
               db_system_id=db["id"], host=host, database=input("Database name: ").strip(),
               username=input("Application PostgreSQL role (not managed administrator): ").strip(),
               secret_id=secret["id"], subnet_id=subnet["id"],
               state_namespace=oci.object_storage.ObjectStorageClient(rc).get_namespace().data,
               state_bucket=input("Dedicated private operation bucket name (existing or planned): ").strip(),
               ca_file=input("Trusted PostgreSQL CA bundle absolute path: ").strip(),
               function_image=input("Built OCIR function image URI with immutable digest: ").strip(),
               port=int(input("Database port [5432]: ") or "5432"),
               rotation_days=int(input("Rotation days [30]: ") or "30"),
               notification_topic_id=input("Optional Notifications topic OCID: ").strip(), vault_id=vault["id"])
    if Path(args.config).exists():
        raise RotationError("Configuration exists; choose a new --config path to avoid overwriting")
    c.write(args.config)
    show({"saved": args.config, **c.identity()})


def terraform(c, action, profile="DEFAULT"):
    clients(c, profile)  # Check tenancy binding before planning or applying anything.
    root = Path(__file__).resolve().parents[2] / "terraform"
    if not root.exists():
        # Installed wheel: invoke from the source delivery package.
        root = Path.cwd() / "terraform"
    if not (root / "main.tf").exists():
        raise RotationError("Run infrastructure commands from the delivery package directory")
    tfvars = {k: getattr(c, k) for k in ("tenancy_id", "region", "compartment_id", "db_system_id",
               "secret_id", "subnet_id", "state_namespace", "state_bucket", "notification_topic_id", "function_image")}
    tfvars["runtime_config"] = asdict(c)
    tfvars["profile"] = profile
    (root / "rotation.auto.tfvars.json").write_text(json.dumps(tfvars, indent=2))
    # This file contains only non-secret identifiers/settings.
    subprocess.run(["terraform", f"-chdir={root}", "init", "-input=false"], check=True)
    if action == "plan":
        subprocess.run(["terraform", f"-chdir={root}", "plan", "-input=false", "-out=rotation.tfplan"], check=True)
    elif action == "deploy":
        # Interactive Terraform approval after the concrete plan; no auto-approve.
        subprocess.run(["terraform", f"-chdir={root}", "apply", "-input=true"], check=True)
    else:
        subprocess.run(["terraform", f"-chdir={root}", "plan", "-destroy", "-input=false"], check=True)


def schedule(c, profile, enable):
    if not c.function_id:
        raise RotationError("Set function_id from Terraform output after deploying and testing the Function")
    oc, auth = clients(c, profile)
    if enable:
        mgmt = oci.functions.FunctionsManagementClient(oc, **auth)
        fn = mgmt.get_function(c.function_id).data
        invoke = oci.functions.FunctionsInvokeClient(oc, service_endpoint=fn.invoke_endpoint, **auth)
        response = invoke.invoke_function(c.function_id, invoke_function_body=json.dumps({"action": "validate"}).encode())
        result = json.loads(response.data.content)
        if result.get("status") != "VALIDATED":
            raise RotationError("Function resource-principal/network preflight failed; scheduling remains disabled")
    control = oci.vault.VaultsClient(oc, **auth)
    secret = control.get_secret(c.secret_id)
    if (secret.data.rotation_config and secret.data.rotation_config.is_scheduled_rotation_enabled and enable
            and secret.data.rotation_config.target_system_details !=
            oci.vault.models.FunctionTargetSystemDetails(function_id=c.function_id)):
        raise RotationError("Secret already has a different enabled rotation target; review and disable it first")
    control.update_secret(c.secret_id, oci.vault.models.UpdateSecretDetails(
        rotation_config=oci.vault.models.RotationConfig(rotation_interval=f"P{c.rotation_days}D",
            is_scheduled_rotation_enabled=enable,
            target_system_details=oci.vault.models.FunctionTargetSystemDetails(function_id=c.function_id))),
        if_match=secret.headers["etag"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Customer-operated PostgreSQL credential rotation")
    parser.add_argument("--config", default="rotation.yaml")
    parser.add_argument("--profile", default="DEFAULT")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("discover").add_argument("--database-only", action="store_true")
    for name in ("configure", "validate", "plan", "status"):
        commands.add_parser(name)
    for name in ("deploy", "rotate", "reconcile", "schedule", "unschedule"):
        sub = commands.add_parser(name)
        sub.add_argument("--confirm", action="store_true")
        if name == "rotate":
            sub.add_argument("--dry-run", action="store_true")
        if name == "reconcile":
            sub.add_argument("--previous-invocation-stopped", action="store_true")
    commands.add_parser("uninstall").add_argument("--plan", action="store_true", required=True)
    bootstrap = commands.add_parser("create-secret")
    bootstrap.add_argument("--key-id", required=True)
    bootstrap.add_argument("--name", required=True)
    bootstrap.add_argument("--confirm", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    # Never enable SDK wire logging or SQL query logging.
    try:
        if args.command == "discover":
            oc = oci.config.from_file(profile_name=args.profile)
            show(discover(oc, args.database_only))
            return 0
        if args.command == "configure":
            configure(args)
            return 0
        c = Config.load(args.config)
        show(c.identity())
        if args.command in ("validate",) or (args.command == "rotate" and args.dry_run):
            show(preflight(c, args.profile))
        elif args.command in ("plan", "uninstall"):
            terraform(c, args.command, args.profile)
        elif args.command == "status":
            engine = runtime(c, args.profile)
            op = engine.store.load()
            oc, auth = clients(c, args.profile)
            secret = oci.vault.VaultsClient(oc, **auth).get_secret(c.secret_id).data
            show({"operation": op.record() if op else None, "current_version": secret.current_version_number,
                  "next_scheduled_rotation": secret.next_rotation_time,
                  "vault_rotation_status": secret.rotation_status})
        else:
            if not args.confirm:
                raise RotationError("Explicit approval required: review plan/target and repeat with --confirm")
            if args.command == "deploy":
                terraform(c, "deploy", args.profile)
            elif args.command == "create-secret":
                from cli.bootstrap import create_secret
                show({"vault_id": c.vault_id, "key_id": args.key_id, "new_secret_name": args.name})
                show(create_secret(c, args.profile, args.key_id, args.name))
            elif args.command in ("schedule", "unschedule"):
                schedule(c, args.profile, args.command == "schedule")
            else:
                engine = runtime(c, args.profile)
                if args.command == "reconcile" and args.previous_invocation_stopped:
                    engine.store.break_lock()
                show(engine.run(reconcile=args.command == "reconcile").record())
        return 0
    except RotationError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    except (Exception, KeyboardInterrupt) as exc:
        # Print classification, not third-party messages, content, tracebacks or SQL.
        print(f"Error: {type(exc).__name__}; inspect IAM, connectivity and configuration. No secret details logged.",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
