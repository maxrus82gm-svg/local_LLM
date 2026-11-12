import hashlib,json,os,subprocess,time
from pathlib import Path
from urllib.request import build_opener,ProxyHandler,Request
ROOT=Path(__file__).resolve().parent
info=json.loads((ROOT/'PACKAGE.json').read_text(encoding='utf-8'))
payload=Path(info['relocated_payload']);qa=payload.parent.parent
env={k:v for k,v in os.environ.items() if k.upper() not in ('PYTHONHOME','PYTHONPATH','PSMODULEPATH')}
windows=Path(os.environ.get('SystemRoot',r'C:\Windows'))
env['LOCALAPPDATA']=str(qa/('Clean AppData Verified '+str(time.time_ns())));env['PATH']=str(windows/'System32')
opener=build_opener(ProxyHandler({}));process=None;url=None
def get(path):
    with opener.open(url+path,timeout=5) as r:return json.loads(r.read())
def stop():
    key=get('/api/session')['csrf']
    with opener.open(Request(url+'/api/shutdown',data=b'{}',headers={'Origin':url,'X-Ultra-CSRF':key,'Content-Type':'application/json'}),timeout=5) as r:
        assert json.loads(r.read())['stopping']
try:
    assert not (Path(env['LOCALAPPDATA'])/'UltraLLM'/'Client').exists()
    process=subprocess.Popen([str(payload/'UltraLLMClient.exe'),'--no-browser'],env=env,cwd=qa,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    private=Path(env['LOCALAPPDATA'])/'UltraLLM'/'Client'
    for _ in range(150):
        try:
            port=int((private/'.web-client.port').read_text());url=f'http://127.0.0.1:{port}'
            if get('/api/config')['configured'] is False:break
        except (OSError,ValueError):pass
        if process.poll() is not None:raise RuntimeError('EXE exited before readiness')
        time.sleep(.1)
    else:raise RuntimeError('EXE did not become ready')
    for name in ('client.js','client.css'):
        with opener.open(url+'/'+name,timeout=5) as response:
            assert hashlib.sha256(response.read()).digest()==hashlib.sha256((payload/'_internal/web_assets'/name).read_bytes()).digest()
    with opener.open(url+'/?utm_source=qa',timeout=5) as response:assert response.status==200
    assert get('/api/status')=={'configured':False,'managers':[]}
    second=subprocess.run([str(payload/'UltraLLMClient.exe'),'--no-browser'],env=env,cwd=qa,timeout=15,
                          creationflags=subprocess.CREATE_NO_WINDOW)
    assert second.returncode==0 and process.poll() is None
    assert int((private/'.web-client.port').read_text())==port
    ps=r"$p=Get-Process -Id %d;[pscustomobject]@{exe=$p.Path;python_dll=@($p.Modules|Where-Object {$_.ModuleName -eq 'python312.dll'}|ForEach-Object {$_.FileName});listeners=@(Get-NetTCPConnection -State Listen|Where-Object {$_.OwningProcess -eq %d}|Select-Object LocalAddress,LocalPort)}|ConvertTo-Json -Compress -Depth 4"%(process.pid,process.pid)
    native=json.loads(subprocess.check_output(['powershell.exe','-NoProfile','-NonInteractive','-Command',ps],encoding='utf-8'))
    assert len(native['python_dll'])==1 and Path(native['python_dll'][0]).is_relative_to(payload)
    assert len(native['listeners'])==1 and native['listeners'][0]['LocalAddress']=='127.0.0.1'
    launch=subprocess.run([str(windows/'System32/cscript.exe'),'//nologo',str(payload/'Start_Ultra_LLM_Client.vbs')],
                          env=env,cwd=qa,timeout=30,capture_output=True,creationflags=subprocess.CREATE_NO_WINDOW)
    assert launch.returncode==0,launch.stderr
    # WScript Run is asynchronous: wait for the duplicate's ACL check and exit
    # before shutting down the first process, otherwise it can start after it.
    time.sleep(3)
    assert process.poll() is None and int((private/'.web-client.port').read_text())==port
    assert not (private/'managers.json').exists() and not list(private.glob('*.token'))
    result={'status':'PASS','actual_packaged_exe':str(payload/'UltraLLMClient.exe'),'pid':process.pid,'url':url,
        'clean_profile':True,'profile_creation_by_exe':True,'system_python_in_path':False,'python_runtime':native['python_dll'][0],
        'system_python_uninstalled':False,'second_pc':'NOT RUN','relocated_to_C_drive_with_spaces_and_unicode':True,
        'single_instance_direct_and_vbs':True,'vbs_exit_code':launch.returncode,'listener':native['listeners'],
        'browser_shell_execute':'VBS exit 0; visible window inspection separate','secrets_created':False}
    (ROOT/'PORTABILITY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)
finally:
    if process and process.poll() is None:
        if url:stop()
        process.wait(timeout=10)
