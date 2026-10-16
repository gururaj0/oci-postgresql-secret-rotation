import io
import json
import logging
import os

from fdk import response

from cli.config import Config
from cli.runtime import runtime
from rotation.protocol import callback
from rotation.telemetry import publish, snapshot


def handler(ctx, data: io.BytesIO = None):
    """OCI Vault four-step protocol. Target is pinned to Function configuration."""
    logging.getLogger().setLevel(logging.INFO)
    for name in ("oci", "urllib3"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("pg_rotation").setLevel(logging.INFO)
    engine = c = None
    try:
        config = ctx.Config()
        c = Config(**json.loads(config["ROTATION_CONFIG"])).validate()
        engine = runtime(c, resource_principal=True)
        payload = json.loads(data.getvalue() or b"{}") if data else {}
        step = payload.get("step")
        safe_step = step if step in ("VERIFY_CONNECTION", "CREATE_PENDING_VERSION",
            "UPDATE_TARGET_SYSTEM", "PROMOTE_PENDING_VERSION") else "action_or_unknown"
        logging.getLogger("pg_rotation").info("event=invocation_start step=%s", safe_step)
        if payload.get("action") == "validate":
            engine.validate()
            body = {"status": "VALIDATED"}
        elif payload.get("action") == "monitor":
            body = snapshot(engine, c.rotation_days)
        else:
            body = callback(engine, c.secret_id, payload)
        publish(c, engine)
        logging.getLogger("pg_rotation").info("event=invocation_complete step=%s", safe_step)
        return response.Response(ctx, response_data=json.dumps(body), headers={"Content-Type": "application/json"})
    except Exception as exc:
        if engine is not None:
            publish(c, engine, failed=True)
        logging.getLogger("pg_rotation").error("event=rotation_failure invocation=%s cause=%s status=%s",
            os.getenv("FN_CALL_ID", "unknown"), type(exc).__name__, getattr(exc, "status", None))
        return response.Response(ctx, response_data=json.dumps({"responseCode": 500,
            "returnMessage": "Rotation incomplete; inspect durable journal and follow recovery runbook"}),
            status_code=500, headers={"Content-Type": "application/json"})
