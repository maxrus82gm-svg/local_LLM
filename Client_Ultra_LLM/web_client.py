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
from contextlib import contextmanager
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
import stat
import sys
import tempfile
import threading
from urllib.parse import urlsplit
import webbrowser

from live_client import fetch_all, load_profiles
from pairing_client import _require_private_acl, _run_windows_powershell, enroll
from chat_client import ChatClientError, send_chat, stream_chat, control_request, cancel_chat
from chat_store import (validate_key, validate_chat_id, history as load_chat_history, legacy_chat_id, wire_bytes,
                        context_for, request_context, append_exchange, claim_request, fail_request,
                        utc_now, get_chat, list_chats, manage_chat, recent_metrics,
                        ChatTargetOccupied, require_unassigned_slot)
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
    for component in (folder, *folder.parents):
        try:
            attributes = component.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(attributes.st_mode) or getattr(attributes, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise PermissionError("Credential directory cannot cross a reparse point")
    if not folder.exists():
        if os.name == "nt":
            installer = HERE / "Prepare-ClientPrivate.ps1"
            result = _run_windows_powershell(
                ["-ExecutionPolicy", "Bypass", "-File", str(installer), "-TargetDirectory", str(folder)], timeout=25)
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


CHAT_LOCKS = set()
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
    if type(payload) is not dict or not required <= set(payload) or set(payload)-required-{"request_id","instance_id","options","context","chat_id"}:
        raise ValueError("invalid_chat_fields")
    key = validate_key(payload["manager_id"],payload["slot_id"],payload["model_id"])
    identity = payload.get("instance_id")
    if identity is not None and (type(identity) is not str or not re.fullmatch(r"[a-f0-9]{32}|legacy-[A-Za-z0-9_.-]{1,96}",identity)):
        raise ValueError("invalid_instance_id")
    message = payload["message"]
    if type(message) is not str or not message.strip() or len(message)>131072 or "\x00" in message:
        raise ValueError("invalid_chat_message")
    context = payload.get("context", {})
    if type(context) is not dict or set(context)-{"max_messages","max_chars","max_bytes"}:
        raise ValueError("invalid_context_policy")
    selected = {"max_messages":context.get("max_messages",100), "max_chars":context.get("max_chars",200000)}
    context_for([], **selected)  # validate before claiming the request
    max_bytes = context.get("max_bytes", MAX_BODY)
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_BODY:
        raise ValueError("invalid_context_policy")
    if "max_bytes" in context:
        selected["max_bytes"] = max_bytes
    wire_bytes(message)
    if type(payload.get("options",{})) is not dict:
        raise ValueError("invalid_generation_options")
    history_id = identity if identity and not identity.startswith("legacy-") else None
    return key, identity, history_id, selected


@contextmanager
def chat_lock(key):
    with CHAT_LOCKS_GUARD:
        if key in CHAT_LOCKS:
            raise ChatClientError("chat_in_progress", 409)
        CHAT_LOCKS.add(key)
    try:
        yield
    finally:
        with CHAT_LOCKS_GUARD:
            CHAT_LOCKS.remove(key)


def chat_record(folder, chat_id):
    try:
        return get_chat(folder, chat_id)
    except KeyError:
        raise ChatClientError("chat_not_found", 404) from None


def chat_action(folder, data):
    fields = {"create": (set(), {"target", "title"}), "rename": ({"title"}, set()),
              "target": ({"target"}, set()), "settings": ({"context"}, set()),
              "preferences": ({"preferences"}, set()),
              "reset": (set(), set()), "resume": (set(), set()), "restore": (set(), set()),
              "clear": ({"confirm"}, set()), "delete": ({"confirm"}, set())}
    op = data.get("op")
    if type(op) is not str or op not in fields:
        raise ValueError("invalid_chat_operation")
    required, optional = fields[op]
    required = required | {"op"} | ({"chat_id"} if op != "create" else set())
    if not required <= set(data) or set(data) - required - optional:
        raise ValueError("invalid_chat_fields")
    if op in ("clear", "delete") and data["confirm"] is not True:
        raise ValueError("chat_confirmation_required")
    target = data.get("target")
    if target is not None:
        if type(target) is not dict:
            raise ValueError("invalid_chat_target")
        selected_profile(folder, target.get("manager_id"))
    try:
        if op == "create":
            return manage_chat(folder, op, data)
        chat_id = validate_chat_id(data["chat_id"])
        with chat_lock((folder, chat_id)):
            chat_record(folder, chat_id)
            return manage_chat(folder, op, data)
    except ChatTargetOccupied:
        raise ChatClientError("chat_target_occupied", 409) from None


def chat_binding(folder, payload, key, context_policy):
    chat_id = payload.get("chat_id")
    if chat_id is not None:
        chat = chat_record(folder, chat_id)
        if tuple(chat[name] for name in ("manager_id", "slot_id", "model_id")) != key:
            raise ChatClientError("chat_target_changed", 409)
        if chat.get("legacy"):
            raise ChatClientError("chat_target_not_assigned", 409)
        if chat.get("target_conflict"):
            raise ChatClientError("chat_target_occupied", 409)
        if "context" not in payload:
            context_policy = chat["settings"]
    else:
        try:
            require_unassigned_slot(folder, key)
        except ChatTargetOccupied:
            raise ChatClientError("chat_target_occupied", 409) from None
    return chat_id, context_policy


def elapsed_ms(started):
    return round((time.perf_counter()-started)*1000, 3)


def finish_metrics(metrics, started, state, *, error=None, event=None):
    event = event or {}
    total = elapsed_ms(started)
    first = metrics.get("first_fragment_ms")
    metrics.update(finished_at=utc_now(), total_ms=total, state=state,
                   generation_ms=round(total-first, 3) if state == "complete" and first is not None else None)
    if error:
        metrics["error"] = error
    if state == "complete":
        usage = event.get("usage", {})
        metrics["usage"] = {k: usage[k] for k in ("prompt_tokens", "completion_tokens")
                            if type(usage.get(k)) is int and usage[k] >= 0}
        # This route rate is not an engine decode rate. Retain its window and definition.
        metrics["throughput"] = event.get("throughput", {})
    return metrics


GLOBAL_PROMPT_LIMIT = 8192


def _global_prompt_path(folder):
    path = Path(folder) / "global_prompt.json"
    if path.is_symlink() or (path.exists() and (
            not path.is_file() or getattr(path.lstat(), "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)):
        raise PermissionError("invalid_global_prompt_store")
    return path


def validate_global_prompt(prompt):
    if type(prompt) is not str or len(prompt) > GLOBAL_PROMPT_LIMIT or "\x00" in prompt:
        raise ValueError("invalid_global_prompt")
    wire_bytes(prompt)
    return prompt


def load_global_prompt(folder):
    with PROFILE_LOCK:
        path = _global_prompt_path(folder)
        if not path.exists():
            return ""
        if path.stat().st_size > 65536:
            raise ValueError("invalid_global_prompt_store")
        return validate_global_prompt(json.loads(path.read_text(encoding="utf-8"))["prompt"])


def save_global_prompt(folder, data):
    if type(data) is not dict or set(data) != {"prompt"}:
        raise ValueError("invalid_global_prompt")
    prompt = validate_global_prompt(data["prompt"])
    with PROFILE_LOCK:
        path = _global_prompt_path(folder)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=folder,
                                             prefix=".global-prompt-", delete=False) as handle:
                temp = Path(handle.name)
                json.dump({"prompt": prompt}, handle, ensure_ascii=False)
            os.replace(temp, path)
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)
    return {"prompt": prompt}


def prepare_chat_messages(folder, key, history_id, chat_id, context_policy, message):
    context_started = time.perf_counter()
    policy = dict(context_policy)
    max_bytes = policy.pop("max_bytes", MAX_BODY)
    current = {"role": "user", "content": message}
    # Account for the request envelope, including the slot, model and options.
    byte_budget = max_bytes - 1024 - wire_bytes(current)
    prompt = load_global_prompt(folder)
    # Legacy Manager does not accept a system role. Prefix the first user turn
    # in a transient request copy; do not alter stored messages or their roles.
    prefix = ("[Global Prompt]\n" + prompt + "\n[/Global Prompt]\n\n") if prompt.strip() else ""
    if prefix:
        byte_budget -= wire_bytes(prefix) + 8
        policy["max_chars"] = max(0, policy["max_chars"] - len(prefix))
        if len(current["content"]) + len(prefix) > 131072 or byte_budget < 0:
            raise ValueError("global_prompt_request_too_large")
    messages, info = request_context(folder, key, history_id, chat_id, policy, byte_budget=byte_budget)
    # Keep within the legacy per-message cap, dropping complete oldest turns.
    if prefix:
        while messages and len(messages[0]["content"]) + len(prefix) > 131072:
            messages.pop(0)
            while messages and messages[0]["role"] != "user":
                messages.pop(0)
        info["sent_history_messages"] = len(messages)
        info["sent_history_chars"] = sum(len(m["content"]) for m in messages)
        info["omitted_messages"] = info["available_messages"] - len(messages)
    messages.append(current)
    if prefix:
        messages[0] = {**messages[0], "content":prefix + messages[0]["content"]}
    info.update(sent_messages=len(messages), sent_chars=info["sent_history_chars"] + len(message) + len(prefix),
                global_prompt_chars=len(prompt) if prefix else 0,
                sent_messages_json_bytes=wire_bytes(messages), preparation_ms=elapsed_ms(context_started))
    return messages, info


def chat_stream_exchange(folder, payload):
    started = time.perf_counter()
    started_at = utc_now()
    key, identity, history_id, context_policy = chat_parameters(payload, stream=True)
    profile = selected_profile(folder, key[0])
    phases = {"client_profile_load_ms":round((time.perf_counter()-started)*1000,3)}
    request_id = payload["request_id"]
    if type(request_id) is not str or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("invalid_request_id")
    lock_key = validate_chat_id(payload["chat_id"]) if payload.get("chat_id") is not None else legacy_chat_id(folder, key, history_id) or (*key, history_id)
    with chat_lock((folder, lock_key)):
        chat_id, context_policy = chat_binding(folder, payload, key, context_policy)
        yield from _run_chat_stream(folder, payload, key, identity, history_id, context_policy,
                                    chat_id, profile, started, started_at, phases)


def _run_chat_stream(folder, payload, key, identity, history_id, context_policy, chat_id,
                     profile, started, started_at, phases):
    request_id, message = payload["request_id"], payload["message"]
    upstream = None
    claimed = False
    cancelled = threading.Event()
    active_key = (*key, request_id)
    metrics = {"started_at": started_at, "target": dict(zip(("manager_id","slot_id","model_id"), key)),
               "instance_id": identity, "options": payload.get("options") or {}, "streaming": True}
    outcome, reason = "failed", "stream_failed"
    try:
        claim_started=time.perf_counter()
        state = claim_request(folder, request_id, (*key,history_id,chat_id) if chat_id else (*key,history_id), message,
            request_options={"options":payload.get("options"),"context":context_policy})
        phases["client_sqlite_claim_ms"] = round((time.perf_counter()-claim_started)*1000,3)
        if state == "complete":
            updated = load_chat_history(folder, *key, instance_id=history_id, chat_id=chat_id)
            yield stream_history_event({"type": "done", "cached": True}, updated)
            return
        if state != "new":
            raise ChatClientError("chat_request_already_attempted", 409)
        claimed = True
        with CHAT_LOCKS_GUARD:
            ACTIVE_STREAMS[active_key] = cancelled
        messages, context_info = prepare_chat_messages(folder, key, history_id, chat_id, context_policy, message)
        metrics["context"] = context_info
        client_prepare_ms = elapsed_ms(started)
        phases["client_history_load_ms"] = context_info["preparation_ms"]
        upstream = stream_chat(profile, key[1], key[2], messages, request_id=request_id,
                               instance_id=identity, options=payload.get("options"))
        reply = ""
        reasoning = ""
        for event in upstream:
            if cancelled.is_set():
                raise ChatClientError("stream_cancelled", 409)
            if event["type"] in ("delta", "reasoning") and event.get("text"):
                if "first_fragment_ms" not in metrics:
                    metrics["first_fragment_ms"] = elapsed_ms(started)
                    metrics["first_fragment_at"] = utc_now()
            if event["type"] == "delta":
                value = event.get("text")
                if not isinstance(value, str) or len(reply) + len(value) > 1048576:
                    raise ChatClientError("invalid_stream_delta")
                reply += value
            if event["type"] == "meta":
                event["context"] = context_info
                metrics.update(engine_limits=event.get("engine_limits", {}), transport_policy=event.get("transport_policy", {}),
                               instance_id=event.get("instance_id", identity), execution_mode=event.get("execution_mode"))
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
                finish_metrics(metrics, started, "complete", event=event)
                with CHAT_LOCKS_GUARD:
                    if cancelled.is_set():
                        raise ChatClientError("stream_cancelled", 409)
                    updated = append_exchange(folder, *key, message, reply, request_id=request_id,
                        instance_id=history_id, reasoning=reasoning, chat_id=chat_id, metrics=metrics)
                    ACTIVE_STREAMS.pop(active_key, None)
                event["metrics"] = metrics
                event["timing"]["client_persist_ms"] = round((time.perf_counter()-persist_started)*1000,3)
                event["timing"]["client_local_total_ms"] = round((time.perf_counter()-started)*1000,3)
                claimed = False
                yield stream_history_event(event, updated)
                return
            yield event
        raise ChatClientError("stream_truncated")
    except GeneratorExit:
        outcome, reason = "cancelled", "browser_disconnected"
        raise
    except ChatClientError as error:
        reason = error.reason
        if cancelled.is_set() or reason in ("cancelled", "stream_cancelled"):
            outcome, reason = "cancelled", "stream_cancelled"
        raise
    finally:
        try:
            if upstream is not None:
                upstream.close()
            if claimed:
                fail_request(folder, request_id, chat_id=chat_id, state=outcome,
                    metrics=finish_metrics(metrics, started, outcome, error=reason))
        finally:
            with CHAT_LOCKS_GUARD:
                ACTIVE_STREAMS.pop(active_key, None)


def stream_history_event(event, messages):
    # Large existing histories are fetched separately, never allowed to turn
    # the final NDJSON event into an unbounded stream frame.
    if len(json.dumps(messages, ensure_ascii=False).encode("utf-8")) > 400*1024:
        return {**event, "history_reload": True}
    return {**event, "messages": messages}


def chat_exchange(folder: Path, payload: dict) -> dict:
    """Send to only the Manager/slot/model named by the existing profile."""
    started, started_at = time.perf_counter(), utc_now()
    key, identity, history_id, context_policy = chat_parameters(payload)
    profile = selected_profile(folder, key[0])
    lock_key = validate_chat_id(payload["chat_id"]) if payload.get("chat_id") is not None else legacy_chat_id(folder, key, history_id) or (*key, history_id)
    with chat_lock((folder, lock_key)):
        chat_id, context_policy = chat_binding(folder, payload, key, context_policy)
        return _run_chat_exchange(folder, payload, key, identity, history_id, context_policy,
                                  chat_id, profile, started, started_at)


def _run_chat_exchange(folder, payload, key, identity, history_id, context_policy, chat_id,
                       profile, started, started_at):
    message = payload["message"]
    request_id = payload.get("request_id")
    if chat_id and request_id is None:
        request_id = secrets.token_hex(16)
    claimed = False
    metrics = {"started_at": started_at, "target": dict(zip(("manager_id","slot_id","model_id"), key)),
               "instance_id": identity, "options": payload.get("options") or {}, "streaming": False}
    reason = "chat_failed"
    try:
        if request_id is not None:
            state = claim_request(folder, request_id, (*key,history_id,chat_id) if chat_id else (*key,history_id), message,
                request_options={"options":payload.get("options"),"context":context_policy})
            if state == "complete":
                updated = load_chat_history(folder, *key, instance_id=history_id, chat_id=chat_id)
                return {"messages": updated, "reply": updated[-1]["content"] if updated else "", "cached": True}
            if state != "new":
                raise ChatClientError("chat_request_already_attempted", 409)
            claimed = True
        messages, context_info = prepare_chat_messages(folder, key, history_id, chat_id, context_policy, message)
        metrics["context"] = context_info
        response = send_chat(profile, key[1], key[2], messages, instance_id=identity, options=payload.get("options"))
        metrics.update({name: response[name] for name in ("instance_id", "execution_mode", "engine_limits", "transport_policy")
                        if name in response})
        finish_metrics(metrics, started, "complete", event=response)
        updated = append_exchange(folder, *key, message, response["reply"], request_id=request_id,
            instance_id=history_id, reasoning=response.get("reasoning", ""), chat_id=chat_id, metrics=metrics)
        claimed = False
        return {"reply": response["reply"], "messages": updated, "context":context_info,
                "usage": response.get("usage", {}), "metrics": metrics,
                "finish_reason": response.get("finish_reason")}
    except ChatClientError as error:
        reason = error.reason
        raise
    finally:
        if claimed:
            fail_request(folder, request_id, chat_id=chat_id, metrics=finish_metrics(metrics, started, "failed", error=reason))


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
            if path == "/api/global-prompt":
                try:
                    return self._send_json(200, {"prompt": load_global_prompt(folder)})
                except (OSError, ValueError, KeyError):
                    return self._send_json(503, {"error": "global_prompt_store_unavailable"})
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
                    if set(query) == {"chat_id"} and len(query["chat_id"]) == 1:
                        chat_id = query["chat_id"][0]
                        chat_record(folder, chat_id)
                        return self._send_json(200, {"messages": load_chat_history(folder, chat_id=chat_id),
                                                     "history_window_messages":100})
                    if not {"manager_id", "slot_id", "model_id"} <= set(query) or set(query)-{"manager_id", "slot_id", "model_id", "instance_id"}:
                        raise ValueError("invalid_query")
                    key = validate_key(*(query[k][0] for k in
                        ("manager_id", "slot_id", "model_id")))
                    return self._send_json(200, {
                        "messages": load_chat_history(folder, *key, instance_id=query.get("instance_id",[None])[0]),
                        "history_window_messages":100})
                except ChatClientError as error:
                    return self._send_json(error.status, {"error": error.reason})
                except (ValueError, KeyError, TypeError):
                    return self._send_json(400, {"error": "invalid_chat_target"})
                except (OSError, sqlite3.Error):
                    return self._send_json(503, {"error": "chat_storage_unavailable"})
            if path == "/api/chats" or path.startswith("/api/chat/metrics?"):
                from urllib.parse import parse_qs
                try:
                    if path == "/api/chats":
                        return self._send_json(200, {"chats": list_chats(folder)})
                    query = parse_qs(path.split("?", 1)[1])
                    if set(query) != {"chat_id"} or len(query["chat_id"]) != 1:
                        raise ValueError("invalid_query")
                    return self._send_json(200, {"results": recent_metrics(folder, query["chat_id"][0])})
                except KeyError:
                    return self._send_json(404, {"error": "chat_not_found"})
                except ValueError:
                    return self._send_json(400, {"error": "invalid_chat_query"})
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
            if self.path not in ("/api/global-prompt", "/api/chats", "/api/chat/send", "/api/chat/stream", "/api/chat/cancel", "/api/control", "/api/enroll", "/api/shutdown",
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
                if self.path == "/api/global-prompt":
                    return self._send_json(200, save_global_prompt(folder, data))
                if self.path == "/api/chats":
                    return self._send_json(200, chat_action(folder, data))
                if self.path == "/api/chat/send":
                    return self._send_json(200, chat_exchange(folder, data))
                if self.path == "/api/chat/stream":
                    return self._stream_chat(data)
                if self.path == "/api/chat/cancel":
                    if set(data) != {"manager_id", "slot_id", "model_id", "request_id"}:
                        raise ValueError("invalid_cancel_fields")
                    key = validate_key(data["manager_id"], data["slot_id"], data["model_id"])
                    validate_chat_id(data["request_id"])
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
