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


def history(folder, manager_id, slot_id, model_id):
    key = validate_key(manager_id, slot_id, model_id)
    path = _database(folder)
    if not path.exists():
        return []
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        db.execute(_SCHEMA)
        rows = db.execute(
            "SELECT role,content FROM messages "
            "WHERE manager_id=? AND slot_id=? AND model_id=? "
            "ORDER BY id DESC LIMIT 100", key).fetchall()
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def context_for(messages):
    """Last complete turns, with bounded count and total characters."""
    selected, total = [], 0
    for m in reversed(messages):
        chars = len(m["content"])
        if chars > 4000 or total + chars > 18000 or len(selected) == 14:
            break
        selected.append(m)
        total += chars
    selected.reverse()
    while selected and selected[0]["role"] != "user":
        selected.pop(0)
    return selected


def append_exchange(folder, manager_id, slot_id, model_id, user, reply, *, request_id=None):
    key = validate_key(manager_id, slot_id, model_id)
    if (not isinstance(user, str) or not isinstance(reply, str)
            or not user or not reply or len(user) > 4000 or len(reply) > 65536):
        raise ValueError("invalid_chat_exchange")
    path = _database(folder)
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        db.execute(_SCHEMA)
        if request_id is not None:
            row = db.execute("SELECT state FROM chat_requests WHERE request_id=?", (request_id,)).fetchone()
            if row != ("pending",):
                raise ValueError("chat_request_not_pending")
        db.executemany(
            "INSERT INTO messages(manager_id,slot_id,model_id,role,content) "
            "VALUES(?,?,?,?,?)",
            [(*key, "user", user), (*key, "assistant", reply)])
        # Retain the most recent 100 messages per Manager/slot/model.
        db.execute(
            "DELETE FROM messages WHERE manager_id=? AND slot_id=? AND model_id=? "
            "AND id NOT IN (SELECT id FROM messages "
            "WHERE manager_id=? AND slot_id=? AND model_id=? "
            "ORDER BY id DESC LIMIT 100)", (*key, *key))
        if request_id is not None:
            db.execute("UPDATE chat_requests SET state='complete' WHERE request_id=?", (request_id,))
        db.commit()
    return history(folder, *key)


def claim_request(folder, request_id, key, message):
    if not isinstance(request_id, str) or not re.fullmatch(r"[a-f0-9]{32}", request_id):
        raise ValueError("invalid_request_id")
    fingerprint = hashlib.sha256(json.dumps([*key, message], ensure_ascii=False).encode()).hexdigest()
    with _LOCK, closing(sqlite3.connect(_database(folder), timeout=8)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS chat_requests (request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL)")
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
