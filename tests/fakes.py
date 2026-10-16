import copy

from rotation.model import Busy


class MemoryStore:
    def __init__(self):
        self.op = None
        self.locked = False
        self.history = []
        self.fail_state = None

    def acquire(self, owner):
        if self.locked:
            raise Busy("Locked")
        self.locked = True

    def release(self):
        self.locked = False

    def load(self):
        return copy.deepcopy(self.op)

    def save(self, op):
        if op.state == self.fail_state:
            self.fail_state = None
            raise RuntimeError("Injected journal failure")
        self.op = copy.deepcopy(op)
        self.history.append(op.record())


class MemoryVault:
    def __init__(self):
        self.versions = {1: "old-password"}
        self.names = {}
        self.active = 1
        self.fail_prepare = self.fail_promote = False
        self.lost_prepare_response = self.lost_promote_response = False

    def current(self):
        return self.active

    def password(self, version):
        return self.versions[version]

    def prepare(self, name, password):
        if self.fail_prepare:
            raise RuntimeError("Vault unavailable")
        if name in self.names:
            return self.names[name]
        version = len(self.versions) + 1
        self.versions[version] = password
        self.names[name] = version
        if self.lost_prepare_response:
            self.lost_prepare_response = False
            raise TimeoutError("Response lost")
        return version

    def promote(self, version, previous):
        if self.fail_promote:
            raise TimeoutError("Promotion failed")
        self.active = version
        if self.lost_promote_response:
            self.lost_promote_response = False
            raise TimeoutError("Response lost")


class MemoryDB:
    def __init__(self):
        self.active = "old-password"
        self.changes = 0
        self.fail_change = self.lost_change_response = self.reject_pending = False

    def verify(self, password):
        return password == self.active and not (self.reject_pending and password != "old-password")

    def preflight(self, password):
        if not self.verify(password):
            raise RuntimeError("Cannot authenticate")

    def change(self, current, pending):
        if self.fail_change:
            raise RuntimeError("ALTER failed")
        assert current == self.active
        self.active = pending
        self.changes += 1
        if self.lost_change_response:
            self.lost_change_response = False
            raise TimeoutError("Commit response lost")
