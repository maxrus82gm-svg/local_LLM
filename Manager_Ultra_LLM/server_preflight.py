"""0D stage A: owner-executed, read-only installation inspection.

Entry: py -3.12 -B server_runner.py --inspect-server (on DESKTOP-KT4G5SM).
This diagnoses an already running Colibri without applying the old dry-run RAM
admission policy. It never launches an engine, imports weights, writes setup,
reserves a slot, creates a listener, installs a service or signals a process.
The next start command depends on this snapshot and must be run by the owner.
Only selected configuration fields are returned; env, args and keys stay local.
"""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import urllib.error
import urllib.request

from manager_core import SERVER
from resource_catalog import initial_catalogue

PROJECT = Path(r"C:\Server\Ultra_LLM")

# Fixed script, local OS queries only. CommandLine and full config are never
# returned. GetOwnerSid is a read operation, not process control.
INSTALLATION_QUERY = r"""
$ErrorActionPreference = 'Stop'
$osInfo = Get-CimInstance Win32_OperatingSystem
$allProcesses = @(Get-CimInstance Win32_Process)
$allListeners = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
$selectedListeners = @($allListeners | Where-Object {$_.LocalPort -in @(8000,8001)})
$selectedIds = @($selectedListeners | Select-Object -ExpandProperty OwningProcess -Unique)
$selectedProcesses = @($allProcesses | Where-Object {
    $_.ProcessId -in $selectedIds -or
    $_.Name -match '^(qwen.*|colibri|glm|deepseek.*|llama-server|ollama|valheim.*|DayZ.*)\.exe$' -or
    ($_.Name -match '^python(w)?\.exe$' -and
     $_.CommandLine -match '(?i)([\\/]coli(?:\s|["''])|openai_server|ULTRA-CONTROL)')
})
$processRows = @($selectedProcesses | ForEach-Object {
    $ownerSid = $null
    try {
        $ownerResult = Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid -ErrorAction Stop
        if ($ownerResult.ReturnValue -eq 0) {$ownerSid = $ownerResult.Sid}
    } catch {}
    [pscustomobject]@{
        pid = [int]$_.ProcessId
        parent_pid = [int]$_.ParentProcessId
        name = $_.Name
        exe = $_.ExecutablePath
        created_utc = if ($_.CreationDate) {$_.CreationDate.ToUniversalTime().ToString('o')} else {$null}
        owner_sid = $ownerSid
        working_set_gib = [double]$_.WorkingSetSize / 1073741824
        private_bytes_gib = [double]$_.PrivatePageCount / 1073741824
    }
})
[pscustomobject]@{
    host = [Environment]::MachineName
    total_gib = [double]$osInfo.TotalVisibleMemorySize / 1048576
    free_gib = [double]$osInfo.FreePhysicalMemory / 1048576
    listeners = @($selectedListeners | ForEach-Object {
        [pscustomobject]@{address=$_.LocalAddress;port=[int]$_.LocalPort;pid=[int]$_.OwningProcess}
    })
    processes = $processRows
} | ConvertTo-Json -Compress -Depth 6
"""


class PreflightError(RuntimeError):
    pass


def require_local_server():
    actual = socket.gethostname()
    if os.name != "nt" or actual.casefold() != SERVER.casefold():
        raise PreflightError(f"Wrong execution host: {actual}; required {SERVER}")
    expected = PROJECT / "Colibri" / "manager_dev"
    if not expected.is_dir() or not Path(__file__).resolve().is_relative_to(expected.resolve()):
        raise PreflightError("Run the server-local C: copy, not a UNC copy")


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None


def selected_configuration(path):
    cfg = read_json(path)
    if not isinstance(cfg, dict):
        return {"path": str(path), "state": "MISSING_OR_INVALID"}
    fields = {key: cfg.get(key) for key in
              ("engine", "launcher", "host", "port", "backend", "model_dir")}
    # Do not stringify arbitrary objects that might contain secret env/args.
    fields = {key: value if type(value) in (str, int, float, bool, type(None)) else None
              for key, value in fields.items()}
    return {"path": str(path), "state": "READ_ONLY", **fields}


def runtime_inventory(cfg):
    value = cfg.get("engine")
    if type(value) is not str or not value:
        return {"state": "UNKNOWN"}
    engine = Path(value)
    if not engine.is_absolute():
        return {"state": "INVALID_ENGINE_PATH"}
    try:
        files = [{"name": p.name, "bytes": p.stat().st_size}
                 for p in sorted(engine.parent.iterdir())
                 if p.is_file() and p.suffix.lower() in (".exe", ".dll")]
        return {"state": "READ_ONLY", "directory": str(engine.parent),
                "engine_present": engine.is_file(), "files": files,
                "cpu_execution_tested": False}
    except OSError:
        return {"state": "UNREADABLE", "directory": str(engine.parent)}


def read_profiles(controller):
    """Read literal profile data from the existing controller without importing it."""
    try:
        tree = ast.parse(controller.read_text(encoding="utf-8-sig"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "PROFILES"
                    for target in node.targets):
                value = ast.literal_eval(node.value)
                return value if isinstance(value, dict) else {}
    except (OSError, ValueError, TypeError, SyntaxError):
        pass
    return {}


def model_inventory(project=PROJECT):
    profiles = read_profiles(project / "Colibri" / "ULTRA-CONTROL.py")
    root = (project / "Base_LLM" / "Models").resolve()
    rows = []
    for key, model in initial_catalogue().items():
        profile = profiles.get(model.profile)
        if type(profile) is not dict or type(profile.get("folder")) is not str:
            rows.append({"key": key, "state": "PROFILE_UNAVAILABLE"})
            continue
        folder = (root / profile["folder"]).resolve()
        subfolder = profile.get("subfolder", "")
        if type(subfolder) is not str:
            rows.append({"key": key, "state": "INVALID_PROFILE_PATH"})
            continue
        container = (folder / subfolder).resolve()
        if not folder.is_relative_to(root) or not container.is_relative_to(folder):
            rows.append({"key": key, "state": "INVALID_PROFILE_PATH"})
            continue
        try:
            weights = [p for directory in {folder, container} if directory.is_dir()
                       for p in directory.iterdir()
                       if p.is_file() and p.suffix.lower() in (".gguf", ".safetensors")]
            config = read_json(container / "config.json")
            gguf = read_json(container / "gguf.json")
            rows.append({
                "key": key, "state": "READ_ONLY",
                "directory": str(container), "directory_present": container.is_dir(),
                "config_present": isinstance(config, dict),
                "model_type": config.get("model_type") if isinstance(config, dict) else None,
                "gguf_arch": gguf.get("arch") if isinstance(gguf, dict) else None,
                "weight_files": len(weights),
                "weight_bytes": sum(p.stat().st_size for p in weights),
                "integrity_verified": False, "cpu_execution_tested": False,
            })
        except OSError:
            rows.append({"key": key, "state": "UNREADABLE"})
    return rows


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def probe_api(port):
    """Metadata GETs only, no generation, no inherited proxy, no redirects/keys."""
    if type(port) is not int or port not in (8000, 8001):
        raise PreflightError("Only known server loopback ports may be inspected")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    report = {"port": port, "health": "UNKNOWN", "model_ids": []}
    for endpoint in ("/health", "/v1/models"):
        try:
            with opener.open(f"http://127.0.0.1:{port}{endpoint}", timeout=3) as response:
                data = json.loads(response.read(65537))
            if endpoint == "/health":
                report["health"] = data.get("status", "UNKNOWN") if isinstance(data, dict) else "INVALID"
            elif isinstance(data, dict) and isinstance(data.get("data"), list):
                report["model_ids"] = [row["id"] for row in data["data"]
                                       if type(row) is dict and type(row.get("id")) is str]
        except urllib.error.HTTPError as error:
            report[endpoint] = f"HTTP_{error.code}"
        except (OSError, ValueError):
            report[endpoint] = "UNAVAILABLE_OR_INVALID"
    return report


def inspect_server():
    require_local_server()       # before any process/port/API/config query
    executable = Path(os.environ.get("SystemRoot", r"C:\Windows")) / (
        "System32/WindowsPowerShell/v1.0/powershell.exe")
    try:
        result = subprocess.run(
            [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
             "-Command", INSTALLATION_QUERY],
            check=True, capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        machine = json.loads(result.stdout)
        if (type(machine) is not dict or machine.get("host", "").casefold() != SERVER.casefold()
                or type(machine.get("listeners")) is not list
                or type(machine.get("processes")) is not list):
            raise PreflightError("Invalid server inventory")
    except (OSError, ValueError, AttributeError, subprocess.SubprocessError) as error:
        raise PreflightError("Server OS inventory failed; no changes made") from error
    homes = []
    if os.environ.get("COLI_SETUP_HOME"):
        homes.append(Path(os.environ["COLI_SETUP_HOME"]))
    if os.environ.get("LOCALAPPDATA"):
        homes.append(Path(os.environ["LOCALAPPDATA"]) / "colibri")
    configurations = [selected_configuration(home / "setup.json") for home in dict.fromkeys(homes)]
    cfg = next((row for row in configurations if row["state"] == "READ_ONLY"), {})
    return {
        "state": "READ_ONLY_PREFLIGHT", "task": "CODEX-UL-MGR-0D-SERVICE-CORE-001",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "server_execution_verified": True,
        "launch_performed": False, "stop_performed": False,
        "python": {"executable": sys.executable, "version": sys.version.split()[0]},
        "project": str(PROJECT), "machine": machine,
        "configurations": configurations, "runtime": runtime_inventory(cfg),
        "models": model_inventory(), "colibri1": probe_api(8000), "colibri2": probe_api(8001),
        "notes": [
            "Working set/private bytes are a snapshot, not a measured RAM peak",
            "No old RAM admission policy applied; first-run policy will be explicit",
            "CPU runtime launch, start/rollback command and LAN stage await review of this output",
        ],
    }
