"""AMENDMENT 01: isolated QA only. --diagnose retains inherited PSMODULEPATH.
Default Stage C removes that child-only override; production is never contacted.
"""
import argparse, datetime, hashlib, json, os, re, socket, subprocess, sys, time, uuid
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
QA=ROOT/'Test/ClientMigration_20261112'
PAYLOAD=QA/'R5'
PS=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
OPENER=build_opener(ProxyHandler({}))
def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,data):p.write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
def require(value,message):
    if not value:raise RuntimeError(message)
def safe(s):
    home=os.environ.get('USERPROFILE','__NO_HOME__')
    for candidate in (home.replace('\\','\\\\'),home):
        s=re.sub(re.escape(candidate),lambda _:'%USERPROFILE%',s,flags=re.I)
    return s
def clean(env):return {k:v for k,v in env.items() if k.upper()!='PSMODULEPATH'}
def ps(script,env,*,startup_policy=False):
    script="[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$OutputEncoding=[Console]::OutputEncoding;"+script
    command=[str(PS),'-NoProfile','-NonInteractive']+(['-ExecutionPolicy','Bypass'] if startup_policy else [])+['-Command',script]
    p=subprocess.run(command,env=env,cwd=QA,
        capture_output=True,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    return {'returncode':p.returncode,'stdout':safe(p.stdout.decode('utf-8-sig',errors='replace').strip()),
        'stderr':safe(p.stderr.decode('utf-8-sig',errors='replace').strip())}
def baseline():
    inv=json.loads((REPORT/'inventory.json').read_text(encoding='utf-8'));old=Path(inv['old_install_path'])
    files={p.relative_to(old).as_posix():digest(p) for p in old.rglob('*') if p.is_file()}
    require(files==inv['old_file_hashes'],'Existing installation file drift')
    shortcut=Path(os.environ['USERPROFILE'])/'Desktop/Ultra LLM Client.lnk'
    require(digest(shortcut)==inv['shortcut_sha256'],'Existing shortcut drift')
    probe=ps("$p=Get-CimInstance Win32_Process -Filter \"ProcessId=29492\";if(!$p){exit 4};[pscustomobject]@{pid=$p.ProcessId;exe=$p.ExecutablePath;creation_utc=$p.CreationDate.ToUniversalTime().ToString('o')}|ConvertTo-Json -Compress",clean(dict(os.environ)))
    require(probe['returncode']==0,'Existing Client identity unavailable');item=json.loads(probe['stdout'])
    require(Path(item['exe'])==old/'UltraLLMClient.exe','Existing PID identity mismatch')
    require(not (ROOT/'Production/Client').exists(),'Production unexpectedly exists')
    return {'old_file_count':len(files),'old_files_digest':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),
        'shortcut_sha256':digest(shortcut),'old_process':item,'production_exists':False}
def acl(folder,env):
    literal="'"+str(folder).replace("'","''")+"'"
    return ps("$ErrorActionPreference='Stop';try{$a=Get-Acl -LiteralPath "+literal+";[pscustomobject]@{protected=$a.AreAccessRulesProtected;rule_count=$a.Access.Count;command_module=(Get-Command Get-Acl).Module.Path}|ConvertTo-Json -Compress;exit 0}catch{[pscustomobject]@{error_id=$_.FullyQualifiedErrorId;exception_type=$_.Exception.GetType().FullName;message=$_.Exception.Message}|ConvertTo-Json -Compress;exit 1}",env)
def get(url,path):
    with OPENER.open(url+path,timeout=3) as r:
        require(r.headers.get('Server','').startswith('UltraLLMWeb/'),'Unexpected local server')
        return r.status,r.read()
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--diagnose',action='store_true');args=parser.parse_args()
    require(socket.gethostname().casefold()=='desktop-sc96d3u','Home PC required')
    require(ROOT==Path(r'M:\GitHub\local_LLM'),'Existing home workspace required')
    rows={}
    for line in (PAYLOAD/'SHA256SUMS.txt').read_text(encoding='utf-8-sig').splitlines():
        expected,name=line.split('  ',1);p=(PAYLOAD/name).resolve()
        require(p.is_relative_to(PAYLOAD.resolve()) and digest(p)==expected,'Payload SHA failure: '+name);rows[name]=expected
    require(len(rows)==72,'Payload manifest differs')
    require({p.relative_to(PAYLOAD).as_posix() for p in PAYLOAD.rglob('*') if p.is_file()}==set(rows)|{'SHA256SUMS.txt'},'Unexpected payload files')
    run=QA/'Amendment01'/(datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8])
    require(run.resolve().is_relative_to(QA.resolve()),'QA path escape');run.mkdir(parents=True)
    temp=run/'Temp';temp.mkdir();private=run/'AppData/UltraLLM/Client'
    require(not private.exists(),'Fresh synthetic profile required')
    env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONPATH','PYTHONHOME')}
    env.update(PYTHONDONTWRITEBYTECODE='1',LOCALAPPDATA=str(run/'AppData'),TEMP=str(temp),TMP=str(temp),TMPDIR=str(temp))
    if not args.diagnose:env=clean(env)
    before=baseline();mutex=lambda p:'Local\\UltraLLM-Web-'+hashlib.sha256(str(p.absolute()).casefold().encode()).hexdigest()[:32]
    real_profile=Path(os.environ['LOCALAPPDATA'])/'UltraLLM/Client'
    require(mutex(private)!=mutex(real_profile),'QA/real mutex collision')
    result={'task_id':'CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001','mode':'inherited_reproduction' if args.diagnose else 'corrected_stage_C',
        'status':'RUNNING','started_at_utc':utc(),'qa_run':str(run),'synthetic_profile':str(private),'profile_initially_absent':True,
        'payload_hashes_verified':72,'payload_total_files':73,'exe_sha256':digest(PAYLOAD/'UltraLLMClient.exe'),
        'helper_matches_source':(PAYLOAD/'_internal/Prepare-ClientPrivate.ps1').read_bytes()==(ROOT/'Client_Ultra_LLM/Prepare-ClientPrivate.ps1').read_bytes(),
        'environment_fix':'NONE' if args.diagnose else 'Child-only removal of inherited PSMODULEPATH',
        'mutex_distinct':True,'qa_mutex':mutex(private),'before':before,'processes':[],'cycles':[],
        'actual_manager_requests':0,'owner_go':False,'stage_D':'NOT RUN','browser_visual':'NOT RUN','VBS_execution':'NOT RUN'}
    output=REPORT/('amendment_01_reproduction.json' if args.diagnose else 'isolated_result.json');save(output,result)
    children=[]
    def launch(label):
        stdout=run/(label+'.stdout.txt');stderr=run/(label+'.stderr.txt');out=stdout.open('wb');err=stderr.open('wb')
        record={'label':label,'command':[str(PAYLOAD/'UltraLLMClient.exe'),'--no-browser'],'started_at_utc':utc(),'returncode':None}
        began=time.perf_counter();p=subprocess.Popen(record['command'],cwd=QA,env=env,stdout=out,stderr=err,creationflags=subprocess.CREATE_NO_WINDOW)
        record['pid']=p.pid;result['processes'].append(record);row=(p,record,began,out,err,stdout,stderr);children.append(row);save(output,result);return row
    def exit_code(row):
        p,record,began,out,err,stdout,stderr=row;code=p.poll()
        if code is not None and record['returncode'] is None:
            record.update(returncode=code,exit_code_hex='0x%08X'%(code&0xffffffff),exit_observed_at_utc=utc(),lifetime_ms=round((time.perf_counter()-began)*1000,3))
            out.flush();err.flush();record['stdout_safe']=safe(stdout.read_text(encoding='utf-8',errors='replace'));record['stderr_safe']=safe(stderr.read_text(encoding='utf-8',errors='replace'));save(output,result)
        return code
    def stop(row,url):
        key=json.loads(get(url,'/api/session')[1])['csrf']
        with OPENER.open(Request(url+'/api/shutdown',data=b'{}',headers={'Origin':url,'X-Ultra-CSRF':key,'Content-Type':'application/json'}),timeout=5) as r:
            require(json.loads(r.read())['stopping'] is True,'QA shutdown rejected')
        row[0].wait(timeout=15);require(exit_code(row)==0,'Nonzero QA shutdown exit')
    print('QA_RUN='+str(run),flush=True)
    try:
        if not args.diagnose:
            command=[sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','Client_Ultra_LLM','-p','test_*.py','-v']
            unit=subprocess.run(command,cwd=ROOT,env=env,capture_output=True,timeout=180)
            (REPORT/'amendment_01_unittest.stdout.txt').write_bytes(unit.stdout);(REPORT/'amendment_01_unittest.stderr.txt').write_bytes(unit.stderr)
            result['source_unit_tests']={'command':command,'returncode':unit.returncode};require(unit.returncode==0,'Client unit tests failed')
        for cycle in range(1 if args.diagnose else 2):
            row=launch('main_'+str(cycle+1));deadline=time.perf_counter()+25;url=None
            while time.perf_counter()<deadline:
                code=exit_code(row)
                require(code is None,'QA EXE exited before HTTP-ready: returncode='+str(code))
                try:
                    port=int((private/'.web-client.port').read_text());require(1024<=port<=65535 and port!=60720,'Unsafe QA port')
                    candidate=f'http://127.0.0.1:{port}'
                    if json.loads(get(candidate,'/api/config')[1])['configured'] is False:url=candidate;break
                except (OSError,ValueError):pass
                time.sleep(.1)
            if not url:
                print('QA_DIAGNOSTIC_PENDING_PID='+str(row[0].pid),flush=True)
                # Preserve the process handle while a diagnostic dialog is observed.
                row[0].wait(timeout=120);code=exit_code(row)
                raise RuntimeError('No HTTP-ready; actual process returncode='+str(code))
            row[1].update(url=url,http_ready_at_utc=utc(),http_ready_ms=round((time.perf_counter()-row[2])*1000,3))
            require(json.loads(get(url,'/api/status')[1])=={'configured':False,'managers':[]},'Synthetic profile unexpectedly configured')
            for route,name in (('/','index.html'),('/client.css','client.css'),('/client.js','client.js')):
                status,body=get(url,route);require(status==200 and hashlib.sha256(body).hexdigest()==rows['_internal/web_assets/'+name],'Frozen asset mismatch')
            native=ps('$p=Get-Process -Id '+str(row[0].pid)+";[pscustomobject]@{exe=$p.Path;python_dll=@($p.Modules|Where-Object {$_.ModuleName -eq 'python312.dll'}|ForEach-Object {$_.FileName});listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -eq "+str(row[0].pid)+'}|Select-Object LocalAddress,LocalPort)}|ConvertTo-Json -Compress -Depth 4',clean(env))
            require(native['returncode']==0,'Native QA state unavailable');native=json.loads(native['stdout'])
            require(len(native['listeners'])==1 and native['listeners'][0]['LocalAddress']=='127.0.0.1','Unexpected QA listeners')
            require(len(native['python_dll'])==1 and Path(native['python_dll'][0]).is_relative_to(PAYLOAD),'Python runtime not bundled')
            for repeat in range(0 if args.diagnose else 2):
                duplicate=launch('duplicate_'+str(cycle+1)+'_'+str(repeat+1));duplicate[0].wait(timeout=20)
                require(exit_code(duplicate)==0 and row[0].poll() is None and int((private/'.web-client.port').read_text())==port,'Single-instance check failed')
            result['cycles'].append({'cycle':cycle+1,'pid':row[0].pid,'port':port,'native':native,'asset_hashes_verified':3,'repeat_launches':0 if args.diagnose else 2})
            stop(row,url);require(not (private/'.web-client.port').exists(),'Stale QA port file')
        result['status']='PASS'
    except Exception as error:
        result.update(status='REPRODUCED FAILURE' if args.diagnose else 'BLOCKED',error_type=type(error).__name__,error=safe(str(error)))
    finally:
        for row in children:
            if row[0].poll() is None and row[1].get('url'):
                try:stop(row,row[1]['url'])
                except Exception as error:result['cleanup_error']=safe(str(error))
            exit_code(row)
            if row[0].poll() is not None:row[3].close();row[4].close()
        if private.exists():
            inherited=dict(env)
            if os.environ.get('PSModulePath'):inherited['PSMODULEPATH']=os.environ['PSModulePath']
            result['acl_inherited_environment']=acl(private,inherited);result['acl_system_modules_environment']=acl(private,clean(env))
            result['synthetic_files']=sorted(p.name for p in private.iterdir())
        result['after']=baseline();require(result['after']==before,'Protected baseline changed')
        result.update(protected_state_unchanged=True,completed_at_utc=utc());save(output,result)
        print(json.dumps({k:result[k] for k in ('status','mode','qa_run','protected_state_unchanged')},ensure_ascii=False),flush=True)
    return 0 if result['status'] in ('PASS','REPRODUCED FAILURE') else 1

if __name__=='__main__':raise SystemExit(main())
