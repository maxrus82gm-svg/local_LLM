"""Isolated SOURCE-chain browser fixture. Only fake models and temporary secrets.

No production profile, Manager or process is contacted. Invoked by the browser
test; all listeners use ephemeral loopback ports and close with this process.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import sys
import threading
import time
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "Manager_Ultra_LLM"))
import web_client
import live_manager
from pairing_inbox import PairingInbox


def main():
    root = Path(sys.argv[1]).resolve()
    root.mkdir(exist_ok=True)
    # OpenSSL is the existing Git distribution, never downloaded/installed.
    openssl = Path(r"C:\Program Files\Git\usr\bin\openssl.exe")
    cert, key = root / "qa-cert.pem", root / "qa-key.pem"
    subprocess.run([str(openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
        "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=127.0.0.1",
        "-addext", "subjectAltName=IP:127.0.0.1"], check=True, capture_output=True,
        creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    allow_answer, allow_done = threading.Event(), threading.Event()
    benchmark = threading.Event()
    received = []
    request_bodies = []
    reload_handler=[None]
    resource_memory=[64]
    normal_active=[0,0]
    normal_lock=threading.Lock()
    normal_pair=threading.Event()
    # Synthetic faults are claimed only by the browser request carrying their probe ID.
    status_faults={}
    status_fault_lock=threading.Lock()
    chat_ux = "--chat-ux" in sys.argv[2:]
    streaming_busy = threading.Event()
    release_until = [0.0]
    wave = threading.Event()
    class Colibri(BaseHTTPRequestHandler):
        model_id="qa-model"
        def do_GET(self):
            if self.path=="/__qa/reload":
                if reload_handler[0]:reload_handler[0]()
                self.send_response(204);self.end_headers();return
            if self.path.startswith("/__qa/status_fault/"):
                parts=self.path.split("/")
                if (len(parts)!=6 or parts[3] not in ("null", "partial", "503", "delay", "disconnect")
                        or not parts[4].isascii() or not parts[4].isdigit() or len(parts[4])>8
                        or not parts[5].isascii() or not parts[5].isdigit()
                        or not 1<=int(parts[5])<=32):
                    self.send_response(400);self.end_headers();return
                mode,probe,count=parts[3],parts[4],int(parts[5])
                with status_fault_lock:
                    if probe in status_faults:
                        self.send_response(409);self.end_headers();return
                    status_faults[probe]=[mode,count]
                self.send_response(204);self.end_headers();return
            if self.path in ("/__qa/low_ram","/__qa/normal_ram"):
                resource_memory[0]=8 if self.path.endswith('low_ram') else 64
                self.send_response(204);self.end_headers();return
            if self.path == "/__qa/benchmark":
                benchmark.set();allow_answer.set();allow_done.set();self.send_response(204);self.end_headers();return
            if self.path == "/__qa/answer":
                allow_answer.set(); self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/done":
                allow_done.set(); self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/wave" and chat_ux:
                wave.set(); self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/stop_model" and chat_ux:
                self.model_id = None
                type(self).model_id = None
                self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/change_model" and chat_ux:
                type(self).model_id = "qa-other"
                self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/manager_down" and chat_ux:
                manager.shutdown()
                manager.server_close()
                self.send_response(204); self.end_headers(); return
            if self.path == "/__qa/payload" and chat_ux:
                data = request_bodies[-1] if request_bodies else {}
            elif self.path == "/__qa/metrics":
                data={"requests":len(received),"generation_options":received[-1] if received else {},
                      "done_released":allow_done.is_set(),
                      "max_parallel_normal":normal_active[1],
                      "same_last_two_requests":len(request_bodies)>=2 and request_bodies[-1]==request_bodies[-2]}
            elif self.path == "/health":
                if self.model_id is None:
                    self.send_response(503); self.end_headers(); return
                busy = streaming_busy.is_set() or time.monotonic() < release_until[0]
                data={"status":"ok","context_tokens":32768,"max_tokens":8192,
                      "scheduler":{"active":int(busy),"queued":0,"capacity":1}}
            elif self.path == "/v1/models":
                data={"data":[{"id":self.model_id}] if self.model_id else []}
            else:
                self.send_response(404);self.end_headers();return
            encoded=json.dumps(data).encode()
            self.send_response(200);self.send_header("Content-Length",str(len(encoded)));self.end_headers();self.wfile.write(encoded)
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            received.append({k:v for k,v in body.items() if k not in ("messages","model")})
            request_bodies.append(body)
            marker = body["messages"][-1]["content"]
            if body.get("stream") is not True:
                with normal_lock:
                    normal_active[0]+=1;normal_active[1]=max(normal_active)
                    if normal_active[0]>=2:normal_pair.set()
                if control_fixture:normal_pair.wait(3)
                try:
                    reply = {"choices":[{"message":{"content":"Фиктивный ответ экземпляра", "reasoning_content":"Отдельное рассуждение"},"finish_reason":"stop"}]}
                    if marker != "qa-no-usage":
                        reply["usage"] = {"prompt_tokens":7,"completion_tokens":5}
                    raw=json.dumps(reply,ensure_ascii=False).encode()
                    self.send_response(200);self.send_header("Content-Type","application/json");self.send_header("Content-Length",str(len(raw)));self.end_headers();self.wfile.write(raw)
                finally:
                    with normal_lock:normal_active[0]-=1
                return
            self.send_response(200);self.send_header("Content-Type","text/event-stream");self.end_headers()
            def emit(delta, **extra):
                raw=("data: "+json.dumps({"model":self.model_id, "choices":[{"index":0,"delta":delta}],**extra},ensure_ascii=False)+"\n\n").encode()
                # Split JSON and multibyte UTF-8 at arbitrary byte boundaries.
                for start in range(0,len(raw),7):
                    self.wfile.write(raw[start:start+7]);self.wfile.flush()
            if chat_ux:
                streaming_busy.set()
                try:
                    emit({"reasoning_content":"Фрагмент рассуждения\n"*100 if marker == "qa-long" else "Фрагмент рассуждения"})
                    if marker == "qa-cancel":
                        for _ in range(300):
                            time.sleep(0.02)
                            emit({"reasoning_content":"."})
                    if marker == "qa-truncated":
                        return
                    if marker == "qa-long":
                        allow_answer.wait(20)
                        emit({"content":"Первая часть ответа\n"*100})
                        wave.wait(20)
                        emit({"content":"Вторая часть ответа\n"*100})
                        allow_done.wait(20)
                    else:
                        emit({"content":"Ответ " + marker})
                    release_until[0] = time.monotonic() + 1.45
                    prompt, completion = (31, 4) if marker == "qa-context" else (17, 8)
                    usage = {"choices": [], "usage": {"prompt_tokens": prompt, "completion_tokens": completion}}
                    self.wfile.write(("data: " + json.dumps(usage) + "\n\ndata: [DONE]\n\n").encode())
                    self.wfile.flush()
                except OSError:
                    pass
                finally:
                    streaming_busy.clear()
                return
            try:
                if benchmark.is_set():time.sleep(0.04)
                emit({"reasoning_content":"Отдельное рассуждение 🧠"})
                allow_answer.wait(30)
                if benchmark.is_set():time.sleep(0.04)
                emit({"content":"Первый фрагмент ответа 🌍"})
                allow_done.wait(30)
                if benchmark.is_set():time.sleep(0.04)
                emit({"content":" и завершение"})
                self.wfile.write(b'data: {"choices":[],"usage":{"prompt_tokens":7,"completion_tokens":5}}\n\ndata: [DONE]\n\n');self.wfile.flush()
            except OSError:
                pass
        def log_message(self,*args): pass
    servers=[]
    def serve(server):
        servers.append(server)
        server.daemon_threads=True
        threading.Thread(target=server.serve_forever,daemon=True).start()
        return server.server_address[1]
    upstream=ThreadingHTTPServer(("127.0.0.1",0),Colibri)
    upstream_port=serve(upstream)
    manager=ThreadingHTTPServer(("127.0.0.1",0),None)
    manager_port=manager.server_address[1]
    config={"manager_id":"qa-manager","display_name":"SOURCE Manager (fake model)",
        "bind_host":"127.0.0.1","listen_port":manager_port,"colibri_root":str(root),"models_root":str(root),
        "cert_file":str(cert),"key_file":str(key),"allowed_client_ips":["127.0.0.1"],
        "slots":[{"slot_id":"slot1","api_port":upstream_port,"protected":True}],
        "clients":[{"client_id":"qa-client","sha256":hashlib.sha256(b"QA-ONLY-NOT-A-PRODUCTION-TOKEN-123456789").hexdigest(),"allowed_slots":["slot1"]}]}
    ipv6=None
    control_fixture=len(sys.argv)>2 and sys.argv[2]=="--control"
    controller_factory=None
    if control_fixture:
        import socket
        from windows_process import NativeWindows
        from control_runtime import ModelControl
        from unittest.mock import patch
        taken={r["port"] for r in NativeWindows().listeners()}
        free=[p for p in range(38000,39000) if p not in taken]
        config["slots"] += [{"slot_id":"slot2","api_port":free[0]}, {"slot_id":"slot3","api_port":free[1]}]
        ipv6=socket.socket(socket.AF_INET6,socket.SOCK_STREAM);ipv6.bind(("::1",free[2]));ipv6.listen(1)
        config["clients"][0].update(control_models=True,allowed_slots=["slot1","slot2","slot3"])
        config["control"]={"owner_go":True,"host":socket.gethostname(),"state_dir":str(root),
            "instance_root":str(root/"instances"),"slot_port_range":[38000,38999],
            "resources":{"allow_risk_ack":True},
            "reviews":{k:{mode:{"evidence":"measured","source_hashes":{"fixture":"not-a-real-runtime"},
                                   "ram_gib":2,"vram_gib":2} for mode in ("cpu","cuda")} for k in ("kat","qwen36")}}
        class FakeBackend:
            instances={}
            def telemetry(self):
                return {"verified":True,"sampled":time.monotonic(),"free_gib":resource_memory[0],
                        "ports":[r["port"] for r in NativeWindows().listeners()],"vram_free_gib":32}
            def preflight(self,spec):pass
            def start(self,spec,identity):
                handler=type("InstanceColibri",(Colibri,),{"model_id":spec.api_id})
                server=ThreadingHTTPServer(("127.0.0.1",spec.port),handler)
                serve(server)
                self.instances[identity]=(server,True)
            def stop(self,spec,identity):
                server,active=self.instances[identity]
                server.shutdown();server.server_close();self.instances[identity]=(server,False)
            def status(self,spec,identity):
                row=self.instances.get(identity)
                return {"state":"READY" if row and row[1] else "STOPPED" if row else "ERROR", "released":bool(row and not row[1])}
        backend=FakeBackend()
        def controller_factory():
            with patch("pairing_server._require_private_acl"):
                return ModelControl(config,backend=backend)
    config_file=root/"manager.json";config_file.write_text(json.dumps(config))
    # Overview hardware is synthetic. Chat uses real native listener identities.
    live_manager._os_telemetry=lambda ports:{"total_gib":64,"free_gib":resource_memory[0],
        "listeners":[{"port":s.server_address[1],"pid":os.getpid()} for s in servers if s.fileno()>=0 and s.server_address[1] in ports]}
    def set_handler():
        manager.RequestHandlerClass=live_manager.make_handler(config_file,live_manager.load_config(config_file),PairingInbox(),
            controller=controller_factory() if controller_factory else None)
    set_handler()
    reload_handler[0]=set_handler
    tls=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);tls.load_cert_chain(cert,key)
    manager.socket=tls.wrap_socket(manager.socket,server_side=True)
    serve(manager)
    (root/"qa-token.txt").write_text("QA-ONLY-NOT-A-PRODUCTION-TOKEN-123456789",encoding="ascii")
    (root/"managers.json").write_text(json.dumps({"managers":[{"manager_id":"qa-manager","client_id":"qa-client",
        "display_name":"SOURCE Manager (fake model)","endpoint":f"https://127.0.0.1:{manager_port}",
        "ca_cert":"qa-cert.pem","token_file":"qa-token.txt"}]}))
    local=ThreadingHTTPServer(("127.0.0.1",0),None)
    local_port=local.server_address[1]
    base_local=web_client.make_handler(root,lambda:local_port,"QA-CSRF")
    class LocalQA(base_local):
        def do_GET(self):
            if self.path=="/api/status":
                probe=self.headers.get("X-QA-Status-Probe")
                mode=None
                if probe is not None:
                    with status_fault_lock:
                        fault=status_faults.get(probe)
                        if fault:
                            mode=fault[0]
                            fault[1]-=1
                            if fault[1]==0:del status_faults[probe]
                    if mode is None:
                        return self._send_json(409,{"error":"qa_probe_unarmed"})
                if mode=="delay":time.sleep(0.35)
                elif mode=="disconnect":
                    self.close_connection=True
                    try:self.connection.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
                    return
                elif mode=="503":return self._send_json(503,{"error":"synthetic_status_unavailable"})
                elif mode in ("null","partial"):
                    data=None if mode=="null" else {"control":None}
                    return self._send_json(200,{"configured":True,"managers":[{
                        "manager_id":"qa-manager","status":"unreachable" if mode=="null" else "online",
                        "data":data,"error":"connection_or_config_error" if mode=="null" else None}]})
            return super().do_GET()
    local.RequestHandlerClass=LocalQA
    serve(local)
    print(json.dumps({"url":f"http://127.0.0.1:{local_port}","upstream":f"http://127.0.0.1:{upstream_port}",
                      "manager":f"https://127.0.0.1:{manager_port}",
                      "ipv6_occupied_port":ipv6.getsockname()[1] if ipv6 else None}),flush=True)
    try:
        for line in sys.stdin:
            if line.strip()=="stop":break
            if line.strip()=="restart-client" and chat_ux:
                local.shutdown()
                local.server_close()
                servers.remove(local)
                class RestartableClient(ThreadingHTTPServer):
                    allow_reuse_address = True
                local = RestartableClient(("127.0.0.1",local_port), web_client.make_handler(root, lambda:local_port, "QA-CSRF"))
                serve(local)
                print("client-restarted", flush=True)
    finally:
        allow_answer.set();allow_done.set();wave.set()
        for server in reversed(servers):
            if server.fileno() >= 0:
                server.shutdown(); server.server_close()
        if ipv6:ipv6.close()


if __name__=="__main__":main()
