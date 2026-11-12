import hashlib,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'QA'/'Source'
evidence_path=ROOT/'EVIDENCE.json'
evidence=json.loads(evidence_path.read_text(encoding='utf-8'))
commands=[('client_unittest',[sys.executable,'-X','utf8','-B','-m','unittest','discover','-s','Client_Ultra_LLM','-q']),
 ('js_syntax',['node','--check','Client_Ultra_LLM/web_assets/client.js']),
 ('legacy_chrome',['node','Client_Ultra_LLM/test_browser_control_stream.mjs']),
 ('p0_source_chrome',['node','Client_Ultra_LLM/test_browser_stream_source.mjs']),
 ('p1_source_chrome',['node','Client_Ultra_LLM/test_browser_slots_source.mjs'])]
for name,command in commands:
    print('RUN '+name,flush=True);began=time.perf_counter()
    result=subprocess.run(command,cwd=SOURCE,capture_output=True,timeout=180,env={**os.environ,'PYTHONUTF8':'1'})
    row={'name':name,'command':command,'cwd':str(SOURCE),'exit_code':result.returncode,'seconds':round(time.perf_counter()-began,3),
         'stdout':result.stdout.decode('utf-8',errors='replace'),'stderr':result.stderr.decode('utf-8',errors='replace')}
    evidence['stages'].append(row);evidence_path.write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    print(('PASS ' if result.returncode==0 else 'FAIL ')+name,flush=True)
    if result.returncode:sys.exit(result.returncode)
