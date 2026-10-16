import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from types import SimpleNamespace
import unittest

from rotation.model import Busy, Operation
from rotation.store import ObjectStore


class Conflict(Exception):
    def __init__(self, status):
        self.status = status


class ObjectAPI:
    def __init__(self):
        self.objects = {}
        self.guard = Lock()
        self.sequence = 0

    def get_object(self, ns, bucket, key):
        with self.guard:
            if key not in self.objects:
                raise Conflict(404)
            value, etag = self.objects[key]
            return SimpleNamespace(data=SimpleNamespace(content=value), headers={"etag": etag})

    def put_object(self, ns, bucket, key, body, **conditions):
        with self.guard:
            previous = self.objects.get(key)
            if conditions.get("if_none_match") == "*" and previous:
                raise Conflict(412)
            if "if_match" in conditions and (not previous or previous[1] != conditions["if_match"]):
                raise Conflict(412)
            self.sequence += 1
            etag = str(self.sequence)
            self.objects[key] = (body, etag)
            return SimpleNamespace(headers={"etag": etag})

    def delete_object(self, ns, bucket, key, if_match):
        with self.guard:
            if key not in self.objects or self.objects[key][1] != if_match:
                raise Conflict(412)
            del self.objects[key]


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.api = ObjectAPI()

    def store(self, role="app"):
        return ObjectStore(self.api, "ns", "bucket", "db", role)

    def test_only_one_of_twenty_contenders_acquires(self):
        def attempt(n):
            try:
                self.store().acquire(str(n))
                return True
            except Busy:
                return False
        with ThreadPoolExecutor(max_workers=20) as pool:
            self.assertEqual(sum(pool.map(attempt, range(20))), 1)

    def test_journal_survives_new_process_adapter(self):
        a = self.store()
        a.acquire("first")
        a.save(Operation("id", "db", "app", 1))
        a.release()
        b = self.store()
        b.acquire("second")
        self.assertEqual(b.load().operation_id, "id")
        b.release()

    def test_stale_journal_cannot_overwrite_newer_state(self):
        a, b = self.store(), self.store()
        a.save(Operation("id", "db", "app", 1))
        b.load()
        a.save(Operation("id", "db", "app", 1, state="PREPARED", pending=2))
        with self.assertRaises(Conflict):
            b.save(Operation("id", "db", "app", 1))
        self.assertEqual(self.store().load().state, "PREPARED")

    def test_different_roles_have_independent_locks(self):
        a, b = self.store("a"), self.store("b")
        a.acquire("a")
        b.acquire("b")
        self.assertEqual(len(self.api.objects), 2)
        a.release()
        b.release()

    def test_journal_schema_has_no_password(self):
        a = self.store()
        a.save(Operation("id", "db", "app", 1))
        stored = json.loads(next(iter(self.api.objects.values()))[0])
        self.assertNotIn("password", stored)
