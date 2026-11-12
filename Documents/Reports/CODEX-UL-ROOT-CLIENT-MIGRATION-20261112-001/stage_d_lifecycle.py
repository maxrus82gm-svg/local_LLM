"""Actual production Client lifecycle checks under the explicit Stage D OWNER GO."""
import ctypes, importlib.util, json, time
from pathlib import Path
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('migration',ROOT/'stage_d.py');d=importlib.util.module_from_spec(spec);spec.loader.exec_module(d)
before=d.read('stage_d_preflight.json');transaction=d.read('stage_d_transaction.json')
require=d.require
row=d.client(d.TARGET);require(row==transaction['current_process'],'Production identity drift before lifecycle')
shortcut_hash=d.digest(d.DESKTOP_LINK)
result={'task_id':d.TASK,'status':'RUNNING','started_at_utc':d.utc(),'initial_process':row,'repeats':[],'contents_exported':False}
d.save('stage_d_lifecycle.json',result)
try:
    for iteration in range(2):
        repeated=d.launch(d.DESKTOP_LINK,d.TARGET,d.ENV,True)
        require(repeated==row and len(d.native())==1,'Repeat launch created competing/changed process')
        require(d.digest(d.DESKTOP_LINK)==shortcut_hash,'Repeat changed shortcut')
        result['repeats'].append({'iteration':iteration+1,'pid':repeated['pid'],'same_identity_and_port':True,'client_count':1})
        d.save('stage_d_lifecycle.json',result)
    status=d.get(d.origin(row),'/api/status')
    for m in status.get('managers',[]):
        for s in m.get('data',{}).get('slots',[]):
            require((s.get('scheduler') or {}).get('active',0)==0,'Request active; do not interrupt')
    # Hold only this verified process for an actual graceful-shutdown exit code.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_bool,ctypes.c_ulong];kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_ulong)]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x1000,False,row['pid']);require(handle,'Cannot retain own process for exit evidence')
    try:
        d.stop(row);exitcode=ctypes.c_ulong();require(kernel.GetExitCodeProcess(handle,ctypes.byref(exitcode)),'Exit code unavailable')
        require(exitcode.value==0,'Graceful Client exit was nonzero')
        result['graceful_exit_code']=exitcode.value
    finally:kernel.CloseHandle(handle)
    require(not d.native(),'Client remained after graceful shutdown')
    restarted=d.launch(d.DESKTOP_LINK,d.TARGET,d.ENV,True)
    require(restarted['pid']!=row['pid'] and len(d.native())==1,'Restart identity/count invalid')
    require(d.digest(d.DESKTOP_LINK)==shortcut_hash,'Restart changed shortcut')
    profile=d.profile_metadata();require(profile==before['profile'],'History/profile/secret data drift')
    status=d.get(d.origin(restarted),'/api/status')
    managers=[{'manager_id':m.get('manager_id'),'status':m.get('status'),'slots':len(m.get('data',{}).get('slots',[])),
        'inventory_models':len(m.get('data',{}).get('models',[])),'streaming':m.get('data',{}).get('chat',{}).get('streaming') is True,
        'dynamic_slots':isinstance(m.get('data',{}).get('control',{}).get('slots'),list)} for m in status.get('managers',[])]
    require(any(m['status']=='online' and m['inventory_models']>0 for m in managers),'Real Manager/catalogue unavailable')
    d.verify(d.TARGET,before['payload_files']);d.verify(d.OLD,d.read('inventory.json')['old_file_hashes']);d.verify(d.ROLLBACK,before['payload_files'])
    result.update(status='PASS',final_process=restarted,final_url=d.origin(restarted),shortcut_sha256=shortcut_hash,
        shortcut_settings=d.shortcut(d.DESKTOP_LINK),profile=profile,profile_history_unchanged=True,
        managers=managers,old_files_unchanged=True,production_files_verified=73,rollback_files_verified=73,
        completed_at_utc=d.utc(),actual_model_generation=False,model_control=False)
    d.save('stage_d_lifecycle.json',result)
    print(json.dumps(result,ensure_ascii=False,indent=2))
except Exception as error:
    result.update(status='FAILED',error=str(error),at_utc=d.utc());d.save('stage_d_lifecycle.json',result)
    candidates=d.native();require(len(candidates)<=1,'Competing processes; refuse unverified recovery')
    failed=candidates[0] if candidates else None
    if failed:require(Path(failed['exe']).resolve()==(d.TARGET/'UltraLLMClient.exe').resolve(),'Unknown process; refuse recovery stop')
    recovered=d.recovery(d.DESKTOP_LINK,d.ENV,True,failed)
    result.update(status='PARTIAL / TESTED ROLLBACK EXECUTED',recovery=recovered);d.save('stage_d_lifecycle.json',result)
    raise
