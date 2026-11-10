"""Owner-operated enrollment for HTTPS Client profiles, with no secret in chat.

Generates a unique bearer token locally, stores it only inside a pre-protected
private directory, and prints only its SHA256 for administrative registration
on the Manager. Never transmits tokens to another machine or Git.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import re
import secrets
import shutil
import tempfile

from live_client import load_profiles

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")


def _validate_id(value: str, kind: str):
    if not _ID.fullmatch(value):
        raise ValueError("Invalid " + kind)
    return value


def _require_private_acl(parent: Path):
    if os.name != "nt":
        if parent.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
            raise PermissionError("Client directory must have mode 0700")
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
        raise PermissionError("Client private directory ACL is not protected")


def enroll(private_dir: Path, manager_id: str, client_id: str, endpoint: str,
           public_ca: Path, display_name: str):
    private_dir = private_dir.resolve(strict=True)
    if not private_dir.is_dir():
        raise ValueError("Client private folder must exist and be access-restricted")
    if private_dir.is_symlink():
        raise ValueError("Refusing symlink credential directory")
    _require_private_acl(private_dir)
    if not public_ca.is_file() or public_ca.suffix.lower() not in (".pem", ".crt"):
        raise ValueError("Expected existing public CA certificate")
    manager_id = _validate_id(manager_id, "manager_id")
    client_id = _validate_id(client_id, "client_id")
    if not isinstance(display_name, str) or not 1 <= len(display_name.strip()) <= 80:
        raise ValueError("Invalid display name")
    manager_profile = {
        "manager_id": manager_id, "client_id": client_id,
        "display_name": display_name.strip(), "endpoint": endpoint,
        "ca_cert": f"{manager_id}.cert.pem",
        "token_file": f"{manager_id}.{client_id}.token"}
    cfgfile = private_dir / "managers.json"
    old = {"managers": []}
    if cfgfile.exists():
        old = json.loads(cfgfile.read_text(encoding="utf-8-sig"))
        if not isinstance(old, dict) or not isinstance(old.get("managers"), list):
            raise ValueError("Invalid current client registry")
        if any(row.get("manager_id") == manager_id for row in old["managers"]):
            raise ValueError("Manager already paired; refuse token replacement")
    if len(old["managers"]) >= 128:
        raise ValueError("Too many Manager profiles")
    token_path = private_dir / manager_profile["token_file"]
    ca_path = private_dir / manager_profile["ca_cert"]
    if token_path.exists() or ca_path.exists():
        raise FileExistsError("Existing pairing artifacts, refusing overwrite")
    token = secrets.token_urlsafe(48)
    digest = hashlib.sha256(token.encode("ascii")).hexdigest()
    created = []
    try:
        # O_EXCL prevents accidental replacement of any secret. Local ACLs
        # are inherited from the private directory (configured by the owner).
        fd = os.open(token_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created.append(token_path)
        with os.fdopen(fd, "w", encoding="ascii") as f:
            f.write(token)
        with ca_path.open("xb") as stream:
            created.append(ca_path)
            stream.write(public_ca.read_bytes())
        draft = dict(old)
        draft["managers"] = list(old["managers"]) + [manager_profile]
        temp = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=private_dir,
                prefix=".ultra-client-", suffix=".json", delete=False
            ) as stream:
                temp = Path(stream.name)
                json.dump(draft, stream, indent=2, ensure_ascii=False)
                stream.write("\n")
            load_profiles(temp)  # Reject bad endpoint before changing the registry.
            os.replace(temp, cfgfile)
            temp = None
        finally:
            if temp and temp.exists():
                temp.unlink()
    except Exception:
        for file in created:
            if file.exists():
                file.unlink()
        raise
    print("CLIENT_PROFILE_CREATED", manager_id, client_id)
    print("MANAGER_REGISTRATION_SHA256", digest)
    print("CA_PUBLIC_SHA256", hashlib.sha256(ca_path.read_bytes()).hexdigest())
    print("Raw token saved locally; do NOT paste token in any chat or GitHub")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-dir", type=Path, required=True)
    parser.add_argument("--manager-id", required=True)
    parser.add_argument("--client-id", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--ca-public-cert", type=Path, required=True)
    parser.add_argument("--display-name", required=True)
    a = parser.parse_args()
    enroll(a.private_dir, a.manager_id, a.client_id, a.endpoint,
           a.ca_public_cert, a.display_name)
