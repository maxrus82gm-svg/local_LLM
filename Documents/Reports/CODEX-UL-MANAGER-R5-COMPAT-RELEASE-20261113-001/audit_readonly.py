"""Home-only read-only inventory. No secret/config/history contents are read.

Only public Manager source is copied into a NEW local backup directory.
Running Manager is queried via the installed Client's existing pinned TLS path.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from urllib.request import build_opener, ProxyHandler
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
TASK = OUT.name
sys.path.insert(0, str(ROOT / "Manager_Ultra_LLM"))
from manager_release import RUNTIME, sha


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT).decode("utf-8").strip()


def main():
    if socket.gethostname().upper() != "DESKTOP-SC96D3U":
        raise RuntimeError("Home PC required")
    result = {"task": TASK, "host": socket.gethostname(),
              "utc": datetime.now(timezone.utc).isoformat(),
              "scope": "READ ONLY remote/public code; GET via existing Client; no secret/history export",
              "branches": {b: git("log", "-1", "--format=%H %s", b) for b in ("main", "GPT_2_local")},
              "active_branch": git("branch", "--show-current"),
              "owner_git_amendment": "NO COMMIT/PUSH/PULL, local diff only"}
    ps = r'''$ps=@(Get-CimInstance Win32_Process -Filter "Name='UltraLLMClient.exe'");$ids=@($ps.ProcessId);[pscustomobject]@{processes=@($ps|Select-Object ProcessId,ParentProcessId,ExecutablePath,@{n='created_utc';e={$_.CreationDate.ToUniversalTime().ToString('o')}});listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -in $ids}|Select-Object LocalAddress,LocalPort,OwningProcess)}|ConvertTo-Json -Depth 5 -Compress'''
    found = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps],
                           check=True, capture_output=True, timeout=25)
    result["client"] = json.loads(found.stdout.decode("utf-8-sig"))
    opener = build_opener(ProxyHandler({}))
    expected = ROOT / "Production/Client/UltraLLMClient.exe"
    result["client"]["exe_sha256"] = sha(expected.read_bytes())
    procs = [p for p in result["client"]["processes"]
             if str(p["ExecutablePath"]).casefold() == str(expected).casefold()]
    if len(procs) == 1:
        ports = [p["LocalPort"] for p in result["client"]["listeners"]
                 if p["OwningProcess"] == procs[0]["ProcessId"] and p["LocalAddress"] == "127.0.0.1"]
        if len(ports) == 1:
            base = f"http://127.0.0.1:{ports[0]}"
            for route, key in (("/api/status", "status"),
                               ("/api/control/catalog?manager_id=manager-server77", "catalog_get")):
                try:
                    with opener.open(base + route, timeout=25) as response:
                        raw = json.load(response)
                    if key == "status":
                        rows = raw.get("managers", [])
                        result[key] = [{k: row[k] for k in ("manager_id", "status", "snapshot", "error") if k in row}
                                       for row in rows]
                    else:
                        result[key] = {"http": 200, "body": raw}
                except HTTPError as error:
                    result[key] = {"http": error.code, "body": error.read(1024).decode("utf-8", "replace")}
    remote = Path(r"\\192.168.0.77\Server\Ultra_LLM\Manager_Live")
    backup = ROOT / "Backups/Manager" / TASK / "public_code"
    result["server_public_root"] = str(remote)
    try:
        entries = list(remote.iterdir())
        result["server_top_level"] = [{"name": p.name, "kind": "directory" if p.is_dir() else "file"}
                                      for p in entries]
        files = [p for p in entries if p.is_file() and p.name in RUNTIME]
        if backup.exists():
            raise FileExistsError("Refuse to overwrite public backup")
        backup.mkdir(parents=True)
        hashes = {}
        for p in files:
            data = p.read_bytes()
            (backup / p.name).write_bytes(data)
            hashes[p.name] = sha(data)
        result["server_public_files"] = hashes
        result["backup"] = str(backup)
        live = (backup / "live_manager.py").read_text(encoding="utf-8-sig")
        result["server_source_routes"] = {route: route in live for route in (
            "/v1/control", "/v1/control/catalog", "/v1/chat", "/v1/chat/stream", "/v1/chat/cancel")}
        result["live_process_identity"] = "NOT VERIFIED remotely: SMB file hash is not running-process provenance"
    except OSError as error:
        result["server_public_audit"] = {"status": "NOT RUN", "error_type": type(error).__name__}
    # Existing task assignment and independent block are retained byte-for-byte.
    card = (ROOT / "Documents/07_Задачи Codex.md").read_bytes()
    text = card.decode("utf-8-sig")
    block4 = text[text.index("### БЛОК 4"):]
    result["card_before_sha256"] = sha(card)
    result["block4_sha256"] = sha(block4.encode("utf-8"))
    result["appearance_sha256"] = sha((ROOT / "Documents/.obsidian/appearance.json").read_bytes())
    (OUT / "baseline.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"saved": str(OUT / "baseline.json"), "server_files": len(result.get("server_public_files", {})),
                      "client_pid": [p["ProcessId"] for p in procs]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
