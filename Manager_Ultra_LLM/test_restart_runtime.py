"""Offline regression for explicit, authorized managed per-chat Restart."""
import json
import unittest
import uuid

from control_runtime import ControlError
from unittest.mock import patch
from colibri2_runner import RunnerSpec
from test_control_runtime import AdmissionTests


class RestartTests(unittest.TestCase):
    setUp = AdmissionTests.setUp
    make = AdmissionTests.make
    start = AdmissionTests.start
    settle = AdmissionTests.settle

    def ready(self, mode="cpu"):
        started = self.start(slot_id="slot2",mode=mode)
        self.settle()
        with self.core.db() as db:
            revision=db.execute("SELECT revision FROM slots WHERE slot_id='slot2'").fetchone()[0]
        self.core.restart_gate=lambda slot,identity,principal:(lambda:None,lambda:None)
        return started,revision

    def restart(self, started, revision, **kwargs):
        return self.core.handle(self.alice,{"op":"restart","request_id":uuid.uuid4().hex,
            "slot_id":"slot2","instance_id":started["instance_id"],
            "expected_revision":revision,**kwargs})

    def test_same_model_mode_slot_and_new_instance_after_confirmed_release(self):
        started,rev=self.ready()
        reply=self.restart(started,rev)
        self.assertEqual(reply["stage"],"STOPPING")
        self.assertFalse(self.backend.stops)
        self.assertEqual(len(self.pending),1)
        self.pending.pop(0)()
        result=self.core.restart_status(self.alice,reply["request_id"])
        self.assertEqual(result["stage"],"READY")
        self.assertNotEqual(result["new_instance_id"],started["instance_id"])
        self.assertEqual((result["slot_id"],result["model_key"],result["mode"]),
                         ("slot2","kat","cpu"))
        self.assertEqual(self.backend.stops,[started["instance_id"]])
        self.assertEqual(len(self.backend.starts),2)
        with self.core.db() as db:
            rows=self.core._rows(db)
        self.assertEqual(sum(not x["released"] for x in rows),1)
        self.assertEqual(next(x for x in rows if not x["released"])["instance_id"],
                         result["new_instance_id"])

    def test_duplicate_id_has_single_stop_and_cross_owner_is_denied(self):
        started,rev=self.ready()
        rid=uuid.uuid4().hex
        command={"op":"restart","slot_id":"slot2","instance_id":started["instance_id"],
                 "expected_revision":rev,"request_id":rid}
        one=self.core.handle(self.alice,command)
        two=self.core.handle(self.alice,command)
        self.assertEqual(one,two)
        self.assertEqual(len(self.pending),1)
        with self.assertRaisesRegex(ControlError,"request_id_conflict"):
            self.core.handle(self.alice,{**command,"expected_revision":rev+1})
        with self.assertRaisesRegex(ControlError,"restart_not_found"):
            self.core.restart_status({**self.alice,"client_id":"stranger"},rid)
        self.pending.pop(0)()
        self.assertEqual(len(self.backend.stops),1)

    def test_busy_or_foreign_instance_does_not_stop(self):
        started,rev=self.ready()
        self.core.restart_gate=lambda *args:(_ for _ in ()).throw(ControlError("slot_chat_in_progress"))
        with self.assertRaisesRegex(ControlError,"slot_chat_in_progress"):
            self.restart(started,rev)
        self.assertFalse(self.backend.stops)
        self.core.restart_gate=lambda *args:(lambda:None,lambda:None)
        with self.assertRaisesRegex(ControlError,"instance_not_authorized"):
            self.restart({"instance_id":uuid.uuid4().hex},rev)
        self.assertFalse(self.backend.stops)

    def test_unconfirmed_stop_does_not_start_another_instance(self):
        started,rev=self.ready()
        previous=len(self.backend.starts)
        def missing_stop(spec,identity):
            raise RuntimeError("unverified")
        self.backend.stop=missing_stop
        accepted=self.restart(started,rev)
        self.pending.pop(0)()
        result=self.core.restart_status(self.alice,accepted["request_id"])
        self.assertEqual(result["stage"],"ERROR")
        self.assertEqual(result["reason"],"runner_action_unconfirmed")
        self.assertIsNone(result["new_instance_id"])
        self.assertEqual(len(self.backend.starts),previous)
        with self.core.db() as db:
            rows=self.core._rows(db)
        self.assertEqual(sum(not row["released"] for row in rows),1)

    def test_saved_cuda_profile_preserved_with_same_cuda_backend(self):
        from cuda_profile import DEFAULT_PROFILE
        self.config["control"]["resources"]={"allow_risk_ack":True}
        started,rev=self.ready("cuda")
        saved={**DEFAULT_PROFILE,"budget_gib":3.0,"chain":True,"rows":256}
        self.core.handle(self.alice,{"op":"cuda_settings","slot_id":"slot2",
            "model_key":"kat","cuda_profile":saved,"expected_revision":rev,
            "request_id":uuid.uuid4().hex})
        with self.core.db() as db:
            updated=db.execute("SELECT revision FROM slots WHERE slot_id='slot2'").fetchone()[0]
        accepted=self.restart(started,updated)
        if accepted["stage"]=="RISK_CONFIRMATION_REQUIRED":
            # Resource forecast may require an explicit owner-approved risk.
            accepted=self.core.handle(self.alice,{"op":"restart",
                "slot_id":"slot2","instance_id":started["instance_id"],
                "expected_revision":updated,"request_id":accepted["request_id"],
                "risk_ack":True,"risk_token":accepted["risk_token"]})
        self.assertEqual(accepted["stage"],"STOPPING")
        self.pending.pop(0)()
        result=self.core.restart_status(self.alice,accepted["request_id"])
        self.assertEqual(result["stage"],"READY")
        self.assertEqual(result["mode"],"cuda")
        with self.core.db() as db:
            row=next(x for x in self.core._rows(db) if x["instance_id"]==result["new_instance_id"])
        spec=RunnerSpec(**json.loads(row["spec"]))
        self.assertEqual(spec.review["launch"]["cuda_profile"],saved)

    def prepare_group_restart(self, *, after_release_insufficient=False):
        from test_multi_gpu import A,B,inventory,profile
        self.config["control"]["resources"]={"allow_risk_ack":True}
        original=self.backend.telemetry
        self.backend.telemetry=lambda:{**original(),"gpu_devices":inventory()}
        def op(name,**kwargs):
            return self.core.handle(self.alice,{"op":name,"request_id":uuid.uuid4().hex,**kwargs})
        selected=op("select",slot_id="slot2",model_key="kat",mode="cuda")
        saved={**profile("full",[A,B],20),"gpu_reserves_gib":{A:3,B:1}}
        op("cuda_settings",slot_id="slot2",model_key="kat",expected_revision=selected["revision"],cuda_profile=saved)
        checked=op("check",slot_id="slot2",model_key="kat",mode="cuda")
        started=self.start(slot_id="slot2",mode="cuda",risk_ack=True,risk_token=checked["risk_token"])
        self.settle()
        with self.core.db() as db:
            revision=db.execute("SELECT revision FROM slots WHERE slot_id='slot2'").fetchone()[0]
        def telemetry():
            devices=inventory()
            if not self.backend.stops or after_release_insufficient:
                devices=[{**d,"free_gib":1.0,"used_gib":d["total_gib"]-1.0} if d["uuid"] in (A,B) else d for d in devices]
            return {**original(),"gpu_devices":devices}
        self.backend.telemetry=telemetry
        self.core.restart_gate=lambda *args:(lambda:None,lambda:None)
        risk=self.restart(started,revision)
        self.assertEqual(risk["stage"],"RISK_CONFIRMATION_REQUIRED")
        self.assertIn("gpu_restart_memory_recheck",risk["warnings"])
        self.assertFalse(self.backend.stops)
        self.assertEqual(risk["forecast"]["gpu_placement"]["gpu_ids"],[A,B])
        accepted=self.core.handle(self.alice,{"op":"restart","slot_id":"slot2","instance_id":started["instance_id"],
            "expected_revision":revision,"request_id":risk["request_id"],"risk_ack":True,"risk_token":risk["risk_token"]})
        self.assertEqual(accepted["stage"],"STOPPING")
        return started,accepted

    def test_group_restart_holds_admission_and_rechecks_reserves_after_release(self):
        from test_multi_gpu import A,B
        started,accepted=self.prepare_group_restart()
        with self.assertRaisesRegex(ControlError,"gpu_restart_in_progress"):
            self.start(slot_id="slot3",mode="cuda")
        self.pending.pop(0)()
        result=self.core.restart_status(self.alice,accepted["request_id"])
        self.assertEqual(result["stage"],"READY")
        with self.core.db() as db:
            rows=self.core._rows(db)
            spec=RunnerSpec(**json.loads(next(r for r in rows if r["instance_id"]==result["new_instance_id"])["spec"]))
        self.assertEqual(spec.resources["gpu_placement"],[A,B])
        self.assertEqual(spec.resources["gpu_weight_cap_gib"],4.0)
        self.assertEqual(self.backend.stops,[started["instance_id"]])
        self.assertEqual(sum(not r["released"] for r in rows),1)

    def test_group_restart_low_vram_after_release_never_launches(self):
        started,accepted=self.prepare_group_restart(after_release_insufficient=True)
        self.pending.pop(0)()
        result=self.core.restart_status(self.alice,accepted["request_id"])
        self.assertEqual(result["stage"],"ERROR")
        self.assertEqual(result["reason"],"gpu_reserve_insufficient")
        self.assertEqual(self.backend.starts,[started["instance_id"]])
        with self.core.db() as db:
            self.assertFalse(self.core.gpu_restart_active(db))
            self.assertTrue(all(r["released"] for r in self.core._rows(db)))

    def test_context_capacity_is_checked_before_stop(self):
        started, rev = self.ready()
        with patch("restart_runtime._validate_context_before_stop",
                   side_effect=ControlError("context_capacity_exceeded")):
            with self.assertRaisesRegex(ControlError, "context_capacity_exceeded"):
                self.restart(started, rev, context_tokens=262144)
        self.assertFalse(self.backend.stops)
        self.assertFalse(self.pending)
        with self.core.db() as db:
            active = [row for row in self.core._rows(db) if not row["released"]]
        self.assertEqual(active[0]["state"], "READY")

    def test_trusted_model_metadata_limits_context(self):
        from restart_runtime import _validate_context_before_stop
        from resource_catalog import initial_catalogue
        model = self.folder / "qa-metadata"
        model.mkdir()
        (model / "config.json").write_text(json.dumps({"max_position_embeddings":8192}), encoding="utf-8")
        profile = initial_catalogue()["kat"].profile
        with patch("server_preflight.read_profiles",
                   return_value={profile:{"folder":"qa-metadata"}}):
            _validate_context_before_stop(self.core, "kat", 8192)
            with self.assertRaisesRegex(ControlError,"context_capacity_exceeded"):
                _validate_context_before_stop(self.core, "kat", 8193)

    def test_interrupted_restart_never_resumes_by_itself(self):
        started,rev=self.ready()
        accepted=self.restart(started,rev)
        self.assertEqual(accepted["stage"],"STOPPING")
        self.core=self.make()  # Simulated Manager process restart; no pending worker executes.
        self.assertEqual(self.core.restart_status(self.alice,accepted["request_id"])["stage"],"ERROR")
        self.assertFalse(self.backend.stops)
        self.assertEqual(len(self.backend.starts),1)


if __name__ == "__main__":
    unittest.main()
