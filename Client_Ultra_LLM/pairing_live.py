"""WEB-03: HTTPS pairing with Manager; raw Client credentials never leave disk.

Client-side transport is strictly verified TLS without OS proxy. All sensitive
HTTP requests originate in local Python, not browser JavaScript. Bootstrap admin
permission must be granted separately by the Manager owner.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import ssl
from urllib.error import HTTPError, URLError
from urllib.request import Request, ProxyHandler, HTTPSHandler, build_opener

from live_client import load_profiles

_MAX_REPLY = 32 * 1024
_TICKET = re.compile(r"^[A-Za-z0-9_-]{20,100}$")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


class PairingRequestError(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def _api(profile, method: str, path: str, payload=None, *, authorized=False):
    try:
        context = ssl.create_default_context(cafile=str(profile["ca_cert"]))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
    except (OSError, ssl.SSLError) as error:
        raise PairingRequestError("manager_unreachable_or_untrusted") from error
    headers = {"Accept": "application/json"}
    if authorized:
        token = profile["token_file"].read_text(encoding="ascii").strip()
        if len(token) < 32:
            raise PairingRequestError("invalid_local_credentials")
        headers["Authorization"] = "Bearer " + token
    body = None
    if method == "POST":
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        if len(body) > 4096:
            raise PairingRequestError("request_too_large")
        headers["Content-Type"] = "application/json"
    req = Request(profile["endpoint"] + path, data=body,
                  headers=headers, method=method)
    opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
    try:
        with opener.open(req, timeout=6) as response:
            raw = response.read(_MAX_REPLY + 1)
            if len(raw) > _MAX_REPLY:
                raise PairingRequestError("response_too_large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise PairingRequestError("invalid_response")
            return result
    except HTTPError as error:
        if error.code == 405:
            raise PairingRequestError("manager_upgrade_required") from error
        if error.code in (401, 403):
            raise PairingRequestError("access_denied") from error
        if error.code == 429:
            raise PairingRequestError("rate_limited") from error
        if error.code == 409:
            raise PairingRequestError("request_conflict") from error
        raise PairingRequestError("manager_http_" + str(error.code)) from error
    except (OSError, URLError, ssl.SSLError, ValueError,
            json.JSONDecodeError) as error:
        raise PairingRequestError("manager_unreachable_or_untrusted") from error


def find_profile(folder: Path, manager_id: str):
    if not isinstance(manager_id, str) or not _ID.fullmatch(manager_id):
        raise ValueError("Invalid manager ID")
    profiles = load_profiles(folder / "managers.json")
    matches = [p for p in profiles if p["manager_id"] == manager_id]
    if len(matches) != 1:
        raise ValueError("Unknown Manager ID")
    return matches[0]


def submit_profile(folder: Path, manager_id: str):
    profile = find_profile(folder, manager_id)
    token = profile["token_file"].read_text(encoding="ascii").strip()
    if len(token) < 32:
        raise PairingRequestError("invalid_local_credentials")
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    data = _api(profile, "POST", "/v1/pairing/request",
                {"client_id": profile["client_id"], "token_sha256": digest})
    ticket_id = data.get("ticket_id")
    if (data.get("state") != "pending" or
            not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id)):
        raise PairingRequestError("invalid_registration_receipt")
    ticket = {"ticket_id": ticket_id, "state": "pending"}
    # Store only a non-credential request receipt in the protected profile.
    receipt = folder / (manager_id + ".pairing-receipt.json")
    receipt.write_text(json.dumps(ticket, separators=(",", ":")), encoding="utf-8")
    return {"state": "pending", "manager_id": manager_id}


def check_profile_ticket(folder: Path, manager_id: str):
    path = folder / (manager_id + ".pairing-receipt.json")
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    ticket_id = data.get("ticket_id")
    if not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id):
        return None
    profile = find_profile(folder, manager_id)
    result = _api(profile, "GET", "/v1/pairing/status/" + ticket_id)
    return result.get("state") if result.get("state") in (
        "pending", "approved", "denied", "expired", "unknown") else "unknown"


def admin_requests(folder: Path, manager_id: str):
    profile = find_profile(folder, manager_id)
    data = _api(profile, "GET", "/v1/pairing/requests", authorized=True)
    if data.get("manager_id") != manager_id or not isinstance(data.get("requests"), list):
        raise PairingRequestError("invalid_admin_response")
    return data


def admin_decision(folder: Path, manager_id: str, ticket_id: str,
                   allowed_slots=None, *, approve: bool):
    if not isinstance(ticket_id, str) or not _TICKET.fullmatch(ticket_id):
        raise ValueError("Invalid ticket ID")
    if approve:
        if not isinstance(allowed_slots, list) or any(
                not isinstance(x, str) or not _ID.fullmatch(x) for x in allowed_slots):
            raise ValueError("Invalid slot selection")
        payload = {"ticket_id": ticket_id, "allowed_slots": allowed_slots}
        path = "/v1/pairing/approve"
    else:
        payload = {"ticket_id": ticket_id}
        path = "/v1/pairing/deny"
    profile = find_profile(folder, manager_id)
    result = _api(profile, "POST", path, payload, authorized=True)
    if result.get("state") != ("approved" if approve else "denied"):
        raise PairingRequestError("invalid_decision_response")
    return {"state": result["state"]}
