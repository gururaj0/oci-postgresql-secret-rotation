"""Resource Manager apply helpers. Never print credentials or raw OCI errors.

OCI CLI inherits the managed runner's authentication. No credentials are accepted
as Terraform inputs. Build credentials exist only in an isolated temporary directory.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import quote


class DeploymentError(RuntimeError):
    pass


def run(args, *, env=None, stdin=None):
    result = subprocess.run(args, input=stdin, text=True, capture_output=True, env=env)
    if result.returncode:
        # CLI errors can include signed request headers. Do not propagate them.
        raise DeploymentError("Command failed: " + " ".join(args[:3]) + "; inspect permissions and connectivity")
    return result.stdout


def cli(*args):
    return json.loads(run(["oci", "--region", os.environ["ROTATION_REGION"], "--output", "json", "--no-retry", "--connection-timeout", "10", "--read-timeout", "310", *args]))


def raw(method, url, body=None, etag=None):
    args = ["raw-request", "--http-method", method, "--target-uri", url]
    if body is not None:
        args += ["--request-body", json.dumps(body)]
    if etag:
        args += ["--request-headers", json.dumps({"if-match": etag})]
    result = cli(*args)
    status = str(result.get("status", ""))
    if not status.startswith("2"):
        raise DeploymentError("OCI request did not succeed")
    data = result.get("data")
    if isinstance(data, str) and data:
        data = json.loads(data)
    return data, {k.lower(): v for k, v in result.get("headers", {}).items()}


def build():
    image = os.environ["ROTATION_IMAGE"]
    registry = os.environ["ROTATION_REGISTRY"]
    if not re.fullmatch(r"[a-z0-9-]+\.ocir\.io", registry) or not image.startswith(registry + "/"):
        raise DeploymentError("Only the selected commercial OCI region's OCIR endpoint is supported")
    ca = os.environ["ROTATION_CA"]
    if "-----BEGIN CERTIFICATE-----" not in ca or "PRIVATE KEY" in ca:
        raise DeploymentError("Database connection details did not return a public PEM CA certificate")
    with tempfile.TemporaryDirectory(prefix="rotation-build-") as temp:
        root = Path(temp)
        context = root / "context"
        shutil.copytree(Path(__file__).resolve().parents[1] / "bundle", context)
        (context / "certs").mkdir()
        (context / "certs/postgresql-ca.pem").write_text(ca)
        original = (context / "functions/vault_rotation/Dockerfile").read_text()
        if original.count("USER 10001") != 1:
            raise DeploymentError("Unexpected Dockerfile: review CA insertion point")
        (context / "Dockerfile").write_text(original.replace("USER 10001", "COPY certs/postgresql-ca.pem /function/certs/postgresql-ca.pem\nUSER 10001"))
        env = os.environ.copy()
        env["DOCKER_CONFIG"] = str(root / "docker-config")
        Path(env["DOCKER_CONFIG"]).mkdir(mode=0o700)
        print("Building the Function image (this can take several minutes)", flush=True)
        run(["docker", "build", "--platform", "linux/amd64", "-t", image, str(context)], env=env)
        # Signed OCI request exchanges runner identity for short-lived registry auth.
        # The token never enters Terraform variables/state, command arguments or logs.
        data, _ = raw("GET", "https://" + registry + "/20180419/docker/token")
        token = data.get("token") if isinstance(data, dict) else None
        if not token:
            raise DeploymentError("OCIR did not return a temporary registry token")
        run(["docker", "login", registry, "--username", "BEARER_TOKEN", "--password-stdin"], env=env, stdin=token)
        print("Publishing the image to the tenancy's private OCIR repository", flush=True)
        run(["docker", "push", image], env=env)
    print("Image published; Terraform will resolve and pin its digest", flush=True)


def desired_config(function_id, days, enabled):
    return {"rotationInterval": "P" + str(days) + "D", "isScheduledRotationEnabled": enabled,
            "targetSystemDetails": {"targetSystemType": "FUNCTION", "functionId": function_id}}


def check_target(secret, function_id):
    if secret.get("isReplica") or secret.get("lifecycleState") != "ACTIVE":
        raise DeploymentError("Select an ACTIVE source secret")
    target = (secret.get("rotationConfig") or {}).get("targetSystemDetails") or {}
    if target and (target.get("targetSystemType") != "FUNCTION" or target.get("functionId") != function_id):
        raise DeploymentError("Secret already has another rotation target; unlink it explicitly before deploying")


def configure():
    region = os.environ["ROTATION_REGION"]
    function_id = os.environ["ROTATION_FUNCTION_ID"]
    secret_id = os.environ["ROTATION_SECRET_ID"]
    days = int(os.environ["ROTATION_DAYS"])
    enabled_text = os.environ["ROTATION_ENABLED"]
    if not 1 <= days <= 360 or enabled_text not in ("true", "false"):
        raise DeploymentError("Invalid rotation schedule settings")
    if not re.fullmatch(r"[a-z0-9-]+", region):
        raise DeploymentError("Invalid region")
    secret_url = "https://vaults." + region + ".oci.oraclecloud.com/20180608/secrets/" + quote(secret_id, safe="")
    secret, _ = raw("GET", secret_url)
    check_target(secret, function_id)
    fn = cli("fn", "function", "get", "--function-id", function_id)["data"]
    endpoint = fn["invoke-endpoint"]
    print("Validating the deployed Function's fresh TLS login; allowing time for IAM propagation", flush=True)
    deadline = time.monotonic() + 600
    while True:
        try:
            result, _ = raw("POST", endpoint.rstrip("/") + "/20181201/functions/" + quote(function_id, safe="") + "/actions/invoke", {"action": "validate"})
            if result.get("status") == "VALIDATED":
                break
        except DeploymentError:
            pass
        if time.monotonic() >= deadline:
            raise DeploymentError("Function validation failed; inspect invocation logs, database access and the existing secret. Rotation settings were not changed.")
        time.sleep(20)
    desired = desired_config(function_id, days, enabled_text == "true")
    # Re-read after validation to catch concurrent edits before the ETag update.
    secret, headers = raw("GET", secret_url)
    check_target(secret, function_id)
    etag = headers.get("etag")
    if not etag:
        raise DeploymentError("Secret metadata response omitted its ETag")
    if secret.get("rotationConfig") != desired:
        raw("PUT", secret_url, {"rotationConfig": desired}, etag=etag)
    deadline = time.monotonic() + 300
    while True:
        current, _ = raw("GET", secret_url)
        if current.get("lifecycleState") == "ACTIVE" and current.get("rotationConfig") == desired:
            break
        if time.monotonic() >= deadline:
            raise DeploymentError("Rotation configuration is not yet confirmed; inspect the secret before reapplying")
        time.sleep(10)
    print("Console rotation configured. Automatic rotation: " + enabled_text, flush=True)


if __name__ == "__main__":
    try:
        {"build": build, "configure": configure}[sys.argv[1]]()
    except Exception as exc:
        # Do not emit exception objects from SDK/CLI or subprocesses.
        message = str(exc) if isinstance(exc, DeploymentError) else type(exc).__name__
        print("Deployment stopped: " + message, file=sys.stderr)
        sys.exit(1)
