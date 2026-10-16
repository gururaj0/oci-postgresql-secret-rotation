from dataclasses import asdict, dataclass
from pathlib import Path

import yaml

from rotation.model import RotationError


@dataclass
class Config:
    tenancy_id: str
    region: str
    compartment_id: str
    db_system_id: str
    host: str
    database: str
    username: str
    secret_id: str
    subnet_id: str
    state_namespace: str
    state_bucket: str
    ca_file: str
    function_image: str
    port: int = 5432
    rotation_days: int = 30
    credential_type: str = "application"
    function_id: str = ""
    notification_topic_id: str = ""
    vault_id: str = ""

    def validate(self):
        if self.credential_type != "application":
            raise RotationError("Administrator and alternating-user strategies are gated; see architecture decision")
        if not 1 <= self.rotation_days <= 360 or not 1 <= self.port <= 65535:
            raise RotationError("rotation_days must be 1..360 and port must be 1..65535")
        for field in ("tenancy_id", "region", "compartment_id", "db_system_id", "host", "database",
                      "username", "secret_id", "subnet_id", "state_namespace", "state_bucket", "ca_file"):
            if not getattr(self, field):
                raise RotationError(f"Missing configuration: {field}")
        return self

    @classmethod
    def load(cls, path):
        try:
            return cls(**yaml.safe_load(Path(path).read_text())).validate()
        except (TypeError, ValueError, OSError, yaml.YAMLError):
            raise RotationError("Cannot read configuration; use configure or config.example.yaml (no passwords)") from None

    def write(self, path):
        self.validate()
        Path(path).write_text(yaml.safe_dump(asdict(self), sort_keys=False))

    def identity(self):
        return {k: getattr(self, k) for k in ("tenancy_id", "region", "db_system_id", "username")}
