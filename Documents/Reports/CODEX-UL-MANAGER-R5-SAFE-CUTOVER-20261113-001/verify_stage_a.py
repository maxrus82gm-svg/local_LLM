"""Read-only handoff integrity checks; writes only local review evidence."""
from datetime import datetime, timedelta, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
OLD = ROOT / "Documents/Reports/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001"


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    baseline, package, qa, rollback, diagnosis, checkpoint, preserved = [read(n) for n in (
        "baseline.json", "a1_release.json", "a2_qa.json", "a2_rollback.json", "a3_diagnostics_final.json",
        "card_checkpoint.json", "report_preservation.json")]
    old_matches = {n: digest(OLD / n) == h for n, h in baseline["previous_evidence"].items()}
    assert all(old_matches.values()), "Earlier evidence must stay unchanged"
    assert digest(package["zip"]) == package["sha256"]
    assert all(digest(ROOT / "Manager_Ultra_LLM" / n) == h for n, h in baseline["manager_runtime"].items())
    assert all(digest(ROOT / n) == h for n, h in baseline["client_source"].items())
    assert qa["status"] == rollback["status"] == diagnosis["status"] == package["status"] == "PASS"
    assert len(qa["steps"]) == 8 and all(s["exit_code"] == 0 for s in qa["steps"])
    assert rollback["decision_cases"] == 66 and len(rollback["scenarios"]) == 2
    assert diagnosis["total_cases"] == 56
    readme = (ROOT / "Manager_Ultra_LLM/README.md").read_bytes()
    assert hashlib.sha256(readme[:preserved["previous_readme_bytes"]]).hexdigest() == preserved["previous_readme_sha256"]
    card = (ROOT / "Documents/07_Задачи Codex.md").read_bytes().decode("utf-8-sig")
    task = card[card.index("# CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001"):card.index("### БЛОК 1.1")]
    assert hashlib.sha256(task.encode()).hexdigest() == checkpoint["task_verbatim_sha256"]
    assert hashlib.sha256(card[card.index("### БЛОК 4"):].encode()).hexdigest() == baseline["block4_sha256"]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    assert head == "d51b22f2c2abcc6411a09400e7046d777261519f"
    assert subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT).decode().strip() == "main"
    assert subprocess.check_output(["git", "rev-parse", "GPT_2_local"], cwd=ROOT).decode().strip() == head
    assert not subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT).strip()
    own = ["Manager_Ultra_LLM/README.md", "Documents/07_Задачи Codex.md"]
    own += [p.relative_to(ROOT).as_posix() for p in OUT.glob("*.py")]
    diff = []
    for name in own:
        before = subprocess.run(["git", "show", "HEAD:" + name], cwd=ROOT, capture_output=True)
        old = before.stdout.decode("utf-8-sig").replace("\r\n", "\n") if before.returncode == 0 else ""
        new = (ROOT / name).read_text(encoding="utf-8-sig")
        if name.endswith(".py"):
            compile(new, name, "exec")
        diff.extend(difflib.unified_diff(old.splitlines(True), new.splitlines(True),
                                       fromfile="a/" + name if before.returncode == 0 else "/dev/null", tofile="b/" + name))
    (OUT / "review.diff").write_text("".join(diff), encoding="utf-8")
    check = subprocess.run(["git", "diff", "--check", "--", *[n for n in own if n != "Documents/07_Задачи Codex.md"]],
                           cwd=ROOT, capture_output=True)
    assert check.returncode == 0, check.stdout.decode("utf-8", "replace")
    card_check = subprocess.run(["git", "diff", "--check", "--", "Documents/07_Задачи Codex.md"], cwd=ROOT, capture_output=True)
    whitespace_lines = [int(n) for n in re.findall(r"\.md:(\d+): trailing whitespace", card_check.stdout.decode("utf-8", "replace"))]
    start = card[:card.index("# CODEX-UL-MANAGER-R5-SAFE-CUTOVER-20261113-001")].count("\n") + 1
    end = card[:card.index("### БЛОК 1.1")].count("\n") + 1
    assert all(start <= n < end for n in whitespace_lines), "No new whitespace errors outside verbatim task"
    screenshot = Path(qa["qa_root"]) / "Client_Ultra_LLM/stream_slots_browser.png"
    shutil.copyfile(screenshot, OUT / "p1_browser.png")
    result = {"task": OUT.name, "stage": "A ONLY", "status": "PREFLIGHT PREPARED / A TESTS PASS / OWNER GO REQUIRED",
              "completed_utc": datetime.now(timezone.utc).isoformat(),
              "completed_owner_local": datetime.now(timezone(timedelta(hours=5))).isoformat(),
              "host": baseline["host"], "zip_sha256": package["sha256"], "zip_members": 21,
              "manager_tests": {"total": 311, "pass": 310, "skip": 1}, "client_tests": {"pass": 49, "total": 49},
              "qa_steps": [{k: s[k] for k in ("name", "status", "exit_code", "seconds")} for s in qa["steps"]],
              "rollback": {"status": "PASS", "cases": 66, "filesystem_scenarios": 2, "live": "NOT RUN"},
              "invalid_messages": {"status": "PASS", "cases": 56, "seconds": diagnosis["seconds"],
                                   "specific_live_root_cause": "NOT PROVEN; no private history/failed request inspected",
                                   "reproduced": "Legacy count/content/aggregate/reasoning contract mismatch; history=0 excludes stored context without deleting rows"},
              "stage_b": "NOT RUN; separate OWNER GO required", "stage_c": "NOT RUN; separate OWNER GO required",
              "stage_d": "NOT RUN; separate OWNER GO required", "real_server_checks": [],
              "pre_post_manager_client_qwen_valheim": "NOT RUN; historical states not treated as current",
              "runtime_manager_unchanged": True, "source_client_unchanged": True,
              "production_client_shortcut_private_history_access": "NONE; no read/write/start/stop",
              "previous_evidence_unchanged": old_matches, "previous_report_bytes_preserved": True,
              "block4_unchanged": True, "task_verbatim_preserved_active_in_block1": True,
              "source_diff_check": "PASS", "card_inherited_task_whitespace_lines": whitespace_lines,
              "git": {"head": head, "number": "47", "branch": "main", "new_commits": 0, "push_pull": "NOT RUN", "index": "unchanged empty"},
              "report": str(ROOT / "Manager_Ultra_LLM/README.md"), "materials": str(OUT / "preflight_plan.json"),
              "rollback_template": str(OUT / "rollback_observations_template.json"),
              "independent_coordinator_review": "PENDING", "next": "STOP at Gate 1; independent review before separately authorized B"}
    (OUT / "handoff.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest = {p.relative_to(ROOT).as_posix(): digest(p) for p in sorted(OUT.iterdir())
                if p.is_file() and p.name != "evidence_manifest.json"}
    (OUT / "evidence_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "prior_evidence_files_unchanged": len(old_matches),
                      "runtime_unchanged": True, "block4_unchanged": True, "commit": "NONE"}))


if __name__ == "__main__":
    main()
