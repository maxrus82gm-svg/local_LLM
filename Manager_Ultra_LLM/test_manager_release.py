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
    def rewrite_consistent(self, suffix):
        """Adversarial fixture: hashes agree, so dependency validation is exercised."""
        payload = release.read_package(self.archive)
        payload['live_manager.py'] += suffix.encode()
        meta = json.loads(payload['RELEASE.json'])
        meta['files'] = {name: release.sha(payload[name]) for name in release.RUNTIME}
        payload['RELEASE.json'] = release.canonical(meta)
        payload['SHA256SUMS.txt'] = ''.join(
            f'{release.sha(payload[name])}  {name}\n'
            for name in sorted((*release.RUNTIME, 'RELEASE.json'))).encode('ascii')
        return payload

    def test_missing_member_and_same_count_replacement_are_refused(self):
        for replacement in (None, '../escape', '..\\escape', 'manager.json'):
            payload = release.read_package(self.archive)
            removed = payload.pop('index.html')
            if replacement is not None:
                payload[replacement] = removed
            target = self.root / ('stage-' + str(len(list(self.root.iterdir()))))
            bad = self.root / (target.name + '.zip')
            with zipfile.ZipFile(bad, 'w') as archive:
                for name, data in payload.items():
                    archive.writestr(name, data)
            with self.subTest(replacement=replacement), self.assertRaisesRegex(ValueError, 'Unsafe archive members'):
                release.stage(bad, target)
            self.assertFalse(target.exists())
            self.assertFalse((self.root / 'escape').exists())

    def test_metadata_and_checksum_only_tampering_are_refused(self):
        for name in ('RELEASE.json', 'SHA256SUMS.txt'):
            payload = release.read_package(self.archive)
            payload[name] += b'changed'
            # Specific decoding/checksum rejection; unrelated exceptions must fail.
            with self.subTest(name=name), self.assertRaises((ValueError, json.JSONDecodeError)):
                release.validate(payload)

    def test_consistent_manifest_does_not_hide_missing_static_dependency(self):
        payload = self.rewrite_consistent('\ndef lazy():\n    import qa_unavailable_dependency\n')
        with self.assertRaisesRegex(ValueError, 'Unpackaged/non-stdlib dependency'):
            release.validate(payload)

    def test_consistent_manifest_must_not_hide_missing_dynamic_dependency(self):
        # Acceptance requirement: currently exposes a production validator gap.
        payload = self.rewrite_consistent("\ndef lazy():\n    return __import__('qa_unavailable_dependency')\n")
        with self.assertRaisesRegex(ValueError, 'Unpackaged/non-stdlib dependency'):
            release.validate(payload)

    def test_literal_importlib_and_builtin_aliases_reject_missing_dependencies(self):
        for statement in (
            "import importlib; importlib.import_module('qa_unavailable_dependency')",
            "import importlib.util; importlib.import_module('qa_unavailable_dependency')",
            "import importlib as il; il.import_module(name='qa_unavailable_dependency')",
            "from importlib import import_module as load; load('qa_unavailable_dependency')",
            "import builtins as bi; bi.__import__('qa_unavailable_dependency')",
            "from builtins import __import__ as load; load('qa_unavailable_dependency')",
        ):
            with self.subTest(statement=statement), self.assertRaisesRegex(ValueError, 'Unpackaged/non-stdlib dependency'):
                release.validate(self.rewrite_consistent('\n' + statement + '\n'))

    def test_unknown_relative_or_escaped_dynamic_imports_fail_closed(self):
        for statement in (
            "__import__(module_name)", "__import__('j' + 'son')",
            "import importlib; importlib.import_module(module_name)",
            "import importlib; importlib.import_module('.child', 'live_manager')",
            "__import__('json', level=1)", "__import__('json', level=unknown)",
            "__import__(**options)", "__import__('json', **options)",
            "loader = __import__", "import importlib; loader = importlib.import_module",
            "from importlib import *", "from . import child",
        ):
            with self.subTest(statement=statement), self.assertRaisesRegex(ValueError, 'Dynamic[/ ]'):
                release.validate(self.rewrite_consistent('\n' + statement + '\n'))

    def test_constant_stdlib_and_flat_local_imports_are_allowed_without_execution(self):
        statement = '''
import importlib as il
from importlib import import_module as load
import builtins as bi
__import__('json')
__import__(name='chat_runtime')
il.import_module('xml.etree.ElementTree')
load('chat_settings')
bi.__import__('pathlib')
raise RuntimeError('PAYLOAD MUST NEVER EXECUTE')
'''
        # A top-level raise would fail immediately if validation executed payload.
        payload = self.rewrite_consistent(statement)
        self.assertEqual(release.validate(payload)['version'], release.VERSION)

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
