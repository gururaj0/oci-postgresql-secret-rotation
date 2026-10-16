import base64
import getpass
import json
import sys

import oci

from cli.runtime import clients
from rotation.model import RotationError


def create_secret(c, profile, key_id, name):
    """Initial credential is supplied only through a real terminal, never argv or files."""
    from postgres.client import Postgres
    if not sys.stdin.isatty():
        raise RotationError("Secure local terminal input is required to initialize a secret")
    if not c.vault_id:
        raise RotationError("Set vault_id in configuration first")
    oc, auth = clients(c, profile)
    value = getpass.getpass("Existing PostgreSQL password (not logged or saved locally): ")
    Postgres(c).preflight(value)
    content = base64.b64encode(json.dumps({"username": c.username, "password": value}).encode()).decode()
    result = oci.vault.VaultsClient(oc, **auth).create_secret(oci.vault.models.CreateSecretDetails(
        compartment_id=c.compartment_id, vault_id=c.vault_id, key_id=key_id, secret_name=name,
        secret_content=oci.vault.models.Base64SecretContentDetails(content=content, stage="CURRENT")))
    return {"secret_id": result.data.id, "next_step": "Set secret_id in configuration; validate before deployment"}
