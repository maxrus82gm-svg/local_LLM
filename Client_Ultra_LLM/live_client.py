"""Ultra LLM Client: real multi-manager HTTPS read-only client.

No simulated states and no raw tokens embedded in source/config. Every Manager
profile has its own CA certificate and per-client token file outside the repo.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import ssl
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, HTTPSHandler, ProxyHandler, build_opener

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def load_profiles(config_path: Path) -> list[dict]:
    cfg = json.loads(config_path.read_text(encoding="utf-8-sig"))
    if not isinstance(cfg, dict) or not isinstance(cfg.get("managers"), list):
        raise ValueError("Missing managers")
    if not cfg["managers"]:
        raise ValueError("No Managers configured")
    result, seen = [], set()
    for raw in cfg["managers"]:
        if not isinstance(raw, dict):
            raise ValueError("Invalid profile")
        mid = raw.get("manager_id")
        if not isinstance(mid, str) or not _ID.fullmatch(mid) or mid in seen:
            raise ValueError("Invalid/repeated manager_id")
        seen.add(mid)
        endpoint = raw.get("endpoint")
        if not isinstance(endpoint, str):
            raise ValueError("Missing endpoint")
        url = urlsplit(endpoint)
        try:
            port = url.port
        except ValueError as error:
            raise ValueError("Invalid manager port") from error
        if (url.scheme != "https" or not url.hostname or
                url.username or url.password or url.query or url.fragment or
                url.path not in ("", "/") or not port):
            raise ValueError("HTTPS host:port required")
        row = {"manager_id": mid,
               "display_name": str(raw.get("display_name", mid))[:80],
               "endpoint": f"https://{url.netloc}",
               "ca_cert": (config_path.parent / raw["ca_cert"]).resolve(),
               "token_file": (config_path.parent / raw["token_file"]).resolve()}
        result.append(row)
    return result


def fetch_one(profile: dict, timeout: float = 6.0) -> dict:
    row = {"manager_id": profile["manager_id"],
           "name": profile["display_name"],
           "endpoint": profile["endpoint"],
           "status": "unreachable", "data": None, "error": None}
    try:
        token = profile["token_file"].read_text(encoding="ascii").strip()
        if len(token) < 32:
            raise ValueError("Token too short")
        context = ssl.create_default_context(cafile=str(profile["ca_cert"]))
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        req = Request(profile["endpoint"] + "/v1/snapshot",
                      headers={"Authorization": "Bearer " + token,
                               "Accept": "application/json"})
        # Ignore system HTTPS_PROXY: never send private Manager tokens to an unrelated proxy.
        opener = build_opener(ProxyHandler({}), HTTPSHandler(context=context))
        with opener.open(req, timeout=timeout) as response:
            if response.status != 200:
                raise ValueError("Unexpected response")
            payload = json.loads(response.read(256 * 1024))
        if (not isinstance(payload, dict) or
                payload.get("schema") != "ultra.manager.live.v1" or
                payload.get("source") != "LIVE_HOST" or
                payload.get("manager_id") != profile["manager_id"] or
                payload.get("admission_enabled") is not False or
                payload.get("reservation_granted") is not False or
                not isinstance(payload.get("slots"), list) or
                not isinstance(payload.get("memory"), dict)):
            raise ValueError("Invalid Manager response")
        row["data"] = payload
        row["status"] = "online"
    except HTTPError as error:
        row["error"] = ("unauthorized" if error.code == 401 else
                        "http_" + str(error.code))
    except (OSError, URLError, ssl.SSLError, ValueError, KeyError,
            json.JSONDecodeError):
        row["error"] = "connection_or_config_error"
    return row


def fetch_all(profiles: list[dict]) -> list[dict]:
    with ThreadPoolExecutor(max_workers=min(8, len(profiles))) as pool:
        return list(pool.map(fetch_one, profiles))


def main():
    parser = argparse.ArgumentParser(description="Live multi-Manager client")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    profiles = load_profiles(args.config.resolve())
    results = fetch_all(profiles)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for item in results:
            print(f"[{item['manager_id']}] {item['name']}: {item['status']}")
            if item["status"] != "online":
                print("  " + str(item["error"]))
                continue
            data = item["data"]
            memory = data.get("memory", {})
            print(f"  host={data.get('host')} RAM={memory.get('free_gib', '?')} GiB free")
            for slot in data["slots"]:
                names = ", ".join(slot.get("models", [])) or "—"
                print(f"  {slot['slot_id']}:{slot['api_port']} | "
                      f"{slot['engine_state']} | {slot['availability']} | {names}")
            for model in data.get("models", []):
                print(f"  disk: {model['directory_name']} [{model['evidence']}]")
    return 0 if all(x["status"] == "online" for x in results) else 2


if __name__ == "__main__":
    sys.exit(main())
