"""Client-side, TLS-validated CHAT-01 forwarding to a configured Manager.

The browser never receives bearer credentials or Manager filesystem paths.
"""
from __future__ import annotations

import json
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener


class ChatClientError(Exception):
    def __init__(self, reason, status=502):
        super().__init__(reason)
        self.reason = reason
        self.status = status


def send_chat(profile, slot_id, model_id, messages, *, timeout=150):
    try:
        token = profile["token_file"].read_text(encoding="ascii").strip()
        if len(token) < 32:
            raise ValueError("Invalid credential")
        ctx = ssl.create_default_context(cafile=str(profile["ca_cert"]))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        payload = json.dumps({"slot_id": slot_id, "model_id": model_id,
                              "messages": messages}, ensure_ascii=False).encode("utf-8")
        req = Request(profile["endpoint"] + "/v1/chat", method="POST",
                      data=payload,
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/json",
                               "Content-Type": "application/json"})
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=ctx))
        with opener.open(req, timeout=timeout) as response:
            if response.status != 200:
                raise ChatClientError("chat_unavailable")
            raw = response.read(256 * 1024 + 1)
        if len(raw) > 256 * 1024:
            raise ChatClientError("chat_response_too_large")
        result = json.loads(raw)
        if (result.get("schema") != "ultra.manager.chat.v1" or
                result.get("manager_id") != profile["manager_id"] or
                result.get("slot_id") != slot_id or
                result.get("model_id") != model_id or
                not isinstance(result.get("reply"), str) or
                not result["reply"].strip()):
            raise ChatClientError("invalid_chat_response")
        return {"reply": result["reply"], "finish_reason": result.get("finish_reason"),
                "usage": result.get("usage", {})}
    except HTTPError as error:
        code = error.code
        if code in (401, 403):
            raise ChatClientError("chat_not_authorized", 403) from None
        if code in (404, 405):
            raise ChatClientError("manager_chat_update_required", 503) from None
        if code == 409:
            raise ChatClientError("model_not_ready_or_busy", 409) from None
        raise ChatClientError("manager_chat_unavailable", 503) from None
    except ChatClientError:
        raise
    except (OSError, TimeoutError, ssl.SSLError, URLError, ValueError, KeyError,
            TypeError, json.JSONDecodeError):
        raise ChatClientError("manager_chat_connection_failed", 503) from None
