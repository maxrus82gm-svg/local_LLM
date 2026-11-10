"""Admin-side pairing lifecycle without contacting models or opening ports."""
from pathlib import Path
import hashlib
import tempfile
from types import SimpleNamespace as Args
import unittest
from unittest.mock import patch

from live_manager import load_config
from pairing_server import create, grant, revoke


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class PairingServerTests(unittest.TestCase):
    def setUp(self):
        # Isolated temp directories are deliberately not production ACL-secured.
        # The ACL gate is checked separately on the actual protected server path.
        self.enterContext(patch("pairing_server._require_private_acl"))
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        private = root / "private"
        private.mkdir()
        engine = root / "Colibri"
        engine.mkdir()
        models = root / "Models"
        models.mkdir()
        cert = private / "server.pem"
        key = private / "server-key.pem"
        cert.write_text("TEST CERT; NOT REAL", encoding="utf-8")
        key.write_text("TEST KEY; NOT REAL", encoding="utf-8")
        self.config = private / "manager.json"
        self.args = Args(config=self.config, manager_id="srv-1", name="Server 1",
                         bind="127.0.0.1", port=18443,
                         colibri_root=engine, models_root=models,
                         cert=cert, key=key,
                         slot=["slot1:8000:protected", "slot2:8001"],
                         allow_ip=["127.0.0.1"],
                         client_id="client-a", token_sha256=digest("example" * 8),
                         grant_slot=["slot1"])

    def test_create_and_read_client_permissions(self):
        create(self.args)
        loaded = load_config(self.config)
        self.assertEqual(loaded["allowed_client_ips"], ["127.0.0.1"])
        self.assertEqual(loaded["clients"][0]["allowed_slots"], ["slot1"])
        self.assertTrue(loaded["slots"][0]["protected"])
        with self.assertRaises(FileExistsError):
            create(self.args)

    def test_grant_and_revoke_apply_without_shared_token(self):
        create(self.args)
        client_b = Args(config=self.config, client_id="client-b",
                        token_sha256=digest("different" * 8), grant_slot=["slot2"])
        grant(client_b)
        loaded = load_config(self.config)
        self.assertEqual(len(loaded["clients"]), 2)
        revoke(Args(config=self.config, client_id="client-a"))
        clients = load_config(self.config)["clients"]
        self.assertEqual([c["client_id"] for c in clients], ["client-b"])
        with self.assertRaises(ValueError):
            revoke(Args(config=self.config, client_id="client-b"))

    def test_wrong_slot_refuses_config_change(self):
        create(self.args)
        prior = self.config.read_bytes()
        with self.assertRaises(ValueError):
            grant(Args(config=self.config, client_id="client-x",
                       token_sha256=digest("another" * 8),
                       grant_slot=["not-a-slot"]))
        self.assertEqual(self.config.read_bytes(), prior)

    def test_reject_insecure_incomplete_allowlist(self):
        self.args.allow_ip = ["0.0.0.0"]
        # Security check may be extended in the host; currently explicit
        # normalized addresses are mandatory (wildcard is forbidden here).
        with self.assertRaises(ValueError):
            create(self.args)


if __name__ == "__main__":
    unittest.main()
