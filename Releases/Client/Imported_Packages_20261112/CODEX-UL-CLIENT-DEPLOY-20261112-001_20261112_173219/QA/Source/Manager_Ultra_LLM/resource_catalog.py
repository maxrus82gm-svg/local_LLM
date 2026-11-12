"""UL-MGR-0B: pure, offline resource catalogue and deployment planning.

No machine access, HTTP calls, file writes, process launch or termination.
Configured RAM is a *planning reservation*, never a Windows OS hard limit.
Measured model RAM remains unknown until real profiling proves otherwise.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math
import threading
from typing import Mapping

HOST_SERVER = "DESKTOP-KT4G5SM"
MODEL_BUDGET_GIB = 10.0
NON_LLM_PROTECTED_GIB = 20.0
SYSTEM_HEADROOM_GIB = 10.0


class ResourceDenied(RuntimeError):
    """Human-readable reason for a fail-closed simulated refusal."""


class RangeEvidence(str, Enum):
    OWNER_HYPOTHESIS = "owner_hypothesis"
    MEASURED = "measured"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RamRange:
    """Expected working RAM range. Never confuse with full model file size."""
    min_gib: float | None
    max_gib: float | None
    evidence: RangeEvidence

    def __post_init__(self) -> None:
        if (self.min_gib is None) != (self.max_gib is None):
            raise ValueError("Both range endpoints are required together")
        if self.min_gib is None:
            if self.evidence != RangeEvidence.UNKNOWN:
                raise ValueError("Unspecified range must be marked unknown")
            return
        if not (math.isfinite(self.min_gib) and math.isfinite(self.max_gib)
                and 0 < self.min_gib <= self.max_gib):
            raise ValueError("Invalid RAM range")
        if self.evidence == RangeEvidence.UNKNOWN:
            raise ValueError("Known endpoints require an evidence label")


@dataclass(frozen=True)
class ModelChoice:
    key: str
    display_name: str
    engine_adapter: str
    profile: str
    budget_gib: float
    expected_ram: RamRange
    source: str
    measured_peak_gib: float | None = None
    live_approved: bool = False

    def __post_init__(self) -> None:
        if not self.key or not self.engine_adapter or not self.profile:
            raise ValueError("Model identification is incomplete")
        if not math.isfinite(self.budget_gib) or self.budget_gib <= 0:
            raise ValueError("RAM budget must be positive")
        if self.measured_peak_gib is not None and (
            not math.isfinite(self.measured_peak_gib) or self.measured_peak_gib <= 0):
            raise ValueError("Invalid measured peak")
        if self.live_approved and self.measured_peak_gib is None:
            raise ValueError("No model may be approved for launch without verified peak")


def initial_catalogue() -> dict[str, ModelChoice]:
    """Two candidates, NOT a whitelist that prevents adding new LLMs.

    Owner's tentative 5..10 GiB is recorded as a hypothesis, not a proof that
    linked 22 GiB weights / mmap / KV / cache will fit the requested budget.
    """
    provisional = RamRange(5.0, 10.0, RangeEvidence.OWNER_HYPOTHESIS)
    return {
        "kat": ModelChoice("kat", "KAT-Coder V2.5 Dev", "colibri", "kat",
                           MODEL_BUDGET_GIB, provisional, "owner_hypothesis"),
        "qwen36": ModelChoice("qwen36", "Qwen3.6-35B-A3B", "colibri", "qwen36",
                              MODEL_BUDGET_GIB, provisional, "owner_hypothesis"),
    }


@dataclass(frozen=True)
class HostPolicy:
    host: str = HOST_SERVER
    total_gib: float = 48.0
    protected_non_llm_gib: float = NON_LLM_PROTECTED_GIB
    min_free_after_gib: float = SYSTEM_HEADROOM_GIB
    max_cuda: int = 1

    def __post_init__(self) -> None:
        numeric = (self.total_gib, self.protected_non_llm_gib, self.min_free_after_gib)
        if not all(math.isfinite(x) and x >= 0 for x in numeric):
            raise ValueError("Invalid resource policy")
        if not self.host or self.total_gib <= 0 or self.max_cuda < 0:
            raise ValueError("Invalid host or GPU policy")
        if self.protected_non_llm_gib + self.min_free_after_gib > self.total_gib:
            raise ValueError("Reserved memory exceeds installed RAM")

    @property
    def model_envelope_gib(self) -> float:
        """Maximum model reservations irrespective of momentary free RAM."""
        return self.total_gib - self.protected_non_llm_gib - self.min_free_after_gib


@dataclass(frozen=True)
class HostTelemetry:
    host: str
    free_gib: float
    verified: bool
    fresh: bool
    external_cuda_count: int = 0

    def valid_for(self, policy: HostPolicy) -> bool:
        return (self.host.casefold() == policy.host.casefold()
                and self.verified and self.fresh
                and math.isfinite(self.free_gib) and self.free_gib >= 0
                and type(self.external_cuda_count) is int
                and self.external_cuda_count >= 0)


@dataclass(frozen=True)
class Reservation:
    slot_id: str
    model_key: str
    owner: str
    backend: str
    ram_gib: float


class ResourcePlanner:
    """Simulated, thread-safe host capacity gate; no process-control methods.

    Authoritative live controller must later check actual server telemetry,
    measured RAM peaks, OS process identity, persistence and interprocess lock.
    """

    def __init__(self, policy: HostPolicy, choices: Mapping[str, ModelChoice]):
        self.policy = policy
        self._choices = dict(choices)
        self._reservations: dict[str, Reservation] = {}
        self._lock = threading.RLock()

    def add_choice(self, model: ModelChoice) -> None:
        """Model additions are config changes, not a startup or download."""
        with self._lock:
            if model.key in self._choices:
                raise ResourceDenied("Duplicate model key")
            self._choices[model.key] = model

    def catalogue(self) -> tuple[ModelChoice, ...]:
        with self._lock:
            return tuple(self._choices.values())

    def reservations(self) -> tuple[Reservation, ...]:
        with self._lock:
            return tuple(self._reservations.values())

    def reserve_simulated(self, *, slot_id: str, model_key: str,
                          owner: str, backend: str, telemetry: HostTelemetry) -> Reservation:
        with self._lock:
            if not slot_id or not owner.strip() or backend not in ("cpu", "cuda"):
                raise ResourceDenied("Invalid reservation request")
            if slot_id in self._reservations:
                raise ResourceDenied("Instance already reserved")
            if model_key not in self._choices:
                raise ResourceDenied("Unknown model; add its configuration first")
            if not isinstance(telemetry, HostTelemetry) or not telemetry.valid_for(self.policy):
                raise ResourceDenied("Real server RAM telemetry unavailable or stale")
            choice = self._choices[model_key]
            # Owner's 10-GiB budget is a *provisional* planner input, NOT a live go.
            claim = choice.budget_gib
            committed = sum(x.ram_gib for x in self._reservations.values())
            if committed + claim > self.policy.model_envelope_gib + 1e-8:
                raise ResourceDenied("Cannot fit model inside reserved server envelope")
            if telemetry.free_gib - committed - claim < self.policy.min_free_after_gib:
                raise ResourceDenied("Projected free RAM would fall below safe headroom")
            cuda_reserved = sum(x.backend == "cuda" for x in self._reservations.values())
            if (backend == "cuda" and
                cuda_reserved + telemetry.external_cuda_count >= self.policy.max_cuda):
                raise ResourceDenied("No available CUDA instance capacity")
            item = Reservation(slot_id, model_key, owner.strip(), backend, claim)
            self._reservations[slot_id] = item
            return item

    def release_simulated(self, slot_id: str, owner: str, admin: bool = False) -> None:
        """Drops only a mock claim; never signals/kills a live PID."""
        with self._lock:
            item = self._reservations.get(slot_id)
            if item is None or (not admin and item.owner != owner):
                raise ResourceDenied("No permission to release this model reservation")
            del self._reservations[slot_id]

    def plan_launch(self, slot_id: str, *, requested_kv_slots: int = 1) -> dict:
        """Show options, but deliberately do not emit executable commands."""
        with self._lock:
            item = self._reservations.get(slot_id)
            if item is None:
                raise ResourceDenied("Model must be reserved first")
            if type(requested_kv_slots) is not int or not 1 <= requested_kv_slots <= 16:
                raise ResourceDenied("Invalid Colibri KV-slot count")
            model = self._choices[item.model_key]
            if requested_kv_slots > 1 and model.engine_adapter != "colibri":
                raise ResourceDenied("KV slots unknown for this engine adapter")
            return {
                "state": "MOCK_NOT_EXECUTABLE",
                "host": self.policy.host,
                "slot_id": slot_id,
                "engine_adapter": model.engine_adapter,
                "profile": model.profile,
                "backend": item.backend,
                "reservation_gib": item.ram_gib,
                "estimated_range_gib": (
                    None if model.expected_ram.min_gib is None else
                    [model.expected_ram.min_gib, model.expected_ram.max_gib]),
                "range_evidence": model.expected_ram.evidence.value,
                "measured_peak_gib": model.measured_peak_gib,
                "live_start_allowed": False,
                "kv_slots": requested_kv_slots,
                "notes": "Simulation only. No installed setup/runtime or live RAM verified.",
            }
