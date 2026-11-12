"""WEB-03 client tests: dummy fixed values; no real credentials or network."""
from pathlib import Path
import hashlib
import json
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import pairing_live

DUMMY_TOKEN = "FIXTURE-ONLY-NOT-A-REAL-TOKEN-NO-ACCESS-TO-ANY-SERVER"


class PairingClientLiveTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.folder = Path(tmp.name)
        self.fake_profile = {
            "manager_id":"manager-test",
            "client_id":"client-test",
            "endpoint":"https://127.0.0.1:18443",
            "ca_cert":self.folder/"fake-public.pem",
            "token_file":MagicMock()
        }
        self.fake_profile["token_file"].read_text.return_value = DUMMY_TOKEN
        self.profiles=patch("pairing_live.find_profile",return_value=self.fake_profile)
        self.profiles.start()
        self.addCleanup(self.profiles.stop)

    def test_submit_uses_hash_not_raw_token_and_keeps_receipt_private(self):
        ticket = "abcdefghijklmnopqrstuvwxyz012345"
        with patch("pairing_live._api",return_value={"ticket_id":ticket,"state":"pending"}) as api:
            result = pairing_live.submit_profile(self.folder,"manager-test")
        self.assertEqual(result["state"],"pending")
        args=api.call_args.args
        self.assertEqual(args[1:3],("POST","/v1/pairing/request"))
        sent=args[3]
        self.assertEqual(sent["client_id"],"client-test")
        self.assertEqual(sent["token_sha256"],
                         hashlib.sha256(DUMMY_TOKEN.encode()).hexdigest())
        self.assertNotIn(DUMMY_TOKEN,json.dumps(sent))
        receipt=(self.folder/"manager-test.pairing-receipt.json").read_text()
        self.assertNotIn(DUMMY_TOKEN,receipt)
        self.assertNotIn(sent["token_sha256"],receipt)

    def test_waiting_status_is_checked_without_bearer(self):
        ticket="abcdefghijklmnopqrstuvwxyz012345"
        (self.folder/"manager-test.pairing-receipt.json").write_text(
            json.dumps({"ticket_id":ticket}),encoding="utf-8")
        with patch("pairing_live._api",return_value={"state":"approved"}) as api:
            state=pairing_live.check_profile_ticket(self.folder,"manager-test")
        self.assertEqual(state,"approved")
        self.assertEqual(api.call_args.args[1],"GET")
        self.assertIn(ticket,api.call_args.args[2])
        self.assertFalse(api.call_args.kwargs.get("authorized",False))

    def test_invalid_receipt_refused_without_network(self):
        (self.folder/"manager-test.pairing-receipt.json").write_text(
            '{"ticket_id":"invalid?"}',encoding="utf-8")
        with patch("pairing_live._api") as api:
            self.assertIsNone(pairing_live.check_profile_ticket(self.folder,"manager-test"))
        api.assert_not_called()

    def test_administrator_actions_pass_through_verified_transport(self):
        with patch("pairing_live._api",return_value={"manager_id":"manager-test",
                   "requests":[]}) as api:
            pairing_live.admin_requests(self.folder,"manager-test")
        self.assertTrue(api.call_args.kwargs["authorized"])
        ticket="abcdefghijklmnopqrstuvwxyz012345"
        with patch("pairing_live._api",return_value={"state":"approved"}) as api:
            result=pairing_live.admin_decision(
                self.folder,"manager-test",ticket,["slot2"],approve=True)
        self.assertEqual(result["state"],"approved")
        self.assertTrue(api.call_args.kwargs["authorized"])
        self.assertEqual(api.call_args.args[3]["allowed_slots"],["slot2"])
        with patch("pairing_live._api",return_value={"state":"denied"}) as api:
            pairing_live.admin_decision(self.folder,"manager-test",ticket,approve=False)
        self.assertTrue(api.call_args.kwargs["authorized"])

    def test_pairing_rejects_invalid_receipt(self):
        with patch("pairing_live._api",return_value={"ticket_id":"short",
                                                   "state":"pending"}):
            with self.assertRaises(pairing_live.PairingRequestError):
                pairing_live.submit_profile(self.folder,"manager-test")
        self.assertFalse((self.folder/"manager-test.pairing-receipt.json").exists())

    def test_browser_never_gets_bearer_token_from_admin_transport(self):
        with patch("pairing_live._api",return_value={"manager_id":"manager-test",
                    "requests":[{"client_id":"waiting","source_ip":"127.0.0.1"}]}) as api:
            result=pairing_live.admin_requests(self.folder,"manager-test")
        self.assertNotIn(DUMMY_TOKEN,json.dumps(result))
        self.assertTrue(api.call_args.kwargs["authorized"])


if __name__=="__main__":
    unittest.main()
