# Execute through existing IP/Negotiate WinRM. READ ONLY, no backup/staging yet.
$ErrorActionPreference = 'Stop'
if ($env:COMPUTERNAME -ne 'DESKTOP-KT4G5SM') { throw 'Wrong execution host' }
$checks = [ordered]@{}
$e = [ordered]@{ host=$env:COMPUTERNAME; sampled_utc=[DateTime]::UtcNow.ToString('o'); phase='B read-only preflight'; writes=$false }
function Check([string]$name, [bool]$value) { $checks[$name]=$value }
function Identity($process) {
    $sid = (Invoke-CimMethod -InputObject $process -MethodName GetOwnerSid).Sid
    if (-not $sid) { throw 'Process owner SID unavailable' }
    return [pscustomobject]@{ pid=[int]$process.ProcessId; parent_pid=[int]$process.ParentProcessId; exe=$process.ExecutablePath; created_utc=$process.CreationDate.ToUniversalTime().ToString('o'); owner_sid=$sid; name=$process.Name }
}
function NoLinks([string]$path) {
    $node = [IO.Path]::GetFullPath($path)
    while ($node) {
        if (Test-Path -LiteralPath $node) {
            if ((Get-Item -LiteralPath $node -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { return $false }
        }
        $parent = [IO.Directory]::GetParent($node)
        $node = if ($parent) {$parent.FullName} else {$null}
    }
    return $true
}
try {
    $who=[Security.Principal.WindowsIdentity]::GetCurrent()
    $e.execution=@{ identity_sid=$who.User.Value; identity_name=$who.Name; authentication=$who.AuthenticationType; is_admin=([Security.Principal.WindowsPrincipal]$who).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator) }
    Check 'admin_backup_authority' $e.execution.is_admin
    $task=Get-ScheduledTask -TaskName 'UltraLLM_Manager_LIVE'
    Check 'task_running_single_action' ($task.State -eq 'Running' -and @($task.Actions).Count -eq 1)
    if (-not $checks.task_running_single_action) { throw 'Task not running with a single action' }
    $action=$task.Actions[0]
    $pattern='^\s*-u\s+-B\s+(?:"(?<script>[^"]+)"|(?<script>\S+))\s+--config\s+(?:"(?<config>[^"]+)"|(?<config>\S+))\s+--log-dir\s+(?:"(?<logs>[^"]+)"|(?<logs>\S+))\s*$'
    $m=[regex]::Match($action.Arguments,$pattern)
    Check 'task_arguments_known_contract' $m.Success
    if (-not $m.Success) { throw 'Unexpected task argument contract; arguments not exported' }
    $script=$m.Groups['script'].Value; $config=$m.Groups['config'].Value; $logs=$m.Groups['logs'].Value
    $root=Split-Path -Parent $script
    Check 'runtime_path_expected_no_links' ($root -ieq 'C:\Server\Ultra_LLM\Manager_Live' -and (NoLinks $root))
    Check 'config_path_expected_no_links' ($config -ieq 'C:\ProgramData\UltraLLM\Manager\private\manager.json' -and (NoLinks $config))
    Check 'python_exists_no_links' ((Test-Path -LiteralPath $action.Execute -PathType Leaf) -and (NoLinks $action.Execute))
    $taskSid=([Security.Principal.NTAccount]$task.Principal.UserId).Translate([Security.Principal.SecurityIdentifier]).Value
    $taskXml=Export-ScheduledTask -TaskName 'UltraLLM_Manager_LIVE'
    $hash=[Security.Cryptography.SHA256]::Create()
    $taskHash=([BitConverter]::ToString($hash.ComputeHash([Text.Encoding]::UTF8.GetBytes($taskXml)))).Replace('-','').ToLowerInvariant()
    $e.task=@{ name=$task.TaskName; state=[string]$task.State; executable=$action.Execute; script=$script; config_path=$config; log_dir=$logs; working_directory=$action.WorkingDirectory; principal_sid=$taskSid; logon_type=[string]$task.Principal.LogonType; run_level=[string]$task.Principal.RunLevel; xml_sha256=$taskHash; restart_count=$task.Settings.RestartCount; restart_interval=[string]$task.Settings.RestartInterval; multiple_instances=[string]$task.Settings.MultipleInstances }
    $cfg=Get-Content -LiteralPath $config -Raw -Encoding UTF8 | ConvertFrom-Json
    Check 'control_disabled' ($cfg.control.owner_go -ne $true)
    Check 'private_paths_local' ((NoLinks $cfg.cert_file) -and (NoLinks $cfg.key_file) -and $cfg.cert_file.StartsWith('C:\ProgramData\UltraLLM\Manager\private\',[StringComparison]::OrdinalIgnoreCase) -and $cfg.key_file.StartsWith('C:\ProgramData\UltraLLM\Manager\private\',[StringComparison]::OrdinalIgnoreCase))
    $listeners=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -eq [int]$cfg.listen_port})
    Check 'one_manager_listener' ($listeners.Count -eq 1 -and $listeners[0].LocalAddress -eq $cfg.bind_host)
    if (-not $checks.one_manager_listener) { throw 'Manager listener ambiguous' }
    $manager=Get-CimInstance Win32_Process -Filter ('ProcessId='+$listeners[0].OwningProcess)
    $managerId=Identity $manager
    Check 'manager_identity_action_match' ($managerId.exe -ieq $action.Execute -and $managerId.owner_sid -eq $taskSid -and $manager.CommandLine.EndsWith($action.Arguments,[StringComparison]::OrdinalIgnoreCase))
    $e.manager=$managerId
    $e.manager_listener=@{address=$listeners[0].LocalAddress;port=$listeners[0].LocalPort;pid=$listeners[0].OwningProcess}
    $qport=8000
    $qListeners=@(Get-NetTCPConnection -State Listen | Where-Object {$_.LocalPort -eq $qport})
    Check 'one_qwen_loopback_listener' ($qListeners.Count -eq 1 -and $qListeners[0].LocalAddress -eq '127.0.0.1')
    if (-not $checks.one_qwen_loopback_listener) { throw 'Qwen listener ambiguous or absent' }
    $gateway=Get-CimInstance Win32_Process -Filter ('ProcessId='+$qListeners[0].OwningProcess)
    $engine=@(Get-CimInstance Win32_Process -Filter ("ParentProcessId="+$gateway.ProcessId) | Where-Object {$_.Name -eq 'qwen36.exe'})
    Check 'one_qwen_engine' ($engine.Count -eq 1)
    $valheim=@(Get-CimInstance Win32_Process -Filter "Name='valheim_server.exe'")
    Check 'one_valheim_process' ($valheim.Count -eq 1)
    if (-not $checks.one_qwen_engine -or -not $checks.one_valheim_process) { throw 'Protected process identity ambiguous or absent' }
    $e.qwen_gateway=Identity $gateway; $e.qwen_engine=Identity $engine[0]; $e.valheim=Identity $valheim[0]
    $e.valheim_udp=@(Get-NetUDPEndpoint | Where-Object {$_.OwningProcess -eq $valheim[0].ProcessId} | Select-Object LocalAddress,LocalPort,OwningProcess)
    Check 'valheim_udp_bound' ($e.valheim_udp.Count -gt 0)
    $tree=@(Get-CimInstance Win32_Process -Property ProcessId,ParentProcessId,Name)
    $descendants=New-Object 'System.Collections.Generic.HashSet[int]'
    [void]$descendants.Add([int]$manager.ProcessId)
    do {
        $changed=$false
        foreach($p in $tree) {if($descendants.Contains([int]$p.ParentProcessId) -and $descendants.Add([int]$p.ProcessId)) {$changed=$true}}
    } while($changed)
    Check 'protected_processes_outside_manager_tree' (-not $descendants.Contains([int]$gateway.ProcessId) -and -not $descendants.Contains([int]$engine[0].ProcessId) -and -not $descendants.Contains([int]$valheim[0].ProcessId))
    $children=@($tree | Where-Object {$_.ProcessId -ne $manager.ProcessId -and $descendants.Contains([int]$_.ProcessId)})
    $e.manager_children=@($children | Select-Object ProcessId,ParentProcessId,Name)
    Check 'manager_has_no_model_children' (@($children | Where-Object {$_.Name -notin @('powershell.exe','conhost.exe')}).Count -eq 0)
    $e.manager_descendant_count=$descendants.Count-1
    $private=Split-Path -Parent $config
    $acl=Get-Acl -LiteralPath $private
    $allowedSids=@($who.User.Value,'S-1-5-18','S-1-5-32-544')
    $aclRows=@($acl.Access | ForEach-Object {[pscustomobject]@{sid=$_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value;type=[string]$_.AccessControlType;rights=[string]$_.FileSystemRights;inherited=$_.IsInherited}})
    Check 'private_acl_protected_scoped' ($acl.AreAccessRulesProtected -and @($aclRows | Where-Object {$_.type -eq 'Allow' -and $_.sid -notin $allowedSids}).Count -eq 0)
    $e.private_acl=@{protected=$acl.AreAccessRulesProtected;rules=$aclRows;owner=$acl.Owner}
    $disk=Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='C:'"
    Check 'backup_space_available' ($disk.FreeSpace -gt 2GB)
    $e.disk=@{drive='C:';free_bytes=$disk.FreeSpace;size_bytes=$disk.Size}
    $e.public_code=@(Get-ChildItem -LiteralPath $root -File -Force | ForEach-Object {[pscustomobject]@{name=$_.Name;bytes=$_.Length;sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}})
    $known=@{'live_manager.py'='e15ef6ccea34fc4a6d7ba2afc2a4a37d6739d9b48884dcd99d0a9baa4584da51';'chat_runtime.py'='fc69896cc40a64237ff3125299d21d8e4a49ec0b5f0ae6ec64c1d905b9755466'}
    Check 'known_installed_manager_version' (@($known.Keys | Where-Object {(Get-FileHash -LiteralPath (Join-Path $root $_) -Algorithm SHA256).Hash.ToLowerInvariant() -ne $known[$_]}).Count -eq 0)
    $py=@'
import hashlib,http.client,json,pathlib,socket,sqlite3,ssl,sys,urllib.request
try:
 c=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
 state=pathlib.Path(sys.argv[1]).parent.parent
 out={'python':{'version':sys.version.split()[0],'bits':__import__('struct').calcsize('P')*8},'config_sha256':hashlib.sha256(pathlib.Path(sys.argv[1]).read_bytes()).hexdigest(),'client_count':len(c['clients']),'control_models_granted_count':sum(x.get('control_models') is True for x in c['clients']),'pairing_admin_count':sum(x.get('pairing_admin') is True for x in c['clients']),'owner_go':c.get('control',{}).get('owner_go',False),'slot_count':len(c['slots'])}
 server=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);server.load_cert_chain(c['cert_file'],c['key_file'])
 out['tls_keypair_load']='PASS'
 ctx=ssl.create_default_context(cafile=c['cert_file']);ctx.minimum_version=ssl.TLSVersion.TLSv1_2
 conn=http.client.HTTPSConnection(c['bind_host'],c['listen_port'],context=ctx,timeout=4)
 conn.connect();out['tls_peer_sha256']=hashlib.sha256(conn.sock.getpeercert(binary_form=True)).hexdigest()
 conn.request('GET','/v1/snapshot');resp=conn.getresponse();out['unauth_snapshot_http']=resp.status;resp.read(4096);conn.close()
 direct=urllib.request.build_opener(urllib.request.ProxyHandler({}))
 for name,route in (('qwen_health','/health'),('qwen_models','/v1/models')):
  with direct.open('http://127.0.0.1:8000'+route,timeout=3) as r:data=json.loads(r.read(65536))
  out[name]=({'status':data.get('status')} if name=='qwen_health' else {'model_ids':[v['id'] for v in data.get('data',[])]})
 dbs=[]
 for p in state.rglob('*'):
  if p.is_file() and p.suffix.lower() in ('.db','.sqlite','.sqlite3'):
   db=sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True,timeout=2)
   good=db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
   tables={x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
   active=db.execute('SELECT COUNT(*) FROM instances WHERE released=0').fetchone()[0] if 'instances' in tables else None
   db.close();dbs.append({'relative':str(p.relative_to(state)),'quick_check_ok':good,'active_owned_instances':active,'wal_present':p.with_name(p.name+'-wal').exists()})
 out['state_databases']=dbs
 out['state_root']=str(state)
 print(json.dumps({'status':'PASS','metadata':out}))
except Exception as e:
 print(json.dumps({'status':'BLOCKED','error_type':type(e).__name__}));sys.exit(2)
'@
    $encoded=[Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($py))
    $pythonOutput=@(& $action.Execute -X utf8 -B -c 'import base64,sys;exec(base64.b64decode(sys.argv.pop(1)))' $encoded $config)
    $pythonExit=$LASTEXITCODE
    $parsed=($pythonOutput -join "`n") | ConvertFrom-Json
    Check 'python_private_tls_health_audit' ($pythonExit -eq 0 -and $parsed.status -eq 'PASS')
    $e.python_audit=$parsed
    if ($parsed.status -eq 'PASS') {
        $meta=$parsed.metadata
        Check 'python_312_x64' ($meta.python.version.StartsWith('3.12.') -and $meta.python.bits -eq 64)
        Check 'tls_and_auth_denial' ($meta.tls_keypair_load -eq 'PASS' -and $meta.unauth_snapshot_http -eq 401)
        Check 'qwen_ready_expected_model' ($meta.qwen_health.status -eq 'ok' -and @($meta.qwen_models.model_ids | Where-Object {$_ -match '(?i)qwen'}).Count -gt 0)
        Check 'state_databases_consistent_no_jobs' (@($meta.state_databases | Where-Object {-not $_.quick_check_ok -or $_.active_owned_instances -gt 0}).Count -eq 0)
    }
} catch {
    $e.error=@{type=$_.Exception.GetType().FullName;id=$_.FullyQualifiedErrorId;message=$_.Exception.Message}
}
$e.checks=$checks
$failed=@($checks.Keys | Where-Object {-not $checks[$_]})
$e.failed_checks=$failed
$e.status=if($e.error -or $failed.Count -gt 0){'BLOCKED'}else{'PREFLIGHT_READONLY_PASS'}
$e | ConvertTo-Json -Depth 12 -Compress
