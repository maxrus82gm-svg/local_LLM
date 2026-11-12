"""Durable slot definitions/selections in the existing control journal.

Ports are assigned by the server under the same admission transaction. A slot
does not bind a port or launch a model. Creating a slot grants its creator use
of that slot, without granting control_models or changing pairing/TLS settings.
"""
import json
import re
import time
import uuid


class SlotRegistry:
    def __init__(self,config):
        self.config=config

    def initialize(self,db):
        db.execute("CREATE TABLE IF NOT EXISTS registry_meta (name TEXT PRIMARY KEY,value TEXT NOT NULL)")
        namespace={"manager_id":self.config["manager_id"],
            "host":self.config.get("control",{}).get("host",""),
            "instance_root":self.config.get("control",{}).get("instance_root","")}
        for name,value in namespace.items():
            old=db.execute("SELECT value FROM registry_meta WHERE name=?",(name,)).fetchone()
            if old and old[0]!=value:raise ValueError("Control journal belongs to another Manager namespace")
            db.execute("INSERT OR IGNORE INTO registry_meta VALUES(?,?)",(name,value))
        db.execute("CREATE TABLE IF NOT EXISTS slots (slot_id TEXT PRIMARY KEY, port INTEGER UNIQUE NOT NULL, protected INTEGER NOT NULL, owner TEXT, model_key TEXT, mode TEXT NOT NULL DEFAULT 'cpu', revision INTEGER NOT NULL DEFAULT 0)")
        db.execute("CREATE TABLE IF NOT EXISTS slot_requests (owner TEXT,id TEXT,fingerprint TEXT NOT NULL,response TEXT NOT NULL,PRIMARY KEY(owner,id))")
        db.execute("CREATE TABLE IF NOT EXISTS risk_checks (token TEXT PRIMARY KEY,owner TEXT NOT NULL,slot TEXT NOT NULL,model TEXT NOT NULL,mode TEXT NOT NULL,free_gib REAL NOT NULL,expires REAL NOT NULL,policy TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS model_checks (model TEXT,mode TEXT,review TEXT NOT NULL,checked REAL NOT NULL,PRIMARY KEY(model,mode))")
        for slot in self.config["slots"]:
            protected=bool(slot.get("protected") or slot["slot_id"]=="slot1" or slot["api_port"]==8000)
            row=db.execute("SELECT port,protected FROM slots WHERE slot_id=?",(slot["slot_id"],)).fetchone()
            if row and row!=(slot["api_port"],int(protected)):
                raise ValueError("Configured slot conflicts with durable registry")
            db.execute("INSERT OR IGNORE INTO slots(slot_id,port,protected) VALUES(?,?,?)",(slot["slot_id"],slot["api_port"],int(protected)))

    def definitions(self,db):
        return [{"slot_id":r[0],"api_port":r[1],"protected":bool(r[2]),"creator":r[3],
                 "model_key":r[4],"mode":r[5],"revision":r[6]}
                for r in db.execute("SELECT * FROM slots ORDER BY rowid")]

    def principal(self,db,principal):
        created=[r[0] for r in db.execute("SELECT slot_id FROM slots WHERE owner=?",(principal["client_id"],))]
        return {**principal,"allowed_slots":list(dict.fromkeys([*principal["allowed_slots"],*created]))}

    def action(self,db,principal,payload,telemetry,rows):
        owner=principal["client_id"]
        fingerprint=json.dumps(payload,sort_keys=True)
        previous=db.execute("SELECT fingerprint,response FROM slot_requests WHERE owner=? AND id=?",(owner,payload["request_id"])).fetchone()
        if previous:
            if previous[0]!=fingerprint:raise ValueError("request_id_conflict")
            return json.loads(previous[1])
        slots=self.definitions(db)
        if payload["op"]=="add_slot":
            low,high=self.config.get("control",{}).get("slot_port_range",[8001,8999])
            if type(low) is not int or type(high) is not int or not 1024<=low<=high<=65535:
                raise ValueError("invalid_slot_port_range")
            occupied={s["api_port"] for s in slots}|set(telemetry["ports"])|{self.config.get("listen_port"),8000,8443}
            port=next((p for p in range(low,high+1) if p not in occupied),None)
            if port is None:raise ValueError("no_free_slot_port")
            number=4
            while any(s["slot_id"]==f"slot{number}" for s in slots):number+=1
            identity=f"slot{number}"
            db.execute("INSERT INTO slots(slot_id,port,protected,owner) VALUES(?,?,0,?)",(identity,port,owner))
            result={"state":"SLOT_CREATED","slot_id":identity,"api_port":port,"creator_grant":True,"revision":0}
        else:
            slot=next((s for s in slots if s["slot_id"]==payload["slot_id"]),None)
            if slot is None or slot["slot_id"] not in principal["allowed_slots"]:raise PermissionError("slot_not_authorized")
            if slot["protected"]:raise PermissionError("legacy_slot_protected")
            if any(r["slot_id"]==slot["slot_id"] and not r["released"] for r in rows):raise ValueError("slot_in_use")
            expected=payload.get("expected_revision",slot["revision"])
            if type(expected) is not int or expected!=slot["revision"]:raise ValueError("slot_selection_changed")
            db.execute("UPDATE slots SET model_key=?,mode=?,revision=revision+1 WHERE slot_id=?",
                       (payload["model_key"],payload["mode"],slot["slot_id"]))
            result={"state":"SLOT_SELECTED","slot_id":slot["slot_id"],"model_key":payload["model_key"],
                    "mode":payload["mode"],"revision":slot["revision"]+1}
        db.execute("INSERT INTO slot_requests VALUES(?,?,?,?)",(owner,payload["request_id"],fingerprint,json.dumps(result)))
        return result

    def risk_token(self,db,principal,slot,key,mode,assessment):
        token=uuid.uuid4().hex
        db.execute("DELETE FROM risk_checks WHERE expires<?",(time.time(),))
        db.execute("INSERT INTO risk_checks VALUES(?,?,?,?,?,?,?,?)",(token,principal["client_id"],slot,key,mode,
            assessment["forecast"]["ram_free_gib"],time.time()+60,json.dumps({"policy":assessment["policy"],"forecast":assessment["forecast"]},sort_keys=True)))
        return token

    def confirm_risk(self,db,principal,payload,slot,assessment):
        if not assessment["requires_ack"]:return
        if not assessment["risk_ack_allowed"]:raise PermissionError("resource_risk_not_permitted")
        if payload.get("risk_ack") is not True:raise ValueError("risk_ack_required")
        token=payload.get("risk_token")
        if type(token) is not str or not re.fullmatch(r"[a-f0-9]{32}",token):raise ValueError("risk_ack_required")
        row=db.execute("SELECT owner,slot,model,mode,free_gib,expires,policy FROM risk_checks WHERE token=?",(token,)).fetchone()
        if (not row or row[:4]!=(principal["client_id"],slot,payload["model_key"],payload["mode"])
                or row[5]<time.time() or assessment["forecast"]["ram_free_gib"]<row[4]-1):
            raise ValueError("risk_confirmation_stale")
        stored=json.loads(row[6]);old=stored["policy"];new=assessment["policy"]
        if any(old[k]!=new[k] for k in ("ram_gib","vram_gib","job_limit_gib","ram_warning_gib")):
            raise ValueError("risk_confirmation_stale")
        if any(assessment["forecast"][k]>stored["forecast"][k] for k in ("ram_reserved_gib","vram_reserved_gib")):
            raise ValueError("risk_confirmation_stale")
        db.execute("DELETE FROM risk_checks WHERE token=?",(token,))
