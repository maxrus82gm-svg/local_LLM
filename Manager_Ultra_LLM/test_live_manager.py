"""Safety regression for live Manager: no model start/stop and no network bind."""
import hashlib
import unittest
from unittest.mock import patch
import live_manager as live

CFG = {"manager_id": "server-1", "display_name": "Test Host",
       "models_root": "C:/nonexistent", "slots": [
           {"slot_id": "slot1", "api_port": 8000, "protected": True},
           {"slot_id": "slot2", "api_port": 8001, "protected": False}]}
MEM = {"total_gib": 48.0, "free_gib": 30.0,
       "listeners": [{"port": 8000, "pid": 17}]}


class LiveSecurityTests(unittest.TestCase):
    def test_native_snapshot_performance_identity_and_cancel(self):
        import threading
        cancel = threading.Event()
        listener = (17, "legacy-" + "a"*32)
        binding = ("slot1", cancel, "b"*32, listener)
        health = {"status": "ok", "scheduler": {"active": 1, "queued": 0},
                  "live": [{"state": "writing", "tok_s_now": 12.5, "tok_s": 10}]}
        with patch.object(live, "_chat_listener", return_value=listener):
            sample = live._snapshot_performance(health, binding, 8000, listener)
            self.assertEqual(sample, {"instance_id": "b"*32, "source": "engine_health",
                                      "current_tok_s": 12.5, "request_mean_tok_s": 10})
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, None))
            self.assertIsNone(live._snapshot_performance(
                {**health, "scheduler": {"active": 2, "queued": 0}}, binding, 8000, listener))
            cancel.set()
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, listener))
        cancel.clear()
        with patch.object(live, "_chat_listener", return_value=(18, "legacy-"+"c"*32)):
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, listener))

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_snapshot_performance_respects_slot_grant(self, local, os_query, dirs):
        import threading
        listener = (17, "legacy-"+"a"*32)
        binding = ("slot1", threading.Event(), "b"*32, listener)
        local.side_effect = lambda port, path: (
            {"status":"ok","scheduler":{"active":1,"queued":0,"capacity":1},
             "live":[{"state":"writing","tok_s_now":9.0,"tok_s":8.0}]}
            if path == "/health" else {"data":[{"id":"model-A"}]})
        with patch.object(live, "_chat_listener", return_value=listener):
            allowed = live.live_snapshot(CFG, {"client_id":"c","allowed_slots":["slot1"]},
                                         performance_bindings={"slot1":binding})
            denied = live.live_snapshot(CFG, {"client_id":"c","allowed_slots":[]},
                                        performance_bindings={"slot1":binding})
        self.assertEqual(allowed["slots"][0]["live_performance"]["current_tok_s"],9.0)
        self.assertNotIn("live_performance",denied["slots"][0])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_ready_requires_trustworthy_scheduler(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok"} if path == "/health" else
            {"data": [{"id": "verified_model"}]})
        client = {"client_id": "client1", "allowed_slots": ["slot1"]}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["slots"][0]["engine_state"], "ready")
        self.assertEqual(result["slots"][0]["availability"], "unknown")
        self.assertFalse(result["reservation_granted"])
        self.assertFalse(result["admission_enabled"])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_ready_unreserved_is_not_a_lease(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok", "scheduler": {"active": 0, "queued": 0, "capacity": 1}}
            if path == "/health" else {"data": [{"id": "verified_model"}]})
        client = {"client_id": "client1", "allowed_slots": ["slot1"]}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["slots"][0]["availability"], "ready_unreserved")
        self.assertFalse(result["slots"][0]["reservation_granted"])

    @patch.object(live, "_inventory_models", return_value=[{"directory_name": "sensitive"}])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_unpermitted_client_cannot_read_slot_details(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok", "scheduler": {"active": 0, "queued": 0, "capacity": 1}}
            if path == "/health" else {"data": [{"id": "model-A"}]})
        client = {"client_id": "blocked", "allowed_slots": []}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["models"], [])
        for row in result["slots"]:
            self.assertEqual(row["availability"], "denied")
            self.assertIsNone(row["pid"])
            self.assertEqual(row["models"], [])
            self.assertIsNone(row["scheduler"])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_local_api_json", return_value=None)
    def test_snapshot_shows_verified_optional_ddr_and_installed_capacity(self, api, dirs):
        evidence = dict(MEM, ddr_generation="DDR4", installed_gib=48.0)
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertEqual(result["memory"]["ddr_generation"], "DDR4")
        self.assertEqual(result["memory"]["installed_gib"], 48.0)
        self.assertEqual(result["memory"]["free_gib"], 30.0)
        evidence["ddr_generation"] = "UNKNOWN"
        evidence["installed_gib"] = 0
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertNotIn("ddr_generation", result["memory"])
        self.assertNotIn("installed_gib", result["memory"])

    def test_regular_telemetry_native_and_hardware_probe_cached(self):
        import subprocess
        from unittest.mock import Mock
        native = Mock()
        native.memory.return_value = {"total_gib": 48, "free_gib": 30}
        native.listeners.return_value = [{"port": 8000, "pid": 17}, {"port": 9999, "pid": 99}]
        completed = Mock(returncode=0, stdout='{"ddr_generation":"DDR4","installed_gib":48}')
        with patch.object(live, "_HARDWARE_RAM_CACHE", None), \
                patch("windows_process.NativeWindows", return_value=native), \
                patch.object(live.subprocess, "run", return_value=completed) as run, \
                patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            for _ in range(4):
                data = live._os_telemetry([8000])
                self.assertEqual(data["listeners"], [{"port": 8000, "pid": 17}])
                self.assertEqual(data["ddr_generation"], "DDR4")
            self.assertEqual(native.memory.call_count, 4)
            self.assertEqual(native.listeners.call_count, 4)
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

    def test_failed_optional_hardware_probe_is_not_repeated(self):
        with patch.object(live, "_HARDWARE_RAM_CACHE", None), \
                patch.object(live.subprocess, "run", side_effect=OSError("unavailable")) as run:
            self.assertEqual(live._hardware_ram(), {})
            self.assertEqual(live._hardware_ram(), {})
            run.assert_called_once()

    def test_native_gpu_aggregation_and_unknown_counters(self):
        import resource_policy as resources
        samples = [("dedicated_gib", "pid_42_luid_a", 2**30),
                   ("dedicated_gib", "pid_42_luid_b", 2**29),
                   ("shared_gib", "pid_42_luid_a", 2**28),
                   ("shared_gib", "pid_43_luid_a", None),
                   ("shared_gib", "pid_43_luid_b", 2**30),
                   ("dedicated_gib", "pid_44_luid_a", 0),
                   ("dedicated_gib", "not_a_pid", 2**30)]
        with patch.object(resources, "_pdh_gpu_samples", return_value=samples), \
                patch.object(live.subprocess, "run") as run:
            self.assertEqual(resources.process_gpu_memory(),
                             {42: {"dedicated_gib": 1.5, "shared_gib": 0.25},
                              44: {"dedicated_gib": 0}})
            run.assert_not_called()
        with patch.object(resources, "_pdh_gpu_samples", side_effect=OSError):
            self.assertEqual(resources.process_gpu_memory(), {})

    def test_token_digest_and_missing_bearer_fail_closed(self):
        token = "SAMPLE-UNIT-TEST-ONLY-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        conf = {"clients": [{"client_id": "alice",
                             "sha256": hashlib.sha256(token.encode()).hexdigest(),
                             "allowed_slots": ["slot1"]}]}
        self.assertIsNone(live._authorized_client(conf, ""))
        self.assertIsNone(live._authorized_client(conf, "Bearer wrong"))
        self.assertEqual(live._authorized_client(conf, "Bearer " + token)["client_id"],
                         "alice")


if __name__ == "__main__":
    unittest.main()
