"""0D controlled first CPU trial, integrated through server_runner --colibri2.

CONTROL-01 adds thread-local RunnerSpec configuration; the same supervisor/job/
ownership logic serves authorized Manager operations without changing globals.
Configured CPU/CUDA starts additionally require matching runtime review hashes.

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
from contextvars import ContextVar
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import uuid

from launch_contract import initial_instances, InstanceDefinition
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


@dataclass(frozen=True)
class RunnerSpec:
    """Trusted server configuration; never constructed from an HTTP request."""
    slot_id: str = "slot2"
    port: int = 8001
    model_key: str = "qwen36"
    backend: str = "cpu"
    review: dict = field(default_factory=dict)
    host: str = SERVER
    project: str = str(PROJECT)
    colibri_root: str = str(PROJECT / "Colibri")
    models_root: str = str(PROJECT / "Base_LLM" / "Models")
    instance_root: str = str(ROOT)
    manager_root: str = str(ROOT)
    primary_port: int = 8000
    instance_id: str | None = None
    resources: dict = field(default_factory=dict)

    def __post_init__(self):
        if (type(self.slot_id) is not str or not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", self.slot_id)
                or self.slot_id == "slot1"
                or type(self.port) is not int or not 1024 <= self.port <= 65535
                or type(self.primary_port) is not int or not 1024 <= self.primary_port <= 65535
                or self.port in (8000, 8443, self.primary_port) or self.model_key not in initial_catalogue()
                or self.backend not in ("cpu", "cuda") or type(self.review) is not dict):
            raise ValueError("Invalid managed runner specification")
        if self.instance_id is not None and (type(self.instance_id) is not str or not re.fullmatch(r"[a-f0-9]{32}",self.instance_id)):
            raise ValueError("Invalid instance identity")
        if type(self.resources) is not dict:
            raise ValueError("Invalid resource policy")
        for path in (self.project, self.colibri_root, self.models_root, self.instance_root, self.manager_root):
            if not Path(path).is_absolute() or str(path).startswith("\\\\"):
                raise ValueError("Server-local absolute runner paths required")

    @property
    def home(self):
        root=Path(self.instance_root) / "instances" / self.slot_id
        return root / "sessions" / self.instance_id if self.instance_id else root

    @property
    def api_id(self):
        if self.instance_id:
            return f"ultra-{self.slot_id[:24]}-{self.model_key[:32]}-{self.backend}-{self.instance_id}"
        return f"ultra-{self.slot_id}-{self.model_key}-{self.backend}"

    @property
    def mutex(self):
        if self.slot_id == "slot2" and self.port == 8001:
            return MUTEX  # serialize with the pre-existing owner-run trial
        return rf"Global\UltraLLM-{self.slot_id}-{self.port}-lifecycle"


def require_execution():
    spec = _SPEC.get()
    if spec is None:
        return require_local_server()
    if (os.name != "nt" or socket.gethostname().casefold() != spec.host.casefold()
            or Path(__file__).resolve().parent != Path(spec.manager_root).resolve()):
        raise StartDenied("Wrong server host or installed Manager directory")


def colibri_path():
    return Path(_SPEC.get().colibri_root) if _SPEC.get() else PROJECT / "Colibri"


def models_path():
    return Path(_SPEC.get().models_root) if _SPEC.get() else PROJECT / "Base_LLM" / "Models"


def instance_root():
    return Path(_SPEC.get().instance_root) if _SPEC.get() else ROOT


def primary_port():
    return _SPEC.get().primary_port if _SPEC.get() else 8000


def probe(port):
    return probe_api(port, allowed_ports=(port,)) if _SPEC.get() else probe_api(port)


_SPEC = ContextVar("colibri_runner_spec", default=None)


def setting(name):
    spec = _SPEC.get()
    if spec is not None:
        return getattr(spec, name)
    return {"slot_id": "slot2", "port": 8001, "model_key": MODEL_KEY,
            "api_id": API_ID, "home": HOME, "mutex": MUTEX, "backend": "cpu"}[name]


@contextmanager
def configured(spec):
    token = _SPEC.set(spec)
    try:
        yield
    finally:
        _SPEC.reset(token)


def verify_review(plan):
    spec = _SPEC.get()
    if spec is None:
        return  # retained legacy owner-run FIRST_CPU_14G trial
    review = spec.review
    if review.get("evidence") not in ("measured", "bounded_owner_trial"):
        raise StartDenied("runtime_review_required")
    if review.get("source_hashes") != plan["source_hashes"]:
        raise StartDenied("runtime_or_model_changed")
    if spec.backend == "cuda":
        if (review.get("evidence") != "measured" or not Path(plan["source_engine"]).with_name("coli_cuda.dll").is_file()
                or type(review.get("vram_gib")) not in (int, float)
                or not 0 < review["vram_gib"] < 1024):
            raise StartDenied("cuda_runtime_or_measurement_unverified")
        from resource_policy import read_vram
        vram=read_vram()
        if vram is None:raise StartDenied("vram_telemetry_unknown")
        if vram["free_gib"]<review["vram_gib"]:raise StartDenied("insufficient_vram")


def validate_model(model, root, profile):
    config = json.loads((model / "config.json").read_text(encoding="utf-8-sig"))
    if config.get("model_type") != "qwen3_5_moe_text":
        raise StartDenied("Unsupported model architecture")
    if setting("model_key") == "kat":
        from server_preflight import inspect_kat
        evidence = inspect_kat(model)
        if not evidence["structural_integrity"]:
            raise StartDenied("KAT structural validation failed")
        return [model / "config.json", model / "qwen36_meta.json"]
    gguf = json.loads((model / "gguf.json").read_text(encoding="utf-8-sig"))
    weights = (root / profile["folder"] / "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf").resolve()
    if (gguf.get("mode") != "link" or gguf.get("arch") != "qwen35moe" or gguf.get("parts") != 1
            or Path(gguf.get("gguf", "")).resolve() != weights or not weights.is_file()
            or weights.stat().st_size != gguf.get("size")):
        raise StartDenied("Existing model link/architecture/size invalid; no import or repair")
    with weights.open("rb") as stream:
        if stream.read(4) != b"GGUF":
            raise StartDenied("Invalid GGUF header")
    return [model / "config.json", model / "gguf.json"]


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
    item = InstanceDefinition(setting("slot_id"), "Managed Colibri", SERVER, setting("port"))
    base = planned_paths(managed_slot(item))
    original = Path(base["instance_home"])
    result = {key: (value if key == "shared_weights_ro"
                    else str(setting("home") / Path(value).relative_to(original)))
              for key, value in base.items()}
    result.update(runtime=str(setting("home") / "runtime"),
                  setup_json=str(setting("home") / "setup" / "setup.json"),
                  gateway_pid=str(setting("home") / "tmp" / f"coli-serve-{setting('port')}.pid"),
                  gateway_stop=str(setting("home") / "tmp" / f"coli-serve-{setting('port')}.stop"))
    result["shared_weights_ro"] = str(models_path())
    return result


def safe_write_path(value):
    target = Path(value)
    if not target.resolve().is_relative_to(setting("home").resolve()) or not setting("home").resolve().is_relative_to(instance_root().resolve()):
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
    if (type(state) is not dict or state.get("instance") != setting("slot_id")
            or state.get("port") != setting("port")
            or not re.fullmatch(r"[0-9a-f]{32}", str(state.get("session", "")))):
        raise StartDenied("Foreign or malformed instance state")
    return state


def policy_check(free_gib):
    if _SPEC.get() is not None:
        if type(free_gib) not in (int,float) or not 0<=free_gib<float("inf"):
            raise StartDenied("resource_telemetry_unknown")
        floor=_SPEC.get().resources.get("min_free_at_start_gib",0)
        if free_gib<floor:raise StartDenied("resources_changed_requires_confirmation")
        return
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
    pids = {r["pid"] for r in listeners if r["port"] == primary_port()}
    if len(pids) != 1:
        raise StartDenied("Primary listener identity unknown")
    with native.process(pids.pop()) as handle:
        gateway = native.identity(handle)
    metadata = probe(primary_port())
    model_verified = bool(metadata.get("model_ids")) if _SPEC.get() else any(
            "qwen3.6" in name.casefold() or "qwen36" in name.casefold()
            for name in metadata.get("model_ids", []))
    if metadata.get("health") != "ok" or not model_verified:
        raise StartDenied("Colibri1 health/model unavailable; do not start another model")
    return gateway


def make_plan(native):
    require_execution()
    policy_check(native.memory()["free_gib"])
    if any(row["port"] == setting("port") for row in native.listeners()):
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
    if inventory.get("host") != (_SPEC.get().host if _SPEC.get() else SERVER) or len(candidates) != 1:
        raise StartDenied("Cannot identify the actual Colibri1 engine/runtime")
    with native.process(candidates[0]["pid"]) as handle:
        engine_record = native.identity(handle)
    if engine_record["owner_sid"] != owner:
        raise StartDenied("Primary engine owner mismatch")
    engine = Path(engine_record["exe"])
    if not engine.is_absolute() or engine.name.casefold() != "qwen36.exe" or not engine.is_file():
        raise StartDenied("Installed engine unavailable")
    launcher = colibri_path() / "c" / "coli"
    verified_cli(launcher)
    profile = read_profiles(colibri_path() / "ULTRA-CONTROL.py").get(
        initial_catalogue()[setting("model_key")].profile)
    if not isinstance(profile, dict):
        raise StartDenied("Existing model profile unavailable")
    root = models_path()
    model = root / profile["folder"] / profile.get("subfolder", "")
    if not model.resolve().is_relative_to(root.resolve()):
        raise StartDenied("Model path outside shared catalogue")
    metadata = validate_model(model, root, profile)
    runtime_files = [engine] + sorted(engine.parent.glob("*.dll"))
    # Metadata and executable hashes only: do not hash/copy the 22 GB weights.
    hashes = {str(p): digest(p) for p in (
        launcher, launcher.with_name("openai_server.py"), launcher.with_name("version.py"),
        *metadata, *runtime_files)}
    plan = {"instance": setting("slot_id"), "port": setting("port"), "model_key": setting("model_key"),
            "model": str(model), "model_id": setting("api_id"), "backend": setting("backend"), "policy": POLICY,
            "primary": primary, "primary_engine": engine_record, "owner_sid": owner,
            "source_engine": str(engine), "launcher": str(launcher),
            "runtime_files": [str(p) for p in runtime_files],
            "runtime_copy_bytes": sum(p.stat().st_size for p in runtime_files),
            "source_hashes": hashes, "paths": paths(),
            "resources": {"cache_ram_cli": 10, "job_private_cap_gib": 14,
                          "min_available_before_gib": 24, "free_floor_gib": 10,
                          "threads": 2, "context": 2048, "max_output": 256, "cap": 8,
                          "range_evidence": "unmeasured_first_trial"}}
    if _SPEC.get():
        plan.update(policy="MODEL_REVIEW",resources=_SPEC.get().resources,
                    launch_options=_SPEC.get().review.get("launch",{}))
    return plan


def command_and_environment(plan):
    p = plan["paths"]
    engine = str(Path(p["runtime"]) / "qwen36.exe")
    command = [sys.executable, "-B", plan["launcher"], "serve",
               "--model", plan["model"], "--model-id", setting("api_id"),
               "--host", "127.0.0.1", "--port", str(setting("port")),
               "--gpu", "none" if setting("backend") == "cpu" else "0", "--ram", "10", "--ctx", "2048",
               "--ngen", "256", "--cap", "32" if setting("model_key") == "kat" else "8", "--kv-slots", "1",
               "--max-queue", "1", "--queue-timeout", "60",
               "--no-tune-profile", "--no-think"]
    env = {key: value for key, value in os.environ.items()
           if key.upper() in {"SYSTEMROOT", "WINDIR", "COMSPEC", "SYSTEMDRIVE", "OS",
                              "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS"}}
    env.update(
        PATH=os.pathsep.join((p["runtime"], str(Path(sys.executable).parent),
                              str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32"))),
        COLI_ENGINE=engine, COLI_MODEL=plan["model"], SNAP=plan["model"],
        COLI_CUDA="0" if setting("backend") == "cpu" else "1", COLI_VULKAN="0", COLI_THINK="0", Q36_MTP="0",
        COLI_SETUP_HOME=p["setup_home"], HEAT_FILE=p["heat"], COLI_USAGE=p["usage"],
        TEMP=p["tmp"], TMP=p["tmp"], TMPDIR=p["tmp"],
        USERPROFILE=str(setting("home") / "user"), LOCALAPPDATA=str(setting("home") / "user" / "Local"),
        APPDATA=str(setting("home") / "user" / "Roaming"), HF_HOME=str(setting("home") / "cache" / "hf"),
        HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1",
        PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="2", OMP_THREAD_LIMIT="2", OPENBLAS_NUM_THREADS="2", MKL_NUM_THREADS="2",
    )
    if _SPEC.get() is not None:
        launch=_SPEC.get().review.get("launch",{})
        if type(launch) is not dict or set(launch)-{"cache_ram_gib","context_tokens","max_output_tokens","threads","thinking","load_timeout_seconds"}:
            raise StartDenied("invalid_launch_policy")
        for flag in ("--ram","--ctx","--ngen"):
            index=command.index(flag);del command[index:index+2]
        command.remove("--no-think")
        env.pop("COLI_THINK",None)
        for name in ("OMP_NUM_THREADS","OMP_THREAD_LIMIT","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS"):
            env.pop(name,None)
        for key,flag in (("cache_ram_gib","--ram"),("context_tokens","--ctx"),("max_output_tokens","--ngen")):
            value=launch.get(key)
            if value is not None:
                if type(value) is not int or not 1<=value<=2147483647:raise StartDenied("invalid_launch_policy")
                command.extend([flag,str(value)])
        if launch.get("thinking") is not None:
            if type(launch["thinking"]) is not bool:raise StartDenied("invalid_launch_policy")
            env["COLI_THINK"]="1" if launch["thinking"] else "0"
            if not launch["thinking"]:command.append("--no-think")
        if launch.get("threads") is not None:
            value=launch["threads"]
            if type(value) is not int or not 1<=value<=1024:raise StartDenied("invalid_launch_policy")
            env.update({k:str(value) for k in ("OMP_NUM_THREADS","OMP_THREAD_LIMIT","OPENBLAS_NUM_THREADS","MKL_NUM_THREADS")})
    return command, env


def materialize(plan):
    for key in ("instance_home", "setup_home", "runtime", "tmp", "logs", "kv_cache"):
        safe_write_path(plan["paths"][key]).mkdir(parents=True, exist_ok=True)
    for directory in ("state", "cache/hf", "user/Local", "user/Roaming"):
        safe_write_path(setting("home") / directory).mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(setting("home")).free < plan["runtime_copy_bytes"] + GIB:
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
        "version": 1, "instance": setting("slot_id"), "backend": setting("backend"), "host": "127.0.0.1", "port": setting("port"),
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
    owners = {r["pid"] for r in native.listeners() if r["port"] == primary_port()}
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
             and api.get("health") == "ok" and setting("api_id") in api.get("model_ids", []))
    if previous == "READY" and not ready:
        raise StartDenied("Colibri2 lost verified readiness; closing only owned job")
    return "READY" if ready else "STARTING"


def supervise(session):
    require_execution()
    if not re.fullmatch(r"[0-9a-f]{32}", session):
        raise StartDenied("Invalid session")
    if _SPEC.get() and _SPEC.get().instance_id and session!=_SPEC.get().instance_id:
        raise StartDenied("Instance/session mismatch")
    native = NativeWindows()
    with native.mutex(setting("mutex")), file_lock():
        plan = None
        event = job = gateway_handle = None
        state = {"instance": setting("slot_id"), "port": setting("port"), "session": session,
                 "state": "PREPARING", "updated_utc": stamp()}
        with native.process(os.getpid()) as own_handle:
            state["supervisor"] = native.identity(own_handle)
        event_name = rf"Global\UltraLLM-{setting('slot_id') if _SPEC.get() else 'Colibri2'}-stop-{session}"
        state["stop_event"] = event_name
        try:
            event = native.event(event_name)
            write_json(paths()["state"], state)
            plan = make_plan(native)
            state.update(plan)
            if native.k.WaitForSingleObject(event, 0) == 0:
                raise OwnerCancelled("owner cancelled preparation")
            verify_review(plan)
            materialize(plan)
            # Recheck RAM, source, primary and port just before child creation.
            policy_check(native.memory()["free_gib"])
            verify_primary(native, plan)
            if any(row["port"] == setting("port") for row in native.listeners()):
                raise StartDenied("Port became occupied during preparation")
            for name, value in plan["source_hashes"].items():
                if digest(Path(name)) != value:
                    raise StartDenied("Reviewed source/model metadata changed during preparation")
            if native.k.WaitForSingleObject(event, 0) == 0:
                raise OwnerCancelled("owner cancelled preparation")
            cap=_SPEC.get().resources.get("job_limit_gib") if _SPEC.get() else 14
            job = native.job(rf"Global\UltraLLM-{setting('slot_id')}-job-{session}", cap)
            command, env = command_and_environment(plan)
            log = safe_write_path(Path(plan["paths"]["logs"]) / f"{session}.stdout.log")
            error_log = safe_write_path(Path(plan["paths"]["logs"]) / f"{session}.stderr.log")
            state.update(stdout=str(log), stderr=str(error_log), command=command)
            with log.open("xb") as stdout, error_log.open("xb") as stderr:
                state["state"] = "STARTING"
                gateway_handle, gateway = native.spawn_contained(
                    command, env, str(setting("home")), stdout, stderr, job)
                state["gateway"] = gateway
                write_json(plan["paths"]["pid"], {
                    "instance": setting("slot_id"), "session": session, "supervisor": state["supervisor"],
                    "gateway": gateway, "port": setting("port")})
                load_timeout=_SPEC.get().review.get("launch",{}).get("load_timeout_seconds",900) if _SPEC.get() else 900
                if type(load_timeout) is not int or not 1<=load_timeout<=3600:raise StartDenied("invalid_launch_timeout")
                deadline = time.monotonic() + load_timeout
                low_samples = 0
                while native.alive(gateway_handle):
                    state["updated_utc"] = stamp()
                    free = native.memory()["free_gib"]
                    state["free_gib"] = free
                    threshold=_SPEC.get().resources.get("ram_warning_gib",10) if _SPEC.get() else 10
                    low_samples = low_samples + 1 if free < threshold else 0
                    state["resource_warnings"]=["low_ram"] if low_samples else []
                    owner_stop=native.k.WaitForSingleObject(event,0)==0
                    if owner_stop or (_SPEC.get() is None and low_samples >= 2):
                        state["state"] = "STOPPING"
                        state["reason"] = "owner stop" if owner_stop else "low server RAM"
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
                    owners = {r["pid"] for r in native.listeners() if r["port"] == setting("port")}
                    api = probe(setting("port")) if owners == {gateway["pid"]} and engines else {}
                    previous = state["state"]
                    state["state"] = readiness(previous, owners, gateway["pid"], engines, api)
                    if state["state"] == "READY" and previous != "READY":
                        if probe(primary_port()).get("health") != "ok":
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
        return {"instance": setting("slot_id"), "port": setting("port"), "state": "NOT_STARTED"}
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
    name = rf"Global\UltraLLM-{setting('slot_id') if _SPEC.get() else 'Colibri2'}-stop-{state['session']}"
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
    if any(r["port"] == setting("port") for r in native.listeners()):
        raise StartDenied("Port 8001 still occupied; no foreign listener was stopped")
    return result


def run(action, *, acknowledge=False, wait=900, session_id=None):
    require_execution()
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
    session = session_id or (_SPEC.get().instance_id if _SPEC.get() else None) or uuid.uuid4().hex
    if not re.fullmatch(r"[a-f0-9]{32}", session):
        raise StartDenied("Invalid session")
    # Parent does not materialize or overwrite instance files before lock owner.
    process = subprocess.Popen(
        [sys.executable, "-B", str(Path(__file__).resolve()), "_supervise", session] +
        ([json.dumps(asdict(_SPEC.get()))] if _SPEC.get() else []),
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
    return {"instance": setting("slot_id"), "session": session, "state": "STARTING_UNCONFIRMED",
            "note": "Check --colibri2 status; --colibri2 stop cancels this instance only"}


if __name__ == "__main__":
    try:
        if len(sys.argv) not in (3, 4) or sys.argv[1] != "_supervise":
            raise StartDenied("Use server_runner.py --colibri2 plan/start/status/stop")
        with configured(RunnerSpec(**json.loads(sys.argv[3])) if len(sys.argv) == 4 else None):
            result = supervise(sys.argv[2])
        raise SystemExit(0 if result["state"] == "STOPPED" else 2)
    except Exception as error:
        print(json.dumps({"state": "BLOCKED", "reason": str(error)}))
        raise SystemExit(2)
