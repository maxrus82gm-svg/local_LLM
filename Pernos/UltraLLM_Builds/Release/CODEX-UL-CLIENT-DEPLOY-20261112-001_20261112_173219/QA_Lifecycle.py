import hashlib,json,os,runpy,sqlite3,time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
d=runpy.run_path(str(ROOT/'Deploy_Client.py'))
first,origin=d['running']()
for _ in range(2):
    for key in tuple(os.environ):
        if key.upper()=='PSMODULEPATH':os.environ.pop(key)
    os.startfile(d['SHORTCUT']);time.sleep(3)
    repeated,repeated_origin=d['running']()
    assert repeated['pid']==first['pid'] and repeated_origin==origin
stopped=d['stop']();assert stopped['pid']==first['pid']
current,url=d['launch']();assert current['pid']!=stopped['pid']
status=d['request'](url,'/api/status')
assert any(m['status']=='online' for m in status['managers'])
private=Path(os.environ['LOCALAPPDATA'])/'UltraLLM/Client'
baseline=json.loads((ROOT/'BEFORE.json').read_text(encoding='utf-8'))['user_preservation_baseline']
nonhistory=[]
for p in sorted(private.iterdir()):
    if p.is_file() and p.name!='.web-client.port' and not p.name.startswith('chat_history.sqlite3'):
        nonhistory.append(p.name.encode()+b'\0'+hashlib.sha256(p.read_bytes()).digest())
assert hashlib.sha256(b''.join(nonhistory)).hexdigest()==baseline['profile_secret_aggregate_sha256']
with sqlite3.connect((private/'chat_history.sqlite3').as_uri()+'?mode=ro',uri=True) as db:
    h=hashlib.sha256();count=0
    for row in db.execute('SELECT id,manager_id,slot_id,model_id,role,content FROM messages ORDER BY id'):
        h.update(json.dumps(row,ensure_ascii=False).encode());count+=1
    assert count==baseline['history_messages'] and h.hexdigest()==baseline['history_original_columns_sha256']
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    version=db.execute('PRAGMA user_version').fetchone()[0]
assert hashlib.sha256(d['SHORTCUT'].read_bytes()).hexdigest()==json.loads((ROOT/'INSTALL.json').read_text(encoding='utf-8'))['shortcut_sha256']
result={'status':'PASS','existing_shortcut_repeated_launches':2,'duplicate_processes':0,'same_pid_on_repeat':first['pid'],
    'graceful_shutdown_confirmed':True,'restart_from_existing_shortcut':True,'final_process':current,'final_url':url,
    'real_manager_online':True,'profile_and_secret_files_unchanged':True,'history_messages_preserved':count,
    'history_original_content_unchanged':True,'sqlite_integrity':'ok','schema_before':baseline['history_schema'],'schema_after':version,
    'schema_change':'Additive instance_id/reasoning_content and chat_requests; original rows unchanged','shortcut_bytes_unchanged':True}
(ROOT/'LIFECYCLE.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
