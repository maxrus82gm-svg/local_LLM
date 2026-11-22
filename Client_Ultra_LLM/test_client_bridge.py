"""Offline Client Bridge v1 checks. No real Manager, engine or production profile."""
from copy import deepcopy
from contextlib import closing
from http.server import ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid

from bridge_core import BridgeError, Journal, digest, target_id, usage
from bridge_runtime import ClientBridge, DISCOVERY_NAME, TOKEN_NAME, targets_from_snapshot
from chat_client import ChatClientError
import web_client

PROFILES=[{"manager_id":"m1","client_id":"c1","display_name":"Manager 1"},
          {"manager_id":"m2","client_id":"c2","display_name":"Manager 2"}]
INSTANCE="a"*32
MODEL="kat"
POLICY={"request_bytes":1048576,"history_messages":128,"history_chars":240000,
        "message_chars":131072,"response_chars":1048576,"stream_bytes":8388608,"timeout_seconds":300}
USER=[{"role":"user","content":"private prompt unique"}]


def snapshot(profile, *, identity=INSTANCE, ready="ready_unreserved", key="kat-key", model=MODEL):
    return {"schema":"ultra.manager.live.v1","source":"LIVE_HOST","manager_id":profile["manager_id"],
            "viewer_id":profile["client_id"],"admission_enabled":False,"reservation_granted":False,"memory":{},
            "slots":[{"slot_id":"slot1","instance_id":identity,"engine_state":"ready",
                      "availability":ready,"models":[model],"context_tokens":65536}],
            "chat":{"streaming":True,"reasoning_events":True,"transport_policy":POLICY},
            "control":{"manager_id":profile["manager_id"],
                       "slots":[{"slot_id":"slot1","authorized":True,"model_key":key}],
                       "models":[{"key":key,"name":"KAT","api_ids":[model]}],
                       "instances":[{"slot_id":"slot1","instance_id":identity,"model_key":key,
                                    "model_id":model,"mode":"cuda","released":False,"state":"READY"}]}}


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        if not self.folder.is_dir():
            raise RuntimeError("temp missing")
        self.calls=[];self.cancel_calls=[];self.snapshots={p["manager_id"]:snapshot(p) for p in PROFILES}
        self.bridge=ClientBridge(self.folder,snapshot=lambda p:deepcopy(self.snapshots[p["manager_id"]]),
                                  stream=self.fake_stream,cancel=self.fake_cancel,profiles=lambda:PROFILES)
        self.cat=self.bridge.refresh()
        self.t=next(t for t in self.cat["targets"] if t["manager_id"]=="m1")

    def fake_stream(self, profile, slot, model, messages, **kw):
        self.calls.append((deepcopy(messages),kw,profile["manager_id"]))
        yield {"type":"meta","manager_id":profile["manager_id"],"slot_id":slot,"model_id":model,
               "instance_id":kw["instance_id"],"execution_mode":"cuda","transport_policy":POLICY,
               "engine_limits":{"context_tokens":65536}}
        yield {"type":"reasoning","text":"private reasoning"}
        yield {"type":"delta","text":"private answer","timing":{}}
        yield {"type":"done","usage":{"prompt_tokens":17,"completion_tokens":23},"finish_reason":"stop"}

    def fake_cancel(self, profile, slot, request):
        self.cancel_calls.append((profile["manager_id"],slot,request))
        return True

    def request(self, **kw):
        return {"request_id":uuid.uuid4().hex,"target_id":self.t["target_id"],
                "instance_id":self.t["instance_id"],"messages":deepcopy(USER),**kw}

    def error(self, code, callable, *args):
        with self.assertRaises(BridgeError) as cm:
            callable(*args)
        self.assertEqual(cm.exception.code,code)
        return cm.exception

    def test_catalog_identity_stable_on_restart_and_distinct_across_managers(self):
        self.assertEqual(len(self.cat["targets"]),2)
        self.assertEqual(len({x["target_id"] for x in self.cat["targets"]}),2)
        expect=target_id(self.bridge.bridge_id,"m1","slot1","kat-key")
        self.assertEqual(self.t["target_id"],expect)
        self.snapshots["m1"]=snapshot(PROFILES[0],identity="b"*32)
        found=next(x for x in self.bridge.refresh()["targets"] if x["target_id"]==expect)
        self.assertEqual(found["instance_id"],"b"*32)
        self.error("stale_instance",self.bridge.start,self.request())
        self.assertEqual(self.calls,[])

    def test_busy_and_unknown_mapping_not_selectable(self):
        self.snapshots["m1"]=snapshot(PROFILES[0],ready="busy")
        a=next(t for t in self.bridge.refresh()["targets"] if t["manager_id"]=="m1")
        self.assertEqual((a["status"],a["allowed_operations"]),("BUSY",[]))
        self.error("slot_busy",self.bridge.start,self.request())
        data=snapshot(PROFILES[0],identity="legacy-"+"b"*32)
        data["control"]["instances"]=[]
        data["control"]["models"]=[]
        self.assertEqual(targets_from_snapshot(self.bridge.bridge_id,PROFILES[0],data),[])

    def test_unknown_capability_and_system_role_denied_without_dispatch(self):
        self.error("unsupported_capability",self.bridge.start,self.request(options={"thinking":"on"}))
        self.error("unsupported_capability",self.bridge.start,self.request(messages=[{"role":"system","content":"test"},*USER]))
        self.error("unsupported_capability",self.bridge.start,self.request(messages=[{"role":"assistant","content":"old","reasoning_content":"hidden"},*USER]))
        self.assertEqual(self.calls,[])

    def test_stateless_success_and_usage_and_no_full_history(self):
        r=self.request(conversation_id="chat",turn_id="turn",messages=[{"role":"user","content":"old"},
            {"role":"assistant","content":"cloud"},*USER])
        es=list(self.bridge.start(r))
        self.assertEqual([x["type"] for x in es],["meta","status","reasoning","delta","usage","telemetry","done"])
        self.assertEqual([x["sequence"] for x in es],list(range(len(es))))
        self.assertTrue(all(x["request_id"]==r["request_id"] for x in es))
        self.assertEqual(self.calls[0][0],r["messages"])
        self.assertNotEqual(self.calls[0][1]["request_id"],r["request_id"])
        u=es[-1]["usage"]
        self.assertEqual((u["status"],u["source"],u["total_tokens"],u["prompt_basis"]),("partial","provider_and_derived_total",40,"unknown"))
        self.assertIsNone(u["cached_prompt_tokens"])
        st=self.bridge.status(r["request_id"])
        self.assertEqual((st["state"],st["last_sequence"]),("SUCCEEDED",es[-1]["sequence"]))
        self.assertFalse((self.folder/"chat_history.sqlite3").exists())
        with closing(sqlite3.connect(self.bridge.journal.path)) as db:
            data=str(list(db.execute("SELECT * FROM attempts")))
        for text in ("private prompt unique","private reasoning","private answer"):
            self.assertNotIn(text,data)

    def test_duplicates_checked_before_stale_instance_and_tombstone(self):
        r=self.request();list(self.bridge.start(r))
        self.snapshots["m1"]=snapshot(PROFILES[0],identity="b"*32)
        self.error("request_already_attempted",self.bridge.start,{**r,"catalog_revision":"changed"})
        self.error("request_conflict",self.bridge.start,{**r,"messages":[{"role":"user","content":"different"}]})
        self.bridge.journal.prune_details(self.bridge.principal,r["request_id"])
        self.assertFalse(self.bridge.status(r["request_id"])["details_retained"])
        self.error("request_already_attempted",self.bridge.start,r)
        self.assertEqual(len(self.calls),1)

    def test_concurrent_duplicate_atomic_claim(self):
        r=self.request()
        def claim():
            try:
                return self.bridge.journal.claim(self.bridge.principal,r)
            except BridgeError as e:
                return e.code
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:claim(),range(2)))
        self.assertEqual(results.count("request_already_attempted"),1)

    def test_cancel_before_dispatch_proven(self):
        r=self.request();g=self.bridge.start(r)
        cancel={k:r[k] for k in ("request_id","target_id","instance_id")}
        ack=self.bridge.cancel(cancel)
        self.assertEqual((ack["state"],ack["stop_confirmed"],ack["cancel_accepted"]),("CANCELLED",True,True))
        es=list(g)
        self.assertEqual(es[-1]["state"],"CANCELLED")
        self.assertEqual(self.calls,[])
        self.assertEqual(self.cancel_calls,[])

    def test_cancel_ack_not_stop_confirmation_completion_can_win(self):
        r=self.request();g=self.bridge.start(r);next(g)
        ack=self.bridge.cancel({k:r[k] for k in ("request_id","target_id","instance_id")})
        self.assertEqual((ack["state"],ack["cancel_accepted"],ack["stop_confirmed"]),("CANCEL_REQUESTED",True,False))
        self.assertEqual(self.cancel_calls[0][2],self.calls[0][1]["request_id"])
        self.assertEqual(list(g)[-1]["state"],"SUCCEEDED")
        repeated=self.bridge.cancel({k:r[k] for k in ("request_id","target_id","instance_id")})
        self.assertEqual((repeated["state"],repeated["stop_confirmed"]),("SUCCEEDED",False))

    def test_cancel_manager_error_conservatively_unknown(self):
        original=self.fake_stream
        def interrupted(*args,**kw):
            it=original(*args,**kw);yield next(it)
            raise ChatClientError("stream_cancelled",409)
        self.bridge._stream=interrupted
        r=self.request();g=self.bridge.start(r);next(g)
        self.bridge.cancel({k:r[k] for k in ("request_id","target_id","instance_id")})
        es=list(g)
        self.assertEqual(es[-1]["state"],"UNKNOWN")
        self.assertEqual(es[-1]["error"]["code"],"cancel_not_confirmed")

    def test_disconnect_before_done_unknown_and_no_retry(self):
        r=self.request();g=self.bridge.start(r);next(g);next(g);next(g);g.close()
        self.assertEqual(self.bridge.status(r["request_id"])["state"],"UNKNOWN")
        self.error("request_already_attempted",self.bridge.start,r)
        self.assertTrue(self.cancel_calls)

    def test_disconnect_after_authoritative_done_still_success(self):
        r=self.request();g=self.bridge.start(r)
        while next(g)["type"]!="usage":
            pass
        g.close()
        self.assertEqual(self.bridge.status(r["request_id"])["state"],"SUCCEEDED")
        self.assertEqual(self.cancel_calls,[])

    def test_recovery_unresolved_is_unknown_and_other_principal_cannot_read(self):
        r=self.request();self.bridge.journal.claim(self.bridge.principal,r)
        recovered=Journal(self.folder)
        self.assertEqual(recovered.get(self.bridge.principal,r["request_id"])["state"],"UNKNOWN")
        self.error("unknown_request",recovered.get,"another",r["request_id"])
        self.error("request_already_attempted",recovered.claim,self.bridge.principal,r)

    def test_confirmed_manager_admission_failure_is_not_success(self):
        def reject(*a,**k):
            raise ChatClientError("slot_chat_in_progress",409)
            yield
        self.bridge._stream=reject
        r=self.request()
        self.error("slot_busy",next,self.bridge.start(r))
        self.assertEqual(self.bridge.status(r["request_id"])["state"],"FAILED")

    def test_same_slot_parallel_block_and_other_manager_independent(self):
        r=self.request();g=self.bridge.start(r);next(g)
        self.error("slot_busy",self.bridge.start,self.request())
        t=next(t for t in self.cat["targets"] if t["manager_id"]=="m2")
        es=list(self.bridge.start(self.request(target_id=t["target_id"],instance_id=t["instance_id"])))
        self.assertEqual(es[-1]["state"],"SUCCEEDED")
        g.close()

    def test_usage_zero_vs_unknown(self):
        self.assertIsNone(usage()["prompt_tokens"])
        self.assertEqual(usage({"prompt_tokens":0})["prompt_tokens"],0)
        self.assertEqual(usage({"prompt_tokens":1,"completion_tokens":2,"total_tokens":3})["status"],"reported")

    def test_discovery_persistent_identity_and_no_secret(self):
        self.bridge.publish(12345)
        d=json.loads((self.folder/DISCOVERY_NAME).read_text())
        self.assertEqual(d["credential_ref"],TOKEN_NAME)
        token=self.bridge._token()
        self.assertNotIn(token,json.dumps(d))
        self.assertEqual(d["origin"],"http://127.0.0.1:12345")
        self.bridge.unpublish();self.assertFalse((self.folder/DISCOVERY_NAME).exists())
        new=ClientBridge(self.folder,profiles=lambda:[])
        self.assertEqual((new.bridge_id,new.principal,new._token()),(self.bridge.bridge_id,self.bridge.principal,token))

    def test_http_same_handler_security_and_sse(self):
        holder={"port":0}
        server=ThreadingHTTPServer(("127.0.0.1",0),web_client.make_handler(self.folder,lambda:holder["port"],"csrf",bridge=self.bridge))
        holder["port"]=server.server_address[1]
        server.daemon_threads=True
        server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start()
        def cleanup():
            server.shutdown();server.server_close();server_thread.join(2)
        self.addCleanup(cleanup)
        def get(path,method="GET",value=None,auth=True,**extra):
            conn=http.client.HTTPConnection("127.0.0.1",holder["port"],timeout=8)
            try:
                headers={"Content-Type":"application/json",**extra}
                if auth:headers["Authorization"]="Bearer "+self.bridge._token()
                conn.request(method,path,json.dumps(value) if value is not None else None,headers)
                response=conn.getresponse()
                return response.status,response.read(),dict(response.getheaders())
            finally:
                conn.close()
        self.assertEqual(get("/bridge/v1/health",auth=False)[0],401)
        self.assertEqual(get("/bridge/v1/health",Origin="http://evil.invalid")[0],403)
        self.assertEqual(get("/bridge/v1/health",Host="evil.invalid")[0],403)
        self.assertEqual(get("/api/session",auth=False)[0],200)
        code,b,headers=get("/bridge/v1/models")
        self.assertEqual(code,200);self.assertNotIn(self.bridge._token(),b.decode())
        r=self.request()
        code,b,headers=get("/bridge/v1/chat/stream","POST",r)
        self.assertEqual(code,200);self.assertTrue(headers["Content-Type"].startswith("text/event-stream"))
        self.assertEqual(headers["Cache-Control"],"no-store")
        frames=b.decode().strip().split("\n\n")
        events=[json.loads(f.split("\n")[2][6:]) for f in frames]
        self.assertEqual([x["sequence"] for x in events],list(range(len(events))))
        self.assertEqual(events[-1]["state"],"SUCCEEDED")
        self.assertEqual(get("/bridge/v1/chat/stream","POST",r)[0],409)
        self.assertEqual(json.loads(get("/bridge/v1/requests/"+r["request_id"])[1])["state"],"SUCCEEDED")

    def test_unavailable_manager_and_unknown_target(self):
        old=self.bridge._snapshot
        def down(profile):
            if profile["manager_id"]=="m1":
                raise ChatClientError("manager_connection_failed",503)
            return old(profile)
        self.bridge._snapshot=down
        rows=self.bridge.refresh()["targets"]
        self.assertEqual(next(t for t in rows if t["manager_id"]=="m1")["status"],"UNAVAILABLE")
        self.error("manager_unavailable",self.bridge.start,self.request())
        self.error("unknown_target",self.bridge.start,self.request(target_id="tgt_"+"f"*64))
        self.assertEqual(self.calls,[])

    def test_permission_scopes_and_token_rotation(self):
        token=self.bridge._token()
        self.bridge.permissions=("read",)
        self.bridge.authorize({"Authorization":"Bearer "+token},"read")
        self.error("forbidden",self.bridge.authorize,{"Authorization":"Bearer "+token},"chat")
        self.assertTrue(all(not x["allowed_operations"] for x in self.bridge.refresh()["targets"]))
        (self.folder/TOKEN_NAME).write_text("X"*64,encoding="ascii")
        self.error("unauthorized",self.bridge.authorize,{"Authorization":"Bearer "+token},"read")
        self.bridge.authorize({"Authorization":"Bearer "+"X"*64},"read")

    def test_preflight_effective_manager_bytes_and_unchanged_messages(self):
        self.snapshots["m1"]["chat"]["transport_policy"]={**POLICY,"request_bytes":64}
        self.error("request_too_large",self.bridge.start,self.request())
        self.assertEqual(self.calls,[])
        self.snapshots["m1"]["chat"]["transport_policy"]=POLICY
        messages=[{"role":"user","content":"Unicode 🌊"}]
        original=deepcopy(messages)
        list(self.bridge.start(self.request(messages=messages)))
        self.assertEqual(messages,original)
        self.assertEqual(self.calls[0][0],original)

    def test_unknown_transport_before_meta_blocks_retry(self):
        def failure(*args,**kwargs):
            raise ChatClientError("manager_connection_failed",503)
            yield
        self.bridge._stream=failure
        r=self.request()
        self.error("manager_unavailable",next,self.bridge.start(r))
        self.assertEqual(self.bridge.status(r["request_id"])["state"],"UNKNOWN")
        self.error("request_already_attempted",self.bridge.start,r)
        self.assertEqual(len(self.cancel_calls),1)

    def test_exact_schema_if_validator_available(self):
        try:
            from jsonschema import Draft202012Validator, FormatChecker
        except ImportError:
            self.skipTest("Optional full JSON Schema checks use existing jsonschema QA environment")
        root=Path(__file__).parent.parent/"Contracts/ClientBridge/v1"
        if not root.is_dir():
            self.skipTest("Canonical contract not included in this sparse source run")
        spec=json.loads((root/"openapi.yaml").read_text(encoding="utf-8"))
        packet=json.loads((root/"stream-events.schema.json").read_text(encoding="utf-8"))
        def valid(name,value):
            schema={"$ref":"#/components/schemas/"+name,"components":spec["components"]}
            Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
        self.bridge.permissions=("read","chat")
        valid("Health",self.bridge.health())
        valid("Catalog",self.bridge.refresh())
        r=self.request()
        valid("ChatRequest",r)
        for e in self.bridge.start(r):
            Draft202012Validator(packet).validate(e)
        valid("RequestStatus",self.bridge.status(r["request_id"]))
        valid("CancelResponse",self.bridge.cancel({k:r[k] for k in ("request_id","target_id","instance_id")}))
        valid("Error",self.error("request_already_attempted",self.bridge.start,r).data)

if __name__=="__main__":
    unittest.main()
