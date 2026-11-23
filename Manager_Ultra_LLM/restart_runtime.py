"""One explicit, fail-closed, per-slot model restart; no Manager/Client process restart.

The Manager owns Stop -> confirmed release -> Check -> Start -> READY.
The request journal is private and survives lost HTTP responses; interrupted jobs
remain ERROR and never resume automatically after a Manager restart.
"""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import re
import time
import uuid

from colibri2_runner import RunnerSpec
from cuda_profile import DEFAULT_PROFILE
from control_runtime import ControlError


_TERMINAL = {"READY", "ERROR"}
_STAGES = {"STOPPING", "WAITING_RELEASE", "CHECKING", "STARTING", *_TERMINAL}
_ID = re.compile(r"[a-f0-9]{32}\Z")


def initialize(db):
    db.execute("""CREATE TABLE IF NOT EXISTS restart_jobs (
        owner TEXT NOT NULL, request_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
        slot TEXT NOT NULL, old_instance TEXT NOT NULL, model TEXT NOT NULL,
        mode TEXT NOT NULL, original_model_id TEXT NOT NULL,
        new_instance TEXT NOT NULL, spec TEXT NOT NULL,
        stage TEXT NOT NULL, reason TEXT, created REAL NOT NULL,
        PRIMARY KEY(owner,request_id))""")
    # A restarted Manager cannot know whether an old background worker
    # completed. Preserve the slot's strict process-ownership recovery gate.
    db.execute("""UPDATE restart_jobs SET stage='ERROR',reason='restart_interrupted'
                  WHERE stage NOT IN ('READY','ERROR')""")


def _result(controller, row):
    owner, request_id, _, slot, old, model, mode, old_model_id, new, spec, stage, reason, _ = row
    new_model_id = RunnerSpec(**json.loads(spec)).api_id
    return {"manager_id": controller.config["manager_id"],
            "request_id": request_id, "slot_id": slot,
            "instance_id": old, "model_key": model, "mode": mode,
            "original_model_id": old_model_id,
            "model_id": new_model_id if stage == "READY" else old_model_id,
            "new_instance_id": new if stage == "READY" else None,
            "stage": stage, "reason": reason}


def status(controller, principal, request_id):
    controller._auth(principal)
    if type(request_id) is not str or not _ID.fullmatch(request_id):
        raise ControlError("invalid_request_id", 400)
    with controller.db() as db:
        row = db.execute("SELECT * FROM restart_jobs WHERE owner=? AND request_id=?",
                         (principal["client_id"], request_id)).fetchone()
    if not row:
        raise ControlError("restart_not_found", 404)
    principal = controller.effective_principal(principal)
    if row[3] not in principal["allowed_slots"]:
        raise ControlError("slot_not_authorized", 403)
    return _result(controller, row)


def _stage(controller, owner, request_id, stage, reason=None):
    with controller.db() as db:
        db.execute("UPDATE restart_jobs SET stage=?,reason=? WHERE owner=? AND request_id=?",
                   (stage, reason, owner, request_id))
        db.commit()


def _wait_status(controller, spec, identity, *, stopping, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            row = controller.backend.status(spec, identity)
        except Exception:
            raise ControlError("runner_action_unconfirmed") from None
        if stopping and row.get("state") == "STOPPED" and row.get("released") is True:
            return row
        if not stopping and row.get("state") == "READY" and row.get("released") is False:
            return row
        if row.get("state") == "ERROR" or row.get("released") is True:
            raise ControlError("runner_action_unconfirmed")
        time.sleep(0.5)
    raise ControlError("restart_stop_timeout" if stopping else "restart_start_timeout")


def _worker(controller, owner, request_id, old_spec, new_spec, old_id, new_id, release):
    phase = "stop"
    released_confirmed = False
    try:
        controller.backend.stop(old_spec, old_id)
        _stage(controller, owner, request_id, "WAITING_RELEASE")
        _wait_status(controller, old_spec, old_id, stopping=True, timeout=120)
        released_confirmed = True

        phase = "check"
        with controller.db() as db:
            db.execute("BEGIN IMMEDIATE")
            before = db.execute("SELECT state,released FROM instances WHERE id=?", (old_id,)).fetchone()
            if before != ("STOPPING", 0):
                raise ControlError("restart_identity_changed")
            db.execute("UPDATE instances SET state='RESTART_HOLD',reason=NULL WHERE id=?",
                       (old_id,))
            db.commit()
        _stage(controller, owner, request_id, "CHECKING")
        telemetry = controller.backend.telemetry()
        if telemetry.get("verified") is not True or new_spec.port in telemetry.get("ports", ()):
            raise ControlError("restart_port_not_free")
        with controller.db() as db:
            controller._sync(db)
            rows = [r for r in controller._rows(db) if r["instance_id"] != old_id]
            assessment = controller._gate(new_spec.model_key, new_spec.backend, telemetry, rows,
                new_spec.review.get("launch", {}).get("context_tokens"),
                new_spec.review.get("launch", {}).get("cuda_profile") if new_spec.backend == "cuda" else None)
            # Free RAM inevitably changes after the old process exits. Keep
            # the accepted admission threshold, but reject changed launch
            # policy and a post-stop memory drop beyond that threshold.
            before = new_spec.resources
            after = assessment["policy"]
            if any(after.get(k) != before.get(k) for k in
                   ("ram_gib","vram_gib","job_limit_gib","ram_warning_gib",
                    "context_tokens","cuda_profile")):
                raise ControlError("restart_resources_changed")
            if telemetry.get("free_gib", 0) < before["min_free_at_start_gib"]:
                raise ControlError("restart_resources_changed")
            new_spec = replace(new_spec, resources={**after,
                "min_free_at_start_gib":before["min_free_at_start_gib"]})
        controller.backend.preflight(new_spec)
        phase = "start"
        with controller.db() as db:
            db.execute("BEGIN IMMEDIATE")
            held = db.execute("SELECT state,released FROM instances WHERE id=?", (old_id,)).fetchone()
            if held != ("RESTART_HOLD", 0):
                raise ControlError("restart_identity_changed")
            db.execute("UPDATE instances SET state='STOPPED',released=1,reason='runner_finished' WHERE id=?", (old_id,))
            db.execute("""INSERT INTO instances(id,slot,model,mode,owner,state,released,spec,reason,created)
                          VALUES(?,?,?,?,?,'STARTING',0,?,NULL,?)""",
                       (new_id, new_spec.slot_id, new_spec.model_key, new_spec.backend,
                        owner, json.dumps(asdict(new_spec)), time.time()))
            db.execute("UPDATE slots SET revision=revision+1 WHERE slot_id=?", (new_spec.slot_id,))
            db.commit()
        _stage(controller, owner, request_id, "STARTING")
        controller.backend.start(new_spec, new_id)
        _wait_status(controller, new_spec, new_id, stopping=False, timeout=300)
        with controller.db() as db:
            db.execute("""UPDATE instances SET state='READY',reason=NULL,released=0
                          WHERE id=? AND released=0 AND state IN ('STARTING','READY')""", (new_id,))
            if db.execute("SELECT changes()").fetchone()[0] != 1:
                raise ControlError("restart_identity_changed")
            db.commit()
        _stage(controller, owner, request_id, "READY")
    except Exception as exc:
        # No automatic replacement/fallback or blind retry after any uncertainty.
        reason = exc.reason if isinstance(exc, ControlError) else "runner_action_unconfirmed"
        if reason not in {"runner_action_unconfirmed", "restart_stop_timeout",
                          "restart_start_timeout", "restart_identity_changed", "restart_port_not_free",
                          "restart_resources_changed", "slot_in_use", "runtime_review_required",
                          "resource_telemetry_unknown", "context_capacity_exceeded", "context_capacity_unknown",
                          "runtime_or_model_changed"}:
            reason = "restart_preflight_failed" if phase == "check" else "runner_action_unconfirmed"
        try:
            if released_confirmed:
                with controller.db() as db:
                    # A failed post-stop Check cannot leave a false ownership
                    # reservation for a process already proven released.
                    db.execute("""UPDATE instances SET state='STOPPED',released=1,reason='runner_finished'
                                  WHERE id=? AND state='RESTART_HOLD' AND released=0""", (old_id,))
                    db.commit()
            if phase == "start":
                with controller.db() as db:
                    db.execute("""UPDATE instances SET state='ERROR',reason='runner_action_unconfirmed'
                                  WHERE id=? AND released=0""", (new_id,))
                    db.commit()
            _stage(controller, owner, request_id, "ERROR", reason)
        except Exception:
            pass
    finally:
        release()


def _validate_context_before_stop(controller, model_key, context_tokens):
    """Validate requested model capacity from trusted installed metadata first.

    A full runner preflight requires the port to be free, so it happens after
    Stop; this early capacity check must not interrupt a healthy old instance.
    """
    if context_tokens is None:
        return
    from pathlib import Path
    from resource_catalog import initial_catalogue
    from server_preflight import read_profiles
    from colibri2_runner import validate_context_capacity, StartDenied

    models_root = Path(controller.config["models_root"]).resolve()
    profiles = read_profiles(Path(controller.config["colibri_root"]) / "ULTRA-CONTROL.py")
    choice = initial_catalogue()[model_key]
    profile = profiles.get(choice.profile)
    if (type(profile) is not dict or type(profile.get("folder")) is not str or
            type(profile.get("subfolder", "")) is not str):
        raise ControlError("model_files_unverified")
    model = (models_root / profile["folder"] / profile.get("subfolder", "")).resolve()
    if not model.is_relative_to(models_root):
        raise ControlError("model_files_unverified")
    try:
        validate_context_capacity(model, context_tokens)
    except (OSError, ValueError, StartDenied) as error:
        reason = str(error)
        if reason in ("context_capacity_exceeded", "context_capacity_unknown"):
            raise ControlError(reason) from None
        raise ControlError("runtime_preflight_unverified") from None


def request(controller, principal, payload):
    controller._auth(principal)
    required = {"op", "slot_id", "instance_id", "expected_revision", "request_id"}
    optional = {"context_tokens", "risk_ack", "risk_token"}
    if (type(payload) is not dict or payload.get("op") != "restart"
            or not required <= set(payload) or set(payload) - required - optional
            or type(payload.get("request_id")) is not str or not _ID.fullmatch(payload["request_id"])
            or type(payload.get("instance_id")) is not str or not _ID.fullmatch(payload["instance_id"])
            or type(payload.get("slot_id")) is not str or not payload["slot_id"]
            or type(payload.get("expected_revision")) is not int
            or ("context_tokens" in payload and
                (type(payload["context_tokens"]) is not int or not 1 <= payload["context_tokens"] <= 999999))
            or ("risk_ack" in payload and type(payload["risk_ack"]) is not bool)):
        raise ControlError("invalid_restart_fields", 400)
    principal = controller.effective_principal(principal)
    slot_id, old_id, request_id = (payload[k] for k in ("slot_id", "instance_id", "request_id"))
    if slot_id not in principal["allowed_slots"]:
        raise ControlError("slot_not_authorized", 403)
    fixed = {k: payload[k] for k in ("slot_id", "instance_id", "expected_revision")}
    fixed["context_tokens"] = payload.get("context_tokens")
    fingerprint = json.dumps(fixed, sort_keys=True)
    with controller.db() as db:
        previous = db.execute("SELECT * FROM restart_jobs WHERE owner=? AND request_id=?",
                              (principal["client_id"], request_id)).fetchone()
        if previous:
            if previous[2] != fingerprint:
                raise ControlError("request_id_conflict")
            return _result(controller, previous)
        if (db.execute("SELECT 1 FROM requests WHERE owner=? AND id=?",
                       (principal["client_id"], request_id)).fetchone()
                or db.execute("SELECT 1 FROM slot_requests WHERE owner=? AND id=?",
                              (principal["client_id"], request_id)).fetchone()):
            raise ControlError("request_id_conflict")
    gate = getattr(controller, "restart_gate", None)
    if gate is None:
        raise ControlError("restart_guard_unavailable", 503)
    release, verify_idle = gate(slot_id, old_id, principal)
    handed_off = False
    try:
        verify_idle()
        with controller.db() as db:
            db.execute("BEGIN IMMEDIATE")
            controller._sync(db)
            definitions = controller.registry.definitions(db)
            slot = next((s for s in definitions if s["slot_id"] == slot_id), None)
            row = next((r for r in controller._rows(db) if
                        r["instance_id"] == old_id and not r["released"]), None)
            if slot is None or slot["protected"]:
                raise ControlError("legacy_slot_protected", 403)
            if slot["revision"] != payload["expected_revision"]:
                raise ControlError("slot_selection_changed")
            if (row is None or row["slot_id"] != slot_id or row["owner"] != principal["client_id"]):
                raise ControlError("instance_not_authorized", 403)
            if row["state"] != "READY" or slot["model_key"] != row["model_key"] or slot["mode"] != row["mode"]:
                raise ControlError("instance_not_ready")
            controller._model_allowed(principal, row["model_key"], row["mode"])
            old_spec = RunnerSpec(**json.loads(row["spec"]))
            key, mode = row["model_key"], row["mode"]
            saved = controller.registry.cuda_profile(db, slot_id, key) if mode == "cuda" else None
            if mode == "cuda" and saved is None and old_spec.review.get("launch", {}).get("cuda_profile") is not None:
                saved = old_spec.review["launch"]["cuda_profile"]
            context = payload.get("context_tokens",
                                  old_spec.review.get("launch", {}).get("context_tokens"))
            telemetry = controller.backend.telemetry()
            rows = [r for r in controller._rows(db) if r["instance_id"] != old_id]
            assessment = controller._gate(key, mode, telemetry, rows, context, saved)
            _validate_context_before_stop(controller, key, context)
            if assessment["requires_ack"]:
                if not assessment["risk_ack_allowed"]:
                    raise ControlError("resource_risk_not_permitted", 403)
                if payload.get("risk_ack") is not True:
                    token = controller.registry.risk_token(db, principal, slot_id, key, mode, assessment)
                    db.commit()
                    return {"manager_id": controller.config["manager_id"],
                            "stage": "RISK_CONFIRMATION_REQUIRED", "request_id": request_id,
                            "slot_id": slot_id, "instance_id": old_id,
                            "risk_token": token, "forecast": assessment["forecast"],
                            "warnings": assessment["warnings"]}
                controller.registry.confirm_risk(db, principal,
                    {**payload, "model_key": key, "mode": mode}, slot_id, assessment)
            new_id = uuid.uuid4().hex
            new_spec = controller._spec(slot, key, mode)
            launch = dict(new_spec.review.get("launch", {}))
            if mode == "cuda" and saved is not None:
                launch["cuda_profile"] = saved
            if context is not None:
                launch["context_tokens"] = context
            new_spec = replace(new_spec, instance_id=new_id,
                review={**new_spec.review, "launch": launch}, resources=assessment["policy"])
            db.execute("UPDATE instances SET state='STOPPING',created=? WHERE id=? AND state='READY'",
                       (time.time(), old_id))
            db.execute("""INSERT INTO restart_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (principal["client_id"], request_id, fingerprint, slot_id, old_id,
                        key, mode, old_spec.api_id, new_id, json.dumps(asdict(new_spec)),
                        "STOPPING", None, time.time()))
            db.commit()
        try:
            controller.dispatch(lambda: _worker(controller, principal["client_id"], request_id,
                                                  old_spec, new_spec, old_id, new_id, release))
        except Exception:
            _stage(controller, principal["client_id"], request_id, "ERROR", "restart_interrupted")
            raise ControlError("restart_dispatch_failed", 503) from None
        handed_off = True
        return status(controller, principal, request_id)
    finally:
        if not handed_off:
            release()
