"""Colibri Client Bridge v1 runtime. Same existing Client process, opt-in only."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import sqlite3
import stat
import threading
import time
import uuid

from bridge_core import (VERSION, RID, INSTANCE, ACTIVE, TERMINAL, BridgeError,
                         Journal, canonical, no_duplicates, private_path,
                         target_id, validate_request, usage)
from chat_client import ChatClientError, manager_open, stream_chat, cancel_chat
from live_client import load_profiles

MAX_BRIDGE_BODY = 9 * 1024 * 1024   # explicit HTTP safety bound, not token ceiling
DISCOVERY_NAME = "bridge-discovery.json"
TOKEN_NAME = "bridge-wua.token"
IDENTITY_NAME = "bridge-identity.json"
UNSUPPORTED = {k:"unsupported" for k in ("detached_generation","replay","model_control")}
TRANSPORT_FIELDS = ("request_bytes","history_messages","history_chars","message_chars",
                    "response_chars","stream_bytes","timeout_seconds")
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}")


def _private_read(path):
    path = private_path(path)
    if not path.is_file():
        raise PermissionError("bridge private file unavailable")
    if os.name != "nt" and path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
        raise PermissionError("bridge private file permissions")
    return path.read_bytes()


def _private_create(path, data):
    path = private_path(path)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())


def _private_replace(path, data):
    path = private_path(path)
    temp = path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    try:
        _private_create(temp, data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _valid_text(value):
    return type(value) is str and 1 <= len(value) <= 256


def _safe_id(value):
    return type(value) is str and bool(SAFE_ID.fullmatch(value))


def _pos(value):
    return value if type(value) is int and value > 0 else None


def _ms(value):
    return value if type(value) in (int,float) and 0 <= value < float("inf") else None


def _limits(policy, engine, *, context=None):
    policy = policy if type(policy) is dict else {}
    engine = engine if type(engine) is dict else {}
    return {"context_tokens":_pos(engine.get("context_tokens")) or _pos(context),
            "max_output_tokens":_pos(engine.get("max_tokens")),
            **{("idle_timeout_seconds" if k=="timeout_seconds" else k):_pos(policy.get(k))
               for k in TRANSPORT_FIELDS}}


def _capabilities(chat, model):
    streaming = "supported" if chat.get("streaming") is True else "unknown"
    reasoning = "supported" if chat.get("reasoning_events") is True else "unknown"
    # Transport support is verified; actual model-specific controls are
    # conservative until verified. A known Qwen coder limitation is explicit.
    qwen = "qwen3-coder" in model.lower()
    return {"streaming":streaming,"reasoning_events":reasoning,"usage":"unknown",
            "thinking":"unsupported" if qwen else "unknown",
            "reasoning_effort":"unsupported" if qwen else "unknown",
            "max_output_tokens":"supported" if streaming=="supported" else "unknown",
            "system_role":"unsupported","tool_calling":"unsupported",
            "assistant_reasoning_input":"unknown","live_steering":"unsupported",**UNSUPPORTED}


def _launch():
    return {"actual_config_id":None,"actual_revision":None,"default_config_id":None,
            "default_revision":None,"hardware_profile_id":None,"configuration_lab":"unsupported"}


def _manager_snapshot(profile):
    # Existing credential/TLS transport; do not follow redirects or use system proxy.
    with manager_open(profile, "/v1/snapshot", timeout=15) as response:
        raw = response.read(256 * 1024 + 1)
    if len(raw) > 256 * 1024:
        raise ChatClientError("invalid_snapshot",502)
    data = json.loads(raw)
    if (type(data) is not dict or data.get("schema") != "ultra.manager.live.v1"
            or data.get("source") != "LIVE_HOST" or data.get("manager_id") != profile["manager_id"]
            or data.get("viewer_id") != profile["client_id"]
            or data.get("admission_enabled") is not False or data.get("reservation_granted") is not False
            or type(data.get("slots")) is not list or type(data.get("memory")) is not dict):
        raise ChatClientError("invalid_snapshot",502)
    return data


def targets_from_snapshot(bridge_id, profile, data):
    """Only verified live/control mappings are offered; no guessed aliases."""
    control = data.get("control") or {}
    if type(control) is not dict or control.get("manager_id") != profile["manager_id"]:
        return []
    chat = data.get("chat") or {}
    if type(chat) is not dict:
        return []
    entries = {m["key"]:m for m in control.get("models", []) if type(m) is dict and _safe_id(m.get("key"))}
    defs = {s["slot_id"]:s for s in control.get("slots", []) if type(s) is dict and _safe_id(s.get("slot_id")) and s.get("authorized") is True}
    live = {s["slot_id"]:s for s in data["slots"] if type(s) is dict and _safe_id(s.get("slot_id"))}
    instances = [i for i in control.get("instances", []) if type(i) is dict and i.get("released") is False]
    targets = []
    for sid, definition in defs.items():
        slot = live.get(sid, {})
        identity = slot.get("instance_id")
        identity = identity if type(identity) is str and INSTANCE.fullmatch(identity) else None
        models = slot.get("models", [])
        models = [m for m in models if _safe_id(m)] if type(models) is list else []
        active = [i for i in instances if i.get("slot_id")==sid]
        active = active[0] if len(active)==1 and active[0].get("instance_id")==identity else None
        pairs = []
        if active is not None and _safe_id(active.get("model_key")) and _safe_id(active.get("model_id")):
            pairs.append((active["model_key"],active["model_id"],active))
        elif identity and identity.startswith("legacy-"):
            for model in models:
                keys = [k for k,m in entries.items() if type(m.get("api_ids")) is list and model in m["api_ids"]]
                if len(keys)==1:
                    pairs.append((keys[0],model,None))
        elif not identity:
            key = definition.get("model_key")
            entry = entries.get(key, {})
            ids = entry.get("api_ids", [])
            if type(ids) is list and len(ids)==1 and _safe_id(ids[0]):
                pairs.append((key,ids[0],None))
        for key, model, managed in pairs:
            caps = _capabilities(chat,model)
            actual = identity if model in models else None
            if (actual and slot.get("engine_state")=="ready" and slot.get("availability")=="ready_unreserved"
                    and (managed is None or managed.get("state")=="READY") and caps["streaming"]=="supported"):
                state = "READY"
            elif actual and slot.get("availability")=="busy":
                state = "BUSY"
            elif slot.get("engine_state")=="not_running" or (managed and managed.get("state") in ("STARTING","STOPPING","ERROR","STOPPED")):
                state = "NOT_READY"
            else:
                state = "UNKNOWN"
            mode = managed.get("mode") if managed else None
            label = entries.get(key,{}).get("name")
            targets.append({"target_id":target_id(bridge_id,profile["manager_id"],sid,key),
                            "bridge_id":bridge_id,"manager_id":profile["manager_id"],"slot_id":sid,
                            "model_key":key,"model_id":model,"instance_id":actual,
                            "model_revision":None,"display_name":label if _valid_text(label) else model,
                            "manager_name":profile.get("display_name") if _valid_text(profile.get("display_name")) else profile["manager_id"],
                            "status":state,"execution_mode":mode.upper() if mode in ("cpu","cuda") else None,
                            "engine":None,"engine_version":None,"capabilities":caps,
                            "limits":_limits(chat.get("transport_policy"),{},context=slot.get("context_tokens")),
                            "launch_configuration":_launch(),"allowed_operations":["chat"] if state=="READY" else []})
    # One stable target may not ambiguously identify multiple upstream IDs.
    counts = {t["target_id"]:sum(x["target_id"]==t["target_id"] for x in targets) for t in targets}
    return [t for t in targets if counts[t["target_id"]]==1]


def _error_from_manager(error, rid, *, seen_meta):
    reason = getattr(error,"reason","manager_connection_failed")
    code, status = {
        "instance_identity_mismatch":("stale_instance",409),
        "slot_chat_in_progress":("slot_busy",409),"slot_busy_or_unknown":("slot_busy",409),
        "stream_in_progress":("slot_busy",409),
        "model_not_running":("target_not_ready",409),"unknown_slot":("unknown_target",404),
        "slot_not_authorized":("forbidden",403),"stream_not_authorized":("forbidden",403),
        "thinking_not_supported":("unsupported_capability",422),
        "requested_output_exceeds_engine_limit":("output_limit",422),
        "invalid_messages":("invalid_request",400),"invalid_model_id":("invalid_request",400),
        "invalid_generation_options":("invalid_request",400),
        "stream_identity_mismatch":("identity_mismatch",503),
        "stream_sequence_mismatch":("protocol_error",503),"invalid_stream_event":("protocol_error",503),
        "stream_idle_timeout":("transport_timeout",503),"stream_cancelled":("cancel_not_confirmed",503),
        "stream_truncated":("protocol_error",503),
        "manager_connection_failed":("manager_unavailable",503),
    }.get(reason,("upstream_failed",503))
    if getattr(error,"status",None)==413:
        code,status="request_too_large",413
    # Only explicit Manager rejection before its stream begins proves that
    # inference did not start. Transport/EOF/cancel acknowledgement do not.
    definitive = not seen_meta and (reason in {"instance_identity_mismatch","slot_chat_in_progress",
                   "slot_busy_or_unknown","stream_in_progress","model_not_running","unknown_slot",
                   "slot_not_authorized","stream_not_authorized","thinking_not_supported",
                   "requested_output_exceeds_engine_limit","invalid_messages","invalid_model_id",
                   "invalid_generation_options","colibri_request_rejected"}
                   or getattr(error,"status",None) in (401,403,413))
    return BridgeError(code,status,request_id=rid,upstream_code=reason), "FAILED" if definitive else "UNKNOWN"


class ClientBridge:
    def __init__(self, folder, *, snapshot=_manager_snapshot, stream=stream_chat, cancel=cancel_chat,
                 profiles=None):
        self.folder = Path(folder)
        identity_path = private_path(self.folder / IDENTITY_NAME)
        if not identity_path.exists():
            _private_create(identity_path, canonical({"bridge_id":uuid.uuid4().hex,
                     "principal_id":uuid.uuid4().hex,"permissions":["read","chat"]}))
        identity = json.loads(_private_read(identity_path),object_pairs_hook=no_duplicates)
        if (type(identity) is not dict or set(identity)!={"bridge_id","principal_id","permissions"}
                or not all(type(identity[k]) is str and RID.fullmatch(identity[k]) for k in ("bridge_id","principal_id"))
                or type(identity["permissions"]) is not list or not all(x in ("read","chat") for x in identity["permissions"])
                or len(set(identity["permissions"]))!=len(identity["permissions"])):
            raise PermissionError("invalid bridge identity")
        self.bridge_id,self.principal,self.permissions = identity["bridge_id"],identity["principal_id"],tuple(identity["permissions"])
        self.token_path = private_path(self.folder/TOKEN_NAME)
        if not self.token_path.exists():
            _private_create(self.token_path,secrets.token_urlsafe(48).encode("ascii"))
        self._token()
        self.launch_id = uuid.uuid4().hex
        self.journal = Journal(self.folder)
        self._snapshot,self._stream,self._cancel = snapshot,stream,cancel
        self._profiles = profiles if profiles is not None else self._load_profiles
        self.lock = threading.RLock()
        self.catalog_lock = threading.Lock()
        self.active,self.targets,self.routes,self.manager_state = {},{},{},{}
        self.revision = self._revision()
        self.discovery_path = self.folder/DISCOVERY_NAME

    def _load_profiles(self):
        path = self.folder/"managers.json"
        return load_profiles(path) if path.is_file() else []

    def _token(self):
        token = _private_read(self.token_path).decode("ascii").strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]{43,128}",token):
            raise PermissionError("invalid bridge token")
        return token

    def publish(self, port):
        _private_replace(self.discovery_path,canonical({"bridge_id":self.bridge_id,
            "protocol_version":VERSION,"origin":"http://127.0.0.1:"+str(port),
            "credential_ref":TOKEN_NAME,"launch_identity":self.launch_id}))

    def unpublish(self):
        try:
            if json.loads(_private_read(self.discovery_path)).get("launch_identity")==self.launch_id:
                self.discovery_path.unlink()
        except (OSError,ValueError,AttributeError):
            pass

    def authorize(self, headers, permission):
        # No browser access, no CSRF fallback, no bearer in URL.
        if headers.get("Origin") or headers.get("Sec-Fetch-Site"):
            raise BridgeError("forbidden",403)
        values=headers.get_all("Authorization",[]) if hasattr(headers,"get_all") else [headers.get("Authorization","")]
        value=values[0] if len(values)==1 else ""
        try:
            valid=type(value) is str and value.isascii() and secrets.compare_digest(value,"Bearer "+self._token())
        except (OSError,ValueError,UnicodeError):
            raise BridgeError("internal_error",503) from None
        if not valid:
            raise BridgeError("unauthorized",401)
        if permission not in self.permissions:
            raise BridgeError("forbidden",403)

    def _revision(self):
        return hashlib.sha256(canonical([self.targets[k] for k in sorted(self.targets)])).hexdigest()

    def health(self):
        with self.catalog_lock:
            return {"bridge_id":self.bridge_id,"protocol_version":VERSION,
                    "status":"READY" if all(x=="online" for x in self.manager_state.values()) else "DEGRADED",
                    "catalog_revision":self.revision,"permissions":list(self.permissions),
                    "capabilities":dict(UNSUPPORTED)}

    def refresh(self, selected=None):
        # Snapshot network I/O outside journal/cancel lock.
        with self.catalog_lock:
            try:
                profiles = self._profiles()
            except (OSError,ValueError,KeyError):
                raise BridgeError("manager_unavailable",503) from None
            valid = {p["manager_id"]:p for p in profiles}
            def query(profile):
                try:
                    data = self._snapshot(profile)
                    return profile,"online",targets_from_snapshot(self.bridge_id,profile,data)
                except ChatClientError as e:
                    return profile,"denied" if e.status in (401,403) else "offline",[]
                except (OSError,ValueError,KeyError,TypeError,AttributeError):
                    return profile,"offline",[]
            todo = list(valid.values()) if selected is None else [valid[selected]] if selected in valid else []
            if todo:
                with ThreadPoolExecutor(max_workers=min(8,len(todo))) as pool:
                    results = list(pool.map(query,todo))
            else:
                results=[]
            for mid in list(self.manager_state):
                if mid not in valid:
                    del self.manager_state[mid]
            for tid,t in list(self.targets.items()):
                if t["manager_id"] not in valid:
                    self.targets.pop(tid);self.routes.pop(tid,None)
            for profile,state,rows in results:
                mid=profile["manager_id"]
                previous=[t for t in self.targets.values() if t["manager_id"]==mid]
                for t in previous:
                    self.targets.pop(t["target_id"],None);self.routes.pop(t["target_id"],None)
                self.manager_state[mid]=state
                if state=="offline":
                    # Keep previously visible stable targets, but not stale readiness or credentials.
                    rows=[{**t,"status":"UNAVAILABLE","instance_id":None,"allowed_operations":[]} for t in previous]
                for t in rows:
                    if "chat" not in self.permissions:
                        t={**t,"allowed_operations":[]}
                    self.targets[t["target_id"]]=t
                    if state=="online":
                        self.routes[t["target_id"]]=profile
            self.revision=self._revision()
            return {"bridge_id":self.bridge_id,"protocol_version":VERSION,
                    "catalog_revision":self.revision,"targets":[copy.deepcopy(self.targets[k]) for k in sorted(self.targets)]}

    def _resolve(self, req):
        rid,tid=req["request_id"],req["target_id"]
        with self.catalog_lock:
            old=self.targets.get(tid)
            selected=old["manager_id"] if old else None
        self.refresh(selected)
        with self.catalog_lock:
            t=self.targets.get(tid)
            if t is None:
                raise BridgeError("unknown_target",404,request_id=rid)
            t=copy.deepcopy(t);profile=self.routes.get(tid);revision=self.revision
        if t["status"]=="UNAVAILABLE":
            raise BridgeError("manager_unavailable",503,request_id=rid)
        if t["instance_id"]!=req["instance_id"]:
            raise BridgeError("stale_instance",409,request_id=rid)
        if t["status"]=="BUSY":
            raise BridgeError("slot_busy",409,request_id=rid)
        if t["status"]!="READY" or "chat" not in t["allowed_operations"] or profile is None:
            raise BridgeError("target_not_ready",409,request_id=rid)
        return t,profile,revision

    @staticmethod
    def _admit(req,t):
        rid=req["request_id"];opts=req.get("options",{});caps=t["capabilities"];lim=t["limits"]
        for key in ("thinking","reasoning_effort","max_output_tokens"):
            if key in opts and opts[key]!="auto" and caps[key]!="supported":
                raise BridgeError("unsupported_capability",422,request_id=rid)
        if any(m.get("reasoning_content") for m in req["messages"]) and caps["assistant_reasoning_input"]!="supported":
            raise BridgeError("unsupported_capability",422,request_id=rid)
        if "max_output_tokens" in opts and lim["max_output_tokens"] is not None and opts["max_output_tokens"]>lim["max_output_tokens"]:
            raise BridgeError("output_limit",422,request_id=rid)
        messages=req["messages"]
        size=len(json.dumps({"slot_id":t["slot_id"],"model_id":t["model_id"],"instance_id":t["instance_id"],
                        "request_id":"0"*32,"messages":messages,**({"options":opts} if "options" in req else {})},ensure_ascii=False).encode("utf-8"))
        def over(key,value):
            return lim[key] is not None and value>lim[key]
        if (over("request_bytes",size) or over("history_messages",len(messages))
                or over("history_chars",sum(len(m["content"])+len(m.get("reasoning_content","")) for m in messages))
                or any(over("message_chars",len(m["content"])) or over("response_chars",len(m.get("reasoning_content",""))) for m in messages)):
            raise BridgeError("request_too_large",413,request_id=rid)

    def start(self, value):
        started=time.perf_counter()
        req=validate_request(value);rid=req["request_id"]
        self.journal.check_duplicate(self.principal,req)
        t,profile,rev=self._resolve(req)
        self._admit(req,t)
        with self.lock:
            self.journal.check_duplicate(self.principal,req)
            if any((a["target"]["manager_id"],a["target"]["slot_id"])==(t["manager_id"],t["slot_id"]) for a in self.active.values()):
                raise BridgeError("slot_busy",409,request_id=rid)
            mid=self.journal.claim(self.principal,req)
            active={"target":t,"profile":profile,"manager_rid":mid,"sequence":None,"dispatched":False}
            self.active[rid]=active
        return self._events(req,active,rev,started)

    def status(self,rid):
        if type(rid) is not str or not RID.fullmatch(rid):
            raise BridgeError("invalid_request",400)
        with self.lock:
            row=self.journal.get(self.principal,rid)
            result=Journal.public(row)
            a=self.active.get(rid)
            if a is not None and a["sequence"] is not None and row["state"] in ACTIVE:
                result["last_sequence"]=a["sequence"]
            return result

    def _forward_cancel(self,a):
        try:
            return self._cancel(a["profile"],a["target"]["slot_id"],a["manager_rid"]) is True
        except (ChatClientError,OSError,ValueError):
            return False

    def cancel(self,value):
        req=validate_request(value,cancel=True);rid=req["request_id"]
        with self.lock:
            row=self.journal.get(self.principal,rid)
            if (row["target_id"],row["instance_id"])!=(req["target_id"],req["instance_id"]):
                raise BridgeError("stale_instance",409,request_id=rid)
            row=self.journal.mark_cancel(self.principal,rid)
            a=self.active.get(rid)
            dispatch=a is not None and a["dispatched"] and row["state"]=="CANCEL_REQUESTED"
            if a is not None and not a["dispatched"] and row["state"]=="CANCEL_REQUESTED":
                row=self.journal.change(self.principal,rid,"CANCELLED",result_usage=usage())
        if dispatch:
            self._forward_cancel(a)
        with self.lock:
            row=self.journal.get(self.principal,rid)
            return {**{k:row[k] for k in ("request_id","target_id","instance_id","state")},
                    "cancel_accepted":bool(row["cancel_intent"]),"stop_confirmed":row["state"]=="CANCELLED"}

    def _events(self, req, a, revision, start):
        rid=req["request_id"];t=a["target"];up=None;seq=-1;seen_meta=False
        first_ms=None;manager_first_ms=None;engine_first_ms=None;observed_terminal=None
        def packet(kind,**fields):
            nonlocal seq
            seq+=1
            with self.lock:
                a["sequence"]=seq
            return {"type":kind,"request_id":rid,"sequence":seq,**fields}
        def meta(source=None):
            source=source or {}
            return packet("meta",**{k:t[k] for k in ("bridge_id","target_id","instance_id","manager_id","slot_id","model_id","capabilities","launch_configuration")},
                          protocol_version=VERSION,catalog_revision=revision,
                          execution_mode=source.get("execution_mode").upper() if source.get("execution_mode") in ("cpu","cuda","CPU","CUDA") else t["execution_mode"],
                          limits=_limits(source.get("transport_policy"),source.get("engine_limits"),context=t["limits"]["context_tokens"]) if source else t["limits"])
        def persist_terminal(state,finish_reason=None,out_usage=None,error=None,sequence=None,telemetry=None):
            out_usage=out_usage or usage()
            with self.lock:
                row=self.journal.change(self.principal,rid,state,error=error,result_usage=out_usage,
                    finish=finish_reason,sequence=sequence,telemetry=telemetry)
                # A proven pre-dispatch cancel may have committed already.
                if row["state"] != state:
                    raise BridgeError("internal_error",500,request_id=rid)
                if sequence is not None and (row["last_sequence"] is None or row["last_sequence"]<sequence):
                    self.journal.sequence(self.principal,rid,sequence)
        def finish(state,finish_reason=None,out_usage=None,error=None):
            out_usage=out_usage or usage()
            persist_terminal(state,finish_reason,out_usage,error,seq+1)
            return packet("done",state=state,finish_reason=finish_reason,usage=out_usage,error=error)
        try:
            with self.lock:
                row=self.journal.get(self.principal,rid)
                before=row["state"]=="CANCELLED" or row["state"]=="CANCEL_REQUESTED"
                if not before:
                    self.journal.change(self.principal,rid,"RUNNING")
                    a["dispatched"]=True
            if before:
                seen_meta=True
                yield meta()
                yield finish("CANCELLED")
                return
            up=self._stream(a["profile"],t["slot_id"],t["model_id"],req["messages"],
                         request_id=a["manager_rid"],instance_id=t["instance_id"],
                         options=req.get("options"))
            try:
                source=next(up)
            except StopIteration:
                raise ChatClientError("stream_truncated",502) from None
            if (source.get("type")!="meta" or any(source.get(k)!=t[k] for k in ("manager_id","slot_id","model_id","instance_id"))):
                raise ChatClientError("stream_identity_mismatch",502)
            seen_meta=True
            yield meta(source)
            with self.lock:
                state=self.journal.get(self.principal,rid)["state"]
            if state=="CANCEL_REQUESTED":
                self._forward_cancel(a)  # initial cancel may precede upstream registration
            yield packet("status",state=state)
            for event in up:
                typ=event.get("type")
                if typ in ("delta","reasoning"):
                    value=event.get("text")
                    if type(value) is not str or not value:
                        raise ChatClientError("invalid_stream_event",502)
                    if first_ms is None:
                        first_ms=(time.perf_counter()-start)*1000
                        timing=event.get("timing") or {}
                        engine_first_ms=_ms(timing.get("first_fragment_ms"))
                        rcv=_ms(timing.get("manager_received_unix_ms"));fwd=_ms(timing.get("manager_first_forward_unix_ms"))
                        if rcv is not None and fwd is not None:
                            manager_first_ms=_ms(fwd-rcv)  # same Manager clock, never cross-host subtraction
                    yield packet(typ,text=value)
                elif typ=="done":
                    u=usage(event.get("usage"))
                    reason=event.get("finish_reason")
                    reason=reason[:64] if isinstance(reason,str) and reason else None
                    # Manager DONE is authoritative even if the WUA socket
                    # disconnects while we emit the remaining packets.
                    timing=event.get("timing") or {}
                    telemetry={
                        "engine_ttft_ms":_ms(timing.get("first_fragment_ms")) if timing.get("first_fragment_ms") is not None else engine_first_ms,
                        "manager_ttft_ms":manager_first_ms,"bridge_ttft_ms":_ms(first_ms),
                        "engine_elapsed_ms":_ms(timing.get("total_ms")),
                        "bridge_elapsed_ms":(time.perf_counter()-start)*1000,
                        "engine_decode_tokens_per_second":None}
                    persist_terminal("SUCCEEDED",reason,u,sequence=seq,telemetry=telemetry)
                    observed_terminal="SUCCEEDED"
                    yield packet("usage",usage=u)
                    yield packet("telemetry",telemetry=telemetry)
                    yield finish("SUCCEEDED",reason,u)
                    return
                else:
                    raise ChatClientError("invalid_stream_event",502)
            raise ChatClientError("stream_truncated",502)
        except (ChatClientError,StopIteration) as exc:
            err,state=_error_from_manager(exc,rid,seen_meta=seen_meta)
            if not seen_meta:
                persist_terminal(state,error=err.data)
                observed_terminal=state
                raise err from None
            persist_terminal(state,error=err.data,sequence=seq)
            observed_terminal=state
            yield packet("error",error=err.data)
            yield finish(state,error=err.data)
        except GeneratorExit:
            raise
        finally:
            if up is not None:
                try:
                    up.close()
                except (OSError,ValueError):
                    pass
            with self.lock:
                row=self.journal.get(self.principal,rid)
                uncertain=row["state"] in ACTIVE
            if (uncertain or observed_terminal=="UNKNOWN") and a["dispatched"]:
                self._forward_cancel(a)
            if uncertain:
                with self.lock:
                    self.journal.change(self.principal,rid,"UNKNOWN",
                        error=BridgeError("upstream_failed",503,request_id=rid).data,
                        result_usage=usage(),sequence=seq if seq>=0 else None)
            with self.lock:
                if seq>=0:
                    self.journal.sequence(self.principal,rid,seq)
                self.active.pop(rid,None)


def dispatch(handler,bridge,port):
    """Handle only /bridge/v1 routes, not GUI session/CSRF or history."""
    path=handler.path
    def reject(err):
        if handler.command=="POST":
            return handler._reject_post(err.status,err.data)
        return handler._send_json(err.status,err.data)
    if (handler.headers.get("Host")!="127.0.0.1:"+str(port) or handler.client_address[0]!="127.0.0.1"):
        return reject(BridgeError("forbidden",403))
    if bridge is None:
        return reject(BridgeError("manager_unavailable",503))
    try:
        if handler.command=="GET":
            permission="read" if path in ("/bridge/v1/health","/bridge/v1/models") else "chat"
            bridge.authorize(handler.headers,permission)
            if path=="/bridge/v1/health":
                return handler._send_json(200,bridge.health())
            if path=="/bridge/v1/models":
                return handler._send_json(200,bridge.refresh())
            prefix="/bridge/v1/requests/"
            if path.startswith(prefix):
                return handler._send_json(200,bridge.status(path[len(prefix):]))
            raise BridgeError("unknown_request",404)
        bridge.authorize(handler.headers,"chat")
        if path not in ("/bridge/v1/chat/stream","/bridge/v1/chat/cancel"):
            raise BridgeError("unknown_request",404)
        lengths=handler.headers.get_all("Content-Length",[])
        if (handler.headers.get("Transfer-Encoding") or len(lengths)!=1
                or not re.fullmatch(r"[0-9]{1,10}",lengths[0])
                or handler.headers.get("Content-Type","").split(";")[0].strip()!="application/json"):
            raise BridgeError("invalid_request",400)
        n=int(lengths[0])
        if not 0<n<=MAX_BRIDGE_BODY:
            raise BridgeError("request_too_large",413)
        previous=handler.connection.gettimeout()
        try:
            handler.connection.settimeout(10)
            raw=handler.rfile.read(n)
        finally:
            handler.connection.settimeout(previous)
        if len(raw)!=n:
            raise BridgeError("invalid_request",400)
        try:
            value=json.loads(raw.decode("utf-8"),object_pairs_hook=no_duplicates,
                             parse_constant=lambda v: (_ for _ in ()).throw(ValueError("invalid constant")))
        except (ValueError,UnicodeError,RecursionError):
            raise BridgeError("invalid_request",400) from None
        if path=="/bridge/v1/chat/cancel":
            return handler._send_json(200,bridge.cancel(value))
        events=bridge.start(value)
        try:
            first=next(events)
            import socket
            handler.close_connection=True
            def emit(event):
                data=canonical(event)
                handler.wfile.write(("event: "+event["type"]+"\nid: "+str(event["sequence"])+"\ndata: ").encode("ascii")+data+b"\n\n")
                handler.wfile.flush()
            try:
                handler.connection.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
                handler._headers(200,"text/event-stream; charset=utf-8",None)
                emit(first)
                for event in events:
                    emit(event)
            except (OSError,TimeoutError,sqlite3.Error,BridgeError,ValueError):
                # Once 200 sent, only valid SSE or EOF; never append HTTP JSON.
                pass
        finally:
            events.close()
    except BridgeError as err:
        return reject(err)
    except (sqlite3.Error,OSError,ValueError,PermissionError):
        return reject(BridgeError("internal_error",503))
