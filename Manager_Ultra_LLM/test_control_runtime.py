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

    def test_context_override_isolated_bound_to_risk_and_forwarded_to_cli(self):
        self.config["control"]["resources"]={"allow_risk_ack":True}
        review=self.config["control"]["reviews"]["kat"]["cuda"]
        review["launch"]={"context_tokens":2048,"threads":2}
        check=self.operation("check",model_key="kat",mode="cuda",slot_id="slot2",context_tokens=16384)
        self.assertIsNone(check["forecast"]["vram_estimate_gib"])
        self.assertIsNone(check["forecast"]["ram_estimate_gib"])
        self.assertEqual(check["forecast"]["estimate_evidence"],"context_unmeasured")
        self.assertTrue(check["requires_ack"])
        with self.assertRaisesRegex(ControlError,"risk_confirmation_stale"):
            self.start(mode="cuda",slot_id="slot2",context_tokens=32768,risk_ack=True,risk_token=check["risk_token"])
        first=self.start(mode="cuda",slot_id="slot2",context_tokens=16384,risk_ack=True,risk_token=check["risk_token"])
        self.assertEqual(review["launch"]["context_tokens"],2048)
        with self.core.db() as db:
            spec=RunnerSpec(**json.loads(self.core._rows(db)[0]["spec"]))
        self.assertEqual(spec.review["launch"]["context_tokens"],16384)
        self.assertEqual(spec.resources["context_tokens"],16384)
        with configured(spec):
            command,env=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
        self.assertEqual(command.count("--ctx"),1)
        self.assertEqual(command[command.index("--ctx")+1],"16384")
        self.assertNotIn("--ngen",command)
        self.assertEqual(env["OMP_NUM_THREADS"],"2")
        self.assertEqual(first["slot_id"],"slot2")
        for bad in (0,-1,1000000,True,2.5,"8192",None):
            with self.subTest(bad=bad),self.assertRaisesRegex(ControlError,"invalid_context_tokens"):
                self.operation("check",model_key="kat",mode="cpu",context_tokens=bad)
        self.assertEqual(len(self.pending),1)

    def test_cuda_profile_saved_per_slot_and_forwarded_only_at_explicit_start(self):
        from cuda_profile import DEFAULT_PROFILE
        self.config["control"]["resources"]={"allow_risk_ack":True}
        selection=self.operation("select",slot_id="slot2",model_key="kat",mode="cuda")
        saved=self.operation("cuda_settings",slot_id="slot2",model_key="kat",
            expected_revision=selection["revision"],cuda_profile=DEFAULT_PROFILE)
        self.assertFalse(self.pending)
        # Persistence and risk binding survive a Manager restart.
        self.core=self.make()
        check=self.operation("check",slot_id="slot2",model_key="kat",mode="cuda",context_tokens=32768)
        self.assertEqual(check["forecast"]["cuda_profile"],DEFAULT_PROFILE)
        self.assertIsNone(check["forecast"]["vram_estimate_gib"])
        started=self.start(mode="cuda",slot_id="slot2",context_tokens=32768,
                           risk_ack=True,risk_token=check["risk_token"])
        with self.core.db() as db:
            spec=RunnerSpec(**json.loads(self.core._rows(db)[0]["spec"]))
        with configured(spec):
            command,env=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
        self.assertEqual(command[command.index("--vram")+1],"3.5")
        self.assertEqual(env["COLI_CUDA_CHAIN"],"0")
        self.assertNotIn("COLI_CUDA_CHAIN_ROWS",env)
        self.assertEqual(started["cuda_profile"],DEFAULT_PROFILE)
        self.settle()
        state=self.core.catalog(self.alice)
        slot=next(x for x in state["slots"] if x["slot_id"]=="slot2")
        changed={**DEFAULT_PROFILE,"chain":True,"rows":256,"target_gib":7.5}
        self.operation("cuda_settings",slot_id="slot2",model_key="kat",expected_revision=slot["revision"],cuda_profile=changed)
        self.assertFalse(self.pending)
        active=next(x for x in self.core.catalog(self.alice)["instances"] if x["instance_id"]==started["instance_id"])
        self.assertEqual(active["cuda_profile"],DEFAULT_PROFILE)
        with self.assertRaisesRegex(ControlError,"slot_selection_changed"):
            self.operation("cuda_settings",slot_id="slot2",model_key="kat",expected_revision=slot["revision"],cuda_profile=changed)
        with self.assertRaisesRegex(ControlError,"invalid_cuda_profile"):
            self.operation("cuda_settings",slot_id="slot2",model_key="kat",expected_revision=slot["revision"]+1,
                           cuda_profile={**changed,"budget_gib":8})
        with configured(RunnerSpec("slot3",8002,"kat","cuda",review={"launch":{"cuda_profile":changed}})):
            cmd,env=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
        self.assertEqual(env["COLI_CUDA_CHAIN_ROWS"],"256")
        with configured(RunnerSpec("slot3",8002,"kat","cpu")):
            cmd,env=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
        self.assertNotIn("--vram",cmd)
        self.assertNotIn("COLI_CUDA_CHAIN",env)

    def test_cuda_profile_rejects_foreign_slot_and_arbitrary_env(self):
        from cuda_profile import DEFAULT_PROFILE
        payload={"op":"cuda_settings","slot_id":"slot2","model_key":"kat","expected_revision":0,
                 "cuda_profile":DEFAULT_PROFILE,"request_id":uuid.uuid4().hex}
        with self.assertRaisesRegex(ControlError,"slot_not_authorized"):
            self.core.handle({**self.alice,"allowed_slots":["slot3"]},payload)
        with self.assertRaisesRegex(ControlError,"invalid_cuda_profile"):
            self.core.handle(self.alice,{**payload,"cuda_profile":{**DEFAULT_PROFILE,"PATH":"evil"}})
        with self.assertRaisesRegex(ControlError,"control_models_required"):
            self.core.handle({**self.alice,"control_models":False},payload)

    def test_context_capacity_uses_model_metadata_not_fixed_defaults(self):
        from colibri2_runner import validate_context_capacity
        meta=self.folder/"config.json"
        meta.write_text(json.dumps({"max_position_embeddings":262144}),encoding="utf-8")
        validate_context_capacity(self.folder,262144)
        with self.assertRaisesRegex(StartDenied,"context_capacity_exceeded"):
            validate_context_capacity(self.folder,262145)
        meta.write_text(json.dumps({"text_config":{"max_position_embeddings":32768}}),encoding="utf-8")
        validate_context_capacity(self.folder,16384)
        meta.write_text("{}",encoding="utf-8")
        with self.assertRaisesRegex(StartDenied,"context_capacity_unknown"):
            validate_context_capacity(self.folder,8192)
        validate_context_capacity(self.folder,None)

    def test_same_slot_race_has_exactly_one_winner(self):
        def request(_):
            try:return self.start(slot_id="slot2")
            except ControlError as error:return error.reason
        with ThreadPoolExecutor(2) as pool:results=list(pool.map(request,range(2)))
        self.assertEqual(sum(type(r) is dict for r in results),1)
        self.assertIn("no_free_authorized_slot",results)

    def test_catalog_requires_verified_profile_metadata_and_weight_header(self):
        profile={"qwen36":{"folder":"qa-qwen","model_id":"qa-qwen"}}
        (self.folder/"ULTRA-CONTROL.py").write_text("PROFILES = "+repr(profile),encoding="utf-8")
        model=self.folder/"qa-qwen"
        model.mkdir()
        def row():
            return next(item for item in self.core.catalog(self.alice)["models"] if item["key"]=="qwen36")
        self.assertFalse(row()["files_present"],"A directory alone is not an installed model")
        self.assertTrue(row()["installation_checked"])
        self.assertEqual(row()["modes"]["cpu"]["reason"],"model_files_unverified")
        (model/"config.json").write_text(json.dumps({"model_type":"qwen3_5_moe_text"}))
        weight=model/"Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
        weight.write_bytes(b"GGUF")
        (model/"gguf.json").write_text(json.dumps({"mode":"link","arch":"qwen35moe",
            "parts":1,"gguf":str(weight),"size":4}))
        self.assertTrue(row()["files_present"])
        self.assertTrue(row()["modes"]["cpu"]["available"])
        weight.write_bytes(b"BAD!")
        self.assertFalse(row()["files_present"],"A changed weight header revokes catalogue readiness")
        weight.write_bytes(b"GGUF")
        (model/"config.json").write_text("[]")
        self.assertFalse(row()["files_present"],"Malformed metadata must not break the whole catalogue")

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

    def test_vram_forecast_does_not_limit_instance_count(self):
        self.backend.vram=8
        first=self.start(mode="cuda");second=self.start(mode="cuda")
        self.assertNotEqual(first["instance_id"],second["instance_id"])
        check=self.operation("check",model_key="kat",mode="cuda")
        self.assertIn("low_vram_forecast",check["warnings"])
        self.assertFalse(check["requires_ack"])
        third=self.start(mode="cuda")
        self.assertNotIn(third["instance_id"],[first["instance_id"],second["instance_id"]])

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
    def test_second_cuda_reservation_warns_without_blocking(self):
        self.backend.vram=7
        self.start(mode="cuda")
        check=self.operation("check",model_key="qwen36",mode="cuda")
        self.assertEqual(check["forecast"]["vram_after_gib"],-1)
        self.assertIn("low_vram_forecast",check["warnings"])
        self.assertFalse(check["requires_ack"])
        self.assertEqual(self.start(key="qwen36",mode="cuda")["state"],"STARTING")

    def test_reviewed_cuda_without_vram_estimate_is_advisory(self):
        self.config["control"]["reviews"]["kat"]["cuda"].pop("vram_gib")
        check=self.operation("check",model_key="kat",mode="cuda")
        self.assertIn("vram_estimate_unknown",check["warnings"])
        self.assertIsNone(check["forecast"]["vram_after_gib"])
        self.assertFalse(check["requires_ack"])
        self.start(mode="cuda")
        check=self.operation("check",model_key="qwen36",mode="cuda")
        self.assertIn("vram_reservation_unknown",check["warnings"])
        self.assertIsNone(check["forecast"]["vram_after_gib"])
        self.assertFalse(check["requires_ack"])
        self.assertEqual(self.start(key="qwen36",mode="cuda")["state"],"STARTING")

    def test_runner_checks_gpu_and_review_but_not_forecast(self):
        exe=self.folder/"qwen36.exe"
        dll=self.folder/"coli_cuda.dll"
        dll.write_bytes(b"fake")
        review={"evidence":"measured","source_hashes":{"a":"b"},"vram_gib":8}
        plan={"source_engine":str(exe),"source_hashes":{"a":"b"}}
        with configured(RunnerSpec("slot2",8001,"kat","cuda",review=review)):
            with patch("resource_policy.read_vram",return_value={"free_gib":0.01,"total_gib":8}):
                verify_review(plan)
                review.pop("vram_gib")
                verify_review(plan)
                with self.assertRaisesRegex(StartDenied,"runtime_or_model_changed"):
                    verify_review({**plan,"source_hashes":{"a":"changed"}})
            with patch("resource_policy.read_vram",return_value=None):
                with self.assertRaisesRegex(StartDenied,"vram_telemetry_unknown"):
                    verify_review(plan)
            dll.unlink()
            with self.assertRaisesRegex(StartDenied,"cuda_runtime_or_measurement_unverified"):
                verify_review(plan)
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

    def test_stop_is_not_accepted_before_start_has_a_verified_supervisor(self):
        instance = self.start()["instance_id"]
        with self.assertRaisesRegex(ControlError, "instance_not_stoppable"):
            self.operation("stop", instance_id=instance)
        self.assertEqual(len(self.pending), 1)
        self.assertEqual(self.backend.stops, [])
        self.settle()
        self.assertEqual(self.core.catalog(self.alice)["instances"][0]["state"], "READY")

    def test_late_start_result_and_catalog_leave_accepted_stop_in_progress(self):
        start_backend = self.backend.start
        start = self.start()
        instance = start["instance_id"]

        def start_then_accept_stop(spec, identity):
            start_backend(spec, identity)
            self.assertEqual(self.operation("stop", instance_id=identity)["state"], "STOPPING")

        self.backend.start = start_then_accept_stop
        self.pending.pop(0)()
        with self.assertRaisesRegex(ControlError, "instance_not_ready"):
            self.core.assert_chat_allowed(start["slot_id"])
        # A verified supervisor can still report READY while STOP waits.
        with self.core.db() as db:
            db.execute("UPDATE instances SET created=? WHERE id=?", (time.time() - 15, instance))
            db.commit()
        self.assertEqual(self.core.catalog(self.alice)["instances"][0]["state"], "STOPPING")
        self.settle()
        stopped = self.core.catalog(self.alice)["instances"][0]
        self.assertEqual((stopped["state"], stopped["released"]), ("STOPPED", True))
        self.assertEqual(self.backend.stops, [instance])

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
    def test_manager_port_forbidden_but_unprotected_primary_supported(self):
        self.assertEqual(RunnerSpec("slot1",8000).port,8000)
        with self.assertRaises(ValueError):
            RunnerSpec("slot4",8443)
        with self.assertRaises(ValueError):
            RunnerSpec("slot4",8433,manager_port=8433)
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
    def test_source_denial_and_revoked_grant_are_distinct_http_failures(self):
        self.assertEqual(self.req('/v1/control/catalog', token=VIEWER_MARKER)[0], 200)
        config = json.loads(self.config_file.read_text(encoding='utf-8'))
        config['allowed_client_ips'] = ['127.0.0.2']
        self.config_file.write_text(json.dumps(config), encoding='utf-8')
        code, data = self.req('/v1/control/catalog', token=VIEWER_MARKER)
        self.assertEqual((code, data['error']), (403, 'source_not_permitted'))
        config['allowed_client_ips'] = ['127.0.0.1']
        config['clients'] = [c for c in config['clients'] if c['client_id'] != 'viewer']
        self.config_file.write_text(json.dumps(config), encoding='utf-8')
        code, data = self.req('/v1/control/catalog', token=VIEWER_MARKER)
        self.assertEqual((code, data['error']), (401, 'unauthorized'))

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
