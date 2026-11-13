"""Repeatable offline QA on a source COPY under Test, no installed Client use."""
from datetime import datetime, timezone
import argparse
import hashlib
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--steps", help="Comma-separated stage names; unchanged browser results can be retained")
    parser.add_argument("--output", default="qa.json")
    args = parser.parse_args()
    output = (OUT / args.output).resolve()
    if output.parent != OUT or output.exists():
        raise ValueError("Evidence must be a NEW file in this report directory")
    if socket.gethostname().upper() != "DESKTOP-SC96D3U":
        raise RuntimeError("Home QA only")
    qa = ROOT / "Test" / OUT.name / datetime.now().strftime("%Y%m%d_%H%M%S")
    qa.mkdir(parents=True)
    manifest = {}
    for folder in ("Manager_Ultra_LLM", "Client_Ultra_LLM"):
        source = ROOT / folder
        for file in source.rglob("*"):
            if not file.is_file() or any(p.startswith(".") or p in ("__pycache__", "node_modules", "build", "dist")
                                         for p in file.relative_to(source).parts):
                continue
            if file.suffix not in (".py", ".ps1", ".mjs", ".js", ".html", ".css", ".vbs"):
                continue
            dest = qa / file.relative_to(ROOT)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, dest)
            manifest[str(file.relative_to(ROOT))] = hashlib.sha256(file.read_bytes()).hexdigest()
    temp = qa / "temp"
    temp.mkdir()
    env = dict(os.environ, TEMP=str(temp), TMP=str(temp), TMPDIR=str(temp),
               LOCALAPPDATA=str(qa / "local_appdata"), PYTHONDONTWRITEBYTECODE="1", PYTHONUTF8="1")
    env.pop("PSModulePath", None)
    env.pop("PSMODULEPATH", None)
    env.pop("UL_COLIBRI_SOURCE", None)
    steps = [
        ("manager_suite", [sys.executable, "-B", "-m", "unittest", "discover", "-s", "Manager_Ultra_LLM", "-p", "test_*.py", "-q"]),
        ("client_suite", [sys.executable, "-B", "-m", "unittest", "discover", "-s", "Client_Ultra_LLM", "-p", "test_*.py", "-q"]),
        ("python_syntax", [sys.executable, "-B", "-c", "from pathlib import Path;[compile(p.read_text(encoding='utf-8-sig'),str(p),'exec') for d in ('Manager_Ultra_LLM','Client_Ultra_LLM') for p in Path(d).glob('*.py')];print('PASS')"]),
        ("js_syntax", ["node", "--check", "Client_Ultra_LLM/web_assets/client.js"]),
        ("legacy_chrome", ["node", "Client_Ultra_LLM/test_browser_control_stream.mjs"]),
        ("p0_tls_chrome", ["node", "Client_Ultra_LLM/test_browser_stream_source.mjs"]),
        ("p1_tls_chrome", ["node", "Client_Ultra_LLM/test_browser_slots_source.mjs"]),
        ("powershell_wrapper", ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "Manager_Ultra_LLM/verify_offline.ps1"]),
    ]
    if args.steps:
        selected = set(args.steps.split(","))
        if selected - {name for name, command in steps}:
            raise ValueError("Unknown QA stage")
        steps = [(name, command) for name, command in steps if name in selected]
    evidence = {"task": OUT.name, "qa_root": str(qa), "host": socket.gethostname(),
                "scope": "Source COPY; synthetic Colibri/resources; native tests use owned dummy Python only",
                "source_sha256": manifest, "steps": [], "independent_review": "PENDING",
                "live_deploy": "NOT RUN", "real_llm": "NOT RUN", "hosted_ci": "NOT RUN"}
    for name, command in steps:
        print("RUN " + name, flush=True)
        began = time.monotonic()
        try:
            result = subprocess.run(command, cwd=qa, env=env, capture_output=True, timeout=300)
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as error:
            code, stdout, stderr = 124, error.stdout or b"", (error.stderr or b"") + b"\nTIMEOUT"
        row = {"name": name, "command": command, "exit_code": code,
               "status": "PASS" if code == 0 else "FAIL", "seconds": round(time.monotonic() - began, 3),
               "stdout": stdout.decode("utf-8", "replace"), "stderr": stderr.decode("utf-8", "replace")}
        evidence["steps"].append(row)
        print(row["status"] + " " + name + " " + str(row["seconds"]), flush=True)
        output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    evidence["status"] = "PASS" if all(s["exit_code"] == 0 for s in evidence["steps"]) else "FAIL"
    evidence["completed_utc"] = datetime.now(timezone.utc).isoformat()
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
