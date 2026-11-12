"""Isolated browser check for CHAT-UI, never connects to live Manager."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import json
import subprocess
import tempfile
import threading

assets = Path(r"M:\GitHub\local_LLM_GPT_docs\Client_Ultra_LLM\web_assets")
payload = {"configured":True,"managers":[{
    "manager_id":"mock-server77","name":"Ultra LLM Server 77","status":"online",
    "data":{"host":"mock-host","memory":{"state":"live","ddr_generation":"DDR4",
        "installed_gib":48,"free_gib":34.8,"total_gib":47.94},
        "slots":[
            {"slot_id":"slot1","engine_state":"ready","availability":"ready_unreserved",
              "models":["qwen3.6-35b-a3b-colibri"]},
            {"slot_id":"slot2","engine_state":"not_running","availability":"not_running","models":[]},
            {"slot_id":"slot3","engine_state":"not_running","availability":"not_running","models":[]}
        ],
        "models":[{"directory_name":"KAT-Coder-V2.5-Dev-Colibri"},
                  {"directory_name":"Qwen3.6-35B-A3B-UD-Q4_K_M"}]}}]}

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        p=self.path.split("?",1)[0]
        if p=="/": data=(assets/"index.html").read_bytes();mime="text/html; charset=utf-8"
        elif p=="/client.js":data=(assets/"client.js").read_bytes();mime="text/javascript; charset=utf-8"
        elif p=="/client.css":data=(assets/"client.css").read_bytes();mime="text/css; charset=utf-8"
        elif p=="/api/status":data=json.dumps(payload).encode();mime="application/json"
        elif p=="/api/config":data=b'{"configured":true}';mime="application/json"
        elif p=="/api/session":data=b'{"csrf":"test"}';mime="application/json"
        else:self.send_error(404);return
        self.send_response(200);self.send_header("Content-Type",mime)
        self.send_header("Content-Length",str(len(data)));self.end_headers();self.wfile.write(data)
    def log_message(self,*args):pass

server=ThreadingHTTPServer(("127.0.0.1",0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
try:
    with tempfile.TemporaryDirectory() as td:
        chrome=r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        proc=subprocess.run([chrome,"--headless=new","--disable-gpu","--no-first-run",
           f"--user-data-dir={td}","--virtual-time-budget=4000","--dump-dom",
           f"http://127.0.0.1:{server.server_port}/"],capture_output=True,
           text=True,encoding="utf-8",errors="replace",timeout=35)
        dom=proc.stdout
        assert proc.returncode==0, "Chrome failed"
        checks={
           "3 models in one Manager card":dom.count('class="manager-model-row"')==3,
           "CPU actions in each model":dom.count('>Старт CPU</button>')==3,
           "CUDA actions in each model":dom.count('>Старт CUDA</button>')==3,
           "STOP actions in each model":dom.count('>Стоп</button>')==3,
           "All action buttons disabled":dom.count('class="btn secondary small manager-model-action"')==9 and dom.count('disabled=""')>=9,
           "DDR4 shown":'DDR4 · Установлено 48.0 GiB · Свободно 34.8 GiB' in dom,
           "Single Manager card":dom.count('class="manager"')==1,
           "Old duplicate slot table removed":'id="slot-table"' not in dom,
           "Old global RAM metric removed":'id="metric-ram"' not in dom,
           "Ready status visible":'Работает · slot1' in dom,
           "Disk model marked unverified":'совместимость и запуск не проверены' in dom
        }
        for k,v in checks.items():print(("PASS" if v else "FAIL")+" | "+k)
        print("CHROME_EXIT",proc.returncode)
        assert all(checks.values()),"Browser test failed"
finally:
    server.shutdown();server.server_close();thread.join(timeout=2)
