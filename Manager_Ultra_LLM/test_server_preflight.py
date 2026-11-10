"""0D first server checkpoint: offline tests, all OS/network/config I/O mocked."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
from unittest import TestCase, main
from unittest.mock import MagicMock, patch
import urllib.error

from manager_core import SERVER
import server_preflight as preflight
from server_runner import main as cli


def machine_row(**changes):
    return dict(host=SERVER, total_gib=47.94, free_gib=35.37,
                listeners=[{"address": "127.0.0.1", "port": 8000, "pid": 138268}],
                processes=[{"pid": 138268, "name": "python.exe"}], **changes)


class InspectionTests(TestCase):
    def test_home_host_refused_before_process_config_or_http_calls(self):
        with patch.object(preflight.socket, "gethostname", return_value="DESKTOP-SC96D3U"), \
             patch.object(preflight.subprocess, "run") as query, \
             patch.object(preflight, "selected_configuration") as config, \
             patch.object(preflight, "probe_api") as http:
            with self.assertRaisesRegex(preflight.PreflightError, "Wrong execution host"):
                preflight.inspect_server()
            query.assert_not_called()
            config.assert_not_called()
            http.assert_not_called()

    def test_environment_computername_cannot_bypass_host_guard(self):
        with patch.dict(preflight.os.environ, {"COMPUTERNAME": SERVER}), \
             patch.object(preflight.socket, "gethostname", return_value="HOME"):
            with self.assertRaises(preflight.PreflightError):
                preflight.require_local_server()

    def test_server_with_wrong_script_location_rejected(self):
        with patch.object(preflight.socket, "gethostname", return_value=SERVER), \
             patch.object(preflight.Path, "is_dir", return_value=True), \
             patch.object(preflight.Path, "is_relative_to", return_value=False):
            with self.assertRaisesRegex(preflight.PreflightError, "server-local"):
                preflight.require_local_server()

    def test_read_only_inventory_bypasses_old_ram_admission(self):
        completed = subprocess.CompletedProcess([], 0, json.dumps(machine_row()), "")
        with patch.object(preflight, "require_local_server"), \
             patch.object(preflight.subprocess, "run", return_value=completed) as query, \
             patch.object(preflight, "selected_configuration", return_value={"state": "MISSING_OR_INVALID"}), \
             patch.object(preflight, "runtime_inventory", return_value={"state": "UNKNOWN"}), \
             patch.object(preflight, "model_inventory", return_value=[]), \
             patch.object(preflight, "probe_api", return_value={"health": "ok"}), \
             patch("server_runner.DryRunRunner") as dry_run:
            result = preflight.inspect_server()
        self.assertEqual(result["state"], "READ_ONLY_PREFLIGHT")
        self.assertTrue(result["server_execution_verified"])
        self.assertFalse(result["launch_performed"])
        self.assertFalse(result["stop_performed"])
        self.assertEqual(result["machine"]["free_gib"], 35.37)
        dry_run.assert_not_called()
        args, kwargs = query.call_args
        self.assertEqual(args[0][-1], preflight.INSTALLATION_QUERY)
        self.assertNotIn("shell", kwargs)
        self.assertTrue(kwargs["check"])

    def test_failed_os_query_has_no_fallback(self):
        with patch.object(preflight, "require_local_server"), \
             patch.object(preflight.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("powershell", 30)), \
             patch.object(preflight, "probe_api") as http:
            with self.assertRaises(preflight.PreflightError):
                preflight.inspect_server()
            http.assert_not_called()

    def test_invalid_inventory_and_wrong_hostname_rejected(self):
        for value in ("not JSON", "[]", "{}", json.dumps({"host": "HOME"})):
            with self.subTest(value=value), \
                 patch.object(preflight, "require_local_server"), \
                 patch.object(preflight.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], 0, value, "")):
                with self.assertRaises(preflight.PreflightError):
                    preflight.inspect_server()

    def test_configuration_redacts_env_args_keys_and_unexpected_nested_fields(self):
        cfg = {"engine": r"C:\runtime\qwen36.exe", "launcher": r"C:\Colibri\c\coli",
               "host": "127.0.0.1", "port": 8000, "backend": "cuda",
               "env": {"COLI_API_KEY": "SECRET"}, "api_key": "SECRET",
               "args": ["--api-key", "SECRET"], "model_dir": {"key": "SECRET"}}
        with patch.object(preflight, "read_json", return_value=cfg):
            result = preflight.selected_configuration(Path(r"C:\setup.json"))
        text = json.dumps(result)
        self.assertNotIn("SECRET", text)
        self.assertNotIn("env", result)
        self.assertNotIn("args", result)
        self.assertEqual(result["port"], 8000)
        self.assertIsNone(result["model_dir"])

    def test_invalid_configuration_is_reported_without_writes(self):
        with patch.object(preflight, "read_json", return_value=None):
            self.assertEqual(preflight.selected_configuration(Path("setup.json"))["state"],
                             "MISSING_OR_INVALID")

    def test_profiles_are_data_only_and_never_import_controller(self):
        controller = MagicMock()
        controller.read_text.return_value = (
            "raise RuntimeError('MUST NOT EXECUTE')\n"
            "PROFILES = {'kat': {'folder': 'KAT'}}\n")
        self.assertEqual(preflight.read_profiles(controller), {"kat": {"folder": "KAT"}})

    def test_nonliteral_profiles_never_evaluated(self):
        controller = MagicMock()
        controller.read_text.return_value = "PROFILES = dangerous_function()\n"
        self.assertEqual(preflight.read_profiles(controller), {})

    def test_missing_profiles_report_unknown_models(self):
        with patch.object(preflight, "read_profiles", return_value={}):
            result = preflight.model_inventory()
        self.assertEqual({row["key"] for row in result}, {"kat", "qwen36"})
        self.assertTrue(all(row["state"] == "PROFILE_UNAVAILABLE" for row in result))

    def test_profile_traversal_refused(self):
        with patch.object(preflight, "read_profiles",
                          return_value={"kat": {"folder": "..\\..\\outside"}}):
            result = preflight.model_inventory()
        self.assertEqual(result[0]["state"], "INVALID_PROFILE_PATH")

    def test_unknown_runtime_does_not_guess_a_home_engine(self):
        self.assertEqual(preflight.runtime_inventory({}), {"state": "UNKNOWN"})
        self.assertEqual(preflight.runtime_inventory({"engine": "qwen36.exe"})["state"],
                         "INVALID_ENGINE_PATH")

    def test_http_only_loopback_gets_and_no_proxy_or_credentials(self):
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.side_effect = [
            b'{"status":"ok","secret":"DO_NOT_EXPORT"}',
            b'{"data":[{"id":"qwen36","secret":"DO_NOT_EXPORT"}]}',
        ]
        with patch.object(preflight.urllib.request, "build_opener", return_value=opener) as build:
            result = preflight.probe_api(8000)
        self.assertEqual(result["model_ids"], ["qwen36"])
        self.assertEqual(result["health"], "ok")
        self.assertNotIn("DO_NOT_EXPORT", json.dumps(result))
        calls = opener.open.call_args_list
        self.assertEqual([call.args[0] for call in calls],
                         ["http://127.0.0.1:8000/health", "http://127.0.0.1:8000/v1/models"])
        self.assertTrue(all(len(call.args) == 1 and call.kwargs == {"timeout": 3} for call in calls))
        self.assertEqual(build.call_args.args[0].proxies, {})
        self.assertIsInstance(build.call_args.args[1], preflight.NoRedirect)

    def test_http_auth_failure_is_diagnostic_no_key_guessing(self):
        opener = MagicMock()
        opener.open.side_effect = urllib.error.HTTPError("loopback", 401, "auth", {}, None)
        with patch.object(preflight.urllib.request, "build_opener", return_value=opener):
            result = preflight.probe_api(8000)
        self.assertEqual(result["/health"], "HTTP_401")
        self.assertEqual(result["/v1/models"], "HTTP_401")

    def test_http_wrong_port_and_redirect_refused(self):
        for value in (80, "8000", True, 8002):
            with self.assertRaises(preflight.PreflightError):
                preflight.probe_api(value)
        self.assertIsNone(preflight.NoRedirect().redirect_request(
            None, None, 302, "redirect", {}, "https://example.com"))

    def test_new_cli_mode_does_not_instantiate_simulator(self):
        output = io.StringIO()
        with patch.object(preflight, "inspect_server",
                          return_value={"state": "READ_ONLY_PREFLIGHT"}) as inspect, \
             patch("server_runner.DryRunRunner") as dry_run, redirect_stdout(output):
            self.assertEqual(cli(["--inspect-server"]), 0)
        inspect.assert_called_once_with()
        dry_run.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["state"], "READ_ONLY_PREFLIGHT")

    def test_inspection_cannot_be_combined_with_synthetic_demo(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit):
                cli(["--inspect-server", "--demo"])

    def test_cli_guard_returns_blocked(self):
        output = io.StringIO()
        with patch.object(preflight, "inspect_server", side_effect=preflight.PreflightError("wrong host")), \
             redirect_stdout(output):
            self.assertEqual(cli(["--inspect-server"]), 2)
        self.assertEqual(json.loads(output.getvalue())["state"], "BLOCKED")


if __name__ == "__main__":
    main()
