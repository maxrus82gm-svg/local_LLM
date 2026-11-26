"""Recovery tests with isolated fake authority and benign Windows children."""
from contextlib import nullcontext
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch
import uuid

import colibri2_runner as runner
from control_runtime import ColibriBackend
import test_control_runtime as admission
from windows_process import (NativeWindows, WindowsError, DEFAULT_PROCESS_INVENTORY_TIMEOUT_SECONDS,
                             validate_process_inventory_timeout)


class ProcessInventoryTimeoutTests(unittest.TestCase):
    def test_timeout_bounds_and_default(self):
        self.assertEqual(DEFAULT_PROCESS_INVENTORY_TIMEOUT_SECONDS, 30)
        for value in (10, 30, 60, 120):
            self.assertEqual(validate_process_inventory_timeout(value), value)
        for value in (0, 4, 121, -1, True, "30", 30.5, None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_process_inventory_timeout(value)

    def test_inventory_uses_configured_deadline_and_propagates_timeout(self):
        native = object.__new__(NativeWindows)
        native.process_inventory_timeout_seconds = 60
        with patch("windows_process.subprocess.run", return_value=Mock(stdout="[101]")) as run:
            self.assertEqual(native.session_pids("a"*32), {101})
            self.assertEqual(run.call_args.kwargs["timeout"], 60)
        with patch("windows_process.subprocess.run", side_effect=subprocess.TimeoutExpired("qa", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                native.session_pids("a"*32)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.sid = "S-1-5-21-test"
        self.session = "a" * 32
        self.supervisor = self.record(101)
        self.gateway = self.record(102)
        self.engine = self.record(103)
        self.state = {"session":self.session,"state":"READY","supervisor":self.supervisor,
                      "gateway":self.gateway,"engines":[self.engine]}
        self.native = Mock()
        self.native.same.side_effect = NativeWindows.same
        self.native.mutex.return_value = nullcontext()
        self.native.process.return_value = nullcontext("own")
        self.native.identity.return_value = {"owner_sid":self.sid}
        self.native.record_state.return_value = "gone"
        self.native.recover_job.return_value = True
        self.native.session_pids.return_value = set()
        self.native.listeners.return_value = []
        self.native.terminate_record.return_value = True
        self.spec = runner.RunnerSpec("slot3",8002,"kat","cpu",instance_id=self.session)

    def record(self,pid):
        return {"pid":pid,"created_filetime":123,"owner_sid":self.sid,"exe":"test.exe"}

    def run_recovery(self):
        with runner.configured(self.spec), patch.object(runner,"read_state",return_value=self.state), \
             patch.object(runner,"file_lock",return_value=nullcontext()), \
             patch.object(runner,"paths",return_value={"state":"dummy.json"}), \
             patch.object(runner,"write_json") as write:
            result=runner.recover_orphan(self.native,self.session)
            return result,write

    def test_dead_session_releases_only_after_all_checks(self):
        ok,write=self.run_recovery()
        self.assertTrue(ok)
        self.assertTrue(write.call_args.args[1]["job_cleanup_confirmed"])
        self.assertEqual(write.call_args.args[1]["state"],"STOPPED")
        self.native.terminate_record.assert_not_called()

    def test_unknown_supervisor_quarantined(self):
        self.native.record_state.return_value="unknown"
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_live_supervisor_never_touched(self):
        self.native.record_state.return_value="alive"
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_unknown_child_quarantined(self):
        self.native.record_state.side_effect=lambda r:"unknown" if r==self.engine else "gone"
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_unrecorded_session_process_blocks_release(self):
        self.native.session_pids.return_value={888}
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.terminate_record.assert_not_called()

    def test_foreign_port_blocks_release(self):
        self.native.listeners.return_value=[{"port":8002,"pid":999}]
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()

    def test_wrong_job_name_never_opened(self):
        self.state["job_name"]="unrelated"
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_job_cleanup_pending_blocks_release(self):
        self.native.recover_job.return_value=False
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()

    def test_recorded_orphan_terminated_only_with_session_marker(self):
        living={103}
        self.native.record_state.side_effect=lambda r:"alive" if r["pid"] in living else "gone"
        self.native.session_pids.side_effect=lambda _:set(living)
        self.native.terminate_record.side_effect=lambda r:(living.remove(r["pid"]) is None)
        ok,write=self.run_recovery()
        self.assertTrue(ok);write.assert_called_once()
        self.native.terminate_record.assert_called_once_with(self.engine)

    def test_recorded_orphan_without_session_marker_quarantined(self):
        self.native.record_state.side_effect=lambda r:"alive" if r==self.engine else "gone"
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.terminate_record.assert_not_called()

    def test_owner_mismatch_blocks_cleanup(self):
        self.state["gateway"]={**self.gateway,"owner_sid":"different"}
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_missing_state_keeps_reservation(self):
        self.state=None
        ok,write=self.run_recovery()
        self.assertFalse(ok);write.assert_not_called()
        self.native.recover_job.assert_not_called()

    def test_backend_reports_recovered_after_verified_cleanup(self):
        with patch.object(runner,"run",return_value={**self.state,"state":"STALE","supervisor_verified":False}), \
             patch.object(runner,"recover_orphan",return_value=True), \
             patch.object(runner,"NativeWindows",return_value=self.native) as native:
            status=ColibriBackend(process_inventory_timeout_seconds=60).recover_status(self.spec,self.session)
        native.assert_called_once_with(process_inventory_timeout_seconds=60)
        self.assertEqual(status,{"state":"STOPPED","released":True,"reason":"orphan_recovered"})

    def test_backend_retains_quarantine_on_recovery_exception(self):
        with patch.object(runner,"run",return_value={**self.state,"state":"STALE","supervisor_verified":False}), \
             patch.object(runner,"recover_orphan",side_effect=RuntimeError("access denied")), \
             patch.object(runner,"NativeWindows",return_value=self.native):
            status=ColibriBackend().recover_status(self.spec,self.session)
        self.assertFalse(status["released"])
        self.assertEqual(status["reason"],"recovery_unverified")


class WatchdogRegistryTests(unittest.TestCase):
    def test_reconciliation_without_http_client_releases_dead_slot_only(self):
        case=admission.AdmissionTests()
        case.setUp()
        try:
            a=case.start(slot_id="slot2")
            b=case.start(slot_id="slot3")
            case.settle()
            case.backend.states[a["instance_id"]]={"state":"STOPPED","released":True,"reason":"orphan_recovered"}
            case.core.watchdog_once()
            with case.core.db() as db:
                rows={r["instance_id"]:r for r in case.core._rows(db)}
            self.assertTrue(rows[a["instance_id"]]["released"])
            self.assertEqual(rows[b["instance_id"]]["state"],"READY")
            self.assertFalse(rows[b["instance_id"]]["released"])
            self.assertEqual(case.start(slot_id="slot2")["slot_id"],"slot2")
        finally:
            case.doCleanups()


@unittest.skipUnless(os.name=="nt","Windows only")
class NativeRecoveryTests(unittest.TestCase):
    def test_job_recovery_never_touches_neighbor_and_requires_anchor(self):
        native=NativeWindows()
        name1="Local\\ULQA-"+uuid.uuid4().hex
        name2="Local\\ULQA-"+uuid.uuid4().hex
        a=native.job(name1,None);b=native.job(name2,None)
        handles=[]
        directory=tempfile.TemporaryDirectory()
        folder=directory.name
        try:
            with open(Path(folder)/"out","wb") as out,open(Path(folder)/"err","wb") as err:
                    session=uuid.uuid4().hex
                    cmd=[sys.executable,"-B","-c","import time;time.sleep(120)",session]
                    persisted=[]
                    hp,r=native.spawn_contained(cmd,os.environ.copy(),folder,out,err,a,before_resume=persisted.append)
                    handles.append(hp)
                    hp2,r2=native.spawn_contained(cmd,os.environ.copy(),folder,out,err,b)
                    handles.append(hp2)
                    self.assertEqual(persisted,[r])
                    self.assertEqual(native.record_state(r),"alive")
                    self.assertEqual(native.record_state({**r,"created_filetime":r["created_filetime"]-1}),"gone")
                    self.assertIn(r["pid"],native.session_pids(session))
                    with self.assertRaises(WindowsError):
                        native.terminate_record({**r,"created_filetime":r["created_filetime"]-1})
                    self.assertTrue(native.alive(hp))
                    with self.assertRaises(WindowsError):
                        native.recover_job(name1,[r2])
                    self.assertTrue(native.alive(hp))
                    self.assertTrue(native.alive(hp2))
                    native.recover_job(name1,[r])
                    self.assertEqual(native.k.WaitForSingleObject(hp,5000),0)
                    self.assertEqual(native.record_state(r),"gone")
                    self.assertTrue(native.alive(hp2))
        finally:
            native.close(a);native.close(b)
            for h in handles:
                native.k.WaitForSingleObject(h,5000)
                native.close(h)
            directory.cleanup()


if __name__=="__main__":
    unittest.main()
