"""Multi-GPU P0: synthetic inventories and trusted launch plan, no GPU access."""
import unittest
from cuda_profile import DEFAULT_PROFILE, normalize, resolve_placement, placement_launch
from resource_policy import parse_gpu_inventory

A="GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
B="GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
C="GPU-cccccccc-cccc-cccc-cccc-cccccccccccc"
D="GPU-dddddddd-dddd-dddd-dddd-dddddddddddd"
E="GPU-eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

def inventory():
    return parse_gpu_inventory(
        f"1, {A}, RTX 4070 Ti SUPER, 0000:02:00.0, 8.9, 16384, 1024, 15360, 5\n"
        f"0, {B}, RTX 3070, 0000:01:00.0, 8.6, 8192, 1024, 7168, 2\n"
        f"2, {C}, RTX 2070, 0000:03:00.0, 7.5, 8192, 0, 8192, N/A")

def profile(mode, ids=None, budget=11):
    return {**DEFAULT_PROFILE,"gpu_mode":mode,"gpu_ids":ids or [],"budget_gib":budget}

class MultiGpuTests(unittest.TestCase):
    def test_legacy_profile_stays_exact(self):
        self.assertEqual(normalize(DEFAULT_PROFILE),DEFAULT_PROFILE)

    def test_auto_chooses_free_not_smi_ordinal(self):
        self.assertEqual(resolve_placement(profile("auto"),inventory(),[])["gpu_ids"],[A])
        self.assertEqual(resolve_placement(profile("auto"),inventory(),[A])["gpu_ids"],[B])

    def test_full_uses_supported_unreserved_devices(self):
        plan=resolve_placement(profile("full"),inventory(),[])
        self.assertEqual(plan["gpu_ids"],[A,B])
        self.assertEqual(plan["total_gib"],24)
        self.assertEqual(plan["free_gib"],22)
        self.assertEqual(plan["weight_capacity_hint_gib"],18)
        self.assertEqual(resolve_placement(profile("full"),inventory(),[A])["gpu_ids"],[B])
        self.assertTrue(resolve_placement(profile("full",budget=23),inventory(),[])["budget_exceeds_hint"])

    def test_manual_groups_and_isolation(self):
        devices=inventory()+[
            {"uuid":D,"total_gib":8,"free_gib":7,"compute_capability":"8.6"},
            {"uuid":E,"total_gib":8,"free_gib":7,"compute_capability":"8.6"}]
        first=resolve_placement(profile("manual",[B,A]),devices,[])
        second=resolve_placement(profile("manual",[D,E]),devices,first["gpu_ids"])
        self.assertEqual(second["gpu_ids"],[D,E])
        self.assertEqual(placement_launch(first["gpu_ids"]),("0,1",{"CUDA_VISIBLE_DEVICES":B+","+A}))
        with self.assertRaisesRegex(ValueError,"gpu_selection_reserved"):
            resolve_placement(profile("manual",[A,D]),devices,first["gpu_ids"])

    def test_unknown_incompatible_and_no_silent_fallback(self):
        for bad in (None,[],[{}]):
            with self.assertRaises(ValueError):resolve_placement(profile("full"),bad,[])
        with self.assertRaisesRegex(ValueError,"gpu_selection_unavailable"):
            resolve_placement(profile("manual",[C]),inventory(),[])
        with self.assertRaisesRegex(ValueError,"gpu_legacy_assignment_unknown"):
            resolve_placement(profile("full"),inventory(),[],legacy_active=True)
        with self.assertRaisesRegex(ValueError,"gpu_selection_unavailable"):
            resolve_placement(profile("auto"),inventory(),[A,B])

    def test_invalid_profiles_and_inventory(self):
        for p in (profile("manual"),profile("full",[A]),profile("manual",[A,A]),profile("manual",["0"]),profile("manual",["GPU-foo,1"])):
            with self.assertRaises(ValueError):normalize(p)
        for raw in ("", "bad", f"0,{A},x,b,8.6,1,1,2,0"):
            with self.assertRaises(ValueError):parse_gpu_inventory(raw)

if __name__=="__main__":unittest.main()
