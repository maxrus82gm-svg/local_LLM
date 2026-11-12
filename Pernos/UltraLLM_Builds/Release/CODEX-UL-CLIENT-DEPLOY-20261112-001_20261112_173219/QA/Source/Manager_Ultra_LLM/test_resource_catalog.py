"""UL-MGR-0B offline tests: no server or real model access."""
from dataclasses import replace
import concurrent.futures
import math
import unittest

from resource_catalog import (
    HostPolicy, HostTelemetry, ModelChoice, RamRange, RangeEvidence,
    ResourceDenied, ResourcePlanner, initial_catalogue,
)


def telemetry(*, free=48, external_cuda=0, host="DESKTOP-KT4G5SM",
              verified=True, fresh=True):
    return HostTelemetry(host, free, verified, fresh, external_cuda)


def planner(protected=20, min_free=10):
    return ResourcePlanner(HostPolicy(protected_non_llm_gib=protected,
                                      min_free_after_gib=min_free), initial_catalogue())


def reserve(r, slot="slot2", model="kat", backend="cpu", owner="alice", t=None):
    return r.reserve_simulated(slot_id=slot, model_key=model, backend=backend,
                               owner=owner, telemetry=t or telemetry())


class CatalogueTests(unittest.TestCase):
    def test_two_candidate_models_have_initial_budget_not_measurement(self):
        choices = initial_catalogue()
        self.assertEqual(set(choices), {"kat", "qwen36"})
        for choice in choices.values():
            self.assertEqual(choice.budget_gib, 10)
            self.assertEqual(choice.expected_ram.evidence, RangeEvidence.OWNER_HYPOTHESIS)
            self.assertEqual((choice.expected_ram.min_gib, choice.expected_ram.max_gib), (5, 10))
            self.assertIsNone(choice.measured_peak_gib)
            self.assertFalse(choice.live_approved)

    def test_unknown_range_supported_for_new_model(self):
        new = ModelChoice("future", "Future model", "colibri", "future", 10,
                          RamRange(None, None, RangeEvidence.UNKNOWN), "unverified")
        r = planner()
        r.add_choice(new)
        self.assertIn("future", [item.key for item in r.catalogue()])

    def test_generic_engine_adapter_future_expansion(self):
        new = ModelChoice("other", "New runtime", "future_engine", "other", 10,
                          RamRange(None, None, RangeEvidence.UNKNOWN), "future")
        r = planner(protected=10)
        r.add_choice(new)
        reserve(r, "slot4", "other")
        self.assertEqual(r.plan_launch("slot4")["engine_adapter"], "future_engine")
        with self.assertRaises(ResourceDenied):
            r.plan_launch("slot4", requested_kv_slots=2)

    def test_duplicate_rejected(self):
        r = planner()
        with self.assertRaises(ResourceDenied):
            r.add_choice(initial_catalogue()["kat"])

    def test_invalid_ram_ranges_rejected(self):
        with self.assertRaises(ValueError):
            RamRange(-1, 2, RangeEvidence.OWNER_HYPOTHESIS)
        with self.assertRaises(ValueError):
            RamRange(10, 5, RangeEvidence.OWNER_HYPOTHESIS)
        with self.assertRaises(ValueError):
            RamRange(5, None, RangeEvidence.MEASURED)
        with self.assertRaises(ValueError):
            RamRange(None, None, RangeEvidence.MEASURED)
        with self.assertRaises(ValueError):
            RamRange(5, 10, RangeEvidence.UNKNOWN)
        with self.assertRaises(ValueError):
            RamRange(1, float("inf"), RangeEvidence.MEASURED)

    def test_cannot_claim_live_approved_without_measured_peak(self):
        source = initial_catalogue()["kat"]
        with self.assertRaises(ValueError):
            replace(source, live_approved=True)

    def test_invalid_budget_rejected(self):
        base = initial_catalogue()["kat"]
        for n in (0, -1, float("nan"), float("inf")):
            with self.subTest(value=n):
                with self.assertRaises(ValueError):
                    replace(base, budget_gib=n)


class AdmissionTests(unittest.TestCase):
    def test_48_minus_20_minus_10_yields_18_model_envelope(self):
        r = planner()
        self.assertEqual(r.policy.model_envelope_gib, 18)
        reserve(r)
        with self.assertRaisesRegex(ResourceDenied, "reserved server envelope"):
            reserve(r, "slot3", "qwen36", owner="bob")
        self.assertEqual(len(r.reservations()), 1)

    def test_lower_protected_budget_allows_two_models_not_three(self):
        r = planner(protected=10, min_free=10)
        reserve(r)
        reserve(r, "slot3", "qwen36", owner="bob")
        with self.assertRaises(ResourceDenied):
            reserve(r, "slot4", "kat", owner="carl")
        self.assertEqual(len(r.reservations()), 2)

    def test_game_and_headroom_protection_are_independent(self):
        p = HostPolicy(total_gib=48, protected_non_llm_gib=20, min_free_after_gib=10)
        self.assertEqual(p.model_envelope_gib, 18)
        with self.assertRaises(ValueError):
            HostPolicy(total_gib=48, protected_non_llm_gib=40, min_free_after_gib=10)

    def test_unknown_server_ram_fails_closed(self):
        for t in (
            telemetry(verified=False), telemetry(fresh=False),
            telemetry(host="AGENT-PC"), telemetry(free=float("nan"))
        ):
            with self.subTest(t=t), self.assertRaises(ResourceDenied):
                reserve(planner(), t=t)

    def test_less_than_required_actual_free_rejected(self):
        with self.assertRaisesRegex(ResourceDenied, "Projected free RAM"):
            reserve(planner(), t=telemetry(free=19.9))

    def test_second_cuda_refused(self):
        r = planner(protected=0)
        reserve(r, backend="cuda")
        with self.assertRaisesRegex(ResourceDenied, "CUDA"):
            reserve(r, "slot3", "qwen36", backend="cuda", owner="bob")

    def test_external_cuda_claim_also_refused(self):
        with self.assertRaisesRegex(ResourceDenied, "CUDA"):
            reserve(planner(), backend="cuda", t=telemetry(external_cuda=1))

    def test_foreign_release_forbidden(self):
        r = planner()
        reserve(r)
        with self.assertRaises(ResourceDenied):
            r.release_simulated("slot2", "bob")
        self.assertEqual(len(r.reservations()), 1)

    def test_admin_mock_release(self):
        r = planner()
        reserve(r)
        r.release_simulated("slot2", "admin", admin=True)
        self.assertEqual(len(r.reservations()), 0)

    def test_no_double_claim(self):
        r = planner(protected=0)
        reserve(r)
        with self.assertRaises(ResourceDenied):
            reserve(r, model="qwen36")
        self.assertEqual(len(r.reservations()), 1)

    def test_racing_claims_atomic(self):
        r = planner(protected=0)
        def attempt(n):
            try:
                return reserve(r, owner=f"user{n}")
            except ResourceDenied:
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            results = list(ex.map(attempt, range(64)))
        self.assertEqual(sum(item is not None for item in results), 1)

    def test_plan_never_emits_executable_or_secrets(self):
        r = planner()
        reserve(r)
        planned = r.plan_launch("slot2", requested_kv_slots=2)
        self.assertFalse(planned["live_start_allowed"])
        self.assertEqual(planned["state"], "MOCK_NOT_EXECUTABLE")
        self.assertEqual(planned["reservation_gib"], 10)
        self.assertEqual(planned["estimated_range_gib"], [5, 10])
        self.assertEqual(planned["range_evidence"], "owner_hypothesis")
        self.assertEqual(planned["kv_slots"], 2)
        self.assertFalse(any(word in planned for word in ("command","password","api_key")))

    def test_invalid_kv_slots_refused(self):
        r = planner()
        reserve(r)
        for n in (0, 17, 1.5, True, "2"):
            with self.subTest(n=n), self.assertRaises(ResourceDenied):
                r.plan_launch("slot2", requested_kv_slots=n)

    def test_plan_requires_reservation(self):
        with self.assertRaises(ResourceDenied):
            planner().plan_launch("slot2")


if __name__ == "__main__":
    unittest.main()
