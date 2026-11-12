"""Explicit transport policy, independent of the engine's token/context limits."""
DEFAULTS = {"request_bytes": 1048576, "message_chars": 131072,
            "history_messages": 128, "history_chars": 240000,
            "response_chars": 1048576, "stream_bytes": 8388608, "timeout_seconds": 300}
CEILINGS = {"request_bytes": 8388608, "message_chars": 1048576,
            "history_messages": 1024, "history_chars": 1048576,
            "response_chars": 8388608, "stream_bytes": 67108864, "timeout_seconds": 3600}


def policy(config=None):
    raw = (config or {}).get("chat", {}).get("transport", {})
    if type(raw) is not dict or set(raw)-set(DEFAULTS):
        raise ValueError("invalid_chat_transport_policy")
    out = {**DEFAULTS, **raw}
    if any(type(v) is not int or not 1 <= v <= CEILINGS[k] for k,v in out.items()):
        raise ValueError("invalid_chat_transport_policy")
    return out


def options(raw=None):
    raw = {} if raw is None else raw
    if type(raw) is not dict or set(raw)-{"thinking", "reasoning_effort", "max_output_tokens"}:
        raise ValueError("invalid_generation_options")
    thinking = raw.get("thinking", "auto")
    effort = raw.get("reasoning_effort", "auto")
    if thinking not in ("auto", "on", "off") or effort not in ("auto", "minimal", "low", "medium", "high", "xhigh"):
        raise ValueError("invalid_generation_options")
    maximum = raw.get("max_output_tokens")
    if maximum is not None and (type(maximum) is not int or not 1 <= maximum <= 2147483647):
        raise ValueError("invalid_generation_options")
    if thinking == "off" and effort != "auto":
        raise ValueError("conflicting_thinking_options")
    return {"thinking": thinking, "reasoning_effort": effort, "max_output_tokens": maximum}


def upstream_options(raw=None, *, thinking_supported=None):
    chosen = options(raw)
    if thinking_supported is False and (chosen["thinking"] == "on" or chosen["reasoning_effort"] != "auto"):
        raise ValueError("thinking_not_supported")
    result = {}
    if chosen["thinking"] != "auto":
        result["enable_thinking"] = chosen["thinking"] == "on"
    if chosen["reasoning_effort"] != "auto":
        result["reasoning_effort"] = chosen["reasoning_effort"]
    if chosen["max_output_tokens"] is not None:
        result["max_tokens"] = chosen["max_output_tokens"]
    return result
