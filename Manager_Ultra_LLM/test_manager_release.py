"""Release isolation, legacy configuration and hostile package tests; no LIVE."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import manager_release as release
from live_manager import load_config
from control_runtime import ModelControl, ControlError


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.result = release.build(Path(release.__file__).parent, self.root / "bundle", "QA-base")
        self.archive = Path(self.result["zip"])

    def test_deterministic_archive_and_relocated_imports(self):
        second = release.build(Path(release.__file__).parent, self.root / "other", "QA-base")
        self.assertEqual(self.result["zip_sha256"], second["zip_sha256"])
        stage = self.root / "staged path with spaces"
        release.stage(self.archive, stage)
        import subprocess, sys
        result = subprocess.run([sys.executable, "-B", "-I", "-c",
            "import sys;sys.path.insert(0,sys.argv[1]);import live_manager,pairing_workflow,control_runtime;print('IMPORT_OK')",
            str(stage)], capture_output=True, timeout=20, check=True)
        self.assertIn(b"IMPORT_OK", result.stdout)

    def test_modified_payload_is_refused_before_staging(self):
        (self.root / "bundle/live_manager.py").write_text("# altered", encoding="utf-8")
        with self.assertRaises(ValueError):
            release.stage(self.root / "bundle", self.root / "should not exist")
        self.assertFalse((self.root / "should not exist").exists())

    def test_unknown_file_including_private_config_is_refused(self):
        (self.root / "bundle/manager.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError):
            release.read_package(self.root / "bundle")

    def test_existing_destination_is_untouched(self):
        target = self.root / "existing"
        target.mkdir()
        sentinel = target / "user data"
        sentinel.write_bytes(b"retain")
        with self.assertRaises(ValueError):
            release.stage(self.archive, target)
        self.assertEqual(sentinel.read_bytes(), b"retain")

    def test_traversal_duplicate_and_link_archive_refused(self):
        for mode in ("traversal", "duplicate", "link"):
            payload = release.read_package(self.archive)
            bad = self.root / (mode + ".zip")
            with zipfile.ZipFile(bad, "w") as archive:
                for name, data in payload.items():
                    item = zipfile.ZipInfo(name)
                    if mode == "link" and name == "live_manager.py":
                        item.external_attr = 0o120777 << 16
                    archive.writestr(item, data)
                if mode == "traversal":
                    archive.writestr("../escape", b"bad")
                elif mode == "duplicate":
                    import warnings
                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr("live_manager.py", b"bad")
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                release.stage(bad, self.root / (mode + "-target"))
            self.assertFalse((self.root / (mode + "-target")).exists())

    def test_junction_destination_ancestor_refused(self):
        if os.name != "nt":
            self.skipTest("Windows junction gate")
        import subprocess
        real, link = self.root / "real", self.root / "junction"
        real.mkdir()
        subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(link), str(real)],
                       check=True, capture_output=True, timeout=5)
        try:
            with self.assertRaises(ValueError):
                release.stage(self.archive, link / "child")
            self.assertFalse((real / "child").exists())
        finally:
            # Remove only this known junction itself, never its target recursively.
            link.rmdir()


class LegacyConfigurationTests(unittest.TestCase):
    def test_legacy_config_bytes_auth_and_disabled_control_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = {"manager_id": "legacy", "display_name": "Legacy Manager",
                   "colibri_root": str(root / "Colibri"), "models_root": str(root / "Models"),
                   "cert_file": str(root / "cert.pem"), "key_file": str(root / "key.pem"),
                   "bind_host": "127.0.0.1", "listen_port": 18443,
                   "allowed_client_ips": ["127.0.0.1"],
                   "clients": [{"client_id": "existing", "sha256": "a" * 64,
                                "allowed_slots": ["slot1"], "pairing_admin": False}]}
            config_file = root / "legacy.json"
            original = json.dumps(old).encode("utf-8")
            config_file.write_bytes(original)
            with patch("subprocess.run", side_effect=AssertionError("no process/telemetry")):
                loaded = load_config(config_file)
                controller = ModelControl(loaded)
                principal = loaded["clients"][0]
                self.assertFalse(controller.catalog(principal)["enabled"])
                self.assertIsNone(controller.db_path)
                with self.assertRaisesRegex(ControlError, "control_models_required"):
                    controller.handle(principal, {"op": "check"})
                # Adding client rights alone must still NOT bypass owner's gate.
                with self.assertRaisesRegex(ControlError, "owner_go_required"):
                    controller.handle({**principal, "control_models": True}, {"op": "check"})
            self.assertEqual(config_file.read_bytes(), original)
            self.assertEqual(loaded["clients"], old["clients"])
            self.assertEqual([s["slot_id"] for s in loaded["slots"]], ["slot1", "slot2", "slot3"])
            self.assertEqual(list(root.iterdir()), [config_file])


if __name__ == "__main__":
    unittest.main()
