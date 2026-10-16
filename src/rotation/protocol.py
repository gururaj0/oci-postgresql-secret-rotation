from rotation.model import RotationError


def callback(engine, secret_id: str, payload: dict) -> dict:
    """Vault uses the verified pending version as input to the final callback.

    The native wire response uses versionNo. Some documentation calls the input
    currentVersionNo; accept that input alias but always emit versionNo.
    """
    if payload.get("secretId") != secret_id:
        raise RotationError("Secret is not the configured target")
    if ("currentVersionNo" in payload and "versionNo" in payload and
            payload["currentVersionNo"] != payload["versionNo"]):
        raise RotationError("Conflicting version fields")
    version = payload.get("currentVersionNo", payload.get("versionNo"))
    if version is not None and (type(version) is not int or version < 1):
        raise RotationError("Version must be a positive integer")
    step = payload.get("step")
    op = engine.store.load()
    if step == "VERIFY_CONNECTION":
        current = engine.vault.current()
        if op and op.state != "COMPLETE" and op.pending:
            valid = engine.db.verify(engine.vault.password(op.pending))
        else:
            valid = False
        if not valid:
            engine.db.preflight(engine.vault.password(current))
        return {"responseCode": 200, "versionNo": current, "returnMessage": "Verified"}
    if step == "CREATE_PENDING_VERSION":
        op = engine.run(stop="PREPARED", expected=version if version is not None else engine.vault.current())
        output = op.current
    elif step == "UPDATE_TARGET_SYSTEM":
        if op is None or op.pending is None:
            raise RotationError("CREATE_PENDING_VERSION must complete first")
        if version is not None and version != op.current:
            raise RotationError("Update callback refers to a different current version")
        op = engine.run(stop="VERIFIED", expected=op.current)
        output = op.pending
    elif step == "PROMOTE_PENDING_VERSION":
        if op is None or op.state not in ("VERIFIED", "VAULT_PROMOTED", "COMPLETE"):
            raise RotationError("UPDATE_TARGET_SYSTEM must verify the pending credential first")
        if version != op.pending:
            raise RotationError("Promotion callback does not refer to the verified pending version")
        op = engine.run(expected=op.current)
        output = op.pending
    else:
        raise RotationError("Unsupported Vault rotation step")
    return {"responseCode": 200, "versionNo": output, "returnMessage": op.state}
