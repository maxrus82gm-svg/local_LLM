"""CHAT-01 Manager tests: real loopback HTTP, synthetic fake backend only.

Never calls live Colibri, a public network, or real service credentials.
"""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

import chat_runtime
import live_manager
from pairing_inbox import PairingInbox

TOKEN = "TEST-CHAT-CLIENT-TOKEN-NOT-PRODUCTION-123456789012345678"


class FakeColibri(BaseHTTPRequestHandler):
    calls = []

    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        n = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(n))
        self.calls.append(body)
        raw = json.dumps({"choices": [{"message": {
            "role": "assistant", "content": "Здравствуйте! Это тестовый ответ."},
            "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 8}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


class ChatRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for d in ("colibri", "models", "private"):
            (root / d).mkdir()
        FakeColibri.calls = []
        self.backend = ThreadingHTTPServer(("127.0.0.1", 0), FakeColibri)
        self.backend.daemon_threads = True
        self.backend_thread = threading.Thread(
            target=self.backend.serve_forever, daemon=True)
        self.backend_thread.start()
        self.addCleanup(self.backend_thread.join, 3)
        self.addCleanup(self.backend.server_close)
        self.addCleanup(self.backend.shutdown)
        self.port = self.backend.server_address[1]
        self.config_file = root / "private" / "manager.json"
        config = {
            "manager_id": "test-manager", "display_name": "QA",
            "bind_host": "127.0.0.1", "listen_port": 18443,
            "colibri_root": str(root / "colibri"),
            "models_root": str(root / "models"),
            "cert_file": str(root / "private" / "cert.pem"),
            "key_file": str(root / "private" / "key.pem"),
            "allowed_client_ips": ["127.0.0.1"],
            "slots": [{"slot_id": "slot1", "api_port": self.port},
                      {"slot_id": "slot2", "api_port": 18802}],
            "clients": [{"client_id": "viewer",
                         "sha256": hashlib.sha256(TOKEN.encode()).hexdigest(),
                         "allowed_slots": ["slot1"]}]
        }
        self.config_file.write_text(json.dumps(config), encoding="utf-8")
        self.telemetry = patch.object(live_manager, "_os_telemetry", return_value={
            "total_gib": 64, "free_gib": 45,
            "listeners": [{"port": self.port, "pid": 1001}]})
        self.telemetry.start()
        self.addCleanup(self.telemetry.stop)

        def fake_local_api(port, path):
            if port != self.port:
                return None
            if path == "/health":
                return {"status": "ok", "scheduler": {
                    "active": 0, "queued": 0, "capacity": 1}}
            if path == "/v1/models":
                return {"data": [{"id": "test-llm"}]}
            return None

        self.api_patch = patch.object(live_manager, "_local_api_json",
                                      side_effect=fake_local_api)
        self.api_patch.start()
        self.addCleanup(self.api_patch.stop)
        self.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            live_manager.make_handler(
                self.config_file, live_manager.load_config(self.config_file),
                PairingInbox()))
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.thread.join, 3)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener = build_opener(ProxyHandler({}))
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"

    def req(self, payload, *, token=TOKEN, path="/v1/chat"):
        headers = {"Content-Type": "application/json"}
        if token is not None:
            headers["Authorization"] = "Bearer " + token
        request = Request(self.url + path, method="POST",
                          data=json.dumps(payload).encode(), headers=headers)
        try:
            with self.opener.open(request, timeout=8) as response:
                return response.status, json.loads(response.read())
        except HTTPError as error:
            return error.code, json.loads(error.read())

    def test_real_loopback_proxy_and_response(self):
        body = {"slot_id": "slot1", "model_id": "test-llm",
                "messages": [{"role": "user", "content": "Привет!"}]}
        code, response = self.req(body)
        self.assertEqual(code, 200)
        self.assertEqual(response["manager_id"], "test-manager")
        self.assertEqual(response["reply"], "Здравствуйте! Это тестовый ответ.")
        self.assertEqual(response["usage"]["completion_tokens"], 8)
        self.assertEqual(len(FakeColibri.calls), 1)
        self.assertEqual(FakeColibri.calls[0]["model"], "test-llm")
        self.assertFalse(FakeColibri.calls[0]["stream"])

    def test_auth_slot_model_and_unknown_are_denied(self):
        good = {"slot_id": "slot1", "model_id": "test-llm",
                "messages": [{"role": "user", "content": "Проверка"}]}
        self.assertEqual(self.req(good, token=None)[0], 401)
        self.assertEqual(self.req(good, token="bad-token")[0], 401)
        self.assertEqual(self.req({**good, "slot_id": "slot2"})[0], 403)
        self.assertEqual(self.req({**good, "slot_id": "slot9"})[0], 404)
        self.assertEqual(self.req({**good, "model_id": "unknown-model"})[0], 409)
        self.assertEqual(len(FakeColibri.calls), 0)

    def test_invalid_messages_and_start_still_denied(self):
        good = {"slot_id": "slot1", "model_id": "test-llm",
                "messages": [{"role": "user", "content": "Hi"}]}
        for bad in (
            {**good, "url": "http://evil.example"},
            {**good, "messages": []},
            {**good, "messages": [{"role": "system", "content": "hack"}]},
            {**good, "messages": [{"role": "user", "content": "x" * 131073}]},
            {**good, "messages": [{"role": "assistant", "content": "old"}]},
        ):
            self.assertEqual(self.req(bad)[0], 400)
        self.assertEqual(self.req({"slot_id": "slot1"}, path="/v1/start")[0], 405)
        self.assertEqual(len(FakeColibri.calls), 0)

    def test_ready_unknown_or_busy_fail_closed(self):
        good = {"slot_id": "slot1", "model_id": "test-llm",
                "messages": [{"role": "user", "content": "Hi"}]}
        with patch.object(live_manager, "_chat_listener", side_effect=chat_runtime.ChatError("slot_process_unverified",409)):
            self.assertEqual(self.req(good)[0], 409)
        with patch.object(live_manager, "_local_api_json",
                          side_effect=lambda p, q: {"status": "ok"} if q == "/health"
                          else {"data": [{"id": "test-llm"}]}):
            self.assertEqual(self.req(good)[0], 409)
        self.assertEqual(len(FakeColibri.calls), 0)

    def test_selected_chat_never_builds_the_full_overview_and_checks_instance(self):
        body={"slot_id":"slot1","model_id":"test-llm","messages":[{"role":"user","content":"x"*5000}]}
        with patch.object(live_manager,"live_snapshot",side_effect=AssertionError("overview on hot path")), \
             patch.object(live_manager,"_os_telemetry",side_effect=AssertionError("RAM probe on hot path")):
            self.assertEqual(self.req(body)[0],200)
            self.assertEqual(self.req({**body,"instance_id":"legacy-wrong"})[0],409)
        self.assertNotIn("max_tokens",FakeColibri.calls[-1])
        self.assertNotIn("enable_thinking",FakeColibri.calls[-1])


if __name__ == "__main__":
    unittest.main()
