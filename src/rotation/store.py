"""Object Storage CAS journal and non-expiring lock. No secret content stored here."""
import hashlib
import json

from rotation.model import Busy, Operation, RotationError


class ObjectStore:
    def __init__(self, client, namespace: str, bucket: str, target: str, role: str):
        self.client, self.namespace, self.bucket = client, namespace, bucket
        self.key = "roles/" + hashlib.sha256(f"{target}\0{role}".encode()).hexdigest()
        self.etag = self.lock_etag = None

    def _get(self, suffix):
        try:
            return self.client.get_object(self.namespace, self.bucket, self.key + suffix)
        except Exception as exc:
            if getattr(exc, "status", None) == 404:
                return None
            raise

    def acquire(self, owner: str):
        try:
            result = self.client.put_object(self.namespace, self.bucket, self.key + ".lock",
                                            json.dumps({"owner": owner}).encode(), if_none_match="*")
            self.lock_etag = result.headers["etag"]
        except Exception as exc:
            if getattr(exc, "status", None) in (409, 412):
                raise Busy("Role is locked. A timed-out invocation requires the recovery runbook") from None
            raise RotationError("Cannot acquire durable role lock; no database changes made") from None

    def release(self):
        if self.lock_etag:
            self.client.delete_object(self.namespace, self.bucket, self.key + ".lock", if_match=self.lock_etag)
            self.lock_etag = None

    def break_lock(self):
        result = self._get(".lock")
        if result:
            self.client.delete_object(self.namespace, self.bucket, self.key + ".lock",
                                      if_match=result.headers["etag"])

    def load(self):
        result = self._get(".json")
        self.etag = result.headers["etag"] if result else None
        return Operation(**json.loads(result.data.content)) if result else None

    def save(self, operation):
        guard = {"if_match": self.etag} if self.etag else {"if_none_match": "*"}
        result = self.client.put_object(self.namespace, self.bucket, self.key + ".json",
                                        json.dumps(operation.record()).encode(), **guard)
        self.etag = result.headers["etag"]
