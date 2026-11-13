"""Stage A only: immutable release checks and reuse of existing offline QA.

No remote access, private profile access, deployment or service APIs. All scratch
files reside under workspace/Test. Earlier evidence is never overwritten.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
OLD_ID = "CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001"
OLD = ROOT / "Documents/Reports" / OLD_ID
ZIP = ROOT / "Releases/Manager" / OLD_ID / "UltraLLM_Manager_R5_compat_Win64.zip"
EXPECTED = "ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2"
sys.path.insert(0, str(ROOT / "Manager_Ultra_LLM"))
import manager_release


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    path = OUT / name
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def checked(command):
    began = time.perf_counter()
    child_env = dict(os.environ)
    if Path(command[0]).name.lower() == "powershell.exe":
        child_env.pop("PSMODULEPATH", None)
        child_env.pop("PSModulePath", None)
    result = subprocess.run(command, cwd=ROOT, env=child_env, capture_output=True, timeout=40)
    row = {"command": command, "exit_code": result.returncode,
           "seconds": round(time.perf_counter() - began, 3),
           "stdout": result.stdout.decode("utf-8-sig", "replace"),
           "stderr": result.stderr.decode("utf-8-sig", "replace")}
    if result.returncode:
        save("a1_failure.json", row)
        raise RuntimeError("BLOCKED: package verifier failed")
    return row


def check():
    if socket.gethostname().upper() != "DESKTOP-SC96D3U":
        raise RuntimeError("Home PC required")
    baseline = {"task": OUT.name, "started_utc": datetime.now(timezone.utc).isoformat(),
                "host": socket.gethostname(), "previous_evidence": {str(p.relative_to(OLD)): sha(p)
                 for p in OLD.rglob("*") if p.is_file()},
                "initial_status": subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).decode("utf-8"),
                "branches": {b: subprocess.check_output(["git", "log", "-1", "--format=%H %s", b], cwd=ROOT).decode().strip()
                             for b in ("main", "GPT_2_local")}}
    card = (ROOT / "Documents/07_Задачи Codex.md").read_bytes()
    text = card.decode("utf-8-sig")
    baseline["card_sha256"] = hashlib.sha256(card).hexdigest()
    baseline["block4_sha256"] = hashlib.sha256(text[text.index("### БЛОК 4"):].encode()).hexdigest()
    baseline["client_source"] = {str(p.relative_to(ROOT)): sha(p) for p in (ROOT / "Client_Ultra_LLM").rglob("*")
                                  if p.is_file() and "__pycache__" not in p.parts and not any(x.startswith(".") for x in p.relative_to(ROOT).parts)}
    baseline["manager_runtime"] = {n: sha(ROOT / "Manager_Ultra_LLM" / n) for n in manager_release.RUNTIME}
    if (OUT / "baseline.json").exists():
        baseline = json.loads((OUT / "baseline.json").read_text(encoding="utf-8"))
    else:
        save("baseline.json", baseline)
    actual = sha(ZIP)
    if actual != EXPECTED:
        save("a1_failure.json", {"status": "BLOCKED", "expected": EXPECTED, "actual": actual})
        raise RuntimeError("BLOCKED: ZIP mismatch; no rebuild permitted")
    independent = checked(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                           "(Get-FileHash -Algorithm SHA256 -LiteralPath '" + str(ZIP) + "').Hash"])
    assert independent["stdout"].strip().lower() == EXPECTED
    verifier = checked([sys.executable, "-B", str(ROOT / "Manager_Ultra_LLM/manager_release.py"), "verify", str(ZIP)])
    payload = manager_release.read_package(ZIP)
    prior = json.loads((OLD / "release_manifest.json").read_text(encoding="utf-8-sig"))
    matches = {name: hashlib.sha256(data).hexdigest() == prior[name] for name, data in payload.items()}
    source = {name: hashlib.sha256(payload[name]).hexdigest() == baseline["manager_runtime"][name]
              for name in manager_release.RUNTIME}
    accepted = {}
    for name in manager_release.RUNTIME:
        data = subprocess.check_output(["git", "show", "b484bd67f4ff6506390860efd87731cced328cad:Manager_Ultra_LLM/" + name], cwd=ROOT)
        accepted[name] = data.replace(b"\r\n", b"\n") == payload[name].replace(b"\r\n", b"\n")
    assert len(payload) == 21 and all(matches.values()) and all(source.values()) and all(accepted.values())
    save("a1_release.json", {"status": "PASS", "zip": str(ZIP), "sha256": actual,
         "file_count": len(payload), "manifest_matches": matches, "working_source_byte_matches": source,
         "accepted_commit_source_matches_after_EOL_normalization": accepted,
         "public_only": "Exact allowlist of code/html + public release metadata/checksums; no config/TLS/SQLite/weights/logs",
         "stdlib_import_closure": "PASS (existing verifier)", "version": json.loads(payload["RELEASE.json"])["version"],
         "commands": [independent, verifier], "rebuild": "NOT RUN"})
    print("A1 PASS: authoritative ZIP SHA, 21 members, manifests, working/accepted source", flush=True)


def qa():
    assert (OUT / "a1_release.json").is_file(), "A1 first"
    runner = module("existing_qa", OLD / "run_qa.py")
    # Reuse its implementation unchanged; isolate this task's output and Test root.
    runner.OUT = OUT
    sys.argv = [str(OLD / "run_qa.py"), "--output", "a2_qa.json"]
    raise SystemExit(runner.main())


def rollback():
    qa_result = json.loads((OUT / "a2_qa.json").read_text(encoding="utf-8"))
    root = Path(qa_result["qa_root"])
    assert root.is_relative_to(ROOT / "Test")
    runner = module("existing_rollback", OLD / "rollback_qa.py")
    runner.ROOT = root
    runner.OUT = root / "Documents/Reports" / OLD_ID
    runner.OUT.mkdir(parents=True)
    source = ROOT / "Backups/Manager" / OLD_ID / "public_code"
    expected = json.loads((OLD / "baseline.json").read_text(encoding="utf-8-sig"))["server_public_files"]
    assert all(sha(source / n) == h for n, h in expected.items())
    target = root / "Backups/Manager" / OLD_ID / "public_code"
    target.parent.mkdir(parents=True)
    shutil.copytree(source, target)
    runner.rehearse(ZIP)
    result = json.loads((runner.OUT / "rollback_qa.json").read_text(encoding="utf-8"))
    result["reused_script_sha256"] = sha(OLD / "rollback_qa.py")
    result["path_rebinding"] = "ROOT/OUT only -> this task's Test copy; original implementation and old evidence unchanged"
    save("a2_rollback.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=("check", "qa", "rollback"))
    args = parser.parse_args()
    {"check": check, "qa": qa, "rollback": rollback}[args.phase]()
