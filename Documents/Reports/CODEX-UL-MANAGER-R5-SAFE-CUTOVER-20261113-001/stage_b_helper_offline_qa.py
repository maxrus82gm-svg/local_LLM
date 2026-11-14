"""Backup-helper safety checks on synthetic files, confined to workspace/Test."""
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent


def main():
    began = time.perf_counter()
    assert socket.gethostname().upper() == "DESKTOP-SC96D3U"
    spec = importlib.util.spec_from_file_location("helper", OUT / "stage_b_prepare_server.py")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    root = ROOT / "Test" / OUT.name / ("backup_helper_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    root.mkdir(parents=True)
    source = root / "source"
    source.mkdir()
    (source / "unknown-empty").mkdir()
    (source / "logs").mkdir()
    (source / "unknown.bin").write_bytes(b"SYNTHETIC USER SENTINEL")
    (source / "logs/active.log").write_bytes(b"SYNTHETIC LOG\n")
    checks = []
    entries = helper.inventory(source)
    target = root / "backup"
    manifest = helper.copy_snapshot(source, target, entries, active_logs=True)
    helper.verify_snapshot(target, manifest)
    assert (target / "unknown-empty").is_dir()
    assert (target / "unknown.bin").read_bytes() == b"SYNTHETIC USER SENTINEL"
    assert "sddl_owner_group_dacl" in manifest["unknown.bin"]
    checks.append("complete inventory/bytes/empty directory/SDDL readback")
    try:
        helper.copy_snapshot(source, target, entries)
        raise AssertionError("Overwrote existing backup")
    except FileExistsError:
        checks.append("existing backup refused")
    (target / "unknown.bin").write_bytes(b"SYNTHETIC TAMPER")
    try:
        helper.verify_snapshot(target, manifest)
        raise AssertionError("Tampering accepted")
    except ValueError:
        checks.append("backup corruption refused")
    (source / "logs/active.log").write_bytes(b"SYNTHETIC LOG\nAPPEND\n")
    later = root / "snapshot-after-append"
    second = helper.copy_snapshot(source, later, entries, active_logs=True)
    helper.verify_snapshot(later, second)
    assert (later / "logs/active.log").read_bytes().endswith(b"APPEND\n")
    checks.append("live log captured at copy-time bounded size")
    real = root / "real"
    real.mkdir()
    junction = source / "forbidden-junction"
    subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(real)], capture_output=True, check=True)
    try:
        try:
            helper.inventory(source)
            raise AssertionError("Followed junction")
        except ValueError:
            checks.append("reparse point refused before backup")
    finally:
        junction.rmdir()  # This known test junction only, no recursive removal.
    try:
        helper.prepare({}, b"invalid")
        raise AssertionError("Server helper ran on home host")
    except RuntimeError:
        checks.append("home execution host denied before writes")
    result = {"status": "PASS", "scope": "Synthetic files under Test only", "root": str(root),
              "checks": checks, "count": len(checks), "exit_code": 0,
              "seconds": round(time.perf_counter() - began, 3)}
    with (OUT / "stage_b_helper_offline_qa.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
