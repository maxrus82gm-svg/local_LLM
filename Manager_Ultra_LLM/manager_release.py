"""Offline Manager R5 source release. Never manages tasks, processes or models.

Python 3.12 x64 + Windows are supplied by the destination; no pip dependencies.
Build/verify/stage affect only explicitly named new directories. A stage is NOT
an installation. No config, credential, TLS, state DB or model is packaged.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import stat
import zipfile

VERSION = "R5-compat-20261113.1"
TASK = "CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001"
RUNTIME = tuple(sorted((
    "live_manager.py", "chat_runtime.py", "chat_settings.py", "control_runtime.py",
    "slot_registry.py", "resource_policy.py", "colibri2_runner.py", "windows_process.py",
    "manager_core.py", "launch_contract.py", "resource_catalog.py", "server_preflight.py",
    "server_runner.py", "pairing_server.py", "pairing_inbox.py", "pairing_workflow.py",
    "service_core.py", "index.html", "manager_release.py")))
MEMBERS = frozenset((*RUNTIME, "RELEASE.json", "SHA256SUMS.txt"))
MAX_FILE = 8 * 1024 * 1024


def sha(data):
    return hashlib.sha256(data).hexdigest()


def canonical(data):
    return (json.dumps(data, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def no_links(path):
    path = Path(path).absolute()
    for node in (path, *path.parents):
        if node.is_symlink() or node.is_junction():
            raise ValueError("Link/reparse path refused")
    return path


def dependency_check(payload):
    """Reject omitted sibling Python modules, including lazy imports."""
    names = {Path(name).stem for name in RUNTIME if name.endswith(".py")}
    # All Manager modules are stdlib-only. Explicitly check local import closure.
    stdlib = __import__("sys").stdlib_module_names
    for name in names:
        tree = ast.parse(payload[name + ".py"].decode("utf-8-sig"))
        for node in ast.walk(tree):
            imported = ([alias.name.split(".")[0] for alias in node.names]
                        if isinstance(node, ast.Import) else
                        [node.module.split(".")[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            if set(imported) - names - stdlib - {"__future__"}:
                raise ValueError("Unpackaged/non-stdlib dependency in " + name)


def validate(payload):
    if set(payload) != MEMBERS or any(len(v) > MAX_FILE for v in payload.values()):
        raise ValueError("Release member set/size mismatch")
    meta = json.loads(payload["RELEASE.json"])
    if meta.get("version") != VERSION or meta.get("task") != TASK:
        raise ValueError("Release identity mismatch")
    expected = {name: sha(payload[name]) for name in RUNTIME}
    if meta.get("files") != expected:
        raise ValueError("Release payload hash mismatch")
    sums = "".join(f"{sha(payload[name])}  {name}\n" for name in sorted((*RUNTIME, "RELEASE.json")))
    if payload["SHA256SUMS.txt"] != sums.encode("ascii"):
        raise ValueError("SHA256 manifest mismatch")
    dependency_check(payload)
    return meta


def read_package(path):
    path = no_links(path)
    if path.is_dir():
        found = list(path.iterdir())
        if {p.name for p in found} != MEMBERS or any(
                no_links(p).is_dir() or p.stat().st_size > MAX_FILE for p in found):
            raise ValueError("Unexpected directory member")
        payload = {p.name: p.read_bytes() for p in found}
    else:
        if path.stat().st_size > MAX_FILE * 4:
            raise ValueError("Oversized archive")
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if (len(entries) != len(MEMBERS) or {e.filename for e in entries} != MEMBERS
                    or any(e.file_size > MAX_FILE or e.flag_bits & 1
                           or stat.S_IFMT(e.external_attr >> 16) == stat.S_IFLNK for e in entries)):
                raise ValueError("Unsafe archive members")
            payload = {e.filename: archive.read(e) for e in entries}
    validate(payload)
    return payload


def write_new(payload, target):
    target = no_links(target)
    if target.exists() or not target.parent.is_dir():
        raise ValueError("Destination must be a NEW directory with existing parent")
    target.mkdir()
    for name, data in sorted(payload.items()):
        with (target / name).open("xb") as stream:
            stream.write(data)
    return target


def build(source, output, base_head):
    source, output = no_links(source), no_links(output)
    payload = {name: no_links(source / name).read_bytes() for name in RUNTIME}
    dependency_check(payload)
    metadata = {"task": TASK, "version": VERSION, "base_head": base_head,
                "provenance": "Local working tree; files pinned by SHA256, NOT an immutable task commit",
                "runtime": "Windows x64, existing CPython 3.12 x64, stdlib only",
                "configuration": "External existing private config/auth/TLS/state; never overwritten",
                "control": "No model autostart. Missing owner_go/control_models stay disabled",
                "files": {name: sha(data) for name, data in sorted(payload.items())}}
    payload["RELEASE.json"] = canonical(metadata)
    payload["SHA256SUMS.txt"] = "".join(
        f"{sha(payload[name])}  {name}\n" for name in sorted(payload)).encode("ascii")
    validate(payload)
    write_new(payload, output)
    archive_path = output.with_suffix(".zip")
    # Refuse replacement; byte-for-byte reproducible regardless of file mtimes.
    with archive_path.open("xb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(payload.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(item, data)
    read_package(archive_path)
    return {"directory": str(output), "zip": str(archive_path),
            "zip_sha256": sha(archive_path.read_bytes()), "files": len(payload), "version": VERSION}


def stage(package, target):
    payload = read_package(package)  # Entire archive verified BEFORE first write.
    output = write_new(payload, target)
    read_package(output)
    return {"status": "STAGED_ONLY", "directory": str(output), "files": len(payload),
            "services_changed": False, "models_started": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    build_cmd = commands.add_parser("build")
    build_cmd.add_argument("--source", type=Path, default=Path(__file__).parent)
    build_cmd.add_argument("--output", type=Path, required=True)
    build_cmd.add_argument("--base-head", required=True)
    verify_cmd = commands.add_parser("verify")
    verify_cmd.add_argument("package", type=Path)
    stage_cmd = commands.add_parser("stage")
    stage_cmd.add_argument("package", type=Path)
    stage_cmd.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "build":
        result = build(args.source, args.output, args.base_head)
    elif args.action == "stage":
        result = stage(args.package, args.target)
    else:
        result = {"status": "VERIFIED", "release": validate(read_package(args.package))}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
