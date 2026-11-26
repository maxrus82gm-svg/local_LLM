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
    if type(profile) is not dict or set(profile) not in (set(DEFAULT_PROFILE), set(DEFAULT_PROFILE)|{"gpu_mode","gpu_ids"}):
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
        if mode not in ("auto", "full", "manual") or (mode == "manual") != bool(ids):
            raise ValueError("invalid_cuda_profile")
        normalized.update(gpu_mode=mode, gpu_ids=ids)
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


def resolve_placement(profile, devices, occupied, *, legacy_active=False):
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
    if mode == "manual":
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
    return {"gpu_ids": ids, "total_gib": total, "free_gib": available,
            "weight_capacity_hint_gib": headroom,
            "budget_exceeds_hint": profile["budget_gib"] is not None and profile["budget_gib"] > headroom}


def placement_launch(ids):
    """Mask by physical UUID; Colibri receives ordinals relative to the mask."""
    ids = validate_gpu_ids(ids)
    return ",".join(str(i) for i in range(len(ids))), {"CUDA_VISIBLE_DEVICES": ",".join(ids)}
