"""CONTROL-01 offline admission: temp journals and injected process authority only."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

from control_runtime import ModelControl, ControlError
from colibri2_runner import RunnerSpec, configured, paths, command_and_environment, verify_review, StartDenied
import test_pairing_http as pairing_qa
from test_pairing_http import ADMIN_MARKER, VIEWER_MARKER


class Backend:
    def __init__(self):
        self.memory = 100
        self.ports = [8000]
        self.verified = True
        self.vram = 20
        self.states = {}
        self.starts = []
        self.stops = []
    def telemetry(self):
        return {"free_gib":self.memory, "ports":self.ports, "sampled":time.monotonic(),
                "verified":self.verified, "vram_free_gib":self.vram}
    def preflight(self, spec):
        pass
    def start(self, spec, identity):
        self.starts.append(identity)
        self.states[identity] = {"state":"READY", "released":False}
    def stop(self, spec, identity):
        self.stops.append(identity)
        self.states[identity] = {"state":"STOPPED", "released":True}
    def status(self, spec, identity):
        return self.states.get(identity, {"state":"ERROR", "released":False})


class AdmissionTests(unittest.TestCase):
    def operation(self,op,**fields):
        return self.core.handle(self.alice,{"op":op,"request_id":uuid.uuid4().hex,**fields})

    def test_same_slot_race_has_exactly_one_winner(self):
        def request(_):
            try:return self.start(slot_id="slot2")
            except ControlError as error:return error.reason
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(request,range(2)))
        self.assertEqual(sum(type(r) is dict for r in results),1)
        self.assertIn("no_free_authorized_slot",results)

    def test_two_identical_models_have_isolated_specs_and_stop_one_only(self):
        first=self.start();second=self.start()
        self.settle()
        with self.core.db() as db:rows=self.core._rows(db)
        specs=[RunnerSpec(**json.loads(r["spec"])) for r in rows]
        self.assertNotEqual(specs[0].home,specs[1].home)
        self.assertNotEqual(specs[0].api_id,specs[1].api_id)
        self.assertNotEqual(specs[0].mutex,specs[1].mutex)
        self.operation("stop",instance_id=first["instance_id"]);self.settle()
        current={r["instance_id"]:r for r in self.core.catalog(self.alice)["instances"]}
        self.assertEqual(current[second["instance_id"]]["state"],"READY")
        self.assertEqual(self.backend.stops,[first["instance_id"]])

    def test_two_cuda_instances_fit_the_measured_budget(self):
        self.backend.vram=8
        first=self.start(mode="cuda");second=self.start(mode="cuda")
        self.assertNotEqual(first["instance_id"],second["instance_id"])
        with self.assertRaisesRegex(ControlError,"insufficient_vram"):self.start(mode="cuda")

    def test_ready_gpu_memory_is_not_charged_twice(self):
        self.backend.vram=8
        self.start(mode="cuda");self.settle()
        self.backend.vram=4  # driver free memory already includes first allocation
        self.assertEqual(self.start(mode="cuda")["state"],"STARTING")

    def test_dynamic_slot_idempotence_access_selection_and_restart(self):
        rid=uuid.uuid4().hex
        body={"op":"add_slot","request_id":rid}
        first=self.core.handle(self.alice,body)
        self.assertEqual(first,self.core.handle(self.alice,body))
        slot=first["slot_id"]
        self.assertIn(slot,self.core.effective_principal(self.alice)["allowed_slots"])
        self.operation("select",slot_id=slot,model_key="kat",mode="cuda",expected_revision=0)
        with self.assertRaisesRegex(ControlError,"slot_selection_changed"):
            self.operation("select",slot_id=slot,model_key="qwen36",mode="cpu",expected_revision=0)
        restored=self.make()
        selected=next(s for s in restored.catalog(self.alice)["slots"] if s["slot_id"]==slot)
        self.assertEqual((selected["model_key"],selected["mode"]),("kat","cuda"))
        with self.assertRaisesRegex(ControlError,"slot_not_authorized"):
            self.start(slot_id=slot,principal={**self.alice,"client_id":"bob"})
        instance=self.start(slot_id=slot)
        with self.assertRaisesRegex(ControlError,"slot_in_use"):
            self.operation("select",slot_id=slot,model_key="qwen36",mode="cpu")
        self.assertEqual(instance["slot_id"],slot)

    def test_concurrent_slot_additions_reserve_unique_ports_and_skip_listeners(self):
        self.config["control"]["slot_port_range"]=[8100,8110]
        self.backend.ports += [8100,8102]
        with ThreadPoolExecutor(4) as pool:rows=list(pool.map(lambda _:self.operation("add_slot"),range(4)))
        self.assertEqual(len({r["slot_id"] for r in rows}),4)
        self.assertEqual(len({r["api_port"] for r in rows}),4)
        self.assertTrue(all(r["api_port"] not in (8100,8102) for r in rows))

    def test_resource_warning_needs_server_permission_and_fresh_single_use_ack(self):
        self.backend.memory=23
        check=self.operation("check",model_key="kat",mode="cpu",slot_id="slot2")
        self.assertTrue(check["requires_ack"])
        self.assertEqual(check["forecast"]["ram_after_gib"],9)
        with self.assertRaisesRegex(ControlError,"resource_risk_not_permitted"):
            self.start(slot_id="slot2",risk_ack=True)
        self.config["control"]["resources"]={"allow_risk_ack":True}
        check=self.operation("check",model_key="kat",mode="cpu",slot_id="slot2")
        with self.assertRaisesRegex(ControlError,"risk_ack_required"):self.start(slot_id="slot2")
        with self.assertRaisesRegex(ControlError,"risk_confirmation_stale"):
            self.start(slot_id="slot3",risk_ack=True,risk_token=check["risk_token"])
        self.start(slot_id="slot2",risk_ack=True,risk_token=check["risk_token"])
        with self.assertRaisesRegex(ControlError,"risk_confirmation_stale"):
            self.start(slot_id="slot3",risk_ack=True,risk_token=check["risk_token"])

    def test_ten_gib_is_an_explicit_warning_setting_not_a_fixed_ban(self):
        self.backend.memory=23
        self.config["control"]["resources"]={"ram_warning_gib":5}
        self.assertEqual(self.start()["state"],"STARTING")

    def test_slot_creation_cannot_grant_control_and_no_delete_api_exists(self):
        with self.assertRaisesRegex(ControlError,"control_models_required"):
            self.core.handle({**self.alice,"control_models":False},{"op":"add_slot","request_id":uuid.uuid4().hex})
        with self.assertRaisesRegex(ControlError,"invalid_control_fields"):
            self.operation("remove_slot",slot_id="slot2")

    def test_configured_runner_inherits_engine_limits_and_keeps_job_ownership(self):
        spec=RunnerSpec("slot2",8001,"kat","cpu",instance_id="a"*32)
        with configured(spec):
            command,environment=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
        for flag in ("--ctx","--ngen","--ram","--no-think"):self.assertNotIn(flag,command)
        self.assertNotIn("COLI_THINK",environment)
        self.assertNotIn("OMP_THREAD_LIMIT",environment)
        self.assertIn("sessions",str(spec.home))
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.backend = Backend()
        self.pending = []
        self.config = {"manager_id":"test", "colibri_root":str(self.folder), "models_root":str(self.folder),
            "slots":[{"slot_id":"slot1","api_port":8000,"protected":True}] +
                    [{"slot_id":f"slot{i}","api_port":7999+i} for i in range(2,7)],
            "control":{"owner_go":True,"host":"offline-test", "state_dir":str(self.folder),
                       "instance_root":str(self.folder), "reviews":{
                key:{mode:{"evidence":"measured", "source_hashes":{"runtime":"hash"}, "vram_gib":4,"ram_gib":14}
                     for mode in ("cpu","cuda")} for key in ("kat","qwen36")}}}
        self.acl = patch("pairing_server._require_private_acl")
        self.acl.start()
        self.addCleanup(self.acl.stop)
        self.core = self.make()
        self.alice = {"client_id":"alice", "control_models":True,
                      "allowed_slots":[f"slot{i}" for i in range(1,7)]}
    def make(self):
        return ModelControl(self.config, backend=self.backend, dispatch=self.pending.append)
    def start(self, key="kat", mode="cpu", principal=None, request_id=None, **extra):
        return self.core.handle(principal or self.alice, {"op":"start","model_key":key,
            "mode":mode,"request_id":uuid.uuid4().hex if request_id is None else request_id, **extra})
    def settle(self):
        while self.pending:
            self.pending.pop(0)()
        with self.core.db() as db:
            db.execute("UPDATE instances SET created=0")
            db.commit()
    def test_no_permission_or_pairing_admin_does_not_control(self):
        for p in ({"client_id":"x","allowed_slots":["slot2"]},
                  {"client_id":"x","allowed_slots":["slot2"],"pairing_admin":True}):
            with self.assertRaisesRegex(ControlError,"control_models_required"):
                self.start(principal=p)
        self.assertFalse(self.pending)
    def test_default_disabled_no_journal_or_process(self):
        core = ModelControl({"manager_id":"m","slots":[]})
        self.assertIsNone(core.db_path)
        with self.assertRaisesRegex(ControlError,"owner_go_required"):
            core.handle(self.alice,{})
    def test_auto_slot_and_idempotent_replay(self):
        rid=uuid.uuid4().hex
        first=self.start(request_id=rid)
        repeat=self.start(request_id=rid)
        self.assertEqual(first["instance_id"],repeat["instance_id"])
        self.assertEqual(first["slot_id"],"slot2")
        self.assertEqual(len(self.pending),1)
        self.settle()
        self.assertEqual(self.core.catalog(self.alice)["instances"][0]["state"],"READY")
    def test_request_id_conflict(self):
        rid=uuid.uuid4().hex
        self.start(request_id=rid)
        with self.assertRaisesRegex(ControlError,"request_id_conflict"):
            self.start(key="qwen36",request_id=rid)
    def test_two_managers_racing_reserve_two_distinct_instances_of_same_model(self):
        other=self.make()
        def submit(core):
            try:
                return core.handle(self.alice,{"op":"start","model_key":"kat","mode":"cpu","request_id":uuid.uuid4().hex})
            except ControlError as e:
                return e.reason
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(submit,[self.core,other]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),2)
        self.assertEqual(len({r["slot_id"] for r in results}),2)
        self.assertEqual(len({r["instance_id"] for r in results}),2)
    def test_different_models_get_different_slots_beyond_three(self):
        self.backend.ports=[8000,8001,8002,8003]
        first=self.start()
        second=self.start(key="qwen36")
        self.assertEqual((first["slot_id"],second["slot_id"]),("slot5","slot6"))
    def test_resource_gates_ram_vram_unknown_and_budget(self):
        for free, vram, verified, mode, reason in (
            (23,20,True,"cpu","resource_risk_not_permitted"),
            (100,None,True,"cuda","vram_telemetry_unknown"),
            (100,2,True,"cuda","insufficient_vram"),
            (100,20,False,"cpu","resource_telemetry_unknown"),
            (float('nan'),20,True,"cpu","resource_telemetry_unknown")):
            self.backend.memory,self.backend.vram,self.backend.verified=free,vram,verified
            with self.subTest(reason=reason),self.assertRaisesRegex(ControlError,reason):
                self.start(mode=mode)
        self.assertFalse(self.pending)
    def test_unreviewed_runtime_denied(self):
        self.config["control"]["reviews"]={}
        with self.assertRaisesRegex(ControlError,"runtime_review_required"):
            self.start()
    def test_unpermitted_model_or_no_free_authorized_slot(self):
        with self.assertRaisesRegex(ControlError,"model_not_authorized"):
            self.start(principal={**self.alice,"allowed_models":["qwen36"]})
        with self.assertRaisesRegex(ControlError,"no_free_authorized_slot"):
            self.start(principal={**self.alice,"allowed_slots":["slot1"]})
    def test_invalid_fields_commands_paths_modes(self):
        for extra in ({"exe":"cmd.exe"},{"port":8001},{"mode":"auto"},{"model_key":"../kat"},
                      {"request_id":False},{"op":["start"]}):
            with self.subTest(extra=extra),self.assertRaises(ControlError):
                self.start(**extra)
        self.assertFalse(self.pending)
    def test_second_cuda_reservation_uses_measured_vram(self):
        self.backend.vram=7
        self.start(mode="cuda")
        with self.assertRaisesRegex(ControlError,"insufficient_vram"):
            self.start(key="qwen36",mode="cuda")
    def test_stop_only_own_stable_instance(self):
        first=self.start()
        self.settle()
        body={"op":"stop","instance_id":first["instance_id"],"request_id":uuid.uuid4().hex}
        with self.assertRaisesRegex(ControlError,"instance_not_authorized"):
            self.core.handle({**self.alice,"client_id":"bob"},body)
        self.assertEqual(self.core.handle(self.alice,body)["state"],"STOPPING")
        with self.assertRaisesRegex(ControlError,"instance_not_ready"):
            self.core.assert_chat_allowed(first["slot_id"])
        self.settle()
        self.assertEqual(self.core.catalog(self.alice)["instances"][0]["state"],"STOPPED")
        self.assertEqual(len(self.backend.stops),1)

    def test_unknown_telemetry_catalog_is_fail_closed(self):
        self.backend.verified=False
        catalog=self.core.catalog(self.alice)
        self.assertTrue(all(not v["available"] for m in catalog["models"] for v in m["modes"].values()))
    def test_restart_recovery_never_kills_or_releases_ambiguous_process(self):
        first=self.start()
        self.pending.clear()  # simulate crash before supervisor dispatch
        self.settle()
        restored=self.make()
        row=restored.catalog(self.alice)["instances"][0]
        self.assertEqual(row["state"],"ERROR")
        self.assertFalse(row["can_stop"])
        with self.assertRaisesRegex(ControlError,"no_free_authorized_slot"):
            self.start(slot_id=first["slot_id"])
        self.assertNotEqual(self.start()["slot_id"],first["slot_id"])
        self.assertEqual(self.backend.stops,[])
    def test_failed_start_quarantines_slot(self):
        self.backend.start=lambda *a: (_ for _ in ()).throw(RuntimeError("private"))
        self.start()
        self.settle()
        row=self.core.catalog(self.alice)["instances"][0]
        self.assertEqual(row["state"],"ERROR")
        self.assertNotIn("private",str(row))
    def test_occupied_port_and_primary_cannot_be_selected(self):
        self.backend.ports=list(range(8000,8006))
        with self.assertRaisesRegex(ControlError,"no_free_authorized_slot"):
            self.start()
    def test_check_no_reservation_or_dispatch(self):
        result=self.core.handle(self.alice,{"op":"check","model_key":"kat","mode":"cpu","request_id":uuid.uuid4().hex})
        self.assertEqual(result["state"],"CHECKED")
        self.assertEqual(self.pending,[])
        self.assertEqual(self.core.catalog(self.alice)["instances"],[])
    def test_runner_specs_isolated_and_cpu_cuda_commands(self):
        from concurrent.futures import ThreadPoolExecutor
        def command(mode):
            spec=RunnerSpec("slot5",8004,"kat",mode)
            with configured(spec):
                p=paths()
                cmd,env=command_and_environment({"paths":p,"launcher":"launcher","model":"model"})
                return p,cmd,env
        with ThreadPoolExecutor(2) as pool:
            cpu,cuda=list(pool.map(command,["cpu","cuda"]))
        self.assertEqual(cpu[1][cpu[1].index("--gpu")+1],"none")
        self.assertEqual(cuda[1][cuda[1].index("--gpu")+1],"0")
        self.assertIn("8004",cpu[0]["gateway_pid"])
        self.assertEqual(paths()["gateway_pid"].split("coli-serve-")[-1],"8001.pid")
    def test_primary_spec_forbidden(self):
        for slot,port in (("slot1",8001),("slot2",8000),("slot4",8443)):
            with self.assertRaises(ValueError):
                RunnerSpec(slot,port)
    def test_review_hash_drift_refuses_before_materialization(self):
        with configured(RunnerSpec(review={"evidence":"measured","source_hashes":{"a":"b"}})):
            with self.assertRaises(StartDenied):
                verify_review({"source_hashes":{"a":"changed"}})

    def test_preflight_reason_is_preserved_without_exposing_paths(self):
        for message,expected in (("runtime_or_model_changed","runtime_or_model_changed"),
                                 ("private C:/server/path", "runtime_preflight_unverified")):
            self.backend.preflight=lambda spec: (_ for _ in ()).throw(StartDenied(message))
            with self.assertRaisesRegex(ControlError,expected):
                self.start()
        self.assertFalse(self.pending)


class HTTPAuthorizationTests(unittest.TestCase):
    setUp=pairing_qa.PairingProtocolTests.setUp
    req=pairing_qa.PairingProtocolTests.req
    def test_control_unauthorized_and_pairing_admin_is_not_control(self):
        body={"op":"start","model_key":"kat","mode":"cpu","request_id":"a"*32}
        self.assertEqual(self.req("/v1/control","POST",body)[0],401)
        for token in (ADMIN_MARKER,VIEWER_MARKER):
            code,data=self.req("/v1/control","POST",body,token)
            self.assertEqual(code,403)
            self.assertEqual(data["error"],"control_models_required")
    def test_catalog_auth_and_default_denial(self):
        self.assertEqual(self.req("/v1/control/catalog")[0],401)
        code,data=self.req("/v1/control/catalog",token=VIEWER_MARKER)
        self.assertEqual(code,200)
        self.assertFalse(data["control_models"])
        self.assertTrue(all(not m["modes"]["cpu"]["available"] for m in data["models"]))

    def test_stream_cancel_auth_and_scope(self):
        body={"slot_id":"slot2","request_id":"a"*32}
        self.assertEqual(self.req("/v1/chat/cancel","POST",body)[0],401)
        self.assertEqual(self.req("/v1/chat/cancel","POST",body,ADMIN_MARKER)[0],403)
        code,result=self.req("/v1/chat/cancel","POST",body,VIEWER_MARKER)
        self.assertEqual(code,200)
        self.assertFalse(result["cancelled"])


if __name__ == "__main__":
    unittest.main()
