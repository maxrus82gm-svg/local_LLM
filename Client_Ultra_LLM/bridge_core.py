"""Client Bridge v1: private, stateless request primitives. No network at import."""
from contextlib import contextmanager, closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import stat
import uuid

VERSION = "1.0.0"
RID = re.compile(r"[a-f0-9]{32}")
TARGET = re.compile(r"tgt_[a-f0-9]{64}")
INSTANCE = re.compile(r"(?:[a-f0-9]{32}|legacy-[A-Za-z0-9_.-]{1,96})")
TERMINAL = frozenset(("SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"))
ACTIVE = frozenset(("ACCEPTED", "RUNNING", "CANCEL_REQUESTED"))
TRANSITIONS = {
    "ACCEPTED": {"RUNNING", "CANCEL_REQUESTED", "FAILED", "CANCELLED", "UNKNOWN"},
    "RUNNING": {"CANCEL_REQUESTED", "SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"},
    "CANCEL_REQUESTED": {"SUCCEEDED", "FAILED", "CANCELLED", "UNKNOWN"},
    "UNKNOWN": {"SUCCEEDED", "FAILED", "CANCELLED"},
    "SUCCEEDED": set(), "FAILED": set(), "CANCELLED": set(),
}


class BridgeError(Exception):
    def __init__(self, code, status, *, request_id=None, upstream_code=None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.data = {"code": code, "message": code.replace("_", " "),
                     "retryable": False}
        if isinstance(request_id, str) and RID.fullmatch(request_id):
            self.data["request_id"] = request_id
        if isinstance(upstream_code, str) and re.fullmatch(r"[a-z0-9_]{1,80}", upstream_code):
            self.data["upstream_code"] = upstream_code


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def private_path(path):
    path = Path(path)
    try:
        st = path.lstat()
    except FileNotFoundError:
        return path
    if path.is_symlink() or getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
        raise PermissionError("bridge private path is a link")
    return path


def canonical(value):
    # All allowed request/identity object keys are fixed ASCII, numbers are
    # bounded integers; this restricted domain implements the JCS encoding.
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def no_duplicates(pairs):
    result = {}
    for k, v in pairs:
        if k in result:
            raise ValueError("duplicate JSON member")
        result[k] = v
    return result


def target_id(bridge_id, manager_id, slot_id, model_key):
    return "tgt_" + hashlib.sha256(canonical([bridge_id, manager_id, slot_id, model_key])).hexdigest()


def digest(request):
    return hashlib.sha256(canonical({k:v for k,v in request.items()
                                     if k not in ("request_id", "catalog_revision")})).hexdigest()


def validate_request(value, *, cancel=False):
    required = {"request_id", "target_id", "instance_id"} | (set() if cancel else {"messages"})
    allowed = required | (set() if cancel else {"catalog_revision", "conversation_id", "turn_id", "options"})
    def bad():
        raise BridgeError("invalid_request", 400)
    if type(value) is not dict or not required <= value.keys() or value.keys() - allowed:
        bad()
    for k, pat in (("request_id", RID), ("target_id", TARGET), ("instance_id", INSTANCE)):
        if type(value[k]) is not str or not pat.fullmatch(value[k]):
            bad()
    if cancel:
        return value
    for k in ("catalog_revision", "conversation_id", "turn_id"):
        if k in value and (type(value[k]) is not str or not 1 <= len(value[k]) <= 256):
            bad()
    messages = value["messages"]
    if type(messages) is not list or not messages:
        bad()
    for message in messages:
        if (type(message) is not dict or not {"role", "content"} <= message.keys()
                or message.keys() - {"role", "content", "reasoning_content"}):
            bad()
        role, content = message["role"], message["content"]
        if type(role) is not str or type(content) is not str:
            bad()
        if role in ("system", "developer", "tool"):
            raise BridgeError("unsupported_capability", 422, request_id=value["request_id"])
        if role not in ("user", "assistant"):
            bad()
        if "reasoning_content" in message and (role != "assistant" or type(message["reasoning_content"]) is not str):
            bad()
        if not content and (role != "assistant" or not message.get("reasoning_content")):
            bad()
    if messages[-1]["role"] != "user":
        bad()
    options = value.get("options", {})
    if (type(options) is not dict or options.keys() - {"thinking", "reasoning_effort", "max_output_tokens"}
            or options.get("thinking", "auto") not in ("auto", "on", "off")
            or options.get("reasoning_effort", "auto") not in ("auto", "minimal", "low", "medium", "high", "xhigh")):
        bad()
    if options.get("thinking") == "off" and options.get("reasoning_effort", "auto") != "auto":
        bad()
    if "max_output_tokens" in options and (type(options["max_output_tokens"]) is not int or
                                             not 1 <= options["max_output_tokens"] <= 2147483647):
        bad()
    try:
        canonical(value)
    except (ValueError, UnicodeError, TypeError):
        bad()
    return value


def usage(raw=None):
    raw = raw if isinstance(raw, dict) else {}
    keys = ("prompt_tokens", "completion_tokens", "total_tokens",
            "reasoning_tokens", "cached_prompt_tokens")
    out = {k: raw[k] if type(raw.get(k)) is int and raw[k] >= 0 else None for k in keys}
    p, c, t = (out[k] for k in keys[:3])
    basis = raw.get("prompt_basis")
    if basis not in ("includes_cached", "excludes_cached"):
        basis = "unknown"
    # The current Manager only reports the first two counters, if supplied.
    # A derived sum preserves the original prompt basis; it is not reported total.
    derived = t is None and p is not None and c is not None
    if derived:
        out["total_tokens"] = p + c
    if out["reasoning_tokens"] is not None and c is not None and out["reasoning_tokens"] > c:
        out["reasoning_tokens"] = None
    if (basis == "includes_cached" and p is not None and out["cached_prompt_tokens"] is not None
            and out["cached_prompt_tokens"] > p):
        out["cached_prompt_tokens"] = None
    known = any(v is not None for v in out.values())
    out.update(status=("reported" if all(x is not None for x in (p,c,t)) else "partial" if known else "unavailable"),
               source=("provider_and_derived_total" if derived else "provider" if known else "unavailable"),
               prompt_basis=basis if known else "unknown")
    return out


class Journal:
    """One durable attempt per (principal, request_id); never stores content."""
    def __init__(self, folder):
        self.path = private_path(Path(folder) / "bridge-requests.sqlite3")
        for suffix in ("-journal", "-wal", "-shm"):
            private_path(str(self.path) + suffix)
        with self.tx() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS attempts(
                principal TEXT NOT NULL, request_id TEXT NOT NULL, request_digest TEXT NOT NULL,
                manager_request_id TEXT NOT NULL UNIQUE, target_id TEXT NOT NULL, instance_id TEXT NOT NULL,
                conversation_id TEXT, turn_id TEXT, state TEXT NOT NULL, created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL, terminal_at TEXT, last_sequence INTEGER,
                usage_json TEXT, error_json TEXT, telemetry_json TEXT, finish_reason TEXT,
                cancel_intent INTEGER NOT NULL DEFAULT 0, details_retained INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY(principal, request_id))""")
            for row in db.execute("SELECT principal,request_id FROM attempts WHERE state IN ('ACCEPTED','RUNNING','CANCEL_REQUESTED')").fetchall():
                self._change(db, row["principal"], row["request_id"], "UNKNOWN",
                             error=BridgeError("upstream_failed", 503, request_id=row["request_id"]).data)

    @contextmanager
    def tx(self):
        private_path(self.path)
        with closing(sqlite3.connect(self.path, timeout=8)) as db:
            db.row_factory = sqlite3.Row
            with db:
                db.execute("BEGIN IMMEDIATE")
                yield db

    @staticmethod
    def _row(db, principal, rid):
        return db.execute("SELECT * FROM attempts WHERE principal=? AND request_id=?", (principal,rid)).fetchone()

    def get(self, principal, rid):
        with self.tx() as db:
            row = self._row(db, principal, rid)
            if row is None:
                raise BridgeError("unknown_request", 404, request_id=rid)
            return dict(row)

    @staticmethod
    def _duplicate(row, value):
        if row is not None:
            raise BridgeError("request_already_attempted" if row["request_digest"] == digest(value)
                              else "request_conflict", 409, request_id=value["request_id"])

    def check_duplicate(self, principal, value):
        with self.tx() as db:
            self._duplicate(self._row(db, principal, value["request_id"]), value)

    def claim(self, principal, value):
        rid = value["request_id"]
        with self.tx() as db:
            self._duplicate(self._row(db, principal, rid), value)
            stamp = now()
            manager_rid = uuid.uuid4().hex
            db.execute("""INSERT INTO attempts(principal,request_id,request_digest,manager_request_id,
                       target_id,instance_id,conversation_id,turn_id,state,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                       (principal,rid,digest(value),manager_rid,value["target_id"],value["instance_id"],
                        value.get("conversation_id"),value.get("turn_id"),"ACCEPTED",stamp,stamp))
        return manager_rid

    @staticmethod
    def _change(db, principal, rid, state, *, error=None, result_usage=None, telemetry=None, finish=None, sequence=None):
        row = Journal._row(db, principal, rid)
        if row is None:
            raise BridgeError("unknown_request",404,request_id=rid)
        if state not in TRANSITIONS[row["state"]]:
            return dict(row)
        stamp = now()
        term = stamp if state in TERMINAL else None
        db.execute("""UPDATE attempts SET state=?,updated_at=?,terminal_at=?,
                   error_json=?,usage_json=?,telemetry_json=?,finish_reason=?,last_sequence=COALESCE(?,last_sequence)
                   WHERE principal=? AND request_id=?""",
                   (state,stamp,term,json.dumps(error) if error is not None else None,
                    json.dumps(result_usage) if result_usage is not None else None,
                    json.dumps(telemetry) if telemetry is not None else None,finish,sequence,principal,rid))
        return dict(Journal._row(db, principal, rid))

    def change(self, principal, rid, state, **kwargs):
        with self.tx() as db:
            return self._change(db, principal, rid, state, **kwargs)

    def mark_cancel(self, principal, rid):
        with self.tx() as db:
            row = self._row(db, principal, rid)
            if row is None:
                raise BridgeError("unknown_request",404,request_id=rid)
            if row["state"] in ACTIVE:
                db.execute("UPDATE attempts SET cancel_intent=1 WHERE principal=? AND request_id=?", (principal,rid))
                if row["state"] != "CANCEL_REQUESTED":
                    self._change(db, principal, rid, "CANCEL_REQUESTED")
            return dict(self._row(db, principal, rid))

    def sequence(self, principal, rid, seq):
        with self.tx() as db:
            db.execute("""UPDATE attempts SET last_sequence=?,updated_at=?
                       WHERE principal=? AND request_id=? AND (last_sequence IS NULL OR last_sequence<?)""",
                       (seq,now(),principal,rid,seq))

    @staticmethod
    def public(row):
        out = {k:row[k] for k in ("request_id","target_id","instance_id","state","created_at","updated_at",
                                   "terminal_at","last_sequence","finish_reason")}
        out["usage"] = json.loads(row["usage_json"]) if row["usage_json"] else None
        out["error"] = json.loads(row["error_json"]) if row["error_json"] else None
        out["details_retained"] = bool(row["details_retained"])
        return out

    def prune_details(self, principal, rid):
        """Explicit retention operation; keep identity/digest and terminal tombstone."""
        with self.tx() as db:
            db.execute("""UPDATE attempts SET details_retained=0,usage_json=NULL,error_json=NULL,telemetry_json=NULL,
                       finish_reason=NULL,conversation_id=NULL,turn_id=NULL
                       WHERE principal=? AND request_id=? AND state IN ('SUCCEEDED','FAILED','CANCELLED','UNKNOWN')""",
                       (principal,rid))
