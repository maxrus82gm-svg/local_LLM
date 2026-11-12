"""Run existing browser assertions against the frozen EXE, fake TLS Manager only.
Only the private QA copy of offline_stream_host is adapted; production source is unchanged.
"""
import json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent;source=ROOT/'QA'/'Source'
host=source/'Client_Ultra_LLM/offline_stream_host.py'
original=host.read_text(encoding='utf-8')
start='    local=ThreadingHTTPServer(("127.0.0.1",0),None)'
end='    print(json.dumps('
left=original.index(start);right=original.index(end,left)
replacement='''    from urllib.request import build_opener, ProxyHandler, Request
    client_exe=Path(os.environ["UL_QA_BUNDLE_EXE"])
    client=subprocess.Popen([str(client_exe),"--config-dir",str(root),"--no-browser"],
        creationflags=subprocess.CREATE_NO_WINDOW)
    local_port=None
    for attempt in range(150):
        try:
            local_port=int((root/".web-client.port").read_text())
            with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{local_port}/api/config",timeout=1) as response:
                assert json.loads(response.read())["configured"] is True
            break
        except (OSError,ValueError):time.sleep(0.1)
        if client.poll() is not None:raise RuntimeError("Frozen Client exited before readiness")
    else:raise RuntimeError("Frozen Client readiness timeout")
'''
changed=original[:left]+replacement+original[right:]
prepare='''    qa_environment={k:v for k,v in os.environ.items() if k.upper()!="PSMODULEPATH"}
    qa_environment["LOCALAPPDATA"]=str(root)
    subprocess.run([str(Path(os.environ.get("SystemRoot",r"C:\\Windows"))/"System32/WindowsPowerShell/v1.0/powershell.exe"),
        "-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(HERE/"Prepare-ClientPrivate.ps1")],
        env=qa_environment,capture_output=True,check=True,creationflags=subprocess.CREATE_NO_WINDOW)
    root=root/"UltraLLM"/"Client"
'''
changed=changed.replace('    root.mkdir(exist_ok=True)\n','    root.mkdir(exist_ok=True)\n'+prepare,1)
shutdown='''        if client.poll() is None:
            origin=f"http://127.0.0.1:{local_port}"
            opener=build_opener(ProxyHandler({}))
            with opener.open(origin+"/api/session",timeout=3) as response:csrf=json.loads(response.read())["csrf"]
            with opener.open(Request(origin+"/api/shutdown",data=b"{}",headers={"Origin":origin,"X-Ultra-CSRF":csrf,"Content-Type":"application/json"}),timeout=3) as response:response.read()
            client.wait(timeout=10)
'''
changed=changed.replace('        allow_answer.set();allow_done.set()\n','        allow_answer.set();allow_done.set()\n'+shutdown,1)
assert changed!=original
host.write_bytes(changed.encode('utf-8'))
payload=json.loads((ROOT/'PACKAGE.json').read_text(encoding='utf-8'))['relocated_payload']
env={k:v for k,v in os.environ.items() if k.upper()!='PSMODULEPATH'}
env.update(UL_QA_BUNDLE_EXE=str(Path(payload)/'UltraLLMClient.exe'),PYTHONUTF8='1')
try:
    slots_test=source/'Client_Ultra_LLM/test_browser_slots_source.mjs'
    slots_original=slots_test.read_text(encoding='utf-8')
    slots_test.write_text(slots_original.replace('  browser.setDialogAcceptance(true);',
        '  await until(\'!isRefreshing && !refreshQueued && !document.querySelector("[data-slot-id=slot2] button").disabled\');\n  browser.setDialogAcceptance(true);'),encoding='utf-8')
    for name,file in [('p1_packaged_exe_tls_chrome','test_browser_slots_source.mjs')]:
        print('RUN '+name,flush=True);began=time.perf_counter()
        command=['node',str(source/'Client_Ultra_LLM'/file)]
        result=subprocess.run(command,cwd=source,env=env,capture_output=True,timeout=180)
        row={'name':name,'scope':'Actual frozen EXE / source TLS Manager / fake Colibri and resource telemetry',
            'command':command,'exit_code':result.returncode,'seconds':round(time.perf_counter()-began,3),
            'stdout':result.stdout.decode('utf-8',errors='replace'),'stderr':result.stderr.decode('utf-8',errors='replace')}
        evidence_path=ROOT/'EVIDENCE.json';evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
        evidence['stages'].append(row);evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
        print(('PASS ' if result.returncode==0 else 'FAIL ')+name,flush=True)
        if result.returncode:sys.exit(result.returncode)
finally:
    host.write_bytes(original.encode('utf-8'))
    slots_test.write_bytes(slots_original.encode('utf-8'))
