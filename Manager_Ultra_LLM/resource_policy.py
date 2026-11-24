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
            return {"free_gib":free/1024,"total_gib":total/1024,"used_gib":used/1024}
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return None


def process_vram():
    """Return attributed GPU bytes only when NVIDIA supplies numeric PID data."""
    import os
    import subprocess
    from pathlib import Path
    executable=Path(os.environ.get("SystemRoot",r"C:\Windows"))/"System32"/"nvidia-smi.exe"
    if not executable.is_file():
        return {}
    try:
        result=subprocess.run([str(executable),"--query-compute-apps=pid,used_gpu_memory",
            "--format=csv,noheader,nounits"], capture_output=True,text=True,timeout=2,check=True,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        values={}
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            p,m=line.split(",",1)
            pid=int(p.strip())
            try:
                amount=float(m.strip())
                if not number(amount): amount=None
            except ValueError:
                amount=None
            old=values.get(pid,0)
            values[pid]=None if old is None or amount is None else old+amount/1024
        return values
    except (OSError,ValueError,subprocess.SubprocessError):
        return {}


def _pdh_gpu_samples():
    """Read WDDM gauge counters in-process; no shell or caller-supplied path."""
    import ctypes as c
    from ctypes import wintypes as w

    class ValueUnion(c.Union):
        _fields_ = [("long_value", w.LONG), ("double_value", c.c_double),
                    ("large_value", c.c_longlong), ("pointer", c.c_void_p)]

    class Value(c.Structure):
        _fields_ = [("status", w.DWORD), ("value", ValueUnion)]

    class Item(c.Structure):
        _fields_ = [("name", c.c_wchar_p), ("formatted", Value)]

    dll = c.WinDLL("pdh", use_last_error=True)
    handle = c.c_void_p
    dword_ptr = c.POINTER(w.DWORD)

    def bind(name, *args):
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = list(args), w.LONG
        return fn

    open_query = bind("PdhOpenQueryW", c.c_wchar_p, c.c_size_t, c.POINTER(handle))
    add = bind("PdhAddEnglishCounterW", handle, c.c_wchar_p, c.c_size_t, c.POINTER(handle))
    collect = bind("PdhCollectQueryData", handle)
    array = bind("PdhGetFormattedCounterArrayW", handle, w.DWORD, dword_ptr, dword_ptr, c.c_void_p)
    close = bind("PdhCloseQuery", handle)
    query = handle()
    if open_query(None, 0, c.byref(query)) != 0:
        return []
    samples = []
    try:
        counters = {}
        for field, label in (("dedicated_gib", "Dedicated Usage"), ("shared_gib", "Shared Usage")):
            counter = handle()
            path = "\\GPU Process Memory(*)\\" + label
            if add(query, path, 0, c.byref(counter)) == 0:
                counters[field] = counter
        if not counters or collect(query) != 0:
            return []
        for field, counter in counters.items():
            size, count = w.DWORD(), w.DWORD()
            # PDH_FMT_DOUBLE | PDH_FMT_NOCAP100; GPU memory is a byte gauge.
            fmt = 0x00000200 | 0x00008000
            code = array(counter, fmt, c.byref(size), c.byref(count), None) & 0xffffffff
            if code != 0x800007d2 or not 0 < size.value <= 32 * 1024 * 1024:
                continue
            buf = c.create_string_buffer(size.value)
            capacity = size.value
            if array(counter, fmt, c.byref(size), c.byref(count), buf) != 0:
                continue
            if count.value * c.sizeof(Item) > capacity:
                continue
            items = c.cast(buf, c.POINTER(Item))
            for i in range(count.value):
                item = items[i]
                if item.name:
                    value = item.formatted.value.double_value if item.formatted.status in (0, 1) else None
                    samples.append((field, item.name, value))
        return samples
    finally:
        close(query)


def process_gpu_memory():
    """WDDM PID dedicated/shared memory via native PDH; unknown is not zero."""
    import re
    try:
        values = {}
        invalid = set()
        for field, instance, amount in _pdh_gpu_samples():
            match = re.match(r"^pid_(\d+)_", instance, re.I)
            if not match or field not in ("dedicated_gib", "shared_gib"):
                continue
            pid = int(match[1])
            key = (pid, field)
            if not number(amount):
                invalid.add(key)
                continue
            item = values.setdefault(pid, {})
            item[field] = item.get(field, 0) + amount / (2**30)
        for pid, field in invalid:
            if pid in values:
                values[pid].pop(field, None)
        return {pid: fields for pid, fields in values.items() if fields}
    except (OSError, ValueError, TypeError, AttributeError, OverflowError):
        return {}


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


def owner_manual_cuda(review):
    """Explicit server-owner opt-in, never a measurement or HTTP override."""
    return review.get("evidence") == "bounded_owner_trial" and review.get("manual_cuda_trial") is True


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
    pending_vram_unknown = any(r.get("vram_gib") is None for r in pending)
    vram_free = telemetry.get("vram_free_gib")
    if mode == "cuda":
        if not number(vram_free):
            raise ValueError("vram_telemetry_unknown")
        if review.get("evidence") != "measured":
            if not owner_manual_cuda(review):
                raise ValueError("cuda_measurement_unverified")
            # Unknown/unmeasured RAM already requires explicit risk confirmation.
            # Manual CUDA is a trusted, opt-in owner trial; never call it measured.
        if vram is not None and (not number(vram) or not 0 < vram < 1024):
            raise ValueError("invalid_resource_estimate")
        # Estimates are advisory; actual allocation success belongs to the engine.
        if vram is None:
            warnings.append("vram_estimate_unknown")
        if pending_vram_unknown:
            warnings.append("vram_reservation_unknown")
        if vram is not None and vram_free-vram_reserved < vram:
            warnings.append("low_vram_forecast")
    job_cap=review.get("job_limit_gib")
    if job_cap is not None and (not number(job_cap) or job_cap<=0):
        raise ValueError("invalid_job_limit")
    if job_cap is not None and ram is not None and job_cap<ram:
        warnings.append("job_cap_below_estimate")
    public={"ram_free_gib":telemetry["free_gib"],"ram_reserved_gib":reserved,"ram_estimate_gib":ram,
        "ram_after_gib":remaining,"ram_warning_gib":threshold,"estimate_evidence":review.get("evidence","unknown"),
        "vram_free_gib":vram_free if mode=="cuda" else None,"vram_reserved_gib":vram_reserved,
        "vram_estimate_gib":vram,"vram_after_gib":vram_free-vram_reserved-vram if mode=="cuda" and vram is not None and not pending_vram_unknown else None,
        "job_limit_gib":job_cap}
    launch={"ram_gib":ram,"vram_gib":vram,"job_limit_gib":job_cap,"ram_warning_gib":threshold,
            "min_free_at_start_gib":max(0,telemetry["free_gib"]-drift)}
    return {"forecast":public,"warnings":warnings,"policy":launch,
            "risk_ack_allowed":settings.get("allow_risk_ack",False) is True,
            "requires_ack":any(w not in {"vram_estimate_unknown","vram_reservation_unknown","low_vram_forecast"} for w in warnings)}
