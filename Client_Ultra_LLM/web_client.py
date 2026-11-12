"""Ultra LLM Web Client P1: portable local-only browser UI and real HTTPS Manager data.

Security boundary:
- Browser accesses only 127.0.0.1 on an ephemeral port; no LAN HTTP service.
- Only this Python process reads Manager tokens. No secrets in JSON/HTML/JS.
- TLS to Managers is strictly verified via a pinned, user-provided CA file.
- New client credentials are made inside the user's protected profile directory.
- Administrator must still explicitly register the returned SHA-256 with Manager.
- Lifecycle actions are forwarded to Manager under its separate control role.
"""
from __future__ import annotations

import argparse
import ctypes
import time
from urllib.request import build_opener, ProxyHandler
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import ssl
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit
import webbrowser

from live_client import fetch_all, load_profiles
from pairing_client import _require_private_acl, enroll
from chat_client import ChatClientError, send_chat, stream_chat, control_request, cancel_chat
from chat_store import (validate_key, history as load_chat_history,
                        context_for, append_exchange, claim_request, fail_request)
from pairing_live import (PairingRequestError, submit_profile, check_profile_ticket,
                          admin_requests, admin_decision)

HERE = Path(__file__).resolve().parent
STATIC = HERE / "web_assets"
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
HOSTNAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.-]{0,251}$")
MAX_BODY = 1048576
_STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/client.css": ("client.css", "text/css; charset=utf-8"),
    "/client.js": ("client.js", "application/javascript; charset=utf-8"),
}
PROFILE_LOCK = threading.RLock()


def config_directory() -> Path:
    if os.name != "nt":
        return Path.home() / ".config" / "UltraLLM" / "Client"
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA is unavailable")
    return Path(base) / "UltraLLM" / "Client"


def ensure_private_dir(folder: Path) -> Path:
    folder = folder.expanduser().absolute()
    if folder.is_symlink():
        raise PermissionError("Credential directory cannot be a symlink")
    if not folder.exists():
        if os.name == "nt":
            installer = HERE / "Prepare-ClientPrivate.ps1"
            ps = Path(os.environ.get("SystemRoot") or
                      os.environ.get("WINDIR") or r"C:\Windows") / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
            cmd = [str(ps), "-NoProfile", "-NonInteractive",
                   "-ExecutionPolicy", "Bypass", "-File", str(installer)]
            result = subprocess.run(
                cmd, capture_output=True, timeout=25,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                check=False)
            if result.returncode:
                raise PermissionError("Unable to create protected Client directory")
        else:
            folder.mkdir(parents=True, mode=0o700)
            folder.chmod(0o700)
    if not folder.is_dir() or folder.is_symlink():
        raise PermissionError("Invalid protected Client directory")
    _require_private_acl(folder)
    return folder


def _safe_address(host: object, port: object) -> str:
    if not isinstance(host, str):
        raise ValueError("Enter Manager IP address or DNS name")
    host = host.strip()
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        if not HOSTNAME.fullmatch(host) or ".." in host or host.endswith("."):
            raise ValueError("Invalid Manager address")
        hostname = host
    else:
        if address.is_unspecified or address.is_multicast or address.is_link_local:
            raise ValueError("Invalid Manager IP address")
        hostname = "[" + host + "]" if address.version == 6 else host
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("Manager port must be 1024–65535")
    return f"https://{hostname}:{port}"


def config_info(folder: Path) -> dict:
    path = folder / "managers.json"
    if not path.exists():
        return {"configured": False, "profiles": []}
    profiles = load_profiles(path)
    return {"configured": True, "profiles": [
        {"manager_id": x["manager_id"],
         "client_id": x["client_id"],
         "display_name": x["display_name"],
         "endpoint": x["endpoint"]}
        for x in profiles]}


def enroll_profile(folder: Path, payload: dict) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Invalid form")
    mid, cid = payload.get("manager_id"), payload.get("client_id")
    if not isinstance(mid, str) or not IDENTIFIER.fullmatch(mid):
        raise ValueError("Manager ID must contain letters, digits, '.', '-' or '_'")
    if not isinstance(cid, str) or not IDENTIFIER.fullmatch(cid):
        raise ValueError("Client ID must contain letters, digits, '.', '-' or '_'")
    display = payload.get("display_name")
    if not isinstance(display, str) or not 1 <= len(display.strip()) <= 80:
        raise ValueError("Enter a Manager name")
    endpoint = _safe_address(payload.get("host"), payload.get("port"))
    pem = payload.get("certificate")
    if not isinstance(pem, str) or len(pem) > 16000:
        raise ValueError("Manager public certificate required")
    try:
        der = ssl.PEM_cert_to_DER_cert(pem.strip())
    except ValueError as error:
        raise ValueError("Invalid PEM certificate") from error
    if len(der) < 100:
        raise ValueError("Certificate is invalid")
    fingerprint = hashlib.sha256(der).hexdigest()
    # Certificate import must be trusted out-of-band; never silently accept a
    # certificate fetched from an unverified remote endpoint.
    cert_path = None
    with PROFILE_LOCK:
        try:
            with tempfile.NamedTemporaryFile(
                    mode="w", encoding="ascii", dir=folder,
                    prefix=".manager-ca-", suffix=".pem",
                    delete=False) as f:
                cert_path = Path(f.name)
                f.write(pem.strip() + "\n")
            digest = enroll(folder, mid, cid, endpoint, cert_path, display.strip(),
                            announce=False)
        finally:
            if cert_path is not None:
                cert_path.unlink(missing_ok=True)
    # This is a local user-requested enrollment action. Manager never sees the
    # raw token: only its SHA-256 is sent over explicitly trusted HTTPS.
    try:
        submitted = submit_profile(folder, mid)
        state = submitted["state"]
        error = None
    except PairingRequestError as failure:
        state = "not_submitted"
        error = failure.reason
    except (OSError, ValueError):
        # An unavailable server must not lose an already-created local profile.
        state = "not_submitted"
        error = "manager_unreachable_or_untrusted"
    return {"manager_id": mid, "client_id": cid, "endpoint": endpoint,
            "registration_sha256": digest,
            "certificate_sha256": fingerprint,
            "state": state, "reason": error}


CHAT_LOCKS = {}
CHAT_LOCKS_GUARD = threading.RLock()
ACTIVE_STREAMS = {}


def selected_profile(folder, manager_id):
    if not isinstance(manager_id, str) or not IDENTIFIER.fullmatch(manager_id):
        raise ValueError("invalid_manager_id")
    profile = next((p for p in load_profiles(folder / "managers.json")
                    if p["manager_id"] == manager_id), None)
    if profile is None:
        raise ChatClientError("unknown_manager", 404)
    return profile


def chat_parameters(payload, *, stream=False):
    required = {"manager_id", "slot_id", "model_id", "message"} | ({"request_id"} if stream else set())
    if type(payload) is not dict or not required <= set(payload) or set(payload)-required-{"request_id","instance_id","options","context"}:
        raise ValueError("invalid_chat_fields")
    key = validate_key(payload["manager_id"],payload["slot_id"],payload["model_id"])
    identity = payload.get("instance_id")
    if identity is not None and (type(identity) is not str or not re.fullmatch(r"[a-f0-9]{32}|legacy-[A-Za-z0-9_.-]{1,96}",identity)):
        raise ValueError("invalid_instance_id")
    message = payload["message"]
    if type(message) is not str or not message.strip() or len(message)>131072:
        raise ValueError("invalid_chat_message")
    context = payload.get("context", {})
    if type(context) is not dict or set(context)-{"max_messages","max_chars"}:
        raise ValueError("invalid_context_policy")
    selected = {"max_messages":context.get("max_messages",100), "max_chars":context.get("max_chars",200000)}
    context_for([], **selected)  # validate before claiming the request
    if type(payload.get("options",{})) is not dict:
        raise ValueError("invalid_generation_options")
    history_id = identity if identity and not identity.startswith("legacy-") else None
    return key, identity, history_id, selected


def chat_stream_exchange(folder, payload):
    started = time.perf_counter()
    key, identity, history_id, context_policy = chat_parameters(payload, stream=True)
    message = payload["message"]
    profile = selected_profile(folder, key[0])
    phases = {"client_profile_load_ms":round((time.perf_counter()-started)*1000,3)}
    if type(payload["request_id"]) is not str or not re.fullmatch(r"[a-f0-9]{32}", payload["request_id"]):
        raise ValueError("invalid_request_id")
    with CHAT_LOCKS_GUARD:
        lock = CHAT_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ChatClientError("chat_in_progress", 409)
    upstream = None
    claimed = False
    cancelled = threading.Event()
    active_key = (*key, payload["request_id"])
    try:
        claim_started=time.perf_counter()
        state = claim_request(folder, payload["request_id"], (*key,history_id), message,
            request_options={"options":payload.get("options"),"context":context_policy})
        phases["client_sqlite_claim_ms"] = round((time.perf_counter()-claim_started)*1000,3)
        if state == "complete":
            updated = load_chat_history(folder, *key, instance_id=history_id)
            yield stream_history_event({"type": "done", "cached": True}, updated)
            return
        if state != "new":
            raise ChatClientError("chat_request_already_attempted", 409)
        claimed = True
        with CHAT_LOCKS_GUARD:
            ACTIVE_STREAMS[active_key] = cancelled
        context_started=time.perf_counter()
        messages, context_info = context_for(load_chat_history(folder, *key, instance_id=history_id, limit=1024),
            **context_policy, with_info=True)
        messages.append({"role":"user","content":message})
        client_prepare_ms = round((time.perf_counter()-started)*1000,3)
        phases["client_history_load_ms"] = round((time.perf_counter()-context_started)*1000,3)
        upstream = stream_chat(profile, key[1], key[2], messages, request_id=payload["request_id"],
                               instance_id=identity, options=payload.get("options"))
        reply = ""
        reasoning = ""
        for event in upstream:
            if cancelled.is_set():
                raise ChatClientError("stream_cancelled", 409)
            if event["type"] == "delta":
                value = event.get("text")
                if not isinstance(value, str) or len(reply) + len(value) > 1048576:
                    raise ChatClientError("invalid_stream_delta")
                reply += value
            if event["type"] == "meta":
                event["context"] = context_info
            if event["type"] == "reasoning":
                value = event.get("text")
                if type(value) is not str or len(reasoning)+len(value)>1048576:
                    raise ChatClientError("invalid_reasoning_delta")
                reasoning += value
            event["timing"] = {**event.get("timing",{}), **phases, "client_prepare_ms":client_prepare_ms,
                "client_local_elapsed_ms":round((time.perf_counter()-started)*1000,3)}
            if event["type"] == "done":
                if not (reply.strip() or reasoning.strip()):
                    raise ChatClientError("empty_stream")
                persist_started=time.perf_counter()
                updated = append_exchange(folder, *key, message, reply, request_id=payload["request_id"],
                    instance_id=history_id, reasoning=reasoning)
                event["timing"]["client_persist_ms"] = round((time.perf_counter()-persist_started)*1000,3)
                event["timing"]["client_local_total_ms"] = round((time.perf_counter()-started)*1000,3)
                claimed = False
                yield stream_history_event(event, updated)
                return
            yield event
        raise ChatClientError("stream_truncated")
    finally:
        try:
            if upstream is not None:
                upstream.close()
            if claimed:
                fail_request(folder, payload["request_id"])
        finally:
            with CHAT_LOCKS_GUARD:
                ACTIVE_STREAMS.pop(active_key, None)
            lock.release()


def stream_history_event(event, messages):
    # Large existing histories are fetched separately, never allowed to turn
    # the final NDJSON event into an unbounded stream frame.
    if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > 400*1024:
        return {**event, "history_reload": True}
    return {**event, "messages": messages}


def chat_exchange(folder: Path, payload: dict) -> dict:
    """Send to only the Manager/slot/model named by the existing profile."""
    key, identity, history_id, context_policy = chat_parameters(payload)
    message = payload["message"]
    profiles = load_profiles(folder / "managers.json")
    profile = next((p for p in profiles if p["manager_id"] == key[0]), None)
    if profile is None:
        raise ChatClientError("unknown_manager", 404)
    with CHAT_LOCKS_GUARD:
        lock = CHAT_LOCKS.setdefault(key, threading.Lock())
    if not lock.acquire(blocking=False):
        raise ChatClientError("chat_in_progress", 409)
    request_id = payload.get("request_id")
    claimed = False
    try:
        if request_id is not None:
            state = claim_request(folder, request_id, (*key,history_id), message,
                request_options={"options":payload.get("options"),"context":context_policy})
            if state == "complete":
                updated = load_chat_history(folder, *key, instance_id=history_id)
                return {"messages": updated, "reply": updated[-1]["content"] if updated else "", "cached": True}
            if state != "new":
                raise ChatClientError("chat_request_already_attempted", 409)
            claimed = True
        existing = load_chat_history(folder, *key, instance_id=history_id, limit=1024)
        messages, context_info = context_for(existing, **context_policy, with_info=True)
        messages.append({"role": "user", "content": message})
        response = send_chat(profile, key[1], key[2], messages, instance_id=identity, options=payload.get("options"))
        updated = append_exchange(folder, *key, message, response["reply"], request_id=request_id,
            instance_id=history_id, reasoning=response.get("reasoning", ""))
        claimed = False
        return {"reply": response["reply"], "messages": updated, "context":context_info,
                "usage": response.get("usage", {}),
                "finish_reason": response.get("finish_reason")}
    finally:
        try:
            if claimed:
                fail_request(folder, request_id)
        finally:
            lock.release()


def _secure_host(handler, port: int) -> bool:
    return handler.headers.get("Host", "") == f"127.0.0.1:{port}"


def make_handler(folder: Path, port_getter, csrf: str):
    class WebHandler(BaseHTTPRequestHandler):
        server_version = "UltraLLMWeb/1.0"
        sys_version = ""
        def _headers(self, status, mime, size):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            if size is not None:
                self.send_header("Content-Length", str(size))
            else:
                self.send_header("Connection", "close")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            self.end_headers()
        def _send_json(self, status, data):
            raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(raw))
            self.wfile.write(raw)
        def _reject_post(self, status, data):
            # Closing with unread request bytes can reset Windows TCP before
            # the caller receives the rejection. Discard only a bounded body,
            # without parsing it or allowing a slow sender to hold this thread.
            if self.command == "POST" and not self.headers.get("Transfer-Encoding"):
                lengths = self.headers.get_all("Content-Length", [])
                try:
                    remaining = int(lengths[0]) if len(lengths) == 1 else 0
                except ValueError:
                    remaining = 0
                if 0 < remaining <= MAX_BODY:
                    previous_timeout = self.connection.gettimeout()
                    deadline = time.perf_counter() + 0.2
                    try:
                        while remaining and time.perf_counter() < deadline:
                            self.connection.settimeout(max(0.001, deadline-time.perf_counter()))
                            chunk = self.rfile.read1(min(remaining, 65536))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    except OSError:
                        pass
                    finally:
                        self.connection.settimeout(previous_timeout)
            return self._send_json(status, data)
        def _bad_host(self):
            if not _secure_host(self, port_getter()):
                self._reject_post(403, {"error": "untrusted_host"})
                return True
            if self.client_address[0] != "127.0.0.1":
                self._reject_post(403, {"error": "loopback_only"})
                return True
            return False
        def do_GET(self):
            if self._bad_host():
                return
            # Tracking parameters added by browsers/link wrappers must not
            # turn the homepage into a 404. Ignore queries ONLY for "/".
            # API routes retain their exact validation/CSRF requirements.
            path = "/" if self.path.startswith("/?") and len(self.path) <= 2048 else self.path
            if path in _STATIC_FILES:
                name, mime = _STATIC_FILES[path]
                file = STATIC / name
                if not file.is_file():
                    return self._send_json(503, {"error": "missing_web_assets"})
                raw = file.read_bytes()
                self._headers(200, mime, len(raw))
                return self.wfile.write(raw)
            if path == "/api/session":
                return self._send_json(200, {"csrf": csrf})
            if path == "/api/config":
                try:
                    return self._send_json(200, config_info(folder))
                except (OSError, ValueError, KeyError):
                    return self._send_json(500, {"error": "invalid_private_configuration"})
            if path == "/api/status":
                try:
                    config_path = folder / "managers.json"
                    if not config_path.is_file():
                        return self._send_json(200, {"configured": False, "managers": []})
                    profiles = load_profiles(config_path)
                    results = fetch_all(profiles)
                    for row in results:
                        if row["status"] == "online":
                            row["pairing_state"] = "approved"
                        else:
                            try:
                                row["pairing_state"] = check_profile_ticket(
                                    folder, row["manager_id"])
                            except (PairingRequestError, OSError, ValueError,
                                    KeyError, json.JSONDecodeError):
                                row["pairing_state"] = "unknown"
                    return self._send_json(200, {
                        "configured": True, "managers": results})
                except (OSError, ValueError, KeyError):
                    return self._send_json(503, {"error": "manager_config_unavailable"})
            if path.startswith("/api/control/catalog?"):
                from urllib.parse import parse_qs
                try:
                    q = parse_qs(path.split("?", 1)[1])
                    if set(q) != {"manager_id"} or len(q["manager_id"]) != 1:
                        raise ValueError()
                    return self._send_json(200, control_request(selected_profile(folder, q["manager_id"][0])))
                except ChatClientError as error:
                    return self._send_json(error.status, {"error": error.reason})
                except (ValueError, OSError):
                    return self._send_json(400, {"error": "invalid_manager_id"})
            if path.startswith("/api/chat/history?"):
                from urllib.parse import parse_qs
                try:
                    if len(path) > 1024:
                        raise ValueError("invalid_query")
                    query = parse_qs(path.split("?", 1)[1])
                    if not {"manager_id", "slot_id", "model_id"} <= set(query) or set(query)-{"manager_id", "slot_id", "model_id", "instance_id"}:
                        raise ValueError("invalid_query")
                    key = validate_key(*(query[k][0] for k in
                        ("manager_id", "slot_id", "model_id")))
                    return self._send_json(200, {
                        "messages": load_chat_history(folder, *key, instance_id=query.get("instance_id",[None])[0]),
                        "history_window_messages":100})
                except (ValueError, KeyError, TypeError):
                    return self._send_json(400, {"error": "invalid_chat_target"})
                except (OSError, sqlite3.Error):
                    return self._send_json(503, {"error": "chat_storage_unavailable"})
            if path.startswith("/api/pairing/admin?"):
                from urllib.parse import parse_qs
                params = parse_qs(path.split("?", 1)[1])
                mid = params.get("manager_id", [None])[0]
                try:
                    return self._send_json(200, admin_requests(folder, mid))
                except (PairingRequestError, OSError, ValueError, KeyError):
                    return self._send_json(403, {"error": "pairing_admin_required_or_offline"})
            return self._send_json(404, {"error": "not_found"})
        def do_POST(self):
            if self._bad_host():
                return
            origin = self.headers.get("Origin", "")
            expected = f"http://127.0.0.1:{port_getter()}"
            if (origin != expected or
                    not secrets.compare_digest(
                        self.headers.get("X-Ultra-CSRF", ""), csrf)):
                return self._reject_post(403, {"error": "request_not_authorised"})
            if self.path not in ("/api/chat/send", "/api/chat/stream", "/api/chat/cancel", "/api/control", "/api/enroll", "/api/shutdown",
                                  "/api/pairing/retry",
                                  "/api/pairing/approve",
                                  "/api/pairing/deny"):
                return self._reject_post(404, {"error": "not_found"})
            if self.path == "/api/shutdown":
                self._send_json(200, {"stopping": True})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self._reject_post(415, {"error": "json_only"})
            try:
                if self.headers.get("Transfer-Encoding"):
                    raise ValueError("unsupported_transfer_encoding")
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= MAX_BODY:
                    return self._send_json(413, {"error": "invalid_request_size"})
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/enroll":
                    response = enroll_profile(folder, data)
                    return self._send_json(201, response)
                if not isinstance(data, dict):
                    raise ValueError("Invalid form")
                if self.path == "/api/chat/send":
                    return self._send_json(200, chat_exchange(folder, data))
                if self.path == "/api/chat/stream":
                    return self._stream_chat(data)
                if self.path == "/api/chat/cancel":
                    if set(data) != {"manager_id", "slot_id", "model_id", "request_id"}:
                        raise ValueError("invalid_cancel_fields")
                    key = validate_key(data["manager_id"], data["slot_id"], data["model_id"])
                    if type(data["request_id"]) is not str:
                        raise ValueError("invalid_request_id")
                    with CHAT_LOCKS_GUARD:
                        flag = ACTIVE_STREAMS.get((*key, data["request_id"]))
                        if flag is not None:
                            flag.set()
                    confirmed = False
                    if flag is not None:
                        try:
                            confirmed = cancel_chat(selected_profile(folder, key[0]), key[1], data["request_id"])
                        except (ChatClientError, ValueError, OSError):
                            pass
                    return self._send_json(200, {"cancelled": flag is not None, "upstream_cancelled": confirmed})
                if self.path == "/api/control":
                    profile = selected_profile(folder, data.get("manager_id"))
                    return self._send_json(200, control_request(profile,
                        {k:v for k,v in data.items() if k != "manager_id"}))
                mid = data.get("manager_id")
                if self.path == "/api/pairing/retry":
                    if set(data) != {"manager_id"}:
                        raise ValueError("Invalid retry")
                    return self._send_json(200, submit_profile(folder, mid))
                ticket = data.get("ticket_id")
                if self.path == "/api/pairing/approve":
                    if set(data) != {"manager_id", "ticket_id", "allowed_slots"}:
                        raise ValueError("Invalid approval")
                    return self._send_json(200, admin_decision(
                        folder, mid, ticket, data.get("allowed_slots"), approve=True))
                if set(data) != {"manager_id", "ticket_id"}:
                    raise ValueError("Invalid denial")
                return self._send_json(200, admin_decision(
                    folder, mid, ticket, approve=False))
            except ChatClientError as error:
                return self._send_json(error.status, {"error": error.reason})
            except sqlite3.Error:
                return self._send_json(503, {"error": "chat_storage_unavailable"})
            except PairingRequestError as error:
                return self._send_json(409, {"error": error.reason})
            except (ValueError, KeyError, FileExistsError) as error:
                return self._send_json(400, {"error": str(error)[:200]})
            except (OSError, PermissionError):
                return self._send_json(500, {"error": "private_store_unavailable"})
        def _stream_chat(self, payload):
            events = chat_stream_exchange(folder, payload)
            try:
                first = next(events)
                import socket
                self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self._headers(200, "application/x-ndjson; charset=utf-8", None)
                self.close_connection = True
                def emit(event):
                    event["timing"] = {**event.get("timing",{}), "client_emit_unix_ms":round(time.time()*1000,3)}
                    self.wfile.write(json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n")
                    self.wfile.flush()
                try:
                    emit(first)
                    for event in events:
                        emit(event)
                except (ChatClientError, sqlite3.Error, ValueError) as error:
                    try:
                        emit({"type": "error", "error": getattr(error, "reason", "chat_stream_failed")})
                    except OSError:
                        pass
                except (OSError, TimeoutError):
                    pass
            finally:
                events.close()

        def log_message(self, *args):
            # URLs and request bodies may contain private details: never log them.
            pass
    return WebHandler


def _open_existing_instance(folder: Path, open_browser: bool) -> bool:
    """Never open an unverified arbitrary port unless another instance owns
    the named mutex for the exact protected Client profile directory."""
    port_path = folder / ".web-client.port"
    opener = build_opener(ProxyHandler({}))
    for _ in range(20):
        try:
            port = int(port_path.read_text(encoding="ascii").strip())
            if not 1024 <= port <= 65535:
                raise ValueError("Invalid port")
            url = f"http://127.0.0.1:{port}/"
            with opener.open(url + "api/config", timeout=1.2) as response:
                if (response.status == 200 and
                        response.headers.get("Server", "").startswith("UltraLLMWeb/")):
                    if open_browser:
                        webbrowser.open(url)
                    return True
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise RuntimeError("An existing Web Client did not respond; check its process")


def _instance_mutex(folder: Path):
    """Keep one browser server per Windows user/session and profile."""
    if os.name != "nt":
        return None, False
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
    kernel.CreateMutexW.restype = ctypes.c_void_p
    name = "Local\\UltraLLM-Web-" + hashlib.sha256(
        str(folder).casefold().encode("utf-8")).hexdigest()[:32]
    handle = kernel.CreateMutexW(None, False, name)
    if not handle:
        raise OSError("Cannot create Web Client single-instance mutex")
    return (kernel, handle), (ctypes.get_last_error() == 183)


def run_server(folder: Path, *, port: int = 0, open_browser: bool = True):
    folder = ensure_private_dir(folder)
    handle, duplicate = _instance_mutex(folder)
    if duplicate:
        try:
            _open_existing_instance(folder, open_browser)
        finally:
            if handle:
                handle[0].CloseHandle(ctypes.c_void_p(handle[1]))
        return
    session_key = secrets.token_urlsafe(32)
    holder = {"port": 0}
    port_path = folder / ".web-client.port"
    server = None
    try:
        handler = make_handler(folder, lambda: holder["port"], session_key)
        server = ThreadingHTTPServer(("127.0.0.1", port), handler)
        server.daemon_threads = True
        holder["port"] = server.server_address[1]
        address = f"http://127.0.0.1:{holder['port']}/"
        port_path.write_text(str(holder["port"]), encoding="ascii")
        # --windowed/--noconsole PyInstaller sets sys.stdout to None.
        # Diagnostics must never prevent a GUI-only package from starting.
        if sys.stdout is not None:
            print("ULTRA_WEB_CLIENT_READY", address, flush=True)
        if open_browser:
            webbrowser.open(address)
        server.serve_forever(poll_interval=0.25)
    finally:
        if server is not None:
            server.server_close()
        if port_path.is_file() and port_path.read_text(encoding="ascii").strip() == str(holder["port"]):
            port_path.unlink()
        if handle:
            handle[0].CloseHandle(ctypes.c_void_p(handle[1]))


def main():
    parser = argparse.ArgumentParser(description="Ultra LLM browser-only Client")
    parser.add_argument("--config-dir", type=Path, default=config_directory())
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=0)
    a = parser.parse_args()
    run_server(a.config_dir, port=a.port, open_browser=not a.no_browser)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # pythonw has no console; surface an actionable error without leaking
        # private paths, credentials, certificate content or HTTP responses.
        if os.name == "nt" and sys.stderr is None:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Не удалось запустить Ultra LLM Web Client. "
                "Проверьте Python 3.12, права на защищённый каталог и файлы приложения.",
                "Ultra LLM Client — ошибка запуска", 0x10)
        raise
