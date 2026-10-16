"""Explicitly approved real-service recovery test; only credentials from the configured Vault are used."""
import argparse
import json
from pathlib import Path
import time

from cli.config import Config
from cli.runtime import runtime
from rotation.model import Busy, RotationError, now


class BlockPromotion:
    def __init__(self, vault):
        self.vault = vault

    def __getattr__(self, name):
        return getattr(self.vault, name)

    def promote(self, version, previous):
        raise RotationError("Injected promotion outage for approved acceptance test")


def run(config, profile):
    engine = runtime(config, profile)
    report = {"target": config.identity(), "started_at": now(), "checks": {}}
    checks = report["checks"]
    initial_version = engine.vault.current()
    old_password = engine.vault.password(initial_version)
    initial_op = engine.store.load()
    if initial_op and initial_op.state != "COMPLETE":
        raise RotationError("Reconcile the existing operation before starting this acceptance test")
    engine.validate()
    assert engine.vault.current() == initial_version
    assert engine.store.load() == initial_op
    checks["dry_run_no_mutation"] = True
    engine.store.acquire("approved-concurrency-test")
    try:
        try:
            runtime(config, profile).run()
        except Busy:
            checks["concurrent_rotation_rejected"] = True
        else:
            raise AssertionError("Second actor acquired the same role")
    finally:
        engine.store.release()

    real_vault = engine.vault
    engine.vault = BlockPromotion(real_vault)
    try:
        with engine.db.connect(old_password) as existing_session:
            # Vault writes can become readable asynchronously. Resume the same
            # journal/UUID while keeping promotion blocked throughout the fault test.
            for attempt in range(10):
                try:
                    engine.run()
                except RotationError:
                    pass
                op = engine.store.load()
                if op and op.state == "VERIFIED":
                    break
                time.sleep(2)
            assert op and op.state == "VERIFIED", "Expected recoverable VERIFIED state"
            pending_password = real_vault.password(op.pending)
            assert real_vault.current() == initial_version
            assert engine.db.verify(pending_password)
            assert not engine.db.verify(old_password)
            checks["database_updated_without_vault_promotion"] = True
            assert existing_session.execute("SELECT 1").fetchone() == (1,)
            checks["existing_session_survives_rotation"] = True
            resumed = runtime(config, profile)
            for attempt in range(10):
                try:
                    final = resumed.run(reconcile=True)
                    break
                except RotationError:
                    if attempt == 9:
                        raise
                    time.sleep(2)
            assert final.operation_id == op.operation_id and final.pending == op.pending
            assert final.state == "COMPLETE"
            checks["recovery_reuses_operation_and_version"] = True
            # Simulate an application refreshing CURRENT for a new physical connection.
            refreshed = resumed.vault.password(resumed.vault.current())
            with resumed.db.connect(refreshed) as new_session:
                assert new_session.execute("SELECT current_user").fetchone()[0] == config.username
            checks["refreshed_current_opens_new_connection"] = True
            metadata = json.dumps(final.record())
            assert old_password not in metadata and pending_password not in metadata
            checks["journal_contains_no_password"] = True
            report.update(initial_version=initial_version, current_version=resumed.vault.current(),
                          operation=final.record(), completed_at=now())
    finally:
        # A test assertion must not abandon a working pending credential.
        engine.vault = real_vault
        op = engine.store.load()
        if op and op.state != "COMPLETE":
            runtime(config, profile).run(reconcile=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True)
    parser.add_argument("--profile", default="DEFAULT")
    parser.add_argument("--report", default="live-acceptance.json")
    parser.add_argument("--confirm", action="store_true", required=True)
    args = parser.parse_args()
    config = Config.load(args.config)
    print(json.dumps(config.identity()), flush=True)
    try:
        report = run(config, args.profile)
    except Exception as exc:
        print(json.dumps({"result": "FAILED", "error_class": type(exc).__name__,
                          "next_step": "Inspect status and reconcile before another test"}))
        return 1
    Path(args.report).write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
