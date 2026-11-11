"""Web Client P1: local-only transport, first-run setup and token isolation."""
from contextlib import redirect_stdout
from http.server import ThreadingHTTPServer
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, Request
import web_client

TEST_CERT = "-----BEGIN CERTIFICATE-----\nTEST-PUBLIC-CERT\n-----END CERTIFICATE-----"


class WebClientP1Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.csrf = "test-csrf-not-a-secret"
        holder = {"port": 0}
        handler = web_client.make_handler(self.root, lambda: holder["port"], self.csrf)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        holder["port"] = self.server.server_address[1]
        self.port = holder["port"]
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.shutdown)
        self.opener = build_opener(ProxyHandler({}))

    def shutdown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    def request(self, path, *, method="GET", host=None,
                origin=None, csrf=None, body=None):
        headers = {"Host": host or f"127.0.0.1:{self.port}"}
        if origin is not None:
            headers["Origin"] = origin
        if csrf is not None:
            headers["X-Ultra-CSRF"] = csrf
        if body is not None:
            headers["Content-Type"] = "application/json"
        req = Request(f"http://127.0.0.1:{self.port}{path}",
                      method=method, headers=headers,
                      data=(json.dumps(body).encode() if body is not None else None))
        try:
            with self.opener.open(req, timeout=4) as r:
                return r.status, r.read(), dict(r.headers)
        except HTTPError as r:
            return r.code, r.read(), dict(r.headers)

    def test_empty_config_starts_onboarding_and_has_real_assets(self):
        for path in ("/", "/client.css", "/client.js"):
            code, data, headers = self.request(path)
            self.assertEqual(code, 200)
            self.assertGreater(len(data), 100)
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        code, data, _ = self.request("/api/config")
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(data)["configured"])
        code, data, _ = self.request("/api/status")
        self.assertEqual(code, 200)
        self.assertFalse(json.loads(data)["configured"])

    def test_loopback_host_rebinding_is_blocked(self):
        code, body, _ = self.request("/api/status", host="evil.example")
        self.assertEqual(code, 403)
        self.assertEqual(json.loads(body)["error"], "untrusted_host")

    def test_mutating_calls_require_exact_origin_and_csrf(self):
        for origin, csrf in ((None, None),
                             ("https://evil.example", self.csrf),
                             (f"http://127.0.0.1:{self.port}", "bad")):
            status, _, _ = self.request(
                "/api/enroll", method="POST", origin=origin,
                csrf=csrf, body={"some": "request"})
            self.assertEqual(status, 403)

    def test_invalid_web_enrollment_is_rejected_without_files(self):
        bad = {"manager_id": "manager-a", "client_id": "client-a",
               "display_name": "Server", "host": "127.0.0.1",
               "port": 8443, "certificate": "invalid"}
        code, _, _ = self.request(
            "/api/enroll", method="POST",
            origin=f"http://127.0.0.1:{self.port}",
            csrf=self.csrf, body=bad)
        self.assertEqual(code, 400)
        self.assertFalse((self.root / "managers.json").exists())

    def test_profile_generation_returns_digest_not_bearer(self):
        enrollment = {"manager_id": "manager-a", "client_id": "client-a",
                      "display_name": "Test server", "host": "127.0.0.1",
                      "port": 8443, "certificate": TEST_CERT}
        # Test certificate is deliberately synthetic, never used for TLS.
        with patch.object(web_client.ssl, "PEM_cert_to_DER_cert", return_value=b"x" * 128), \
             patch("pairing_client._require_private_acl"):
            code, body, _ = self.request(
                "/api/enroll", method="POST",
                origin=f"http://127.0.0.1:{self.port}",
                csrf=self.csrf, body=enrollment)
        self.assertEqual(code, 201)
        data = json.loads(body)
        token_path = self.root / "manager-a.client-a.token"
        secret = token_path.read_text("ascii")
        self.assertEqual(len(data["registration_sha256"]), 64)
        self.assertNotIn(secret, body.decode("utf-8"))
        code, content, _ = self.request("/api/config")
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(content)["configured"])
        self.assertNotIn(secret, content.decode("utf-8"))
        self.assertNotIn("token_file", content.decode("utf-8"))

    def test_invalid_ip_host_and_port_rejected(self):
        for host, port in (("0.0.0.0", 8443),
                           ("bad/url", 8443),
                           ("192.168.0.77", 80),
                           ("224.0.0.1", 8443)):
            with self.subTest(host=host, port=port), self.assertRaises(ValueError):
                web_client._safe_address(host, port)

    def test_local_shutdown_requires_csrf(self):
        code, _, _ = self.request("/api/shutdown", method="POST")
        self.assertEqual(code, 403)
        self.assertTrue(self.thread.is_alive())
        code, body, _ = self.request(
            "/api/shutdown", method="POST",
            origin=f"http://127.0.0.1:{self.port}", csrf=self.csrf)
        self.assertEqual(code, 200)
        self.assertTrue(json.loads(body)["stopping"])
        self.thread.join(2)
        self.assertFalse(self.thread.is_alive())

    def test_pairing_admin_read_uses_server_side_authorization(self):
        data = {"manager_id":"manager-a","slots":[{"slot_id":"slot1"}],
                "requests":[{"client_id":"client-b","source_ip":"127.0.0.1"}]}
        with patch.object(web_client,"admin_requests",return_value=data) as call:
            status,body,_=self.request("/api/pairing/admin?manager_id=manager-a")
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body),data)
        self.assertEqual(call.call_args.args[1],"manager-a")
        with patch.object(web_client,"admin_requests",
                          side_effect=web_client.PairingRequestError("access_denied")):
            status,body,_=self.request("/api/pairing/admin?manager_id=manager-a")
        self.assertEqual(status,403)
        self.assertNotIn("token",body.decode())

    def test_pairing_approval_and_denial_require_csrf(self):
        payload={"manager_id":"manager-a",
                 "ticket_id":"abcdefghijklmnopqrstuvwxyz012345",
                 "allowed_slots":["slot2"]}
        with patch.object(web_client,"admin_decision",return_value={"state":"approved"}) as call:
            status,_,_=self.request("/api/pairing/approve",method="POST",body=payload)
            self.assertEqual(status,403)
            call.assert_not_called()
            status,body,_=self.request(
                "/api/pairing/approve",method="POST",body=payload,
                origin=f"http://127.0.0.1:{self.port}",csrf=self.csrf)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)["state"],"approved")
            self.assertTrue(call.call_args.kwargs["approve"])
        denial={"manager_id":"manager-a","ticket_id":payload["ticket_id"]}
        with patch.object(web_client,"admin_decision",return_value={"state":"denied"}) as call:
            status,body,_=self.request(
                "/api/pairing/deny",method="POST",body=denial,
                origin=f"http://127.0.0.1:{self.port}",csrf=self.csrf)
            self.assertEqual(status,200)
            self.assertEqual(json.loads(body)["state"],"denied")
            self.assertFalse(call.call_args.kwargs["approve"])

    def test_retry_uses_existing_profile_not_second_credential(self):
        with patch.object(web_client,"submit_profile",
                          return_value={"state":"pending","manager_id":"manager-a"}) as call:
            status,body,_=self.request(
                "/api/pairing/retry",method="POST",body={"manager_id":"manager-a"},
                origin=f"http://127.0.0.1:{self.port}",csrf=self.csrf)
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["state"],"pending")
        self.assertEqual(call.call_args.args[1],"manager-a")
        status,_,_=self.request(
            "/api/pairing/retry",method="POST",
            body={"manager_id":"manager-a","token":"bad"},
            origin=f"http://127.0.0.1:{self.port}",csrf=self.csrf)
        self.assertEqual(status,400)

    def test_status_reports_ticket_without_exposing_config(self):
        (self.root/"managers.json").write_text('{"managers":[{}]}',encoding="utf-8")
        pretend=[{"manager_id":"manager-a","name":"QA Manager",
                  "status":"unreachable","data":None,"error":"unauthorized"}]
        with patch.object(web_client,"load_profiles",return_value=[{"manager_id":"manager-a"}]), \
             patch.object(web_client,"fetch_all",return_value=pretend), \
             patch.object(web_client,"check_profile_ticket",return_value="pending"):
            status,body,_=self.request("/api/status")
        self.assertEqual(status,200)
        self.assertEqual(json.loads(body)["managers"][0]["pairing_state"],"pending")
        self.assertNotIn("token_file",body.decode())

    def test_server_never_offers_mutating_remote_operations(self):
        code, _, _ = self.request(
            "/api/start", method="POST",
            origin=f"http://127.0.0.1:{self.port}",
            csrf=self.csrf, body={"slot_id": "slot1"})
        self.assertEqual(code, 404)


if __name__ == "__main__":
    unittest.main()
