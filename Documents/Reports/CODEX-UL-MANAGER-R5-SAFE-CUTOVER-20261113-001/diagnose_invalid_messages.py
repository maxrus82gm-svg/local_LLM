"""Offline reproductions with synthetic SQLite + actual Client/Manager functions.

No production SQLite/profile is opened. Transport is replaced with validators,
not real HTTP/inference. Evidence contains metadata only, no conversation text.
"""
from contextlib import closing
import argparse
from datetime import datetime
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sqlite3
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
sys.path[:0] = [str(ROOT / "Client_Ultra_LLM"), str(ROOT / "Manager_Ultra_LLM")]
import chat_client
import chat_store
import web_client
import chat_runtime as current

OLD = ROOT / "Backups/Manager/CODEX-UL-MANAGER-R5-COMPAT-RELEASE-20261113-001/public_code/chat_runtime.py"
EXPECTED_OLD = "fc69896cc40a64237ff3125299d21d8e4a49ec0b5f0ae6ec64c1d905b9755466"


def outcome(validator, body):
    try:
        validator(body)
        return "ACCEPT"
    except Exception as error:
        if hasattr(error, "reason"):
            return error.reason
        raise


def metadata(messages):
    return {"messages": len(messages), "role_sequence": [m.get("role") for m in messages],
            "content_chars": sum(len(m["content"]) for m in messages),
            "max_message_content_chars": max((len(m["content"]) for m in messages), default=0),
            "reasoning_chars": sum(len(m.get("reasoning_content", "")) for m in messages),
            "extra_message_keys": sorted(set().union(*(set(m) - {"role", "content"} for m in messages)))}


def body(messages):
    return {"slot_id": "slot1", "model_id": "qa-model", "messages": messages}


def messages(count, size=1):
    rows = [{"role": "user" if i % 2 == 0 else "assistant", "content": "x" * size} for i in range(count)]
    rows[-1]["role"] = "user"  # isolate count from last-role check
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="a3_invalid_messages.json")
    args = parser.parse_args()
    output = (OUT / args.output).resolve()
    if output.parent != OUT or output.exists():
        raise ValueError("Use a new evidence filename in this task directory")
    started = time.perf_counter()
    assert hashlib.sha256(OLD.read_bytes()).hexdigest() == EXPECTED_OLD
    spec = importlib.util.spec_from_file_location("audited_legacy_chat", OLD)
    legacy = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(legacy)
    cases = []
    def check(name, packet, old_expected, new_expected):
        old, new = outcome(legacy.validate_request, packet), outcome(current.validate_request, packet)
        assert (old, new) == (old_expected, new_expected), (name, old, new)
        size = len(json.dumps(packet, ensure_ascii=False).encode())
        cases.append({"case": name, "legacy": old, "r5": new,
                      "payload_bytes_utf8": size, "legacy_http_body_48kib_would_accept_size": size <= 48 * 1024,
                      "metadata": metadata(packet["messages"])})
    for n in (15, 16, 17, 127, 128, 129):
        check("message_count_" + str(n), body(messages(n)), "ACCEPT" if n <= 16 else "invalid_messages",
              "ACCEPT" if n <= 128 else "invalid_messages")
    for size in (4000, 4001, 131072, 131073):
        check("single_content_chars_" + str(size), body(messages(1, size)),
              "ACCEPT" if size <= 4000 else "invalid_messages", "ACCEPT" if size <= 131072 else "invalid_messages")
    check("legacy_total_24000", body(messages(6, 4000)), "ACCEPT", "ACCEPT")
    check("legacy_total_24001", body(messages(7, 3428) + [{"role": "user", "content": "xxxxx"}]), "invalid_messages", "ACCEPT")
    for total in (240000, 240001):
        check("r5_total_" + str(total), body([{"role": "assistant", "content": "x" * 120000},
              {"role": "user", "content": "x" * (total - 120000)}]), "invalid_messages",
              "ACCEPT" if total <= 240000 else "invalid_messages")
    for reasoning in ("", "why"):
        check("reasoning_key_" + ("empty" if not reasoning else "nonempty"), body([
            {"role": "user", "content": "x"}, {"role": "assistant", "content": "x", "reasoning_content": reasoning},
            {"role": "user", "content": "x"}]), "invalid_messages", "ACCEPT")
    check("reasoning_only_assistant", body([{"role": "user", "content": "x"},
          {"role": "assistant", "content": "", "reasoning_content": "why"}, {"role": "user", "content": "x"}]),
          "invalid_messages", "ACCEPT")
    check("two_consecutive_users", body(messages(2)), "ACCEPT", "ACCEPT")
    check("system_role", body([{"role": "system", "content": "x"}, {"role": "user", "content": "x"}]),
          "invalid_messages", "invalid_messages")
    check("last_role_assistant", body([{"role": "assistant", "content": "x"}]), "invalid_messages", "invalid_messages")
    check("empty_user", body([{"role": "user", "content": ""}]), "invalid_messages", "invalid_messages")
    check("reasoning_on_user", body([{"role": "user", "content": "x", "reasoning_content": "why"}]),
          "invalid_messages", "invalid_messages")
    for key, value in (("options", {"thinking": "auto"}), ("instance_id", "legacy-qa")):
        check("extra_top_level_" + key, {**body(messages(1)), key: value}, "invalid_fields", "ACCEPT")

    qa = ROOT / "Test" / OUT.name / ("messages_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
    qa.mkdir(parents=True)
    client_cases = []
    seeds = {"long_history": messages(34), "large_old_reply": messages(2, 4001),
             "large_total": messages(8, 3500),
             "reasoning": [{"role": "user", "content": "x"},
                           {"role": "assistant", "content": "x", "reasoning_content": "why"}]}
    # Restore genuine alternating legacy pairs for persistence scenarios.
    for name in ("long_history", "large_old_reply", "large_total"):
        for i, row in enumerate(seeds[name]):
            row["role"] = "user" if i % 2 == 0 else "assistant"
    for name, seed in seeds.items():
        for budget in (0, 5, 10, 100):
            for label, validator in (("legacy", legacy.validate_request), ("r5", current.validate_request)):
                folder = qa / f"{name}_{budget}_{label}"
                folder.mkdir()
                database = folder / "chat_history.sqlite3"
                with closing(sqlite3.connect(database)) as db:
                    if name == "reasoning":
                        chat_store._migrate(db)
                        db.executemany("INSERT INTO messages(manager_id,slot_id,model_id,role,content,instance_id,reasoning_content) VALUES('qa','slot1','qa-model',?,?,'',?)",
                                       [(m["role"], m["content"], m.get("reasoning_content", "")) for m in seed])
                    else:
                        # A real legacy schema-0 layout, entirely synthetic rows.
                        db.execute(chat_store._SCHEMA)
                        db.executemany("INSERT INTO messages(manager_id,slot_id,model_id,role,content) VALUES('qa','slot1','qa-model',?,?)",
                                       [(m["role"], m["content"]) for m in seed])
                    db.commit()
                sent = []
                def transport(profile, route, packet=None, **kwargs):
                    sent.append(packet)
                    rejected = outcome(validator, packet)
                    if rejected != "ACCEPT":
                        raise chat_client.ChatClientError(rejected, 400)
                    return io.BytesIO(json.dumps({"schema": "ultra.manager.chat.v1", "manager_id": "qa",
                        "slot_id": "slot1", "model_id": "qa-model", "reply": "QA reply"}).encode())
                with patch.object(web_client, "load_profiles", return_value=[{"manager_id": "qa"}]), \
                     patch.object(chat_client, "manager_open", side_effect=transport):
                    try:
                        web_client.chat_exchange(folder, {"manager_id": "qa", "slot_id": "slot1", "model_id": "qa-model",
                                                 "message": "QA prompt", "context": {"max_messages": budget}})
                        actual = "ACCEPT"
                    except chat_client.ChatClientError as error:
                        actual = error.reason
                assert len(sent) == 1
                assert set(sent[0]) == {"slot_id", "model_id", "messages"}
                after = chat_store.history(folder, "qa", "slot1", "qa-model", limit=1024)
                assert after[:len(seed)] == seed
                assert len(after) == len(seed) + (2 if actual == "ACCEPT" else 0)
                rejected_by_legacy = (name in ("large_old_reply", "reasoning")
                                      or name == "long_history" and budget == 100
                                      or name == "large_total" and budget in (10, 100))
                expected = "invalid_messages" if label == "legacy" and budget != 0 and rejected_by_legacy else "ACCEPT"
                assert actual == expected, (name, budget, label, actual, expected)
                assert len(json.dumps(sent[0], ensure_ascii=False).encode()) <= 48 * 1024
                client_cases.append({"case": name, "context_messages_budget": budget, "manager": label,
                                     "outcome": actual, "sent": metadata(sent[0]["messages"]),
                                     "prior_rows_preserved": True, "rows_before": len(seed), "rows_after": len(after)})
    result = {"task": OUT.name, "status": "PASS", "scope": "Synthetic history, actual Client payload builder, old/R5 validators; no HTTP/inference/private data",
              "old_source_sha256": EXPECTED_OLD, "root": str(qa), "validator_cases": cases,
              "command": [sys.executable, "-X", "utf8", "-B", str(Path(__file__).resolve()), "--output", args.output],
              "seconds": round(time.perf_counter() - started, 3), "exit_code": 0,
              "http_note": "Direct validators, no HTTP; oversized direct boundary cases could fail body-size validation earlier. All 32 Client reproductions fit legacy 48KiB body limit and use exactly 3 legacy fields.",
              "client_exchange_cases": client_cases, "total_cases": len(cases) + len(client_cases),
              "real_user_root_cause": "NOT PROVEN: private history/failed payload/server were not inspected",
              "findings": ["Legacy count limit 16 includes current request; default Client history=100 can produce 35 messages from 34-row QA history",
                           "Legacy per-message 4000 and total 24000 differ from R5 defaults 131072/240000/128 messages",
                           "Legacy rejects reasoning_content key, R5 accepts valid assistant reasoning",
                           "History=0 excludes saved messages from request and does not delete them",
                           "Budgets 5/10 help counts but do not guarantee legacy compatibility for long text or reasoning",
                           "Validators enforce role whitelist/last user, not strict alternation; upstream-specific behavior NOT RUN",
                           "R5 still has explicit ceilings: e.g. 129 total messages rejected; no unlimited-history guarantee"],
              "installed_client_changed": False, "runtime_fix": "NONE: immutable release retained; diagnosis/recommendations only"}
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": "PASS", "validator_cases": len(cases), "client_exchange_cases": len(client_cases)}))


if __name__ == "__main__":
    main()
