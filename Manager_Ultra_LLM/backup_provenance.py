"""Read-only verifier for the pinned Stage B code/state/task backup contract.

verify_backup(backups_root, trusted_manifest_sha256=EXTERNALLY_RECORDED_SHA)
requires an explicit pin from independently retained evidence, never the backup.
The caller establishes that trust and obtains authorization for any real audit.
No network, source execution, TLS loading, ACL changes or secret export occurs.
This proves correspondence to the pin, not authenticity at initial capture.
Use a quiescent, access-controlled local tree; metadata checks detect observed
races but cannot establish an atomic snapshot against a privileged writer.
"""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import stat
import xml.etree.ElementTree as ET

MANIFEST = "backup_manifest_PRIVATE.json"
MAX_METADATA = 8 * 1024 * 1024
MAX_ENTRIES = 100000
HEX = re.compile(r"[0-9a-fA-F]{64}\Z")
FIELDS = {"scope", "code_source", "state_source", "code", "state",
          "task_xml_canonical_utf8_sha256", "task_xml_file_sha256", "security", "sqlite_wal"}


class VerificationError(ValueError):
    """Stable reason code; contains no private paths, names or values."""


def require(condition, code):
    if not condition:
        raise VerificationError(code)


def _fingerprint(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_nlink,
            getattr(info, "st_file_attributes", 0), info.st_ctime_ns)


def _checked_stat(path):
    info = path.lstat()
    require(not stat.S_ISLNK(info.st_mode)
            and not getattr(info, "st_file_attributes", 0) & 0x400, "unsafe_link")
    require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode), "unsafe_file_type")
    require(not stat.S_ISREG(info.st_mode) or info.st_nlink == 1, "unsafe_hardlink")
    return info


def _check_chain(path):
    for part in (*reversed(path.parents), path):
        _checked_stat(part)


def _inventory(root):
    found = {}
    def visit(path, relative):
        info = _checked_stat(path)
        require(len(found) < MAX_ENTRIES, "inventory_limit")
        found[relative] = (stat.S_ISDIR(info.st_mode), _fingerprint(info))
        if stat.S_ISDIR(info.st_mode):
            with os.scandir(path) as entries:
                children = sorted(entries, key=lambda entry: entry.name)
            for child in children:
                visit(path / child.name, child.name if relative == "." else relative + "/" + child.name)
    visit(root, ".")
    return found


def _read_verified(path, expected_info, expected_size=None, capture=False):
    _check_chain(path)
    info = _checked_stat(path)
    require(stat.S_ISREG(info.st_mode) and _fingerprint(info) == expected_info, "file_changed")
    size = info.st_size
    require(expected_size is None or size == expected_size, "file_size_mismatch")
    require(not capture or size <= MAX_METADATA, "metadata_limit")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    digest, chunks = hashlib.sha256(), []
    with os.fdopen(descriptor, "rb") as stream:
        opened = _fingerprint(os.fstat(stream.fileno()))
        # CPython 3.12 Windows lstat/fstat can expose different ctime semantics
        # after utime. Compare identity/size/mtime across APIs, and retain ctime
        # in both same-API before/after comparisons.
        require(opened[:-1] == expected_info[:-1], "file_changed")
        remaining = size
        while remaining:
            chunk = stream.read(min(remaining, 1024 * 1024))
            require(bool(chunk), "file_changed")
            digest.update(chunk)
            if capture:
                chunks.append(chunk)
            remaining -= len(chunk)
        require(not stream.read(1) and _fingerprint(os.fstat(stream.fileno())) == opened,
                "file_changed")
    require(_fingerprint(_checked_stat(path)) == expected_info, "file_changed")
    return digest.hexdigest(), b"".join(chunks)


def _sha(value):
    return type(value) is str and HEX.fullmatch(value) is not None


def _relative(name):
    require(type(name) is str and name != "" and "\\" not in name, "unsafe_manifest_path")
    if name == ".":
        return
    for part in name.split("/"):
        reserved = part.split(".")[0].upper()
        require(part not in ("", ".", "..") and not part.endswith((" ", "."))
                and not any(ord(c) < 32 or c in ':*?"<>|' for c in part)
                and reserved not in {"CON", "PRN", "AUX", "NUL"}
                and re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", reserved) is None,
                "unsafe_manifest_path")


def _tree_schema(tree):
    require(type(tree) is dict and 1 < len(tree) < MAX_ENTRIES and "." in tree,
            "manifest_schema")
    require(len({name.casefold() for name in tree}) == len(tree), "manifest_schema")
    for name, row in tree.items():
        _relative(name)
        require(type(row) is dict and type(row.get("directory")) is bool, "manifest_schema")
        fields = {"directory", "sddl_owner_group_dacl"}
        if not row["directory"]:
            fields |= {"bytes", "sha256", "snapshot"}
            require(type(row.get("bytes")) is int and 0 <= row["bytes"] < 2**63
                    and _sha(row.get("sha256")) and type(row.get("snapshot")) is str,
                    "manifest_schema")
        require(set(row) == fields and type(row.get("sddl_owner_group_dacl")) is str,
                "manifest_schema")
        if name == ".":
            require(row["directory"], "manifest_schema")
        else:
            parent = name.rsplit("/", 1)[0] if "/" in name else "."
            require(type(tree.get(parent)) is dict and tree[parent].get("directory") is True,
                    "manifest_schema")
    require(any(not row["directory"] for row in tree.values()), "manifest_schema")


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "manifest_schema")
        result[key] = value
    return result


def _invalid_constant(value):
    raise VerificationError("manifest_schema")


def verify_backup(backups_root, *, trusted_manifest_sha256):
    """Return safe counts on success, raise VerificationError on any refusal.

    Root contains exactly code/, state/, task_original.xml and MANIFEST.
    Raw manifest SHA and both raw UTF-16/canonical UTF-8 task hashes are required.
    Stored SDDL is schema-checked metadata; current ACL/TLS health is not audited.
    No successful result may be used as a LIVE rollback or release authorization.
    """
    require(_sha(trusted_manifest_sha256), "trusted_pin_required")
    pin = trusted_manifest_sha256.lower()
    try:
        root = Path(os.path.abspath(backups_root))
        require(not str(root).startswith("\\\\"), "local_root_required")
        _check_chain(root)
        require(stat.S_ISDIR(_checked_stat(root).st_mode), "backup_root_required")
        before = _inventory(root)
        require(MANIFEST in before and not before[MANIFEST][0], "manifest_missing")
        digest, raw = _read_verified(root / MANIFEST, before[MANIFEST][1], capture=True)
        require(hmac.compare_digest(digest, pin), "trusted_manifest_mismatch")
        try:
            data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs,
                              parse_constant=_invalid_constant)
        except (UnicodeError, json.JSONDecodeError, RecursionError):
            raise VerificationError("manifest_schema") from None
        require(type(data) is dict and set(data) == FIELDS, "manifest_schema")
        for key in ("scope", "code_source", "state_source", "security", "sqlite_wal"):
            require(type(data[key]) is str and bool(data[key]), "manifest_schema")
        require(_sha(data["task_xml_canonical_utf8_sha256"])
                and _sha(data["task_xml_file_sha256"]), "manifest_schema")
        expected = {".": True, MANIFEST: False, "task_original.xml": False}
        counts = {}
        for tree in ("code", "state"):
            _tree_schema(data[tree])
            counts[tree + "_files"] = sum(not row["directory"] for row in data[tree].values())
            for name, row in data[tree].items():
                expected[tree if name == "." else tree + "/" + name] = row["directory"]
        require(set(before) == set(expected) and all(before[n][0] == directory
                for n, directory in expected.items()), "backup_inventory_mismatch")
        for tree in ("code", "state"):
            for name, row in data[tree].items():
                if not row["directory"]:
                    relative = tree + "/" + name
                    actual, _ = _read_verified(root / relative, before[relative][1], row["bytes"])
                    require(hmac.compare_digest(actual, row["sha256"].lower()), "file_hash_mismatch")
        task_sha, task_raw = _read_verified(root / "task_original.xml", before["task_original.xml"][1], capture=True)
        require(hmac.compare_digest(task_sha, data["task_xml_file_sha256"].lower()), "task_hash_mismatch")
        try:
            xml = task_raw.decode("utf-16")
            task = ET.fromstring(xml)
            require(task.tag.rsplit("}", 1)[-1] == "Task", "task_xml_invalid")
        except (UnicodeError, ET.ParseError):
            raise VerificationError("task_xml_invalid") from None
        require(hmac.compare_digest(hashlib.sha256(xml.encode("utf-8")).hexdigest(),
                                    data["task_xml_canonical_utf8_sha256"].lower()), "task_hash_mismatch")
        _check_chain(root)
        require(_inventory(root) == before, "backup_changed")
        return {"status": "PASS", "manifest_sha256": pin, **counts, "task_xml": "PASS",
                "read_only": True, "initial_authenticity": "NOT PROVEN"}
    except OSError:
        raise VerificationError("backup_unreadable") from None
    except RecursionError:
        raise VerificationError("inventory_limit") from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--trusted-manifest-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        result = verify_backup(args.backup_root, trusted_manifest_sha256=args.trusted_manifest_sha256)
    except VerificationError as error:
        print(json.dumps({"status": "FAIL", "reason": str(error), "read_only": True}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
