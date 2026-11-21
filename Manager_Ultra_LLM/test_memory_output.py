import os
from pathlib import Path
import tempfile
import unittest
import uuid
import sys
from unittest.mock import patch
from windows_process import NativeWindows, WindowsError, read_shared_text
from colibri2_runner import RunnerSpec, configured, paths, command_and_environment
from chat_settings import upstream_options


class OutputPolicyTests(unittest.TestCase):
    def test_default_output_not_pinned_to_test_cap(self):
        for key in ("kat","qwen36"):
            spec=RunnerSpec("slot2",8001,key,"cuda",review={"launch":{"context_tokens":2048,
                            "cache_ram_gib":10,"threads":2,"thinking":False,"load_timeout_seconds":300}})
            with configured(spec):
                cmd,_=command_and_environment({"paths":paths(),"launcher":"launcher","model":"model"})
            self.assertNotIn("--ngen",cmd)
            self.assertEqual(cmd[cmd.index("--ctx")+1],"2048")
        self.assertNotIn("max_tokens",upstream_options())
        self.assertEqual(upstream_options({"max_output_tokens":500})["max_tokens"],500)


@unittest.skipUnless(os.name=="nt","Windows only")
class LiveMemoryPrimitiveTests(unittest.TestCase):
    def test_only_verified_job_memory_and_no_termination(self):
        native=NativeWindows()
        name="Local\\ULQA-memory-"+uuid.uuid4().hex
        other="Local\\ULQA-memory-"+uuid.uuid4().hex
        a=native.job(name,None); b=native.job(other,None)
        handles=[]
        directory=tempfile.TemporaryDirectory()
        folder=directory.name
        try:
            with open(Path(folder)/"out","wb") as out,open(Path(folder)/"err","wb") as err:
                cmd=[sys.executable,"-B","-c","import time;time.sleep(20)"]
                h,r=native.spawn_contained(cmd,os.environ.copy(),folder,out,err,a)
                handles.append(h)
                h2,r2=native.spawn_contained(cmd,os.environ.copy(),folder,out,err,b)
                handles.append(h2)
                data=native.job_memory(name,r)
                self.assertGreater(data["ram_gib"],0)
                self.assertGreater(data["private_commit_gib"],0)
                # Windows Python launchers may themselves create a child.
                members={x["pid"] for x in data["records"]}
                self.assertIn(r["pid"],members)
                self.assertNotIn(r2["pid"],members)
                self.assertEqual(members,set(native.job_pids(a)))
                with self.assertRaises(WindowsError):
                    native.job_memory(name,r2)
                self.assertTrue(native.alive(h)); self.assertTrue(native.alive(h2))
        finally:
            native.close(a);native.close(b)
            for h in handles:
                native.k.WaitForSingleObject(h,5000);native.close(h)
            directory.cleanup()

    def test_shared_snapshot_reader(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/"state.json"
            p.write_text('{"state":"READY"}',encoding="utf-8")
            self.assertEqual(read_shared_text(p),'{"state":"READY"}')
            q=p.with_suffix(".tmp");q.write_text('{"state":"STOPPED"}',encoding="utf-8")
            os.replace(q,p)
            self.assertEqual(read_shared_text(p),'{"state":"STOPPED"}')
