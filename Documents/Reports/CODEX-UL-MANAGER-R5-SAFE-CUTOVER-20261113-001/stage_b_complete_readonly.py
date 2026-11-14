"""Conclude B from fresh read-only evidence; no server execution or mutation.

For the observed ACL case, reordering distinct inherited Allow/FullControl ACEs
does not change access. Deny/noncanonical/owner/group/flag differences fail.
"""
from collections import Counter
from datetime import datetime, timezone, timedelta
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent

# Versioned contract of stage_b_server_preflight_v3.ps1, not caller-supplied keys.
EXPECTED_CHECKS = frozenset((
    "admin_backup_authority", "task_running_single_action", "task_arguments_known_contract",
    "runtime_path_expected_no_links", "config_path_expected_no_links", "python_exists_no_links",
    "control_disabled", "private_paths_local", "one_manager_listener", "manager_identity_action_match",
    "one_qwen_loopback_listener", "one_qwen_engine", "one_valheim_process", "valheim_udp_bound",
    "protected_processes_outside_manager_tree", "manager_has_no_model_children",
    "private_acl_protected_scoped", "backup_space_available", "known_installed_manager_version",
    "python_private_tls_health_audit", "python_312_x64", "tls_and_access_denial",
    "qwen_ready_expected_model", "state_databases_consistent_no_jobs"))


def require(condition, message="Stage B evidence validation failed"):
    # Explicit exception preserves fail-closed semantics under python -O.
    if not condition:
        raise AssertionError(message)


def validate_snapshot(snapshot):
    checks = snapshot["checks"]
    require(type(checks) is dict and set(checks) == EXPECTED_CHECKS
            and all(value is True for value in checks.values()), "Invalid guard set/types")
    listener = snapshot["manager_listener"]
    require(type(listener) is dict and set(listener) == {"address", "port", "pid"},
            "Invalid listener fields")
    require(type(listener["address"]) is str and bool(listener["address"].strip()),
            "Invalid listener address")
    require(type(listener["port"]) is int and 0 < listener["port"] <= 65535,
            "Invalid listener port")
    require(type(listener["pid"]) is int and listener["pid"] > 0
            and type(snapshot["manager"]["pid"]) is int
            and listener["pid"] == snapshot["manager"]["pid"], "Listener/Manager PID mismatch")
    metadata = snapshot["python_audit"]["metadata"]
    require(type(metadata["unauth_snapshot_http"]) is int
            and metadata["unauth_snapshot_http"] == 403
            and metadata["unauth_snapshot_error"] == "source_not_permitted",
            "Unexpected unauthenticated HTTP status/reason")


def read(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def acl_equivalent(left, right):
    fields = ("owner_sid", "group_sid", "protected", "canonical")
    if any(left[k] != right[k] for k in fields) or not left["canonical"]:
        return False
    rows = left["rules"] + right["rules"]
    if any(r["type"] != "Allow" or r["rights"] != "FullControl" or not r["inherited"]
           or r["inheritance"] != "None" or r["propagation"] != "None" for r in rows):
        return False
    return Counter(json.dumps(r, sort_keys=True) for r in left["rules"]) == Counter(
        json.dumps(r, sort_keys=True) for r in right["rules"])


def main():
    baseline = read("stage_b_server_preflight_ready.json")["result"]
    diagnostic = read("stage_b_acl_readonly_diagnostic.json")
    require(diagnostic["exit_code"] == 0 and len(diagnostic["records"]) == 2)
    acl, post = diagnostic["records"]
    prepared = acl["summary"]
    require(prepared["status"] == "BACKUP_STAGING_PREPARED")
    require(post["status"] == baseline["status"] == "PREFLIGHT_READONLY_PASS")
    validate_snapshot(baseline)
    validate_snapshot(post)
    require(post["manager_listener"] == baseline["manager_listener"], "Listener changed")
    require(acl["unsafe_new_tree_items"] == 0 and acl["checked_new_tree_items"] == 112)
    require(acl_equivalent(acl["source_acl"], acl["probe_acl"]))
    for key in ("owner_sid", "group_sid", "protected", "canonical"):
        bad = json.loads(json.dumps(acl["probe_acl"]))
        bad[key] = not bad[key] if isinstance(bad[key], bool) else "different"
        require(not acl_equivalent(acl["source_acl"], bad))
    for key, value in (("sid", "different"), ("rights", "Read"), ("type", "Deny"), ("inherited", False)):
        bad = json.loads(json.dumps(acl["probe_acl"]))
        bad["rules"][0][key] = value
        require(not acl_equivalent(acl["source_acl"], bad))
    for role in ("manager", "qwen_gateway", "qwen_engine", "valheim"):
        require(post[role] == baseline[role], "Protected identity changed")
    require(post["task"] == baseline["task"])
    for key in ("config_sha256", "tls_peer_sha256", "owner_go", "client_count",
                "control_models_granted_count", "pairing_admin_count", "slot_count"):
        require(post["python_audit"]["metadata"][key] == baseline["python_audit"]["metadata"][key])
    require(post["public_code"] == baseline["public_code"])
    require(prepared["stage_files"] == 21)
    require(prepared["zip_sha256"] == "ba4ebf65af7a0693cf4dce045eb08254434a4475fd4f79e031424c905d661ce2")
    resume = read("stage_b_resume_baseline_20261114.json")
    require(all(hashlib.sha256((OUT / n).read_bytes()).hexdigest() == h for n, h in resume["previous_files"].items()))
    require(subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip() == resume["head"])
    result = {"task": OUT.name, "stage": "B ONLY", "status": "B PASS / GATE 2 / INDEPENDENT REVIEW PENDING",
        "completed_utc": datetime.now(timezone.utc).isoformat(),
        "completed_owner_local": datetime.now(timezone(timedelta(hours=5))).isoformat(),
        "backup_staging": prepared, "post": post,
        "acl": {"new_tree_items": 112, "unsafe_items": 0, "directory_restore_rehearsal": "PASS",
                "file_restore_rehearsal": "PASS by owner/group/ACE/flags equivalence",
                "original_sddl_order_only_difference": True,
                "canonical_all_allow_rules": True, "negative_equivalence_checks": 8,
                "source_or_backup_acl_changed_to_resolve_difference": False},
        "limitations": ["Live service rollback, task re-registration and working-directory rename NOT RUN",
                        "Task XML, owner/group/DACL preserved; auditing policy not changed",
                        "Live logs captured at bounded file lengths, not a global atomic log snapshot",
                        "SQLite/WAL absent; no synthetic claim of database backup",
                        "Server-local unauthenticated Manager request returned expected IP-filter 403; authenticated Client roundtrip belongs to C/D",
                        "No real LLM generation, cancel or model-control START/STOP"],
        "stage_c": "NOT RUN / SEPARATE OWNER GO REQUIRED",
        "stage_d": "NOT RUN / SEPARATE OWNER GO REQUIRED",
        "current_live_manager": "Previous version still running; R5 only staged",
        "client_shortcut_history_changes": False, "private_data_exported": False,
        "existing_task_config_tls_auth_network_trust_acl_changes": False,
        "new_server_writes": "Only new protected maintenance directory and its backup/stage/rehearsal contents",
        "git": {"head": resume["head"], "number": "50", "new_commits": 0, "push_pull_fetch": "NOT RUN"},
        "next": "STOP at Gate 2. Independent coordinator review; do not execute C or D without their separate OWNER GO."}
    with (OUT / "stage_b_completion.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "code_backup_files": prepared["code_files"],
                      "state_backup_files": prepared["state_files"], "stage_files": prepared["stage_files"],
                      "protected_processes_unchanged": True, "acl_equivalent": True}))


if __name__ == "__main__":
    main()
