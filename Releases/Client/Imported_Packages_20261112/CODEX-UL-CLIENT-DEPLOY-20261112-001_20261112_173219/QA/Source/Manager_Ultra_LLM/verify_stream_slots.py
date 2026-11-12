"""Repeatable offline acceptance evidence, never deploys or runs an LLM.

The optional installed audit reads only launcher/release files, process metadata
and static JS. It never reads the real private profile, tokens or chat history.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from urllib.request import build_opener, ProxyHandler

ROOT=Path(__file__).resolve().parent.parent
TASK="CODEX-UL-STREAM-SLOTS-20261112-001"


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def installed_audit():
    result={"scope":"READ_ONLY; no private profile/history/token files"}
    installed=Path(r"M:\UltraLLM_Client")
    result["root"]=str(installed)
    checks=[]
    manifest=installed/'SHA256SUMS.txt'
    if manifest.is_file():
        for line in manifest.read_text(encoding='utf-8-sig').splitlines():
            expected,relative=line.split('  ',1)
            file=(installed/relative).resolve()
            if not file.is_relative_to(installed.resolve()):raise ValueError("Installed manifest path escaped release")
            checks.append(file.is_file() and digest(file)==expected.lower())
    result['manifest_files']=len(checks);result['manifest_matches']=sum(checks)
    for name in ('UltraLLMClient.exe','Start_Ultra_LLM_Client.vbs','_internal/web_assets/client.js'):
        path=installed/name
        if path.is_file():result[name]={'sha256':digest(path),'bytes':path.stat().st_size}
    js=(installed/'_internal/web_assets/client.js').read_text(encoding='utf-8')
    result['installed_has_stream_route']='/api/chat/stream' in js
    script=r"""$s=New-Object -ComObject WScript.Shell;$p=Join-Path $s.SpecialFolders.Item('Desktop') 'Ultra LLM Client.lnk';$l=$s.CreateShortcut($p);$ps=@(Get-CimInstance Win32_Process -Filter "Name='UltraLLMClient.exe'");$ids=@($ps.ProcessId);[pscustomobject]@{shortcut=[pscustomobject]@{target=$l.TargetPath;arguments=$l.Arguments;working_directory=$l.WorkingDirectory};processes=@($ps|Select-Object ProcessId,ParentProcessId,ExecutablePath);listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -in $ids}|Select-Object LocalAddress,LocalPort,OwningProcess)}|ConvertTo-Json -Compress -Depth 5"""
    probe=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,timeout=20,check=True)
    result['startup']=json.loads(probe.stdout.decode('utf-8-sig'))
    relevant=[p for p in result['startup']['processes'] if str(p['ExecutablePath']).casefold()==str(installed/'UltraLLMClient.exe').casefold()]
    result['matching_client_processes']=len(relevant)
    if len(relevant)==1:
        listeners=[p for p in result['startup']['listeners'] if p['OwningProcess']==relevant[0]['ProcessId'] and p['LocalAddress']=='127.0.0.1']
        if len(listeners)==1:
            with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{listeners[0]['LocalPort']}/client.js",timeout=3) as response:
                result['running_static_js_matches_release']=hashlib.sha256(response.read(1048577)).hexdigest()==digest(installed/'_internal/web_assets/client.js')
    server=Path(r"\\192.168.0.77\Server\Ultra_LLM\Manager_Live")
    for name in ('live_manager.py','chat_runtime.py'):
        file=server/name
        if file.is_file():
            source=file.read_text(encoding='utf-8-sig')
            result['server_'+name]={'sha256':digest(file),'stream_present':'/v1/chat/stream' in source or 'def proxy_stream' in source}
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-installed',action='store_true')
    parser.add_argument('--evidence',type=Path,default=Path(__file__).with_name('STREAM_SLOTS_EVIDENCE.json'))
    args=parser.parse_args()
    if sys.version_info[:2]!=(3,12):raise RuntimeError("Use Python 3.12")
    output=args.evidence.resolve()
    if not output.is_relative_to(ROOT):raise ValueError('Evidence must remain inside this checkout')
    if output.exists() and json.loads(output.read_text(encoding='utf-8')).get('task_id')!=TASK:
        raise FileExistsError('Refuse to replace unrelated evidence')
    evidence={'task_id':TASK,'base_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'started_at_utc':datetime.now(timezone.utc).isoformat(),
        'scope':'Offline SOURCE; all engines/resources in browser tests are fixtures; native jobs use dummy Python only',
        'independent_acceptance':'PENDING','live_models':'NOT RUN','production_deployment':'NOT RUN','steps':[]}
    commands=[('manager_suite',['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'Manager_Ultra_LLM/verify_offline.ps1')]),
        ('python_syntax',[sys.executable,'-X','utf8','-B','-c',"from pathlib import Path;[compile(p.read_text(encoding='utf-8-sig'),str(p),'exec') for d in ('Manager_Ultra_LLM','Client_Ultra_LLM') for p in Path(d).glob('*.py')];print('SYNTAX PASS')"]),
        ('client_suite',[sys.executable,'-X','utf8','-B','-m','unittest','discover','-s',str(ROOT/'Client_Ultra_LLM'),'-q']),
        ('js_syntax',['node','--check',str(ROOT/'Client_Ultra_LLM/web_assets/client.js')]),
        ('legacy_browser',['node',str(ROOT/'Client_Ultra_LLM/test_browser_control_stream.mjs')]),
        ('p0_source_tls_browser',['node',str(ROOT/'Client_Ultra_LLM/test_browser_stream_source.mjs')]),
        ('p1_source_tls_browser',['node',str(ROOT/'Client_Ultra_LLM/test_browser_slots_source.mjs')]),
        ('diff_check',['git','diff','--check','--','Manager_Ultra_LLM','Client_Ultra_LLM'])]
    for name,command in commands:
        print('RUN '+name,flush=True)
        began=time.perf_counter()
        try:
            result=subprocess.run(command,cwd=ROOT,env={**os.environ,'PYTHONUTF8':'1'},capture_output=True,timeout=240)
        except subprocess.TimeoutExpired as failure:
            result=subprocess.CompletedProcess(command,124,failure.stdout or b'',(failure.stderr or b'')+b'\nOFFLINE STAGE TIMEOUT')
        row={'name':name,'status':'PASS' if result.returncode==0 else 'FAIL','exit_code':result.returncode,
             'seconds':round(time.perf_counter()-began,3),'command':command,
             'stdout':result.stdout.decode('utf-8',errors='replace'),'stderr':result.stderr.decode('utf-8',errors='replace')}
        if name.endswith('browser') and result.returncode==0:
            row['result']=json.loads(row['stdout'])
        evidence['steps'].append(row)
        print(row['status']+' '+name,flush=True)
    if args.audit_installed:
        print('RUN read_only_installed_audit',flush=True)
        evidence['installed_audit']=installed_audit()
    files=[]
    for item in subprocess.check_output(['git','status','--porcelain','-z'],cwd=ROOT).decode().split('\0'):
        if not item or not item[3:].startswith(('Manager_Ultra_LLM/','Client_Ultra_LLM/')):continue
        relative=item[3:];file=ROOT/relative
        if file.is_file() and file.suffix in ('.py','.ps1','.mjs','.js','.html','.css'):
            files.append({'path':relative,'sha256':digest(file)})
    evidence['source_files']=sorted(files,key=lambda r:r['path'])
    canonical=''.join(f"{r['sha256']}  {r['path']}\n" for r in evidence['source_files'])
    evidence['source_manifest_sha256']=hashlib.sha256(canonical.encode()).hexdigest()
    evidence['temporary_fixtures_removed']=not (ROOT/'c').exists() and not any((ROOT/'Client_Ultra_LLM').glob('.*-qa-*'))
    image=ROOT/'Client_Ultra_LLM/stream_slots_browser.png'
    if image.exists():evidence['browser_screenshot']={'path':str(image),'sha256':digest(image)}
    evidence['status']='PASS' if all(r['status']=='PASS' for r in evidence['steps']) and evidence['temporary_fixtures_removed'] else 'FAIL'
    evidence['completed_at_utc']=datetime.now(timezone.utc).isoformat()
    output.write_bytes((json.dumps(evidence,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
    print('EVIDENCE '+str(output),flush=True)
    return 0 if evidence['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
