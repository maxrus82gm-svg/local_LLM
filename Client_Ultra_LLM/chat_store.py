"""Private per-user CHAT-01 history; each Manager/slot/model is isolated.

SQLite lives next to existing protected Client credentials. No server-side chat
history or raw credentials are written to this database.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import re
import sqlite3
import threading
import hashlib
import json

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_LOCK = threading.RLock()
_SCHEMA = """CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    manager_id TEXT NOT NULL,
    slot_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','assistant')),
    content TEXT NOT NULL)"""


def validate_key(manager_id, slot_id, model_id):
    for value in (manager_id, slot_id, model_id):
        if not isinstance(value, str) or not _NAME.fullmatch(value):
            raise ValueError("invalid_chat_target")
    return manager_id, slot_id, model_id


def _database(folder: Path):
    path = folder / "chat_history.sqlite3"
    if path.is_symlink() or not folder.is_dir():
        raise OSError("invalid_chat_storage")
    return path


def _migrate(db):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == 1:
        return
    if version != 0:
        raise ValueError("unsupported_chat_schema")
    db.execute("BEGIN IMMEDIATE")
    db.execute(_SCHEMA)
    columns = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
    if "instance_id" not in columns:
        db.execute("ALTER TABLE messages ADD COLUMN instance_id TEXT NOT NULL DEFAULT ''")
    if "reasoning_content" not in columns:
        db.execute("ALTER TABLE messages ADD COLUMN reasoning_content TEXT NOT NULL DEFAULT ''")
    db.execute("CREATE TABLE IF NOT EXISTS chat_requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL)")
    db.execute("PRAGMA user_version=1")
    db.commit()


def history(folder, manager_id, slot_id, model_id, *, instance_id=None, limit=100):
    key = validate_key(manager_id, slot_id, model_id)
    path = _database(folder)
    if not path.exists():
        return []
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        _migrate(db)
        rows = db.execute(
            "SELECT role,content,reasoning_content FROM messages "
            "WHERE manager_id=? AND slot_id=? AND model_id=? AND instance_id=? "
            "ORDER BY id DESC LIMIT ?", (*key, instance_id or "", min(1024, max(1, limit)))).fetchall()
    return [{"role": role, "content": content, **({"reasoning_content": reasoning} if reasoning else {})}
            for role, content, reasoning in reversed(rows)]


def context_for(messages, *, max_messages=100, max_chars=200000, with_info=False):
    """User-visible history window; no guessed conversion from chars to tokens."""
    if type(max_messages) is not int or not 0 <= max_messages <= 1024 or type(max_chars) is not int or not 0 <= max_chars <= 1048576:
        raise ValueError("invalid_context_policy")
    selected, total = [], 0
    for m in reversed(messages):
        chars = len(m["content"]) + len(m.get("reasoning_content", ""))
        if total + chars > max_chars or len(selected) >= max_messages:
            break
        selected.append(m)
        total += chars
    selected.reverse()
    while selected and selected[0]["role"] != "user":
        selected.pop(0)
    info = {"available_messages":len(messages), "sent_history_messages":len(selected),
            "omitted_messages":len(messages)-len(selected), "history_char_budget":max_chars,
            "history_message_budget":max_messages, "units":"characters_not_tokens"}
    return (selected, info) if with_info else selected


def append_exchange(folder, manager_id, slot_id, model_id, user, reply, *, request_id=None, instance_id=None, reasoning=""):
    key = validate_key(manager_id, slot_id, model_id)
    if (not isinstance(user, str) or not isinstance(reply, str)
            or not user or not (reply or reasoning) or len(user) > 1048576 or len(reply) > 8388608 or type(reasoning) is not str or len(reasoning) > 8388608):
        raise ValueError("invalid_chat_exchange")
    path = _database(folder)
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        _migrate(db)
        if request_id is not None:
            row = db.execute("SELECT state FROM chat_requests WHERE request_id=?", (request_id,)).fetchone()
            if row != ("pending",):
                raise ValueError("chat_request_not_pending")
        db.executemany(
            "INSERT INTO messages(manager_id,slot_id,model_id,role,content,instance_id,reasoning_content) "
            "VALUES(?,?,?,?,?,?,?)",
            [(*key, "user", user, instance_id or "", ""), (*key, "assistant", reply, instance_id or "", reasoning)])
        # Keep prior conversations; limiting request context never deletes history.
        if request_id is not None:
            db.execute("UPDATE chat_requests SET state='complete' WHERE request_id=?", (request_id,))
        db.commit()
    return history(folder, *key, instance_id=instance_id)


def claim_request(folder, request_id, key, message, *, request_options=None):
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("invalid_request_id")
    fingerprint = hashlib.sha256(json.dumps([*key, message, request_options], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with _LOCK, closing(sqlite3.connect(_database(folder), timeout=8)) as db:
        _migrate(db)
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT fingerprint,state FROM chat_requests WHERE request_id=?", (request_id,)).fetchone()
        if row:
            if row[0] != fingerprint:
                raise ValueError("request_id_conflict")
            return row[1]
        db.execute("INSERT INTO chat_requests VALUES(?,?,'pending')", (request_id, fingerprint))
        db.commit()
        return "new"


def fail_request(folder, request_id):
    with _LOCK, closing(sqlite3.connect(_database(folder), timeout=8)) as db:
        db.execute("UPDATE chat_requests SET state='failed' WHERE request_id=? AND state='pending'", (request_id,))
        db.commit()
