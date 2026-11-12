"""UL-MGR-0D: OFFLINE ONLY manager request boundary.

This module is not a Windows service, authentication provider, HTTP handler or
production admission authority. All actions are memory-only simulation. No
network bind, shell, filesystem writes, process creation, process stop, or OS
service calls are implemented. No function here grants permission for live use.

Transport-authenticated identity and trusted host telemetry must be supplied
by future separately reviewed SERVER components; never trust client JSON.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import secrets
import threading
from typing import Protocol

from manager_core import Principal
from server_runner import DryRunLease, DryRunRunner, ServerObservation


class CoreDenied(RuntimeError):
    """Safe, non-sensitive refusal from an offline simulation."""


class CredentialVerifier(Protocol):
    """FUTURE server-side verifier; no implementation supplied by this module."""
    def resolve(self, transport_credential: str) -> Principal: ...


class ObservationSource(Protocol):
    """FUTURE server-side reader; client never supplies this observation."""
    def read(self) -> ServerObservation: ...


class InterprocessLock(Protocol):
    """UNIMPLEMENTED live prerequisite; not used for offline simulation."""
    def acquire_exclusive(self) -> object: ...


class DurableLeaseStore(Protocol):
    """UNIMPLEMENTED live prerequisite; no persistent lease is created."""
    def restore_verified(self) -> object: ...


class ProcessAuthority(Protocol):
    """UNIMPLEMENTED live prerequisite; requires same-handle OS verification."""
    def verify_owned_handle(self) -> object: ...


class ProcessWatchdog(Protocol):
    """UNIMPLEMENTED live prerequisite; must monitor trusted runtime state."""
    def check_health(self) -> object: ...


@dataclass(frozen=True)
class LivePrerequisites:
    authenticated_transport: bool = False
    server_execution: bool = False
    interprocess_lock: bool = False
    durable_leases: bool = False
    verified_process_handles: bool = False
    resource_telemetry: bool = False
    watchdog: bool = False

    @property
    def ready_for_live(self) -> bool:
        # This task is intentionally non-executable even if tests set all flags.
        return False


_ID = re.compile(r"[a-z][a-z0-9_-]{0,31}\Z", re.ASCII)
_MODEL = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z", re.ASCII)
_TOKEN = re.compile(r"[0-9a-f]{32}\Z", re.ASCII)
_OPS = {
    "slots": frozenset({"op"}),
    "models": frozenset({"op"}),
    "dry_run": frozenset({"op", "slot_id", "model_key", "backend"}),
    "release_dry_run": frozenset({"op", "slot_id", "lease_token"}),
}


def _field(value, pattern) -> str:
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise CoreDenied("Invalid request field")
    return value


class OfflineServiceCore:
    """Composition boundary: strictly allowlisted JSON-like requests.

    The credential arrives separately from client data as a future trusted
    transport field. The injected verifier is only an OFFLINE test double for
    this stage; never interpret it as real Windows authentication.
    The observation source is injected server-side; no telemetry, PID, admin,
    command, path or process ownership claim is accepted from client payloads.
    """

    production_ready = False

    def __init__(self, *, verifier: CredentialVerifier,
                 observations: ObservationSource,
                 runner: DryRunRunner | None = None):
        if verifier is None or not callable(getattr(verifier, "resolve", None)):
            raise CoreDenied("No identity authority configured")
        if observations is None or not callable(getattr(observations, "read", None)):
            raise CoreDenied("No telemetry authority configured")
        self._verifier = verifier
        self._observations = observations
        self._runner = runner if runner is not None else DryRunRunner()
        if not isinstance(self._runner, DryRunRunner):
            raise CoreDenied("Only the reviewed dry-run runner is permitted")
        self._mutex = threading.RLock()  # process-local only, not a Windows mutex
        self._issued: dict[str, tuple[str, DryRunLease]] = {}
        self.live_prerequisites = LivePrerequisites()

    def handle(self, payload: dict, *, transport_credential: str) -> dict:
        """Return a safe simulated response. Never raise raw internal errors."""
        try:
            return self._handle(payload, transport_credential)
        except Exception:
            # Do not expose internal reader/verifier errors to future clients.
            return {
                "ok": False, "state": "DENIED",
                "reason": "REQUEST_REJECTED_OR_UNVERIFIED",
                "simulated": True, "live_start_allowed": False,
            }

    def _handle(self, payload, credential):
        # Exact dict and keys only: no custom Mapping objects, unknown fields,
        # nested arguments, supplied Principal or claimed telemetry.
        if type(payload) is not dict or type(credential) is not str or not credential:
            raise CoreDenied("Invalid request or credentials")
        operation = payload.get("op")
        if type(operation) is not str or operation not in _OPS:
            raise CoreDenied("Unknown or live operation forbidden")
        if payload.keys() != _OPS[operation]:
            raise CoreDenied("Unexpected or missing client fields")
        # Identity is resolved by a separate injected authority, never from JSON.
        principal = self._verifier.resolve(credential)
        if (type(principal) is not Principal or
                type(principal.name) is not str or
                not principal.name.strip() or
                type(principal.is_admin) is not bool):
            raise CoreDenied("Identity not verified")
        with self._mutex:
            if operation == "slots":
                return {
                    "ok": True, "simulated": True,
                    "slots": [
                        {"id": item.slot_id, "name": item.name, "port": item.port,
                         "legacy_protected": item.is_legacy}
                        for item in self._runner.registry.list()
                    ],
                    "live_start_allowed": False,
                }
            if operation == "models":
                return {
                    "ok": True, "simulated": True,
                    "models": [
                        {"key": model.key, "name": model.display_name,
                         "adapter": model.engine_adapter, "live_approved": False}
                        for model in self._runner.planner.catalogue()
                    ],
                    "live_start_allowed": False,
                }
            slot_id = _field(payload["slot_id"], _ID)
            if operation == "dry_run":
                model_key = _field(payload["model_key"], _MODEL)
                backend = payload["backend"]
                if type(backend) is not str or backend != "cpu":
                    raise CoreDenied("Only CPU offline plans supported")
                # This is read at the service boundary, never passed by client.
                observation = self._observations.read()
                if not isinstance(observation, ServerObservation):
                    raise CoreDenied("Missing trusted host observation")
                plan = self._runner.dry_run(
                    slot_id, model_key=model_key,
                    principal=principal, observation=observation, backend="cpu",
                )
                lease_row = plan.get("lease")
                if (type(lease_row) is not dict
                        or lease_row.get("slot_id") != slot_id
                        or lease_row.get("owner") != principal.name.strip()):
                    raise CoreDenied("No verified in-memory mock lease")
                token = lease_row.get("token")
                _field(token, _TOKEN)
                lease = DryRunLease(slot_id, principal.name.strip(), token)
                # All plans remain in memory. Do not return setup paths or
                # detailed internal process plans to untrusted clients.
                self._issued[slot_id] = (principal.name.strip(), lease)
                return {
                    "ok": True, "state": "DRY_RUN_ONLY",
                    "simulated": True, "slot_id": slot_id,
                    "model_key": model_key, "backend": "cpu",
                    "lease_token": token, "live_start_allowed": False,
                    "server_execution_verified": False,
                }
            if operation == "release_dry_run":
                token = _field(payload["lease_token"], _TOKEN)
                issued = self._issued.get(slot_id)
                if (issued is None or issued[0] != principal.name.strip()
                        or not secrets.compare_digest(issued[1].token, token)):
                    raise CoreDenied("Foreign or replayed dry-run lease")
                self._runner.release_dry_run(issued[1], principal)
                del self._issued[slot_id]
                return {
                    "ok": True, "state": "DRY_RUN_RELEASED",
                    "slot_id": slot_id, "simulated": True,
                    "live_stop_allowed": False,
                }
            raise CoreDenied("Not an allowed offline operation")

    def live_start(self, *args, **kwargs):
        raise CoreDenied("UL-MGR-0D cannot start processes")

    def live_stop(self, *args, **kwargs):
        raise CoreDenied("UL-MGR-0D cannot stop processes")

    def install_service(self, *args, **kwargs):
        raise CoreDenied("UL-MGR-0D cannot install services")

    def open_network_listener(self, *args, **kwargs):
        raise CoreDenied("UL-MGR-0D has no network listener")
