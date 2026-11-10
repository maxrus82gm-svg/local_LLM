"""Explicit admin-only pairing registration for an installed Ultra LLM Manager.

Never receives a raw bearer token: the CLIENT creates it privately and supplies
only SHA-256. Only edits the local Manager config (outside Git); no networking,
process launches, firewall changes, or certificate/key exports.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import stat
import subprocess
import re
import tempfile

from live_manager import load_config

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _id(value: str, field: str) -> str:
    if not _NAME.fullmatch(value):
        raise ValueError(f"Invalid {field}")
    return value


def _require_private_acl(parent: Path):
    """Refuse an inherited or broadly readable credential directory."""
    if os.name != "nt":
        if parent.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError("Private directory must have mode 0700")
        return
    # Quote the literal path for -Command; extra process arguments are not
    # reliable as PowerShell's $args across Windows remoting environments.
    literal = "'" + str(parent).replace("'", "''") + "'"
    check = (
        "$ErrorActionPreference='Stop';"
        "$a=Get-Acl -LiteralPath " + literal + ";"
        "if (-not $a.AreAccessRulesProtected) {exit 8};"
        "$bad=@('S-1-1-0','S-1-5-11','S-1-5-32-545','S-1-5-2');"
        "foreach($rule in $a.Access){"
        "if($rule.AccessControlType -eq 'Allow'){"
        "try{$sid=$rule.IdentityReference.Translate("
        "[Security.Principal.SecurityIdentifier]).Value}catch{exit 9};"
        "if($bad -contains $sid){exit 10}"
        "}};exit 0"
    )
    command = ["powershell.exe", "-NoProfile", "-NonInteractive",
               "-Command", check]
    result = subprocess.run(command, capture_output=True,
                            timeout=10, check=False)
    if result.returncode:
        raise PermissionError("Manager private directory ACL is not protected")


def _trusted_parent(file: Path):
    file = file.absolute()
    if file.suffix.lower() != ".json" or file.name.lower() != "manager.json":
        raise ValueError("Refusing non-manager.json destination")
    parent = file.parent
    if not parent.exists() or not parent.is_dir() or parent.is_symlink():
        raise ValueError("Pre-provisioned protected private directory required")
    _require_private_acl(parent)
    return file


def _write_config(dest: Path, data: dict, *, new: bool):
    """Atomic replace, no partial config; root ACL must be owner-verified."""
    dest = _trusted_parent(dest)
    if new and dest.exists():
        raise FileExistsError("Manager already paired; refusing overwrite")
    if not new and not dest.exists():
        raise FileNotFoundError("Manager config absent")
    temp = None
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=dest.parent,
                suffix=".json", prefix=".ultra-manager-", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(data, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
        load_config(temp)  # Fail closed on invalid Manager settings.
        # Windows files normally inherit the protected parent directory ACL.
        if new and dest.exists():
            raise FileExistsError("Concurrent Manager registration")
        os.replace(temp, dest)
        temp = None
    finally:
        if temp and temp.exists():
            temp.unlink()


def _parse_slot(spec: str) -> dict:
    bits = spec.split(":")
    if len(bits) not in (2, 3):
        raise ValueError("Use --slot slot1:8000:protected")
    slot_id = _id(bits[0], "slot ID")
    port = int(bits[1])
    if not 1024 <= port <= 65535:
        raise ValueError("Invalid slot port")
    flag = bits[2] if len(bits) == 3 else "normal"
    if flag not in ("normal", "protected"):
        raise ValueError("Invalid protection flag")
    return {"slot_id": slot_id, "api_port": port,
            "protected": flag == "protected"}


def _entry(client_id: str, digest: str, allowed: list[str]) -> dict:
    if not _SHA256.fullmatch(digest):
        raise ValueError("Expected SHA256 of client-generated random token")
    if len(set(allowed)) != len(allowed):
        raise ValueError("Repeated slot permission")
    return {"client_id": _id(client_id, "client ID"), "sha256": digest,
            "allowed_slots": allowed}


def create(args):
    root = _trusted_parent(args.config)
    slots = [_parse_slot(s) for s in args.slot]
    ips = [str(ipaddress.ip_address(x)) for x in args.allow_ip]
    record = {
        "manager_id": _id(args.manager_id, "manager ID"),
        "display_name": args.name,
        "bind_host": args.bind,
        "listen_port": args.port,
        "colibri_root": str(args.colibri_root.absolute()),
        "models_root": str(args.models_root.absolute()),
        "cert_file": str(args.cert.absolute()),
        "key_file": str(args.key.absolute()),
        "slots": slots,
        "allowed_client_ips": ips,
        "clients": [_entry(args.client_id, args.token_sha256, args.grant_slot)]}
    if not args.cert.is_file() or not args.key.is_file():
        raise FileNotFoundError("Server TLS cert/key must already exist")
    if not args.colibri_root.is_dir() or not args.models_root.is_dir():
        raise FileNotFoundError("Colibri/models paths not found on this host")
    _write_config(root, record, new=True)
    print("MANAGER_CONFIG_CREATED: client hash only; no raw token stored")


def grant(args):
    record = load_config(_trusted_parent(args.config))
    entry = _entry(args.client_id, args.token_sha256, args.grant_slot)
    if entry["client_id"] in {c["client_id"] for c in record["clients"]}:
        raise ValueError("Client already registered; use revoke and re-pair")
    record["clients"].append(entry)
    _write_config(args.config, record, new=False)
    print("CLIENT_GRANT_SAVED: active Manager reloads client list each request")


def revoke(args):
    record = load_config(_trusted_parent(args.config))
    record["clients"] = [
        c for c in record["clients"] if c["client_id"] != args.client_id]
    if len(record["clients"]) == 0:
        raise ValueError("Refusing to revoke last client; stop Manager first")
    _write_config(args.config, record, new=False)
    print("CLIENT_REVOKED: existing issued token no longer permitted")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    init = sub.add_parser("create")
    init.add_argument("--manager-id", required=True)
    init.add_argument("--name", required=True)
    init.add_argument("--bind", required=True)
    init.add_argument("--port", required=True, type=int)
    init.add_argument("--colibri-root", required=True, type=Path)
    init.add_argument("--models-root", required=True, type=Path)
    init.add_argument("--cert", required=True, type=Path)
    init.add_argument("--key", required=True, type=Path)
    init.add_argument("--slot", action="append", required=True)
    init.add_argument("--allow-ip", action="append", required=True)
    init.add_argument("--client-id", required=True)
    init.add_argument("--token-sha256", required=True)
    init.add_argument("--grant-slot", action="append", default=[])
    init.set_defaults(func=create)
    for action, func in (("grant", grant), ("revoke", revoke)):
        p = sub.add_parser(action)
        p.add_argument("--client-id", required=True)
        if action == "grant":
            p.add_argument("--token-sha256", required=True)
            p.add_argument("--grant-slot", action="append", default=[])
        p.set_defaults(func=func)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
