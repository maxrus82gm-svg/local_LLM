"""Final read-only acceptance checks + safe diff/JSON, no LIVE execution."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
sys.path.insert(0, str(ROOT / "Manager_Ultra_LLM"))
import manager_release as release


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8-sig"))


def main():
    base, initial, final, package, rollback = (read(n) for n in (
        "baseline.json", "qa.json", "qa_regression.json", "release.json", "rollback_qa.json"))
    payload = release.read_package(Path(package["zip"]))
    assert release.sha(Path(package["zip"]).read_bytes()) == package["zip_sha256"]
    assert all(payload[name] == (ROOT / "Manager_Ultra_LLM" / name).read_bytes() for name in release.RUNTIME)
    # Browser results remain valid: every candidate runtime byte is unchanged.
    browser_runtime_same = all(initial["source_sha256"][str(Path("Manager_Ultra_LLM") / name)]
                               == release.sha(payload[name]) for name in release.RUNTIME)
    assert browser_runtime_same
    assert all(initial["source_sha256"][name] == digest for name, digest in final["source_sha256"].items()
               if name.startswith("Client_Ultra_LLM/") and name in initial["source_sha256"])
    steps = [s for s in initial["steps"] if s["name"] not in ("manager_suite", "client_suite", "powershell_wrapper")]
    steps += final["steps"]
    assert all(s["exit_code"] == 0 for s in steps)
    assert rollback["status"] == "PASS"
    candidate_manifest = {name: release.sha(data) for name, data in payload.items()}
    (OUT / "release_manifest.json").write_bytes(release.canonical(candidate_manifest))
    backup = Path(base["backup"])
    assert all(release.sha((backup / name).read_bytes()) == digest for name, digest in base["server_public_files"].items())
    remote = Path(base["server_public_root"])
    remote_unchanged = {name: release.sha((remote / name).read_bytes()) == digest
                        for name, digest in base["server_public_files"].items()}
    assert all(remote_unchanged.values())
    assets = {}
    for name in ("client.js", "client.css", "index.html"):
        source = ROOT / "Client_Ultra_LLM/web_assets" / name
        installed = ROOT / "Production/Client/_internal/web_assets" / name
        assets[name] = {"source_sha256": release.sha(source.read_bytes()),
                        "installed_sha256": release.sha(installed.read_bytes())}
        assert assets[name]["source_sha256"] == assets[name]["installed_sha256"]
    installed_root = ROOT / "Production/Client"
    client_files = 0
    for line in (installed_root / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        digest, name = line.split("  ", 1)
        path = (installed_root / name).resolve()
        assert path.is_relative_to(installed_root.resolve())
        assert release.sha(path.read_bytes()) == digest.lower()
        client_files += 1
    card = (ROOT / "Documents/07_Задачи Codex.md").read_bytes().decode("utf-8-sig")
    independent = card[card.index("### БЛОК 4"):]
    assert release.sha(independent.encode("utf-8")) == base["block4_sha256"]
    assert "ARCHIVE BLOCKED — CODEX-UL-MANAGER-R5" in card
    assert subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip() == "71462bde1f245f96180bec351e0f1ea7ecdd8b50"
    assert not subprocess.check_output(["git", "diff", "--cached", "--name-only"], cwd=ROOT).strip()
    own = [".github/workflows/ultra-offline-ci.yml", "Manager_Ultra_LLM/README.md",
           "Manager_Ultra_LLM/manager_release.py", "Manager_Ultra_LLM/test_manager_release.py",
           "Manager_Ultra_LLM/test_colibri2_runner.py", "Manager_Ultra_LLM/verify_offline.ps1",
           "Documents/07_Задачи Codex.md"]
    own += [str(p.relative_to(ROOT)).replace("\\", "/") for p in OUT.glob("*.py")]
    diff = []
    for name in own:
        old = subprocess.run(["git", "show", "HEAD:" + name], cwd=ROOT, capture_output=True)
        before = old.stdout.decode("utf-8-sig").replace("\r\n", "\n") if old.returncode == 0 else ""
        after = (ROOT / name).read_text(encoding="utf-8-sig")
        diff.extend(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                    fromfile="a/" + name if old.returncode == 0 else "/dev/null", tofile="b/" + name))
    (OUT / "review.diff").write_text("".join(diff), encoding="utf-8")
    screenshot = Path(initial["qa_root"]) / "Client_Ultra_LLM/stream_slots_browser.png"
    (OUT / "p1_browser.png").write_bytes(screenshot.read_bytes())
    check = subprocess.run(["git", "diff", "--check", "--", *[p for p in own if p != "Documents/07_Задачи Codex.md"]], cwd=ROOT, capture_output=True)
    assert check.returncode == 0, check.stdout.decode("utf-8", "replace")
    card_check = subprocess.run(["git", "diff", "--check", "--", "Documents/07_Задачи Codex.md"], cwd=ROOT, capture_output=True)
    warnings = card_check.stdout.decode("utf-8", "replace")
    task_start = card[:card.index("# CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001")].count("\n") + 1
    task_end = card[:card.index("### БЛОК 1.1")].count("\n") + 1
    warning_lines = [int(n) for n in re.findall(r"\.md:(\d+): trailing whitespace", warnings)]
    assert all(task_start <= n < task_end for n in warning_lines), "New whitespace outside verbatim owner task"
    result = {"task": OUT.name, "completed_utc": datetime.now(timezone.utc).isoformat(),
              "status": "RELEASE CANDIDATE READY / LIVE DEPLOY NOT RUN", "qa": "PASS",
              "manager": {"total": 311, "passed": 310, "skipped": 1,
                          "skip": "Optional installed Colibri source AST audit NOT RUN"},
              "client": {"total": 49, "passed": 49},
              "checks": [{k: s[k] for k in ("name", "status", "exit_code", "seconds")} for s in steps],
              "browser_candidate_runtime_sha_match": browser_runtime_same,
              "p1_browser_screenshot": {"path": str(OUT / "p1_browser.png"),
                                        "sha256": release.sha(screenshot.read_bytes()), "scope": "Fake models only"},
              "installed_client_payload_files_verified": client_files,
              "installed_client_assets_equal_tested_source": assets,
              "installed_client_exe": str(installed_root / "UltraLLMClient.exe"),
              "server_public_files_unchanged": remote_unchanged,
              "release": package, "rollback": {"qa": "PASS", "decision_cases": 66, "scenarios": 2,
                                                  "live": "NOT RUN; full private/task backup and authority pending OWNER GO"},
              "live_checked": "SMB public-source inventory/SHA only; NOT running process provenance",
              "live_not_run": ["Manager process/task/TLS/authenticated API", "Qwen/Valheim health and identities",
                               "real inference/reasoning/cancel", "CPU/CUDA/START/STOP", "deploy/rollback"],
              "history": "Real user history not read or modified; synthetic QA persistence PASS",
              "rotation": "ARCHIVE BLOCKED; old 1.1 retained; exact Git original verified, missing index in 05/09",
              "block4_unchanged": True, "source_18_29": "SOURCE UNAVAILABLE",
              "diff_check": {"source": "PASS", "card_exit_code": card_check.returncode,
                             "inherited_verbatim_task_whitespace_lines": warning_lines,
                             "reason": "Owner-assigned task retained verbatim; not normalized to silence git diff --check"},
              "git": {"branch": "main", "head_number": "45", "head_sha": "71462bde1f245f96180bec351e0f1ea7ecdd8b50",
                      "task_commit": None, "reason": "Explicit owner amendment: NO COMMIT/PUSH/PULL", "index_unchanged_empty": True},
              "independent_acceptance": "PENDING", "report": str(ROOT / "Manager_Ultra_LLM/README.md"),
              "initial_failures": "Retained qa.json; QA config/copy mistakes fixed; final affected suites qa_regression.json PASS"}
    (OUT / "acceptance.json").write_bytes(release.canonical(result))
    files = {str(p.relative_to(ROOT)).replace("\\", "/"): release.sha(p.read_bytes())
             for p in sorted(OUT.iterdir()) if p.is_file() and p.name != "evidence_manifest.json"}
    (OUT / "evidence_manifest.json").write_bytes(release.canonical(files))
    print(json.dumps({"status": result["status"], "qa": "PASS", "release_files": len(payload),
                      "client_payload_unchanged": client_files, "rotation": "ARCHIVE BLOCKED",
                      "source_diff_check": "PASS", "verbatim_task_whitespace_lines": len(warning_lines)}))


if __name__ == "__main__":
    main()
