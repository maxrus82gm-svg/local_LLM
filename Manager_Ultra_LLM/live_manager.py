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
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import re
import socket
import ssl
import subprocess
import threading
import urllib.error
import urllib.request

from pairing_inbox import PairingInbox

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
    if not isinstance(bind, str):
        raise ValueError("Explicit IP bind_host required")
    try:
        ip = ipaddress.ip_address(bind)
    except ValueError as error:
        raise ValueError("bind_host must be a numeric interface IP") from error
    if (ip.is_unspecified or ip.is_multicast or ip.is_link_local
            or not (ip.is_private or ip.is_loopback)):
        raise ValueError("Only explicit private/loopback binds allowed at LAN stage")
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
    allowed_ips = raw.get("allowed_client_ips")
    if not isinstance(allowed_ips, list) or not allowed_ips:
        raise ValueError("Explicit allowlist of client IPs required")
    normalized = []
    for address in allowed_ips:
        if not isinstance(address, str):
            raise ValueError("Invalid client IP")
        try:
            addr = ipaddress.ip_address(address)
        except ValueError as error:
            raise ValueError("Client allowlist must contain literal IP addresses") from error
        if (addr.is_unspecified or addr.is_multicast or addr.is_link_local
                or not (addr.is_private or addr.is_loopback)):
            raise ValueError("Only explicitly allowed private/loopback client IPs")
        normalized.append(str(addr))
    if len(set(normalized)) != len(normalized):
        raise ValueError("Duplicate allowed client IP")
    raw["allowed_client_ips"] = normalized
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
        if type(client.get("pairing_admin", False)) is not bool:
            raise ValueError("Invalid pairing_admin role")
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
              "pairing_admin": bool(client.get("pairing_admin", False)),
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
                    if row["scheduler"] is None or row["scheduler"]["capacity"] == 0:
                        row["availability"] = "unknown"
                    elif (row["scheduler"]["active"] >= row["scheduler"]["capacity"]
                          or row["scheduler"]["queued"] > 0):
                        row["availability"] = "busy"
                    else:
                        row["availability"] = "ready_unreserved"
            if allowed and isinstance(models, dict) and isinstance(models.get("data"), list):
                row["models"] = [
                    str(m["id"])[:128] for m in models["data"][:30]
                    if isinstance(m, dict) and isinstance(m.get("id"), str)]
        if not allowed:
            # An unauthorised viewer gets no PID, model details or live scheduler.
            row.update(pid=None, models=[], scheduler=None)
        result["slots"].append(row)
    # Never disclose model catalog paths to clients lacking any slot grant.
    if not client["allowed_slots"]:
        result["models"] = []
    return result


def make_handler(config_file, config, inbox):
    """HTTP handler; live role checks are repeated on every request."""
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
        def _current(self):
            # Reload grants on EVERY request: revoke/rotate without a restart.
            # Never trust client-provided identity or X-Forwarded-For.
            try:
                current = load_config(config_file)
                if any(current[field] != config[field] for field in
                       ("manager_id", "bind_host", "listen_port",
                        "cert_file", "key_file")):
                    self._reply(503, {"error": "manager_config_changed"})
                    return None
            except (OSError, ValueError, TypeError):
                self._reply(503, {"error": "configuration_unavailable"})
                return None
            if self.client_address[0] not in current["allowed_client_ips"]:
                self._reply(403, {"error": "source_not_permitted"})
                return None
            return current

        def _admin(self, current):
            client = _authorized_client(current, self.headers.get("Authorization", ""))
            if client is None:
                self._reply(401, {"error": "unauthorized"})
                return False
            if not client.get("pairing_admin", False):
                self._reply(403, {"error": "pairing_admin_required"})
                return False
            return True

        def _json_post(self):
            if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                self._reply(415, {"error": "json_required"})
                return None
            try:
                n = int(self.headers.get("Content-Length", "0"))
                if not 0 < n <= 4096:
                    raise ValueError()
                payload = json.loads(self.rfile.read(n))
                if not isinstance(payload, dict):
                    raise ValueError()
                return payload
            except (ValueError, UnicodeDecodeError):
                self._reply(400, {"error": "invalid_json_body"})
                return None

        def do_GET(self):
            current = self._current()
            if current is None:
                return
            if self.path == "/v1/snapshot":
                client = _authorized_client(current, self.headers.get("Authorization", ""))
                if client is None:
                    return self._reply(401, {"error": "unauthorized"})
                if not _MAX_REQUESTS.acquire(blocking=False):
                    return self._reply(503, {"error": "busy"})
                try:
                    self._reply(200, live_snapshot(current, client))
                except Exception as error:
                    _LOG.exception("Snapshot failed: %s", type(error).__name__)
                    self._reply(503, {"error": "temporarily_unavailable"})
                finally:
                    _MAX_REQUESTS.release()
                return
            if self.path == "/v1/pairing/requests":
                if not self._admin(current):
                    return
                from pairing_workflow import request_summary
                result = request_summary(current)
                result["requests"] = inbox.pending()
                return self._reply(200, result)
            if self.path.startswith("/v1/pairing/status/"):
                ticket = self.path[len("/v1/pairing/status/"):]
                try:
                    result = inbox.status(ticket, self.client_address[0])
                except ValueError:
                    return self._reply(400, {"error": "invalid_ticket"})
                return self._reply(200, result)
            return self._reply(404, {"error": "not_found"})

        def do_POST(self):
            current = self._current()
            if current is None:
                return
            if self.path not in ("/v1/pairing/request",
                                 "/v1/pairing/approve",
                                 "/v1/pairing/deny"):
                return self._reply(405, {"error": "read_only_stage"})
            if self.path != "/v1/pairing/request" and not self._admin(current):
                return
            body = self._json_post()
            if body is None:
                return
            if self.path == "/v1/pairing/request":
                if set(body) != {"client_id", "token_sha256"}:
                    return self._reply(400, {"error": "invalid_fields"})
                try:
                    ids = {x["client_id"] for x in current["clients"]}
                    response = inbox.submit(body, self.client_address[0], ids)
                    return self._reply(202, response)
                except OverflowError:
                    return self._reply(429, {"error": "pairing_rate_limited"})
                except ValueError:
                    return self._reply(400, {"error": "invalid_pairing_request"})
            if self.path == "/v1/pairing/approve":
                if set(body) != {"ticket_id", "allowed_slots"}:
                    return self._reply(400, {"error": "invalid_fields"})
                from pairing_workflow import grant_pending
                try:
                    response = inbox.approve(
                        body["ticket_id"], body["allowed_slots"],
                        lambda cid, digest, ip, allowed: grant_pending(
                            config_file, cid, digest, ip, allowed))
                    return self._reply(200, response)
                except (ValueError, PermissionError, OSError) as error:
                    _LOG.warning("Pairing approval refused: %s", type(error).__name__)
                    return self._reply(409, {"error": "grant_not_applied"})
            if set(body) != {"ticket_id"}:
                return self._reply(400, {"error": "invalid_fields"})
            try:
                return self._reply(200, inbox.deny(body["ticket_id"]))
            except ValueError:
                return self._reply(409, {"error": "not_pending"})
        def log_message(self, fmt, *args):
            # Never log URL paths/query strings or auth headers: they may
            # inadvertently contain secrets, even for rejected requests.
            _LOG.info("HTTPS request from %s", self.client_address[0])

    return Handler


class ShortTimeoutManagerHTTPServer(ThreadingHTTPServer):
    """Bound slow request clients; do not let unauthenticated pairing hang."""
    request_queue_size = 16

    def get_request(self):
        connection, address = super().get_request()
        connection.settimeout(8)
        return connection, address


def run(config_file):
    config = load_config(config_file)
    inbox = PairingInbox()
    handler = make_handler(config_file, config, inbox)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(config["cert_file"], config["key_file"])
    server = ShortTimeoutManagerHTTPServer(
        (config["bind_host"], config["listen_port"]), handler)
    server.daemon_threads = True
    server.socket = context.wrap_socket(server.socket, server_side=True)
    _LOG.info("Manager %s listening securely at %s:%d",
              config["manager_id"], config["bind_host"], config["listen_port"])
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--log-dir", type=Path,
                        help="Existing ACL-protected directory outside Git")
    parser.add_argument("--check-config", action="store_true",
                        help="Validate the configuration without binding a port")
    args = parser.parse_args()
    log_handlers = []
    if args.log_dir:
        log_dir = args.log_dir
        if (not log_dir.is_absolute() or not log_dir.is_dir() or
                log_dir.is_symlink()):
            parser.error("--log-dir must be an existing absolute directory")
        log_handlers.append(RotatingFileHandler(
            log_dir / "manager.log", maxBytes=2 * 1024 * 1024,
            backupCount=3, encoding="utf-8"))
    if not log_handlers:
        log_handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        handlers=log_handlers)
    if args.check_config:
        config = load_config(args.config)
        if not Path(config["cert_file"]).is_file() or not Path(config["key_file"]).is_file():
            parser.error("Missing TLS certificate or key")
        print("MANAGER_CONFIGURATION_OK")
    else:
        run(args.config)
