#!/usr/bin/env python3
"""Ultra's offline-only Colibri controller. Python 3.12, standard library only.

Never calls setup/start/build, installs packages, or fetches releases/models.
Lifecycle operations must run on the actual server, not from an SMB client.
"""
from __future__ import annotations

import argparse
import contextlib
import ctypes
import datetime as dt
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
MODEL = PROJECT / "Base_LLM" / "Models" / "Qwen3-Coder-30B-A3B"
REPORTS = PROJECT / "Documents" / "Reports" / "CODEX-ULTRA-LLM-COLIBRI-START-001"
EXPECTED_HOST = "DESKTOP-KT4G5SM"
MODEL_ID = "qwen3-coder-30b-a3b-colibri"
SELECTED_PROFILE = "qwen"
PROFILES = {
    "qwen": {"name": "Qwen3-Coder-30B-A3B", "folder": "Qwen3-Coder-30B-A3B",
             "engine": "qwen36.exe", "model_id": "qwen3-coder-30b-a3b-colibri",
             "ram": 12, "ctx": 16384, "cap": 32, "wait": 300},
    "deepseek": {"name": "DeepSeek-V4-Flash-REAP-150B", "folder": "DeepSeek-V4-Flash-REAP-150B",
                 "engine": "deepseek_v4.exe", "model_id": "deepseek-v4-flash-reap-150b-colibri",
                 "ram": 24, "ctx": 16384, "cap": 16, "wait": 600},
}
GIB = 1024 ** 3
SECRET = re.compile(r"(?i)(bearer\s+)[^\s\"']+|((?:api[_-]?key|password|token|secret)[\"']?\s*[:=]\s*[\"']?)[^\s,\"']+")


class ControlError(RuntimeError):
    pass


def select_profile(name):
    global SELECTED_PROFILE, MODEL, MODEL_ID
    SELECTED_PROFILE = name
    profile = PROFILES[name]
    MODEL = PROJECT / "Base_LLM" / "Models" / profile["folder"]
    MODEL_ID = profile["model_id"]


def previous_profile(home):
    state = read_json(state_file(home), {})
    plan = state.get("plan") or {}
    if plan.get("profile") in PROFILES:
        return plan["profile"]
    folder = str(plan.get("model", "")).replace("\\", "/").rstrip("/").rsplit("/", 1)[-1]
    return next((key for key, profile in PROFILES.items() if profile["folder"] == folder), "qwen")


def clean(value):
    return SECRET.sub(lambda m: (m.group(1) or m.group(2) or "") + "[REDACTED]", str(value))


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return default


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def digest(path):
    with open(path, "rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def inside(path, parent):
    try:
        Path(path).resolve().relative_to(Path(parent).resolve())
        return True
    except (ValueError, OSError):
        return False


def require_server():
    if os.name != "nt" or os.environ.get("COMPUTERNAME", "").upper() != EXPECTED_HOST:
        raise ControlError(f"Run this BAT ON {EXPECTED_HOST}, signed in as the user who installed Colibri. "
                           "Opening a BAT over SMB on the home PC does not execute it on the server.")
    if str(ROOT).startswith("\\\\"):
        raise ControlError("Run the local server copy of ULTRA-START/STOP/STATUS.bat, not a UNC copy.")


def home_path(explicit=None):
    return Path(explicit or os.environ.get("COLI_SETUP_HOME") or
                str(Path(os.environ.get("LOCALAPPDATA", "")) / "colibri")).resolve()


class Windows:
    """Query/terminate one verified process handle. Never kill by image name."""
    def __init__(self):
        from ctypes import wintypes as w
        self.w = w
        self.k = ctypes.WinDLL("kernel32", use_last_error=True)
        self.k.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]
        self.k.OpenProcess.restype = w.HANDLE
        self.k.CloseHandle.argtypes = [w.HANDLE]
        self.k.WaitForSingleObject.argtypes = [w.HANDLE, w.DWORD]
        self.k.WaitForSingleObject.restype = w.DWORD
        self.k.GetProcessTimes.argtypes = [w.HANDLE] + [ctypes.POINTER(w.FILETIME)] * 4
        self.k.GetProcessTimes.restype = w.BOOL
        self.k.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
        self.k.TerminateProcess.restype = w.BOOL

    @contextlib.contextmanager
    def process(self, pid, terminate=False):
        rights = 0x1000 | 0x100000 | (1 if terminate else 0)
        handle = self.k.OpenProcess(rights, False, int(pid))
        try:
            yield handle
        finally:
            if handle:
                self.k.CloseHandle(handle)

    def identity(self, pid):
        with self.process(pid) as handle:
            if not handle or self.k.WaitForSingleObject(handle, 0) != 258:
                return None
            times = [self.w.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(handle, *(ctypes.byref(x) for x in times)):
                return None
            born = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            return {"pid": int(pid), "created_filetime": born}

    def matches(self, record):
        return bool(record and self.identity(record["pid"]) ==
                    {k: record[k] for k in ("pid", "created_filetime")})

    def terminate(self, record):
        # Validate birth time again on the SAME handle that is terminated.
        with self.process(record["pid"], terminate=True) as handle:
            if not handle or self.k.WaitForSingleObject(handle, 0) != 258:
                return
            times = [self.w.FILETIME() for _ in range(4)]
            if not self.k.GetProcessTimes(handle, *(ctypes.byref(x) for x in times)):
                raise ControlError("Cannot verify process creation time; refusing termination")
            born = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
            if born != record["created_filetime"]:
                raise ControlError("PID was reused; refusing termination")
            if not self.k.TerminateProcess(handle, 1):
                raise ControlError(f"Cannot stop verified Colibri PID {record['pid']}; use the same Windows user/elevation")


def memory():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong)] + [
            (n, ctypes.c_ulonglong) for n in ("total", "available", "page_total", "page_available",
                                           "virtual_total", "virtual_available", "extended")]
    state = MEMORYSTATUSEX()
    state.length = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        raise ControlError("Cannot read server memory")
    return {"total_gib": round(state.total / GIB, 2),
            "available_gib": round(state.available / GIB, 2), "load_percent": state.load}


def inspect_deepseek(model, config):
    wanted = {"model_type": "deepseek_v4", "num_hidden_layers": 43,
              "n_routed_experts": 132, "hidden_size": 4096, "num_experts_per_tok": 6}
    if any(config.get(k) != v for k, v in wanted.items()):
        raise ControlError("DeepSeek does not match the inspected 43-layer / 132-expert REAP-150B checkpoint")
    if not (model / "tokenizer.json").is_file():
        raise ControlError("DeepSeek tokenizer.json is missing; nothing will be downloaded")
    index = read_json(model / "model.safetensors.index.json", {})
    mapping = index.get("weight_map")
    if not isinstance(mapping, dict) or not mapping:
        raise ControlError("DeepSeek safetensors index is missing/invalid")
    if any(not isinstance(n, str) or Path(n).name != n or "/" in n or "\\" in n
           for n in mapping.values()):
        raise ControlError("DeepSeek shard index contains an unsafe path")
    names = sorted(set(mapping.values()))
    seen, types, total = set(), set(), 0
    for name in names:
        path = model / name
        size = path.stat().st_size
        with path.open("rb") as handle:
            raw = handle.read(8)
            if len(raw) != 8:
                raise ControlError("Truncated DeepSeek shard header: " + name)
            length = struct.unpack("<Q", raw)[0]
            if not 2 <= length <= min(16 * 1024 * 1024, size - 8):
                raise ControlError("Invalid DeepSeek shard header length: " + name)
            header = json.loads(handle.read(length))
        intervals = []
        for key, tensor in header.items():
            if key == "__metadata__":
                continue
            start, end = tensor["data_offsets"]
            if key in seen or mapping.get(key) != name or not 0 <= start <= end <= size - length - 8:
                raise ControlError("Invalid DeepSeek tensor mapping/bounds: " + key)
            seen.add(key)
            types.add(tensor["dtype"])
            intervals.append((start, end))
        ordered = sorted(intervals)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ControlError("Overlapping DeepSeek tensors: " + name)
        total += size
    if seen != set(mapping):
        raise ControlError("DeepSeek index references missing tensors")
    return {"name": PROFILES["deepseek"]["name"], "path": str(model), "geometry": wanted,
            "shards": len(names), "tensor_headers_checked": len(seen), "bytes": total,
            "tensor_storage_types": sorted(types), "source_index_complete": True,
            "conversion_required": False, "check": "headers_index_and_bounds_only_not_full_weight_hashes"}


def inspect_model(model=None):
    selected = model is None
    model = Path(model or MODEL)
    config = read_json(model / "config.json", {})
    if config.get("model_type") == "deepseek_v4":
        if selected and SELECTED_PROFILE != "deepseek":
            raise ControlError("The selected Qwen directory contains a DeepSeek model")
        return inspect_deepseek(model, config)
    if selected and SELECTED_PROFILE != "qwen":
        raise ControlError("The selected DeepSeek directory does not contain a deepseek_v4 model")
    wanted = {"model_type": "qwen3_moe", "num_hidden_layers": 48, "num_experts": 128, "hidden_size": 2048}
    if any(config.get(k) != v for k, v in wanted.items()):
        raise ControlError("Model geometry is not Qwen3-Coder-30B-A3B; refusing a misleading model label")
    for name in ("tokenizer.json", "qwen36_meta.json"):
        if not (model / name).is_file():
            raise ControlError(f"Missing model file: {name}; nothing will be downloaded")
    meta = read_json(model / "qwen36_meta.json", {})
    if meta.get("model_type") != "qwen3_moe" or meta.get("n_layers") != 48 or meta.get("num_experts") != 128:
        raise ControlError("Converted model metadata disagrees with config.json")
    names = [f"model-{layer:05d}.safetensors" for layer in range(48)] + ["model-globals.safetensors"]
    count, total, types = 0, 0, set()
    for name in names:
        path = model / name
        size = path.stat().st_size
        with path.open("rb") as handle:
            raw = handle.read(8)
            if len(raw) != 8:
                raise ControlError(f"Truncated safetensors header: {name}")
            length = struct.unpack("<Q", raw)[0]
            if not 2 <= length <= min(16 * 1024 * 1024, size - 8):
                raise ControlError(f"Invalid safetensors header length: {name}")
            header = json.loads(handle.read(length))
        tensors = [(key, value) for key, value in header.items() if key != "__metadata__"]
        if not tensors:
            raise ControlError(f"No tensors in {name}")
        intervals = []
        for key, tensor in tensors:
            start, end = tensor["data_offsets"]
            if not 0 <= start <= end <= size - 8 - length:
                raise ControlError(f"Tensor offset outside shard: {name}: {key}")
            intervals.append((start, end))
            types.add(tensor["dtype"])
        ordered = sorted(intervals)
        if any(a[1] > b[0] for a, b in zip(ordered, ordered[1:])):
            raise ControlError(f"Overlapping tensors in {name}")
        total += size
        count += len(tensors)
    return {"name": "Qwen3-Coder-30B-A3B", "path": str(model), "geometry": wanted,
            "shards": len(names), "tensor_headers_checked": count, "bytes": total,
            "tensor_storage_types": sorted(types), "check": "headers_and_file_bounds_only_not_full_weight_hashes"}


def remove_options(args, names):
    result, i = [], 0
    while i < len(args):
        arg = args[i]
        key = arg.split("=", 1)[0]
        if key in names:
            if "=" not in arg and names[key]:
                if i + 1 >= len(args):
                    raise ControlError(f"Missing saved argument value: {key}")
                i += 1
        else:
            result.append(arg)
        i += 1
    return result


def configuration(home):
    cfg = read_json(home / "setup.json")
    if not isinstance(cfg, dict) or cfg.get("version") != 1:
        raise ControlError(f"Existing setup.json is missing/invalid: {home / 'setup.json'}. "
                           "Run STATUS as the original server user; setup is NOT invoked automatically.")
    for name in ("engine", "launcher", "host", "port", "backend"):
        if name not in cfg:
            raise ControlError(f"Existing setup.json has no {name}")
    return cfg


def plan_run(home, ram=None, ctx=None, cap=None, backend=None):
    cfg = configuration(home)
    profile = PROFILES[SELECTED_PROFILE]
    ram = profile["ram"] if ram is None else ram
    ctx = profile["ctx"] if ctx is None else ctx
    cap = profile["cap"] if cap is None else cap
    engine = Path(cfg["engine"]).resolve().with_name(profile["engine"])
    launcher = Path(cfg["launcher"]).resolve()
    for path in (engine, launcher):
        if not path.is_file() or not (inside(path, PROJECT) or inside(path, home)):
            raise ControlError(f"Configured existing runtime file is unavailable/unexpected: {path}")
    if engine.name.lower() != profile["engine"] or launcher.name.lower() != "coli":
        raise ControlError("Expected the selected model's installed engine and coli Python launcher")
    launcher_source = launcher.read_text(encoding="utf-8-sig")
    if "_watch_stop_file" not in launcher_source or "serve_stopfile" not in launcher_source:
        raise ControlError("Installed launcher lacks the verified graceful stop-file protocol")
    saved = cfg.get("args") or []
    if not isinstance(saved, list) or not saved or saved[0] not in ("web", "serve"):
        raise ControlError("Saved runtime arguments must describe web/serve, never setup/start/build")
    if not all(isinstance(a, str) for a in saved):
        raise ControlError("Saved runtime arguments are not strings")
    if any(a.split("=", 1)[0] in ("--cluster-workers", "--cluster-coordinator") for a in saved):
        raise ControlError("Saved cluster execution is outside this local-model launcher; no remote workers were contacted")
    backend = backend or cfg["backend"]
    if backend not in ("cpu", "cuda", "vulkan"):
        raise ControlError("Backend must be cpu, cuda or vulkan")
    if SELECTED_PROFILE == "deepseek" and backend == "vulkan":
        raise ControlError("This DeepSeek profile supports the inspected CUDA or CPU path; Vulkan was not verified")
    port = int(cfg["port"])
    if not 1 <= port <= 65535:
        raise ControlError("Invalid configured API port")
    if not 4 <= ram <= 64 or not 512 <= ctx <= 16384 or not 1 <= cap <= 128:
        raise ControlError("Safe limits: --ram 4..64 GB, --ctx 512..16384, --cap 1..128")
    # Credentials are moved to the child environment, never command logs/state.
    env = os.environ.copy()
    env.update({str(k): str(v) for k, v in (cfg.get("env") or {}).items()})
    for i, arg in enumerate(saved):
        if arg == "--api-key" and i + 1 < len(saved):
            env["COLI_API_KEY"] = saved[i + 1]
        elif arg.startswith("--api-key="):
            env["COLI_API_KEY"] = arg.split("=", 1)[1]
    stripped = remove_options(saved[1:], {"--model": True, "--host": True, "--port": True,
        "--model-id": True, "--api-key": True, "--ram": True, "--ctx": True, "--ngen": True, "--cap": True,
        "--auto-tier": False, "--no-browser": False, "--no-tune-profile": False,
        "--gpu": True})
    command = [sys.executable, str(launcher), "serve"] + stripped + [
        "--model", str(MODEL), "--model-id", MODEL_ID, "--host", str(cfg["host"]),
        "--port", str(port), "--ram", str(ram), "--ctx", str(ctx), "--ngen", str(ctx), "--cap", str(cap),
        "--no-tune-profile"]
    if backend == "cuda":
        command += ["--gpu", "auto"]
    elif backend == "cpu":
        command += ["--gpu", "none"]
    env.update(COLI_ENGINE=str(engine), COLI_MODEL=str(MODEL), SNAP=str(MODEL),
               COLI_CUDA="1" if backend == "cuda" else "0",
               COLI_VULKAN="1" if backend == "vulkan" else "0",
               PYTHONUNBUFFERED="1", PYTHONDONTWRITEBYTECODE="1", COLI_COLOR="0")
    env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", HF_DATASETS_OFFLINE="1")
    if SELECTED_PROFILE == "deepseek":
        command += ["--no-think"]
        # The server has an 8 GiB RTX 3070. Keep the large prefill expert bank
        # off beside dense mirrors. Use only the already installed generic DLL.
        env.update(DSV4_CUDA="1" if backend == "cuda" else "0",
                   CUDA_DENSE="1" if backend == "cuda" else "0",
                   COLI_CUDA_ATTN_BATCH="1" if backend == "cuda" else "0",
                   COLI_CUDA_MOE_BATCH="0", DSV4_CUDA_TC="0",
                   COLI_DSV4_DLL=str(engine.parent / "coli_cuda_dsv4.dll"),
                   DSV4_CUDA_EXPERT_MIRRORS="32", DSV4_CUDA_VRAM_RESERVE_MB="768",
                   V4_DRAFT="0", V4_MTP="0")
        if backend == "cuda" and not (engine.parent / "coli_cuda_dsv4.dll").is_file():
            raise ControlError("Existing runtime has no generic coli_cuda_dsv4.dll; no download/extraction was attempted")
    # Vulkan resources and DLL discovery stay beside the installed engine.
    env["PATH"] = str(engine.parent) + os.pathsep + env.get("PATH", "")
    if backend == "vulkan" and (engine.parent / "shaders").is_dir():
        env.setdefault("COLI_VK_SHADERS", str(engine.parent / "shaders"))
    host = str(cfg["host"])
    shown = "127.0.0.1" if host in ("0.0.0.0", "::", "") else host
    if shown == "::1":
        shown = "[::1]"
    if host not in ("127.0.0.1", "localhost", "::1", "") and not env.get("COLI_API_KEY"):
        raise ControlError("Existing LAN binding has no API key; refusing insecure startup. No settings changed.")
    return {"home": str(home), "engine": str(engine), "launcher": str(launcher),
            "profile": SELECTED_PROFILE, "model_name": profile["name"],
            "model": str(MODEL), "model_id": MODEL_ID, "host": host, "port": port,
            "base_url": f"http://{shown}:{port}", "backend": backend,
            "config_path": str(home / "setup.json"),
            "saved_model_name": (cfg.get("model") or {}).get("name"),
            "saved_model_dir": cfg.get("model_dir"),
            "ram_gb": ram, "ctx": ctx, "cap": cap, "command": command,
            "config_sha256": digest(home / "setup.json"), "environment": env}


def public_plan(plan):
    return {k: v for k, v in plan.items() if k not in ("environment", "command")}


def available_profiles(plan):
    runtime = Path(plan["engine"]).parent
    return {key: {"name": profile["name"],
                  "model_directory_present": (PROJECT / "Base_LLM" / "Models" / profile["folder"]).is_dir(),
                  "engine_present": (runtime / profile["engine"]).is_file(),
                  "generic_cuda_dll_present": (runtime / "coli_cuda_dsv4.dll").is_file() if key == "deepseek" else None,
                  "note": "File presence only; does not prove load or generation"}
            for key, profile in PROFILES.items()}


def active_stop_plan(home, requested, win):
    """STOP follows the active session, not the next requested model."""
    state = read_json(state_file(home), {})
    recorded = state.get("plan") or {}
    owned = [state.get("supervisor"), state.get("gateway")] + state.get("engines", [])
    if recorded and any(win.matches(item) for item in owned if item):
        for key in ("engine", "launcher"):
            if not (inside(recorded[key], PROJECT) or inside(recorded[key], home)):
                raise ControlError("Recorded active runtime path is outside the approved installation")
        if Path(recorded["engine"]).name.lower() not in {p["engine"] for p in PROFILES.values()}:
            raise ControlError("Unexpected recorded active engine")
        return dict(requested, **recorded)
    return requested


def publish_supervisor(state):
    """Small, credential-free shared evidence; no access to the private profile needed."""
    record = dict(state)
    if record.get("log"):
        record["log_tail"] = tail(record["log"], 70)
    write_json(REPORTS / "SUPERVISOR-STATE.json", record)


PROCESS_SCRIPT = r'''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$launchers=(ConvertFrom-Json -InputObject $env:ULTRA_LAUNCHERS).paths
$otherEngines=(ConvertFrom-Json -InputObject $env:ULTRA_OTHER_ENGINES).paths
$otherNames=@($otherEngines | ForEach-Object {[IO.Path]::GetFileName($_)})
$wantedModel=$env:ULTRA_MODEL.ToLowerInvariant()
$rows=@(Get-CimInstance Win32_Process | ForEach-Object {
 $p=$_; $kind=$null; $line=[string]$p.CommandLine
 if($p.ExecutablePath -and $p.ExecutablePath.Equals($env:ULTRA_ENGINE,[StringComparison]::OrdinalIgnoreCase)){$kind='engine'}
 elseif(-not $p.ExecutablePath -and $p.Name.Equals([IO.Path]::GetFileName($env:ULTRA_ENGINE),[StringComparison]::OrdinalIgnoreCase)){$kind='engine_unverified_path'}
 elseif($otherEngines -contains $p.ExecutablePath){$kind='other_model_engine'}
 elseif(-not $p.ExecutablePath -and $otherNames -contains $p.Name){$kind='other_model_engine_unverified_path'}
 elseif($p.Name -match '^pythonw?\.exe$' -and $line -match '\s(?:serve|web)\s') {
  foreach($launcher in $launchers){
   $portMatch=[regex]::Match($line,'--port(?:=|\s+)["'']?(\d+)(?!\d)')
   $port=if($portMatch.Success){[int]$portMatch.Groups[1].Value}else{8000}
   if($line.IndexOf($launcher,[StringComparison]::OrdinalIgnoreCase) -ge 0 -and
      $line.ToLowerInvariant().Contains($wantedModel) -and $port -eq [int]$env:ULTRA_PORT){$kind='gateway';break}
  }
 }
 if($kind){[pscustomobject]@{pid=[int]$p.ProcessId;ppid=[int]$p.ParentProcessId;
   kind=$kind;path=$p.ExecutablePath;working_set_bytes=[long]$p.WorkingSetSize;
   private_bytes=[long]$p.PrivatePageCount}}
})
ConvertTo-Json -InputObject $rows -Compress
'''


def processes(plan, win):
    env = os.environ.copy()
    env.update(ULTRA_ENGINE=plan["engine"], ULTRA_MODEL=plan["model"],
               ULTRA_PORT=str(plan["port"]),
               ULTRA_OTHER_ENGINES=json.dumps({"paths": [str(Path(plan["engine"]).with_name(p["engine"]))
                    for p in PROFILES.values() if p["engine"] != Path(plan["engine"]).name.lower()]}),
               ULTRA_LAUNCHERS=json.dumps({"paths": [plan["launcher"], str(ROOT / "c" / "coli")]}))
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", PROCESS_SCRIPT],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", env=env,
                            timeout=20, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise ControlError("Cannot inspect Colibri processes with local CIM: " + clean(result.stderr[-800:]))
    rows = json.loads(result.stdout.strip() or "[]")
    if isinstance(rows, dict):
        rows = [rows]
    out = []
    for row in rows:
        identity = win.identity(row["pid"])
        if identity:
            row.update(identity)
            out.append(row)
    return out


def api(plan, path, timeout=3):
    headers = {}
    if plan.get("environment", {}).get("COLI_API_KEY"):
        headers["Authorization"] = "Bearer " + plan["environment"]["COLI_API_KEY"]
    request = urllib.request.Request(plan["base_url"] + path, headers=headers)
    # Local API must never go through a workstation/server proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            if not (response.headers.get("Server", "").split()[:1] == ["colibri"]):
                return {"error": "Port answered by a non-Colibri server"}
            return json.load(response)
    except (OSError, ValueError, urllib.error.URLError) as error:
        return {"error": clean(error)}


def gpu_status(owned_engine_pids=()):
    executable = shutil.which("nvidia-smi")
    if not executable:
        return {"nvidia_smi": "not available; Vulkan/CPU must be verified from engine evidence"}
    try:
        result = subprocess.run([executable, "--query-gpu=index,name,driver_version,memory.total,memory.used,utilization.gpu",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        applications = subprocess.run([executable, "--query-compute-apps=pid,process_name,used_gpu_memory",
                                      "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=10,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        allowed = {int(pid) for pid in owned_engine_pids}
        app_lines = applications.stdout.strip().splitlines()
        matching = [line for line in app_lines if line.split(",", 1)[0].strip().isdigit()
                    and int(line.split(",", 1)[0].strip()) in allowed]
        return {"nvidia_smi_exit": result.returncode, "gpus_csv": result.stdout.strip(),
                "colibri_compute_apps_csv": "\n".join(matching),
                "other_process_entries_omitted": len(app_lines) - len(matching),
                "error": clean(result.stderr.strip())}
    except (OSError, subprocess.SubprocessError) as error:
        return {"error": clean(error)}


def state_file(home):
    return home / "ultra" / "state.json"


@contextlib.contextmanager
def lifecycle_lock(home):
    import msvcrt
    path = home / "ultra" / "controller.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        if path.stat().st_size == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as error:
            raise ControlError("Another Ultra start/stop operation is in progress") from error
        yield
    finally:
        handle.close()


def request_gateway_stop(plan, record, win):
    if not win.matches(record):
        return False
    pidfile = Path(tempfile.gettempdir()) / f"coli-serve-{plan['port']}.pid"
    try:
        pid = int(pidfile.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return False
    if pid != record["pid"] or not win.matches(record):
        return False
    stopfile = pidfile.with_suffix(".stop")
    stopfile.write_text("Ultra requests graceful Colibri shutdown\n", encoding="utf-8")
    return True


def tail(path, lines=35):
    try:
        with open(path, "rb") as handle:
            handle.seek(0, 2)
            handle.seek(max(0, handle.tell() - 32768))
            return clean("\n".join(handle.read().decode("utf-8", "replace").splitlines()[-lines:]))
    except OSError:
        return "No log file yet"


def export_status(data):
    # Windows may deny os.replace while another process has SERVER-STATUS.json
    # open without FILE_SHARE_DELETE. Reporting must not block START/STOP/STATUS.
    target = REPORTS / "SERVER-STATUS.json"
    try:
        write_json(target, data)
    except OSError as error:
        with contextlib.suppress(OSError):
            target.with_name(target.name + f".{os.getpid()}.tmp").unlink()
        alternate = REPORTS / (
            f"SERVER-STATUS-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S%f}-{os.getpid()}.json"
        )
        try:
            write_json(alternate, data)
            print(f"WARNING: Primary status report is locked ({clean(error)}). "
                  f"Snapshot saved to {alternate}", file=sys.stderr)
        except OSError as fallback_error:
            print(f"WARNING: Status reporting unavailable: {clean(error)}; "
                  f"fallback failed: {clean(fallback_error)}", file=sys.stderr)
    lines = ["# Colibri server status", "", f"Checked: {data['checked_at']}",
             "", "```json", json.dumps(data, ensure_ascii=False, indent=2), "```", ""]
    try:
        (REPORTS / "SERVER-STATUS.md").write_text("\n".join(lines), encoding="utf-8")
    except OSError as error:
        print(f"WARNING: Could not update Markdown status report: {clean(error)}", file=sys.stderr)


def snapshot(plan, win):
    rows = processes(plan, win)
    health = api(plan, "/health")
    models = api(plan, "/v1/models") if health.get("status") == "ok" else {}
    state = read_json(state_file(Path(plan["home"])), {})
    gateway = state.get("gateway")
    owned = bool(gateway and win.matches(gateway))
    active = bool(rows)
    status = "ready" if health.get("status") == "ok" else "loading_or_unresponsive" if active else "stopped"
    advertised = [item.get("id") for item in models.get("data", [])]
    if status == "ready" and plan.get("model_id", MODEL_ID) not in advertised:
        status = "different_model_ready"
    return {"checked_at": stamp(), "computer": os.environ.get("COMPUTERNAME"),
            "status": status, "plan": public_plan(plan), "health": health, "models": models,
            "memory": memory(), "colibri_processes": rows, "managed_gateway_verified": owned,
            "engine_process_count": sum(row["kind"] == "engine" for row in rows),
            "configured_backend": plan["backend"],
            "available_profiles": available_profiles(plan),
            "running_plan": state.get("plan") if owned else None,
            "backend_verification": "inspect health tiers/hwinfo, engine log and NVIDIA process list; configuration alone is not GPU proof",
            "gpu": gpu_status([r["pid"] for r in rows if r["kind"] == "engine"]),
            "colibri_working_sets_gib": round(sum(r.get("working_set_bytes", 0) for r in rows) / GIB, 3),
            "colibri_private_bytes_gib": round(sum(r.get("private_bytes", 0) for r in rows) / GIB, 3),
            "log_path": state.get("log") or str(Path(plan["home"]) / "logs" / "serve.log"),
            "supervisor_state": {key: state.get(key) for key in ("status", "reason", "updated_at")}}


def prepare_start(args, home, win):
    # The caller holds the lifecycle lock only during this preparation/spawn.
    # STOP must remain usable while the parent waits for a slow model to load.
    model = inspect_model()
    plan = plan_run(home, args.ram, args.ctx, args.cap, args.backend)
    current = snapshot(plan, win)
    prior = read_json(state_file(home), {})
    pending = read_json(home / "ultra" / "request.json", {})
    if (not prior.get("supervisor") or not win.matches(prior["supervisor"])) and pending.get("supervisor"):
        prior = pending
    if prior.get("supervisor") and win.matches(prior["supervisor"]):
        print("An existing Ultra supervisor owns this session; no duplicate was started.")
        export_status(current)
        print_status(current)
        advertised = [m.get("id") for m in current["models"].get("data", [])]
        return 0 if (current["status"] == "ready" and plan.get("model_id", MODEL_ID) in advertised
                     and current.get("managed_gateway_verified") and current.get("engine_process_count", 0) >= 1) else 2
    if current["colibri_processes"] or current["health"].get("status") == "ok":
        export_status(current)
        print("Colibri process/API already exists; no duplicate was started.")
        print_status(current)
        advertised = [m.get("id") for m in current["models"].get("data", [])]
        return 0 if (current["status"] == "ready" and plan.get("model_id", MODEL_ID) in advertised
                     and current.get("managed_gateway_verified") and current.get("engine_process_count", 0) >= 1) else 2
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        try:
            probe.bind((plan["host"] or "0.0.0.0", plan["port"]))
        except OSError as error:
            raise ControlError("Configured port is occupied/unavailable; no automatic port change") from error
    available = current["memory"]["available_gib"]
    reserve = max(3.0, current["memory"]["total_gib"] * 0.12)
    if available < min(args.ram + reserve, 9.0 + reserve):
        raise ControlError(f"Only {available:.1f} GiB free. Need at least {min(args.ram + reserve, 9 + reserve):.1f} "
                           "GiB before safe startup; no process was started")
    print(f"Existing setup: {home / 'setup.json'} (read-only)")
    print(f"Model: {model['name']}; {model['shards']} weight shards structurally checked")
    print(f"Session limits: --ram {args.ram} GB, --ctx {args.ctx}, --cap {args.cap}; backend={plan['backend']}")
    print("Reason: replace automatic RAM/cache sizing for the first controlled run. RAM is a planner budget, not an OS hard limit.")
    print("No setup, start, build, package installation, release/model download, or automatic backend fallback.")
    session = uuid.uuid4().hex
    request = {"session": session, "profile": SELECTED_PROFILE, "ram": args.ram, "ctx": args.ctx, "cap": args.cap,
               "backend": args.backend, "config_sha256": plan["config_sha256"], "reserve_gib": reserve}
    write_json(home / "ultra" / "request.json", request)
    write_json(REPORTS / "START-PREFLIGHT.json", {"checked_at": stamp(), "model": model,
               "memory_before": current["memory"], "plan": public_plan(plan)})
    flags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP
    process = subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()), "_supervise",
                               "--setup-home", str(home), "--session", session, "--model", SELECTED_PROFILE],
                              cwd=str(ROOT), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                              stderr=subprocess.DEVNULL, creationflags=flags)
    identity = win.identity(process.pid)
    if not identity:
        raise ControlError("Supervisor exited immediately")
    # Bootstrap identity is separate from the child's state: no parent/child
    # last-writer race can erase a freshly recorded gateway PID.
    request["supervisor"] = identity
    write_json(home / "ultra" / "request.json", request)
    return process, session, plan


def start(args, home, win):
    with lifecycle_lock(home):
        prepared = prepare_start(args, home, win)
    if isinstance(prepared, int):
        return prepared
    process, session, plan = prepared
    print(f"Supervisor PID: {process.pid}; waiting up to {args.wait}s for a healthy engine...", flush=True)
    deadline = time.monotonic() + args.wait
    previous = None
    while time.monotonic() < deadline:
        state = read_json(state_file(home), {})
        if state.get("session") == session:
            if state.get("status") in ("failed", "stopped"):
                raise ControlError(f"Startup failed/stopped: {state.get('reason')}. Log: {state.get('log')}")
            if api(plan, "/health").get("status") == "ok":
                status = snapshot(plan, win)
                ids = [m.get("id") for m in status["models"].get("data", [])]
                if plan.get("model_id", MODEL_ID) not in ids or not status["managed_gateway_verified"] or status["engine_process_count"] < 1:
                    raise ControlError("API answered but expected model/owned gateway/engine could not be verified; run STOP")
                export_status(status)
                print_status(status)
                return 0
            if state.get("status") != previous:
                print(f"State: {state.get('status')}; log: {state.get('log')}", flush=True)
                previous = state.get("status")
        if process.poll() is not None:
            raise ControlError("Supervisor exited before reporting readiness; inspect logs in setup-home/ultra")
        time.sleep(1)
    export_status(snapshot(plan, win))
    print("NOT READY: startup timeout. The owned supervisor remains monitored; use STATUS or STOP.")
    return 2


def supervise(args, home, win):
    request = read_json(home / "ultra" / "request.json", {})
    if request.get("session") != args.session:
        raise ControlError("Supervisor session mismatch")
    if request.get("profile", "qwen") != SELECTED_PROFILE:
        raise ControlError("Supervisor model profile mismatch; no engine was started")
    state = {"session": args.session, "supervisor": win.identity(os.getpid()), "status": "starting", "updated_at": stamp()}
    log_dir = home / "ultra" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (dt.datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + args.session[:8] + ".log")
    state["log"] = str(log_path)
    gateway = None
    known_engines = {}
    plan = None
    try:
        plan = plan_run(home, request["ram"], request["ctx"], request["cap"], request.get("backend"))
        if plan["config_sha256"] != request["config_sha256"]:
            raise ControlError("setup.json changed between preflight and launch")
        with log_path.open("a", encoding="utf-8", buffering=1) as log:
            log.write(f"Ultra session {args.session}; {stamp()}\n")
            log.write("Command (no credentials): " + subprocess.list2cmdline(plan["command"]) + "\n")
            gateway = subprocess.Popen(plan["command"], cwd=str(Path(plan["launcher"]).parent),
                                       env=plan["environment"], stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            state["gateway"] = win.identity(gateway.pid)
            if not state["gateway"]:
                raise ControlError("Gateway exited before its identity could be recorded")
            state.update(status="loading", plan=public_plan(plan))
            write_json(state_file(home), state)
            publish_supervisor(state)
            low_count = 0
            last_publish = 0.0
            while gateway.poll() is None:
                rows = processes(plan, win)
                for row in rows:
                    if row["kind"] == "engine" and row["ppid"] == gateway.pid:
                        known_engines[row["pid"]] = row
                state["engines"] = list(known_engines.values())
                stopping = read_json(home / "ultra" / "stop.json", {}).get("session") == args.session
                free = memory()["available_gib"]
                low_count = low_count + 1 if free < request["reserve_gib"] else 0
                if stopping or low_count >= 2:
                    state.update(status="stopping", reason="owner requested stop" if stopping else "low available server RAM")
                    write_json(state_file(home), state)
                    publish_supervisor(state)
                    request_gateway_stop(plan, state["gateway"], win)
                    try:
                        gateway.wait(timeout=40)
                    except subprocess.TimeoutExpired:
                        # Snapshot ownership was established while the parent was alive.
                        win.terminate(state["gateway"])
                    break
                state.update(status="ready" if api(plan, "/health").get("status") == "ok" else "loading",
                             available_ram_gib=free, updated_at=stamp())
                write_json(state_file(home), state)
                if time.monotonic() - last_publish >= 12:
                    publish_supervisor(state)
                    last_publish = time.monotonic()
                time.sleep(3)
            state.setdefault("reason", f"gateway exit code {gateway.poll()}")
    except Exception as error:
        state.update(status="failed", reason=clean(error))
        if gateway and gateway.poll() is None:
            if plan and state.get("gateway"):
                request_gateway_stop(plan, state["gateway"], win)
                try:
                    gateway.wait(timeout=40)
                except subprocess.TimeoutExpired:
                    win.terminate(state["gateway"])
    finally:
        # Only children with the recorded creation time and exact configured engine path.
        if plan and gateway:
            try:
                for row in processes(plan, win):
                    if row["kind"] == "engine" and row["ppid"] == gateway.pid:
                        known_engines[row["pid"]] = row
            except ControlError as error:
                state.update(status="failed", reason=clean(error))
        time.sleep(1)
        for record in known_engines.values():
            if win.matches(record):
                try:
                    win.terminate(record)
                except ControlError as error:
                    state.update(status="failed", reason=clean(error))
        alive = [r for r in known_engines.values() if win.matches(r)]
        if alive:
            state.update(status="failed", reason="owned engine still alive", remaining_engines=alive)
        elif state.get("status") != "failed":
            state["status"] = "stopped"
        state["updated_at"] = stamp()
        write_json(state_file(home), state)
        publish_supervisor(state)


def stop(args, home, win):
    with lifecycle_lock(home):
        requested = plan_run(home, args.ram, args.ctx, args.cap, args.backend)
        plan = active_stop_plan(home, requested, win)
        state = read_json(state_file(home), {})
        pending = read_json(home / "ultra" / "request.json", {})
        if (not state.get("supervisor") or not win.matches(state["supervisor"])) and pending.get("supervisor"):
            if win.matches(pending["supervisor"]):
                state = pending
        rows = processes(plan, win)
        gateways = [r for r in rows if r["kind"] == "gateway"]
        supervisor = state.get("supervisor")
        if supervisor and win.matches(supervisor):
            write_json(home / "ultra" / "stop.json", {"session": state["session"], "requested_at": stamp()})
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline and win.matches(supervisor):
                time.sleep(0.5)
        else:
            # An existing START-HERE run can be asked to drain without killing Python.
            for record in gateways:
                request_gateway_stop(plan, record, win)
            deadline = time.monotonic() + 45
            while gateways and time.monotonic() < deadline and any(win.matches(r) for r in gateways):
                time.sleep(0.5)
        remaining = processes(plan, win)
        if args.force_orphans:
            for record in remaining:
                if (record["kind"] == "engine" and not win.identity(record["ppid"])
                        and os.path.normcase(record["path"]) == os.path.normcase(plan["engine"])):
                    win.terminate(record)
            time.sleep(1)
            remaining = processes(plan, win)
        status = snapshot(plan, win)
        export_status(status)
        if remaining or status["health"].get("status") == "ok":
            print_status(status)
            raise ControlError("Colibri is NOT fully stopped. Unowned orphan engines are not killed by default. "
                               "Review STATUS; --force-orphans targets only the exact configured engine executable, never Python.")
        print("STOPPED: no matching gateway/engine and no healthy API remain. No unrelated Python was terminated.")
        return 0


def print_status(data):
    plan = data["plan"]
    print(f"State: {data['status']}")
    print(f"Requested model: {plan.get('model_name', 'Qwen3-Coder-30B-A3B')} ({plan['model']})")
    print(f"Saved setup label: {plan.get('saved_model_name')}; saved directory: {plan.get('saved_model_dir')}")
    print(f"Configured backend: {plan['backend']} (actual execution evidence below)")
    if data.get("running_plan"):
        print(f"Managed running session: {data['running_plan']['backend']}; "
              f"RAM budget {data['running_plan']['ram_gb']} GB, "
              f"context {data['running_plan']['ctx']}, cap {data['running_plan']['cap']}")
    print(f"API: {plan['base_url']}/v1")
    print(f"Memory: {data['memory']}")
    print(f"Matching processes: {len(data['colibri_processes'])}; engines: {data['engine_process_count']}")
    print(f"Engine health: {json.dumps(data['health'], ensure_ascii=False)}")
    print(f"GPU evidence: {json.dumps(data['gpu'], ensure_ascii=False)}")
    print(f"Log: {data['log_path']}")
    print(f"Saved status: {REPORTS / 'SERVER-STATUS.json'}")


def stream_turn(plan, messages, timeout=180, max_tokens=64):
    url = urllib.parse.urlsplit(plan["base_url"])
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    body = json.dumps({"model": plan.get("model_id", MODEL_ID), "messages": messages, "max_tokens": max_tokens,
                       "temperature": 0, "stream": True, "stream_options": {"include_usage": True}})
    headers = {"Content-Type": "application/json"}
    key = plan.get("environment", {}).get("COLI_API_KEY")
    if key:
        headers["Authorization"] = "Bearer " + key
    start = time.perf_counter()
    first = None
    text, usage, done = [], {}, False
    try:
        connection.request("POST", "/v1/chat/completions", body, headers)
        response = connection.getresponse()
        if response.status != 200:
            raise ControlError(f"Generation HTTP {response.status}: {clean(response.read(2048).decode('utf-8','replace'))}")
        while True:
            remaining = timeout - (time.perf_counter() - start)
            if remaining <= 0:
                raise ControlError("Generation deadline exceeded")
            if connection.sock:
                connection.sock.settimeout(remaining)
            raw = response.readline()
            if not raw:
                break
            line = raw.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                done = True
                break
            event = json.loads(payload)
            if event.get("error"):
                raise ControlError(clean(event["error"]))
            if event.get("usage"):
                usage = event["usage"]
            for choice in event.get("choices", []):
                content = choice.get("delta", {}).get("content") or ""
                if content:
                    first = first or time.perf_counter()
                    text.append(content)
        elapsed = time.perf_counter() - start
        tokens = usage.get("completion_tokens")
        if not done or not text or not isinstance(tokens, int) or tokens <= 0:
            raise ControlError("Incomplete/empty stream or missing measured completion_tokens")
        return {"text": "".join(text), "completion_tokens": tokens, "usage": usage,
                "elapsed_s": round(elapsed, 4), "time_to_first_text_s": round(first - start, 4),
                "tokens_per_second_including_prefill": round(tokens / elapsed, 3),
                "stream_finished": done}
    finally:
        connection.close()


def benchmark(plan, win):
    before = snapshot(plan, win)
    ids = [row.get("id") for row in before["models"].get("data", [])]
    if before["status"] != "ready" or plan.get("model_id", MODEL_ID) not in ids:
        raise ControlError("Real generation tests require a healthy API advertising the selected model ID")
    engines = [(r["pid"], r["created_filetime"]) for r in before["colibri_processes"] if r["kind"] == "engine"]
    if not engines or not any(r["kind"] == "gateway" for r in before["colibri_processes"]):
        raise ControlError("Cannot verify the local model's gateway/engine identities; generation tests were not started")
    messages = [{"role": "user", "content": "Name two primary colors in one short sentence."}]
    results = []
    try:
        for number in (1, 2):
            result = stream_turn(plan, messages, timeout=600 if plan.get("profile") == "deepseek" else 180,
                                 max_tokens=48 if plan.get("profile") == "deepseek" else 64)
            result.update(turn=number, profile=api(plan, "/profile"), gpu_after=gpu_status([r[0] for r in engines]))
            results.append(result)
            messages += [{"role": "assistant", "content": result["text"]},
                         {"role": "user", "content": "Now list those two colors in the reverse order, briefly."}]
            print(f"Turn {number}: {result['completion_tokens']} tokens, {result['elapsed_s']}s, "
                  f"{result['tokens_per_second_including_prefill']} tok/s including prefill", flush=True)
        after = snapshot(plan, win)
        after_engines = [(r["pid"], r["created_filetime"]) for r in after["colibri_processes"] if r["kind"] == "engine"]
        if not engines or sorted(engines) != sorted(after_engines) or after["status"] != "ready":
            raise ControlError("The engine restarted/exited between the two real generation tests")
        record = {"kind": "REAL_SERVER_INFERENCE", "checked_at": stamp(), "passed": True,
                  "profile": plan.get("profile", SELECTED_PROFILE),
                  "turns": results, "before": before, "after": after,
                  "speed_definition": "completion_tokens / client wall time; includes prefill; engine phase data retained in /profile"}
        return record
    except Exception as error:
        record = {"kind": "REAL_SERVER_INFERENCE", "checked_at": stamp(), "passed": False,
                  "profile": plan.get("profile", SELECTED_PROFILE),
                  "turns": results, "error": clean(error), "before": before}
        raise
    finally:
        if 'record' in locals():
            write_json(REPORTS / "REAL-GENERATION-TESTS.json", record)
            write_json(REPORTS / ("REAL-GENERATION-TESTS-" + plan.get("profile", SELECTED_PROFILE) + ".json"), record)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "_supervise"))
    parser.add_argument("--setup-home")
    parser.add_argument("--model", choices=tuple(PROFILES), default=None, help="Profile: qwen or deepseek; default last selected")
    parser.add_argument("--switch", action="store_true", help="START: validate, stop active owned session, start selected model")
    parser.add_argument("--ram", type=int, default=None, help="Session planner RAM budget in GB; not an OS memory cap")
    parser.add_argument("--ctx", type=int, default=None)
    parser.add_argument("--cap", type=int, default=None)
    parser.add_argument("--backend", choices=("cpu", "cuda", "vulkan"), default=None)
    parser.add_argument("--wait", type=int, default=None)
    parser.add_argument("--logs", action="store_true")
    parser.add_argument("--test", action="store_true", help="START/STATUS: two REAL sequential generation requests")
    parser.add_argument("--inspect-model", action="store_true")
    parser.add_argument("--force-orphans", action="store_true", help="STOP: terminate only exact configured engine executable, never Python")
    parser.add_argument("--session", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        require_server()
        home = home_path(args.setup_home)
        select_profile(args.model or previous_profile(home))
        profile = PROFILES[SELECTED_PROFILE]
        for field in ("ram", "ctx", "cap", "wait"):
            if getattr(args, field) is None:
                setattr(args, field, profile[field])
        win = Windows()
        if args.action == "_supervise":
            return supervise(args, home, win) or 0
        if args.action == "start":
            if args.switch:
                # Validate the new files/runtime BEFORE touching a running model.
                inspect_model()
                plan_run(home, args.ram, args.ctx, args.cap, args.backend)
                stop(args, home, win)
            code = start(args, home, win)
            if args.test and code == 0:
                benchmark(plan_run(home, args.ram, args.ctx, args.cap, args.backend), win)
            return code
        if args.action == "stop":
            return stop(args, home, win)
        plan = plan_run(home, args.ram, args.ctx, args.cap, args.backend)
        data = snapshot(plan, win)
        if args.inspect_model:
            data["model_validation"] = inspect_model()
        if args.logs:
            data["log_tail"] = tail(data["log_path"], 70)
        export_status(data)
        print_status(data)
        if args.logs:
            print("\nLast log lines (credential patterns redacted):\n" + data["log_tail"])
        if args.test:
            benchmark(plan, win)
        return 0 if data["status"] == "ready" else 2
    except KeyboardInterrupt:
        print("Wait interrupted. The background session remains owned/monitored. Use ULTRA-STOP.bat to stop it.", file=sys.stderr)
        return 130
    except Exception as error:
        message = clean(error)
        print("ERROR: " + message, file=sys.stderr)
        # Publish a safe diagnostic even when setup.json is missing; no secret config dump.
        if os.environ.get("COMPUTERNAME", "").upper() == EXPECTED_HOST:
            try:
                write_json(REPORTS / "LAST-ERROR.json", {"checked_at": stamp(), "action": args.action,
                           "computer": os.environ.get("COMPUTERNAME"), "error": message,
                           "setup_home": str(home_path(args.setup_home))})
            except OSError:
                pass
        return 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
