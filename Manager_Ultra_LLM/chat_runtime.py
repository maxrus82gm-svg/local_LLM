"""CHAT-01: bounded server-side inference through an existing Colibri slot.

Never accepts a backend URL, port, local path or caller-declared identity.
Only the Manager's validated slot configuration selects the loopback API.
"""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, build_opener

MODEL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")


class ChatError(Exception):
    def __init__(self, reason, status=400):
        super().__init__(reason)
        self.reason = reason
        self.status = status


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
        with build_opener(ProxyHandler({})).open(req, timeout=timeout) as response:
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
