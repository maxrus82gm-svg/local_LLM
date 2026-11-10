"""Safety tests for the real multi-Manager HTTPS client configuration."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import live_client


class LiveClientValidation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = Path(self.temp.name) / "profiles.json"

    def _profiles(self, entries):
        self.config.write_text(json.dumps({"managers": entries}), encoding="utf-8")
        return live_client.load_profiles(self.config)

    def test_multiple_managers_have_separate_client_id_and_trust(self):
        rows = self._profiles([
            {"manager_id": "server-a", "client_id": "alice",
             "endpoint": "https://192.168.0.77:8443",
             "ca_cert": "a-cert.pem", "token_file": "a-token.txt"},
            {"manager_id": "server-b", "client_id": "alice-b",
             "endpoint": "https://node-b.example:9443",
             "ca_cert": "b-cert.pem", "token_file": "b-token.txt"}])
        self.assertEqual(len(rows), 2)
        self.assertNotEqual(rows[0]["token_file"], rows[1]["token_file"])
        self.assertNotEqual(rows[0]["client_id"], rows[1]["client_id"])

    def test_refuses_insecure_urls_and_missing_identity(self):
        base = {"manager_id": "a", "client_id": "alice",
                "ca_cert": "a.pem", "token_file": "a.txt"}
        for bad in ({"endpoint": "http://127.0.0.1:8443"},
                    {"endpoint": "https://u:p@node:8443"},
                    {"endpoint": "https://node:8443/private"},
                    {"endpoint": "https://node:8443", "client_id": None}):
            row = dict(base, **bad)
            with self.subTest(row=row), self.assertRaises(ValueError):
                self._profiles([row])

    def test_duplicate_manager_id_refused(self):
        row = {"manager_id": "x", "client_id": "alice",
               "endpoint": "https://node:8443", "ca_cert": "a.pem",
               "token_file": "a.txt"}
        with self.assertRaises(ValueError):
            self._profiles([row, row])

    def test_missing_client_secret_cannot_be_online(self):
        profile = self._profiles([{"manager_id": "x", "client_id": "alice",
                                   "endpoint": "https://node:8443",
                                   "ca_cert": "a.pem", "token_file": "missing.txt"}])[0]
        response = live_client.fetch_one(profile)
        self.assertEqual(response["status"], "unreachable")
        self.assertEqual(response["error"], "connection_or_config_error")
        self.assertIsNone(response["data"])


if __name__ == "__main__":
    unittest.main()
