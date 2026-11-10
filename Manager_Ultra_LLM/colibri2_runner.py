"""0D controlled first CPU trial, integrated through server_runner --colibri2.

Only the owner runs this on the server. All writes stay in manager_dev/instances/
slot2. Existing setup.json is never read or copied. Common weights and Colibri
sources are read-only. START requires explicit first-trial policy acknowledgement.
STOP signals a session-specific supervisor event after PID/birth/image/SID
verification; the supervisor drains its gateway and closes its OWN Windows job.
No services, LAN listener, Git, downloads, primary-process changes or kill-by-PID.

Policy FIRST_CPU_14G: --ram 10 (expert-cache input, not an OS RAM limit),
14 GiB committed-memory cap across the new job, >=24 GiB available at admission,
10 GiB free-RAM watchdog, 2 CPU threads, 2048 context, 256 output, one KV slot.
Existing games/Ollama/Colibri already reduce actual free RAM; the former 20 GiB
reserve is not subtracted again. This is an explicit bounded owner-run trial.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from launch_contract import initial_instances
from manager_core import SERVER, planned_paths
from resource_catalog import initial_catalogue
from server_preflight import (INSTALLATION_QUERY, PROJECT, probe_api, read_profiles,
                              require_local_server)
from server_runner import managed_slot
from windows_process import NativeWindows, WindowsError

ROOT = PROJECT / "Colibri" / "manager_dev"
HOME = ROOT / "instances" / "slot2"
MODEL_KEY = "qwen36"
API_ID = "ultra-colibri2-qwen36-cpu"
POLICY = "FIRST_CPU_14G"
MUTEX = r"Global\UltraLLM-Colibri2-8001-lifecycle"
GIB = 2**30


class StartDenied(RuntimeError):
    pass


class OwnerCancelled(Exception):
    pass


def stamp():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def paths():
    item = next(x for x in initial_instances() if x.slot_id == "slot2")
    base = planned_paths(managed_slot(item))
    original = Path(base["instance_home"])
    result = {key: (value if key == "shared_weights_ro"
                    else str(HOME / Path(value).relative_to(original)))
              for key, value in base.items()}
    result.update(runtime=str(HOME / "runtime"),
                  setup_json=str(HOME / "setup" / "setup.json"),
                  gateway_pid=str(HOME / "tmp" / "coli-serve-8001.pid"),
                  gateway_stop=str(HOME / "tmp" / "coli-serve-8001.stop"))
    return result


def safe_write_path(value):
    target = Path(value)
    if not target.resolve().is_relative_to(HOME.resolve()) or not HOME.resolve().is_relative_to(ROOT.resolve()):
        raise StartDenied("Instance path escaped manager_dev; no write")
    return target


def write_json(path, data):
    path = safe_write_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = safe_write_path(path.with_name(path.name + f".{os.getpid()}.tmp"))
    with temp.open("w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
    os.replace(temp, path)


def read_state():
    path = safe_write_path(paths()["state"])
    if not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise StartDenied("Invalid instance state; no lifecycle action") from error
    if (type(state) is not dict or state.get("instance") != "slot2"
            or state.get("port") != 8001
            or not re.fullmatch(r"[0-9a-f]{32}", str(state.get("session", "")))):
        raise StartDenied("Foreign or malformed instance state")
    return state


def policy_check(free_gib):
    if type(free_gib) not in (int, float) or not 24 <= free_gib < float("inf"):
        raise StartDenied("FIRST_CPU_14G requires at least 24 GiB actually available RAM")


def verified_cli(launcher):
    source = launcher.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    flags = {argument.value for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
             and node.func.attr == "add_argument" and isinstance(node.func.value, ast.Name)
             and node.func.value.id in ("common", "ps")
             for argument in node.args if isinstance(argument, ast.Constant)
             and isinstance(argument.value, str)}
    required = {"--model", "--ram", "--ctx", "--gpu", "--cap", "--ngen",
                "--no-tune-profile", "--no-think", "--host", "--port",
                "--model-id", "--kv-slots", "--max-queue", "--queue-timeout"}
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    if not required <= flags or not {"serve_pidfile", "serve_stopfile", "_watch_stop_file"} <= functions:
        raise StartDenied("Installed source CLI/stop protocol differs; no guessed flags")
    version = ast.parse(launcher.with_name("version.py").read_text(encoding="utf-8-sig"))
    if not any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__"
               for t in n.targets) and isinstance(n.value, ast.Constant)
               and n.value.value == "2.1.0" for n in version.body):
        raise StartDenied("Expected verified Colibri 2.1.0 source")


def get_primary(native):
    listeners = native.listeners()
    pids = {r["pid"] for r in listeners if r["port"] == 8000}
    if len(pids) != 1:
        raise StartDenied("Primary listener identity unknown")
    with native.process(pids.pop()) as handle:
        gateway = native.identity(handle)
    metadata = probe_api(8000)
    if metadata.get("health") != "ok" or not any(
            "qwen3.6" in name.casefold() or "qwen36" in name.casefold()
            for name in metadata.get("model_ids", [])):
        raise StartDenied("Colibri1 health/model unavailable; do not start another model")
    return gateway


def make_plan(native):
    require_local_server()
    policy_check(native.memory()["free_gib"])
    if any(row["port"] == 8001 for row in native.listeners()):
        raise StartDenied("Port 8001 occupied; no stop or automatic port change")
    primary = get_primary(native)
    with native.process(os.getpid()) as own_handle:
        owner = native.identity(own_handle)["owner_sid"]
    if primary["owner_sid"] != owner:
        raise StartDenied("Use the same server Windows account as Colibri1")
    # Installed executable is discovered from the RUNNING process, never setup.json.
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
        "System32/WindowsPowerShell/v1.0/powershell.exe")
    result = subprocess.run(
        [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", INSTALLATION_QUERY],
        capture_output=True, text=True, check=True, timeout=30,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    inventory = json.loads(result.stdout)
    candidates = [r for r in inventory["processes"] if r["parent_pid"] == primary["pid"]
                  and str(r.get("name", "")).casefold() == "qwen36.exe"]
    if inventory.get("host") != SERVER or len(candidates) != 1:
        raise StartDenied("Cannot identify the actual Colibri1 engine/runtime")
    with native.process(candidates[0]["pid"]) as handle:
        engine_record = native.identity(handle)
    if engine_record["owner_sid"] != owner:
        raise StartDenied("Primary engine owner mismatch")
    engine = Path(engine_record["exe"])
    if not engine.is_absolute() or engine.name.casefold() != "qwen36.exe" or not engine.is_file():
        raise StartDenied("Installed engine unavailable")
    launcher = PROJECT / "Colibri" / "c" / "coli"
    verified_cli(launcher)
    profile = read_profiles(PROJECT / "Colibri" / "ULTRA-CONTROL.py").get(
        initial_catalogue()[MODEL_KEY].profile)
    if not isinstance(profile, dict):
        raise StartDenied("Existing model profile unavailable")
    root = PROJECT / "Base_LLM" / "Models"
    model = root / profile["folder"] / profile.get("subfolder", "")
    if not model.resolve().is_relative_to(root.resolve()):
        raise StartDenied("Model path outside shared catalogue")
    config = json.loads((model / "config.json").read_text(encoding="utf-8-sig"))
    gguf = json.loads((model / "gguf.json").read_text(encoding="utf-8-sig"))
    weights = (root / profile["folder"] / "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf").resolve()
    if (config.get("model_type") != "qwen3_5_moe_text" or gguf.get("mode") != "link"
            or gguf.get("arch") != "qwen35moe" or gguf.get("parts") != 1
            or Path(gguf.get("gguf", "")).resolve() != weights
            or not weights.is_file() or weights.stat().st_size != gguf.get("size")):
        raise StartDenied("Existing model link/architecture/size invalid; no import or repair")
    with weights.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise StartDenied("Invalid GGUF header")
    runtime_files = [engine] + sorted(engine.parent.glob("*.dll"))
    # Metadata and executable hashes only: do not hash/copy the 22 GB weights.
    hashes = {str(p): digest(p) for p in (
        launcher, launcher.with_name("openai_server.py"), launcher.with_name("version.py"),
        model / "config.json", model / "gguf.json", engine)}
    return {"instance": "slot2", "port": 8001, "model_key": MODEL_KEY,
            "model": str(model), "model_id": API_ID, "backend": "cpu", "policy": POLICY,
            "primary": primary, "primary_engine": engine_record, "owner_sid": owner,
            "source_engine": str(engine), "launcher": str(launcher),
            "runtime_files": [str(p) for p in runtime_files],
            "runtime_copy_bytes": sum(p.stat().st_size for p in runtime_files),
            "source_hashes": hashes, "paths": paths(),
            "resources": {"cache_ram_cli": 10, "job_private_cap_gib": 14,
                          "min_available_before_gib": 24, "free_floor_gib": 10,
                          "threads": 2, "context": 2048, "max_output": 256, "cap": 8,
                          "range_evidence": "unmeasured_first_trial"}}


def command_and_environment(plan):
    p = plan["paths"]
    engine = str(Path(p["runtime"]) / "qwen36.exe")
    command = [sys.executable, "-B", plan["launcher"], "serve",
               "--model", plan["model"], "--model-id", API_ID,
               "--host", "127.0.0.1", "--port", "8001",
               "--gpu", "none", "--ram", "10", "--ctx", "2048",
               "--ngen", "256", "--cap", "8", "--kv-slots", "1",
               "--max-queue", "1", "--queue-timeout", "60",
               "--no-tune-profile", "--no-think"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "OS",
                              "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}}
    env.update(
        PATH=os.pathsep.join((p["runtime"], str(Path(sys.executable).parent),
                              str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"))),
        COLI_ENGINE=engine, COLI_MODEL=plan["model"], SNAP=plan["model"],
        COLI_CUDA="0", COLI_VULKAN="0", COLI_THINK="0", Q36_MTP="0",
        COLI_SETUP_HOME=p["setup_home"], HEAT_FILE=p["heat"], COLI_USAGE=p["usage"],
        TEMP=p["tmp"], TMP=p["tmp"], TMPDIR=p["tmp"],
        USERPROFILE=str(HOME / "user"), LOCALAPPDATA=str(HOME / "user" / "Local"),
        APPDATA=str(HOME / "user" / "Roaming"), HF_HOME=str(HOME / "cache" / "hf"),
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="2", OMP_THREAD_LIMIT="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2",
    )
    return command, env


def materialize(plan):
    for key in ("instance_home", "setup_home", "runtime", "tmp", "logs", "kv_cache"):
        safe_write_path(plan["paths"][key]).mkdir(parents=True, exist_ok=True)
    for directory in ("state", "cache/hf", "user/Local", "user/Roaming"):
        safe_write_path(HOME / directory).mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(HOME).free < plan["runtime_copy_bytes"] + GIB:
        raise StartDenied("Not enough disk space for the isolated runtime copy")
    for original in map(Path, plan["runtime_files"]):
        target = safe_write_path(Path(plan["paths"]["runtime"]) / original.name)
        if target.exists():
            if digest(original) != digest(target):
                raise StartDenied("Previous runtime copy differs; no overwrite")
        else:
            with original.open("rb") as source, target.open("xb") as destination:
                shutil.copyfileobj(source, destination, 1024 * 1024)
            if digest(original) != digest(target):
                raise StartDenied("Runtime copy integrity check failed")
    command, _ = command_and_environment(plan)
    write_json(plan["paths"]["setup_json"], {
        "version": 1, "instance": "slot2", "backend": "cpu", "host": "127.0.0.1", "port": 8001,
        "engine": str(Path(plan["paths"]["runtime"]) / "qwen36.exe"),
        "launcher": plan["launcher"], "model_dir": plan["model"],
        "args": command[3:], "first_trial_policy": POLICY})


@contextmanager
def file_lock():
    import msvcrt
    path = safe_write_path(paths()["lock"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as stream:
        if path.stat().st_size == 0:
            stream.write(b"\0")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def verify_record(native, record):
    with native.process(record["pid"]) as handle:
        if not native.same(record, native.identity(handle)):
            raise StartDenied("PID/birth/image/SID mismatch; no action")


def verify_primary(native, plan):
    for key in ("primary", "primary_engine"):
        verify_record(native, plan[key])
    owners = {r["pid"] for r in native.listeners() if r["port"] == 8000}
    if owners != {plan["primary"]["pid"]}:
        raise StartDenied("Primary listener changed")


def graceful_stop(native, job, gateway, plan):
    """Only write the isolated upstream stopfile for a verified live job member."""
    with native.process(gateway["pid"]) as handle:
        if not native.same(gateway, native.identity(handle)) or not native.member(handle, job):
            raise StartDenied("Owned gateway identity lost; stopfile not written")
        pidfile = safe_write_path(plan["paths"]["gateway_pid"])
        if int(pidfile.read_text(encoding="utf-8").split()[0]) != gateway["pid"]:
            raise StartDenied("Isolated gateway PID file mismatch")
        safe_write_path(plan["paths"]["gateway_stop"]).write_text("owned-supervisor\n", encoding="utf-8")


def readiness(previous, owners, gateway_pid, engines, api):
    if owners and owners != {gateway_pid}:
        raise StartDenied("Foreign process owns port 8001; only our job will close")
    ready = (owners == {gateway_pid} and bool(engines)
             and api.get("health") == "ok" and API_ID in api.get("model_ids", []))
    if previous == "READY" and not ready:
        raise StartDenied("Colibri2 lost verified readiness; closing only owned job")
    return "READY" if ready else "STARTING"


def supervise(session):
    require_local_server()
    if not re.fullmatch(r"[0-9a-f]{32}", session):
        raise StartDenied("Invalid session")
    native = NativeWindows()
    with native.mutex(MUTEX), file_lock():
        plan = None
        event = job = gateway_handle = None
        state = {"instance": "slot2", "port": 8001, "session": session,
                 "state": "PREPARING", "updated_utc": stamp()}
        with native.process(os.getpid()) as own_handle:
            state["supervisor"] = native.identity(own_handle)
        event_name = rf"Global\UltraLLM-Colibri2-stop-{session}"
        state["stop_event"] = event_name
        try:
            event = native.event(event_name)
            write_json(paths()["state"], state)
            plan = make_plan(native)
            state.update(plan)
            if native.k.WaitForSingleObject(event, 0) == 0:
                raise OwnerCancelled("owner cancelled preparation")
            materialize(plan)
            # Recheck RAM, source, primary and port just before child creation.
            policy_check(native.memory()["free_gib"])
            verify_primary(native, plan)
            if any(row["port"] == 8001 for row in native.listeners()):
                raise StartDenied("Port became occupied during preparation")
            for name, value in plan["source_hashes"].items():
                if digest(Path(name)) != value:
                    raise StartDenied("Reviewed source/model metadata changed during preparation")
            if native.k.WaitForSingleObject(event, 0) == 0:
                raise OwnerCancelled("owner cancelled preparation")
            job = native.job(rf"Global\UltraLLM-Colibri2-job-{session}", 14)
            command, env = command_and_environment(plan)
            log = safe_write_path(Path(plan["paths"]["logs"]) / f"{session}.stdout.log")
            error_log = safe_write_path(Path(plan["paths"]["logs"]) / f"{session}.stderr.log")
            state.update(stdout=str(log), stderr=str(error_log), command=command)
            with log.open("xb") as stdout, error_log.open("xb") as stderr:
                state["state"] = "STARTING"
                gateway_handle, gateway = native.spawn_contained(
                    command, env, str(HOME), stdout, stderr, job)
                state["gateway"] = gateway
                write_json(plan["paths"]["pid"], {
                    "instance": "slot2", "session": session, "supervisor": state["supervisor"],
                    "gateway": gateway, "port": 8001})
                deadline = time.monotonic() + 900
                low_samples = 0
                while native.alive(gateway_handle):
                    state["updated_utc"] = stamp()
                    free = native.memory()["free_gib"]
                    state["free_gib"] = free
                    low_samples = low_samples + 1 if free < 10 else 0
                    if native.k.WaitForSingleObject(event, 0) == 0 or low_samples >= 2:
                        state["state"] = "STOPPING"
                        state["reason"] = "owner stop" if low_samples < 2 else "low server RAM"
                        break
                    verify_primary(native, plan)
                    engines = []
                    for pid in native.job_pids(job):
                        try:
                            with native.process(pid) as handle:
                                identity = native.identity(handle)
                                if (Path(identity["exe"]) == Path(plan["paths"]["runtime"]) / "qwen36.exe"
                                        and native.member(handle, job)):
                                    engines.append(identity)
                        except WindowsError:
                            continue  # child exited between two OS reads
                    state["engines"] = engines
                    owners = {r["pid"] for r in native.listeners() if r["port"] == 8001}
                    api = probe_api(8001) if owners == {gateway["pid"]} and engines else {}
                    previous = state["state"]
                    state["state"] = readiness(previous, owners, gateway["pid"], engines, api)
                    if state["state"] == "READY" and previous != "READY":
                        if probe_api(8000).get("health") != "ok":
                            raise StartDenied("Primary API lost health; closing only Colibri2")
                        state["primary_health_at_ready"] = "ok"
                    if time.monotonic() > deadline and state["state"] != "READY":
                        raise StartDenied("CPU load timeout; closing only owned job")
                    write_json(plan["paths"]["state"], state)
                    time.sleep(1)
                if state["state"] != "STOPPING":
                    raise StartDenied("Owned gateway exited; inspect the isolated stderr log")
                write_json(plan["paths"]["state"], state)
                graceful_stop(native, job, gateway, plan)
                native.k.WaitForSingleObject(gateway_handle, 45000)
        except OwnerCancelled as error:
            state.update(state="STOPPING", reason=str(error))
        except BaseException as error:
            state.update(state="ERROR", reason=str(error))
        finally:
            # Non-inheritable handle, owned by this supervisor alone. Closing
            # affects its descendants, never the existing primary or game server.
            held = []
            cleanup_confirmed = True
            if job:
                try:
                    for pid in native.job_pids(job):
                        context = native.process(pid)
                        held.append((context, context.__enter__()))
                except WindowsError:
                    cleanup_confirmed = False
            native.close(job)  # no new child can escape while membership is inherited
            cleanup_deadline = time.monotonic() + 10
            for context, handle in held:
                try:
                    timeout = max(0, int((cleanup_deadline - time.monotonic()) * 1000))
                    if native.k.WaitForSingleObject(handle, timeout) != 0:
                        cleanup_confirmed = False
                finally:
                    context.__exit__(None, None, None)
            native.close(event)
            native.close(gateway_handle)
            state["job_cleanup_confirmed"] = cleanup_confirmed
            if plan:
                try:
                    verify_primary(native, plan)
                    state["primary_preserved"] = True
                except Exception:
                    state["primary_preserved"] = False
            if state["state"] == "STOPPING" and cleanup_confirmed:
                state["state"] = "STOPPED"
            elif not cleanup_confirmed:
                state.update(state="ERROR", reason="Owned job closed; process exit confirmation incomplete")
            state["updated_utc"] = stamp()
            write_json(paths()["state"], state)
        return state


def status(native):
    state = read_state()
    if state is None:
        return {"instance": "slot2", "port": 8001, "state": "NOT_STARTED"}
    try:
        verify_record(native, state["supervisor"])
    except (KeyError, WindowsError, StartDenied):
        return {**state, "supervisor_verified": False,
                "state": state["state"] if state["state"] in ("STOPPED", "ERROR") else "STALE"}
    return {**state, "supervisor_verified": True}


def stop(native):
    state = read_state()
    if state is None or state["state"] in ("STOPPED", "ERROR"):
        raise StartDenied("No running owned Colibri2; no action")
    with native.process(os.getpid()) as own_handle:
        owner = native.identity(own_handle)["owner_sid"]
    expected = state.get("supervisor")
    if not isinstance(expected, dict) or expected.get("owner_sid") != owner:
        raise StartDenied("Another Windows owner; no STOP")
    name = rf"Global\UltraLLM-Colibri2-stop-{state['session']}"
    if state.get("stop_event") != name:
        raise StartDenied("Foreign stop event")
    # Hold the same queried process handle through signalling (PID reuse guard).
    with native.process(expected["pid"]) as handle:
        if not native.same(expected, native.identity(handle)):
            raise StartDenied("Supervisor identity mismatch; no STOP")
        native.signal_event(name)
        native.k.WaitForSingleObject(handle, 60000)
    result = status(native)
    if result.get("state") != "STOPPED":
        raise StartDenied("Stop not confirmed; inspect status/logs, never kill by PID")
    if any(r["port"] == 8001 for r in native.listeners()):
        raise StartDenied("Port 8001 still occupied; no foreign listener was stopped")
    return result


def run(action, *, acknowledge=False, wait=900):
    require_local_server()
    native = NativeWindows()
    if action == "plan":
        plan = make_plan(native)
        command, env = command_and_environment(plan)
        return {**plan, "state": "PLAN_ONLY", "command": command,
                "cpu_environment": {k: env[k] for k in ("COLI_CUDA", "COLI_VULKAN", "OMP_NUM_THREADS")},
                "launch_performed": False}
    if action == "status":
        return status(native)
    if action == "stop":
        return stop(native)
    if action != "start" or acknowledge is not True:
        raise StartDenied("START requires --ack-first-cpu-policy after owner review")
    if type(wait) is not int or not 1 <= wait <= 900:
        raise StartDenied("Wait must be 1..900 seconds")
    current = status(native)
    if current.get("supervisor_verified"):
        raise StartDenied("Colibri2 already has a verified supervisor")
    session = uuid.uuid4().hex
    # Parent does not materialize or overwrite instance files before lock owner.
    process = subprocess.Popen(
        [sys.executable, "-B", str(Path(__file__).resolve()), "_supervise", session],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        state = read_state()
        if state and state["session"] == session:
            if state["state"] == "READY":
                verify_record(native, state["supervisor"])
                verify_primary(native, state)
                return state
            if state["state"] in ("STOPPED", "ERROR"):
                raise StartDenied(f"Colibri2 failed: {state.get('reason')}; logs: {state.get('stderr')}")
        if process.poll() is not None:
            raise StartDenied("Supervisor refused preparation/lock; no automatic retry. Run --colibri2 plan")
        time.sleep(1)
    return {"instance": "slot2", "session": session, "state": "STARTING_UNCONFIRMED",
            "note": "Check --colibri2 status; --colibri2 stop cancels this instance only"}


if __name__ == "__main__":
    try:
        if len(sys.argv) != 3 or sys.argv[1] != "_supervise":
            raise StartDenied("Use server_runner.py --colibri2 plan/start/status/stop")
        result = supervise(sys.argv[2])
        raise SystemExit(0 if result["state"] == "STOPPED" else 2)
    except Exception as error:
        print(json.dumps({"state": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2)
