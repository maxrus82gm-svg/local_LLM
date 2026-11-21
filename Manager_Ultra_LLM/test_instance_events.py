import unittest
from unittest.mock import patch, Mock
import colibri2_runner as runner
from control_runtime import ColibriBackend
import test_control_runtime as admission


def denied(code=5):
    error = PermissionError("test")
    error.winerror = code
    return error


class HeartbeatTests(unittest.TestCase):
    def test_ready_conflict_recovers_without_raising(self):
        writer = runner.HeartbeatWriter()
        state = {"instance":"slot5","session":"a"*32,"state":"READY"}
        with patch.object(runner,"write_json",side_effect=[denied(),denied(),None]), patch.object(runner,"state_write_event") as log:
            self.assertFalse(writer.publish("state.json",state,"READY"))
            self.assertFalse(writer.publish("state.json",state,"READY"))
            self.assertTrue(writer.publish("state.json",state,"READY"))
            self.assertEqual([c.args[1] for c in log.call_args_list],["heartbeat_write_delayed","heartbeat_write_recovered"])

    def test_initial_and_other_errors_remain_strict(self):
        for previous,code in [("STARTING",5),("READY",112)]:
            with patch.object(runner,"write_json",side_effect=denied(code)):
                with self.assertRaises(OSError):
                    runner.HeartbeatWriter().publish("state.json",{"state":"READY"},previous)

    def test_persistent_conflict_is_bounded(self):
        writer=runner.HeartbeatWriter()
        with patch.object(runner,"write_json",side_effect=denied()), patch.object(runner,"state_write_event"), patch.object(runner.time,"monotonic",side_effect=[1,32]):
            self.assertFalse(writer.publish("state.json",{"state":"READY"},"READY"))
            with self.assertRaises(OSError):
                writer.publish("state.json",{"state":"READY"},"READY")


class InstanceEventTests(unittest.TestCase):
    def test_every_instance_and_no_duplicate_polling(self):
        case=admission.AdmissionTests()
        case.setUp()
        try:
            a=case.start(slot_id="slot2")
            b=case.start(slot_id="slot3")
            case.settle()
            case.backend.states[a["instance_id"]]={"state":"ERROR","released":True,"reason":"state_file_winerror_5"}
            for _ in range(3):
                case.core.watchdog_once()
            with case.core.db() as db:
                rows=db.execute("SELECT instance_id,state,reason FROM instance_events ORDER BY event_id").fetchall()
            self.assertEqual([r[1] for r in rows if r[0]==a["instance_id"]],["STARTING","READY","ERROR"])
            self.assertEqual([r[1] for r in rows if r[0]==b["instance_id"]],["STARTING","READY"])
            self.assertEqual(rows[-1][2],"state_file_winerror_5")
        finally:
            case.doCleanups()

    def test_reason_is_sanitized_and_specific(self):
        spec=runner.RunnerSpec("slot3",8002,"kat","cpu",instance_id="a"*32)
        native=Mock()
        native.listeners.return_value=[]
        state={"state":"ERROR","session":"a"*32,"job_cleanup_confirmed":True,
               "reason":"[WinError 5] denied state.json SECRET"}
        with patch.object(runner,"NativeWindows",return_value=native), patch.object(runner,"run",return_value=state):
            status=ColibriBackend().status(spec,"a"*32)
        self.assertEqual(status["reason"],"state_file_winerror_5")
        self.assertTrue(status["released"])
