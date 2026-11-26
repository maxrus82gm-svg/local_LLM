"""Typed, server-owned CUDA placement settings. Not an OS VRAM quota.

For the qualified qwen36 runner the numeric CUDA_EXPERT_GB allowance covers
trunk and experts; additional CUDA buffers and the optional KV mirror are
separate. No arbitrary environment variables may cross the HTTP boundary.
"""
import math
import re

DEFAULT_PROFILE = {"budget_gib": None, "chain": False, "rows": None, "target_gib": None}


def number(value):
    return type(value) in (int, float) and 0 < value <= 1024 and math.isfinite(value)


def normalize(profile):
    base = set(DEFAULT_PROFILE)
    explicit = base | {"gpu_mode", "gpu_ids"}
    if type(profile) is not dict or set(profile) not in (base, explicit, explicit | {"gpu_reserves_gib"}):
        raise ValueError("invalid_cuda_profile")
    budget, target, chain, rows = (profile[k] for k in ("budget_gib", "target_gib", "chain", "rows"))
    if ((target is not None and not number(target)) or
            (budget is not None and not number(budget)) or
            type(chain) is not bool or
            (rows is not None and (type(rows) is not int or not 1 <= rows <= 8192))):
        raise ValueError("invalid_cuda_profile")
    normalized = {"budget_gib": None if budget is None else float(budget),
                  "chain": chain, "rows": rows, "target_gib": None if target is None else float(target)}
    if "gpu_mode" in profile:
        mode = profile["gpu_mode"]
        ids = validate_gpu_ids(profile["gpu_ids"], allow_empty=True)
        restricted = "gpu_reserves_gib" in profile
        if mode not in ("auto", "full", "manual") or (not restricted and (mode == "manual") != bool(ids)):
            raise ValueError("invalid_cuda_profile")
        normalized.update(gpu_mode=mode, gpu_ids=ids)
        if restricted:
            values = profile["gpu_reserves_gib"]
            if not ids or type(values) is not dict:
                raise ValueError("invalid_cuda_profile")
            keys = validate_gpu_ids(list(values))
            if set(keys) != set(ids) or any(type(v) not in (int, float) or not math.isfinite(v)
                                            or not 0 <= v <= 1024 for v in values.values()):
                raise ValueError("invalid_cuda_profile")
            normalized["gpu_reserves_gib"] = dict(sorted(zip(keys, map(float, values.values()))))
    return normalized


def launch_values(profile):
    profile = normalize(profile)
    argv = [] if profile["budget_gib"] is None else ["--vram", str(profile["budget_gib"])]
    env = {"COLI_CUDA_CHAIN": "1" if profile["chain"] else "0"}
    if profile["rows"] is not None and profile["chain"]:
        env["COLI_CUDA_CHAIN_ROWS"] = str(profile["rows"])
    return argv, env


_GPU_UUID = re.compile(r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\Z")
# A reviewed stock Windows 2.1.0 CUDA package supports sm_80 and newer.
# Hardware eligibility is not evidence that the specific runtime works.
HEADROOM_GIB = 2.0


def validate_gpu_ids(ids, *, allow_empty=False):
    if (type(ids) is not list or (not ids and not allow_empty) or len(ids) > 64
            or any(type(i) is not str or not _GPU_UUID.fullmatch(i) for i in ids)):
        raise ValueError("invalid_gpu_ids")
    result = ["GPU-" + i[4:].lower() for i in ids]
    if len(set(result)) != len(result):
        raise ValueError("invalid_gpu_ids")
    return result


def eligible_devices(devices):
    if type(devices) is not list or not devices:
        raise ValueError("gpu_inventory_unknown")
    ids = validate_gpu_ids([d.get("uuid") if type(d) is dict else None for d in devices])
    result = {}
    for uuid, d in zip(ids, devices):
        total, free = d.get("total_gib"), d.get("free_gib")
        cap = d.get("compute_capability")
        if (type(total) not in (int, float) or not math.isfinite(total) or total <= 0
                or type(free) not in (int, float) or not math.isfinite(free) or not 0 <= free <= total
                or type(cap) is not str or not re.fullmatch(r"[0-9]{1,2}\.[0-9]{1,2}", cap)):
            raise ValueError("gpu_inventory_unknown")
        if int(cap.split(".")[0]) >= 8:
            result[uuid] = d
    return result


def resolve_placement(profile, devices, occupied, *, legacy_active=False, pinned_ids=None, defer_reserve=False):
    """Exclusive managed-device selection. No driver allocation or process IO.
    
    A legacy unmasked process has no verified GPU identity: do not guess.
    Free memory is advisory, not a quota. External processes are not reserved.
    """
    profile = normalize(profile)
    if "gpu_mode" not in profile:
        raise ValueError("gpu_selection_required")
    if legacy_active:
        raise ValueError("gpu_legacy_assignment_unknown")
    eligible = eligible_devices(devices)
    occupied = set(occupied)
    free = {i: d for i, d in eligible.items() if i not in occupied}
    mode = profile["gpu_mode"]
    restricted = "gpu_reserves_gib" in profile
    if restricted:
        allowed = profile["gpu_ids"]
        if any(i not in eligible for i in allowed):
            raise ValueError("gpu_selection_unavailable")
        if any(profile["gpu_reserves_gib"][i] >= eligible[i]["total_gib"] for i in allowed):
            raise ValueError("gpu_reserve_invalid")
    if pinned_ids is not None:
        ids = validate_gpu_ids(pinned_ids)
        if any(i not in eligible for i in ids):
            raise ValueError("gpu_selection_unavailable")
        if any(i in occupied for i in ids):
            raise ValueError("gpu_selection_reserved")
        if mode == "auto" and len(ids) != 1:
            raise ValueError("gpu_selection_unavailable")
        if restricted and any(i not in allowed for i in ids):
            raise ValueError("gpu_selection_unavailable")
        if (mode == "manual" or restricted and mode == "full") and ids != profile["gpu_ids"]:
            raise ValueError("gpu_selection_unavailable")
    elif restricted:
        if mode in ("full", "manual"):
            if any(i in occupied for i in allowed):
                raise ValueError("gpu_selection_reserved")
            ids = allowed
        else:
            ids = sorted((i for i in allowed if i in free),
                         key=lambda i: (-max(0, free[i]["free_gib"] - profile["gpu_reserves_gib"][i]),
                                        -free[i]["total_gib"], i))[:1]
            if not ids:
                raise ValueError("gpu_selection_unavailable")
    elif mode == "manual":
        ids = profile["gpu_ids"]
        if any(i not in eligible for i in ids):
            raise ValueError("gpu_selection_unavailable")
        if any(i in occupied for i in ids):
            raise ValueError("gpu_selection_reserved")
    else:
        # Prefer available memory, then capacity, then stable identity.
        ids = sorted(free, key=lambda i: (-free[i]["free_gib"], -free[i]["total_gib"], i))
        if mode == "auto":
            ids = ids[:1]
        if not ids:
            raise ValueError("gpu_selection_unavailable")
    total = sum(eligible[i]["total_gib"] for i in ids)
    available = sum(eligible[i]["free_gib"] for i in ids)
    headroom = sum(max(0, eligible[i]["free_gib"] - HEADROOM_GIB) for i in ids)
    result = {"gpu_ids": ids, "total_gib": total, "free_gib": available,
              "weight_capacity_hint_gib": headroom,
              "budget_exceeds_hint": profile["budget_gib"] is not None and profile["budget_gib"] > headroom}
    if restricted:
        if defer_reserve:
            # A running instance still owns its VRAM. Never fabricate memory
            # released by that instance or approve a launch based on it.
            if any(eligible[i]["total_gib"] - profile["gpu_reserves_gib"][i] - HEADROOM_GIB < 0.1 for i in ids):
                raise ValueError("gpu_reserve_insufficient")
            result["gpu_reserve_enforcement"] = "recheck_after_confirmed_release"
        else:
            result.update(reserve_plan(profile, eligible, ids))
            result["budget_exceeds_hint"] = (profile["budget_gib"] is not None and
                                             profile["budget_gib"] > result["gpu_weight_cap_gib"])
    return result


def reserve_plan(profile, eligible, ids):
    """Conservative common numeric weight cap, not an OS allocation limit.

    Stock Colibri paths interpret the numeric budget differently (group vs
    device). Never pass the sum of asymmetric budgets as a per-device cap.
    Reserve is additional currently-free memory; fixed headroom is extra.
    The engine's auxiliary allocations and external processes remain unbounded.
    """
    profile = normalize(profile)
    reserves = profile["gpu_reserves_gib"]
    if not ids or any(i not in reserves or i not in eligible for i in ids):
        raise ValueError("gpu_selection_unavailable")
    details = []
    for i in ids:
        d = eligible[i]
        reserve = reserves[i]
        if reserve >= d["total_gib"]:
            raise ValueError("gpu_reserve_invalid")
        capacity = max(0.0, d["free_gib"] - reserve - HEADROOM_GIB)
        details.append({"uuid": i, "reserve_gib": reserve,
                        "free_gib": d["free_gib"], "weight_capacity_gib": capacity})
    common = min(d["weight_capacity_gib"] for d in details)
    requested = profile["budget_gib"]
    cap = math.floor(min(common, requested if requested is not None else common) * 10) / 10
    if cap < 0.1:
        raise ValueError("gpu_reserve_insufficient")
    return {"gpu_weight_cap_gib": cap, "gpu_reserve_details": details,
            "weight_capacity_hint_gib": sum(d["weight_capacity_gib"] for d in details),
            "gpu_reserve_enforcement": "conservative_weight_cap_not_os_quota"}


def placement_launch(ids):
    """Mask by physical UUID; Colibri receives ordinals relative to the mask."""
    ids = validate_gpu_ids(ids)
    return ",".join(str(i) for i in range(len(ids))), {"CUDA_VISIBLE_DEVICES": ",".join(ids)}
