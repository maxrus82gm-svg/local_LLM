"""Local-only credential enrollment tests; no real tokens in fixtures."""
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
from unittest.mock import patch
from contextlib import redirect_stdout
import unittest

import pairing_client


class PairingClientTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.private = self.root / "private"
        self.private.mkdir()
        self.cert = self.root / "public.pem"
        self.cert.write_text("PUBLIC CERT UNIT TEST", encoding="utf-8")

    def _create(self, manager="manager-a", endpoint="https://localhost:8443"):
        out = io.StringIO()
        with patch.object(pairing_client, "_require_private_acl"), redirect_stdout(out):
            pairing_client.enroll(self.private, manager, "client-home",
                                  endpoint, self.cert, "Manager A")
        return out.getvalue()

    def test_credential_is_local_and_only_digest_printed(self):
        printed = self._create()
        path = self.private / "manager-a.client-home.token"
        token = path.read_text(encoding="ascii")
        assert len(token) >= 48
        assert token not in printed
        assert hashlib.sha256(token.encode("ascii")).hexdigest() in printed
        saved = json.loads((self.private / "managers.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["managers"][0]["client_id"], "client-home")
        self.assertEqual(saved["managers"][0]["endpoint"], "https://localhost:8443")

    def test_multiple_managers_are_independently_enrolled(self):
        self._create("node-a")
        self._create("node-b", "https://192.168.0.77:8443")
        saved = json.loads((self.private / "managers.json").read_text(encoding="utf-8"))
        self.assertEqual(len(saved["managers"]), 2)
        self.assertNotEqual(saved["managers"][0]["token_file"], saved["managers"][1]["token_file"])
        with self.assertRaises(ValueError):
            self._create("node-a")

    def test_insecure_endpoint_does_not_leave_token(self):
        with self.assertRaises(ValueError):
            self._create(endpoint="http://localhost:8443")
        self.assertFalse((self.private / "manager-a.client-home.token").exists())
        self.assertFalse((self.private / "managers.json").exists())

    def test_acl_subprocess_uses_only_its_own_system_module_path(self):
        ps_home = Path(r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0"
        inherited = str(self.root / "incompatible-modules")
        with patch.dict(os.environ, {"SystemRoot":r"C:\Windows", "PSModulePath":inherited}):
            with patch.object(pairing_client.subprocess, "run") as run:
                pairing_client._run_windows_powershell(["-Command", "Get-Acl"], timeout=10)
            self.assertEqual(os.environ["PSModulePath"], inherited)
        args, options = run.call_args
        self.assertEqual(args[0], [str(ps_home / "powershell.exe"),
                                  "-NoProfile", "-NonInteractive", "-Command", "Get-Acl"])
        module_paths = [value for key, value in options["env"].items() if key.upper() == "PSMODULEPATH"]
        self.assertEqual(module_paths, [str(ps_home / "Modules")])
        self.assertEqual(options["timeout"], 10)


if __name__ == "__main__":
    unittest.main()
