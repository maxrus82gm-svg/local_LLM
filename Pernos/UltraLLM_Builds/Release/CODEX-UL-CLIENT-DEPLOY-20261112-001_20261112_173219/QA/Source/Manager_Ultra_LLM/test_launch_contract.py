"""Independent simulated launch tests. Absolutely no process/network calls."""
from dataclasses import replace
import concurrent.futures
import unittest

from launch_contract import (
    ContractDenied, EngineEvidence, FakeColibriAdapter, InstanceDefinition,
    InstanceRegistry, InstanceState, MockLaunchCoordinator, initial_instances
)
from resource_catalog import HostPolicy, HostTelemetry, ResourcePlanner, ResourceDenied, initial_catalogue

HOST = "DESKTOP-KT4G5SM"
def telemetry(free=48, external_cuda=0):
    return HostTelemetry(HOST, free, True, True, external_cuda)

def make_coordinator(protected=0):
    r = InstanceRegistry(initial_instances())
    p = ResourcePlanner(HostPolicy(protected_non_llm_gib=protected), initial_catalogue())
    return MockLaunchCoordinator(r,p)

def start(c, slot="slot2", model="kat", backend="cpu", owner="alice", t=None):
    return c.start_fake(slot, model_key=model, backend=backend, owner=owner,
                        telemetry=t or telemetry())

class RegistryTests(unittest.TestCase):
    def test_registry_can_add_later_instances(self):
        c = make_coordinator()
        version = c.registry.version
        c.registry.register(InstanceDefinition("slot4", "Fourth model", HOST, 8003))
        self.assertEqual(c.registry.version, version+1)
        c.sync_registry()
        self.assertEqual(c.status("slot4").state, InstanceState.OFF)

    def test_duplicate_id_refused(self):
        r = InstanceRegistry(initial_instances())
        with self.assertRaises(ContractDenied):
            r.register(InstanceDefinition("slot2", "Other", HOST, 9000))

    def test_duplicate_host_port_refused(self):
        r = InstanceRegistry(initial_instances())
        with self.assertRaises(ContractDenied):
            r.register(InstanceDefinition("slot9", "Other", HOST, 8001))

    def test_same_port_on_different_host_allowed(self):
        r = InstanceRegistry(initial_instances())
        r.register(InstanceDefinition("local", "Future local", "PERSONAL-PC", 8001))
        self.assertIn("local", [x.slot_id for x in r.list()])

    def test_invalid_port_refused(self):
        for port in (0, 65536, True):
            with self.assertRaises(ValueError):
                InstanceDefinition("x","new",HOST,port)

    def test_unknown_instance_refused(self):
        with self.assertRaises(ContractDenied):
            make_coordinator().status("missing")


class SimulatorTests(unittest.TestCase):
    def test_fake_ready_never_real_ready(self):
        c = make_coordinator()
        state = start(c)
        self.assertEqual(state.state, InstanceState.READY)
        self.assertTrue(state.simulated)
        self.assertIn("NOT started", state.message)
        self.assertEqual(state.evidence.instance_id, "slot2")
        self.assertEqual(c.events()[-1]["mode"], "SIMULATION")

    def test_fake_stop_returns_off_and_releases(self):
        c = make_coordinator()
        start(c)
        self.assertEqual(c.stop_fake("slot2", owner="alice").state, InstanceState.OFF)
        self.assertEqual(len(c.planner.reservations()), 0)

    def test_original_slot_read_only(self):
        c = make_coordinator()
        with self.assertRaises(ContractDenied):
            start(c, "slot1")
        with self.assertRaises(ContractDenied):
            c.stop_fake("slot1", owner="alice")
        self.assertEqual(c.status("slot1").state, InstanceState.OFF)

    def test_cannot_stop_foreign_user(self):
        c = make_coordinator()
        start(c)
        with self.assertRaisesRegex(ContractDenied, "another user's"):
            c.stop_fake("slot2", owner="bob")
        self.assertEqual(c.status("slot2").state, InstanceState.READY)

    def test_admin_can_stop_fake_only(self):
        c = make_coordinator()
        start(c)
        self.assertEqual(c.stop_fake("slot2", owner="admin", admin=True).state, InstanceState.OFF)

    def test_other_model_independent(self):
        c = make_coordinator()
        a = start(c,"slot2")
        b = start(c,"slot3","qwen36",owner="bob")
        self.assertNotEqual(a.evidence.fake_pid,b.evidence.fake_pid)
        c.stop_fake("slot3",owner="bob")
        self.assertEqual(c.status("slot2").evidence,a.evidence)
        self.assertEqual(c.status("slot2").state,InstanceState.READY)

    def test_capacity_failure_does_not_start(self):
        c = make_coordinator(protected=20)
        start(c)
        with self.assertRaises(ResourceDenied):
            start(c,"slot3","qwen36",owner="bob")
        self.assertIsNone(c.fake.owned("slot3"))
        self.assertEqual(c.status("slot3").state,InstanceState.OFF)

    def test_second_cuda_refused(self):
        c = make_coordinator()
        start(c,backend="cuda")
        with self.assertRaises(ResourceDenied):
            start(c,"slot3","qwen36",backend="cuda",owner="bob")

    def test_wrong_host_refused(self):
        c = make_coordinator()
        c.registry.register(InstanceDefinition("remote", "Remote", "OTHER-PC",9001))
        with self.assertRaisesRegex(ContractDenied,"host"):
            start(c,"remote")

    def test_process_identity_mismatch_prohibits_stop(self):
        c = make_coordinator()
        state = start(c)
        c._statuses["slot2"] = replace(state,evidence=replace(state.evidence, fake_pid=999))
        with self.assertRaisesRegex(ContractDenied,"identity mismatch"):
            c.stop_fake("slot2",owner="alice")
        self.assertIsNotNone(c.fake.owned("slot2"))

    def test_stale_telemetry_refuses(self):
        c = make_coordinator()
        with self.assertRaises(ResourceDenied):
            start(c,t=HostTelemetry(HOST,48,True,False))
        self.assertFalse(c.events())

    def test_invalid_kv_count_rolls_back_mock_reservation(self):
        c = make_coordinator()
        with self.assertRaises(ResourceDenied):
            c.start_fake("slot2",model_key="kat",backend="cpu",
                         owner="alice",telemetry=telemetry(),kv_slots=17)
        self.assertEqual(len(c.planner.reservations()),0)
        self.assertEqual(c.status("slot2").state,InstanceState.OFF)

    def test_concurrent_starts_only_one_wins(self):
        c = make_coordinator()
        def compete(i):
            try:
                return start(c,owner=f"user{i}")
            except (ResourceDenied,ContractDenied):
                return None
        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            attempts = list(ex.map(compete,range(64)))
        self.assertEqual(sum(x is not None for x in attempts),1)

    def test_live_methods_are_inert(self):
        c = make_coordinator()
        with self.assertRaisesRegex(ContractDenied,"NOT IMPLEMENTED"):
            c.live_start("slot2")
        with self.assertRaisesRegex(ContractDenied,"NOT IMPLEMENTED"):
            c.live_stop("slot2")
        self.assertEqual(len(c.planner.reservations()),0)

    def test_event_log_is_only_simulated(self):
        c=make_coordinator()
        start(c)
        c.stop_fake("slot2",owner="alice")
        self.assertEqual([x["action"] for x in c.events()],["START","STOP"])
        self.assertTrue(all(x["mode"]=="SIMULATION" for x in c.events()))
        self.assertTrue(all("pid" not in x for x in c.events()))

    def test_register_new_instance_and_fake_start(self):
        c=make_coordinator()
        c.registry.register(InstanceDefinition("slot4","Colibri4",HOST,8004))
        c.sync_registry()
        status=start(c,"slot4","qwen36")
        self.assertEqual(status.state,InstanceState.READY)


class AdapterOwnershipTests(unittest.TestCase):
    def test_engine_same_fake_pid_but_wrong_ticket_refused(self):
        a=FakeColibriAdapter()
        evidence=a.start_fake(slot_id="slot2",model_key="kat")
        wrong=replace(evidence,ticket="forged")
        with self.assertRaises(ContractDenied):
            a.stop_fake(slot_id="slot2",evidence=wrong)
        self.assertEqual(a.owned("slot2"),evidence)

    def test_foreign_instance_id_not_owner(self):
        a=FakeColibriAdapter()
        evidence=a.start_fake(slot_id="slot2",model_key="kat")
        with self.assertRaises(ContractDenied):
            a.stop_fake(slot_id="slot3",evidence=evidence)
        self.assertEqual(a.owned("slot2"),evidence)


if __name__=="__main__":
    unittest.main()
