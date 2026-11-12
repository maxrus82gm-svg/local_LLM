"""UL-MGR-0A: pure, simulation-only slot registry. No server lifecycle APIs.

IMPORTANT: NOT a production server, process controller, authentication layer, or
resource monitor. Never use a simulated claim to authorize a real model launch.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
import math
from pathlib import PureWindowsPath
import secrets
import threading


SERVER = "DESKTOP-KT4G5SM"
SHARED_MODELS = PureWindowsPath(r"C:\Server\Ultra_LLM\Base_LLM\Models")
INSTANCE_ROOT = PureWindowsPath(r"C:\Server\Ultra_LLM\Base_LLM\Data\ManagerInstances")
MIN_HEADROOM_GIB = 10.0


class State(str, Enum):
    OFF = "OFF"
    RESERVED = "RESERVED"
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class Denied(RuntimeError):
    """A safe refusal, not permission to fall back to unsafe operation."""


@dataclass(frozen=True)
class Principal:
    """Provided by a future trusted authentication layer, NOT from browser JSON."""
    name: str
    is_admin: bool = False


@dataclass(frozen=True)
class Slot:
    slot_id: str
    name: str
    port: int
    legacy: bool = False


@dataclass(frozen=True)
class Estimate:
    """An approved worst-case incremental RAM estimate, NOT CLI --ram."""
    peak_gib: float
    validated: bool = False


@dataclass(frozen=True)
class Snapshot:
    """Server-origin telemetry to be verified by a FUTURE real manager."""
    available_gib: float
    external_cuda_count: int
    verified: bool
    fresh: bool
    host: str = SERVER


@dataclass(frozen=True)
class Identity:
    """Fields to compare after independently reading OS metadata and port owner."""
    pid: int
    born_filetime: int
    exe_path: str
    gateway_pid: int
    gateway_born_filetime: int
    instance_id: str
    port: int
    setup_home: str


@dataclass(frozen=True)
class View:
    slot_id: str
    state: State = State.OFF
    owner: str | None = None
    profile: str | None = None
    backend: str | None = None
    lease: str | None = None


SLOTS = (
    Slot("slot1", "Colibri", 8000, legacy=True),
    Slot("slot2", "Colibri2", 8001),
    Slot("slot3", "Colibri3 CUDA", 8002),
)
ALLOWED_PROFILES = frozenset({"kat", "qwen36"})
ALLOWED_BACKENDS = frozenset({"cpu", "cuda"})


def _winpath(value: str) -> str:
    if not value or not PureWindowsPath(value).is_absolute():
        raise ValueError("Expected an absolute Windows path")
    return str(PureWindowsPath(value)).casefold()


def same_process(expected: Identity, observed: Identity | None, slot: Slot) -> bool:
    """Fail closed on any mismatch; executable name alone is never ownership."""
    if observed is None or expected.instance_id != slot.slot_id:
        return False
    try:
        return (
            expected.pid > 0
            and expected.born_filetime > 0
            and expected.gateway_pid > 0
            and expected.gateway_born_filetime > 0
            and observed.pid == expected.pid
            and observed.born_filetime == expected.born_filetime
            and observed.gateway_pid == expected.gateway_pid
            and observed.gateway_born_filetime == expected.gateway_born_filetime
            and observed.instance_id == expected.instance_id
            and expected.port == observed.port == slot.port
            and _winpath(expected.exe_path) == _winpath(observed.exe_path)
            and _winpath(expected.setup_home) == _winpath(observed.setup_home)
        )
    except (ValueError, TypeError):
        return False


def planned_paths(slot: Slot) -> dict[str, str]:
    """Plan only; creates no directories and never rewrites the legacy slot1."""
    if slot.legacy:
        raise Denied("Legacy slot1 uses existing home; no migration is permitted in UL-MGR-0A")
    home = INSTANCE_ROOT / slot.slot_id
    return {
        "instance_home": str(home),
        "setup_home": str(home / "setup"),
        "state": str(home / "state" / "state.json"),
        "lock": str(home / "state" / "controller.lock"),
        "request": str(home / "state" / "request.json"),
        "stop": str(home / "state" / "stop.json"),
        "pid": str(home / "state" / "pid.json"),
        "logs": str(home / "logs"),
        "reports": str(home / "reports"),
        "tmp": str(home / "tmp"),
        "heat": str(home / "cache" / "heat.bin"),
        "usage": str(home / "cache" / "usage.bin"),
        "kv_cache": str(home / "cache" / "kv"),
        "shared_weights_ro": str(SHARED_MODELS),
    }


class MockRegistry:
    """In-memory simulator. All methods are thread-safe; NO real START/STOP."""

    def __init__(self, estimates: dict[tuple[str, str], Estimate] | None = None):
        self._lock = threading.RLock()
        self._slots = {slot.slot_id: slot for slot in SLOTS}
        self._views = {slot.slot_id: View(slot.slot_id) for slot in SLOTS}
        # trusted config must be populated server-side after independent profiling
        self._estimates = dict(estimates or {})
        self._claimed_peak: dict[str, float] = {}

    def view(self, slot_id: str) -> View:
        with self._lock:
            self._require_slot(slot_id)
            return replace(self._views[slot_id])

    def all_views(self) -> tuple[View, ...]:
        with self._lock:
            return tuple(replace(self._views[s.slot_id]) for s in SLOTS)

    def _require_slot(self, slot_id: str) -> Slot:
        try:
            return self._slots[slot_id]
        except (KeyError, TypeError):
            raise Denied("Unknown slot; no action") from None

    @staticmethod
    def _principal(principal: Principal) -> None:
        if not isinstance(principal, Principal) or not isinstance(principal.name, str) or not principal.name.strip():
            raise Denied("No authenticated principal")

    @staticmethod
    def _telemetry(snapshot: Snapshot) -> None:
        if (
            not isinstance(snapshot, Snapshot)
            or not snapshot.verified
            or not snapshot.fresh
            or snapshot.host.casefold() != SERVER.casefold()
            or not math.isfinite(snapshot.available_gib)
            or snapshot.available_gib < 0
            or type(snapshot.external_cuda_count) is not int
            or snapshot.external_cuda_count < 0
        ):
            raise Denied("Server telemetry unknown/stale/invalid: deny all reservations")

    def reserve(self, slot_id: str, principal: Principal, profile: str,
                backend: str, snapshot: Snapshot) -> str:
        """Atomic *mock* claim + aggregate RAM/CUDA admission (no OS calls)."""
        with self._lock:
            slot = self._require_slot(slot_id)
            self._principal(principal)
            if slot.legacy:
                raise Denied("Legacy slot1 is read-only until separately authorized")
            current = self._views[slot_id]
            if current.state is not State.OFF:
                raise Denied("Slot already reserved, active, or unavailable")
            if profile not in ALLOWED_PROFILES or backend not in ALLOWED_BACKENDS:
                raise Denied("Unknown model/backend")
            self._telemetry(snapshot)
            key = (profile, backend)
            estimate = self._estimates.get(key)
            if not isinstance(estimate, Estimate) or not estimate.validated:
                raise Denied("No approved RAM peak estimate; deny")
            peak = estimate.peak_gib
            if not math.isfinite(peak) or peak <= 0:
                raise Denied("Invalid RAM peak estimate")
            if snapshot.available_gib < MIN_HEADROOM_GIB:
                raise Denied("RAM below 10 GiB safety floor")
            committed = sum(self._claimed_peak.values())
            if snapshot.available_gib - committed - peak < MIN_HEADROOM_GIB:
                raise Denied("Predicted remaining RAM below 10 GiB")
            cuda_claims = sum(
                1 for v in self._views.values()
                if v.backend == "cuda" and v.state is not State.OFF
            )
            if backend == "cuda" and snapshot.external_cuda_count + cuda_claims >= 1:
                raise Denied("Initial policy allows at most one CUDA instance")
            lease = secrets.token_hex(16)
            self._views[slot_id] = View(slot_id, State.RESERVED, principal.name.strip(),
                                        profile, backend, lease)
            self._claimed_peak[slot_id] = peak
            return lease

    def cancel_reservation(self, slot_id: str, principal: Principal, lease: str) -> None:
        """Only drops a mock RESERVED claim; NEVER stops a process."""
        with self._lock:
            self._require_slot(slot_id)
            self._principal(principal)
            current = self._views[slot_id]
            if current.state is not State.RESERVED or not lease or current.lease != lease:
                raise Denied("No matching active reservation")
            if current.owner != principal.name.strip() and not principal.is_admin:
                raise Denied("Cannot change another user's slot")
            self._views[slot_id] = View(slot_id)
            self._claimed_peak.pop(slot_id, None)

    def deny_live_action(self, *_args, **_kwargs) -> None:
        raise Denied("UL-MGR-0A is simulation only; real START/STOP/RESTART NOT IMPLEMENTED")
