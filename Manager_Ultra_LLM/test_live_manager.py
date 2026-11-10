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
