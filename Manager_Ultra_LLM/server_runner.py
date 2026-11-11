"""UL-MGR-0C: read-only server preflight and NON-EXECUTABLE runner contracts.

Run with Python -B. No setup files, PID files, locks or logs are written.
--demo uses synthetic observations; otherwise telemetry is read locally on the
expected Windows server. The original dry-run contracts never start/stop an LLM.
0D adds --inspect-server: read-only installation evidence for an owner-executed
controlled Colibri2 start. It does not reserve a slot or apply dry-run admission.
0D owner-only --colibri2 delegates the isolated CPU trial to colibri2_runner.
The former DryRunRunner/service-core contracts remain non-executable.
CONTROL-01 --managed composes the existing runner with the durable control
coordinator. START/STOP require owner-enabled configuration and acknowledgement.

Trust boundary: configuration, Principal, process records and observations must
eventually come from trusted server code, never directly from browser JSON.
The in-memory leases below protect one simulator only. Before live use a single
authoritative service, machine-wide admission mutex, durable leases and same-
handle process revalidation are required. A dry-run lease grants no live rights.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import secrets
import socket
import subprocess
import threading
import time
from typing import Protocol

from launch_contract import ContractDenied, InstanceDefinition, InstanceRegistry, initial_instances
from manager_core import Identity, Principal, SERVER, Slot, planned_paths, same_process
from resource_catalog import HostPolicy, HostTelemetry, ResourcePlanner, initial_catalogue


class RunnerDenied(ContractDenied):
    """Fail closed; never try another host, port, backend or stop target."""


def number(value, *, positive=False):
    return (type(value) in (int, float) and math.isfinite(value)
            and (value > 0 if positive else value >= 0))


def local_path(value: str) -> PureWindowsPath:
    if not isinstance(value, str) or not value:
        raise RunnerDenied("Expected an absolute server path")
    p = PureWindowsPath(value)
    if (not p.is_absolute() or p.drive.casefold() != "c:"
            or ".." in p.parts or any(":" in part for part in p.parts[1:])):
        raise RunnerDenied("Expected a local C: server path without traversal/streams")
    return p


def managed_slot(item: InstanceDefinition) -> Slot:
    if (item.is_legacy or item.slot_id.casefold() == "slot1" or item.port == 8000):
        raise RunnerDenied("Existing Colibri is protected, including from admin requests")
    if not re.fullmatch(r"[a-z][a-z0-9_-]{0,31}", item.slot_id):
        raise RunnerDenied("Unsafe instance identifier")
    if item.host.casefold() != SERVER.casefold():
        raise RunnerDenied("Wrong configured server")
    return Slot(item.slot_id, item.name, item.port)


@dataclass(frozen=True)
class ServerObservation:
    host: str
    total_gib: float
    free_gib: float
    sampled_monotonic: float
    source: str                       # LOCAL_WINDOWS or SYNTHETIC
    listening_ports: tuple[int, ...] | None
    process_inventory_complete: bool
    external_llm_peak_gib: float | None
    external_cuda_count: int = 0
    legacy_process_ids: tuple[int, ...] = ()


class TelemetryReader(Protocol):
    def read(self) -> ServerObservation: ...


# Fixed, local, read-only script. No user-provided shell text or credentials.
# Missing identity/access produces UNKNOWN, never an empty successful inventory.
READ_ONLY_POWERSHELL = r"""
$ErrorActionPreference = 'Stop'
$os = Get-CimInstance Win32_OperatingSystem
$all = @(Get-CimInstance Win32_Process)
$ports = @(Get-NetTCPConnection -State Listen -ErrorAction Stop)
$candidate = @($all | Where-Object {
    $_.Name -match '^(qwen.*|colibri|glm|deepseek.*|llama-server|ollama)\.exe$' -or
    ($_.Name -match '^python(w)?\.exe$' -and
     $_.CommandLine -match '(?i)([\\/]coli(?:\s|["''])|openai_server)')
})
$primary = @($ports | Where-Object {$_.LocalPort -eq 8000} |
    Select-Object -ExpandProperty OwningProcess -Unique)
[pscustomobject]@{
    host = [Environment]::MachineName
    total_gib = [double]$os.TotalVisibleMemorySize / 1048576
    free_gib = [double]$os.FreePhysicalMemory / 1048576
    ports = @($ports | Select-Object -ExpandProperty LocalPort -Unique)
    llm_count = $candidate.Count
    legacy_pids = @($primary)
    complete = (@($all | Where-Object {
        ($_.Name -match '^python(w)?\.exe$' -and -not $_.CommandLine) -or
        ($_.ProcessId -in $candidate.ProcessId -and -not $_.ExecutablePath)
    }).Count -eq 0)
} | ConvertTo-Json -Compress
"""


class LocalWindowsReader:
    """Never query the home PC as though its RAM belonged to the server."""

    def read(self) -> ServerObservation:
        actual = socket.gethostname()
        if os.name != "nt" or actual.casefold() != SERVER.casefold():
            raise RunnerDenied(f"Wrong execution host: {actual}; required {SERVER}")
        project = Path(r"C:\Server\Ultra_LLM")
        if not (project / "Colibri" / "manager_dev").is_dir():
            raise RunnerDenied("Server-local project path is unavailable")
        started = time.monotonic()
        try:
            system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
            executable = system_root / "System32/WindowsPowerShell/v1.0/powershell.exe"
            result = subprocess.run(
                [str(executable), "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-Command", READ_ONLY_POWERSHELL],
                capture_output=True, text=True, check=True, timeout=15,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            row = json.loads(result.stdout)
            if (not isinstance(row, dict) or not isinstance(row.get("host"), str)
                    or row["host"].casefold() != actual.casefold()):
                raise RunnerDenied("OS hostname mismatch")
            if (type(row.get("complete")) is not bool
                    or type(row.get("llm_count")) is not int or row["llm_count"] < 0
                    or not isinstance(row.get("ports"), list)
                    or not isinstance(row.get("legacy_pids"), list)
                    or any(type(n) is not int or not 1 <= n <= 65535 for n in row["ports"])
                    or any(type(n) is not int or n <= 0 for n in row["legacy_pids"])
                    or not number(row.get("total_gib"), positive=True)
                    or not number(row.get("free_gib"))
                    or row["free_gib"] > row["total_gib"]):
                raise RunnerDenied("OS telemetry schema UNKNOWN/invalid")
            # Working set is NOT a future RAM peak. Any external LLM or legacy
            # listener needs a separately verified reservation before admission.
            external = None if row["llm_count"] or row["legacy_pids"] else 0.0
            return ServerObservation(
                row["host"], row["total_gib"], row["free_gib"], started,
                "LOCAL_WINDOWS", tuple(row["ports"]), row["complete"],
                external, legacy_process_ids=tuple(row["legacy_pids"]),
            )
        except (OSError, ValueError, KeyError, TypeError, AttributeError,
                subprocess.SubprocessError) as error:
            raise RunnerDenied("Server telemetry UNKNOWN; no admission") from error


def validate_observation(t: ServerObservation, now: float, allow_synthetic: bool):
    if (not isinstance(t, ServerObservation) or not isinstance(t.host, str)
            or t.host.casefold() != SERVER.casefold()):
        raise RunnerDenied("Wrong server telemetry")
    if (t.source not in ("LOCAL_WINDOWS", "SYNTHETIC")
            or (t.source == "SYNTHETIC" and not allow_synthetic)):
        raise RunnerDenied("Synthetic/unknown telemetry cannot prove server access")
    if (not number(now) or not number(t.sampled_monotonic)
            or not 0 <= now - t.sampled_monotonic <= 5):
        raise RunnerDenied("Stale/future server telemetry")
    if (not number(t.total_gib, positive=True) or not number(t.free_gib)
            or t.free_gib > t.total_gib):
        raise RunnerDenied("RAM telemetry UNKNOWN/invalid")
    if (t.process_inventory_complete is not True or t.listening_ports is None
            or not isinstance(t.listening_ports, tuple)
            or any(type(p) is not int or not 1 <= p <= 65535 for p in t.listening_ports)
            or type(t.external_cuda_count) is not int or t.external_cuda_count < 0
            or not number(t.external_llm_peak_gib)):
        raise RunnerDenied("Process/port inventory or external LLM peak UNKNOWN")


@dataclass(frozen=True)
class DryRunLease:
    slot_id: str
    owner: str
    token: str


class EnginePlanAdapter(Protocol):
    """Future adapters return typed plans, never shell commands."""
    def describe(self, item: InstanceDefinition, model, paths: dict) -> dict: ...


class ColibriCPUPlan:
    def describe(self, item, model, paths):
        return {
            "backend": "cpu",
            "bind": "127.0.0.1",
            "port": item.port,
            "options": {"gpu": "none", "ram": model.budget_gib, "kv_slots": 1},
            "environment_overrides": {
                "COLI_CUDA": "0", "COLI_VULKAN": "0",
                "COLI_SETUP_HOME": paths["setup_home"],
                "TEMP": paths["tmp"], "TMP": paths["tmp"], "TMPDIR": paths["tmp"],
                "HEAT_FILE": paths["heat"], "COLI_USAGE": paths["usage"],
                "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            "environment_policy": "Construct an allowlisted child environment; do not inherit COLI/GPU overrides",
            "runtime_evidence": "NOT VERIFIED: installed CPU engine, launcher, model inspection, hashes",
            "setup": {"path": paths["setup_json"], "write": False},
            "weight_access": "read-only intent; no model import or weight duplication",
            "kv_policy": "one independent gateway/engine; in-memory KV must not cross instance/session",
        }


class RunnerContract(Protocol):
    """Boundary for future authenticated Ultra or other application clients."""
    def dry_run(self, slot_id: str, *, model_key: str, principal: Principal,
                observation: ServerObservation, backend: str = "cpu") -> dict: ...
    def live_start(self, *args, **kwargs): ...
    def live_stop(self, *args, **kwargs): ...


class DryRunRunner:
    def __init__(self, registry=None, planner=None, adapters=None, *,
                 allow_synthetic=False, clock=time.monotonic):
        self.registry = registry or InstanceRegistry(initial_instances())
        self.planner = planner or ResourcePlanner(HostPolicy(), initial_catalogue())
        self.adapters = dict(adapters if adapters is not None else {"colibri": ColibriCPUPlan()})
        self.allow_synthetic = allow_synthetic
        self.clock = clock
        self._lock = threading.RLock()
        self._leases: dict[str, DryRunLease] = {}
        if self.planner.policy.host.casefold() != SERVER.casefold():
            raise RunnerDenied("Wrong resource policy server")

    def dry_run(self, slot_id, *, model_key, principal, observation, backend="cpu"):
        with self._lock:
            slot = managed_slot(self.registry.get(slot_id))
            if (not isinstance(principal, Principal) or not isinstance(principal.name, str)
                    or not principal.name.strip()):
                raise RunnerDenied("Authenticated principal required")
            if backend != "cpu":
                raise RunnerDenied("This runner permits CPU only; no CUDA fallback")
            validate_observation(observation, self.clock(), self.allow_synthetic)
            if slot.port in observation.listening_ports:
                raise RunnerDenied("Port conflict; never stop the listener or select another port")
            if slot_id in self._leases:
                raise RunnerDenied("Slot already leased by a dry-run user")
            item = self.registry.get(slot_id)
            model = next((m for m in self.planner.catalogue() if m.key == model_key), None)
            adapter = self.adapters.get(item.adapter)
            if model is None or adapter is None or model.engine_adapter != item.adapter:
                raise RunnerDenied("Unknown model or missing/mismatched engine adapter")
            policy = self.planner.policy
            if policy.protected_non_llm_gib < 20 or policy.min_free_after_gib < 10:
                raise RunnerDenied("Runner requires 20 GiB game reserve and 10 GiB safe remainder")
            committed = sum(r.ram_gib for r in self.planner.reservations())
            claim = max(model.budget_gib, model.expected_ram.max_gib or 0,
                        model.measured_peak_gib or 0)
            if claim > model.budget_gib:
                raise RunnerDenied("Model budget is below its configured/observed RAM peak")
            # Conservative: protect all 20 GiB even when games are currently
            # using RAM. Existing free RAM already includes external processes;
            # their peak reservations additionally constrain the total envelope.
            envelope = (min(policy.total_gib, observation.total_gib)
                        - policy.protected_non_llm_gib - policy.min_free_after_gib)
            if committed + claim + observation.external_llm_peak_gib > envelope:
                raise RunnerDenied("Existing LLMs plus claims exceed server RAM envelope")
            remaining = (observation.free_gib - policy.protected_non_llm_gib
                         - committed - claim)
            if remaining < policy.min_free_after_gib:
                raise RunnerDenied("Insufficient actual RAM after game reserve and model claim")
            paths = planned_paths(slot)
            for key, value in paths.items():
                local_path(value)
            home = PureWindowsPath(paths["instance_home"])
            paths.update(
                setup_json=str(PureWindowsPath(paths["setup_home"]) / "setup.json"),
                gateway_pid=str(PureWindowsPath(paths["tmp"]) / f"coli-serve-{slot.port}.pid"),
                gateway_stop=str(PureWindowsPath(paths["tmp"]) / f"coli-serve-{slot.port}.stop"),
                stdout=str(home / "logs" / "gateway.stdout.log"),
                stderr=str(home / "logs" / "gateway.stderr.log"),
            )
            engine = adapter.describe(item, model, dict(paths))
            self.planner.reserve_simulated(
                slot_id=slot_id, model_key=model_key, owner=principal.name,
                backend="cpu", telemetry=HostTelemetry(
                    SERVER, observation.free_gib, True, True, observation.external_cuda_count))
            try:
                result = self.planner.plan_launch(slot_id)
                lease = DryRunLease(slot_id, principal.name.strip(), secrets.token_hex(16))
                result.update(
                    state="DRY_RUN_ONLY", source=observation.source,
                    # A source label in an injected contract is not attestation.
                    # Only main's actual local OS reader can establish execution.
                    server_execution_verified=False,
                    lease=asdict(lease), paths=paths, engine=engine,
                    protected_non_llm_gib=policy.protected_non_llm_gib,
                    min_free_after_gib=policy.min_free_after_gib,
                    external_llm_peak_gib=observation.external_llm_peak_gib,
                    projected_safe_free_gib=remaining,
                    admission_mutex=f"Global\\UltraLLM-{SERVER}-admission",
                    lock_status="PLANNED ONLY: no interprocess lock or durable lease acquired",
                    blockers=[
                        "Real START/STOP are disabled by task scope",
                        "Independent review and a new owner authorization required",
                        "Installed CPU runtime and actual model RAM peak unverified",
                        "Durable leases, OS ownership, same-handle stop and RAM watchdog not implemented",
                    ],
                )
                self._leases[slot_id] = lease
                return result
            except Exception:
                self.planner.release_simulated(slot_id, principal.name.strip())
                raise

    def release_dry_run(self, lease: DryRunLease, principal: Principal):
        with self._lock:
            if (not isinstance(lease, DryRunLease) or not isinstance(principal, Principal)
                    or not isinstance(principal.name, str)
                    or self._leases.get(lease.slot_id) != lease
                    or principal.name.strip() != lease.owner):
                raise RunnerDenied("Foreign/replayed lease; even admin cannot stop another instance")
            self.planner.release_simulated(lease.slot_id, lease.owner)
            del self._leases[lease.slot_id]

    def live_start(self, *args, **kwargs):
        raise RunnerDenied("Real START disabled in UL-MGR-0C")

    def live_stop(self, *args, **kwargs):
        raise RunnerDenied("Real STOP disabled in UL-MGR-0C")


@dataclass(frozen=True)
class OwnedProcess:
    identity: Identity
    owner: str
    windows_sid: str
    session_token: str


@dataclass(frozen=True)
class ProcessObservation:
    record: OwnedProcess
    host: str
    sampled_monotonic: float
    verified: bool
    port_owner_pid: int
    parent_pid: int


def stop_dry_run(item: InstanceDefinition, principal: Principal,
                 expected: OwnedProcess, observed: ProcessObservation | None, *, now=None):
    """Compare trusted synthetic/OS records; NEVER signal, write a stopfile or kill.

    A future live adapter must read the durable expected record under the global
    lock, obtain SID/parent/port from the OS, and recheck creation time and image
    on the SAME process handle used for any final action (avoid PID-reuse races).
    """
    slot = managed_slot(item)
    if (not isinstance(expected, OwnedProcess) or not isinstance(expected.identity, Identity)
            or not isinstance(principal, Principal) or not isinstance(principal.name, str)
            or principal.name.strip() != expected.owner
            or not expected.owner or not expected.windows_sid or not expected.session_token):
        raise RunnerDenied("Foreign process owner/session")
    if (not isinstance(observed, ProcessObservation)
            or not isinstance(observed.record, OwnedProcess)
            or not isinstance(observed.record.identity, Identity)
            or observed.verified is not True or not isinstance(observed.host, str)
            or observed.host.casefold() != SERVER.casefold()):
        raise RunnerDenied("Process observation UNKNOWN or wrong server")
    checked = time.monotonic() if now is None else now
    if (not number(checked) or not number(observed.sampled_monotonic)
            or not 0 <= checked - observed.sampled_monotonic <= 5):
        raise RunnerDenied("Stale/future process observation")
    identity = expected.identity
    if any(type(n) is not int or n <= 0 for n in (
            identity.pid, identity.born_filetime, identity.gateway_pid,
            identity.gateway_born_filetime, observed.port_owner_pid, observed.parent_pid)):
        raise RunnerDenied("Invalid PID/creation-time/parent identity")
    try:
        local_path(identity.exe_path)
        expected_home = local_path(identity.setup_home)
        required_home = PureWindowsPath(planned_paths(slot)["setup_home"])
        valid = (
            expected_home == required_home
            and same_process(identity, observed.record.identity, slot)
            and observed.record.owner == expected.owner
            and observed.record.windows_sid == expected.windows_sid
            and observed.record.session_token == expected.session_token
            and observed.port_owner_pid == identity.gateway_pid
            and observed.parent_pid == identity.gateway_pid
        )
    except (AttributeError, TypeError, ValueError):
        valid = False
    if not valid:
        raise RunnerDenied("Process identity/parent/port/SID/session mismatch; no STOP")
    return {"state": "IDENTITY_MATCH_DRY_RUN_ONLY", "live_stop_allowed": False}


def demo_observation():
    # Illustrative only: 48 total, 40 free, 8 existing LLM reservation.
    return ServerObservation(SERVER, 48, 40, time.monotonic(), "SYNTHETIC",
                             (8000,), True, 8, 1, (12345,))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--demo", action="store_true", help="explicit synthetic offline dry-run")
    mode.add_argument("--inspect-server", action="store_true",
                      help="0D read-only installation inspection; run on the server")
    mode.add_argument("--colibri2", choices=("plan", "start", "status", "stop"),
                      help="0D owner-run isolated CPU trial, server-local only")
    mode.add_argument("--managed", choices=("plan", "start", "status", "stop"),
                      help="CONTROL-01 configured owner CLI; live actions require owner GO")
    parser.add_argument("--manager-config", type=__import__('pathlib').Path)
    parser.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--instance-id")
    parser.add_argument("--ack-first-cpu-policy", "--ack-owner-go", action="store_true",
                        help="explicitly accept FIRST_CPU_14G for the first controlled start")
    parser.add_argument("--wait", type=int, default=900)
    parser.add_argument("--model", default="kat")
    parser.add_argument("--instance", default="slot2")
    args = parser.parse_args(argv)
    try:
        if args.managed:
            if args.manager_config is None:
                raise RunnerDenied("--manager-config required")
            from live_manager import load_config
            from control_runtime import ModelControl
            from colibri2_runner import configured, run
            config = load_config(args.manager_config)
            core_config = config if args.managed != "plan" else {
                **config, "control": {**config.get("control", {}), "owner_go": False}}
            core = ModelControl(core_config, dispatch=lambda fn: fn())
            if args.managed == "plan":
                slot = next((s for s in config["slots"] if s["slot_id"] == args.instance
                             and not s.get("protected")), None)
                if slot is None:
                    raise RunnerDenied("Unknown or protected slot")
                with configured(core._spec(slot, args.model, args.backend)):
                    result = run("plan")
            else:
                if args.managed != "status" and not args.ack_first_cpu_policy:
                    raise RunnerDenied("Owner-run START/STOP requires --ack-first-cpu-policy")
                principal = {"client_id": "owner-cli", "control_models": True,
                             "allowed_slots": [s["slot_id"] for s in config["slots"]]}
                if args.managed == "status":
                    result = core.catalog(principal)
                else:
                    body = {"op": args.managed, "request_id": __import__('uuid').uuid4().hex}
                    if args.managed == "start":
                        body.update(model_key=args.model, mode=args.backend)
                    else:
                        body["instance_id"] = args.instance_id
                    result = core.handle(principal, body)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        if args.colibri2:
            if args.instance != "slot2":
                raise RunnerDenied("0D controlled trial is restricted to slot2; primary is protected")
            from colibri2_runner import run
            print(json.dumps(run(args.colibri2, acknowledge=args.ack_first_cpu_policy,
                                 wait=args.wait), ensure_ascii=False, indent=2))
            return 0
        if args.inspect_server:
            from server_preflight import inspect_server
            print(json.dumps(inspect_server(), ensure_ascii=False, indent=2))
            return 0
        observation = demo_observation() if args.demo else LocalWindowsReader().read()
        runner = DryRunRunner(allow_synthetic=args.demo)
        plan = runner.dry_run(args.instance, model_key=args.model,
                              principal=Principal("local-dry-run"), observation=observation)
        plan["server_execution_verified"] = not args.demo
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    except (ContractDenied, RuntimeError, OSError, ValueError, KeyError,
            subprocess.SubprocessError) as error:
        print(json.dumps({"state": "BLOCKED", "reason": str(error),
                          "live_start_allowed": False, "live_stop_allowed": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
