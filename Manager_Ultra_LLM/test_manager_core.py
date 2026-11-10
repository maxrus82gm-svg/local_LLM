"""Offline unit tests: no model, process, network, or server runtime actions."""
import concurrent.futures
from dataclasses import replace
import unittest

from manager_core import (
    Denied, Estimate, Identity, MockRegistry, Principal, SLOTS, Snapshot,
    State, planned_paths, same_process
)

A = Principal("alice")
B = Principal("bob")
ADMIN = Principal("admin", is_admin=True)

def snap(ram=48, external_cuda=0, verified=True, fresh=True):
    return Snapshot(ram, external_cuda, verified, fresh)

def registry(peak=4):
    return MockRegistry({
        ("kat", "cpu"): Estimate(peak, validated=True),
        ("qwen36", "cpu"): Estimate(peak, validated=True),
        ("kat", "cuda"): Estimate(peak, validated=True),
        ("qwen36", "cuda"): Estimate(peak, validated=True),
    })

def ident(slot="slot2", pid=333, born=100, gateway=222, gateway_born=90,
          exe=r"C:\Runtime\qwen36.exe", port=8001,
          home=r"C:\Manager\slot2"):
    return Identity(pid, born, exe, gateway, gateway_born, slot, port, home)


class RegistryTests(unittest.TestCase):
    def test_default_slots_and_legacy_protected(self):
        self.assertEqual([s.name for s in SLOTS], ["Colibri", "Colibri2", "Colibri3 CUDA"])
        r = registry()
        with self.assertRaises(Denied):
            r.reserve("slot1", A, "kat", "cpu", snap())
        self.assertEqual(r.view("slot1").state, State.OFF)

    def test_reservation_and_release(self):
        r = registry()
        token = r.reserve("slot2", A, "kat", "cpu", snap())
        self.assertEqual(r.view("slot2").owner, "alice")
        self.assertEqual(r.view("slot2").state, State.RESERVED)
        r.cancel_reservation("slot2", A, token)
        self.assertEqual(r.view("slot2").state, State.OFF)

    def test_no_other_user_release(self):
        r = registry()
        token = r.reserve("slot2", A, "kat", "cpu", snap())
        with self.assertRaises(Denied):
            r.cancel_reservation("slot2", B, token)
        self.assertEqual(r.view("slot2").owner, "alice")

    def test_admin_can_release_mock_claim(self):
        r = registry()
        token = r.reserve("slot2", A, "kat", "cpu", snap())
        r.cancel_reservation("slot2", ADMIN, token)
        self.assertEqual(r.view("slot2").state, State.OFF)

    def test_bad_token_and_lease_replay(self):
        r = registry()
        token = r.reserve("slot2", A, "kat", "cpu", snap())
        with self.assertRaises(Denied):
            r.cancel_reservation("slot2", A, "another-token")
        r.cancel_reservation("slot2", A, token)
        with self.assertRaises(Denied):
            r.cancel_reservation("slot2", A, token)

    def test_simultaneous_claims_atomic(self):
        r = registry()
        def compete(i):
            try:
                return r.reserve("slot2", Principal("user" + str(i)), "kat", "cpu", snap())
            except Denied:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            outcomes = list(ex.map(compete, range(64)))
        self.assertEqual(sum(bool(x) for x in outcomes), 1)

    def test_second_slot_does_not_mutate_first(self):
        r = registry()
        original = r.view("slot1")
        t = r.reserve("slot2", A, "kat", "cpu", snap())
        self.assertEqual(r.view("slot1"), original)
        r.cancel_reservation("slot2", A, t)
        self.assertEqual(r.view("slot1"), original)

    def test_ram_9_9_refused(self):
        with self.assertRaises(Denied):
            registry(0.1).reserve("slot2", A, "kat", "cpu", snap(9.9))

    def test_ram_10_1_refused_if_peak_exceeds(self):
        with self.assertRaises(Denied):
            registry(0.2).reserve("slot2", A, "kat", "cpu", snap(10.1))

    def test_ram_exact_safe_boundary_accepted(self):
        r = registry(4)
        self.assertTrue(r.reserve("slot2", A, "kat", "cpu", snap(14)))

    def test_aggregate_reservation_ram(self):
        r = registry(15)
        r.reserve("slot2", A, "kat", "cpu", snap(38))
        with self.assertRaises(Denied):
            r.reserve("slot3", B, "kat", "cpu", snap(38))
        self.assertEqual(r.view("slot3").state, State.OFF)

    def test_external_cuda_already_running(self):
        with self.assertRaises(Denied):
            registry().reserve("slot3", A, "qwen36", "cuda", snap(48, external_cuda=1))

    def test_one_cuda_in_registry(self):
        r = registry()
        r.reserve("slot2", A, "kat", "cuda", snap())
        with self.assertRaises(Denied):
            r.reserve("slot3", B, "qwen36", "cuda", snap())
        self.assertEqual(r.view("slot3").state, State.OFF)

    def test_cpu_allowed_with_external_cuda_if_ram_safe(self):
        r = registry()
        self.assertTrue(r.reserve("slot2", A, "kat", "cpu", snap(48, external_cuda=1)))

    def test_stale_unverified_or_wrong_host_denied(self):
        r = registry()
        for s in (snap(48, verified=False), snap(48, fresh=False),
                  replace(snap(), host="HOME-PC")):
            with self.subTest(s=s):
                with self.assertRaises(Denied):
                    r.reserve("slot2", A, "kat", "cpu", s)

    def test_no_approved_profile_denied(self):
        r = MockRegistry()
        with self.assertRaises(Denied):
            r.reserve("slot2", A, "kat", "cpu", snap())
        r2 = MockRegistry({("kat", "cpu"): Estimate(3, validated=False)})
        with self.assertRaises(Denied):
            r2.reserve("slot2", A, "kat", "cpu", snap())

    def test_invalid_peak_and_telemetry_denied(self):
        for peak in (0, -1, float("nan"), float("inf")):
            with self.subTest(peak=peak):
                with self.assertRaises(Denied):
                    registry(peak).reserve("slot2", A, "kat", "cpu", snap())
        with self.assertRaises(Denied):
            registry().reserve("slot2", A, "kat", "cpu", snap(float("nan")))

    def test_invalid_identity_and_profile_denied(self):
        for slot, profile, backend in (
            ("missing", "kat", "cpu"), ("slot2", "unknown", "cpu"),
            ("slot2", "kat", "vulkan")
        ):
            with self.subTest(slot=slot, profile=profile):
                with self.assertRaises(Denied):
                    registry().reserve(slot, A, profile, backend, snap())

    def test_owner_required(self):
        with self.assertRaises(Denied):
            registry().reserve("slot2", Principal(""), "kat", "cpu", snap())

    def test_live_actions_never_implemented(self):
        with self.assertRaisesRegex(Denied, "simulation only"):
            registry().deny_live_action("STOP", "slot1")

    def test_plan_paths_no_collision_or_duplicate_weight_path(self):
        a, b = planned_paths(SLOTS[1]), planned_paths(SLOTS[2])
        self.assertEqual(a["shared_weights_ro"], b["shared_weights_ro"])
        for k in a:
            if k != "shared_weights_ro":
                self.assertNotEqual(a[k].lower(), b[k].lower(), k)
        self.assertIn("slot2", a["setup_home"])
        with self.assertRaises(Denied):
            planned_paths(SLOTS[0])


class ProcessIdentityTests(unittest.TestCase):
    def test_exact_identity(self):
        self.assertTrue(same_process(ident(), ident(), SLOTS[1]))

    def test_same_executable_different_slot_is_not_owner(self):
        self.assertFalse(same_process(ident(), ident(slot="slot3", port=8002), SLOTS[1]))

    def test_pid_reuse_refused(self):
        self.assertFalse(same_process(ident(), ident(born=101), SLOTS[1]))

    def test_gateway_parent_reuse_refused(self):
        self.assertFalse(same_process(ident(), ident(gateway_born=92), SLOTS[1]))
        self.assertFalse(same_process(ident(), ident(gateway=999), SLOTS[1]))

    def test_changed_port_or_setup_home_refused(self):
        self.assertFalse(same_process(ident(), ident(port=8002), SLOTS[1]))
        self.assertFalse(same_process(ident(), ident(home=r"C:\Manager\slot3"), SLOTS[1]))

    def test_wrong_path_refused(self):
        self.assertFalse(same_process(ident(), ident(exe=r"C:\Other\qwen36.exe"), SLOTS[1]))

    def test_case_insensitive_windows_normalization(self):
        x = ident()
        y = ident(exe=r"c:\runtime\QWEN36.exe", home=r"c:\manager\SLOT2")
        self.assertTrue(same_process(x, y, SLOTS[1]))

    def test_missing_observation_fail_closed(self):
        self.assertFalse(same_process(ident(), None, SLOTS[1]))


class StaticPanelTests(unittest.TestCase):
    def test_panel_does_not_contain_live_execution(self):
        from pathlib import Path
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn("UL-MGR-0A / МАКЕТ", html)
        self.assertIn("127.0.0.1:8000", html)
        self.assertIn("Colibri2", html)
        self.assertIn("Colibri3 CUDA", html)
        for forbidden in ("<iframe", "<form", "fetch(", "XMLHttpRequest", "WebSocket",
                          "EventSource(", "subprocess", "TerminateProcess"):
            self.assertNotIn(forbidden, html)

    def test_only_language_controls_enabled(self):
        from html.parser import HTMLParser
        from pathlib import Path

        class Controls(HTMLParser):
            def __init__(self):
                super().__init__()
                self.controls = []
            def handle_starttag(self, tag, attrs):
                if tag in ("button", "select"):
                    self.controls.append((tag, dict(attrs)))
        p = Controls()
        p.feed(Path(__file__).with_name("index.html").read_text(encoding="utf-8"))
        self.assertGreater(len(p.controls), 2)
        locale_buttons = [attrs for tag,attrs in p.controls if attrs.get("id") in
                          ("locale-ru","locale-en")]
        self.assertEqual(len(locale_buttons), 2)
        self.assertTrue(all("disabled" not in a for a in locale_buttons))
        self.assertTrue(all("disabled" in a for tag,a in p.controls
                            if a.get("id") not in ("locale-ru","locale-en")))

    def test_russian_default_and_switch_persistence(self):
        from pathlib import Path
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ru">', html)
        self.assertIn('const DEFAULT_LANGUAGE = "ru";', html)
        self.assertIn('document.documentElement.lang = selected;', html)
        self.assertIn('localStorage.getItem(LOCALE_STORAGE_KEY)', html)
        self.assertIn('localStorage.setItem(LOCALE_STORAGE_KEY, selected)', html)
        self.assertIn('id="locale-ru"', html)
        self.assertIn('id="locale-en"', html)

    def test_translation_catalogue_complete_and_unique(self):
        from pathlib import Path
        import json
        import re
        html = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
        matched = re.search(r"const TRANSLATIONS = (\[\[.*?\]\]);", html, re.S)
        self.assertIsNotNone(matched)
        rows = json.loads(matched.group(1))
        self.assertGreaterEqual(len(rows), 55)
        self.assertEqual(len(rows), len({ru for ru,en in rows}))
        for ru,en in rows:
            self.assertTrue(ru and en)
            # Source text or attribute must exist in static Russian HTML.
            self.assertIn(re.sub(r"\s+", " ", ru),
                          re.sub(r"\s+", " ", html[:matched.start()]))


if __name__ == "__main__":
    unittest.main()
