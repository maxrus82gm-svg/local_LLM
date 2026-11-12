"""UL-MGR-0D independent offline-oriented unit cases, synthetic host data only.

No test establishes Windows authentication, server execution or real START/STOP.
"""
from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from manager_core import Principal, SERVER
from server_runner import DryRunRunner, ServerObservation
from service_core import CoreDenied, LivePrerequisites, OfflineServiceCore


class TestCredentials:
    def __init__(self, users=None):
        self._users = users if users is not None else {
            "token-alice": Principal("alice"),
            "token-bob": Principal("bob"),
            "token-admin": Principal("root", True),
        }
        self.calls = 0

    def resolve(self, token):
        self.calls += 1
        return self._users.get(token)


class TestObservations:
    def __init__(self, observation=None):
        self.value = observation if observation is not None else ServerObservation(
            SERVER, 48, 40, 100, "SYNTHETIC",
            (8000,), True, 8, 1, (12345,),
        )
        self.calls = 0

    def read(self):
        self.calls += 1
        return self.value


def make_core(*, obs=None, users=None, reader=None, auth=None):
    verifier = auth if auth is not None else TestCredentials(users)
    observations = reader if reader is not None else TestObservations(obs)
    runner = DryRunRunner(allow_synthetic=True, clock=lambda: 100)
    return OfflineServiceCore(
        verifier=verifier, observations=observations, runner=runner,
    )


def call(core, op, cred="token-alice", **fields):
    return core.handle({"op": op, **fields}, transport_credential=cred)


def reserve(core, cred="token-alice", slot="slot2", model="kat"):
    return call(core, "dry_run", cred, slot_id=slot, model_key=model, backend="cpu")


class OfflineDispatchTests(TestCase):
    def setUp(self):
        self.core = make_core()

    def test_slot_inventory_safe_and_simulated(self):
        result = call(self.core, "slots")
        self.assertTrue(result["ok"])
        self.assertFalse(result["live_start_allowed"])
        self.assertTrue(result["simulated"])
        self.assertEqual([x["id"] for x in result["slots"]],
                         ["slot1", "slot2", "slot3"])
        self.assertTrue(result["slots"][0]["legacy_protected"])

    def test_model_catalogue_safe(self):
        result = call(self.core, "models")
        self.assertEqual([x["key"] for x in result["models"]],
                         ["kat", "qwen36"])
        self.assertTrue(all(not row["live_approved"]
                            for row in result["models"]))
        self.assertNotIn("setup", json.dumps(result))

    def test_dry_run_uses_existing_0c_runner(self):
        result = reserve(self.core)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["state"], "DRY_RUN_ONLY")
        self.assertEqual(result["backend"], "cpu")
        self.assertFalse(result["server_execution_verified"])
        self.assertFalse(result["live_start_allowed"])
        self.assertRegex(result["lease_token"], "^[0-9a-f]{32}$")

    def test_two_distinct_cpu_slots_simulated_on_larger_synthetic_host(self):
        from resource_catalog import HostPolicy, ResourcePlanner, initial_catalogue
        obs = replace(TestObservations().value, total_gib=64, free_gib=50)
        service = make_core(obs=obs)
        service._runner.planner = ResourcePlanner(HostPolicy(total_gib=64), initial_catalogue())
        a = reserve(service)
        b = reserve(service, slot="slot3", model="qwen36")
        self.assertTrue(a["ok"] and b["ok"], (a, b))
        self.assertNotEqual(a["lease_token"], b["lease_token"])

    def test_second_cpu_denied_under_conservative_48gib_policy(self):
        self.assertTrue(reserve(self.core)["ok"])
        self.assertFalse(reserve(self.core, slot="slot3", model="qwen36")["ok"])

    def test_original_slot1_protected_even_admin(self):
        for cred in ("token-alice", "token-admin"):
            result = reserve(self.core, cred, "slot1")
            self.assertFalse(result["ok"])

    def test_release_simulated_and_reuse(self):
        res = reserve(self.core)
        done = call(self.core, "release_dry_run",
                    slot_id="slot2", lease_token=res["lease_token"])
        self.assertTrue(done["ok"])
        self.assertFalse(done["live_stop_allowed"])
        self.assertTrue(reserve(self.core)["ok"])

    def test_release_replay_rejected(self):
        res = reserve(self.core)
        args = {"slot_id": "slot2", "lease_token": res["lease_token"]}
        self.assertTrue(call(self.core, "release_dry_run", **args)["ok"])
        self.assertFalse(call(self.core, "release_dry_run", **args)["ok"])

    def test_foreign_release_even_admin_rejected(self):
        res = reserve(self.core)
        for cred in ("token-bob", "token-admin"):
            self.assertFalse(call(self.core, "release_dry_run", cred,
                                  slot_id="slot2",
                                  lease_token=res["lease_token"])["ok"])
        self.assertTrue(call(self.core, "release_dry_run",
                             slot_id="slot2",
                             lease_token=res["lease_token"])["ok"])

    def test_concurrent_same_slot_has_one_winner(self):
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: reserve(self.core), range(32)))
        self.assertEqual(sum(x["ok"] for x in results), 1)

    def test_unknown_model_or_invalid_backend_denied(self):
        self.assertFalse(reserve(self.core, model="unknown")["ok"])
        self.assertFalse(call(self.core, "dry_run", slot_id="slot2",
                              model_key="kat", backend="cuda")["ok"])

    def test_weak_or_oversized_identifier_denied(self):
        for name in ("", "slot2/../../other", " SLOT2 ", "slot2:secret",
                     "slot2\n", "a" * 60):
            self.assertFalse(call(self.core, "dry_run",
                                  slot_id=name, model_key="kat",
                                  backend="cpu")["ok"])

    def test_live_operations_refused_even_with_admin(self):
        for op in ("start", "stop", "restart", "live_start",
                   "live_stop", "install_service", "bind", "shell",
                   "shutdown", "approve", "allocate_gpu"):
            self.assertFalse(call(self.core, op, "token-admin")["ok"])

    def test_explicit_non_executable_methods(self):
        for operation in (self.core.live_start, self.core.live_stop,
                          self.core.install_service, self.core.open_network_listener):
            with self.assertRaises(CoreDenied):
                operation()

    def test_client_cannot_override_principal_admin_or_telemetry(self):
        arguments = {"slot_id": "slot2", "model_key": "kat", "backend": "cpu"}
        for extra in ({"principal": {"name": "root", "is_admin": True}},
                      {"is_admin": True}, {"telemetry": {"free_gib": 1e8}},
                      {"pid": 12345}, {"cmd": "powershell -Command whoami"},
                      {"path": "C:\\Windows\\System32\\cmd.exe"},
                      {"host": SERVER}, {"owner": "bob"},
                      {"port": 8000}, {"shell": "cmd /c exit"}):
            self.assertFalse(call(self.core, "dry_run",
                                  **{**arguments, **extra})["ok"])

    def test_unknown_schema_fields_denied_in_read_only_ops(self):
        for operation in ("slots", "models"):
            self.assertFalse(call(self.core, operation, is_admin=True)["ok"])

    def test_nested_or_non_dict_payload_denied(self):
        for bad in (None, "slots", [], (), {"op": ["slots"]},
                    {"op": 123}, {"op": "slots", "x": None}):
            response = self.core.handle(bad, transport_credential="token-alice")
            self.assertEqual(response["state"], "DENIED")

    def test_bool_or_integer_credential_denied(self):
        for credential in (None, False, 3, "", {}, []):
            self.assertFalse(self.core.handle(
                {"op": "slots"}, transport_credential=credential)["ok"])

    def test_unknown_credential_denied(self):
        self.assertFalse(call(self.core, "slots", cred="wrong")["ok"])

    def test_auth_called_before_resource_read(self):
        source = TestObservations()
        core = make_core(reader=source)
        self.assertFalse(reserve(core, cred="invalid")["ok"])
        self.assertEqual(source.calls, 0)

    def test_auth_trust_cannot_come_from_request(self):
        source = TestObservations()
        core = make_core(reader=source)
        response = core.handle(
            {"op": "dry_run", "slot_id": "slot2", "model_key": "kat",
             "backend": "cpu", "transport_credential": "token-alice"},
            transport_credential="invalid",
        )
        self.assertFalse(response["ok"])
        self.assertEqual(source.calls, 0)

    def test_no_production_auth_material_or_credentials_leaked(self):
        result = reserve(self.core)
        wire = json.dumps(result)
        self.assertNotIn("token-alice", wire)
        self.assertNotIn("server\\", wire.lower())
        self.assertNotIn("setup_home", wire)
        self.assertNotIn("pid", wire.lower())

    def test_missing_dependency_rejected(self):
        with self.assertRaises(CoreDenied):
            OfflineServiceCore(verifier=None, observations=TestObservations())
        with self.assertRaises(CoreDenied):
            OfflineServiceCore(verifier=TestCredentials(), observations=None)

    def test_malicious_or_missing_identity_rejected(self):
        for user in (Principal("", False), Principal("alice", "true"),
                     object(), None):
            result = call(make_core(users={"fake": user}), "slots", cred="fake")
            self.assertFalse(result["ok"])

    def test_unexpected_reader_data_fail_closed(self):
        for bad in (None, "fake", {"host": SERVER}, object()):
            reader = TestObservations()
            reader.value = bad
            self.assertFalse(reserve(make_core(reader=reader))["ok"])

    def test_stale_or_wrong_hostname_denied(self):
        basis = TestObservations().value
        for bad in (replace(basis, host="DESKTOP-SC96D3U"),
                    replace(basis, sampled_monotonic=1),
                    replace(basis, process_inventory_complete=False),
                    replace(basis, external_llm_peak_gib=None),
                    replace(basis, free_gib=2),
                    replace(basis, source="UNKNOWN")):
            self.assertFalse(reserve(make_core(obs=bad))["ok"])

    def test_port_conflict_does_not_pick_another_port(self):
        observation = replace(TestObservations().value,
                              listening_ports=(8000, 8001))
        self.assertFalse(reserve(make_core(obs=observation))["ok"])

    def test_mock_lease_never_authorizes_live_actions(self):
        response = reserve(self.core)
        self.assertTrue(response["ok"])
        self.assertFalse(call(self.core, "live_start", "token-alice",
                              slot_id="slot2", lease_token=response["lease_token"])["ok"])

    def test_live_prerequisite_flags_never_enable_live(self):
        fields = {field: True for field in LivePrerequisites.__dataclass_fields__}
        self.assertFalse(LivePrerequisites(**fields).ready_for_live)

    def test_no_executable_network_or_service_primitives(self):
        text = Path(__file__).with_name("service_core.py").read_text(encoding="utf-8")
        tree = ast.parse(text)
        forbidden = {"socket", "subprocess", "http", "http.server",
                     "win32service", "winreg", "ctypes"}
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                names.add(node.module)
        self.assertTrue(forbidden.isdisjoint(names), names & forbidden)
        self.assertNotIn("Popen(", text)
        self.assertNotIn("os.system(", text)

    def test_import_has_no_network_process_or_disk_side_effects(self):
        import sys
        import types
        file_path = Path(__file__).with_name("service_core.py")
        module = types.ModuleType("_service_core_import_probe")
        module.__file__ = str(file_path)
        sys.modules[module.__name__] = module
        try:
            with patch("socket.socket", side_effect=AssertionError("network prohibited")), \
                 patch("subprocess.Popen", side_effect=AssertionError("process prohibited")), \
                 patch("pathlib.Path.mkdir", side_effect=AssertionError("disk prohibited")):
                exec(compile(file_path.read_text(encoding="utf-8"),
                             str(file_path), "exec"), module.__dict__)
            self.assertFalse(module.OfflineServiceCore.production_ready)
        finally:
            sys.modules.pop(module.__name__, None)
