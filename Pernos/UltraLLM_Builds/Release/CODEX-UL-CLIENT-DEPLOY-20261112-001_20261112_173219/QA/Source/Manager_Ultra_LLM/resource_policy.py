"""Model-specific estimates and explicit warnings, separate from hard OS gates."""
import math
import time


def read_vram():
    """Read GPU 0 from the installed OS utility; never install or accept a path."""
    import os
    import subprocess
    from pathlib import Path
    executable=Path(os.environ.get("SystemRoot",r"C:\Windows"))/"System32"/"nvidia-smi.exe"
    if not executable.is_file():return None
    try:
        result=subprocess.run([str(executable),"--id=0","--query-gpu=memory.total,memory.used,memory.free",
            "--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=5,check=True,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        total,used,free=map(float,result.stdout.strip().split(','))
        if all(number(x) for x in (total,used,free)) and total>0 and used+free<=total+2:
            return {"free_gib":free/1024,"total_gib":total/1024}
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return None


def number(value):
    return type(value) in (int,float) and math.isfinite(value) and value >= 0


def validate_settings(config):
    settings=config.get("control",{}).get("resources",{})
    if type(settings) is not dict or set(settings)-{"ram_warning_gib","admission_drift_gib","allow_risk_ack"}:
        raise ValueError("invalid_resource_policy")
    if not number(settings.get("ram_warning_gib",10)) or not number(settings.get("admission_drift_gib",1)) or type(settings.get("allow_risk_ack",False)) is not bool:
        raise ValueError("invalid_resource_policy")
    ports=config.get("control",{}).get("slot_port_range",[8001,8999])
    if type(ports) is not list or len(ports)!=2 or any(type(p) is not int for p in ports) or not 1024<=ports[0]<=ports[1]<=65535:
        raise ValueError("invalid_slot_port_range")
    return settings


def assess(config, review, mode, telemetry, reservations):
    if (telemetry.get("verified") is not True or not number(telemetry.get("free_gib"))
            or not number(telemetry.get("sampled")) or not 0 <= time.monotonic()-telemetry["sampled"] <= 5
            or type(telemetry.get("ports")) is not list):
        raise ValueError("resource_telemetry_unknown")
    settings = validate_settings(config)
    threshold = settings.get("ram_warning_gib",10)
    drift=settings.get("admission_drift_gib",1)
    if not number(threshold) or not number(drift) or type(settings.get("allow_risk_ack",False)) is not bool:
        raise ValueError("invalid_resource_policy")
    ram = review.get("ram_gib")
    if ram is not None and (not number(ram) or ram <= 0):
        raise ValueError("invalid_resource_estimate")
    # READY allocations already reduce physical free memory. Only pending or
    # unverified claims are subtracted, avoiding a second charge for one job.
    pending=[r for r in reservations if r.get("state")!="READY"]
    reserved = sum(r.get("ram_gib") or 0 for r in pending)
    remaining = None if ram is None else telemetry["free_gib"]-reserved-ram
    warnings=[]
    if ram is None:
        warnings.append("ram_estimate_unknown")
    elif review.get("evidence") != "measured":
        warnings.append("ram_estimate_unmeasured")
    if telemetry["free_gib"] < threshold or (remaining is not None and remaining < threshold):
        warnings.append("low_ram_forecast")
    vram = review.get("vram_gib") if mode == "cuda" else 0
    vram_reserved = sum(r.get("vram_gib") or 0 for r in pending)
    vram_free = telemetry.get("vram_free_gib")
    if mode == "cuda":
        if not number(vram_free):
            raise ValueError("vram_telemetry_unknown")
        if review.get("evidence") != "measured" or not number(vram) or vram <= 0:
            raise ValueError("cuda_measurement_unverified")
        if vram_free-vram_reserved < vram:
            raise ValueError("insufficient_vram")
    job_cap=review.get("job_limit_gib")
    if job_cap is not None and (not number(job_cap) or job_cap<=0):
        raise ValueError("invalid_job_limit")
    if job_cap is not None and ram is not None and job_cap<ram:
        warnings.append("job_cap_below_estimate")
    public={"ram_free_gib":telemetry["free_gib"],"ram_reserved_gib":reserved,"ram_estimate_gib":ram,
        "ram_after_gib":remaining,"ram_warning_gib":threshold,"estimate_evidence":review.get("evidence","unknown"),
        "vram_free_gib":vram_free if mode=="cuda" else None,"vram_reserved_gib":vram_reserved,
        "vram_estimate_gib":vram,"vram_after_gib":vram_free-vram_reserved-vram if mode=="cuda" else None,
        "job_limit_gib":job_cap}
    launch={"ram_gib":ram,"vram_gib":vram,"job_limit_gib":job_cap,"ram_warning_gib":threshold,
            "min_free_at_start_gib":max(0,telemetry["free_gib"]-drift)}
    return {"forecast":public,"warnings":warnings,"policy":launch,
            "risk_ack_allowed":settings.get("allow_risk_ack",False) is True,
            "requires_ack":bool(warnings)}
