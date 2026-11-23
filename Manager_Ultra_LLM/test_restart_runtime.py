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
