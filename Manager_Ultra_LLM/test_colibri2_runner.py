"""0D launch safety tests; no Colibri launch, no server command execution.

Native integration uses only short-lived dummy Python processes on the HOME PC,
with temporary log files confined to manager_dev. Production host guards remain
mandatory. All Colibri lifecycle and API tests use injected observations.
"""
from contextlib import nullcontext
import ctypes
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import MagicMock, patch
import uuid

import colibri2_runner as runner
from server_runner import main as cli
from windows_process import BasicLimit, ExtendedLimit, NativeWindows, WindowsError

HERE = Path(__file__).parent
REC = {"pid": 333, "created_filetime": 100, "exe": r"C:\Python\python.exe", "owner_sid": "S-1-5-21-1"}


def plan():
    return {"paths": runner.paths(), "launcher": r"C:\Server\Ultra_LLM\Colibri\c\coli",
            "model": r"C:\Server\Ultra_LLM\Base_LLM\Models\Qwen3.6\model.colibri",
            "source_hashes": {}, "primary": REC, "primary_engine": {**REC, "pid": 444}}


def state():
    session = "a" * 32
    return {"instance": "slot2", "port": 8001, "session": session, "state": "READY",
            "supervisor": REC, "stop_event": rf"Global\UltraLLM-Colibri2-stop-{session}"}


def fake_native():
    native = MagicMock()
    native.process.side_effect = lambda pid: nullcontext(pid)
    native.identity.return_value = REC
    native.same.side_effect = NativeWindows.same
    native.mutex.side_effect = lambda name: nullcontext()
    native.event.return_value = 111
    native.job.return_value = 222
    native.memory.return_value = {"total_gib": 47.9358, "free_gib": 35.2843}
    native.listeners.return_value = [{"port": 8000, "pid": 333}]
    native.job_pids.return_value = []
    return native


class PlanTests(unittest.TestCase):
    def test_cli_flags_are_present_in_actual_server_colibri_210_source(self):
        source = HERE.parent / "c" / "coli"
        runner.verified_cli(source)  # AST inspection only, no import/execution

    def test_cli_drift_refuses_instead_of_guessing(self):
        launcher = MagicMock()
        launcher.read_text.return_value = "def cmd_serve(): pass\n"
        with self.assertRaises(runner.StartDenied):
            runner.verified_cli(launcher)

    def test_version_drift_refused(self):
        source = (HERE.parent / "c" / "coli").read_text(encoding="utf-8-sig")
        launcher = MagicMock()
        launcher.read_text.return_value = source
        launcher.with_name.return_value.read_text.return_value = "__version__ = '9.9.9'"
        with self.assertRaisesRegex(runner.StartDenied, "2.1.0"):
            runner.verified_cli(launcher)

    def test_runtime_paths_stay_inside_development_directory(self):
        values = runner.paths()
        for key, value in values.items():
            if key != "shared_weights_ro":
                self.assertTrue(Path(value).is_relative_to(runner.HOME), key)
        self.assertEqual(Path(values["gateway_stop"]).name, "coli-serve-8001.stop")
        self.assertNotIn("8000", values["gateway_pid"])

    def test_path_escape_and_junction_destination_refused(self):
        with self.assertRaises(runner.StartDenied):
            runner.safe_write_path(r"C:\Server\Ultra_LLM\Colibri\ULTRA-CONTROL.py")
        with self.assertRaises(runner.StartDenied):
            runner.safe_write_path(runner.HOME / ".." / ".." / ".." / "outside")

    def test_actual_available_ram_policy_boundary(self):
        for amount in (None, True, "35", 23.99, float("nan"), float("inf"), -1):
            with self.subTest(amount=amount), self.assertRaises(runner.StartDenied):
                runner.policy_check(amount)
        runner.policy_check(24)
        runner.policy_check(35.2843)

    def test_exact_reviewed_cpu_command(self):
        command, env = runner.command_and_environment(plan())
        self.assertEqual(command[3], "serve")
        for key, value in (("--gpu", "none"), ("--host", "127.0.0.1"), ("--port", "8001"),
                           ("--ram", "10"), ("--ctx", "2048"), ("--ngen", "256"),
                           ("--cap", "8"), ("--kv-slots", "1")):
            self.assertEqual(command[command.index(key) + 1], value)
        self.assertIn("--no-tune-profile", command)
        self.assertIn("--no-think", command)
        self.assertFalse(any(x in command for x in ("setup", "import", "start", "stop", "--switch")))
        self.assertEqual(env["COLI_CUDA"], "0")
        self.assertEqual(env["COLI_VULKAN"], "0")
        self.assertEqual(env["OMP_THREAD_LIMIT"], "2")

    def test_no_inherited_gpu_cluster_api_key_or_debug_writer(self):
        poison = {"COLI_API_KEY": "SECRET", "COLI_CUDA": "1", "COLI_VULKAN": "1",
                  "CLUSTER_WORKERS": "other-host", "COLI_SETUP_HOME": r"C:\Primary",
                  "PYTHONPATH": r"S:\Ultra_LLM", "HEAT_FILE": r"C:\Primary\heat",
                  "DUMP_LAYERS": r"C:\outside", "QWEN_DENSE_CACHE": r"C:\outside",
                  "CUDA_DENSE": "1", "Q36_MTP": "1", "COLI_PROFILE_CAP": "100"}
        with patch.dict(os.environ, poison):
            _, env = runner.command_and_environment(plan())
        for key in ("COLI_API_KEY", "CLUSTER_WORKERS", "PYTHONPATH", "DUMP_LAYERS",
                    "QWEN_DENSE_CACHE", "CUDA_DENSE", "COLI_PROFILE_CAP"):
            self.assertNotIn(key, env)
        self.assertNotIn("SECRET", json.dumps(env))
        self.assertTrue(Path(env["COLI_SETUP_HOME"]).is_relative_to(runner.HOME))

    def test_start_acknowledgement_required_before_spawning(self):
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=fake_native()), \
             patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaisesRegex(runner.StartDenied, "ack"):
                runner.run("start")
            spawn.assert_not_called()

    def test_verified_existing_supervisor_refuses_duplicate_start(self):
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=fake_native()), \
             patch.object(runner, "status", return_value={"supervisor_verified": True}), \
             patch.object(runner.subprocess, "Popen") as spawn:
            with self.assertRaises(runner.StartDenied):
                runner.run("start", acknowledge=True)
            spawn.assert_not_called()

    def test_plan_has_no_materialization_or_engine_creation(self):
        native = fake_native()
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=native), \
             patch.object(runner, "make_plan", return_value=plan()), \
             patch.object(runner, "materialize") as materialize:
            result = runner.run("plan")
        self.assertEqual(result["state"], "PLAN_ONLY")
        self.assertFalse(result["launch_performed"])
        materialize.assert_not_called()
        native.spawn_contained.assert_not_called()

    def test_foreign_primary_or_missing_health_refuses_start(self):
        native = fake_native()
        for metadata in ({"health": "bad"}, {"health": "ok", "model_ids": ["other"]}):
            with patch.object(runner, "probe_api", return_value=metadata):
                with self.assertRaises(runner.StartDenied):
                    runner.get_primary(native)

    def test_unknown_primary_port_owner_refused(self):
        native = fake_native()
        for rows in ([], [{"port": 8000, "pid": 1}, {"port": 8000, "pid": 2}]):
            native.listeners.return_value = rows
            with self.assertRaises(runner.StartDenied):
                runner.get_primary(native)

    def test_changed_primary_identity_refused(self):
        native = fake_native()
        native.identity.return_value = {**REC, "created_filetime": 101}
        with self.assertRaises(runner.StartDenied):
            runner.verify_primary(native, plan())

    def test_startup_waits_for_owned_engine_port_and_expected_api_model(self):
        for owners, engines, api in (
            (set(), [], {}), ({333}, [], {"health": "ok"}),
            ({333}, [REC], {"health": "ok", "model_ids": ["wrong"]}),
        ):
            self.assertEqual(runner.readiness("STARTING", owners, 333, engines, api), "STARTING")
        self.assertEqual(runner.readiness(
            "STARTING", {333}, 333, [REC], {"health": "ok", "model_ids": [runner.API_ID]}), "READY")

    def test_lost_engine_port_or_health_never_keeps_stale_ready(self):
        for owners, engines, api in (
            (set(), [REC], {"health": "ok", "model_ids": [runner.API_ID]}),
            ({333}, [], {"health": "ok", "model_ids": [runner.API_ID]}),
            ({333}, [REC], {"health": "bad", "model_ids": [runner.API_ID]}),
        ):
            with self.assertRaises(runner.StartDenied):
                runner.readiness("READY", owners, 333, engines, api)

    def test_foreign_port_owner_always_aborts_only_new_job(self):
        for previous in ("STARTING", "READY"):
            with self.assertRaises(runner.StartDenied):
                runner.readiness(previous, {999}, 333, [REC], {"health": "ok"})


class StopTests(unittest.TestCase):
    def test_wrong_pid_reused_pid_exe_sid_fail_closed(self):
        for field, value in (("pid", 1), ("created_filetime", 101),
                             ("exe", r"C:\Other\python.exe"), ("owner_sid", "OTHER")):
            self.assertFalse(NativeWindows.same(REC, {**REC, field: value}))

    def test_missing_or_invalid_identity_refused(self):
        for record in (None, {}, {**REC, "pid": True}, {**REC, "created_filetime": 0}):
            self.assertFalse(NativeWindows.same(record, REC))

    def test_foreign_windows_owner_never_signals_stop(self):
        native = fake_native()
        native.identity.return_value = {**REC, "owner_sid": "OTHER"}
        with patch.object(runner, "read_state", return_value=state()):
            with self.assertRaises(runner.StartDenied):
                runner.stop(native)
        native.signal_event.assert_not_called()

    def test_reused_supervisor_pid_never_signals_stop(self):
        native = fake_native()
        native.identity.side_effect = [REC, {**REC, "created_filetime": 101}]
        with patch.object(runner, "read_state", return_value=state()):
            with self.assertRaises(runner.StartDenied):
                runner.stop(native)
        native.signal_event.assert_not_called()

    def test_forged_stop_event_refused(self):
        native = fake_native()
        with patch.object(runner, "read_state", return_value={**state(), "stop_event": "other"}):
            with self.assertRaises(runner.StartDenied):
                runner.stop(native)
        native.signal_event.assert_not_called()

    def test_confirmed_stop_does_not_touch_primary_listener(self):
        native = fake_native()
        with patch.object(runner, "read_state", return_value=state()), \
             patch.object(runner, "status", return_value={"state": "STOPPED"}):
            result = runner.stop(native)
        self.assertEqual(result["state"], "STOPPED")
        native.signal_event.assert_called_once_with(state()["stop_event"])
        native.k.TerminateProcess.assert_not_called()

    def test_unconfirmed_stop_never_claims_success(self):
        native = fake_native()
        with patch.object(runner, "read_state", return_value=state()), \
             patch.object(runner, "status", return_value={"state": "READY"}):
            with self.assertRaisesRegex(runner.StartDenied, "not confirmed"):
                runner.stop(native)

    def test_foreign_8001_listener_is_left_running(self):
        native = fake_native()
        native.listeners.return_value = [{"port": 8001, "pid": 999}]
        with patch.object(runner, "read_state", return_value=state()), \
             patch.object(runner, "status", return_value={"state": "STOPPED"}):
            with self.assertRaisesRegex(runner.StartDenied, "still occupied"):
                runner.stop(native)
        native.k.TerminateProcess.assert_not_called()

    def test_graceful_stop_requires_job_membership_before_any_file_write(self):
        native = fake_native()
        native.member.return_value = False
        with patch.object(Path, "write_text") as write:
            with self.assertRaises(runner.StartDenied):
                runner.graceful_stop(native, 111, REC, plan())
        write.assert_not_called()

    def test_graceful_stopfile_wrong_pid_refused(self):
        native = fake_native()
        native.member.return_value = True
        with patch.object(Path, "read_text", return_value="999 model"), \
             patch.object(Path, "write_text") as write:
            with self.assertRaises(runner.StartDenied):
                runner.graceful_stop(native, 111, REC, plan())
        write.assert_not_called()

    def test_only_isolated_stopfile_written_for_matching_job_member(self):
        native = fake_native()
        native.member.return_value = True
        with patch.object(Path, "read_text", return_value="333 model"), \
             patch.object(Path, "write_text", autospec=True) as write:
            runner.graceful_stop(native, 111, REC, plan())
        self.assertEqual(write.call_args.args[0], Path(runner.paths()["gateway_stop"]))

    def test_preparation_failure_is_persisted_without_spawning(self):
        native = fake_native()
        states = []
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=native), \
             patch.object(runner, "file_lock", side_effect=lambda: nullcontext()), \
             patch.object(runner, "make_plan", side_effect=runner.StartDenied("blocked")), \
             patch.object(runner, "write_json", side_effect=lambda p, data: states.append(dict(data))):
            result = runner.supervise("a" * 32)
        self.assertEqual(result["state"], "ERROR")
        self.assertEqual(states[0]["state"], "PREPARING")
        self.assertEqual(states[-1]["reason"], "blocked")
        native.spawn_contained.assert_not_called()

    def test_owner_can_cancel_before_runtime_copy_or_spawn(self):
        native = fake_native()
        native.k.WaitForSingleObject.return_value = 0
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=native), \
             patch.object(runner, "file_lock", side_effect=lambda: nullcontext()), \
             patch.object(runner, "make_plan", return_value=plan()), \
             patch.object(runner, "verify_primary"), patch.object(runner, "write_json"), \
             patch.object(runner, "materialize") as materialize:
            result = runner.supervise("a" * 32)
        self.assertEqual(result["state"], "STOPPED")
        materialize.assert_not_called()
        native.spawn_contained.assert_not_called()

    def test_owner_cancellation_after_runtime_copy_still_prevents_launch(self):
        native = fake_native()
        native.k.WaitForSingleObject.side_effect = [258, 0]
        with patch.object(runner, "require_local_server"), \
             patch.object(runner, "NativeWindows", return_value=native), \
             patch.object(runner, "file_lock", side_effect=lambda: nullcontext()), \
             patch.object(runner, "make_plan", return_value=plan()), \
             patch.object(runner, "verify_primary"), patch.object(runner, "write_json"), \
             patch.object(runner, "materialize") as materialize:
            result = runner.supervise("a" * 32)
        self.assertEqual(result["state"], "STOPPED")
        materialize.assert_called_once()
        native.spawn_contained.assert_not_called()
        native.job.assert_not_called()

    def test_production_guard_blocks_home_plan_start_stop_status(self):
        for action in ("plan", "start", "stop", "status"):
            with patch("server_preflight.socket.gethostname", return_value="DESKTOP-SC96D3U"), \
                 patch.object(runner, "NativeWindows") as native:
                with self.assertRaises(RuntimeError):
                    runner.run(action, acknowledge=True)
                native.assert_not_called()

    def test_cli_integration_delegates_explicit_action(self):
        with patch.object(runner, "run", return_value={"state": "PLAN_ONLY"}) as run, \
             patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli(["--colibri2", "plan"]), 0)
        run.assert_called_once_with("plan", acknowledge=False, wait=900)

    def test_cli_primary_instance_rejected_before_delegation(self):
        with patch.object(runner, "run") as run, patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(cli(["--colibri2", "stop", "--instance", "slot1"]), 2)
        run.assert_not_called()


@unittest.skipUnless(os.name == "nt", "Windows native integration only")
class NativeIntegrationTests(unittest.TestCase):
    def test_structure_sizes_match_windows_x64_abi(self):
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            self.assertEqual(ctypes.sizeof(BasicLimit), 64)
            self.assertEqual(ctypes.sizeof(ExtendedLimit), 144)

    def test_current_process_identity_memory_and_listener_query(self):
        native = NativeWindows()
        with native.process(os.getpid()) as handle:
            identity = native.identity(handle)
            self.assertTrue(native.same(identity, identity))
            self.assertEqual(identity["pid"], os.getpid())
            self.assertTrue(identity["owner_sid"].startswith("S-1-"))
        self.assertGreater(native.memory()["total_gib"], 0)
        self.assertIsInstance(native.listeners(), list)

    def test_mutex_denies_another_owner_and_session_event_is_exact(self):
        native = NativeWindows()
        name = rf"Local\UltraLLM-test-{uuid.uuid4().hex}"
        with native.mutex(name):
            # Windows mutex is reentrant on the same thread; contend on another.
            from concurrent.futures import ThreadPoolExecutor
            def compete():
                with native.mutex(name):
                    return True
            with ThreadPoolExecutor(max_workers=1) as pool:
                with self.assertRaises(WindowsError):
                    pool.submit(compete).result()
        event = native.event(name + "-stop")
        try:
            native.signal_event(name + "-stop")
            self.assertEqual(native.k.WaitForSingleObject(event, 0), 0)
        finally:
            native.close(event)

    def test_suspended_dummy_and_descendant_are_contained_and_close_together(self):
        native = NativeWindows()
        job = native.job(rf"Local\UltraLLM-test-job-{uuid.uuid4().hex}", 0.25)
        handle = None
        child_context = None
        child_handle = None
        try:
            with tempfile.TemporaryFile(dir=HERE, mode="w+b") as stdout, \
                 tempfile.TemporaryFile(dir=HERE, mode="w+b") as stderr:
                command = [sys.executable, "-B", "-c",
                    "import subprocess,sys,time; "
                    "p=subprocess.Popen([sys.executable,'-B','-c','import time; time.sleep(30)']); "
                    "print(p.pid,flush=True); time.sleep(30)"]
                handle, record = native.spawn_contained(
                    command, dict(os.environ), str(Path(sys.executable).parent), stdout, stderr, job)
                self.assertTrue(native.member(handle, job))
                deadline = time.monotonic() + 5
                python_children = []
                while time.monotonic() < deadline:
                    python_children = []
                    for pid in native.job_pids(job):
                        if pid == record["pid"]:
                            continue
                        try:
                            with native.process(pid) as candidate:
                                if (Path(native.identity(candidate)["exe"]).name.casefold()
                                        == Path(sys.executable).name.casefold()):
                                    self.assertTrue(native.member(candidate, job))
                                    python_children.append(pid)
                        except WindowsError:
                            continue  # Transient Windows helpers may have already exited.
                    if python_children:
                        break
                    time.sleep(.05)
                self.assertEqual(len(python_children), 1,
                                 "Expected one owned Python descendant (conhost.exe may also join)")
                child_pid = python_children[0]
                child_context = native.process(child_pid)
                child_handle = child_context.__enter__()
                self.assertTrue(native.member(child_handle, job))
                native.close(job)
                job = None
                self.assertEqual(native.k.WaitForSingleObject(handle, 5000), 0)
                self.assertEqual(native.k.WaitForSingleObject(child_handle, 5000), 0)
        finally:
            native.close(job)
            native.close(handle)
            if child_context and child_handle:
                child_context.__exit__(None, None, None)

    def test_assignment_failure_never_resumes_or_targets_a_foreign_pid(self):
        native = NativeWindows()
        native.k = MagicMock()
        native.k.AssignProcessToJobObject.return_value = 0
        native.k.TerminateProcess.return_value = 1
        with patch("_winapi.CreateProcess", return_value=(801, 802, 803, 804)), \
             patch("msvcrt.get_osfhandle", side_effect=[11, 12, 13]), \
             patch("os.set_handle_inheritable"):
            with self.assertRaises(WindowsError):
                native.spawn_contained([sys.executable, "-c", "pass"], {},
                                       str(HERE), MagicMock(), MagicMock(), 900)
        native.k.ResumeThread.assert_not_called()
        native.k.TerminateProcess.assert_called_once_with(801, 1)
        self.assertTrue(any(call.args == (801,) for call in native.k.CloseHandle.call_args_list))

    def test_job_commit_limit_is_enforced_for_benign_dummy(self):
        native = NativeWindows()
        job = native.job(rf"Local\UltraLLM-test-memory-{uuid.uuid4().hex}", .125)
        handle = None
        try:
            limits = ExtendedLimit()
            native.checked(native.k.QueryInformationJobObject(
                job, 9, ctypes.byref(limits), ctypes.sizeof(limits), None), "job query")
            self.assertEqual(limits.JobMemoryLimit, 128 * 1024 * 1024)
            self.assertTrue(limits.Basic.LimitFlags & 0x2000)
            with tempfile.TemporaryFile(dir=HERE, mode="w+b") as stdout, \
                 tempfile.TemporaryFile(dir=HERE, mode="w+b") as stderr:
                command = [sys.executable, "-B", "-c",
                    "try:\n a=bytearray(256*1024*1024)\n print('UNEXPECTED',flush=True)\n"
                    "except MemoryError:\n print('LIMIT_ENFORCED',flush=True)\n"]
                handle, _ = native.spawn_contained(
                    command, dict(os.environ), str(Path(sys.executable).parent), stdout, stderr, job)
                self.assertEqual(native.k.WaitForSingleObject(handle, 5000), 0)
                stdout.seek(0)
                self.assertIn(b"LIMIT_ENFORCED", stdout.read())
        finally:
            native.close(job)
            native.close(handle)


if __name__ == "__main__":
    unittest.main()
