import base64
import json
import time

import oci

from rotation.model import ReconciliationRequired, RotationError


class OciVault:
    def __init__(self, control, bundles, secret_id: str, username: str):
        self.control, self.bundles, self.secret_id, self.username = control, bundles, secret_id, username

    def current(self):
        return self._call(self.control.get_secret, self.secret_id).data.current_version_number

    def password(self, version):
        self._active()
        bundle = self._call(self.bundles.get_secret_bundle, self.secret_id, version_number=version).data
        value = json.loads(base64.b64decode(bundle.secret_bundle_content.content, validate=True))
        if not isinstance(value, dict) or set(value) != {"username", "password"} or value["username"] != self.username:
            raise RotationError("Secret must contain JSON with matching username and password only")
        if not isinstance(value["password"], str) or not value["password"]:
            raise RotationError("Secret password is empty or invalid")
        return value["password"]

    def prepare(self, name, password):
        # Query by deterministic name BEFORE writing: retries cannot create another version.
        versions = self.versions()
        for version in versions:
            if version.name == name:
                return version.version_number
        if any("PENDING" in v.stages for v in versions):
            raise ReconciliationRequired("Unrelated pending Vault version exists; review before rotation")
        response = self._active()
        content = base64.b64encode(json.dumps({"username": self.username, "password": password}).encode()).decode()
        self._call(self.control.update_secret, self.secret_id, oci.vault.models.UpdateSecretDetails(
            secret_content=oci.vault.models.Base64SecretContentDetails(content=content, name=name, stage="PENDING")),
            if_match=response.headers["etag"], retry_strategy=oci.retry.NoneRetryStrategy())
        self._active()
        versions = self.versions()
        for version in versions:
            if version.name == name:
                return version.version_number
        raise RotationError("Prepared version is not visible; retry the same operation")

    def versions(self):
        values, page = [], None
        while True:
            args = {"page": page} if page else {}
            result = self._call(self.control.list_secret_versions, self.secret_id, **args,
                                                       retry_strategy=oci.retry.NoneRetryStrategy())
            values.extend(result.data)
            page = result.headers.get("opc-next-page")
            if not page:
                return values

    def promote(self, version, previous):
        response = self._active()
        current = response.data.current_version_number
        if current == version:
            return
        if current != previous:
            raise ReconciliationRequired("Vault CURRENT changed outside this rotation")
        self._call(self.control.update_secret, self.secret_id, oci.vault.models.UpdateSecretDetails(current_version_number=version),
                                   if_match=response.headers["etag"], retry_strategy=oci.retry.NoneRetryStrategy())
        self._active()

    def _active(self):
        # UpdateSecret is asynchronous. Do not read new bundle content or issue
        # another update while the secret is still UPDATING.
        deadline = time.monotonic() + 60
        while True:
            response = self._call(self.control.get_secret, self.secret_id)
            state = response.data.lifecycle_state
            if state == "ACTIVE":
                return response
            if state not in ("CREATING", "UPDATING"):
                raise RotationError("Vault secret is not in a usable lifecycle state")
            if time.monotonic() >= deadline:
                raise RotationError("Vault update still pending; resume the durable rotation operation")
            time.sleep(2)

    @staticmethod
    def _call(method, *args, **kwargs):
        # A 429 explicitly rejects the request. Retrying it is safe even for
        # ETag-guarded writes. Unknown write outcomes still use journal recovery.
        for attempt in range(5):
            try:
                return method(*args, **kwargs)
            except Exception as exc:
                if getattr(exc, "status", None) != 429 or attempt == 4:
                    raise
                time.sleep(min(2 ** (attempt + 1), 8))
