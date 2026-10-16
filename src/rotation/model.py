from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RotationError(Exception):
    """Safe operator-facing error; never wrap raw database or SDK messages."""


class Busy(RotationError):
    pass


class ReconciliationRequired(RotationError):
    pass


@dataclass
class Operation:
    operation_id: str
    target: str
    role: str
    current: int
    state: str = "PRECHECK"
    pending: int | None = None
    started_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    retries: int = 0
    consecutive_failures: int = 0
    last_success: str | None = None

    def record(self) -> dict:
        return asdict(self)


class Vault(Protocol):
    def current(self) -> int: ...
    def password(self, version: int) -> str: ...
    def prepare(self, name: str, password: str) -> int: ...
    def promote(self, version: int, previous: int) -> None: ...


class Database(Protocol):
    def verify(self, password: str) -> bool: ...
    def preflight(self, password: str) -> None: ...
    def change(self, current: str, pending: str) -> None: ...


class Store(Protocol):
    def acquire(self, owner: str) -> None: ...
    def release(self) -> None: ...
    def load(self) -> Operation | None: ...
    def save(self, operation: Operation) -> None: ...
