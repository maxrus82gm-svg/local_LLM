"""Read-only old Client; all new profiles/runtime checks remain inside this workspace."""
from pathlib import Path
import hashlib, json, os, subprocess, time
from urllib.request import build_opener, ProxyHandler, Request

ROOT = Path(__file__).resolve().parents[3]
REPORT = Path(__file__).resolve().parent
QA = ROOT / "Test/ClientMigration_20261112"
PAYLOAD = QA / "R5"
PRIVATE = QA / "AppData/UltraLLM/Client"
TEMP = QA / "Temp"
TEMP.mkdir(exist_ok=True)
env = {k:v for k,v in os.environ.items() if k.upper() not in ("PYTHONPATH", "PYTHONHOME")}
env.update(PYTHONDONTWRITEBYTECODE="1", LOCALAPPDATA=str(QA / "AppData"),
           TEMP=str(TEMP), TMP=str(TEMP), TMPDIR=str(TEMP))
command = ["py", "-3.12", "-B", "-m", "unittest", "discover", "-s", "Client_Ultra_LLM", "-p", "test_*.py", "-v"]
unit = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, timeout=180)
(REPORT / "unittest.stdout.txt").write_bytes(unit.stdout)
(REPORT / "unittest.stderr.txt").write_bytes(unit.stderr)
assert unit.returncode == 0, "Client source tests failed; stop before packaged startup"
opener = build_opener(ProxyHandler({}))
process = None
url = None

def get(path):
    with opener.open(url + path, timeout=5) as r:
        return r.status, r.read(), r.headers

def stop_owned():
    assert process is not None and process.poll() is None
    csrf = json.loads(get("/api/session")[1])["csrf"]
    with opener.open(Request(url + "/api/shutdown", data=b"{}", headers={
            "Origin": url, "X-Ultra-CSRF": csrf, "Content-Type": "application/json"}), timeout=5) as r:
        assert json.loads(r.read())["stopping"]
    process.wait(timeout=15)
    assert process.returncode == 0

try:
    assert not PRIVATE.exists(), "Never reuse a real or previous profile"
    observations = []
    for cycle in range(2):
        cmd = [str(PAYLOAD / "UltraLLMClient.exe"), "--no-browser"]
        process = subprocess.Popen(cmd, cwd=QA, env=env, creationflags=subprocess.CREATE_NO_WINDOW)
        for _ in range(200):
            assert process.poll() is None, "Packaged client exited before ready"
            try:
                port = int((PRIVATE / ".web-client.port").read_text())
                assert port != 60720
                url = f"http://127.0.0.1:{port}"
                if json.loads(get("/api/config")[1])["configured"] is False:
                    break
            except (OSError, ValueError):
                pass
            time.sleep(.1)
        else:
            raise RuntimeError("Isolated Client readiness timeout")
        assert json.loads(get("/api/status")[1]) == {"configured": False, "managers": []}
        for route, source in [("/", "index.html"), ("/client.css", "client.css"), ("/client.js", "client.js")]:
            status, body, headers = get(route)
            assert status == 200 and len(body) > 100
            assert hashlib.sha256(body).digest() == hashlib.sha256((PAYLOAD / "_internal/web_assets" / source).read_bytes()).digest()
        for _ in range(2):
            duplicate = subprocess.run(cmd, cwd=QA, env=env, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
            assert duplicate.returncode == 0 and process.poll() is None
            assert int((PRIVATE / ".web-client.port").read_text()) == port
        observations.append({"cycle": cycle + 1, "pid": process.pid, "port": port,
                             "configured": False, "managers": 0, "repeat_launches": 2})
        stop_owned()
        assert not (PRIVATE / ".web-client.port").exists()
    result = {"status": "PASS", "source_unit_command": command, "source_unit_exit": unit.returncode,
              "packaged_exe": str(PAYLOAD / "UltraLLMClient.exe"), "profile": str(PRIVATE),
              "cycles": observations, "graceful_shutdowns": 2, "actual_manager_requests": 0,
              "old_client_shutdown": False, "browser_visual": "NOT RUN", "VBS_execution": "NOT RUN"}
    (REPORT / "isolated_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
finally:
    if process and process.poll() is None and url:
        stop_owned()
