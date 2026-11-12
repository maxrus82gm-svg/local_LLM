"""OWNER GO Stage D, home Client only. No model/server mutation or filesystem deletion.

--prepare verifies all backups and rehearses operational rollback on a QA shortcut.
--execute requires the successful rehearsal, switches the real shortcut once, and
automatically uses only that tested recovery on any subsequent failure.
"""
import argparse, datetime, hashlib, json, os, shutil, socket, sqlite3, subprocess, sys, time, uuid
from pathlib import Path
from urllib.request import build_opener, ProxyHandler, Request

ROOT=Path(__file__).resolve().parents[3]
REPORT=Path(__file__).resolve().parent
TASK='CODEX-UL-ROOT-CLIENT-MIGRATION-20261112-001'
BACKUPS=ROOT/'Backups/Client'/TASK
ROLLBACK=BACKUPS/'Rollback_R5_Complete'
PAYLOAD=ROOT/'Test/ClientMigration_20261112/R5'
TARGET=ROOT/'Production/Client'
OLD=Path(r'M:\UltraLLM_Client')
DESKTOP_LINK=Path(os.environ['USERPROFILE'])/'Desktop/Ultra LLM Client.lnk'
PS=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
ENV={k:v for k,v in os.environ.items() if k.upper() not in ('PSMODULEPATH','PYTHONPATH','PYTHONHOME')}
ENV['PYTHONDONTWRITEBYTECODE']='1'
OPENER=build_opener(ProxyHandler({}))
JOURNAL={'task_id':TASK,'owner_go':'Explicit user Stage D authorization, 13.11.2026','events':[]}

def utc():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def require(value,message):
    if not value:raise RuntimeError(message)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(name):return json.loads((REPORT/name).read_text(encoding='utf-8'))
def save(name,data):(REPORT/name).write_bytes((json.dumps(data,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))
def event(name,**data):
    JOURNAL['events'].append({'at_utc':utc(),'event':name,**data});save('stage_d_transaction.json',JOURNAL)
def literal(p):return "'"+str(p).replace("'","''")+"'"
def ps(script,env=None):
    prefix='[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);$OutputEncoding=[Console]::OutputEncoding;$ErrorActionPreference="Stop";'
    p=subprocess.run([str(PS),'-NoProfile','-NonInteractive','-Command',prefix+script],env=env or ENV,cwd=ROOT,
        capture_output=True,timeout=30,creationflags=subprocess.CREATE_NO_WINDOW)
    require(p.returncode==0,'PowerShell local helper failed: '+p.stderr.decode('utf-8',errors='replace')[:800])
    raw=p.stdout.decode('utf-8-sig').strip();return json.loads(raw) if raw else None
def filemap(folder):
    require(folder.is_dir() and not folder.is_symlink() and not folder.is_junction(),'Untrusted directory: '+str(folder))
    result={}
    for p in folder.rglob('*'):
        require(not p.is_symlink() and not p.is_junction(),'Link in release/backup')
        if p.is_file():result[p.relative_to(folder).as_posix()]=digest(p)
    return result
def verify(folder,expected):require(filemap(folder)==expected,'File/hash drift: '+str(folder))
def native():
    return ps(r'''$sid=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;$rows=@(Get-CimInstance Win32_Process -Filter "Name='UltraLLMClient.exe'"|ForEach-Object {$p=$_;$id=$p.ProcessId;[pscustomobject]@{pid=$id;exe=$p.ExecutablePath;creation_utc=$p.CreationDate.ToUniversalTime().ToString('o');owner_verified=((Invoke-CimMethod -InputObject $p -MethodName GetOwnerSid).Sid -eq $sid);listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -eq $id}|Select-Object LocalAddress,LocalPort)}});[pscustomobject]@{clients=$rows}|ConvertTo-Json -Compress -Depth 5''')['clients']
def client(folder):
    rows=[r for r in native() if Path(r['exe']).resolve()==(folder/'UltraLLMClient.exe').resolve()]
    require(len(rows)==1,'Expected exactly one Client at '+str(folder));row=rows[0]
    require(row['owner_verified'] and len(row['listeners'])==1 and row['listeners'][0]['LocalAddress']=='127.0.0.1','Client ownership/listener unverified')
    return row
def origin(row):return 'http://127.0.0.1:'+str(row['listeners'][0]['LocalPort'])
def get(url,path):
    require(url.startswith('http://127.0.0.1:'),'Only loopback Client API permitted')
    with OPENER.open(url+path,timeout=12) as r:
        require(r.headers.get('Server','').startswith('UltraLLMWeb/'),'Unexpected Client server');return json.loads(r.read())
def stop(row):
    # Same PID/creation/path/owner/port immediately before the only allowed POST.
    current=next((r for r in native() if r['pid']==row['pid']),None)
    require(current==row,'Process identity drift; refuse shutdown')
    url=origin(row);key=get(url,'/api/session')['csrf']
    with OPENER.open(Request(url+'/api/shutdown',data=b'{}',headers={'Origin':url,'X-Ultra-CSRF':key,'Content-Type':'application/json'}),timeout=8) as r:
        require(json.loads(r.read())['stopping'] is True,'Local shutdown rejected')
    for _ in range(20):
        if not any(r['pid']==row['pid'] and r['creation_utc']==row['creation_utc'] for r in native()):return
        time.sleep(.2)
    raise RuntimeError('Graceful stop unconfirmed; no force termination')
def shortcut(link):
    return ps('$s=New-Object -ComObject WScript.Shell;$l=$s.CreateShortcut('+literal(link)+');[pscustomobject]@{target=$l.TargetPath;arguments=$l.Arguments;working_directory=$l.WorkingDirectory;description=$l.Description;icon=$l.IconLocation;hotkey=$l.Hotkey;window_style=$l.WindowStyle}|ConvertTo-Json -Compress')
def set_shortcut(link,folder):
    require(folder.resolve().is_relative_to(ROOT),'Shortcut destination escaped workspace')
    require(link==DESKTOP_LINK or link.resolve().is_relative_to(ROOT/'Test/ClientMigration_20261112'),'Unexpected shortcut file')
    require((folder/'Start_Ultra_LLM_Client.vbs').is_file(),'Launcher missing')
    args='"'+str(folder/'Start_Ultra_LLM_Client.vbs')+'"'
    wscript=PS.parents[2]/'wscript.exe'
    require(wscript.is_file() and wscript.parent.name.casefold()=='system32','System WScript path invalid')
    ps('$s=New-Object -ComObject WScript.Shell;$l=$s.CreateShortcut('+literal(link)+');$l.TargetPath='+literal(wscript)+';$l.Arguments='+literal(args)+';$l.WorkingDirectory='+literal(folder)+';$l.Save()')
    value=shortcut(link);require(value['arguments']==args and Path(value['working_directory'])==folder,'Shortcut validation failed');return value
def launch(link,folder,env,configured):
    ps('Start-Process -FilePath '+literal(link)+' -WindowStyle Hidden',env)
    for _ in range(35):
        try:
            row=client(folder)
            if get(origin(row),'/api/config')['configured'] is configured:
                time.sleep(2);row=client(folder);return row
        except (RuntimeError,OSError,ValueError):pass
        time.sleep(.2)
    raise RuntimeError('Shortcut Client readiness not confirmed: '+str(folder))
def recovery(link,env,configured,failed=None):
    expected=read('stage_d_preflight.json')['payload_files']
    verify(ROLLBACK,expected)
    if failed:stop(failed)
    # Operational recovery goes to full backup; never to the old missing VBS.
    settings=set_shortcut(link,ROLLBACK)
    row=launch(link,ROLLBACK,env,configured)
    return {'process':row,'shortcut':settings,'url':origin(row),'target':str(ROLLBACK)}
def profile_metadata():
    private=Path(os.environ['LOCALAPPDATA'])/'UltraLLM/Client';require(private.is_dir(),'Existing user profile missing')
    aggregate=[]
    for p in sorted(private.iterdir()):
        if p.is_file() and p.name!='.web-client.port' and not p.name.startswith('chat_history.sqlite3'):
            aggregate.append(p.name.encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
    dbpath=private/'chat_history.sqlite3';require(dbpath.is_file(),'Existing history missing')
    with sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True) as db:
        count,first,last=db.execute('SELECT count(*),min(id),max(id) FROM messages').fetchone()
        schema=db.execute('PRAGMA user_version').fetchone()[0]
        require(db.execute('PRAGMA integrity_check').fetchone()[0]=='ok','History integrity failure')
    return {'profile_file_count':len(aggregate),'profile_secret_aggregate_sha256':hashlib.sha256(b''.join(aggregate)).hexdigest(),
        'history_messages':count,'history_min_id':first,'history_max_id':last,'history_sha256':digest(dbpath),'schema':schema,'integrity':'ok','contents_exported':False}
def preflight():
    require(socket.gethostname().casefold()=='desktop-sc96d3u','Home host required')
    require(ROOT==Path(r'M:\GitHub\local_LLM'),'Original workspace required')
    inventory=read('inventory.json');backup_manifest=json.loads((BACKUPS/'manifest.json').read_text(encoding='utf-8'))
    zip_path=ROOT/'Releases/Client/Imported_Packages_20261112/CODEX-UL-CLIENT-DEPLOY-20261112-001_20261112_173219/UltraLLM_Client_STREAM_SLOTS_R5_Win64.zip'
    require(digest(zip_path)==inventory['zip_sha256'],'R5 ZIP SHA mismatch')
    expected=filemap(PAYLOAD);require(len(expected)==73,'Expected 73 R5 files')
    require(backup_manifest['complete_r5']==expected,'Complete backup manifest mismatch')
    verify(ROLLBACK,expected);verify(OLD,inventory['old_file_hashes']);verify(BACKUPS/'Installed_Original_68_files',inventory['old_file_hashes'])
    require(digest(DESKTOP_LINK)==inventory['shortcut_sha256']==digest(BACKUPS/'Ultra LLM Client.lnk'),'Original shortcut hash mismatch')
    old=client(OLD)
    require(old['pid']==29492 and old['creation_utc']=='2026-11-12T12:49:36.6123520Z','Old Client identity changed')
    require(len(native())==1,'Unaccounted Client process before migration')
    require(not TARGET.exists() or (TARGET.is_dir() and not any(TARGET.iterdir())),'Production contains unknown files')
    # Read-only real Client metadata, no generation or model control.
    state=get(origin(old),'/api/status');require(any(m.get('status')=='online' for m in state.get('managers',[])),'Real Manager not ONLINE')
    for m in state.get('managers',[]):
        for slot in m.get('data',{}).get('slots',[]):
            scheduler=slot.get('scheduler') or {}
            require(scheduler.get('active',0)==0 and scheduler.get('queued',0)==0,'Model request in flight; refuse cutover')
    result={'status':'PASS','at_utc':utc(),'host':socket.gethostname(),'old_process':old,'old_port':old['listeners'][0]['LocalPort'],
        'shortcut':shortcut(DESKTOP_LINK),'shortcut_sha256':digest(DESKTOP_LINK),'zip_sha256':inventory['zip_sha256'],
        'zip':str(zip_path),'payload_files':expected,'old_files_verified':68,'backup_original_verified':68,'backup_complete_verified':73,
        'original_link_backup_verified':True,'production_was_absent':not TARGET.exists(),'profile':profile_metadata(),
        'source_head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()}
    save('stage_d_preflight.json',result);return result
def prepare():
    before=preflight();stamp=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]
    qa=ROOT/'Test/ClientMigration_20261112/StageD'/stamp;qa.mkdir(parents=True)
    snapshot=BACKUPS/('StageD_'+stamp);snapshot.mkdir()
    shutil.copyfile(DESKTOP_LINK,snapshot/'Original_Desktop.lnk');require(digest(snapshot/'Original_Desktop.lnk')==before['shortcut_sha256'],'New link backup mismatch')
    save('stage_d_shortcut_backup.json',{'path':str(snapshot/'Original_Desktop.lnk'),'sha256':before['shortcut_sha256'],'settings':before['shortcut']})
    env=dict(ENV);env.update(LOCALAPPDATA=str(qa/'AppData'),TEMP=str(qa/'Temp'),TMP=str(qa/'Temp'),TMPDIR=str(qa/'Temp'));(qa/'Temp').mkdir()
    sandbox=qa/'SandboxClient';shutil.copytree(PAYLOAD,sandbox);verify(sandbox,before['payload_files'])
    qa_link=qa/'Rollback_Test.lnk';set_shortcut(qa_link,sandbox)
    simulated=launch(qa_link,sandbox,env,False)
    require(get(origin(simulated),'/api/status')=={'configured':False,'managers':[]},'QA profile unexpectedly configured')
    # Exercise the same recovery function that production failures would use.
    recovered=recovery(qa_link,env,False,simulated)
    require(get(recovered['url'],'/api/status')=={'configured':False,'managers':[]},'Recovery QA profile configured')
    with OPENER.open(recovered['url']+'/client.js',timeout=4) as r:require(hashlib.sha256(r.read()).hexdigest()==before['payload_files']['_internal/web_assets/client.js'],'Recovery served wrong assets')
    stop(recovered['process'])
    # Verify actual existing-profile ACL/mutex compatibility without stopping it.
    child=subprocess.run([str(ROLLBACK/'UltraLLMClient.exe'),'--no-browser'],env=ENV,cwd=qa,timeout=20,creationflags=subprocess.CREATE_NO_WINDOW)
    require(child.returncode==0,'Backup cannot read/attach existing profile')
    require(client(OLD)==before['old_process'] and len(native())==1,'Rollback rehearsal changed existing Client')
    require(profile_metadata()==before['profile'],'User data changed during preflight')
    require(digest(DESKTOP_LINK)==before['shortcut_sha256'],'Desktop shortcut changed in rehearsal')
    verify(ROLLBACK,before['payload_files']);verify(OLD,read('inventory.json')['old_file_hashes'])
    staged=qa/'ProductionPayload';shutil.copytree(PAYLOAD,staged);verify(staged,before['payload_files'])
    outcome={'status':'PASS','at_utc':utc(),'qa_directory':str(qa),'qa_shortcut':str(qa_link),'simulated_process':simulated,
        'recovered_process':recovered['process'],'recovery_target':str(ROLLBACK),'recovered_assets_verified':True,
        'existing_profile_duplicate_exit':child.returncode,'desktop_shortcut_unchanged':True,'old_client_unchanged':True,
        'profile_unchanged':True,'old_broken_VBS_used':False,'staged_payload':str(staged),'staged_files':73}
    save('stage_d_rollback_rehearsal.json',outcome);print(json.dumps(outcome,ensure_ascii=False,indent=2))
def execute():
    rehearsal=read('stage_d_rollback_rehearsal.json');require(rehearsal['status']=='PASS','Rollback not verified')
    before=preflight();staged=Path(rehearsal['staged_payload']);verify(staged,before['payload_files'])
    require(staged.resolve().is_relative_to(ROOT/'Test/ClientMigration_20261112'),'Stage path escaped workspace')
    JOURNAL.update(status='EXECUTING',started_at_utc=utc(),preflight=before,rollback_rehearsal='PASS')
    event('ready_before_old_shutdown')
    old_stopped=False
    try:
        stop(before['old_process']);old_stopped=True;event('old_client_gracefully_stopped',pid=before['old_process']['pid'])
        require(not native(),'Unexpected Client before install')
        TARGET.parent.mkdir(parents=True,exist_ok=True)
        if TARGET.exists():
            require(not any(TARGET.iterdir()),'Unknown files appeared in target');shutil.copytree(staged,TARGET,dirs_exist_ok=True)
        else:
            require(TARGET.resolve().is_relative_to(ROOT/'Production'),'Production path escaped root');os.rename(staged,TARGET)
        verify(TARGET,before['payload_files']);event('installed_verified',files=73,path=str(TARGET))
        settings=set_shortcut(DESKTOP_LINK,TARGET);event('desktop_shortcut_switched_once',settings=settings,sha256=digest(DESKTOP_LINK))
        current=launch(DESKTOP_LINK,TARGET,ENV,True);event('production_started_from_shortcut',process=current,url=origin(current))
        require(len(native())==1,'Competing Client after cutover')
        status=get(origin(current),'/api/status');require(any(m.get('status')=='online' for m in status.get('managers',[])),'Real Manager unavailable')
        require(profile_metadata()==before['profile'],'User data changed during migration')
        JOURNAL.update(status='INSTALLED / LIVE SMOKE PENDING',current_process=current,current_url=origin(current),profile_unchanged=True,completed_at_utc=utc())
        save('stage_d_transaction.json',JOURNAL)
        print(json.dumps({'status':JOURNAL['status'],'process':current,'url':origin(current)},indent=2))
    except Exception as error:
        event('migration_failed',error=str(error),old_stopped=old_stopped)
        if old_stopped:
            candidates=native();require(len(candidates)<=1,'Unknown competing processes; refuse broad rollback stop')
            failed=candidates[0] if candidates else None
            if failed:require(Path(failed['exe']).resolve()==(TARGET/'UltraLLMClient.exe').resolve(),'Unknown Client; no rollback kill')
            recovered=recovery(DESKTOP_LINK,ENV,True,failed);event('tested_recovery_completed',recovery=recovered)
            JOURNAL.update(status='PARTIAL / ROLLED BACK TO FULL WORKSPACE R5 BACKUP',recovery=recovered)
        else:JOURNAL['status']='BLOCKED / OLD CLIENT RETAINED'
        save('stage_d_transaction.json',JOURNAL);raise

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--prepare',action='store_true');parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    require(args.prepare!=args.execute,'Choose exactly one action')
    try:
        prepare() if args.prepare else execute()
    except Exception as error:
        if args.prepare:
            name='stage_d_prepare_failures.json';prior=read(name) if (REPORT/name).exists() else {'attempts':[]}
            prior['attempts'].append({'at_utc':utc(),'error':str(error),'production_changed':TARGET.exists(),
                'original_shortcut_sha256':digest(DESKTOP_LINK),'clients':native()});save(name,prior)
        raise
