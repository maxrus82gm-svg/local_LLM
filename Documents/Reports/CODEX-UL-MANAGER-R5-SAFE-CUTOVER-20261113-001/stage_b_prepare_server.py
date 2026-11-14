"""B-only protected backup/staging helper, executed in server memory with -B.

Never stops processes, edits existing files, runs a listener or deletes anything.
Private content/SDDL/task XML stay in the new protected server directory.
"""
from datetime import datetime, timezone
import base64
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import xml.etree.ElementTree as ET
import zipfile

EXPECTED_ZIP = "ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2"
REPARSE = 0x400


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def no_links(path):
    path = Path(path).absolute()
    for item in (path, *path.parents):
        if item.exists() and item.lstat().st_file_attributes & REPARSE:
            raise ValueError("Reparse path refused")
    return path


def inventory(root):
    root = no_links(root)
    if not root.is_dir():
        raise ValueError("Source directory absent")
    result = {".": {"directory": True}}
    for parent, directories, files in os.walk(root, followlinks=False):
        for name in (*directories, *files):
            path = no_links(Path(parent) / name)
            stat = path.stat()
            result[path.relative_to(root).as_posix()] = {"directory": path.is_dir(),
                "bytes": stat.st_size if path.is_file() else 0, "mtime_ns": stat.st_mtime_ns}
            if path.is_file():
                with path.open("rb"):
                    pass  # Required backup read access, without locking writers.
    return result


def security_descriptor(path):
    """Read owner/group/DACL as SDDL. No audit-policy or permission changes."""
    advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    get_info = advapi.GetNamedSecurityInfoW
    get_info.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_uint,
                        ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
    get_info.restype = ctypes.c_uint
    to_text = advapi.ConvertSecurityDescriptorToStringSecurityDescriptorW
    to_text.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                       ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(ctypes.c_uint)]
    to_text.restype = ctypes.c_int
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    descriptor, text, length = ctypes.c_void_p(), ctypes.c_void_p(), ctypes.c_uint()
    error = get_info(str(path), 1, 7, None, None, None, None, ctypes.byref(descriptor))
    if error:
        raise OSError(error, "Security descriptor read refused")
    try:
        if not to_text(descriptor, 1, 7, ctypes.byref(text), ctypes.byref(length)):
            raise ctypes.WinError(ctypes.get_last_error())
        return ctypes.wstring_at(text)
    finally:
        if text:
            kernel.LocalFree(text)
        kernel.LocalFree(descriptor)


def copy_snapshot(source, target, entries, *, active_logs=False):
    """Copy all entries. Only append-only log prefixes can grow during snapshot."""
    source, target = no_links(source), no_links(target)
    if target.exists():
        raise FileExistsError("Never overwrite a backup")
    target.mkdir()
    manifest = {}
    for relative, metadata in sorted(entries.items(), key=lambda pair: (len(Path(pair[0]).parts), pair[0])):
        src = no_links(source / relative)
        dst = target / relative
        if relative == "." or metadata["directory"]:
            if relative != ".":
                dst.mkdir()
            manifest[relative] = {"directory": True, "sddl_owner_group_dacl": security_descriptor(src)}
            continue
        size = src.stat().st_size
        digest = hashlib.sha256()
        with src.open("rb") as incoming, dst.open("xb") as outgoing:
            remaining = size
            while remaining:
                chunk = incoming.read(min(1024 * 1024, remaining))
                if not chunk:
                    raise ValueError("Source shrank during snapshot")
                digest.update(chunk)
                outgoing.write(chunk)
                remaining -= len(chunk)
        if file_sha(dst) != digest.hexdigest():
            raise ValueError("Backup readback mismatch")
        dynamic = active_logs and Path(relative).parts[0].lower() == "logs"
        with src.open("rb") as current:
            prefix = hashlib.sha256()
            left = size
            while left:
                chunk = current.read(min(left, 1024 * 1024))
                if not chunk:
                    raise ValueError("Source changed during snapshot")
                prefix.update(chunk)
                left -= len(chunk)
            grew = bool(current.read(1))
        if prefix.hexdigest() != digest.hexdigest() or (grew and not dynamic):
            raise ValueError("Non-log source changed during snapshot")
        manifest[relative] = {"directory": False, "bytes": size, "sha256": digest.hexdigest(),
            "sddl_owner_group_dacl": security_descriptor(src),
            "snapshot": "captured log prefix; live append permitted" if dynamic else "stable exact file"}
        os.utime(dst, ns=(src.stat().st_atime_ns, metadata["mtime_ns"]))
    return manifest


def verify_snapshot(root, manifest):
    actual = inventory(root)
    if set(actual) != set(manifest):
        raise ValueError("Backup inventory mismatch")
    for relative, row in manifest.items():
        path = root / relative
        if path.is_dir() != row["directory"]:
            raise ValueError("Backup entry type mismatch")
        if not row["directory"] and (path.stat().st_size != row["bytes"] or file_sha(path) != row["sha256"]):
            raise ValueError("Backup verification failed")


def write_json(path, value):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run_python(command):
    # Ignore copied legacy __pycache__ as well as preventing new bytecode writes.
    unused_cache = Path(__file__).resolve().parent / "_no_bytecode_cache"
    result = subprocess.run([sys.executable, "-X", "utf8", "-X", "pycache_prefix=" + str(unused_cache), "-I", "-B", *command],
                            capture_output=True, timeout=25,
                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if result.returncode:
        raise RuntimeError("Isolated Python check failed; exit=" + str(result.returncode))
    return result.stdout.decode("utf-8-sig").strip()


def prepare(params, package_bytes):
    if socket.gethostname().upper() != "DESKTOP-KT4G5SM":
        raise RuntimeError("Server execution required")
    root = no_links(Path(params["maintenance_root"]))
    code = no_links(Path(r"C:\Server\Ultra_LLM\Manager_Live"))
    state = no_links(Path(r"C:\ProgramData\UltraLLM\Manager"))
    if root.parent != Path(r"C:\ProgramData\UltraLLM") or not root.name.startswith("Manager_R5_STAGEB_"):
        raise ValueError("Unexpected maintenance destination")
    if not root.is_dir() or {p.name for p in root.iterdir()} != {"incoming"}:
        raise ValueError("New protected directory with only verified public incoming files required")
    if sha(package_bytes) != EXPECTED_ZIP:
        raise ValueError("Authoritative ZIP mismatch")
    code_files, state_files = inventory(code), inventory(state)
    if any(Path(name).suffix.lower() in (".db", ".sqlite", ".sqlite3") or name.lower().endswith(("-wal", "-shm"))
           for name, row in (*code_files.items(), *state_files.items()) if not row["directory"]):
        raise ValueError("Unexpected SQLite/WAL requires a consistent backup plan")
    for name, expected in params["source_top_hashes"].items():
        if file_sha(code / name) != expected:
            raise ValueError("Live code differs from approved preflight")
    config = state / "private/manager.json"
    if file_sha(config) != params["config_sha256"]:
        raise ValueError("Live config changed")
    cfg = json.loads(config.read_text(encoding="utf-8-sig"))
    if cfg.get("control", {}).get("owner_go") is True:
        raise ValueError("Control must remain disabled")
    if any(Path(cfg[k]).resolve().parent != (state / "private").resolve() for k in ("cert_file", "key_file")):
        raise ValueError("External private dependencies not in backup scope")
    estimated = sum(row.get("bytes", 0) for row in (*code_files.values(), *state_files.values()))
    if shutil.disk_usage(root).free < estimated * 4 + 1024 ** 3:
        raise ValueError("Insufficient backup/stage space")
    backups = root / "backups"
    backups.mkdir()
    code_manifest = copy_snapshot(code, backups / "code", code_files)
    state_manifest = copy_snapshot(state, backups / "state", state_files, active_logs=True)
    verify_snapshot(backups / "code", code_manifest)
    verify_snapshot(backups / "state", state_manifest)
    xml = base64.b64decode(params["task_xml_utf8_b64"]).decode("utf-8")
    if sha(xml.encode("utf-8")) != params["task_xml_sha256"]:
        raise ValueError("Task XML differs from preflight")
    xml_bytes = xml.encode("utf-16")
    task_file = backups / "task_original.xml"
    with task_file.open("xb") as stream:
        stream.write(xml_bytes)
    ET.fromstring(task_file.read_bytes())
    if sha(task_file.read_bytes().decode("utf-16").encode("utf-8")) != params["task_xml_sha256"]:
        raise ValueError("Task XML backup readback failed")
    private_manifest = {"scope": "FULL code/state trees; logs captured as bounded point-in-time prefixes",
        "code_source": str(code), "state_source": str(state),
        "code": code_manifest, "state": state_manifest,
        "task_xml_canonical_utf8_sha256": params["task_xml_sha256"],
        "task_xml_file_sha256": file_sha(task_file),
        "security": "Original owner/group/DACL SDDL recorded; backups inherit restrictive maintenance ACL, never source broad ACL",
        "sqlite_wal": "Not present in source inventory"}
    manifest_file = backups / "backup_manifest_PRIVATE.json"
    write_json(manifest_file, private_manifest)
    # Restore rehearsal into a NEW protected copy, never working directories.
    rehearsal = root / "rollback_rehearsal"
    rehearsal.mkdir()
    shutil.copytree(backups / "code", rehearsal / "code")
    shutil.copytree(backups / "state/private", rehearsal / "private")
    verify_snapshot(rehearsal / "code", code_manifest)
    for name, row in state_manifest.items():
        if name.startswith("private/") and not row["directory"]:
            if file_sha(rehearsal / name) != row["sha256"]:
                raise ValueError("Restored private bytes mismatch")
    restored_cert = rehearsal / "private" / Path(cfg["cert_file"]).name
    restored_key = rehearsal / "private" / Path(cfg["key_file"]).name
    ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER).load_cert_chain(restored_cert, restored_key)
    old_import = run_python(["-c", "import sys;sys.path.insert(0,sys.argv[1]);import live_manager,pairing_workflow;print('OLD_IMPORT_OK')", str(rehearsal / "code")])
    if old_import != "OLD_IMPORT_OK":
        raise ValueError("Restored old runtime import failed")
    # Only the externally pinned PUBLIC archive/verifier is executed for staging.
    package_dir = root / "package"
    package_dir.mkdir()
    package = package_dir / "UltraLLM_Manager_R5_compat_Win64.zip"
    with package.open("xb") as stream:
        stream.write(package_bytes)
    tools = root / "package_tools"
    tools.mkdir()
    with zipfile.ZipFile(package) as archive:
        verifier_bytes = archive.read("manager_release.py")
    if sha(verifier_bytes) != params["verifier_sha256"]:
        raise ValueError("Verifier provenance mismatch")
    verifier_path = tools / "manager_release.py"
    with verifier_path.open("xb") as stream:
        stream.write(verifier_bytes)
    spec = importlib.util.spec_from_file_location("pinned_manager_release", verifier_path)
    release = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(release)
    release.read_package(package)
    staged = root / "staging"
    stage_result = release.stage(package, staged)
    stage_meta = release.validate(release.read_package(staged))
    check_config = run_python(["-c", "import runpy,sys;from pathlib import Path;root=sys.argv.pop(1);sys.path.insert(0,root);sys.argv[0]=str(Path(root)/'live_manager.py');runpy.run_path(sys.argv[0],run_name='__main__')",
                               str(staged), "--config", str(config), "--check-config"])
    if check_config != "MANAGER_CONFIGURATION_OK":
        raise ValueError("Staged config check failed")
    imports = run_python(["-c", "import sys;sys.path.insert(0,sys.argv[1]);import live_manager,control_runtime,pairing_workflow;print('R5_IMPORT_OK')", str(staged)])
    if imports != "R5_IMPORT_OK":
        raise ValueError("Staged imports failed")
    release.read_package(staged)  # Imports/check-config must leave no pycache/state.
    # Static config/auth/TLS bytes must remain unchanged; logs may append normally.
    for name, row in state_manifest.items():
        if not row["directory"] and Path(name).parts[0].lower() != "logs" and file_sha(state / name) != row["sha256"]:
            raise ValueError("Live private state changed")
    if set(inventory(code)) != set(code_manifest):
        raise ValueError("Live code inventory changed")
    for name, row in code_manifest.items():
        if not row["directory"] and file_sha(code / name) != row["sha256"]:
            raise ValueError("Live code bytes changed")
    if any(Path(n).suffix.lower() in (".db", ".sqlite", ".sqlite3") or n.lower().endswith(("-wal", "-shm"))
           for n, row in inventory(state).items() if not row["directory"]):
        raise ValueError("State database appeared during maintenance")
    summary = {"status": "BACKUP_STAGING_PREPARED", "maintenance_root": str(root),
        "backup_code": str(backups / "code"), "backup_state": str(backups / "state"),
        "backup_task_xml": str(task_file), "private_manifest": str(manifest_file),
        "private_manifest_sha256": file_sha(manifest_file),
        "code_files": sum(not row["directory"] for row in code_manifest.values()),
        "state_files": sum(not row["directory"] for row in state_manifest.values()),
        "code_directories": sum(row["directory"] for row in code_manifest.values()),
        "state_directories": sum(row["directory"] for row in state_manifest.values()),
        "sqlite_wal": "NOT PRESENT / N/A", "original_acl_owner_group_dacl_recorded": True,
        "log_snapshot": "Fixed captured lengths; no global atomic log snapshot claimed",
        "backup_readback": "PASS", "restored_private_bytes_and_tls_pair": "PASS",
        "restored_old_runtime_import": "PASS", "staging": str(staged),
        "zip_sha256": file_sha(package), "stage_files": stage_result["files"],
        "release_version": stage_meta["version"], "staged_config": check_config,
        "staged_imports": imports, "working_code_state_bytes_unchanged": True,
        "listener_or_model_start": False, "live_rollback": "NOT RUN", "stage_c_d": "NOT RUN"}
    write_json(root / "summary_PUBLIC.json", summary)
    return summary


if __name__ == "__main__":
    try:
        parameters = json.loads(base64.b64decode(sys.argv[1]))
        package_path = no_links(Path(sys.argv[2]))
        if package_path.parent != Path(parameters["maintenance_root"]) / "incoming":
            raise ValueError("Incoming package escaped new maintenance directory")
        data = package_path.read_bytes()
        print(json.dumps(prepare(parameters, data), ensure_ascii=False))
    except Exception as error:
        print(json.dumps({"status": "BLOCKED", "phase": "B protected backup/staging", "error_type": type(error).__name__,
                          "error": str(error), "partial_new_directory_retained": True}))
        raise SystemExit(2)
