"""Offline control/safety tests. NO model inference and NO server execution."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SOURCE = Path(__file__).resolve().parents[3] / "Colibri" / "ULTRA-CONTROL.py"
spec = importlib.util.spec_from_file_location("ultra_control", SOURCE)
ultra = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ultra)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="ultra control test ")
        self.base = Path(self.temp.name)
        self.home = self.base / "profile" / "colibri"
        self.runtime = self.home / "runtime"
        self.runtime.mkdir(parents=True)
        self.engine = self.runtime / "qwen36.exe"
        self.engine.write_bytes(b"test stub - never execute")
        self.launcher = self.runtime / "coli"
        self.launcher.write_text("# _watch_stop_file serve_stopfile\n", encoding="utf-8")
        self.project = self.base / "project"
        self.model = self.project / "Base_LLM" / "Models" / "Qwen3-Coder-30B-A3B"
        self.model.mkdir(parents=True)
        self.cfg = {"version": 1, "engine": str(self.engine), "launcher": str(self.launcher),
                    "host": "127.0.0.1", "port": 8000, "backend": "cpu", "env": {},
                    "args": ["web", "--model", str(self.model), "--host", "127.0.0.1", "--port", "8000", "--auto-tier"]}
        self.save()
        self.patches = [patch.object(ultra, "PROJECT", self.project),
                        patch.object(ultra, "MODEL", self.model),
                        patch.object(ultra, "SELECTED_PROFILE", "qwen"),
                        patch.object(ultra, "MODEL_ID", ultra.PROFILES["qwen"]["model_id"]),
                        patch.object(ultra, "REPORTS", self.base / "reports")]
        for item in self.patches:
            item.start()

    def tearDown(self):
        for item in reversed(self.patches):
            item.stop()
        self.temp.cleanup()

    def save(self):
        ultra.write_json(self.home / "setup.json", self.cfg)

    def kat_fixture(self):
        ultra.select_profile("kat")
        model = ultra.MODEL
        model.mkdir(parents=True)
        layout = ["full_attention" if i % 4 == 3 else "linear_attention" for i in range(40)]
        ultra.write_json(model / "config.json", {"model_type": "qwen3_5_moe_text", "num_hidden_layers": 40,
            "num_experts": 256, "hidden_size": 2048, "num_experts_per_tok": 8,
            "moe_intermediate_size": 512, "vocab_size": 248320, "layer_types": layout})
        ultra.write_json(model / "qwen36_meta.json", {"model_type": "qwen3_5_moe", "n_layers": 40,
            "num_experts": 256, "hidden": 2048, "topk": 8, "moe_inter": 512,
            "ebits": 4, "expert_gs": 64, "layer_types": layout})
        (model / "tokenizer.json").write_text("{}", encoding="utf-8")
        return model

    def test_kat_wrong_quantization_or_geometry_refused(self):
        model = self.kat_fixture()
        path = model / "qwen36_meta.json"
        original = ultra.read_json(path)
        for key, wrong in (("expert_gs", 0), ("ebits", 8), ("num_experts", 128), ("n_layers", 48)):
            ultra.write_json(path, dict(original, **{key: wrong}))
            with self.assertRaises(ultra.ControlError):
                ultra.inspect_model()

    def test_kat_missing_shard_detected(self):
        self.kat_fixture()
        with self.assertRaises(OSError):
            ultra.inspect_model()

    def test_kat_hybrid_attention_mismatch_detected(self):
        model = self.kat_fixture()
        cfg = ultra.read_json(model / "config.json")
        cfg["layer_types"][0] = "full_attention"
        ultra.write_json(model / "config.json", cfg)
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()

    def test_kat_required_expert_tensors_and_group_scales_checked(self):
        header = {}
        for expert in range(256):
            prefix = f"model.layers.0.mlp.experts.{expert}."
            header[prefix + "merged_weight"] = {"dtype": "U8", "shape": [1572864]}
            header[prefix + "qs"] = {"dtype": "F32", "shape": [49152]}
        ultra.validate_kat_header(header, 0)
        key = "model.layers.0.mlp.experts.255.qs"
        header[key]["shape"] = [1536]
        with self.assertRaises(ultra.ControlError):
            ultra.validate_kat_header(header, 0)
        del header[key]
        with self.assertRaises(ultra.ControlError):
            ultra.validate_kat_header(header, 0)

    def test_kat_selected_profile_cannot_mislabel_qwen(self):
        self.make_shards()
        with patch.object(ultra, "SELECTED_PROFILE", "kat"):
            with self.assertRaises(ultra.ControlError):
                ultra.inspect_model()

    def test_kat_uses_shared_engine_own_model_and_session_without_config_write(self):
        model = self.kat_fixture()
        before = (self.home / "setup.json").read_bytes()
        plan = ultra.plan_run(self.home)
        self.assertEqual(plan["engine"], str(self.engine))
        self.assertEqual(plan["model"], str(model))
        self.assertEqual(plan["model_id"], "kat-coder-v2.5-dev-colibri")
        self.assertEqual((plan["ram_gb"], plan["ctx"], plan["cap"]), (16, 16384, 32))
        self.assertEqual(plan["environment"]["Q36_MTP"], "0")
        self.assertTrue(plan["environment"]["HEAT_FILE"].endswith("kat-heat.bin"))
        self.assertNotIn("--no-think", plan["command"])
        self.assertEqual(plan["environment"]["COLI_THINK"], "1")
        self.assertEqual((self.home / "setup.json").read_bytes(), before)

    def test_reasoning_default_kat_is_on_even_if_saved_args_disable_it(self):
        self.kat_fixture()
        self.cfg["args"].append("--no-think")
        self.save()
        plan = ultra.plan_run(self.home)
        self.assertEqual(plan["environment"]["COLI_THINK"], "1")
        self.assertNotIn("--no-think", plan["command"])
        self.assertNotIn("--think", plan["command"])

    def test_reasoning_coder_has_no_forced_think(self):
        plan = ultra.plan_run(self.home)
        # Qwen3-Coder Instruct has no native <think> block.
        self.assertNotIn("--think", plan["command"])
        self.assertNotIn("--no-think", plan["command"])

    def test_kat_cuda_requires_existing_common_backend(self):
        self.kat_fixture()
        with self.assertRaises(ultra.ControlError):
            ultra.plan_run(self.home, backend="cuda")
        (self.runtime / "coli_cuda.dll").write_bytes(b"test stub - never load")
        plan = ultra.plan_run(self.home, backend="cuda")
        self.assertEqual(plan["environment"]["COLI_CUDA"], "1")
        self.assertNotIn("DSV4_CUDA", plan["environment"])
        self.assertNotIn("COLI_DSV4_DLL", plan["environment"])

    def test_switch_missing_runtime_does_not_stop_active_model(self):
        self.kat_fixture()
        self.engine.unlink()
        with patch.object(ultra, "require_server"), patch.object(ultra, "Windows"), \
             patch.object(ultra, "inspect_model", return_value={}), patch.object(ultra, "stop") as stop, \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ultra.main(["start", "--setup-home", str(self.home), "--model", "kat", "--switch"]), 1)
        stop.assert_not_called()

    def test_stop_selected_kat_follows_actual_qwen_session(self):
        qwen = ultra.plan_run(self.home)
        identity = {"pid": 123, "created_filetime": 456}
        ultra.write_json(ultra.state_file(self.home), {"gateway": identity, "plan": ultra.public_plan(qwen)})
        self.kat_fixture()
        win = Mock(); win.matches.return_value = True
        stopped = ultra.active_stop_plan(self.home, ultra.plan_run(self.home), win)
        self.assertEqual(stopped["profile"], "qwen")
        self.assertEqual(stopped["model"], str(self.model))

    def test_last_profile_legacy_kat_and_retired_deepseek(self):
        ultra.write_json(ultra.state_file(self.home), {"plan": {"model": str(self.model)}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen")
        ultra.write_json(ultra.state_file(self.home), {"plan": {"profile": "kat"}})
        self.assertEqual(ultra.previous_profile(self.home), "kat")
        ultra.write_json(ultra.state_file(self.home), {"plan": {"profile": "deepseek"}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen")
        self.assertNotIn("deepseek", ultra.PROFILES)

    def test_kat_profile_is_passed_to_background_supervisor(self):
        self.kat_fixture()
        args = type("Args", (), dict(ram=16, ctx=16384, cap=32, backend=None))()
        current = {"colibri_processes": [], "health": {}, "memory": {"available_gib": 40, "total_gib": 48}}
        win = Mock(); win.identity.return_value = {"pid": 777, "created_filetime": 888}
        with patch.object(ultra, "snapshot", return_value=current), patch.object(ultra.socket, "socket"), \
             patch.object(ultra, "inspect_model", return_value={"name": ultra.PROFILES["kat"]["name"], "shards": 41}), \
             patch.object(ultra.subprocess, "Popen") as spawn, contextlib.redirect_stdout(io.StringIO()):
            ultra.prepare_start(args, self.home, win)
        command = spawn.call_args.args[0]
        self.assertEqual(command[command.index("--model") + 1], "kat")
        self.assertEqual(ultra.read_json(self.home / "ultra" / "request.json")["profile"], "kat")

    def test_supervisor_profile_mismatch_never_launches(self):
        ultra.write_json(self.home / "ultra" / "request.json", {"session": "fixture", "profile": "kat"})
        with patch.object(ultra.subprocess, "Popen") as spawn:
            with self.assertRaises(ultra.ControlError):
                ultra.supervise(type("Args", (), {"session": "fixture"})(), self.home, Mock())
        spawn.assert_not_called()

    def test_selected_api_model_id_used_in_stream_request(self):
        response = Mock(status=200)
        response.readline.side_effect = [b'data: {"choices":[{"delta":{"content":"OK"}}],"usage":{"completion_tokens":1}}\n', b'data: [DONE]\n']
        connection = Mock(); connection.getresponse.return_value = response
        model_id = ultra.PROFILES["kat"]["model_id"]
        with patch.object(ultra.http.client, "HTTPConnection", return_value=connection):
            ultra.stream_turn({"base_url": "http://127.0.0.1:8000", "model_id": model_id}, [])
        self.assertEqual(json.loads(connection.request.call_args.args[2])["model"], model_id)

    def test_snapshot_does_not_call_other_active_model_ready(self):
        self.kat_fixture()
        plan = ultra.plan_run(self.home)
        with patch.object(ultra, "processes", return_value=[]), \
             patch.object(ultra, "api", side_effect=[{"status": "ok"}, {"data": [{"id": ultra.PROFILES["qwen"]["model_id"]}]}]), \
             patch.object(ultra, "memory", return_value={}), patch.object(ultra, "gpu_status", return_value={}):
            self.assertEqual(ultra.snapshot(plan, Mock())["status"], "different_model_ready")

    @unittest.skipUnless(os.name == "nt", "Windows PowerShell process-filter check")
    def test_other_model_engine_is_detected_even_with_hidden_path(self):
        prefix = r'''
function Get-CimInstance {
 param($ClassName)
 [pscustomobject]@{ProcessId=101;ParentProcessId=1;ExecutablePath=([IO.Path]::Combine([IO.Path]::GetDirectoryName($env:ULTRA_ENGINE),'deepseek_v4.exe'));Name='deepseek_v4.exe';CommandLine='';WorkingSetSize=1;PrivatePageCount=1}
 [pscustomobject]@{ProcessId=102;ParentProcessId=1;ExecutablePath=$null;Name='deepseek_v4.exe';CommandLine='';WorkingSetSize=1;PrivatePageCount=1}
 [pscustomobject]@{ProcessId=103;ParentProcessId=1;ExecutablePath='C:\Unrelated\python.exe';Name='python.exe';CommandLine='python independent.py';WorkingSetSize=1;PrivatePageCount=1}
}
'''
        win = Mock(); win.identity.side_effect = lambda pid: {"pid": pid, "created_filetime": pid + 10}
        with patch.object(ultra, "PROCESS_SCRIPT", prefix + ultra.PROCESS_SCRIPT):
            rows = ultra.processes(ultra.plan_run(self.home), win)
        self.assertEqual({r["pid"]: r["kind"] for r in rows},
                         {101: "other_model_engine", 102: "other_model_engine_unverified_path"})

    def test_launch_is_existing_serve_without_setup_or_rebuild(self):
        before = (self.home / "setup.json").read_bytes()
        plan = ultra.plan_run(self.home)
        self.assertEqual(plan["command"][2], "serve")
        self.assertFalse(set(("setup", "start", "build", "install")).intersection(plan["command"]))
        self.assertNotIn("--auto-tier", plan["command"])
        self.assertIn("--no-tune-profile", plan["command"])
        self.assertEqual(plan["environment"]["SNAP"], str(self.model))
        self.assertEqual(plan["environment"]["COLI_ENGINE"], str(self.engine))
        self.assertEqual((self.home / "setup.json").read_bytes(), before)

    def test_credentials_not_in_command_or_public_plan(self):
        self.cfg["args"] += ["--api-key", "test-only-private-value"]
        self.save()
        plan = ultra.plan_run(self.home)
        self.assertEqual(plan["environment"]["COLI_API_KEY"], "test-only-private-value")
        self.assertNotIn("test-only-private-value", json.dumps(plan["command"]))
        self.assertNotIn("test-only-private-value", json.dumps(ultra.public_plan(plan)))

    def test_cuda_and_cpu_are_explicit_no_silent_fallback(self):
        plan = ultra.plan_run(self.home, backend="cuda")
        self.assertEqual(plan["environment"]["COLI_CUDA"], "1")
        self.assertEqual(plan["environment"]["COLI_VULKAN"], "0")
        self.assertEqual(plan["command"][-2:], ["--gpu", "auto"])
        self.assertEqual(ultra.plan_run(self.home)["command"][-2:], ["--gpu", "none"])

    def test_missing_runtime_fails_without_install(self):
        self.engine.unlink()
        with self.assertRaises(ultra.ControlError):
            ultra.plan_run(self.home)

    def test_unknown_launcher_protocol_refused(self):
        self.launcher.write_text("# old launcher", encoding="utf-8")
        with self.assertRaises(ultra.ControlError):
            ultra.plan_run(self.home)

    def test_config_cannot_call_setup(self):
        self.cfg["args"][0] = "setup"
        self.save()
        with self.assertRaises(ultra.ControlError):
            ultra.plan_run(self.home)

    def test_lan_without_key_refused(self):
        self.cfg["host"] = "0.0.0.0"
        self.save()
        with self.assertRaises(ultra.ControlError):
            ultra.plan_run(self.home)

    def test_limits_checked(self):
        for values in ({"ram": 0}, {"ctx": 262144}, {"cap": 129}):
            with self.assertRaises(ultra.ControlError):
                ultra.plan_run(self.home, **values)

    def test_wrong_host_guard(self):
        with patch.dict(os.environ, {"COMPUTERNAME": "HOME-TEST"}):
            with self.assertRaises(ultra.ControlError):
                ultra.require_server()

    def make_shards(self):
        (self.model / "config.json").write_text(json.dumps({"model_type": "qwen3_moe",
            "num_hidden_layers": 48, "num_experts": 128, "hidden_size": 2048}), encoding="utf-8")
        (self.model / "qwen36_meta.json").write_text(json.dumps({"model_type": "qwen3_moe",
            "n_layers": 48, "num_experts": 128}), encoding="utf-8")
        (self.model / "tokenizer.json").write_text("{}", encoding="utf-8")
        for name in [f"model-{i:05d}.safetensors" for i in range(48)] + ["model-globals.safetensors"]:
            header = json.dumps({"fixture": {"dtype": "I8", "shape": [1], "data_offsets": [0, 1]}}).encode()
            (self.model / name).write_bytes(struct.pack("<Q", len(header)) + header + b"\x00")

    def test_all_49_weight_headers_and_bounds(self):
        self.make_shards()
        result = ultra.inspect_model(self.model)
        self.assertEqual(result["shards"], 49)
        self.assertEqual(result["tensor_headers_checked"], 49)

    def test_missing_weight_shard_detected(self):
        self.make_shards()
        (self.model / "model-00031.safetensors").unlink()
        with self.assertRaises(OSError):
            ultra.inspect_model(self.model)

    def test_truncated_weight_data_detected(self):
        self.make_shards()
        path = self.model / "model-00012.safetensors"
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model(self.model)

    def test_wrong_model_cannot_be_renamed_to_coder(self):
        self.make_shards()
        cfg = json.loads((self.model / "config.json").read_text())
        cfg["num_experts"] = 256
        (self.model / "config.json").write_text(json.dumps(cfg))
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model(self.model)

    def test_stop_request_checks_pidfile(self):
        win = Mock()
        win.matches.return_value = True
        record = {"pid": 123, "created_filetime": 4}
        pidfile = self.base / "coli-serve-8000.pid"
        with patch.object(ultra.tempfile, "gettempdir", return_value=str(self.base)):
            pidfile.write_text("456 different-model\n")
            self.assertFalse(ultra.request_gateway_stop({"port": 8000}, record, win))
            self.assertFalse(pidfile.with_suffix(".stop").exists())
            pidfile.write_text("123 model\n")
            self.assertTrue(ultra.request_gateway_stop({"port": 8000}, record, win))
            self.assertTrue(pidfile.with_suffix(".stop").exists())

    def test_stop_does_not_kill_unowned_engine_by_default(self):
        args = type("Args", (), dict(ram=12, ctx=4096, cap=32, backend=None, force_orphans=False))()
        win = Mock()
        rows = [{"pid": 123, "ppid": 456, "kind": "engine", "path": str(self.engine)}]
        with patch.object(ultra, "processes", return_value=rows), \
             patch.object(ultra, "snapshot", return_value={"health": {}}), \
             patch.object(ultra, "export_status"), patch.object(ultra, "print_status"):
            with self.assertRaises(ultra.ControlError):
                ultra.stop(args, self.home, win)
        win.terminate.assert_not_called()

    def test_api_rejects_other_service_on_same_port(self):
        class Handler(BaseHTTPRequestHandler):
            server_version = "unrelated-service"
            def do_GET(self):
                self.send_response(200); self.end_headers(); self.wfile.write(b'{"status":"ok"}')
            def log_message(self, *_): pass
        with self.http_server(Handler) as port:
            result = ultra.api({"base_url": f"http://127.0.0.1:{port}"}, "/health")
            self.assertIn("non-Colibri", result["error"])

    @contextlib.contextmanager
    def http_server(self, handler):
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_port
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=5)

    def test_two_sequential_mock_streams_with_exact_usage(self):
        requests = []
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                requests.append(data)
                events = [{"choices": [{"delta": {"content": "mock response"}}]},
                          {"choices": [], "usage": {"completion_tokens": 2, "prompt_tokens": 4}}, "[DONE]"]
                payload = "".join("data: " + (x if isinstance(x, str) else json.dumps(x)) + "\n\n" for x in events).encode()
                self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *_): pass
        with self.http_server(Handler) as port:
            plan = {"base_url": f"http://127.0.0.1:{port}"}
            messages = [{"role": "user", "content": "mock turn one"}]
            one = ultra.stream_turn(plan, messages)
            messages += [{"role": "assistant", "content": one["text"]}, {"role": "user", "content": "mock turn two"}]
            two = ultra.stream_turn(plan, messages)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(requests[1]["messages"]), 3)
        self.assertEqual(one["completion_tokens"], 2)
        self.assertEqual(two["completion_tokens"], 2)
        self.assertTrue(one["stream_finished"] and two["stream_finished"])

    def test_generation_without_usage_refused(self):
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                payload = b'data: {"choices":[{"delta":{"content":"not measured"}}]}\n\ndata: [DONE]\n\n'
                self.send_response(200); self.send_header("Content-Length", str(len(payload))); self.end_headers()
                self.wfile.write(payload)
            def log_message(self, *_): pass
        with self.http_server(Handler) as port:
            with self.assertRaises(ultra.ControlError):
                ultra.stream_turn({"base_url": f"http://127.0.0.1:{port}"}, [])

    def test_credential_redaction(self):
        self.assertNotIn("test-secret", ultra.clean("Authorization: Bearer test-secret"))
        self.assertNotIn("test-secret", ultra.clean("api_key=test-secret"))
        self.assertNotIn("test-secret", ultra.clean('{"api_key": "test-secret"}'))

    def test_start_wait_does_not_hold_stop_lock(self):
        args = type("Args", (), dict(wait=3))()
        session = "fixture-session"
        ultra.write_json(ultra.state_file(self.home), {"session": session, "status": "loading"})
        process = Mock(pid=123)
        process.poll.return_value = None
        plan = {"fixture": True}
        status = {"models": {"data": [{"id": ultra.MODEL_ID}]},
                  "managed_gateway_verified": True, "engine_process_count": 1}
        def ready(*_):
            with ultra.lifecycle_lock(self.home):
                return {"status": "ok"}
        with patch.object(ultra, "prepare_start", return_value=(process, session, plan)), \
             patch.object(ultra, "api", side_effect=ready), \
             patch.object(ultra, "snapshot", return_value=status), \
             patch.object(ultra, "export_status"), patch.object(ultra, "print_status"):
            self.assertEqual(ultra.start(args, self.home, Mock()), 0)

    def test_benchmark_refuses_unverified_engine_before_any_generation(self):
        status = {"status": "ready", "models": {"data": [{"id": ultra.MODEL_ID}]},
                  "colibri_processes": []}
        with patch.object(ultra, "snapshot", return_value=status), \
             patch.object(ultra, "stream_turn") as generation:
            with self.assertRaises(ultra.ControlError):
                ultra.benchmark({}, Mock())
        generation.assert_not_called()

    def test_stop_can_request_shutdown_during_bootstrap(self):
        args = type("Args", (), dict(ram=12, ctx=4096, cap=32, backend=None, force_orphans=False))()
        record = {"pid": 777, "created_filetime": 888}
        ultra.write_json(self.home / "ultra" / "request.json", {"session": "boot", "supervisor": record})
        win = Mock()
        win.matches.side_effect = [True, True, False]
        with patch.object(ultra, "processes", return_value=[]), \
             patch.object(ultra, "snapshot", return_value={"health": {}}), \
             patch.object(ultra, "export_status"), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ultra.stop(args, self.home, win), 0)
        self.assertEqual(ultra.read_json(self.home / "ultra" / "stop.json")["session"], "boot")
        win.terminate.assert_not_called()

    def test_existing_supervisor_wrong_api_model_is_not_success(self):
        args = type("Args", (), dict(ram=12, ctx=4096, cap=32, backend=None))()
        ultra.write_json(ultra.state_file(self.home), {"supervisor": {"pid": 777, "created_filetime": 888}})
        current = {"status": "ready", "models": {"data": [{"id": "other-model"}]}}
        win = Mock()
        win.matches.return_value = True
        with patch.object(ultra, "inspect_model", return_value={}), \
             patch.object(ultra, "snapshot", return_value=current), \
             patch.object(ultra, "export_status"), patch.object(ultra, "print_status"), \
             patch.object(ultra.subprocess, "Popen") as spawn, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ultra.prepare_start(args, self.home, win), 2)
        spawn.assert_not_called()

    def test_shared_supervisor_evidence_redacts_log_credentials(self):
        log = self.base / "engine.log"
        log.write_text('api_key=unit-private-value\n[CUDA] device 0: fixture\n', encoding='utf-8')
        ultra.publish_supervisor({"status": "loading", "log": str(log), "session": "fixture"})
        saved = (ultra.REPORTS / "SUPERVISOR-STATE.json").read_text(encoding='utf-8')
        self.assertNotIn('unit-private-value', saved)
        self.assertIn('[CUDA]', saved)

    def test_gpu_app_report_contains_only_colibri_pids(self):
        gpu = Mock(returncode=0, stdout='0, Test GPU, 1, 8000, 1000, 5', stderr='')
        apps = Mock(returncode=0, stdout='12, qwen36.exe, 500\n34, unrelated.exe, 20\n', stderr='')
        with patch.object(ultra.shutil, 'which', return_value='nvidia-smi'), \
             patch.object(ultra.subprocess, 'run', side_effect=[gpu, apps]):
            result = ultra.gpu_status([12])
        self.assertIn('12, qwen36.exe', result['colibri_compute_apps_csv'])
        self.assertNotIn('unrelated', json.dumps(result))
        self.assertEqual(result['other_process_entries_omitted'], 1)

    def test_unverified_engine_path_blocks_duplicate_start(self):
        args = type('Args', (), dict(ram=12, ctx=4096, cap=32, backend=None))()
        current = {'status': 'loading_or_unresponsive', 'health': {}, 'models': {},
                   'colibri_processes': [{'kind': 'engine_unverified_path', 'pid': 77}]}
        with patch.object(ultra, 'inspect_model', return_value={}), \
             patch.object(ultra, 'snapshot', return_value=current), \
             patch.object(ultra, 'export_status'), patch.object(ultra, 'print_status'), \
             patch.object(ultra.subprocess, 'Popen') as spawn, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ultra.prepare_start(args, self.home, Mock()), 2)
        spawn.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows-specific safety check")
    def test_native_pid_reuse_guard_and_unrelated_python_survives(self):
        children = [subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                    creationflags=subprocess.CREATE_NO_WINDOW) for _ in range(2)]
        try:
            win = ultra.Windows()
            identity = win.identity(children[0].pid)
            self.assertTrue(win.matches(identity))
            stale = dict(identity, created_filetime=identity["created_filetime"] + 1)
            self.assertFalse(win.matches(stale))
            with self.assertRaises(ultra.ControlError):
                win.terminate(stale)
            self.assertIsNone(children[0].poll())
            win.terminate(identity)
            children[0].wait(timeout=5)
            self.assertIsNone(children[1].poll())
        finally:
            for process in children:
                if process.poll() is None:
                    process.terminate()
                process.wait(timeout=5)

    @unittest.skipUnless(os.name == "nt", "Windows-specific local CIM check")
    def test_process_filter_exact_launcher_model_and_port(self):
        plan = ultra.plan_run(self.home)
        child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)",
                str(self.launcher), "serve", "--model", str(self.model), "--port", "8000"],
                creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            rows = ultra.processes(plan, ultra.Windows())
            self.assertIn(child.pid, [r["pid"] for r in rows if r["kind"] == "gateway"])
            plan["port"] = 8001
            rows = ultra.processes(plan, ultra.Windows())
            self.assertNotIn(child.pid, [r["pid"] for r in rows])
            # Qwen and KAT share qwen36.exe. A gateway for the old model must
            # not be mistaken for the new model solely because of its engine.
            plan["port"] = 8000
            plan["model"] = str(self.project / "Base_LLM" / "Models" / "KAT-Coder-V2.5-Dev-Colibri")
            rows = ultra.processes(plan, ultra.Windows())
            self.assertNotIn(child.pid, [r["pid"] for r in rows])
        finally:
            child.terminate(); child.wait(timeout=5)



    def qwen38_fixture(self):
        ultra.select_profile("qwen38")
        model = ultra.MODEL
        model.mkdir(parents=True)
        source = model.parent / "Qwen3.8-27B-UD-Q6_K_M.gguf"
        source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 866, 50))
        layout = ["full_attention" if i % 4 == 3 else "linear_attention" for i in range(64)]
        config = {"model_type": "qwen3_5_text", "num_hidden_layers": 64,
                  "hidden_size": 5120, "num_attention_heads": 24,
                  "num_key_value_heads": 4, "vocab_size": 248320,
                  "intermediate_size": 17408, "layer_types": layout,
                  "colibri_gguf": {"arch": "qwen35", "mode": "link", "source": str(source)}}
        ultra.write_json(model / "config.json", config)
        ultra.write_json(model / "gguf.json", {"format": "colibri-gguf-v1",
              "gguf": str(source), "mode": "link", "arch": "qwen35",
              "parts": 1, "size": 23088409504})
        (model / "tokenizer.json").write_text("{}", encoding="utf-8")
        return model, source

    def test_qwen38_profile_uses_exact_nested_link_and_safe_limits(self):
        model, _ = self.qwen38_fixture()
        self.assertTrue(str(model).endswith("Qwen3.8-27B-UD-Q6_K_M.colibri"))
        (self.runtime / "coli_cuda.dll").write_bytes(b"test stub - never load")
        before = (self.home / "setup.json").read_bytes()
        plan = ultra.plan_run(self.home, backend="cuda")
        self.assertEqual(plan["model"], str(model))
        self.assertEqual(plan["model_id"], "qwen3.8-27b-colibri")
        self.assertEqual((plan["ram_gb"], plan["ctx"], plan["cap"]), (32, 16384, 8))
        self.assertEqual(plan["environment"]["Q36_MTP"], "0")
        self.assertEqual(plan["environment"]["COLI_CUDA"], "1")
        self.assertIn("--no-tune-profile", plan["command"])
        self.assertNotIn("--no-think", plan["command"])
        self.assertEqual((self.home / "setup.json").read_bytes(), before)
        self.assertEqual(ultra.available_profiles(plan)["qwen38"]["model_directory_present"], True)

    def test_qwen38_gguf_verification_and_wrong_source_refused(self):
        model, source = self.qwen38_fixture()
        original_stat = Path.stat
        def synthetic_stat(path, *args, **kwargs):
            if path == source:
                fields = list(original_stat(path, *args, **kwargs))
                fields[6] = 23088409504  # st_size; preserve st_mode for Path.is_file
                return os.stat_result(fields)
            return original_stat(path, *args, **kwargs)
        with patch.object(Path, "stat", synthetic_stat):
            verified = ultra.inspect_model()
        self.assertEqual(verified["shards"], 1)
        self.assertEqual(verified["tensor_count_header"], 866)
        self.assertEqual(verified["check"], "config_link_header_size_only_not_full_tensor_read_or_hash")
        description = ultra.read_json(model / "gguf.json")
        description["gguf"] = str(self.base / "unexpected.gguf")
        ultra.write_json(model / "gguf.json", description)
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()

    def test_qwen38_wrong_geometry_and_missing_weight_refused(self):
        model, source = self.qwen38_fixture()
        cfg = ultra.read_json(model / "config.json")
        cfg["num_hidden_layers"] = 65
        ultra.write_json(model / "config.json", cfg)
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()
        cfg["num_hidden_layers"] = 64
        ultra.write_json(model / "config.json", cfg)
        source.unlink()
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()

    def test_qwen38_invalid_import_never_stops_current_session(self):
        self.qwen38_fixture()
        with patch.object(ultra, "require_server"), patch.object(ultra, "Windows"), \
             patch.object(ultra, "stop") as stop, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ultra.main(["start", "--setup-home", str(self.home),
                                         "--model", "qwen38", "--switch"]), 1)
        stop.assert_not_called()

    def test_previous_profile_recovers_nested_qwen38(self):
        model, _ = self.qwen38_fixture()
        ultra.write_json(ultra.state_file(self.home), {"plan": {"model": str(model)}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen38")
        ultra.write_json(ultra.state_file(self.home), {"plan": {"profile": "qwen38"}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen38")



    def qwen36_fixture(self):
        ultra.select_profile("qwen36")
        model = ultra.MODEL
        model.mkdir(parents=True)
        source = model.parent / "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
        source.write_bytes(struct.pack("<4sIQQ", b"GGUF", 3, 733, 54))
        layout = ["full_attention" if i % 4 == 3 else "linear_attention" for i in range(40)]
        config = {"model_type": "qwen3_5_moe_text", "num_hidden_layers": 40,
                  "num_experts": 256, "hidden_size": 2048, "num_experts_per_tok": 8,
                  "moe_intermediate_size": 512, "vocab_size": 248320,
                  "layer_types": layout,
                  "colibri_gguf": {"arch": "qwen35moe", "mode": "link", "source": str(source)}}
        ultra.write_json(model / "config.json", config)
        ultra.write_json(model / "gguf.json", {"format": "colibri-gguf-v1",
              "gguf": str(source), "mode": "link", "arch": "qwen35moe",
              "parts": 1, "size": 22134528992})
        (model / "tokenizer.json").write_text("{}", encoding="utf-8")
        return model, source

    def test_qwen36_profile_and_api_id_no_setup_mutation(self):
        model, source = self.qwen36_fixture()
        (self.runtime / "coli_cuda.dll").write_bytes(b"stub: test only")
        before = (self.home / "setup.json").read_bytes()
        plan = ultra.plan_run(self.home, backend="cuda")
        self.assertEqual(plan["model"], str(model))
        self.assertEqual(plan["model_id"], "qwen3.6-35b-a3b-colibri")
        self.assertEqual((plan["ram_gb"], plan["ctx"], plan["cap"]), (32, 16384, 8))
        self.assertEqual(plan["environment"]["Q36_MTP"], "0")
        self.assertEqual(plan["environment"]["COLI_THINK"], "1")
        self.assertNotIn("--no-think", plan["command"])
        self.assertEqual(plan["environment"]["COLI_CUDA"], "1")
        self.assertTrue(plan["environment"]["HEAT_FILE"].endswith("qwen36-heat.bin"))
        self.assertIn("--no-tune-profile", plan["command"])
        self.assertEqual((self.home / "setup.json").read_bytes(), before)

    def test_qwen36_inspect_real_geometry_with_mocked_file_size(self):
        model, source = self.qwen36_fixture()
        original_stat = Path.stat
        def synthetic_stat(path, *args, **kwargs):
            result = original_stat(path, *args, **kwargs)
            if path == source:
                fields = list(result)
                fields[6] = 22134528992
                return os.stat_result(fields)
            return result
        with patch.object(Path, "stat", synthetic_stat):
            valid = ultra.inspect_model()
        self.assertEqual(valid["tensor_count_header"], 733)
        self.assertEqual(valid["bytes"], 22134528992)
        self.assertEqual(valid["shards"], 1)

    def test_qwen36_corrupted_source_or_config_is_rejected(self):
        model, source = self.qwen36_fixture()
        descriptor = ultra.read_json(model / "gguf.json")
        descriptor["gguf"] = str(self.base / "another.gguf")
        ultra.write_json(model / "gguf.json", descriptor)
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()
        descriptor["gguf"] = str(source)
        ultra.write_json(model / "gguf.json", descriptor)
        cfg = ultra.read_json(model / "config.json")
        cfg["num_experts"] = 1
        ultra.write_json(model / "config.json", cfg)
        with self.assertRaises(ultra.ControlError):
            ultra.inspect_model()

    def test_qwen36_invalid_import_cannot_stop_active_model(self):
        self.qwen36_fixture()
        with patch.object(ultra, "require_server"), patch.object(ultra, "Windows"), \
             patch.object(ultra, "stop") as stop, contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(ultra.main(["start", "--setup-home", str(self.home),
                                         "--model", "qwen36", "--switch"]), 1)
        stop.assert_not_called()

    def test_qwen36_previous_profile_recovery_without_running(self):
        model, source = self.qwen36_fixture()
        ultra.write_json(ultra.state_file(self.home), {"plan": {"model": str(model)}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen36")
        ultra.write_json(ultra.state_file(self.home), {"plan": {"profile": "qwen36"}})
        self.assertEqual(ultra.previous_profile(self.home), "qwen36")


if __name__ == "__main__":
    unittest.main(verbosity=2)
