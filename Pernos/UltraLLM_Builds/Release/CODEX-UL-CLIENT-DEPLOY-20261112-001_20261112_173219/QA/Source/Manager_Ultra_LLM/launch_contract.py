"""UL-MGR-0B instance/adapter contract and offline lifecycle simulator.

No imports of subprocess, socket, HTTP client, service control, OS PID APIs.
This cannot launch or stop real Colibri. A future server-side adapter must be
separately authorized, independently reviewed and run ON THE SERVER.
"""
from __future__ import annotations
from dataclasses import dataclass, replace
from enum import Enum
import threading

from resource_catalog import HostTelemetry, ResourcePlanner, ResourceDenied


class InstanceState(str, Enum):
    OFF = "OFF"
    RESERVED = "RESERVED"
    STARTING = "STARTING"
    READY = "READY"
    BUSY = "BUSY"
    STOPPING = "STOPPING"
    ERROR = "ERROR"


class ContractDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class InstanceDefinition:
    slot_id: str
    name: str
    host: str
    port: int
    adapter: str = "colibri"
    is_legacy: bool = False

    def __post_init__(self):
        if not self.slot_id or not self.name or not self.host:
            raise ValueError("Instance identity missing")
        if not isinstance(self.port, int) or type(self.port) is bool or not 1 <= self.port <= 65535:
            raise ValueError("Invalid API port")


@dataclass(frozen=True)
class EngineEvidence:
    """MOCK process identity, not a Windows verified PID."""
    instance_id: str
    model_key: str
    fake_pid: int
    ticket: str


@dataclass(frozen=True)
class InstanceStatus:
    slot_id: str
    state: InstanceState = InstanceState.OFF
    model_key: str | None = None
    backend: str | None = None
    owner: str | None = None
    evidence: EngineEvidence | None = None
    message: str = "Mock instance not started"
    simulated: bool = True


class InstanceRegistry:
    """Versioned dynamic registration. Does NOT create Colibri processes."""
    def __init__(self, instances: tuple[InstanceDefinition, ...]):
        self._lock = threading.RLock()
        self._records: dict[str, InstanceDefinition] = {}
        self._version = 0
        for item in instances:
            self.register(item)

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def register(self, definition: InstanceDefinition) -> None:
        with self._lock:
            if definition.slot_id in self._records:
                raise ContractDenied("Duplicate instance identifier")
            if any(r.host.casefold() == definition.host.casefold() and r.port == definition.port
                   for r in self._records.values()):
                raise ContractDenied("Duplicate host:port")
            self._records[definition.slot_id] = definition
            self._version += 1

    def get(self, slot_id: str) -> InstanceDefinition:
        with self._lock:
            try:
                return self._records[slot_id]
            except (KeyError, TypeError):
                raise ContractDenied("Unknown instance") from None

    def list(self) -> tuple[InstanceDefinition, ...]:
        with self._lock:
            return tuple(self._records.values())


class FakeColibriAdapter:
    """Tracks synthetic engine tickets; no real subprocess/Colibri access."""
    def __init__(self):
        self._next_pid = 900001
        self._owned: dict[str, EngineEvidence] = {}

    def start_fake(self, *, slot_id: str, model_key: str) -> EngineEvidence:
        if slot_id in self._owned:
            raise ContractDenied("Fake engine already assigned")
        self._next_pid += 1
        ticket = f"SIM-{slot_id}-{self._next_pid}"
        evidence = EngineEvidence(slot_id, model_key, self._next_pid, ticket)
        self._owned[slot_id] = evidence
        return evidence

    def stop_fake(self, *, slot_id: str, evidence: EngineEvidence) -> None:
        if self._owned.get(slot_id) != evidence or evidence.instance_id != slot_id:
            raise ContractDenied("Engine does not belong to requested slot")
        del self._owned[slot_id]

    def owned(self, slot_id: str) -> EngineEvidence | None:
        return self._owned.get(slot_id)


def initial_instances(host: str = "DESKTOP-KT4G5SM") -> tuple[InstanceDefinition, ...]:
    return (
        InstanceDefinition("slot1", "Colibri", host, 8000, is_legacy=True),
        InstanceDefinition("slot2", "Colibri2", host, 8001),
        InstanceDefinition("slot3", "Colibri3 CUDA", host, 8002),
    )


class MockLaunchCoordinator:
    """Single-process dry-run orchestrator; NOT a secure live server service."""

    def __init__(self, registry: InstanceRegistry, planner: ResourcePlanner):
        self.registry = registry
        self.planner = planner
        self.fake = FakeColibriAdapter()
        self._lock = threading.RLock()
        self._statuses: dict[str, InstanceStatus] = {
            item.slot_id: InstanceStatus(item.slot_id) for item in registry.list()
        }
        self._events: list[dict[str,str]] = []

    def sync_registry(self) -> None:
        """New entries appear after a config refresh; existing status preserved."""
        with self._lock:
            for instance in self.registry.list():
                self._statuses.setdefault(instance.slot_id, InstanceStatus(instance.slot_id))

    def status(self, slot_id: str) -> InstanceStatus:
        with self._lock:
            self.registry.get(slot_id)
            self.sync_registry()
            return replace(self._statuses[slot_id])

    def events(self) -> tuple[dict[str, str], ...]:
        with self._lock:
            return tuple(dict(entry) for entry in self._events)

    def _event(self, action: str, slot_id: str, result: str) -> None:
        self._events.append({"action": action, "slot_id": slot_id, "result": result,
                             "mode": "SIMULATION"})

    def start_fake(self, slot_id: str, *, model_key: str, backend: str,
                   owner: str, telemetry: HostTelemetry, kv_slots: int = 1) -> InstanceStatus:
        with self._lock:
            instance = self.registry.get(slot_id)
            self.sync_registry()
            if instance.is_legacy:
                raise ContractDenied("Existing Colibri is read-only in current iteration")
            if instance.adapter != "colibri":
                raise ContractDenied("No adapter for requested runtime")
            if instance.host.casefold() != self.planner.policy.host.casefold():
                raise ContractDenied("The host is not controlled by this manager")
            if self._statuses[slot_id].state != InstanceState.OFF:
                raise ContractDenied("Instance already assigned")
            # Calculate and reserve resources BEFORE any simulated startup.
            claim = self.planner.reserve_simulated(
                slot_id=slot_id, model_key=model_key, owner=owner,
                backend=backend, telemetry=telemetry)
            try:
                plan = self.planner.plan_launch(slot_id, requested_kv_slots=kv_slots)
                if plan["state"] != "MOCK_NOT_EXECUTABLE":
                    raise ContractDenied("Unexpected launch mode")
                self._statuses[slot_id] = InstanceStatus(
                    slot_id, InstanceState.RESERVED, model_key, backend, claim.owner,
                    message="Mock reservation accepted")
                self._statuses[slot_id] = replace(
                    self._statuses[slot_id], state=InstanceState.STARTING)
                fake_pid = self.fake.start_fake(slot_id=slot_id, model_key=model_key)
                self._statuses[slot_id] = replace(
                    self._statuses[slot_id], state=InstanceState.READY,
                    evidence=fake_pid, message="Mock READY; real process NOT started")
                self._event("START", slot_id, "MOCK_READY")
                return replace(self._statuses[slot_id])
            except Exception:
                self._statuses[slot_id] = InstanceStatus(slot_id)
                self.planner.release_simulated(slot_id, claim.owner)
                self._event("START", slot_id, "MOCK_REFUSED")
                raise

    def stop_fake(self, slot_id: str, *, owner: str, admin: bool = False) -> InstanceStatus:
        with self._lock:
            instance = self.registry.get(slot_id)
            if instance.is_legacy:
                raise ContractDenied("Legacy slot cannot be stopped by mock Manager")
            current = self.status(slot_id)
            if current.state != InstanceState.READY or current.evidence is None:
                raise ContractDenied("No owned mock process to stop")
            if current.owner != owner and not admin:
                raise ContractDenied("Cannot stop another user's model")
            if self.fake.owned(slot_id) != current.evidence:
                raise ContractDenied("Mock process identity mismatch")
            self._statuses[slot_id] = replace(current, state=InstanceState.STOPPING)
            self.fake.stop_fake(slot_id=slot_id, evidence=current.evidence)
            self.planner.release_simulated(slot_id, owner, admin)
            self._statuses[slot_id] = InstanceStatus(slot_id)
            self._event("STOP", slot_id, "MOCK_STOPPED")
            return replace(self._statuses[slot_id])

    def live_start(self, *_args, **_kwargs):
        raise ContractDenied("Real START NOT IMPLEMENTED / server-side runner required")

    def live_stop(self, *_args, **_kwargs):
        raise ContractDenied("Real STOP NOT IMPLEMENTED / server-side runner required")
