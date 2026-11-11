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
        if total + chars > 18000 or len(selected) == 14:
            break
        selected.append(m)
        total += chars
    selected.reverse()
    while selected and selected[0]["role"] != "user":
        selected.pop(0)
    return selected


def append_exchange(folder, manager_id, slot_id, model_id, user, reply):
    key = validate_key(manager_id, slot_id, model_id)
    if (not isinstance(user, str) or not isinstance(reply, str)
            or not user or not reply or len(user) > 4000 or len(reply) > 65536):
        raise ValueError("invalid_chat_exchange")
    path = _database(folder)
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        db.execute(_SCHEMA)
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
        db.commit()
    return history(folder, *key)
