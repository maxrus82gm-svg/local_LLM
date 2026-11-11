"""Owner-approved pairing grants for the live read-only Manager.

This module is deliberately restricted to Manager config clients/permissions.
It never grants control of models or alters the Windows Firewall. New client
IP addresses must already be explicitly allowed in Manager and firewall.
"""
from __future__ import annotations

from pathlib import Path

from live_manager import load_config
from pairing_server import _entry, _write_config, manager_config_lock


def grant_pending(config_file: Path, client_id: str, digest: str,
                  source_ip: str, allowed_slots: list[str]) -> None:
    with manager_config_lock(config_file):
        config = load_config(config_file)
        if source_ip not in config["allowed_client_ips"]:
            raise PermissionError("Client source IP requires a separate administrator allowlist decision")
        if client_id in {row["client_id"] for row in config["clients"]}:
            raise ValueError("Client already granted")
        if digest in {row["sha256"] for row in config["clients"]}:
            raise ValueError("Repeated credential digest")
        slots = {row["slot_id"] for row in config["slots"]}
        if len(set(allowed_slots)) != len(allowed_slots) or any(
                x not in slots for x in allowed_slots):
            raise ValueError("Unknown/repeated slot")
        client = _entry(client_id, digest, allowed_slots)
        client["pairing_admin"] = False
        config["clients"].append(client)
        # Keeps all other existing clients/roles in one protected atomic write.
        _write_config(config_file, config, new=False)


def request_summary(config):
    return {"manager_id": config["manager_id"],
            "slots": [{"slot_id": row["slot_id"],
                       "protected": bool(row.get("protected", False))}
                      for row in config["slots"]]}
