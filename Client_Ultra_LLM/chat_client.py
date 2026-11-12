"""Client-side, TLS-validated CHAT-01 forwarding to a configured Manager.

The browser never receives bearer credentials or Manager filesystem paths.
"""
from __future__ import annotations

import json
import ssl
import time
import threading
import socket
from contextlib import contextmanager
from urllib.request import HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener


class ChatClientError(Exception):
    def __init__(self, reason, status=502):
        super().__init__(reason)
        self.reason = reason
        self.status = status


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def manager_open(profile, path, payload=None, *, timeout=15, timing=None):
    """Private transport shared by control and streaming; never accepts URLs from JS."""
    try:
        timing = {} if timing is None else timing
        began = time.perf_counter()
        token = profile["token_file"].read_text(encoding="ascii").strip()
        if not 32 <= len(token) <= 249:
            raise ValueError()
        timing["client_token_read_ms"] = round((time.perf_counter()-began)*1000,3)
        tls_started = time.perf_counter()
        ctx = ssl.create_default_context(cafile=str(profile["ca_cert"]))
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        timing["client_tls_setup_ms"] = round((time.perf_counter()-tls_started)*1000,3)
        req = Request(profile["endpoint"] + path,
            data=None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"})
        headers_started=time.perf_counter()
        response = build_opener(ProxyHandler({}), HTTPSHandler(context=ctx), NoRedirect()).open(req, timeout=timeout)
        timing["client_http_headers_ms"] = round((time.perf_counter()-headers_started)*1000,3)
        return response
    except HTTPError as error:
        # Only machine-readable allowlisted error names, never raw HTTP text.
        reason = "manager_http_" + str(error.code)
        try:
            body = json.loads(error.read(4097))
            import re
            if isinstance(body.get("error"), str) and re.fullmatch(r"[a-z0-9_]{1,80}", body["error"]):
                reason = body["error"]
        except (ValueError, OSError, AttributeError):
            pass
        finally:
            error.close()
        raise ChatClientError(reason, error.code) from None
    except (OSError, ValueError, URLError, KeyError):
        raise ChatClientError("manager_connection_failed", 503) from None


def control_request(profile, payload=None):
    path = "/v1/control/catalog" if payload is None else "/v1/control"
    with manager_open(profile, path, payload) as r:
        raw = r.read(256*1024+1)
    if len(raw) > 256*1024:
        raise ChatClientError("control_response_too_large")
    try:
        data = json.loads(raw)
        if data.get("manager_id") != profile["manager_id"]:
            raise ValueError()
        return data
    except (ValueError, AttributeError):
        raise ChatClientError("invalid_control_response") from None


@contextmanager
def stream_guard(response, deadline):
    sock = getattr(getattr(getattr(response, "fp", None), "raw", None), "_sock", None)
    def interrupt():
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                socket.close(sock.detach())
            except OSError:
                pass
    timer = threading.Timer(max(0.01, deadline-time.perf_counter()), interrupt)
    timer.daemon = True
    timer.start()
    try:
        yield
    finally:
        timer.cancel()


def cancel_chat(profile, slot_id, request_id):
    with manager_open(profile, "/v1/chat/cancel", {"slot_id": slot_id, "request_id": request_id}, timeout=5) as r:
        result = json.loads(r.read(4097))
    return result.get("manager_id") == profile["manager_id"] and result.get("cancelled") is True


def stream_chat(profile, slot_id, model_id, messages, *, timeout=330, request_id=None, instance_id=None, options=None):
    started = time.perf_counter()
    timing = {}
    try:
        payload = {"slot_id": slot_id, "model_id": model_id, "messages": messages}
        if request_id is not None:
            payload["request_id"] = request_id
        if instance_id is not None:
            payload["instance_id"] = instance_id
        if options is not None:
            payload["options"] = options
        with manager_open(profile, "/v1/chat/stream", payload, timeout=timeout, timing=timing) as r, \
                stream_guard(r, started+timeout):
            if r.headers.get_content_type() != "application/x-ndjson":
                raise ChatClientError("invalid_stream_response")
            seen_meta = False
            require_sequence = False
            sequence = 0
            total = 0
            while True:
                if time.perf_counter()-started > timeout:
                    raise ChatClientError("stream_deadline", 504)
                raw = r.readline(2097154)
                total += len(raw)
                if total > 67108864 or len(raw) > 2097152:
                    raise ChatClientError("stream_too_large")
                if not raw:
                    raise ChatClientError("stream_truncated")
                event = json.loads(raw)
                kind = event.get("type")
                if not seen_meta:
                    if (kind != "meta" or event.get("manager_id") != profile["manager_id"]
                            or event.get("slot_id") != slot_id or event.get("model_id") != model_id):
                        raise ChatClientError("stream_identity_mismatch")
                    if instance_id is not None and event.get("instance_id") != instance_id:
                        raise ChatClientError("stream_identity_mismatch")
                    seen_meta = True
                    require_sequence = event.get("schema") == "ultra.manager.stream.v2"
                elif kind not in ("delta", "reasoning", "done", "error"):
                    raise ChatClientError("invalid_stream_event")
                if kind == "error":
                    reason = event.get("error", "stream_failed")
                    import re
                    if not isinstance(reason, str) or not re.fullmatch(r"[a-z0-9_]{1,80}", reason):
                        reason = "stream_failed"
                    raise ChatClientError(reason, 502)
                if kind in ("delta", "reasoning"):
                    if "client_first_fragment_unix_ms" not in timing:
                        timing["client_first_fragment_unix_ms"] = round(time.time()*1000, 3)
                        timing["client_first_fragment_elapsed_ms"] = round((time.perf_counter()-started)*1000, 3)
                    sequence += 1
                    if require_sequence and event.get("sequence") != sequence:
                        raise ChatClientError("stream_sequence_mismatch")
                event["timing"] = {**event.get("timing", {}), **timing,
                    "client_received_unix_ms": round(time.time()*1000, 3),
                    "client_elapsed_ms":round((time.perf_counter()-started)*1000, 3)}
                yield event
                if kind == "done":
                    return
    except ChatClientError:
        raise
    except (OSError, TimeoutError, URLError, ValueError, AttributeError):
        raise ChatClientError("manager_stream_failed", 503) from None


def send_chat(profile, slot_id, model_id, messages, *, timeout=330, instance_id=None, options=None):
    """Same authenticated transport and precise errors as streaming/control."""
    started=time.perf_counter()
    body={"slot_id":slot_id,"model_id":model_id,"messages":messages}
    if instance_id is not None:body["instance_id"]=instance_id
    if options is not None:body["options"]=options
    try:
        with manager_open(profile,"/v1/chat",body,timeout=timeout) as response, stream_guard(response,started+timeout):
            raw=response.read(8388609)
        if len(raw)>8388608:raise ChatClientError("chat_response_too_large")
        result=json.loads(raw)
        if (result.get("schema")!="ultra.manager.chat.v1" or result.get("manager_id")!=profile["manager_id"]
                or result.get("slot_id")!=slot_id or result.get("model_id")!=model_id
                or type(result.get("reply")) is not str or not (result["reply"].strip() or result.get("reasoning"))):
            raise ChatClientError("invalid_chat_response")
        if instance_id is not None and result.get("instance_id")!=instance_id:
            raise ChatClientError("chat_identity_mismatch")
        return {"reply":result["reply"],"finish_reason":result.get("finish_reason"),
                "usage":result.get("usage",{}),"reasoning":result.get("reasoning","")}
    except ChatClientError:raise
    except (OSError,ValueError,KeyError,TypeError,IndexError,AttributeError):
        raise ChatClientError("invalid_chat_response") from None
