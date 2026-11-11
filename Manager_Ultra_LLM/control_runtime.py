"""CONTROL-01 admission/API coordinator. Process authority remains ColibriRunner.

No import-time writes or launches. Disabled unless server owner_go is explicitly
true. SQLite transactions serialize admission across Manager processes. Failed or
ambiguous instances remain quarantined until verified runner cleanup; recovery
never adopts or kills a process by name/PID alone.
"""
from contextlib import closing
from dataclasses import asdict
import json
import math
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

from resource_catalog import initial_catalogue
from colibri2_runner import RunnerSpec, configured
import colibri2_runner as runner


class ControlError(RuntimeError):
    def __init__(self, reason, status=409):
        super().__init__(reason)
        self.reason, self.status = reason, status


def number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


class ColibriBackend:
    """Adapter to the existing supervisor, handles, jobs, stop events and watchdog."""
    def telemetry(self):
        # ModelControl checks configured host before invoking this adapter.
        from windows_process import NativeWindows
        native = NativeWindows()
        vram = None
        import os
        import subprocess
        executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "nvidia-smi.exe"
        if executable.is_file():
            try:
                result = subprocess.run([str(executable), "--id=0", "--query-gpu=memory.total,memory.used,memory.free",
                    "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=5,
                    check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                total, used, free = map(float, result.stdout.strip().split(","))
                if all(number(v) for v in (total, used, free)) and total > 0 and used + free <= total + 2:
                    vram = free / 1024
            except (ValueError, OSError, subprocess.SubprocessError):
                pass
        return {**native.memory(), "ports": [r["port"] for r in native.listeners()],
                "sampled": time.monotonic(), "verified": True,
                "vram_free_gib": vram}

    def preflight(self, spec):
        with configured(spec):
            from windows_process import NativeWindows
            plan = runner.make_plan(NativeWindows())
            runner.verify_review(plan)

    def status(self, spec, instance_id):
        with configured(spec):
            state = runner.run("status")
        if state.get("session") != instance_id:
            return {"state": "ERROR", "reason": "instance_identity_unverified", "released": False}
        status = state.get("state")
        if status in ("STOPPED", "ERROR") and state.get("job_cleanup_confirmed") is True:
            return {"state": status, "released": True, "reason": "runner_finished"}
        if state.get("supervisor_verified") and status in ("STARTING", "READY", "STOPPING", "PREPARING"):
            return {"state": "STARTING" if status == "PREPARING" else status,
                    "released": False, "reason": None}
        return {"state": "ERROR", "released": False, "reason": "supervisor_unverified"}

    def start(self, spec, instance_id):
        with configured(spec):
            runner.run("start", acknowledge=True, session_id=instance_id, wait=1)

    def stop(self, spec, instance_id):
        with configured(spec):
            state = runner.read_state()
            if not state or state.get("session") != instance_id:
                raise ControlError("instance_identity_unverified")
            runner.run("stop")


class ModelControl:
    def __init__(self, config, *, backend=None, dispatch=None):
        self.config = config
        self.backend = backend or ColibriBackend()
        self.dispatch = dispatch or self._dispatch
        self.db_path = None
        options = config.get("control", {})
        if options.get("owner_go") is True:
            if backend is None:
                import socket
                if options.get("host", "").casefold() != socket.gethostname().casefold():
                    raise ValueError("Wrong control host")
            root = Path(options["state_dir"])
            if not root.is_absolute() or not root.is_dir() or root.is_symlink():
                raise ValueError("Existing private control state directory required")
            # Same private-ACL checker as the existing pairing configuration.
            from pairing_server import _require_private_acl
            _require_private_acl(root)
            path = root / "control.sqlite3"
            if path.is_symlink():
                raise ValueError("Invalid control journal")
            self.db_path = path
            with self.db() as db:
                db.execute("CREATE TABLE IF NOT EXISTS instances (id TEXT PRIMARY KEY, slot TEXT NOT NULL, model TEXT NOT NULL, mode TEXT NOT NULL, owner TEXT NOT NULL, state TEXT NOT NULL, released INTEGER NOT NULL, spec TEXT NOT NULL, reason TEXT, created REAL NOT NULL)")
                db.execute("CREATE UNIQUE INDEX IF NOT EXISTS reserved_slot ON instances(slot) WHERE released=0")
                db.execute("CREATE TABLE IF NOT EXISTS requests (owner TEXT, id TEXT, fingerprint TEXT NOT NULL, instance TEXT NOT NULL, PRIMARY KEY(owner,id))")
                db.commit()

    @staticmethod
    def _dispatch(fn):
        threading.Thread(target=fn, daemon=True).start()

    def db(self):
        return closing(sqlite3.connect(self.db_path, timeout=8))

    def _auth(self, principal):
        if not principal or principal.get("control_models") is not True:
            raise ControlError("control_models_required", 403)
        if self.db_path is None:
            raise ControlError("owner_go_required", 503)

    def _spec(self, slot, key, mode):
        options = self.config.get("control", {})
        review = options.get("reviews", {}).get(key, {}).get(mode, {})
        return RunnerSpec(slot["slot_id"], slot["api_port"], key, mode, review,
            host=options.get("host", runner.SERVER), project=str(Path(self.config["colibri_root"]).parent),
            colibri_root=self.config["colibri_root"], models_root=self.config["models_root"],
            instance_root=options.get("instance_root", str(Path(self.config["colibri_root"]) / "manager_dev")),
            manager_root=str(Path(__file__).resolve().parent),
            primary_port=next((s["api_port"] for s in self.config["slots"]
                               if s["slot_id"] == "slot1" or s.get("protected")), 8000))

    def assert_chat_allowed(self, slot_id):
        if self.db_path:
            with self.db() as db:
                row = db.execute("SELECT state FROM instances WHERE slot=? AND released=0", (slot_id,)).fetchone()
            if row and row[0] != "READY":
                raise ControlError("instance_not_ready")

    def _gate(self, key, mode, telemetry, reserved, vram_reserved=0):
        review = self.config.get("control", {}).get("reviews", {}).get(key, {}).get(mode, {})
        if review.get("evidence") not in ("measured", "bounded_owner_trial") or not review.get("source_hashes"):
            raise ControlError("runtime_review_required")
        if (telemetry.get("verified") is not True or not number(telemetry.get("free_gib"))
                or not number(telemetry.get("sampled"))
                or not 0 <= time.monotonic() - telemetry["sampled"] <= 5
                or type(telemetry.get("ports")) is not list):
            raise ControlError("resource_telemetry_unknown", 503)
        # First bounded trial retains reviewed 14 GiB job cap + 10 GiB headroom.
        if telemetry["free_gib"] - reserved*14 < 24:
            raise ControlError("insufficient_ram")
        if mode == "cuda":
            need, free = review.get("vram_gib"), telemetry.get("vram_free_gib")
            if review.get("evidence") != "measured" or not number(need) or need <= 0:
                raise ControlError("cuda_measurement_unverified")
            if not number(free):
                raise ControlError("vram_telemetry_unknown", 503)
            if free - vram_reserved < need + 1:
                raise ControlError("insufficient_vram")

    def _rows(self, db):
        return [dict(zip(("instance_id", "slot_id", "model_key", "mode", "owner", "state",
                          "released", "spec", "reason", "created"), row))
                for row in db.execute("SELECT * FROM instances")]

    def _vram_reserved(self, rows):
        reviews = self.config.get("control", {}).get("reviews", {})
        return sum(reviews.get(r["model_key"], {}).get("cuda", {}).get("vram_gib", 0)
                   for r in rows if r.get("mode") == "cuda" and not r.get("released", False))

    def _sync(self, db):
        for row in self._rows(db):
            # Worker owns transition until it returns; a grace interval prevents
            # treating supervisor boot as a stale lease. No automatic retry.
            if row["released"] or (row["state"] in ("STARTING", "STOPPING") and time.time()-row["created"] < 10):
                continue
            try:
                status = self.backend.status(RunnerSpec(**json.loads(row["spec"])), row["instance_id"])
            except Exception:
                status = {"state": "ERROR", "reason": "recovery_unverified", "released": False}
            db.execute("UPDATE instances SET state=?,reason=?,released=? WHERE id=?",
                (status["state"], status.get("reason"), int(status.get("released") is True), row["instance_id"]))

    @staticmethod
    def _public(row, principal):
        return {k:row[k] for k in ("instance_id", "slot_id", "model_key", "mode", "state", "reason")} | {
            "model_id": f"ultra-{row['slot_id']}-{row['model_key']}-{row['mode']}",
            "released": bool(row["released"]),
            "can_stop": row["owner"] == principal["client_id"] and not row["released"]
                        and row["state"] in ("STARTING", "READY") and principal.get("control_models") is True}

    def catalog(self, principal):
        instances = []
        all_rows = []
        if self.db_path:
            with self.db() as db:
                db.execute("BEGIN IMMEDIATE")
                self._sync(db)
                all_rows = self._rows(db)
                visible = [r for r in all_rows if not r["released"]]
                active_models = {r["model_key"] for r in visible}
                latest = {}
                for row in sorted(all_rows, key=lambda r:r["created"], reverse=True):
                    if row["released"] and row["model_key"] not in active_models:
                        latest.setdefault(row["model_key"], row)
                instances = [self._public(r, principal) for r in [*visible, *latest.values()]
                             if r["slot_id"] in principal["allowed_slots"]]
                db.commit()
        models = []
        telemetry = None
        from server_preflight import read_profiles
        profiles = read_profiles(Path(self.config.get("colibri_root", ".")) / "ULTRA-CONTROL.py")
        for key, choice in initial_catalogue().items() if principal["allowed_slots"] else ():
            if principal.get("allowed_models") is not None and key not in principal["allowed_models"]:
                continue
            modes = {}
            for mode in ("cpu", "cuda"):
                try:
                    self._auth(principal)
                    if any(r["model_key"] == key and not r["released"] for r in all_rows):
                        raise ControlError("model_already_managed")
                    reserved = sum(not r["released"] for r in all_rows)
                    if telemetry is None:
                        telemetry = self.backend.telemetry()
                    t = telemetry
                    self._gate(key, mode, t, reserved, self._vram_reserved(all_rows))
                    if not any(not s.get("protected") and s["slot_id"] != "slot1"
                               and s["api_port"] != 8000 and s["slot_id"] in principal["allowed_slots"]
                               and s["api_port"] not in t["ports"]
                               and not any(i["slot_id"] == s["slot_id"] and not i["released"] for i in all_rows)
                               for s in self.config["slots"]):
                        raise ControlError("no_free_authorized_slot")
                    modes[mode] = {"available": True, "reason": None}
                except ControlError as error:
                    modes[mode] = {"available": False, "reason": error.reason}
                except Exception:
                    modes[mode] = {"available": False, "reason": "runtime_or_telemetry_unverified"}
            profile = profiles.get(choice.profile, {})
            models.append({"key": key, "name": choice.display_name, "modes": modes,
                "directory_name": profile.get("folder"), "api_ids": [profile["model_id"]] if profile.get("model_id") else []})
        return {"manager_id": self.config["manager_id"], "models": models, "instances": instances,
                "control_models": principal.get("control_models") is True}

    def handle(self, principal, payload):
        self._auth(principal)
        op = payload.get("op") if type(payload) is dict else None
        fields = {"start": {"op", "model_key", "mode", "request_id"},
                  "check": {"op", "model_key", "mode", "request_id"},
                  "stop": {"op", "instance_id", "request_id"}}
        if (type(op) is not str or op not in fields or set(payload) != fields[op]
                or type(payload["request_id"]) is not str or not re.fullmatch(r"[a-f0-9]{32}", payload["request_id"])):
            raise ControlError("invalid_control_fields", 400)
        owner = principal["client_id"]
        fingerprint = json.dumps(payload, sort_keys=True)
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            self._sync(db)
            rows = self._rows(db)
            previous = db.execute("SELECT fingerprint,instance FROM requests WHERE owner=? AND id=?",
                                  (owner, payload["request_id"])).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise ControlError("request_id_conflict")
                row = next(r for r in rows if r["instance_id"] == previous[1])
                if row["slot_id"] not in principal["allowed_slots"]:
                    raise ControlError("slot_not_authorized", 403)
                db.commit()
                return {"manager_id": self.config["manager_id"], **self._public(row, principal)}
            if op in ("start", "check"):
                key, mode = payload["model_key"], payload["mode"]
                if type(key) is not str or key not in initial_catalogue() or mode not in ("cpu", "cuda"):
                    raise ControlError("invalid_model_or_mode", 400)
                if principal.get("allowed_models") is not None and key not in principal["allowed_models"]:
                    raise ControlError("model_not_authorized", 403)
                if any(r["model_key"] == key and not r["released"] for r in rows):
                    raise ControlError("model_already_managed")
                try:
                    telemetry = self.backend.telemetry()
                except Exception:
                    raise ControlError("resource_telemetry_unknown", 503) from None
                self._gate(key, mode, telemetry, sum(not r["released"] for r in rows), self._vram_reserved(rows))
                slot = next((s for s in self.config["slots"] if not s.get("protected")
                    and s["slot_id"] != "slot1" and s["api_port"] != 8000
                    and s["slot_id"] in principal["allowed_slots"]
                    and s["api_port"] not in telemetry["ports"]
                    and not any(r["slot_id"] == s["slot_id"] and not r["released"] for r in rows)), None)
                if slot is None:
                    raise ControlError("no_free_authorized_slot")
                spec = self._spec(slot, key, mode)
                try:
                    self.backend.preflight(spec)
                except ControlError:
                    raise
                except Exception as error:
                    reason = str(error)
                    if reason not in ("runtime_review_required", "runtime_or_model_changed",
                                      "cuda_runtime_or_measurement_unverified"):
                        reason = "runtime_preflight_unverified"
                    raise ControlError(reason) from None
                if op == "check":
                    db.commit()
                    return {"manager_id": self.config["manager_id"], "state": "CHECKED", "slot_id": slot["slot_id"]}
                identity = uuid.uuid4().hex
                row = {"instance_id": identity, "slot_id": slot["slot_id"], "model_key": key,
                       "mode": mode, "owner": owner, "state": "STARTING", "released": False,
                       "reason": None, "created": time.time(), "spec": json.dumps(asdict(spec))}
                db.execute("INSERT INTO instances VALUES(?,?,?,?,?,?,?,?,?,?)", tuple(row[k] for k in
                    ("instance_id", "slot_id", "model_key", "mode", "owner", "state", "released", "spec", "reason", "created")))
            else:
                row = next((r for r in rows if r["instance_id"] == payload["instance_id"]), None)
                if not row or row["owner"] != owner or row["slot_id"] not in principal["allowed_slots"]:
                    raise ControlError("instance_not_authorized", 403)
                if row["released"] or row["state"] not in ("READY", "STARTING"):
                    raise ControlError("instance_not_stoppable")
                spec = RunnerSpec(**json.loads(row["spec"]))
                identity = row["instance_id"]
                row["state"] = "STOPPING"
                db.execute("UPDATE instances SET state='STOPPING',created=? WHERE id=?", (time.time(), identity))
            db.execute("INSERT INTO requests VALUES(?,?,?,?)", (owner, payload["request_id"], fingerprint, identity))
            db.commit()
        def perform():
            try:
                getattr(self.backend, op)(spec, identity)
            except Exception:
                # Never release a slot on an ambiguous launch/stop result.
                with self.db() as db:
                    db.execute("UPDATE instances SET state='ERROR',reason='runner_action_unconfirmed' WHERE id=?", (identity,))
                    db.commit()
        self.dispatch(perform)
        return {"manager_id": self.config["manager_id"], **self._public(row, principal)}
