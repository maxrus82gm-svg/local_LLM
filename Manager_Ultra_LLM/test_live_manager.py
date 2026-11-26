"""Safety regression for live Manager: no model start/stop and no network bind."""
import hashlib
import unittest
from unittest.mock import patch
import live_manager as live

CFG = {"manager_id": "server-1", "display_name": "Test Host",
       "models_root": "C:/nonexistent", "slots": [
           {"slot_id": "slot1", "api_port": 8000, "protected": True},
           {"slot_id": "slot2", "api_port": 8001, "protected": False}]}
MEM = {"total_gib": 48.0, "free_gib": 30.0,
       "listeners": [{"port": 8000, "pid": 17}]}


class LiveSecurityTests(unittest.TestCase):
    def test_native_snapshot_performance_identity_and_cancel(self):
        import threading
        cancel = threading.Event()
        listener = (17, "legacy-" + "a"*32)
        binding = ("slot1", cancel, "b"*32, listener)
        health = {"status": "ok", "scheduler": {"active": 1, "queued": 0},
                  "live": [{"state": "writing", "tok_s_now": 12.5, "tok_s": 10}]}
        with patch.object(live, "_chat_listener", return_value=listener):
            sample = live._snapshot_performance(health, binding, 8000, listener)
            self.assertEqual(sample, {"instance_id": "b"*32, "source": "engine_health",
                                      "current_tok_s": 12.5, "request_mean_tok_s": 10})
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, None))
            self.assertIsNone(live._snapshot_performance(
                {**health, "scheduler": {"active": 2, "queued": 0}}, binding, 8000, listener))
            cancel.set()
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, listener))
        cancel.clear()
        with patch.object(live, "_chat_listener", return_value=(18, "legacy-"+"c"*32)):
            self.assertIsNone(live._snapshot_performance(health, binding, 8000, listener))

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_snapshot_performance_respects_slot_grant(self, local, os_query, dirs):
        import threading
        listener = (17, "legacy-"+"a"*32)
        binding = ("slot1", threading.Event(), "b"*32, listener)
        local.side_effect = lambda port, path: (
            {"status":"ok","scheduler":{"active":1,"queued":0,"capacity":1},
             "live":[{"state":"writing","tok_s_now":9.0,"tok_s":8.0}]}
            if path == "/health" else {"data":[{"id":"model-A"}]})
        with patch.object(live, "_chat_listener", return_value=listener):
            allowed = live.live_snapshot(CFG, {"client_id":"c","allowed_slots":["slot1"]},
                                         performance_bindings={"slot1":binding})
            denied = live.live_snapshot(CFG, {"client_id":"c","allowed_slots":[]},
                                        performance_bindings={"slot1":binding})
        self.assertEqual(allowed["slots"][0]["live_performance"]["current_tok_s"],9.0)
        self.assertNotIn("live_performance",denied["slots"][0])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_ready_requires_trustworthy_scheduler(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok"} if path == "/health" else
            {"data": [{"id": "verified_model"}]})
        client = {"client_id": "client1", "allowed_slots": ["slot1"]}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["slots"][0]["engine_state"], "ready")
        self.assertEqual(result["slots"][0]["availability"], "unknown")
        self.assertFalse(result["reservation_granted"])
        self.assertFalse(result["admission_enabled"])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_ready_unreserved_is_not_a_lease(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok", "scheduler": {"active": 0, "queued": 0, "capacity": 1}}
            if path == "/health" else {"data": [{"id": "verified_model"}]})
        client = {"client_id": "client1", "allowed_slots": ["slot1"]}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["slots"][0]["availability"], "ready_unreserved")
        self.assertFalse(result["slots"][0]["reservation_granted"])

    @patch.object(live, "_inventory_models", return_value=[{"directory_name": "sensitive"}])
    @patch.object(live, "_os_telemetry", return_value=MEM)
    @patch.object(live, "_local_api_json")
    def test_unpermitted_client_cannot_read_slot_details(self, local, os_query, model_dirs):
        local.side_effect = lambda port, path: (
            {"status": "ok", "scheduler": {"active": 0, "queued": 0, "capacity": 1}}
            if path == "/health" else {"data": [{"id": "model-A"}]})
        client = {"client_id": "blocked", "allowed_slots": []}
        result = live.live_snapshot(CFG, client)
        self.assertEqual(result["models"], [])
        for row in result["slots"]:
            self.assertEqual(row["availability"], "denied")
            self.assertIsNone(row["pid"])
            self.assertEqual(row["models"], [])
            self.assertIsNone(row["scheduler"])

    @patch.object(live, "_inventory_models", return_value=[])
    @patch.object(live, "_local_api_json", return_value=None)
    def test_snapshot_shows_verified_optional_ddr_and_installed_capacity(self, api, dirs):
        evidence = dict(MEM, ddr_generation="DDR4", installed_gib=48.0)
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertEqual(result["memory"]["ddr_generation"], "DDR4")
        self.assertEqual(result["memory"]["installed_gib"], 48.0)
        self.assertEqual(result["memory"]["free_gib"], 30.0)
        evidence["ddr_generation"] = "UNKNOWN"
        evidence["installed_gib"] = 0
        with patch.object(live, "_os_telemetry", return_value=evidence):
            result = live.live_snapshot(CFG, {"client_id": "c", "allowed_slots": ["slot1"]})
        self.assertNotIn("ddr_generation", result["memory"])
        self.assertNotIn("installed_gib", result["memory"])

    def test_regular_telemetry_native_and_hardware_probe_cached(self):
        import subprocess
        from unittest.mock import Mock
        native = Mock()
        native.memory.return_value = {"total_gib": 48, "free_gib": 30}
        native.listeners.return_value = [{"port": 8000, "pid": 17}, {"port": 9999, "pid": 99}]
        completed = Mock(returncode=0, stdout='{"ddr_generation":"DDR4","installed_gib":48}')
        with patch.object(live, "_HARDWARE_RAM_CACHE", None), \
                patch("windows_process.NativeWindows", return_value=native), \
                patch.object(live.subprocess, "run", return_value=completed) as run, \
                patch.object(subprocess, "CREATE_NO_WINDOW", 0x08000000, create=True):
            for _ in range(4):
                data = live._os_telemetry([8000])
                self.assertEqual(data["listeners"], [{"port": 8000, "pid": 17}])
                self.assertEqual(data["ddr_generation"], "DDR4")
            self.assertEqual(native.memory.call_count, 4)
            self.assertEqual(native.listeners.call_count, 4)
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs["creationflags"], 0x08000000)

    def test_failed_optional_hardware_probe_is_not_repeated(self):
        with patch.object(live, "_HARDWARE_RAM_CACHE", None), \
                patch.object(live.subprocess, "run", side_effect=OSError("unavailable")) as run:
            self.assertEqual(live._hardware_ram(), {})
            self.assertEqual(live._hardware_ram(), {})
            run.assert_called_once()

    def test_native_gpu_aggregation_and_unknown_counters(self):
        import resource_policy as resources
        samples = [("dedicated_gib", "pid_42_luid_a", 2**30),
                   ("dedicated_gib", "pid_42_luid_b", 2**29),
                   ("shared_gib", "pid_42_luid_a", 2**28),
                   ("shared_gib", "pid_43_luid_a", None),
                   ("shared_gib", "pid_43_luid_b", 2**30),
                   ("dedicated_gib", "pid_44_luid_a", 0),
                   ("dedicated_gib", "not_a_pid", 2**30)]
        with patch.object(resources, "_pdh_gpu_samples", return_value=samples), \
                patch.object(live.subprocess, "run") as run:
            self.assertEqual(resources.process_gpu_memory(),
                             {42: {"dedicated_gib": 1.5, "shared_gib": 0.25},
                              44: {"dedicated_gib": 0}})
            run.assert_not_called()
        with patch.object(resources, "_pdh_gpu_samples", side_effect=OSError):
            self.assertEqual(resources.process_gpu_memory(), {})

    def test_token_digest_and_missing_bearer_fail_closed(self):
        token = "SAMPLE-UNIT-TEST-ONLY-xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
        conf = {"clients": [{"client_id": "alice",
                             "sha256": hashlib.sha256(token.encode()).hexdigest(),
                             "allowed_slots": ["slot1"]}]}
        self.assertIsNone(live._authorized_client(conf, ""))
        self.assertIsNone(live._authorized_client(conf, "Bearer wrong"))
        self.assertEqual(live._authorized_client(conf, "Bearer " + token)["client_id"],
                         "alice")


    def test_vpn_schema_exact_peer_and_separate_identity(self):
        from copy import deepcopy
        from pathlib import Path
        cfg = {"bind_host": "127.0.0.1", "cert_file": str(Path("local.cert").absolute()),
               "key_file": str(Path("local.key").absolute())}
        client = {"client_id":"local", "sha256":"a"*64}
        vpn = {"enabled":True,"bind_host":"10.7.0.3","source_ip":"10.7.0.2",
               "cert_file":str(Path("vpn.cert").absolute()),"key_file":str(Path("vpn.key").absolute()),
               "client":{"client_id":"vpn","sha256":"b"*64,"allowed_slots":["slot1"],
                         "control_models":True}}
        cfg["vpn_listener"]=vpn
        live.validate_vpn(cfg, {"slot1"}, [client])
        for field,value in (("bind_host","0.0.0.0"),("bind_host","8.8.8.8"),
                            ("bind_host","127.0.0.1"),("bind_host","10.7.0.2"),
                            ("source_ip","10.7.0.0/24"),("source_ip","127.0.0.1"),
                            ("enabled",1),("cert_file",cfg["cert_file"])):
            bad=deepcopy(cfg)
            bad["vpn_listener"][field]=value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                live.validate_vpn(bad, {"slot1"}, [client])
        for field,value in (("client_id","local"),("sha256","a"*64),
                            ("allowed_slots",["slot9"]),("control_models",1),
                            ("pairing_admin",True)):
            bad=deepcopy(cfg)
            bad["vpn_listener"]["client"][field]=value
            with self.subTest(field=field), self.assertRaises(ValueError):
                live.validate_vpn(bad, {"slot1"}, [client])
        self.assertIsNone(live.vpn_request_config(cfg,vpn,"10.7.0.4"))
        current=live.vpn_request_config(cfg,vpn,"10.7.0.2")
        self.assertEqual(current["clients"][0]["client_id"],"vpn")
        self.assertFalse(current["clients"][0]["pairing_admin"])
        changed=deepcopy(cfg);changed["vpn_listener"]["enabled"]=False
        self.assertIsNone(live.vpn_request_config(changed,vpn,"10.7.0.2"))
        self.assertIsNone(live.vpn_request_config(cfg,None,"10.7.0.2"))

    def test_vpn_tls_rejects_wrong_san(self):
        from pathlib import Path
        from unittest.mock import Mock, MagicMock
        vpn={"bind_host":"10.7.0.3","cert_file":"cert","key_file":"key"}
        cert,key=MagicMock(spec=Path),MagicMock(spec=Path)
        cert.resolve.return_value=Path("cert")
        key.resolve.return_value=Path("key")
        cert.__str__=Mock(return_value="cert")
        key.__str__=Mock(return_value="key")
        key.stat.return_value.st_mode=0o600
        with patch("pairing_server._trusted_parent"), \
             patch.object(live,"_vpn_private_file",side_effect=[cert,key]), \
             patch.object(live.subprocess,"run",return_value=Mock(returncode=0)), \
             patch.object(live.ssl._ssl,"_test_decode_cert",
                          return_value={"subjectAltName":[("IP Address","127.0.0.1")]}):
            with self.assertRaisesRegex(ValueError,"SAN"):
                live.vpn_tls_context(vpn,Path("manager.json"))



    def test_vpn_save_preserves_primary_and_requires_expected_state(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config=root/"manager.json"
            primary={"manager_id":"server-test","display_name":"Server",
                "bind_host":"127.0.0.1","listen_port":18443,
                "cert_file":str(root/"primary.cert"),"key_file":str(root/"primary.key"),
                "colibri_root":str(root/"engine"),"models_root":str(root/"models"),
                "slots":[{"slot_id":"slot1","api_port":8000}],
                "allowed_client_ips":["127.0.0.1"],"clients":[{"client_id":"local",
                    "sha256":"a"*64,"allowed_slots":["slot1"],"control_models":True}]}
            config.write_text(json.dumps(primary),encoding="utf-8")
            original=config.read_bytes()
            vpn={"enabled":True,"bind_host":"10.7.0.3","source_ip":"10.7.0.2",
                 "cert_file":str(root/"vpn.cert"),"key_file":str(root/"vpn.key"),
                 "client":{"client_id":"vpn","sha256":"b"*64,
                           "allowed_slots":["slot1"],"control_models":False}}
            with patch("pairing_server._require_private_acl"), \
                 patch.object(live,"vpn_tls_context") as tls:
                live.save_vpn_settings(config,None,vpn)
                tls.assert_called_once_with(vpn,config)
                current=live.load_config(config)
                self.assertEqual(current.pop("vpn_listener"),vpn)
                self.assertEqual(current,primary)
                backups=list(root.glob("manager.pre-vpn-*.json"))
                self.assertEqual(len(backups),1)
                self.assertEqual(backups[0].read_bytes(),original)
                before=config.read_bytes()
                with self.assertRaisesRegex(ValueError,"changed"):
                    live.save_vpn_settings(config,None,vpn)
                self.assertEqual(config.read_bytes(),before)
                self.assertEqual(list(root.glob("manager.pre-vpn-*.json")),backups)
                disabled={**vpn,"enabled":False}
                live.save_vpn_settings(config,vpn,disabled)
                current=live.load_config(config)
                self.assertEqual(current.pop("vpn_listener"),disabled)
                self.assertEqual(current,primary)
                tls.assert_called_once_with(vpn,config)
                self.assertEqual(len(list(root.glob("manager.pre-vpn-*.json"))),2)

    def test_process_inventory_timeout_save_is_independent(self):
        import json
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            config=root/"manager.json"
            primary={"manager_id":"server-test","display_name":"Server",
                "bind_host":"127.0.0.1","listen_port":18443,
                "cert_file":str(root/"primary.cert"),"key_file":str(root/"primary.key"),
                "colibri_root":str(root/"engine"),"models_root":str(root/"models"),
                "slots":[{"slot_id":"slot1","api_port":8000}],
                "allowed_client_ips":["127.0.0.1"],"clients":[{"client_id":"local",
                    "sha256":"a"*64,"allowed_slots":["slot1"],"control_models":True}]}
            config.write_text(json.dumps(primary),encoding="utf-8")
            original=config.read_bytes()
            with patch("pairing_server._require_private_acl"):
                live.save_process_inventory_timeout(config,None,60)
                self.assertEqual(live.load_config(config),{**primary,"process_inventory_timeout_seconds":60})
                backup=list(root.glob("manager.pre-timeout-*.json"))
                self.assertEqual(len(backup),1)
                self.assertEqual(backup[0].read_bytes(),original)
                before=config.read_bytes()
                with self.assertRaises(ValueError):
                    live.save_process_inventory_timeout(config,None,30)
                with self.assertRaises(ValueError):
                    live.save_process_inventory_timeout(config,60,4)
                self.assertEqual(config.read_bytes(),before)
                self.assertEqual(list(root.glob("manager.pre-timeout-*.json")),backup)

    def test_vpn_rejects_wrong_tcp_peer_before_tls(self):
        from unittest.mock import Mock
        server=object.__new__(live.VPNManagerHTTPServer)
        server.vpn_listener={"source_ip":"10.7.0.2"}
        server.tls_context=Mock()
        connection=Mock()
        with patch.object(live.ShortTimeoutManagerHTTPServer,"get_request",
                          return_value=(connection,("10.7.0.4",12345))):
            with self.assertRaises(PermissionError):
                server.get_request()
        connection.close.assert_called_once()
        server.tls_context.wrap_socket.assert_not_called()


    def test_vpn_socket_real_tls_and_certificate_verification(self):
        # Temporary synthetic key, no real Manager, Windows service or LLM.
        import os
        import shutil
        import ssl
        import socket
        import subprocess
        import tempfile
        import threading
        from http.server import BaseHTTPRequestHandler
        from pathlib import Path
        openssl=shutil.which("openssl")
        if not openssl and os.name=="nt":
            candidate=Path(os.environ.get("ProgramFiles",r"C:\Program Files"))/"Git/usr/bin/openssl.exe"
            openssl=str(candidate) if candidate.is_file() else None
        if not openssl:
            self.skipTest("OpenSSL executable unavailable for ephemeral real TLS fixture")
        with tempfile.TemporaryDirectory() as folder:
            cert,key=Path(folder)/"cert.pem",Path(folder)/"key.pem"
            subprocess.run([openssl,"req","-x509","-newkey","rsa:2048","-nodes",
                    "-sha256","-days","1","-subj","/CN=127.0.0.1",
                    "-addext","subjectAltName=IP:127.0.0.1",
                    "-addext","extendedKeyUsage=serverAuth",
                    "-addext","basicConstraints=critical,CA:FALSE",
                    "-keyout",str(key),"-out",str(cert)],
                    check=True,timeout=30,capture_output=True)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version=ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(str(cert),str(key))
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.send_header("Content-Length","2")
                    self.end_headers()
                    self.wfile.write(b"OK")
                def log_message(self,*args):
                    pass
            server=live.VPNManagerHTTPServer(("127.0.0.1",0),Handler,
                                             {"source_ip":"127.0.0.1"},context)
            thread=threading.Thread(target=server.serve_forever,daemon=True)
            thread.start()
            try:
                address=server.server_address
                trusted=ssl.create_default_context(cafile=str(cert))
                with socket.create_connection(address,timeout=4) as raw:
                    with trusted.wrap_socket(raw,server_hostname="127.0.0.1") as tls:
                        tls.sendall(b"GET / HTTP/1.0\r\nHost: localhost\r\n\r\n")
                        self.assertIn(b"200",tls.recv(4096))
                with socket.create_connection(address,timeout=4) as raw:
                    with self.assertRaises(ssl.SSLCertVerificationError):
                        trusted.wrap_socket(raw,server_hostname="10.7.0.3")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(3)

if __name__ == "__main__":
    unittest.main()
