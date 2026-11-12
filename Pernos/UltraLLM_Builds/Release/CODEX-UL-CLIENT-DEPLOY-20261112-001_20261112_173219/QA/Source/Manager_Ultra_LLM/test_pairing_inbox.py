"""WEB-03 tests use only dummy digests and no real credentials or hosts."""
from pathlib import Path
from contextlib import nullcontext
import unittest
from unittest.mock import patch

from pairing_inbox import PairingInbox
from pairing_workflow import grant_pending


class PairingInboxTests(unittest.TestCase):
    def setUp(self):
        self.time = [100.]
        self.inbox = PairingInbox(clock=lambda: self.time[0], ttl=100, maximum=2)
        self.known = {"existing-client"}

    def submit(self, client, digest="b"*64, ip="127.0.0.1"):
        return self.inbox.submit({"client_id": client, "token_sha256": digest},
                                 ip, self.known)

    def test_receipt_does_not_disclose_verifier(self):
        receipt = self.submit("new-client")
        self.assertEqual(receipt["state"], "pending")
        self.assertNotIn("b"*64, str(receipt))
        requests = self.inbox.pending()
        self.assertEqual(requests[0]["client_id"], "new-client")
        self.assertEqual(requests[0]["source_ip"], "127.0.0.1")
        self.assertNotIn("b"*64, str(requests))
        self.assertEqual(self.inbox.status(receipt["ticket_id"], "127.0.0.1"),
                         {"state": "pending"})
        self.assertEqual(self.inbox.status(receipt["ticket_id"], "127.0.0.2"),
                         {"state": "unknown"})

    def test_requires_explicit_approval_callback(self):
        item = self.submit("new-client")
        calls = []
        def persist(client, digest, ip, slots):
            calls.append((client, digest, ip, slots))
        result = self.inbox.approve(item["ticket_id"], ["slot2"], persist)
        self.assertEqual(result, {"state": "approved", "client_id": "new-client"})
        self.assertEqual(calls, [("new-client", "b"*64, "127.0.0.1", ["slot2"])])
        self.assertFalse(self.inbox.pending())
        with self.assertRaises(ValueError):
            self.inbox.approve(item["ticket_id"], ["slot2"], persist)

    def test_failed_persistence_preserves_pending(self):
        item = self.submit("new-client")
        def fail(*_):
            raise PermissionError("ACL denied")
        with self.assertRaises(PermissionError):
            self.inbox.approve(item["ticket_id"], [], fail)
        self.assertEqual(self.inbox.status(item["ticket_id"], "127.0.0.1"),
                         {"state": "pending"})

    def test_expiration_and_deny(self):
        item = self.submit("new-client")
        self.inbox.deny(item["ticket_id"])
        self.assertEqual(self.inbox.status(item["ticket_id"], "127.0.0.1"),
                         {"state": "denied"})
        self.time[0] += 101
        other = self.submit("second-client", "c"*64)
        self.time[0] += 101
        self.assertEqual(self.inbox.status(other["ticket_id"], "127.0.0.1"),
                         {"state": "expired"})
        self.assertFalse(self.inbox.pending())

    def test_rate_capacity_and_identity(self):
        first = self.submit("new-client")
        with self.assertRaises(ValueError):
            self.submit("new-client", "c"*64)
        with self.assertRaises(ValueError):
            self.submit("existing-client", "c"*64)
        with self.assertRaises(OverflowError):
            self.submit("another", "c"*64)
        self.time[0] += 4
        self.submit("another", "c"*64)
        self.time[0] += 4
        with self.assertRaises(OverflowError):
            self.submit("third", "d"*64)
        self.assertTrue(first["ticket_id"])

    def test_rejects_invalid_values(self):
        for payload in ({"client_id":"bad/id", "token_sha256":"b"*64},
                        {"client_id":"good", "token_sha256":"short"},
                        {"client_id":"good", "token_sha256":"b"*64,"allowed_slots":["slot1"]}):
            if "allowed_slots" in payload:
                # The inbox ignores unexpected fields, HTTP layer rejects them.
                continue
            with self.assertRaises(ValueError):
                self.inbox.submit(payload, "127.0.0.1", self.known)


class PairingWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "manager_id":"srv-test",
            "slots":[{"slot_id":"slot1"},{"slot_id":"slot2"}],
            "allowed_client_ips":["127.0.0.1"],
            "clients":[{"client_id":"admin", "sha256":"a"*64,
                        "allowed_slots":["slot1"],"pairing_admin":True}]
        }
        self.written = []
        self.patch_lock = patch("pairing_workflow.manager_config_lock",
                                side_effect=lambda _: nullcontext())
        self.patch_lock.start()
        self.addCleanup(self.patch_lock.stop)
        self.patch_read = patch("pairing_workflow.load_config", return_value=self.record)
        self.patch_write = patch("pairing_workflow._write_config",
                                 side_effect=lambda path,data,new: self.written.append(data))
        self.patch_read.start()
        self.patch_write.start()
        self.addCleanup(self.patch_read.stop)
        self.addCleanup(self.patch_write.stop)

    def test_permission_preserves_existing_and_never_admins_new_client(self):
        grant_pending(Path("manager.json"), "new-client", "b"*64,
                      "127.0.0.1", ["slot2"])
        self.assertEqual(len(self.written),1)
        clients = self.written[0]["clients"]
        self.assertTrue(clients[0]["pairing_admin"])
        self.assertFalse(clients[1]["pairing_admin"])
        self.assertEqual(clients[1]["allowed_slots"],["slot2"])

    def test_source_ip_must_be_preapproved(self):
        with self.assertRaises(PermissionError):
            grant_pending(Path("manager.json"),"new-client","b"*64,
                          "192.168.0.99",["slot2"])
        self.assertFalse(self.written)

    def test_invalid_grant_is_fail_closed(self):
        for slots in (["unknown"],["slot1","slot1"]):
            with self.subTest(slots=slots), self.assertRaises(ValueError):
                grant_pending(Path("manager.json"),"new-client","b"*64,
                              "127.0.0.1",slots)
        self.assertFalse(self.written)


if __name__ == "__main__":
    unittest.main()
