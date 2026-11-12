"""Local Client release transaction. No remote execution or model API POST.
Default is read-only rollback validation. --install/--rollback require owner authorization.
"""
import argparse,hashlib,json,os,shutil,subprocess,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,Request
ROOT=Path(__file__).resolve().parent
INSTALLED=Path(r'M:\UltraLLM_Client')
BACKUPS=Path(r'M:\UltraLLM_Builds\Stable_Backups')
SHORTCUT=Path(os.environ['USERPROFILE'])/'Desktop/Ultra LLM Client.lnk'
BEFORE=json.loads((ROOT/'BEFORE.json').read_text(encoding='utf-8'))
PACKAGE=json.loads((ROOT/'PACKAGE.json').read_text(encoding='utf-8'))
BACKUP=json.loads((ROOT/'BACKUP.json').read_text(encoding='utf-8'))
ENV={k:v for k,v in os.environ.items() if k.upper()!='PSMODULEPATH'}
OPENER=build_opener(ProxyHandler({}))
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def files(path):return {p.relative_to(path).as_posix():digest(p) for p in path.rglob('*') if p.is_file()}
def verify(path,expected):
    assert path.is_dir() and not path.is_symlink() and not path.is_junction()
    assert files(path)==expected,'File set/hash drift: '+str(path)
def ps(script):
    return json.loads(subprocess.check_output([r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe','-NoProfile','-NonInteractive','-Command',script],env=ENV,encoding='utf-8-sig'))
def native():
    script=r'''$me=[Security.Principal.WindowsIdentity]::GetCurrent().User.Value;$p=@(Get-CimInstance Win32_Process -Filter "Name='UltraLLMClient.exe'");[pscustomobject]@{current_sid=$me;processes=@($p|ForEach-Object {$id=$_.ProcessId;[pscustomobject]@{pid=$id;exe=$_.ExecutablePath;creation=$_.CreationDate.ToUniversalTime().ToString('o');sid=(Invoke-CimMethod -InputObject $_ -MethodName GetOwnerSid).Sid;ports=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -eq $id}|Select-Object LocalAddress,LocalPort)}})}|ConvertTo-Json -Compress -Depth 5'''
    return ps(script)
def request(origin,path,post=None):
    headers={}
    if post is not None:
        key=request(origin,'/api/session')['csrf']
        headers={'Origin':origin,'X-Ultra-CSRF':key,'Content-Type':'application/json'}
    req=Request(origin+path,headers=headers,data=json.dumps(post).encode() if post is not None else None)
    with OPENER.open(req,timeout=12) as response:
        assert response.headers.get('Server','').startswith('UltraLLMWeb/')
        return json.loads(response.read())
def running():
    snapshot=native();candidates=[p for p in snapshot['processes'] if Path(p['exe']).resolve()==(INSTALLED/'UltraLLMClient.exe').resolve()]
    assert len(candidates)==1 and len(snapshot['processes'])==1,'Competing/unverified Client process'
    item=candidates[0];assert item['sid']==snapshot['current_sid'] and len(item['ports'])==1
    assert item['ports'][0]['LocalAddress']=='127.0.0.1'
    return item,'http://127.0.0.1:'+str(item['ports'][0]['LocalPort'])
def stop():
    item,origin=running()
    assert request(origin,'/api/shutdown',{})['stopping'] is True
    for _ in range(30):
        state=native()
        if not any(p['pid']==item['pid'] and p['creation']==item['creation'] for p in state['processes']):return item
        time.sleep(.2)
    raise RuntimeError('Graceful shutdown not confirmed; no force kill')
def launch():
    for name in tuple(os.environ):
        if name.upper()=='PSMODULEPATH':os.environ.pop(name)
    os.startfile(SHORTCUT)
    private=Path(os.environ['LOCALAPPDATA'])/'UltraLLM/Client'
    for _ in range(100):
        try:
            origin='http://127.0.0.1:'+str(int((private/'.web-client.port').read_text()))
            if request(origin,'/api/config')['configured']:
                item,actual=running();assert actual==origin;return item,origin
        except (OSError,ValueError,AssertionError):pass
        time.sleep(.2)
    raise RuntimeError('New Client/shortcut readiness not confirmed')
def save(name,data):(ROOT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--install',action='store_true');parser.add_argument('--rollback',action='store_true');args=parser.parse_args()
    assert not (args.install and args.rollback)
    old_expected={r['path']:r['sha256'] for r in BEFORE['installed_files']}
    verify(Path(BACKUP['backup_path']),old_expected)
    new_expected=files(Path(PACKAGE['release_dir']))
    assert len(new_expected)==73 and digest(Path(PACKAGE['zip']))==PACKAGE['zip_sha256']
    shortcut_hash=digest(SHORTCUT)
    if not args.install and not args.rollback:
        print(json.dumps({'rollback_validation':'PASS','backup_files':len(old_expected),'installation_touched':False}));return
    assert INSTALLED.resolve()==Path(r'M:\UltraLLM_Client')
    if args.install:
        evidence=json.loads((ROOT/'EVIDENCE.json').read_text(encoding='utf-8'))
        for name in ('client_unittest','js_syntax','legacy_chrome','p0_source_chrome','p1_source_chrome','p0_packaged_exe_tls_chrome','p1_packaged_exe_tls_chrome'):
            assert [s for s in evidence['stages'] if s['name']==name][-1]['exit_code']==0,name
        assert json.loads((ROOT/'PORTABILITY.json').read_text(encoding='utf-8'))['status']=='PASS'
        verify(INSTALLED,old_expected)
        stage=Path(r'M:\UltraLLM_Client.stage_CLIENT_DEPLOY_20261112_173219')
        retired=BACKUPS/'UltraLLM_Client_R4_retired_CLIENT_DEPLOY_20261112_173219'
        expected=new_expected;source=Path(PACKAGE['release_dir'])
    else:
        verify(INSTALLED,new_expected)
        stage=Path(r'M:\UltraLLM_Client.rollback_stage_20261112_173219')
        retired=BACKUPS/('UltraLLM_Client_R5_rollback_'+str(time.time_ns()))
        expected=old_expected;source=Path(BACKUP['backup_path'])
    assert not stage.exists() and not retired.exists()
    assert retired.resolve().is_relative_to(BACKUPS.resolve())
    assert stage.parent==INSTALLED.parent and stage.name.startswith('UltraLLM_Client.')
    shutil.copytree(source,stage);verify(stage,expected)
    previous,origin=running()
    status=request(origin,'/api/status')
    assert all(s.get('scheduler',{}).get('active',0)==0 for m in status.get('managers',[]) for s in m.get('data',{}).get('slots',[]) if s.get('scheduler')),'Generation active; refuse shutdown'
    stopped=stop()
    verify(INSTALLED,old_expected if args.install else new_expected)
    os.rename(INSTALLED,retired)
    try:
        os.rename(stage,INSTALLED);verify(INSTALLED,expected)
        item,origin=launch();assert digest(SHORTCUT)==shortcut_hash
        status=request(origin,'/api/status')
        assert status.get('configured') is True and any(m.get('status')=='online' for m in status.get('managers',[]))
        save('INSTALL.json' if args.install else 'ROLLBACK_EXECUTED.json',{'status':'PASS','operation':'install' if args.install else 'rollback',
             'installed_path':str(INSTALLED),'retired_path':str(retired),'backup_path':BACKUP['backup_path'],
             'verified_files':len(expected),'shortcut_path':str(SHORTCUT),'shortcut_sha256':shortcut_hash,
             'previous_process':stopped,'current_process':item,'url':origin,'manager_online':True,'source_commit':evidence['source_commit'] if args.install else None})
        print(json.dumps({'status':'PASS','path':str(INSTALLED),'pid':item['pid'],'url':origin,'verified_files':len(expected),'shortcut_unchanged':True},indent=2))
    except Exception:
        # Preserve failed files; restore the original folder only after a proven stop.
        if INSTALLED.exists():
            snapshot=native()
            if snapshot['processes']:stop()
            quarantine=BACKUPS/('UltraLLM_Client_failed_'+str(time.time_ns()))
            assert quarantine.resolve().is_relative_to(BACKUPS.resolve())
            os.rename(INSTALLED,quarantine)
        os.rename(retired,INSTALLED);launch()
        save('INSTALL_AUTO_ROLLBACK.json',{'status':'RESTORED_ORIGINAL','shortcut_unchanged':digest(SHORTCUT)==shortcut_hash})
        raise
if __name__=='__main__':main()
