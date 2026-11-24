"""Typed, server-owned CUDA placement settings. Not an OS VRAM quota.

For the qualified qwen36 runner the numeric CUDA_EXPERT_GB allowance covers
trunk and experts; additional CUDA buffers and the optional KV mirror are
separate. No arbitrary environment variables may cross the HTTP boundary.
"""
import math

DEFAULT_PROFILE = {"budget_gib": None, "chain": False, "rows": None, "target_gib": None}


def number(value):
    return type(value) in (int, float) and 0 < value <= 1024 and math.isfinite(value)


def normalize(profile):
    if type(profile) is not dict or set(profile) != set(DEFAULT_PROFILE):
        raise ValueError("invalid_cuda_profile")
    budget, target, chain, rows = (profile[k] for k in ("budget_gib", "target_gib", "chain", "rows"))
    if ((target is not None and not number(target)) or
            (budget is not None and not number(budget)) or
            type(chain) is not bool or
            (rows is not None and (type(rows) is not int or not 1 <= rows <= 8192))):
        raise ValueError("invalid_cuda_profile")
    return {"budget_gib": None if budget is None else float(budget),
            "chain": chain, "rows": rows, "target_gib": None if target is None else float(target)}


def launch_values(profile):
    profile = normalize(profile)
    argv = [] if profile["budget_gib"] is None else ["--vram", str(profile["budget_gib"])]
    env = {"COLI_CUDA_CHAIN": "1" if profile["chain"] else "0"}
    if profile["rows"] is not None and profile["chain"]:
        env["COLI_CUDA_CHAIN_ROWS"] = str(profile["rows"])
    return argv, env
