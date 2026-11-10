"""UL-MGR-0C offline tests; synthetic telemetry, no live server or LLM actions."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from dataclasses import replace
import io
import json
from pathlib import Path
import subprocess
from unittest import TestCase, main
from unittest.mock import patch

from launch_contract import ContractDenied, InstanceDefinition
from manager_core import Identity, Principal, SERVER, planned_paths, Slot
from resource_catalog import HostPolicy, ModelChoice, RamRange, RangeEvidence, ResourcePlanner, initial_catalogue
from server_runner import (
    DryRunLease, DryRunRunner, LocalWindowsReader, OwnedProcess, ProcessObservation,
    RunnerDenied, ServerObservation, local_path, main as cli, stop_dry_run,
)


ALICE, BOB = Principal("alice"), Principal("bob")
SECOND = InstanceDefinition("slot2", "Colibri2", SERVER, 8001)


def observation(**changes):
    base = ServerObservation(SERVER, 48, 40, 100, "SYNTHETIC", (8000,), True, 8, 1, (12345,))
    return replace(base, **changes)


def runner(**changes):
    return DryRunRunner(allow_synthetic=True, clock=lambda: 100, **changes)


def plan(r=None, **changes):
    args = dict(model_key="kat", principal=ALICE, observation=observation())
    args.update(changes)
    return (r or runner()).dry_run("slot2", **args)


def owned():
    home = planned_paths(Slot("slot2", "Colibri2", 8001))["setup_home"]
    return OwnedProcess(
        Identity(333, 1000, r"C:\Server\Ultra_LLM\Soft\cpu\qwen36.exe",
                 222, 900, "slot2", 8001, home), "alice", "S-1-5-21-100", "session-A")


def seen(record=None, **changes):
    return replace(ProcessObservation(record or owned(), SERVER, 100, True, 222, 222), **changes)


class AdmissionTests(TestCase):
    def test_cpu_plan_uses_existing_catalogue_and_paths(self):
        result = plan()
        self.assertEqual(result["state"], "DRY_RUN_ONLY")
        self.assertEqual(result["reservation_gib"], 10)
        self.assertEqual(result["estimated_range_gib"], [5, 10])
        self.assertEqual(result["range_evidence"], "owner_hypothesis")
        self.assertIsNone(result["measured_peak_gib"])
        self.assertFalse(result["live_start_allowed"])
        self.assertFalse(result["server_execution_verified"])
        self.assertEqual(result["source"], "SYNTHETIC")
        self.assertEqual(result["projected_safe_free_gib"], 10)

    def test_separate_setup_pid_stop_logs_and_tmp(self):
        a = plan()
        r = runner()
        b = r.dry_run("slot3", model_key="qwen36", principal=BOB, observation=observation())
        for key in a["paths"]:
            if key != "shared_weights_ro":
                self.assertNotEqual(a["paths"][key], b["paths"][key], key)
        self.assertTrue(a["paths"]["gateway_pid"].endswith(r"tmp\coli-serve-8001.pid"))
        self.assertTrue(a["paths"]["gateway_stop"].endswith(r"tmp\coli-serve-8001.stop"))
        self.assertTrue(a["paths"]["setup_json"].endswith(r"slot2\setup\setup.json"))
        self.assertEqual(a["paths"]["shared_weights_ro"], b["paths"]["shared_weights_ro"])

    def test_cpu_environment_and_loopback(self):
        settings = plan()["engine"]
        self.assertEqual(settings["options"]["gpu"], "none")
        self.assertEqual(settings["bind"], "127.0.0.1")
        env = settings["environment_overrides"]
        self.assertEqual((env["COLI_CUDA"], env["COLI_VULKAN"]), ("0", "0"))
        self.assertEqual(env["TMP"], env["TEMP"])
        self.assertIn(r"slot2\tmp", env["TEMP"])
        self.assertFalse(settings["setup"]["write"])
        self.assertNotIn("command", plan())

    def test_synthetic_requires_explicit_opt_in(self):
        with self.assertRaisesRegex(RunnerDenied, "Synthetic"):
            plan(DryRunRunner(clock=lambda: 100))

    def test_source_label_alone_cannot_attest_server_execution(self):
        result = plan(observation=observation(source="LOCAL_WINDOWS"))
        self.assertFalse(result["server_execution_verified"])
        self.assertFalse(result["live_start_allowed"])
        self.assertIn("NOT VERIFIED", result["engine"]["runtime_evidence"])

    def test_wrong_observed_server(self):
        with self.assertRaisesRegex(RunnerDenied, "server"):
            plan(observation=observation(host="DESKTOP-SC96D3U"))

    def test_malformed_observation_and_principal_fail_closed(self):
        for data in (None, {}, observation(host=None)):
            with self.assertRaises(RunnerDenied):
                plan(observation=data)
        with self.assertRaises(RunnerDenied):
            plan(principal=Principal(None))

    def test_wrong_configured_server(self):
        r = runner()
        r.registry.register(InstanceDefinition("remote", "Remote", "OTHER", 9001))
        with self.assertRaisesRegex(RunnerDenied, "server"):
            r.dry_run("remote", model_key="kat", principal=ALICE, observation=observation())

    def test_wrong_resource_policy_server(self):
        p = ResourcePlanner(HostPolicy(host="OTHER"), initial_catalogue())
        with self.assertRaises(RunnerDenied):
            runner(planner=p)

    def test_legacy_is_protected_even_from_admin(self):
        r = runner()
        for actor in (ALICE, Principal("admin", True)):
            with self.subTest(actor=actor), self.assertRaises(RunnerDenied):
                r.dry_run("slot1", model_key="kat", principal=actor, observation=observation())

    def test_port_8000_protected_without_legacy_flag(self):
        from launch_contract import InstanceRegistry
        r = runner(registry=InstanceRegistry((InstanceDefinition("new", "New", SERVER, 8000),)))
        with self.assertRaises(RunnerDenied):
            r.dry_run("new", model_key="kat", principal=ALICE, observation=observation())

    def test_cuda_or_backend_fallback_forbidden(self):
        for backend in ("cuda", "vulkan", "auto", "", None):
            with self.subTest(backend=backend), self.assertRaisesRegex(RunnerDenied, "CPU"):
                plan(backend=backend)

    def test_port_conflict_does_not_reserve(self):
        r = runner()
        with self.assertRaisesRegex(RunnerDenied, "Port conflict"):
            plan(r, observation=observation(listening_ports=(8000, 8001)))
        self.assertEqual(r.planner.reservations(), ())

    def test_unknown_incomplete_telemetry(self):
        for changes in (
            {"listening_ports": None}, {"process_inventory_complete": False},
            {"external_llm_peak_gib": None}, {"source": "SMB"},
            {"external_cuda_count": -1}, {"external_cuda_count": True},
            {"listening_ports": (True,)}, {"listening_ports": (65536,)},
        ):
            with self.subTest(changes=changes), self.assertRaises(RunnerDenied):
                plan(observation=observation(**changes))

    def test_invalid_memory_never_reserves(self):
        for field in ("total_gib", "free_gib", "external_llm_peak_gib"):
            for value in (None, -1, float("nan"), float("inf"), True, "48"):
                r = runner()
                with self.subTest(field=field, value=value), self.assertRaises(RunnerDenied):
                    plan(r, observation=observation(**{field: value}))
                self.assertEqual(r.planner.reservations(), ())

    def test_free_above_total_and_zero_total(self):
        for t in (observation(free_gib=49), observation(total_gib=0, free_gib=0)):
            with self.assertRaises(RunnerDenied):
                plan(observation=t)

    def test_stale_future_and_invalid_timestamps(self):
        for value in (94.9, 101, float("nan"), None, True):
            with self.subTest(value=value), self.assertRaises(RunnerDenied):
                plan(observation=observation(sampled_monotonic=value))

    def test_actual_ram_reserves_games_and_safe_remainder(self):
        with self.assertRaisesRegex(RunnerDenied, "actual RAM"):
            plan(observation=observation(free_gib=39.99))
        self.assertEqual(plan()["protected_non_llm_gib"], 20)
        self.assertEqual(plan()["min_free_after_gib"], 10)

    def test_actual_total_overrides_optimistic_48gib_configuration(self):
        with self.assertRaisesRegex(RunnerDenied, "envelope"):
            plan(observation=observation(total_gib=47.94))

    def test_existing_colibri_peak_is_included(self):
        with self.assertRaisesRegex(RunnerDenied, "envelope"):
            plan(observation=observation(external_llm_peak_gib=12))

    def test_cannot_lower_protected_game_or_system_reserve(self):
        for policy in (HostPolicy(protected_non_llm_gib=19), HostPolicy(min_free_after_gib=9)):
            p = ResourcePlanner(policy, initial_catalogue())
            with self.assertRaises(RunnerDenied):
                plan(runner(planner=p))

    def test_two_users_cannot_take_slot(self):
        r = runner()
        plan(r)
        with self.assertRaisesRegex(RunnerDenied, "leased"):
            plan(r, principal=BOB)
        self.assertEqual(len(r.planner.reservations()), 1)

    def test_concurrent_users_one_simulated_lease(self):
        r = runner()
        def attempt(i):
            try:
                return plan(r, principal=Principal(f"user{i}"))
            except RunnerDenied:
                return None
        with ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(attempt, range(48)))
        self.assertEqual(sum(p is not None for p in results), 1)

    def test_two_different_slots_still_share_ram_envelope(self):
        r = runner()
        plan(r)
        with self.assertRaisesRegex(RunnerDenied, "envelope"):
            r.dry_run("slot3", model_key="qwen36", principal=BOB, observation=observation())

    def test_config_adds_instance_and_model_without_new_manager(self):
        r = runner()
        r.registry.register(InstanceDefinition("slot4", "Fourth", SERVER, 8003))
        r.planner.add_choice(ModelChoice(
            "new", "New", "colibri", "new", 10,
            RamRange(None, None, RangeEvidence.UNKNOWN), "trusted config"))
        result = r.dry_run("slot4", model_key="new", principal=ALICE, observation=observation())
        self.assertEqual(result["profile"], "new")
        self.assertIsNone(result["estimated_range_gib"])
        self.assertFalse(result["live_start_allowed"])

    def test_budget_can_change_but_cannot_understate_known_peak(self):
        for changes in ({"expected_ram": RamRange(5, 12, RangeEvidence.OWNER_HYPOTHESIS)},
                        {"measured_peak_gib": 12}):
            models = initial_catalogue()
            models["kat"] = replace(models["kat"], **changes)
            with self.assertRaisesRegex(RunnerDenied, "peak"):
                plan(runner(planner=ResourcePlanner(HostPolicy(), models)))

    def test_configurable_budget_and_range(self):
        models = initial_catalogue()
        models["kat"] = replace(models["kat"], budget_gib=8,
                                expected_ram=RamRange(4, 8, RangeEvidence.OWNER_HYPOTHESIS))
        result = plan(runner(planner=ResourcePlanner(HostPolicy(), models)))
        self.assertEqual(result["reservation_gib"], 8)
        self.assertEqual(result["estimated_range_gib"], [4, 8])

    def test_adapter_mismatch_or_unimplemented_adapter(self):
        with self.assertRaises(RunnerDenied):
            plan(runner(adapters={}))
        r = runner()
        r.planner.add_choice(ModelChoice("other", "Other", "other-engine", "x", 10,
                                       RamRange(None, None, RangeEvidence.UNKNOWN), "config"))
        with self.assertRaises(RunnerDenied):
            plan(r, model_key="other")

    def test_unknown_model_and_missing_principal(self):
        for changes in ({"model_key": "missing"}, {"principal": Principal("")}, {"principal": None}):
            with self.assertRaises(RunnerDenied):
                plan(**changes)

    def test_traversal_in_instance_name(self):
        r = runner()
        r.registry.register(InstanceDefinition("../escape", "Unsafe", SERVER, 8004))
        with self.assertRaises(RunnerDenied):
            r.dry_run("../escape", model_key="kat", principal=ALICE, observation=observation())

    def test_windows_path_traversal_unc_and_alternate_stream_rejected(self):
        for value in (r"C:\x\..\other", r"\\server\share\x", r"S:\home",
                      r"C:relative", r"C:\file:stream"):
            with self.subTest(value=value), self.assertRaises(RunnerDenied):
                local_path(value)

    def test_foreign_forged_and_replayed_lease(self):
        r = runner()
        lease = DryRunLease(**plan(r)["lease"])
        for actor, claimed in ((BOB, lease), (Principal("admin", True), lease),
                               (ALICE, replace(lease, token="fake"))):
            with self.assertRaises(RunnerDenied):
                r.release_dry_run(claimed, actor)
        r.release_dry_run(lease, ALICE)
        with self.assertRaises(RunnerDenied):
            r.release_dry_run(lease, ALICE)
        self.assertEqual(r.planner.reservations(), ())

    def test_failure_after_reservation_rolls_back(self):
        r = runner()
        with patch.object(r.planner, "plan_launch", side_effect=RuntimeError("planning failed")):
            with self.assertRaises(RuntimeError):
                plan(r)
        self.assertEqual(r.planner.reservations(), ())
        self.assertEqual(plan(r)["state"], "DRY_RUN_ONLY")

    def test_no_live_actions_with_any_arguments(self):
        r = runner()
        for action in (r.live_start, r.live_stop):
            with self.assertRaisesRegex(RunnerDenied, "disabled"):
                action("slot1", force=True, admin=True)
        self.assertEqual(r.planner.reservations(), ())

    def test_interprocess_protection_is_explicitly_unimplemented(self):
        result = plan()
        self.assertIn("PLANNED ONLY", result["lock_status"])
        self.assertIn("Global\\", result["admission_mutex"])


class StopIdentityTests(TestCase):
    def check(self, **changes):
        args = dict(item=SECOND, principal=ALICE, expected=owned(), observed=seen(), now=100)
        args.update(changes)
        return stop_dry_run(**args)

    def test_matching_identity_never_authorizes_stop(self):
        self.assertFalse(self.check()["live_stop_allowed"])

    def test_foreign_pid_and_reused_pid(self):
        for changes in ({"pid": 444}, {"born_filetime": 1001},
                        {"gateway_pid": 999}, {"gateway_born_filetime": 901}):
            rec = replace(owned(), identity=replace(owned().identity, **changes))
            with self.subTest(changes=changes), self.assertRaises(RunnerDenied):
                self.check(observed=seen(rec))

    def test_foreign_instance_port_executable_or_home(self):
        for changes in (
            {"instance_id": "slot1"}, {"port": 8000},
            {"exe_path": r"C:\Other\qwen36.exe"}, {"setup_home": r"C:\Other"},
        ):
            rec = replace(owned(), identity=replace(owned().identity, **changes))
            with self.subTest(changes=changes), self.assertRaises(RunnerDenied):
                self.check(observed=seen(rec))

    def test_correct_pid_but_foreign_sid_session_or_owner(self):
        for changes in ({"windows_sid": "S-1-5-21-999"}, {"session_token": "other"},
                        {"owner": "bob"}):
            with self.assertRaises(RunnerDenied):
                self.check(observed=seen(replace(owned(), **changes)))

    def test_port_owner_and_parent_must_match_gateway(self):
        for changes in ({"port_owner_pid": 12345}, {"parent_pid": 12345}):
            with self.assertRaises(RunnerDenied):
                self.check(observed=seen(**changes))

    def test_missing_stale_wrong_host_or_unverified_observation(self):
        for data in (None, seen(verified=False), seen(host="HOME"),
                     seen(sampled_monotonic=94), seen(sampled_monotonic=101)):
            with self.assertRaises(RunnerDenied):
                self.check(observed=data)

    def test_foreign_user_including_admin_cannot_stop(self):
        for actor in (BOB, Principal("admin", True), None):
            with self.assertRaises(RunnerDenied):
                self.check(principal=actor)

    def test_existing_colibri_cannot_be_stopped(self):
        with self.assertRaises(RunnerDenied):
            self.check(item=InstanceDefinition("slot1", "Colibri", SERVER, 8000, is_legacy=True))

    def test_forged_matching_home_outside_instance_refused(self):
        rec = replace(owned(), identity=replace(owned().identity, setup_home=r"C:\Other"))
        with self.assertRaises(RunnerDenied):
            self.check(expected=rec, observed=seen(rec))

    def test_matching_empty_sid_or_session_refused(self):
        for changes in ({"windows_sid": ""}, {"session_token": ""}):
            rec = replace(owned(), **changes)
            with self.assertRaises(RunnerDenied):
                self.check(expected=rec, observed=seen(rec))

    def test_invalid_pid_and_creation_time_never_match(self):
        for field in ("pid", "born_filetime", "gateway_pid", "gateway_born_filetime"):
            for value in (0, -1, True, 1.5):
                rec = replace(owned(), identity=replace(owned().identity, **{field: value}))
                with self.subTest(field=field, value=value), self.assertRaises(RunnerDenied):
                    self.check(expected=rec, observed=seen(rec))


class SafeEntryTests(TestCase):
    def read_mocked_server(self, result=None, error=None):
        with patch("server_runner.socket.gethostname", return_value=SERVER), \
             patch("server_runner.Path.is_dir", return_value=True), \
             patch("server_runner.subprocess.run", return_value=result, side_effect=error) as call:
            data = LocalWindowsReader().read()
            args, kwargs = call.call_args
            self.assertEqual(args[0][-2], "-Command")
            self.assertNotIn("shell", kwargs)
            self.assertTrue(kwargs["check"])
            return data

    def os_result(self, **changes):
        row = dict(host=SERVER, total_gib=47.94, free_gib=40, ports=[8000],
                   llm_count=1, legacy_pids=[12345], complete=True)
        row.update(changes)
        return subprocess.CompletedProcess([], 0, json.dumps(row), "")

    def test_local_reader_does_not_invent_legacy_peak_from_working_set(self):
        data = self.read_mocked_server(self.os_result())
        self.assertEqual(data.total_gib, 47.94)
        self.assertEqual(data.legacy_process_ids, (12345,))
        self.assertIsNone(data.external_llm_peak_gib)
        self.assertEqual(data.source, "LOCAL_WINDOWS")

    def test_no_external_process_only_when_inventory_reports_none(self):
        data = self.read_mocked_server(self.os_result(ports=[], llm_count=0, legacy_pids=[]))
        self.assertEqual(data.external_llm_peak_gib, 0)
        self.assertEqual(data.listening_ports, ())

    def test_unknown_os_response_or_denied_query_does_not_fallback(self):
        for result in (subprocess.CompletedProcess([], 0, "not JSON", ""),
                       self.os_result(host="HOME"),
                       subprocess.CompletedProcess([], 0, "{}", ""),
                       self.os_result(llm_count=None), self.os_result(ports=None),
                       self.os_result(complete="unknown"), self.os_result(legacy_pids=[None])):
            with self.assertRaises(RunnerDenied):
                self.read_mocked_server(result)
        for error in (subprocess.TimeoutExpired("powershell", 15),
                      subprocess.CalledProcessError(1, "powershell"), OSError("denied")):
            with self.assertRaises(RunnerDenied):
                self.read_mocked_server(error=error)

    def test_demo_plan_and_stop_contract_never_write_or_signal(self):
        with patch("builtins.open") as opened, \
             patch("pathlib.Path.mkdir") as mkdir, \
             patch("pathlib.Path.write_text") as write, \
             patch("server_runner.subprocess.run") as process, \
             patch("os.kill") as signal:
            result = plan()
            self.assertEqual(result["state"], "DRY_RUN_ONLY")
            stop_dry_run(SECOND, ALICE, owned(), seen(), now=100)
            for operation in (opened, mkdir, write, process, signal):
                operation.assert_not_called()

    def test_wrong_real_host_refuses_before_os_queries(self):
        with patch("server_runner.socket.gethostname", return_value="DESKTOP-SC96D3U"), \
             patch("server_runner.subprocess.run") as read:
            with self.assertRaisesRegex(RunnerDenied, "execution host"):
                LocalWindowsReader().read()
            read.assert_not_called()

    def test_computername_environment_cannot_bypass_host_guard(self):
        with patch.dict("os.environ", {"COMPUTERNAME": SERVER}), \
             patch("server_runner.socket.gethostname", return_value="HOME"):
            with self.assertRaises(RunnerDenied):
                LocalWindowsReader().read()

    def test_demo_cli_is_explicitly_synthetic(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("server_runner.LocalWindowsReader.read") as read:
            self.assertEqual(cli(["--demo"]), 0)
        read.assert_not_called()
        row = json.loads(output.getvalue())
        self.assertEqual(row["source"], "SYNTHETIC")
        self.assertFalse(row["live_start_allowed"])

    def test_cli_reports_blocked_without_launch(self):
        output = io.StringIO()
        with redirect_stdout(output), patch("server_runner.LocalWindowsReader.read",
                                           side_effect=RunnerDenied("wrong host")):
            self.assertEqual(cli([]), 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "BLOCKED")

    def test_live_flags_and_shell_text_not_accepted(self):
        with redirect_stdout(io.StringIO()), patch("sys.stderr", new_callable=io.StringIO):
            for args in (["--start"], ["--stop"], ["--shell", "anything"]):
                with self.assertRaises(SystemExit) as result:
                    cli(args)
                self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    main()
