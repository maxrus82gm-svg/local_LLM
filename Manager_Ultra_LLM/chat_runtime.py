"""CHAT-01: bounded server-side inference through an existing Colibri slot.

Never accepts a backend URL, port, local path or caller-declared identity.
Only the Manager's validated slot configuration selects the loopback API.
"""
from __future__ import annotations

import json
import re
import time
import socket
import threading
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener, HTTPRedirectHandler


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class ChatError(Exception):
    def __init__(self, reason, status=400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


@contextmanager
def response_guard(response, deadline, cancelled):
    """Interrupt only this response socket on absolute deadline/cancellation."""
    finished = threading.Event()
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    def watch():
        while not finished.wait(0.05):
            if cancelled.is_set() or time.monotonic() >= deadline:
                if sock:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                        # Windows timed reads can remain in select() after
                        # shutdown. Detach before close prevents a later file
                        # cleanup from closing a reused socket handle.
                        socket.close(sock.detach())
                    except OSError:
                        pass
                return
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        finished.set()
        watcher.join(0.2)


def validate_request(payload):
    if not isinstance(payload, dict) or set(payload) != {"slot_id", "model_id", "messages"}:
        raise ChatError("invalid_fields")
    slot_id, model_id, messages = (
        payload["slot_id"], payload["model_id"], payload["messages"])
    if not isinstance(slot_id, str) or not MODEL_ID.fullmatch(slot_id):
        raise ChatError("invalid_slot_id")
    if not isinstance(model_id, str) or not MODEL_ID.fullmatch(model_id):
        raise ChatError("invalid_model_id")
    if not isinstance(messages, list) or not 1 <= len(messages) <= 16:
        raise ChatError("invalid_messages")
    total = 0
    for m in messages:
        if not isinstance(m, dict) or set(m) != {"role", "content"}:
            raise ChatError("invalid_messages")
        if m["role"] not in ("user", "assistant"):
            raise ChatError("invalid_messages")
        if not isinstance(m["content"], str) or not 1 <= len(m["content"]) <= 4000:
            raise ChatError("invalid_messages")
        total += len(m["content"])
    if total > 24000 or messages[-1]["role"] != "user":
        raise ChatError("invalid_messages")
    return slot_id, model_id, messages


def select_backend(config, principal, snapshot, slot_id, model_id):
    """Strictly bind authorized client, live API model and configured slot."""
    if (snapshot.get("source") != "LIVE_HOST"
            or snapshot.get("viewer_id") != principal["client_id"]):
        raise ChatError("live_snapshot_unavailable", 503)
    if slot_id not in principal["allowed_slots"]:
        raise ChatError("slot_not_authorized", 403)
    configured = [s for s in config["slots"] if s["slot_id"] == slot_id]
    if len(configured) != 1:
        raise ChatError("unknown_slot", 404)
    current = [s for s in snapshot.get("slots", []) if s.get("slot_id") == slot_id]
    if len(current) != 1:
        raise ChatError("slot_unavailable", 503)
    row = current[0]
    if row.get("engine_state") != "ready" or model_id not in row.get("models", []):
        raise ChatError("model_not_running", 409)
    if row.get("availability") != "ready_unreserved":
        raise ChatError("slot_busy_or_unknown", 409)
    return configured[0]["api_port"]


def proxy_chat(port, model_id, messages, *, timeout=120):
    """One actual non-streaming request; no fabricated output or retries."""
    body = json.dumps({
        "model": model_id, "messages": messages,
        "max_tokens": 512, "stream": False, "enable_thinking": False,
    }, ensure_ascii=False).encode("utf-8")
    req = Request(
        f"http://127.0.0.1:{port}/v1/chat/completions", method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        data=body)
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as response:
            if response.status != 200:
                raise ChatError("colibri_unavailable", 502)
            raw = response.read(512 * 1024 + 1)
        if len(raw) > 512 * 1024:
            raise ChatError("colibri_response_too_large", 502)
        parsed = json.loads(raw)
        choice = parsed["choices"][0]
        content = choice["message"]["content"]
        if not isinstance(content, str) or not content.strip() or len(content) > 65536:
            raise ValueError("Empty answer")
        usage = parsed.get("usage") or {}
        return {
            "reply": content,
            "finish_reason": str(choice.get("finish_reason") or "unknown")[:32],
            "usage": {k: usage[k] for k in ("prompt_tokens", "completion_tokens")
                      if isinstance(usage, dict) and type(usage.get(k)) is int
                      and usage[k] >= 0}
        }
    except ChatError:
        raise
    except (HTTPError, URLError, OSError, TimeoutError, ValueError,
            KeyError, IndexError, TypeError, json.JSONDecodeError):
        raise ChatError("colibri_inference_failed", 502) from None


def proxy_stream(port, model_id, messages, *, timeout=120, cancelled=None):
    """Colibri SSE -> bounded semantic events. Never replay a full answer.

    EOF without [DONE] is an error. Separate reasoning deltas stay separate.
    Closing this iterator closes upstream; no retry or synthetic token counts.
    """
    started = time.monotonic()
    if type(timeout) not in (int, float) or not 0 < timeout <= 120:
        raise ChatError("stream_deadline", 504)
    req = Request(f"http://127.0.0.1:{port}/v1/chat/completions", method="POST",
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        data=json.dumps({"model": model_id, "messages": messages, "stream": True,
                         "max_tokens": 512, "enable_thinking": False}).encode("utf-8"))
    total = output = reasoning = 0
    first = None
    usage = {}
    finish = "unknown"
    cancelled = cancelled or threading.Event()
    try:
        with build_opener(ProxyHandler({}), NoRedirect()).open(req, timeout=timeout) as r, \
                response_guard(r, started+timeout, cancelled):
            if r.status != 200 or r.headers.get_content_type() != "text/event-stream":
                raise ChatError("colibri_stream_not_supported", 502)
            data_lines = []
            while True:
                if cancelled.is_set():
                    raise ChatError("stream_cancelled", 409)
                if time.monotonic() - started > timeout:
                    raise ChatError("stream_deadline", 504)
                line = r.readline(65538)
                if cancelled.is_set():
                    raise ChatError("stream_cancelled", 409)
                if time.monotonic() - started > timeout:
                    raise ChatError("stream_deadline", 504)
                total += len(line)
                if len(line) > 65536 or total > 1024 * 1024:
                    raise ChatError("stream_too_large", 502)
                if not line:
                    raise ChatError("stream_truncated", 502)
                line = line.decode("utf-8").rstrip("\r\n")
                if line.startswith("data:"):
                    data_lines.append(line[5:].lstrip(" "))
                elif line == "" and data_lines:
                    data = "\n".join(data_lines)
                    data_lines = []
                    if data == "[DONE]":
                        if not output:
                            raise ChatError("empty_stream", 502)
                        yield {"type": "done", "finish_reason": finish, "usage": usage,
                               "timing": {"first_fragment_ms": first,
                                          "total_ms": round((time.monotonic()-started)*1000, 2)}}
                        return
                    chunk = json.loads(data)
                    if not isinstance(chunk, dict) or not isinstance(chunk.get("choices", []), list):
                        raise ChatError("invalid_stream_event", 502)
                    if chunk.get("error"):
                        raise ChatError("colibri_stream_error", 502)
                    raw_usage = chunk.get("usage")
                    if isinstance(raw_usage, dict):
                        usage = {k: raw_usage[k] for k in ("prompt_tokens", "completion_tokens")
                                 if type(raw_usage.get(k)) is int and raw_usage[k] >= 0}
                    for choice in chunk.get("choices", []):
                        if choice.get("index", 0) != 0:
                            continue
                        if choice.get("finish_reason"):
                            finish = str(choice["finish_reason"])[:32]
                        delta = choice.get("delta", {})
                        for field, kind in (("content", "delta"), ("reasoning_content", "reasoning")):
                            value = delta.get(field)
                            if value is None or value == "":
                                continue
                            if not isinstance(value, str):
                                raise ChatError("invalid_stream_delta", 502)
                            if kind == "delta":
                                output += len(value)
                            else:
                                reasoning += len(value)
                            if output > 65536 or reasoning > 65536:
                                raise ChatError("stream_too_large", 502)
                            if first is None:
                                first = round((time.monotonic()-started)*1000, 2)
                            yield {"type": kind, "text": value}
    except ChatError:
        raise
    except TimeoutError:
        if cancelled.is_set():
            raise ChatError("stream_cancelled", 409) from None
        raise ChatError("stream_deadline", 504) from None
    except (OSError, TimeoutError, ValueError, KeyError, IndexError, TypeError, AttributeError, URLError):
        if cancelled.is_set():
            raise ChatError("stream_cancelled", 409) from None
        if time.monotonic()-started >= timeout:
            raise ChatError("stream_deadline", 504) from None
        raise ChatError("colibri_stream_failed", 502) from None
