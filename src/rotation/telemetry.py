from datetime import datetime, timezone
import logging

import oci

from rotation.engine import STATES


def snapshot(engine, days, clock=None):
    clock = clock or datetime.now(timezone.utc)
    op = engine.store.load()
    secret = engine.vault.control.get_secret(engine.vault.secret_id).data
    base = datetime.fromisoformat(op.last_success) if op and op.last_success else secret.time_created
    overdue = (clock - base).total_seconds() > (days * 86400 + 3600)
    age = (clock - datetime.fromisoformat(op.started_at)).total_seconds() if op else 0
    duration = ((datetime.fromisoformat(op.completed_at) - datetime.fromisoformat(op.started_at)).total_seconds()
                if op and op.completed_at else age)
    return {"RotationOverdue": int(overdue), "RotationDuration": duration,
            "RotationState": STATES.index(op.state) if op else -1,
            "ConsecutiveFailures": op.consecutive_failures if op else 0,
            "PendingSecretAge": age if op and op.pending and op.state != "COMPLETE" else 0,
            "ReconciliationRequired": int(bool(op and op.error == "RECONCILIATION_REQUIRED")),
            "AuthenticationVerificationFailure": int(bool(op and op.error == "RECONCILIATION_REQUIRED"
                                                          and op.state == "DATABASE_UPDATED")),
            "LastSuccessfulRotation": datetime.fromisoformat(op.last_success).timestamp()
            if op and op.last_success else 0,
            "NextScheduledRotation": secret.next_rotation_time.timestamp() if secret.next_rotation_time else 0}


def publish(c, engine, failed=False):
    from cli.runtime import clients
    try:
        oc, auth = clients(c, resource_principal=True)
        client = oci.monitoring.MonitoringClient(oc, **auth)
        # Preserve the SDK-resolved realm/domain rather than assuming commercial OCI endpoints.
        client.base_client.endpoint = client.base_client.endpoint.replace("telemetry.", "telemetry-ingestion.", 1)
        values = {"RotationFailure": int(failed), "MonitorHeartbeat": 1}
        try:
            values.update(snapshot(engine, c.rotation_days))
        except Exception:
            values["RotationFailure"] = 1
            logging.getLogger("pg_rotation").error("event=monitor_dependency_unavailable")
        timestamp = datetime.now(timezone.utc)
        models = oci.monitoring.models
        result = client.post_metric_data(models.PostMetricDataDetails(metric_data=[models.MetricDataDetails(
            namespace="pg_vault_rotation", compartment_id=c.compartment_id, name=name,
            dimensions={"dbSystemId": c.db_system_id, "role": c.username},
            datapoints=[models.Datapoint(timestamp=timestamp, value=value)]) for name, value in values.items()]))
        if result.data.failed_metrics_count:
            logging.getLogger("pg_rotation").error("event=telemetry_partial_failure")
    except Exception as exc:
        # Telemetry must not roll back a successful rotation or hide its real failure.
        logging.getLogger("pg_rotation").error("event=telemetry_unavailable cause=%s status=%s",
                                              type(exc).__name__, getattr(exc, "status", None))
