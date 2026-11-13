"""Rollback decision + filesystem rehearsal ONLY under home workspace Test.

No service/task/network/process APIs. This is not a LIVE deploy/rollback tool.
Unknown or missing post-deploy observations fail closed. No files are deleted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "Manager_Ultra_LLM"))
import manager_release

REQUIRED = ("manager_identity_verified", "one_manager_listener", "tls_verified",
            "authenticated_snapshot", "streaming_advertised", "catalog_route_ok",
            "client_online", "qwen_health_unchanged", "qwen_identity_unchanged",
            "valheim_identity_unchanged", "config_auth_tls_hashes_unchanged",
            "task_settings_unchanged", "no_new_model_process", "no_owned_instances",
            "private_backup_verified", "deadline_met")


def decision(observations):
    reasons = [key for key in REQUIRED if observations.get(key) is not True]
    return {"decision": "ROLLBACK_REQUIRED" if reasons else "HOLD_CANDIDATE",
            "failed_or_missing": reasons, "execution": "NONE; owner-controlled Manager-only transaction required"}


def tree_hashes(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file()}


def rehearse(package):
    if socket.gethostname().upper() != "DESKTOP-SC96D3U":
        raise RuntimeError("Home PC QA only")
    qa = ROOT / "Test" / OUT.name / ("rollback_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    qa.mkdir(parents=True)
    original = ROOT / "Backups/Manager" / OUT.name / "public_code"
    results = []
    for scenario in ("failed_health", "failed_second_rename"):
        base = qa / scenario
        base.mkdir()
        live, prior, stage, failed = (base / n for n in ("Manager_Live", "prior_retained", "staged", "failed_retained"))
        shutil.copytree(original, live)
        (live / "unknown-user-file.bin").write_bytes(b"QA sentinel preserved")
        private = base / "private"
        private.mkdir()
        (private / "synthetic-state.bin").write_bytes(b"QA only; no real auth or DB")
        before, private_before = tree_hashes(live), tree_hashes(private)
        manager_release.stage(package, stage)
        # Directory renames preserve the complete old tree, including unknown files.
        live.rename(prior)
        if scenario == "failed_second_rename":
            try:
                raise OSError("QA injected second-rename failure")
            except OSError:
                prior.rename(live)
        else:
            stage.rename(live)
            observations = dict.fromkeys(REQUIRED, True)
            observations["authenticated_snapshot"] = False
            assert decision(observations)["decision"] == "ROLLBACK_REQUIRED"
            live.rename(failed)
            prior.rename(live)
        assert tree_hashes(live) == before
        assert tree_hashes(private) == private_before
        proc = subprocess.run([sys.executable, "-B", "-I", "-c",
            "import sys;sys.path.insert(0,sys.argv[1]);import live_manager,pairing_workflow;print('OLD_IMPORT_OK')",
            str(live)], capture_output=True, timeout=15)
        assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
        results.append({"scenario": scenario, "status": "PASS", "restored_files": before,
                        "private_bytes_unchanged": True, "unknown_file_preserved": True,
                        "restored_runtime_import_exit_code": proc.returncode,
                        "retained_candidate": str(failed if failed.exists() else stage)})
    assert decision({})["decision"] == "ROLLBACK_REQUIRED"
    assert decision(dict.fromkeys(REQUIRED, True))["decision"] == "HOLD_CANDIDATE"
    for field in REQUIRED:
        for value in (False, None, "true", 1):
            sample = dict.fromkeys(REQUIRED, True)
            sample[field] = value
            assert decision(sample)["decision"] == "ROLLBACK_REQUIRED"
    result = {"status": "PASS", "scope": "QA filesystem, copied old public source, synthetic private bytes; no task restart",
              "root": str(qa), "scenarios": results, "decision_cases": len(REQUIRED) * 4 + 2,
              "live_rollback": "NOT RUN; protected private snapshot and actual process/task authority require OWNER GO"}
    (OUT / "rollback_qa.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PASS", "decision_cases": result["decision_cases"], "scenarios": len(results)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rehearse", type=Path)
    parser.add_argument("--observations", type=Path)
    args = parser.parse_args()
    if args.rehearse:
        rehearse(args.rehearse)
    elif args.observations:
        print(json.dumps(decision(json.loads(args.observations.read_text(encoding="utf-8-sig"))), indent=2))
    else:
        parser.error("Choose --rehearse or --observations; neither performs LIVE actions")
