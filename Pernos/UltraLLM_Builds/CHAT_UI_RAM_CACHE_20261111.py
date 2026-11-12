from pathlib import Path
p=Path(r"M:\GitHub\local_LLM_GPT_docs\Manager_Ultra_LLM\live_manager.py")
s=p.read_text(encoding="utf-8-sig")
needle="def _os_telemetry(ports):"
assert s.count(needle)==1
s=s.replace(needle,
'''_HARDWARE_RAM_CACHE = None
_HARDWARE_RAM_LOCK = threading.Lock()


def _os_telemetry(ports):''',1)
start=s.index("    script = (",s.index("def _os_telemetry(ports):"))
end=s.index("    cmd = [",start)
block=s[start:end]
needle='''    script = (r"$ErrorActionPreference='Stop';" +
'''
assert block.startswith(needle),repr(block[:130])
block=block.replace(needle,'''    global _HARDWARE_RAM_CACHE
    cached_hardware = _HARDWARE_RAM_CACHE
    probe_hardware = cached_hardware is None
    probe = (
        r"$mem=@();try{$mem=@(Get-CimInstance Win32_PhysicalMemory -ErrorAction Stop)}catch{$mem=@()};"
        r"$generation='';$installed=0.0;"
        r"if($mem.Count -gt 0){$kinds=@($mem|ForEach-Object{[int]$_.SMBIOSMemoryType}|Sort-Object -Unique);"
        r"if($kinds.Count -eq 1 -and $kinds[0] -eq 26){$generation='DDR4'}"
        r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 34){$generation='DDR5'}"
        r"elseif($kinds.Count -eq 1 -and $kinds[0] -eq 24){$generation='DDR3'};"
        r"$installed=[double](($mem|Measure-Object -Property Capacity -Sum).Sum)/1GB};"
    ) if probe_hardware else ""
    fields = r"ddr_generation=$generation;installed_gib=$installed;" if probe_hardware else ""
    script = (r"$ErrorActionPreference='Stop';" +
''',1)
a=block.index('              r"$mem=@();try{')
b=block.index('              r"$list=@(',a)
block=block[:a]+'              probe +\n'+block[b:]
needle='''              r"ddr_generation=$generation;installed_gib=$installed;" +
'''
assert block.count(needle)==1
block=block.replace(needle,'''              fields +
''',1)
s=s[:start]+block+s[end:]
needle='''    data = json.loads(result.stdout.strip())
    if not isinstance(data, dict) or not isinstance(data.get("listeners"), list):
        raise RuntimeError("Windows telemetry incomplete")
    return data
'''
assert s.count(needle)==1
replace='''    data = json.loads(result.stdout.strip())
    if not isinstance(data, dict) or not isinstance(data.get("listeners"), list):
        raise RuntimeError("Windows telemetry incomplete")
    if probe_hardware:
        stable = {}
        if data.get("ddr_generation") in ("DDR3", "DDR4", "DDR5"):
            stable["ddr_generation"] = data["ddr_generation"]
        installed = data.get("installed_gib")
        if type(installed) in (int, float) and 0 < installed < 8192:
            stable["installed_gib"] = round(float(installed), 2)
        with _HARDWARE_RAM_LOCK:
            if _HARDWARE_RAM_CACHE is None:
                _HARDWARE_RAM_CACHE = stable
    else:
        data.update(cached_hardware)
    return data
'''
s=s.replace(needle,replace,1)
p.write_text(s,encoding="utf-8",newline="\n")
print("Hardware RAM probe runs once per Manager process, then cached.")
