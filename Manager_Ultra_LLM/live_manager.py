"""Ultra LLM Manager live read-only HTTPS host (Windows, stdlib only).

Live inventory is read from THIS machine, not from mock fixtures or SMB.
The daemon does not launch/stop models. Model directories are unverified until
Colibri itself reports an active model; no resource reservations are granted.
Security: TLS + per-client bearer-token hash + bounded read-only endpoints.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
from pathlib import Path
import re
import socket
import ssl
import subprocess
import threading
import urllib.error
import urllib.request

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_LOG = logging.getLogger("ultra-live-manager")
_POWERSHELL = r"powershell.exe"
_API_TIMEOUT = 2
_OS_TIMEOUT = 8
_MAX_REQUESTS = threading.BoundedSemaphore(4)


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read_json(path: Path):
    with path.open("r", encoding="utf-8-sig") as stream:
        return json.load(stream)


def _text_id(value, field):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ValueError("Invalid " + field)
    return value


def load_config(file: Path):
    raw = _read_json(file)
    if not isinstance(raw, dict):
        raise ValueError("Invalid config")
    _text_id(raw.get("manager_id"), "manager_id")
    name = raw.get("display_name")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
        raise ValueError("Invalid display_name")
    for field in ("colibri_root", "models_root", "cert_file", "key_file"):
        value = raw.get(field)
        if not isinstance(value, str) or not Path(value).is_absolute():
            raise ValueError("Missing absolute " + field)
    bind = raw.get("bind_host")
    if not isinstance(bind, str) or not bind or bind in ("0.0.0.0", "::"):
        raise ValueError("Explicit LAN bind_host required, no wildcard")
    port = raw.get("listen_port")
    if type(port) is not int or not (1024 <= port <= 65535):
        raise ValueError("Invalid listen_port")
    slots = raw.get("slots")
    if not isinstance(slots, list) or not slots:
        raise ValueError("No slots")
    ids, ports = set(), set()
    for slot in slots:
        if not isinstance(slot, dict):
            raise ValueError("Invalid slot")
        _text_id(slot.get("slot_id"), "slot_id")
        n = slot.get("api_port")
        if type(n) is not int or not 1024 <= n <= 65535:
            raise ValueError("Invalid API port")
        if slot["slot_id"] in ids or n in ports or n == port:
            raise ValueError("Duplicate slot/port")
        ids.add(slot["slot_id"])
        ports.add(n)
    clients = raw.get("clients")
    if not isinstance(clients, list) or not clients:
        raise ValueError("No client credentials")
    client_ids, token_hashes = set(), set()
    for client in clients:
        if not isinstance(client, dict):
            raise ValueError("Invalid client")
        _text_id(client.get("client_id"), "client_id")
        digest = client.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError("Invalid client token digest")
        if client["client_id"] in client_ids or digest in token_hashes:
            raise ValueError("Repeated client")
        client_ids.add(client["client_id"])
        token_hashes.add(digest)
        allowed = client.get("allowed_slots")
        if not isinstance(allowed, list) or any(x not in ids for x in allowed):
            raise ValueError("Invalid client access list")
    return raw


def _os_telemetry(ports):
    # Only validated integer ports are substituted. Never accepts input from HTTP.
    safe = ",".join(str(x) for x in sorted(set(ports)))
    script = (r"$ErrorActionPreference='Stop';" +
              r"$os=Get-CimInstance Win32_OperatingSystem -ErrorAction Stop;" +
              r"$list=@(Get-NetTCPConnection -State Listen -ErrorAction Stop | " +
              r"Where-Object {$_.LocalPort -in @(" + safe + r")});" +
              r"[pscustomobject]@{total_gib=[double]$os.TotalVisibleMemorySize/1048576;" +
              r"free_gib=[double]$os.FreePhysicalMemory/1048576;" +
              r"listeners=@($list|ForEach-Object{" +
              r"[pscustomobject]@{port=[int]$_.LocalPort;pid=[int]$_.OwningProcess;" +
              r"address=[string]$_.LocalAddress}})} | ConvertTo-Json -Compress -Depth 4")
    cmd = [_POWERSHELL, "-NoProfile", "-NonInteractive",
           "-EncodedCommand", __import__("base64").b64encode(
               script.encode("utf-16le")).decode("ascii")]
    result = subprocess.run(cmd, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", timeout=_OS_TIMEOUT)
    if result.returncode:
        raise RuntimeError("Windows telemetry query failed")
    data = json.loads(result.stdout.strip())
    if not isinstance(data, dict) or not isinstance(data.get("listeners"), list):
        raise RuntimeError("Windows telemetry incomplete")
    return data


def _local_api_json(port, path):
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", headers={"Accept": "application/json"})
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(request, timeout=_API_TIMEOUT) as response:
            if response.status != 200:
                return None
            data = response.read(256 * 1024)
        return json.loads(data)
    except (OSError, TimeoutError, ValueError, urllib.error.URLError):
        return None


def _inventory_models(models_root):
    root = Path(models_root)
    if not root.is_dir():
        return []
    out = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.is_symlink() or len(out) >= 100:
            continue
        # Directory presence does not prove completed downloads or compatibility.
        metadata = any(x.is_file() for x in child.glob("*.gguf")) or any(
            x.is_file() for x in child.glob("*.colibri/config.json"))
        out.append({"directory_name": child.name[:128],
                    "evidence": "files_present_unverified",
                    "metadata_detected": bool(metadata)})
    return out


def _authorized_client(config, authorization):
    if not authorization.startswith("Bearer ") or len(authorization) > 256:
        return None
    token = authorization[7:]
    if len(token) < 32:
        return None
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    selected = None
    for client in config["clients"]:
        if hmac.compare_digest(digest, client["sha256"]):
            selected = client
    return selected


def live_snapshot(config, client):
    slots = config["slots"]
    result = {"schema": "ultra.manager.live.v1", "source": "LIVE_HOST",
              "manager_id": config["manager_id"],
              "display_name": config["display_name"],
              "host": socket.gethostname(),
              "generated_at_utc": _utc_now(),
              "viewer_id": client["client_id"],
              "admission_enabled": False,
              "reservation_granted": False,
              "memory": {"state": "unknown"},
              "slots": [],
              "models": _inventory_models(config["models_root"])}
    try:
        evidence = _os_telemetry([s["api_port"] for s in slots])
        result["memory"] = {"state": "live",
                            "total_gib": round(float(evidence["total_gib"]), 2),
                            "free_gib": round(float(evidence["free_gib"]), 2)}
        listening = {int(s["port"]): int(s["pid"])
                     for s in evidence["listeners"]
                     if isinstance(s, dict) and isinstance(s.get("port"), int)
                     and isinstance(s.get("pid"), int)}
    except (RuntimeError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        _LOG.warning("Host telemetry unavailable: %s", type(error).__name__)
        listening = {}
    for slot in slots:
        slot_id = slot["slot_id"]
        port = slot["api_port"]
        allowed = slot_id in client["allowed_slots"]
        row = {"slot_id": slot_id, "api_port": port,
               "protected": bool(slot.get("protected", False)),
               "pid": listening.get(port),
               "engine_state": "unknown",
               "models": [],
               "scheduler": None,
               "availability": "denied" if not allowed else "unknown",
               "reservation_granted": False}
        if result["memory"]["state"] == "live" and port not in listening:
            row["engine_state"] = "not_running"
            if allowed:
                row["availability"] = "not_running"
        elif port in listening:
            health = _local_api_json(port, "/health")
            models = _local_api_json(port, "/v1/models")
            if isinstance(health, dict) and health.get("status") == "ok":
                row["engine_state"] = "ready"
                queue = health.get("scheduler")
                if isinstance(queue, dict):
                    vals = [queue.get(k) for k in ("active", "queued", "capacity")]
                    if all(type(x) is int and x >= 0 for x in vals):
                        row["scheduler"] = dict(zip(("active", "queued", "capacity"), vals))
                if allowed:
                    if row["scheduler"] and (
                            row["scheduler"]["active"] >= row["scheduler"]["capacity"]
                            or row["scheduler"]["queued"] > 0):
                        row["availability"] = "busy"
                    else:
                        row["availability"] = "ready_unreserved"
            if isinstance(models, dict) and isinstance(models.get("data"), list):
                row["models"] = [
                    str(m["id"])[:128] for m in models["data"][:30]
                    if isinstance(m, dict) and isinstance(m.get("id"), str)]
        result["slots"].append(row)
    return result


def run(config_file):
    config = load_config(config_file)
    class Handler(BaseHTTPRequestHandler):
        server_version = "UltraLLMManager/1.0"
        sys_version = ""
        def _reply(self, status, payload):
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(encoded)
        def do_GET(self):
            if self.path != "/v1/snapshot":
                return self._reply(404, {"error": "not_found"})
            client = _authorized_client(config, self.headers.get("Authorization", ""))
            if client is None:
                return self._reply(401, {"error": "unauthorized"})
            if not _MAX_REQUESTS.acquire(blocking=False):
                return self._reply(503, {"error": "busy"})
            try:
                self._reply(200, live_snapshot(config, client))
            except Exception as error:
                _LOG.exception("Snapshot failed: %s", type(error).__name__)
                self._reply(503, {"error": "temporarily_unavailable"})
            finally:
                _MAX_REQUESTS.release()
        def do_POST(self):
            self._reply(405, {"error": "read_only_stage"})
        def log_message(self, fmt, *args):
            # Never log auth headers or credentials.
            _LOG.info("%s %s", self.client_address[0], fmt % args)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config["cert_file"], config["key_file"])
    server = ThreadingHTTPServer((config["bind_host"], config["listen_port"]), Handler)
    server.daemon_threads = True
    server.socket = context.wrap_socket(server.socket, server_side=True)
    _LOG.info("Manager %s listening securely at %s:%d",
              config["manager_id"], config["bind_host"], config["listen_port"])
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    run(args.config)
