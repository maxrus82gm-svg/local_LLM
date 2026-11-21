"""Private SQLite chats, with a compatibility mapping for the old slot API."""
from __future__ import annotations

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import re
import sqlite3
import stat
import threading
import uuid

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")
_ID = re.compile(r"[a-f0-9]{32}")
_LOCK = threading.RLock()
DEFAULT_CONTEXT = {"max_messages": 100, "max_chars": 200000}
DEFAULT_PREFERENCES = {"stream": True, "thinking": True}


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def validate_key(manager_id, slot_id, model_id):
    for value in (manager_id, slot_id, model_id):
        if not isinstance(value, str) or not _NAME.fullmatch(value):
            raise ValueError("invalid_chat_target")
    return manager_id, slot_id, model_id


def validate_chat_id(value):
    if type(value) is not str or not _ID.fullmatch(value):
        raise ValueError("invalid_chat_id")
    return value


def _safe_path(path):
    try:
        metadata = path.lstat()
    except FileNotFoundError:
        return path
    if path.is_symlink() or (getattr(metadata, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise OSError("invalid_chat_storage")
    return path


@contextmanager
def _connect(folder):
    folder = _safe_path(Path(folder))
    if not folder.is_dir():
        raise OSError("invalid_chat_storage")
    path = _safe_path(folder / "chat_history.sqlite3")
    with _LOCK, closing(sqlite3.connect(path, timeout=8)) as db:
        db.execute("PRAGMA foreign_keys=ON")
        _migrate(db, path)
        with db:
            db.execute("BEGIN IMMEDIATE")
            yield db


def _backup(db, path, *, target_version):
    # Reserve a new name without overwriting an earlier recovery file.
    backup = path.with_name(f"chat_history.pre-v{target_version}-{uuid.uuid4().hex}.sqlite3")
    with backup.open("xb"):
        pass
    with closing(sqlite3.connect(backup)) as destination:
        db.backup(destination)
        if destination.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise sqlite3.DatabaseError("chat_backup_integrity_failed")


def _migrate(db, path):
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == 3:
        return
    if version not in (0, 1, 2):
        raise ValueError("unsupported_chat_schema")
    # A separate read connection supplies a consistent snapshot while this
    # connection reserves the writer across backup and migration.
    with db:
        db.execute("BEGIN IMMEDIATE")
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version == 3:
            return
        if version not in (0, 1, 2):
            raise ValueError("unsupported_chat_schema")
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='messages'").fetchone():
            with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as source:
                _backup(source, path, target_version=3 if version == 2 else 2)
        if version < 2:
            _migrate_conversations(db)
        _link_message_metrics(db)
        db.execute("PRAGMA user_version=3")


def _migrate_conversations(db):
    db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, manager_id TEXT NOT NULL,
            slot_id TEXT NOT NULL, model_id TEXT NOT NULL, role TEXT NOT NULL
            CHECK (role IN ('user','assistant')), content TEXT NOT NULL)""")
    columns = {r[1] for r in db.execute("PRAGMA table_info(messages)")}
    if "instance_id" not in columns:
        db.execute("ALTER TABLE messages ADD COLUMN instance_id TEXT NOT NULL DEFAULT ''")
    db.execute("""CREATE TABLE chats (
            chat_id TEXT PRIMARY KEY, title TEXT NOT NULL, created_at TEXT,
            manager_id TEXT, slot_id TEXT, model_id TEXT, settings TEXT NOT NULL DEFAULT '{}',
            context_after INTEGER NOT NULL DEFAULT 0, cleared_through INTEGER NOT NULL DEFAULT 0,
            restore_to INTEGER,
            legacy INTEGER NOT NULL DEFAULT 0)""")
    db.execute("""CREATE TABLE legacy_chats (
            manager_id TEXT NOT NULL, slot_id TEXT NOT NULL, model_id TEXT NOT NULL, instance_id TEXT NOT NULL,
            chat_id TEXT NOT NULL REFERENCES chats ON DELETE CASCADE,
            PRIMARY KEY(manager_id,slot_id,model_id,instance_id))""")
    db.execute("ALTER TABLE messages ADD COLUMN chat_id TEXT REFERENCES chats ON DELETE CASCADE")
    db.execute("ALTER TABLE messages ADD COLUMN created_at TEXT")
    db.execute("CREATE INDEX messages_by_chat ON messages(chat_id,id)")
    db.execute("""CREATE TABLE reasoning (
            message_id INTEGER PRIMARY KEY REFERENCES messages ON DELETE CASCADE, content TEXT NOT NULL)""")
    if "reasoning_content" in columns:
        db.execute("INSERT INTO reasoning SELECT id,reasoning_content FROM messages WHERE reasoning_content<>''")
        db.execute("ALTER TABLE messages DROP COLUMN reasoning_content")
    for *key, instance in db.execute("SELECT DISTINCT manager_id,slot_id,model_id,instance_id FROM messages"):
        chat_id = _legacy_id(db, key, instance, create=True)
        db.execute("""UPDATE messages SET chat_id=? WHERE
                       manager_id=? AND slot_id=? AND model_id=? AND instance_id=?""", (chat_id, *key, instance))
    db.execute("""CREATE TABLE IF NOT EXISTS chat_requests (
            request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, state TEXT NOT NULL)""")
    db.execute("""CREATE TABLE request_metrics (
            request_id TEXT PRIMARY KEY, chat_id TEXT NOT NULL REFERENCES chats ON DELETE CASCADE,
            started_at TEXT NOT NULL, finished_at TEXT NOT NULL, state TEXT NOT NULL,
            metrics TEXT NOT NULL)""")
    db.execute("CREATE INDEX metrics_by_chat ON request_metrics(chat_id,started_at DESC)")


def _link_message_metrics(db):
    db.execute("ALTER TABLE messages ADD COLUMN request_id TEXT REFERENCES request_metrics ON DELETE SET NULL")
    db.execute("CREATE INDEX messages_by_request ON messages(request_id) WHERE request_id IS NOT NULL")
    # v2 saved each pair in one transaction using the measured start and finish UTC
    # timestamps. Import only one-to-one matches, including when timestamps collide.
    db.execute("""WITH candidates AS (
        SELECT u.id AS user_id, a.id AS assistant_id, r.request_id,
               COUNT(*) OVER (PARTITION BY r.request_id) AS request_matches,
               COUNT(*) OVER (PARTITION BY u.id) AS exchange_matches
        FROM messages u JOIN messages a ON a.id=u.id+1 AND a.chat_id=u.chat_id
        JOIN request_metrics r ON r.chat_id=u.chat_id AND r.started_at=u.created_at AND r.finished_at=a.created_at
        WHERE u.role='user' AND a.role='assistant' AND r.state='complete'
    ), matches AS (
        SELECT user_id, assistant_id, request_id FROM candidates WHERE request_matches=1 AND exchange_matches=1
    ), links AS (
        SELECT user_id AS message_id, request_id FROM matches
        UNION ALL
        SELECT assistant_id AS message_id, request_id FROM matches
    )
    UPDATE messages SET request_id=links.request_id FROM links WHERE messages.id=links.message_id""")


def _legacy_id(db, key, instance, *, create=False):
    identity = (*key, instance or "")
    result = db.execute("""SELECT chat_id FROM legacy_chats
        WHERE manager_id=? AND slot_id=? AND model_id=? AND instance_id=?""", identity).fetchone()
    if result:
        return result[0]
    if create:
        chat_id = uuid.uuid4().hex
        db.execute("""INSERT INTO chats(chat_id,title,manager_id,slot_id,model_id,legacy)
            VALUES(?,?,?,?,?,1)""", (chat_id, "Архив · " + " / ".join(key), *key))
        db.execute("INSERT INTO legacy_chats VALUES(?,?,?,?,?)", (*identity, chat_id))
        return chat_id
    return None


_CHAT_FIELDS = """chat_id,title,created_at,manager_id,slot_id,model_id,settings,
                  context_after,restore_to IS NOT NULL AS can_restore,legacy,
                  CASE WHEN legacy=0 AND EXISTS (
                      SELECT 1 FROM chats AS owner WHERE owner.legacy=0
                      AND owner.manager_id=chats.manager_id AND owner.slot_id=chats.slot_id
                      AND owner.rowid<chats.rowid
                  ) THEN 1 ELSE 0 END AS target_conflict"""


class ChatTargetOccupied(ValueError):
    """A named chat already owns the Manager slot."""


def _require_target_owner(db, target, chat_id=None):
    # Reserve the slot, not the display name, mode, or a model alias.
    # Keep older assignments until explicit unbind/rebind/delete.
    if target[0] is None:
        return
    owner = db.execute("""SELECT chat_id FROM chats WHERE legacy=0
        AND manager_id=? AND slot_id=? ORDER BY rowid LIMIT 1""", target[:2]).fetchone()
    if owner is not None and owner[0] != chat_id:
        raise ChatTargetOccupied("chat_target_occupied")


def require_unassigned_slot(folder, key):
    if not _safe_path(Path(folder) / "chat_history.sqlite3").exists():
        return
    with _connect(folder) as db:
        _require_target_owner(db, key)


def _chat(row):
    result = dict(row)
    saved = json.loads(result["settings"])
    result["preferences"] = {**DEFAULT_PREFERENCES, **saved.get("preferences", {})}
    result["settings"] = {**DEFAULT_CONTEXT, **{k:v for k,v in saved.items() if k in DEFAULT_CONTEXT}}
    return result


def _get_chat(db, chat_id):
    db.row_factory = sqlite3.Row
    row = db.execute(f"SELECT {_CHAT_FIELDS} FROM chats WHERE chat_id=?", (validate_chat_id(chat_id),)).fetchone()
    if row is None:
        raise KeyError("chat_not_found")
    return _chat(row)


def get_chat(folder, chat_id):
    with _connect(folder) as db:
        return _get_chat(db, chat_id)


def legacy_chat_id(folder, key, instance_id):
    if not _safe_path(Path(folder) / "chat_history.sqlite3").exists():
        return None
    with _connect(folder) as db:
        return _legacy_id(db, key, instance_id)


def list_chats(folder):
    with _connect(folder) as db:
        db.row_factory = sqlite3.Row
        return [_chat(row) for row in db.execute(f"SELECT {_CHAT_FIELDS} FROM chats ORDER BY rowid DESC")]


def manage_chat(folder, op, data):
    with _connect(folder) as db:
        if op == "create":
            chat_id = uuid.uuid4().hex
            target = _target(data.get("target"))
            _require_target_owner(db, target)
            db.execute("INSERT INTO chats(chat_id,title,created_at,manager_id,slot_id,model_id) VALUES(?,?,?,?,?,?)",
                       (chat_id, _title(data.get("title", "Новый чат")), utc_now(), *target))
        else:
            chat_id = data["chat_id"]
            current = _get_chat(db, chat_id)
            if op == "rename":
                db.execute("UPDATE chats SET title=? WHERE chat_id=?", (_title(data["title"]), chat_id))
            elif op == "target":
                target = _target(data["target"])
                _require_target_owner(db, target, chat_id)
                db.execute("UPDATE chats SET manager_id=?,slot_id=?,model_id=?,legacy=0 WHERE chat_id=?",
                           (*target, chat_id))
            elif op == "settings":
                settings = data["context"]
                if type(settings) is not dict or set(settings) != set(DEFAULT_CONTEXT):
                    raise ValueError("invalid_context_policy")
                context_for([], **settings)
                saved = {**settings, "preferences":current["preferences"]}
                db.execute("UPDATE chats SET settings=? WHERE chat_id=?", (json.dumps(saved), chat_id))
            elif op == "preferences":
                preferences = data["preferences"]
                if type(preferences) is not dict or set(preferences) != set(DEFAULT_PREFERENCES) or any(type(v) is not bool for v in preferences.values()):
                    raise ValueError("invalid_chat_preferences")
                saved = {**current["settings"], "preferences":preferences}
                db.execute("UPDATE chats SET settings=? WHERE chat_id=?", (json.dumps(saved), chat_id))
            elif op in ("reset", "clear"):
                last = db.execute("SELECT COALESCE(MAX(id),0) FROM messages WHERE chat_id=?", (chat_id,)).fetchone()[0]
                if op == "reset":
                    db.execute("UPDATE chats SET context_after=? WHERE chat_id=?", (last, chat_id))
                else:
                    db.execute("""UPDATE chats SET restore_to=COALESCE(restore_to,cleared_through),
                        cleared_through=?,context_after=? WHERE chat_id=? AND cleared_through<?""",
                        (last, last, chat_id, last))
            elif op == "resume":
                db.execute("UPDATE chats SET context_after=0 WHERE chat_id=?", (chat_id,))
            elif op == "restore":
                db.execute("UPDATE chats SET cleared_through=COALESCE(restore_to,cleared_through),restore_to=NULL WHERE chat_id=?",
                           (chat_id,))
            elif op == "delete":
                db.execute("DELETE FROM chats WHERE chat_id=?", (chat_id,))
                return {"deleted": True}
            else:
                raise ValueError("invalid_chat_operation")
        return _get_chat(db, chat_id)


def _title(value):
    if type(value) is not str or not 1 <= len(value.strip()) <= 120:
        raise ValueError("invalid_chat_title")
    return value.strip()


def _target(value):
    if value is None:
        return None, None, None
    if type(value) is not dict or set(value) != {"manager_id", "slot_id", "model_id"}:
        raise ValueError("invalid_chat_target")
    return validate_key(*(value[name] for name in ("manager_id", "slot_id", "model_id")))


def _history(db, chat_id, limit, *, context=False, timestamps=False):
    # The context reader deliberately never reads from the reasoning archive.
    if context:
        cutoff = "MAX(c.cleared_through,c.context_after)"
        archive = "''"
        join = ""
    else:
        cutoff = "c.cleared_through"
        archive = "r.content"
        join = "LEFT JOIN reasoning r ON r.message_id=m.id"
    metrics_column = "NULL"
    if timestamps:
        metrics_column = "measurement.metrics"
        join += """ LEFT JOIN request_metrics measurement ON measurement.request_id=m.request_id
                    AND measurement.chat_id=m.chat_id AND measurement.state='complete'"""
    rows = db.execute(f"""SELECT m.role,m.content,{archive},m.created_at,{metrics_column}
        FROM messages m JOIN chats c ON c.chat_id=m.chat_id {join}
        WHERE m.chat_id=? AND m.id>{cutoff} ORDER BY m.id DESC LIMIT ?""",
        (chat_id, min(1024, max(1, limit)))).fetchall()
    return [{"role": role, "content": content, **({"reasoning_content": reasoning} if reasoning else {}),
             **({"created_at": created_at} if timestamps else {}),
             **({"metrics": _message_metrics(metrics)} if metrics else {})}
            for role, content, reasoning, created_at, metrics in reversed(rows)]


def _message_metrics(raw):
    data = json.loads(raw)
    return {key: data[key] for key in ("first_fragment_ms", "generation_ms", "total_ms", "usage", "throughput")
            if key in data}


def history(folder, manager_id=None, slot_id=None, model_id=None, *, instance_id=None,
            limit=100, chat_id=None, context=False):
    if chat_id is None:
        key = validate_key(manager_id, slot_id, model_id)
        if not _safe_path(Path(folder) / "chat_history.sqlite3").exists():
            return []
    with _connect(folder) as db:
        if chat_id is not None:
            _get_chat(db, chat_id)
            return _history(db, chat_id, limit, context=context, timestamps=not context)
        return _history(db, _legacy_id(db, key, instance_id), limit, context=context)


def request_context(folder, key, instance_id, chat_id, policy, *, byte_budget):
    if chat_id is None and not _safe_path(Path(folder) / "chat_history.sqlite3").exists():
        return context_for([], **policy, with_info=True)
    with _connect(folder) as db:
        if chat_id is not None:
            _get_chat(db, chat_id)
        else:
            chat_id = _legacy_id(db, key, instance_id)
        count = db.execute("""SELECT COUNT(*) FROM messages m JOIN chats c ON c.chat_id=m.chat_id
            WHERE m.chat_id=? AND m.id>c.cleared_through""", (chat_id,)).fetchone()[0]
        cursor = db.execute("""SELECT m.role,m.content FROM messages m JOIN chats c ON c.chat_id=m.chat_id
            WHERE m.chat_id=? AND m.id>MAX(c.cleared_through,c.context_after) ORDER BY m.id DESC""", (chat_id,))
        selected, info = _select_context(({"role":role, "content":content} for role, content in cursor),
                                         byte_budget=byte_budget, **policy)
    info["available_messages"] = count
    info["omitted_messages"] = count - len(selected)
    return selected, info


def context_for(messages, *, max_messages=100, max_chars=200000, with_info=False):
    """Select whole text messages, dropping any orphaned leading assistant."""
    selected, info = _select_context(reversed(messages), max_messages=max_messages, max_chars=max_chars)
    info.update(available_messages=len(messages), omitted_messages=len(messages)-len(selected))
    return (selected, info) if with_info else selected


def _select_context(newest_first, *, max_messages, max_chars, byte_budget=None):
    if type(max_messages) is not int or not 0 <= max_messages <= 1024 or type(max_chars) is not int or not 0 <= max_chars <= 1048576:
        raise ValueError("invalid_context_policy")
    selected, total = [], 0
    total_bytes = 0
    for m in newest_first if max_messages else ():
        role, content = m["role"], m["content"]
        if role not in ("user", "assistant") or type(content) is not str or "\x00" in content:
            raise ValueError("invalid_context_message")
        if not content.strip():
            continue
        if total + len(content) > max_chars or len(selected) >= max_messages:
            break
        clean = {"role": role, "content": content}
        if byte_budget is not None:
            total_bytes += wire_bytes(clean) + 2
            if total_bytes > byte_budget:
                break
        selected.append(clean)
        total += len(content)
    while selected and selected[-1]["role"] != "user":
        total -= len(selected.pop()["content"])
    selected.reverse()
    info = {"sent_history_messages": len(selected), "history_char_budget": max_chars,
            "history_message_budget": max_messages, "sent_history_chars": total, "units": "characters_not_tokens"}

    return selected, info


def wire_bytes(value):
    try:
        return len(json.dumps(value, ensure_ascii=False).encode("utf-8"))
    except UnicodeError:
        raise ValueError("invalid_chat_text_encoding") from None


def append_exchange(folder, manager_id, slot_id, model_id, user, reply, *, request_id=None,
                    instance_id=None, reasoning="", chat_id=None, metrics=None):
    key = validate_key(manager_id, slot_id, model_id)
    if (type(user) is not str or type(reply) is not str or type(reasoning) is not str
            or not user or not (reply or reasoning) or len(user) > 1048576 or max(len(reply), len(reasoning)) > 8388608):
        raise ValueError("invalid_chat_exchange")
    with _connect(folder) as db:
        if request_id is not None:
            row = db.execute("SELECT state FROM chat_requests WHERE request_id=?", (request_id,)).fetchone()
            if row != ("pending",):
                raise ValueError("chat_request_not_pending")
        selected = chat_id or _legacy_id(db, key, instance_id, create=True)
        linked_request = None
        if request_id is not None and chat_id is not None and metrics is not None:
            _save_metrics(db, request_id, chat_id, "complete", metrics)
            linked_request = request_id
        insert = """INSERT INTO messages(manager_id,slot_id,model_id,role,content,instance_id,chat_id,created_at,request_id)
                    VALUES(?,?,?,?,?,?,?,?,?)"""
        db.execute(insert, (*key, "user", user, instance_id or "", selected,
                            (metrics or {}).get("started_at") or utc_now(), linked_request))
        assistant = db.execute(insert, (*key, "assistant", reply, instance_id or "", selected,
                                        (metrics or {}).get("finished_at") or utc_now(), linked_request))
        if reasoning:
            db.execute("INSERT INTO reasoning VALUES(?,?)", (assistant.lastrowid, reasoning))
        if request_id is not None:
            db.execute("UPDATE chat_requests SET state='complete' WHERE request_id=?", (request_id,))
        return _history(db, selected, 100, timestamps=chat_id is not None)


def claim_request(folder, request_id, key, message, *, request_options=None):
    validate_chat_id(request_id)
    fingerprint = hashlib.sha256(json.dumps([*key, message, request_options], ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    with _connect(folder) as db:
        row = db.execute("SELECT fingerprint,state FROM chat_requests WHERE request_id=?", (request_id,)).fetchone()
        if row:
            if row[0] != fingerprint:
                raise ValueError("request_id_conflict")
            return row[1]
        db.execute("INSERT INTO chat_requests VALUES(?,?,'pending')", (request_id, fingerprint))
        return "new"


def _save_metrics(db, request_id, chat_id, state, metrics):
    db.execute("INSERT INTO request_metrics VALUES(?,?,?,?,?,?)",
               (request_id, chat_id, metrics["started_at"], metrics["finished_at"], state, json.dumps(metrics)))


def fail_request(folder, request_id, *, chat_id=None, metrics=None, state="failed"):
    with _connect(folder) as db:
        updated = db.execute("UPDATE chat_requests SET state='failed' WHERE request_id=? AND state='pending'", (request_id,))
        if updated.rowcount and chat_id is not None and metrics is not None:
            _save_metrics(db, request_id, chat_id, state, metrics)


def recent_metrics(folder, chat_id, limit=25):
    with _connect(folder) as db:
        _get_chat(db, chat_id)
        return [{"request_id": request_id, "state": state, **json.loads(metrics)}
                for request_id, state, metrics in db.execute("""SELECT request_id,state,metrics FROM request_metrics
                    WHERE chat_id=? ORDER BY started_at DESC,rowid DESC LIMIT ?""", (chat_id, limit))]
