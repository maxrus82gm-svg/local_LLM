"""Local HTTP protocol verification with synthetic values; NOT a live TLS test."""
from http.server import ThreadingHTTPServer
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, ProxyHandler, build_opener

from live_manager import load_config, make_handler
from pairing_inbox import PairingInbox

ADMIN_MARKER = "TEST-ADMIN-ONLY-NOT-A-REAL-CREDENTIAL-0000000001"
VIEWER_MARKER = "TEST-VIEWER-ONLY-NOT-A-REAL-CREDENTIAL-000000001"


class PairingProtocolTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        private = root / "private"
        private.mkdir()
        for d in ("colibri", "models"):
            (root / d).mkdir()
        self.config_file = private / "manager.json"
        config = {
            "manager_id":"srv-test", "display_name":"QA Manager",
            "bind_host":"127.0.0.1", "listen_port":18443,
            "colibri_root":str(root / "colibri"),
            "models_root":str(root / "models"),
            "cert_file":str(private / "dummy-cert.pem"),
            "key_file":str(private / "dummy-key.pem"),
            "slots":[{"slot_id":"slot1","api_port":18000,"protected":True},
                     {"slot_id":"slot2","api_port":18001,"protected":False}],
            "allowed_client_ips":["127.0.0.1"],
            "clients":[
                {"client_id":"admin","sha256":hashlib.sha256(ADMIN_MARKER.encode()).hexdigest(),
                 "allowed_slots":["slot1"],"pairing_admin":True},
                {"client_id":"viewer","sha256":hashlib.sha256(VIEWER_MARKER.encode()).hexdigest(),
                 "allowed_slots":["slot2"]}
            ]
        }
        self.config_file.write_text(json.dumps(config),encoding="utf-8")
        self.acl = patch("pairing_server._require_private_acl")
        self.acl.start()
        self.addCleanup(self.acl.stop)
        self.inbox = PairingInbox()
        self.server = ThreadingHTTPServer(("127.0.0.1",0),
             make_handler(self.config_file, load_config(self.config_file), self.inbox))
        self.server.daemon_threads = True
        thread = threading.Thread(target=self.server.serve_forever,daemon=True)
        thread.start()
        # LIFO cleanup order: stop server, close socket, then join thread.
        self.addCleanup(lambda:thread.join(3))
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.opener=build_opener(ProxyHandler({}))
        self.root=f"http://127.0.0.1:{self.server.server_address[1]}"

    def req(self,path,method="GET",payload=None,token=None):
        headers = {}
        if token is not None:
            headers["Authorization"]="Bearer "+token
        body = json.dumps(payload).encode() if payload is not None else None
        if body is not None:
            headers["Content-Type"]="application/json"
        req = Request(self.root+path,method=method,data=body,headers=headers)
        try:
            with self.opener.open(req,timeout=5) as r:
                return r.status,json.loads(r.read())
        except HTTPError as e:
            return e.code,json.loads(e.read())

    def _new_request(self):
        status,data=self.req("/v1/pairing/request","POST",{
            "client_id":"client-new",
            "token_sha256":"d"*64})
        self.assertEqual(status,202)
        self.assertNotIn("d"*64,str(data))
        return data["ticket_id"]

    def test_admin_permission_and_explicit_slot_grant(self):
        ticket=self._new_request()
        code,_=self.req("/v1/pairing/requests")
        self.assertEqual(code,401)
        code,_=self.req("/v1/pairing/requests",token=VIEWER_MARKER)
        self.assertEqual(code,403)
        code,list_data=self.req("/v1/pairing/requests",token=ADMIN_MARKER)
        self.assertEqual(code,200)
        self.assertEqual(len(list_data["requests"]),1)
        self.assertNotIn("d"*64,str(list_data))
        code,_=self.req("/v1/pairing/approve","POST",{
            "ticket_id":ticket,"allowed_slots":["slot2"]})
        self.assertEqual(code,401)
        code,_=self.req("/v1/pairing/approve","POST",{
            "ticket_id":ticket,"allowed_slots":["slot2"]},token=VIEWER_MARKER)
        self.assertEqual(code,403)
        code,response=self.req("/v1/pairing/approve","POST",{
            "ticket_id":ticket,"allowed_slots":["slot2"]},token=ADMIN_MARKER)
        self.assertEqual(code,200)
        self.assertEqual(response["state"],"approved")
        clients=load_config(self.config_file)["clients"]
        self.assertEqual(clients[-1]["client_id"],"client-new")
        self.assertEqual(clients[-1]["allowed_slots"],["slot2"])
        self.assertFalse(clients[-1]["pairing_admin"])
        self.assertTrue(clients[0]["pairing_admin"])
        code,_=self.req("/v1/pairing/approve","POST",{
            "ticket_id":ticket,"allowed_slots":[]},token=ADMIN_MARKER)
        self.assertEqual(code,409)
        status,response=self.req("/v1/pairing/status/"+ticket)
        self.assertEqual(status,200)
        self.assertEqual(response["state"],"approved")

    def test_deny_never_changes_config(self):
        ticket=self._new_request()
        before=self.config_file.read_bytes()
        code,response=self.req("/v1/pairing/deny","POST",{
            "ticket_id":ticket},token=ADMIN_MARKER)
        self.assertEqual((code,response["state"]),(200,"denied"))
        self.assertEqual(self.config_file.read_bytes(),before)

    def test_invalid_request_and_rate_limit(self):
        code,_=self.req("/v1/pairing/request","POST",{
            "client_id":"other","token_sha256":"short"})
        self.assertEqual(code,400)
        self._new_request()
        code,_=self.req("/v1/pairing/request","POST",{
            "client_id":"client-three","token_sha256":"e"*64})
        self.assertEqual(code,429)

    def test_no_start_stop_regression(self):
        code,body=self.req("/v1/start","POST",{"slot_id":"slot1"},token=ADMIN_MARKER)
        self.assertEqual(code,405)
        self.assertEqual(body["error"],"read_only_stage")


if __name__=="__main__":
    unittest.main()
