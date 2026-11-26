// Real SOURCE API/SQLite/TLS/Chrome; engines and resource telemetry are fixtures.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromeSession,delay} from './browser_qa_helpers.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=await fs.mkdtemp(path.join(process.env.UL_QA_ROOT || here,'.slots-source-qa-'));
let fixture,browser;
const statusTrace=[];
const phaseTrace=[];
const mark=stage=>phaseTrace.push({stage,ms:Date.now()});
try{
  fixture=spawn('py',['-3.12','-X','utf8','-B',path.join(here,'offline_stream_host.py'),path.join(root,'fixture'),'--control'],{windowsHide:true,stdio:['pipe','pipe','pipe']});
  mark('fixture_spawned');
  let output='',stderr='';fixture.stderr.on('data',d=>stderr+=d.toString());
  const host=await new Promise((resolve,reject)=>{
    const deadline=setTimeout(()=>reject(Error('Fixture startup deadline '+stderr)),20000);
    fixture.stdout.on('data',d=>{output+=d.toString();const end=output.indexOf('\n');if(end>=0){clearTimeout(deadline);try{resolve(JSON.parse(output.slice(0,end)));}catch(e){reject(e);}}});
    fixture.on('exit',code=>{if(code)reject(Error(`Fixture ${code}: ${stderr}`));});
  });
  mark('fixture_ready');
  await fetch(host.upstream+'/__qa/benchmark');
  browser=await chromeSession(host.url,path.join(root,'chrome'));
  mark('chrome_ready');
  const {evaluate,until}=browser;
  let nextProbe=0;
  async function armFault(mode,count=1){
    const probe=String(++nextProbe);
    const response=await fetch(`${host.upstream}/__qa/status_fault/${mode}/${probe}/${count}`);
    assert.equal(response.status,204);
    return probe;
  }
  async function status(probe=null){
    // Capture only status/shape; never include private snapshot fields in evidence.
    const sampled=performance.now();
    const options=probe===null?'':`,{headers:{"X-QA-Status-Probe":${JSON.stringify(probe)}}}`;
    const view=await evaluate(`fetch('/api/status'${options}).then(async r=>{
      let p;try{p=await r.json()}catch{return {http:r.status,kind:'invalid_json'}}
      const m=Array.isArray(p?.managers)?p.managers.find(x=>x?.manager_id==='qa-manager'):null;
      const d=m?.data,c=d?.control;
      return {http:r.status,manager_status:m?.status??null,error_class:m?.error??p?.error??null,
        kind:d===null?'null':typeof d,control:!!c,
        instances:Array.isArray(c?.instances)?c.instances.map(i=>({slot:i.slot_id,state:i.state,released:!!i.released})):null,
        slots:Array.isArray(c?.slots)?c.slots.map(s=>({slot:s.slot_id,model:s.model_key,mode:s.mode,port:s.api_port})):null};
    }).catch(e=>({http:0,kind:'network_error',error_class:e.name}))`);
    statusTrace.push({ms:Date.now(),elapsed_ms:Math.round(performance.now()-sampled),...view});
    return view;
  }
  async function refreshWithProbe(probe){
    const started=performance.now();
    while(performance.now()-started<5000){
      await until('!isRefreshing && !refreshQueued');
      const result=await evaluate(`(async()=>{
        if(isRefreshing||refreshQueued)return {busy:true};
        const original=window.fetch;let targeted=0,sawNull=false;
        window.fetch=(input,options)=>{
          if(input==='/api/status'&&targeted===0){
            targeted=1;
            return original.call(window,input,{...options,headers:{...(options?.headers||{}),
              "X-QA-Status-Probe":${JSON.stringify(probe)}}}).then(async response=>{
                const payload=await response.clone().json();
                sawNull=payload.managers?.[0]?.data===null;
                return response;
              });
          }
          return original.call(window,input,options);
        };
        try{await refresh(true);return {busy:false,targeted,saw_null:sawNull};}
        finally{window.fetch=original;}
      })()`);
      if(!result.busy)return result;
    }
    throw Error('Targeted refresh did not become idle within 5 s');
  }
  async function waitStatus(label,predicate,timeoutMs=22000,probe=null){
    const start=performance.now();let last;
    do{
      last=await status(probe);
      if(last.http===200&&last.manager_status==='online'&&last.control&&predicate(last))return last;
      await delay(100);
    }while(performance.now()-start<timeoutMs);
    throw Error(`Status deadline ${label}: ${JSON.stringify({elapsed_ms:Math.round(performance.now()-start),last,
      recent:statusTrace.slice(-8)})}`);
  }
  const data=async()=>{
    const start=performance.now();
    do{
      await waitStatus('complete status',()=>true);
      const value=await evaluate('api("/api/status").then(x=>x.managers?.find(m=>m.manager_id==="qa-manager")?.data??null).catch(()=>null)');
      if(value?.control&&Array.isArray(value.control.instances)&&Array.isArray(value.control.slots))return value;
      await delay(100);
    }while(performance.now()-start<22000);
    throw Error(`Status data deadline: ${JSON.stringify(statusTrace.slice(-8))}`);
  };
  await until('document.querySelectorAll(".working-slot").length===3');
  mark('default_slots_rendered');
  assert.equal((await data()).control.models.every(m=>m.installation_checked===true&&m.files_present===true),true);
  assert.equal(await evaluate('Boolean(document.querySelector(".slot-catalog").compareDocumentPosition(document.querySelector(".working-slots")) & Node.DOCUMENT_POSITION_FOLLOWING)'),true);
  assert.equal(await evaluate('document.querySelector("[data-slot-id=slot1] select").disabled'),true);
  const row=slot=>`document.querySelector('[data-slot-id="${slot}"]')`;
  assert.equal(await evaluate('document.querySelector("[data-slot-id=slot1] .slot-context").textContent.startsWith("Контекст ")'),true);
  const action=(slot,label)=>`[...${row(slot)}.querySelectorAll(".manager-model-action")].find(x=>x.textContent===${JSON.stringify(label)})`;
  const click=async(slot,label)=>evaluate(`${action(slot,label)}.click()`);
  async function pick(slot,model){
    await evaluate(`{const e=${row(slot)}.querySelector("select");e.value=${JSON.stringify(model)};e.dispatchEvent(new Event("change"));}`);
    await waitStatus(`pick ${slot}`,s=>s.slots?.some(row=>row.slot===slot&&row.model===model));
    await evaluate('refresh()');
    await until(`${row(slot)}.querySelector("select").value===${JSON.stringify(model)} && !slotPending.has("qa-manager:${slot}") && !${action(slot,"Старт CPU")}.disabled`);
  }
  async function ready(slot){
    await waitStatus(`ready ${slot}`,s=>s.instances?.some(i=>i.slot===slot&&i.state==='READY'));
    await evaluate('refresh(true)');
    await until(`${row(slot)}.querySelector(".slot-state").classList.contains("running") && ${action(slot,"Старт CPU")}.disabled && ${action(slot,"Старт CUDA")}.disabled`);
  }
  await pick('slot2','kat');await click('slot2','Старт CPU');await ready('slot2');
  await pick('slot3','kat');await click('slot3','Старт CPU');await ready('slot3');
  let state=await data();
  const twins=state.control.instances.filter(i=>!i.released&&i.model_key==='kat');
  assert.equal(twins.length,2);assert.notEqual(twins[0].instance_id,twins[1].instance_id);assert.notEqual(twins[0].model_id,twins[1].model_id);
  const uiStates=await evaluate(`(() => {
    const manager=structuredClone(chatSnapshot.managers.find(m=>m.manager_id==='qa-manager'));
    const slot=manager.data.slots.find(s=>s.slot_id==='slot2');
    const instance=manager.data.control.instances.find(i=>i.slot_id==='slot2');
    const shown=()=>{const host=document.createElement('div');workspaces(host,manager);return host;};
    slot.availability='busy';
    const runningRow=shown().querySelector('[data-slot-id=slot2]');
    const busy=runningRow.querySelector('.slot-state').textContent;
    const busyTip=runningRow.querySelector('.slot-state').dataset.tip;
    const activeMode=runningRow.querySelector('.slot-active-mode').textContent;
    const greenMode=runningRow.querySelector('.slot-mode-running')?.textContent;
    instance.state='ERROR';instance.reason='runner_action_unconfirmed';
    const errorHost=shown();
    const errorStatus=errorHost.querySelector('[data-slot-id=slot2] .slot-state');
    const error=errorStatus.textContent;
    const errorTip=errorStatus.dataset.tip;
    const stopDisabled=[...errorHost.querySelector('[data-slot-id=slot2]').querySelectorAll('button')].find(b=>b.textContent==='Стоп').disabled;
    manager.data.control.control_models=false;manager.data.control.can_add_slot=false;
    const denied=shown().querySelector('.manager-pairing-note').textContent;
    manager.data.control.control_models=true;
    manager.data.control.instances=[];slot.engine_state='not_running';slot.availability='not_running';
    for(const model of manager.data.control.models)delete model.installation_checked;
    const staleHost=shown();
    const staleStart=[...staleHost.querySelector('[data-slot-id=slot2]').querySelectorAll('button')].find(b=>b.textContent==='Старт CPU').disabled;
    const stopped=staleHost.querySelector('[data-slot-id=slot2] .slot-state').textContent;
    const stoppedMode=staleHost.querySelector('[data-slot-id=slot2] .slot-active-mode').textContent;
    return {busy,busyTip,activeMode,greenMode,error,errorTip,stopDisabled,denied,staleStart,stopped,stoppedMode,verbose:runningRow.querySelectorAll(".slot-resource").length};
  })()`);
  assert.equal(uiStates.busy,"Запущен");
  assert.match(uiStates.busyTip,/выполняет запрос/);
  assert.equal(uiStates.activeMode,"CPU");
  assert.equal(uiStates.greenMode,"Старт CPU");
  assert.equal(uiStates.error,"Ошибка");
  assert.match(uiStates.errorTip,/runner_action_unconfirmed/);
  assert.equal(uiStates.stopped,"Остановлен");
  assert.equal(uiStates.stoppedMode,"—");
  assert.equal(uiStates.verbose,0);
  assert.equal(uiStates.stopDisabled,true);
  assert.match(uiStates.denied,/set-control-models/);
  assert.equal(uiStates.staleStart,true,'Old folder-only Manager catalogue must not enable Start');
  const rejected=async body=>evaluate(`pairingPost('/api/control',${JSON.stringify({manager_id:'qa-manager',...body})})
    .then(()=>'unexpected',error=>error.message)`);
  assert.match(await rejected({op:'start',slot_id:'slot2',model_key:'kat',mode:'cpu',request_id:'d'.repeat(32)}),/no_free_authorized_slot/);
  assert.match(await rejected({op:'start',slot_id:'slot3',model_key:'not-installed',mode:'cpu',request_id:'e'.repeat(32)}),/invalid_model_or_mode/);
  assert.match(await rejected({op:'stop',instance_id:'0'.repeat(32),request_id:'f'.repeat(32)}),/instance_not_authorized/);
  await evaluate('showChats()');
  await until('!byId("chat-new").disabled');
  async function uiChat(slot,message,count){
    await evaluate('byId("chat-new").click()');
    await until(`document.querySelectorAll('.chat-choice').length===${count}`);
    const chatId=await evaluate('chatSelected');
    await evaluate(`{const target=chatTargets.find(t=>t.slot_id===${JSON.stringify(slot)});
      const manager=byId('chat-manager');manager.value=target.manager_id;manager.dispatchEvent(new Event('change'));
      const select=byId('chat-model');select.value=targetKey(target);select.dispatchEvent(new Event('change'));}`);
    await until(`!chatMutation && currentChat()?.chat_id===${JSON.stringify(chatId)} &&
      currentChat()?.slot_id===${JSON.stringify(slot)} && !byId("chat-send").disabled`);
    const submitted=await evaluate(`(()=>{
      byId('chat-stream').checked=false;byId('chat-input').value=${JSON.stringify(message)};
      byId('chat-form').requestSubmit();
      const request=conversation(${JSON.stringify(chatId)}).request;
      return {started:!!request,slot:request?.target.slot_id??null};
    })()`);
    assert.deepEqual(submitted,{started:true,slot},'One explicit UI submit must start the exact chat/slot; no retry');
    mark('ui_chat_submitted_'+slot);
    await until(`byId('chat-messages').textContent.includes(${JSON.stringify(message)}) &&
      byId('chat-messages').textContent.includes('Фиктивный ответ экземпляра') &&
      !conversation(${JSON.stringify(chatId)}).request &&
      !releasingSlots.has(slotKey(currentChat())) && !byId('chat-send').disabled`);
    mark('ui_chat_completed_'+slot);
    assert.equal(await evaluate('document.querySelectorAll(".chat-message-metrics").length'),2);
    return chatId;
  }
  const chatA=await uiChat('slot2','qa-ui-one',1);
  const chatB=await uiChat('slot3','qa-ui-two',2);
  assert.notEqual(chatA,chatB);
  await evaluate(`selectChat(${JSON.stringify(chatA)})`);
  await until('byId("chat-messages").textContent.includes("qa-ui-one")');
  assert.equal(await evaluate('byId("chat-messages").textContent.includes("qa-ui-two")'),false);
  await evaluate('showOverview()');
  browser.setDialogAcceptance(true);
  for(const slot of ['slot4','slot5']){
    await evaluate('document.querySelector(".add-slot").click()');
    await until(`document.querySelector('[data-slot-id="${slot}"]')!==null`);
    await pick(slot,'qwen36');
    if(slot==='slot4'){
      await until('Boolean(document.querySelector("[data-slot-id=slot4] .slot-cuda-config"))');
      await evaluate('document.querySelector("[data-slot-id=slot4] .slot-cuda-config").click()');
      assert.equal(await evaluate('byId("pre-cuda-budget").value'),"");
      assert.equal(await evaluate('byId("pre-cuda-target").value'),"");
      assert.equal(await evaluate('byId("pre-cuda-gpu-mode").value'),"legacy");
      assert.equal(await evaluate('byId("pre-cuda-gpu-devices").querySelectorAll("[data-gpu-id]").length'),2);
      await evaluate('byId("pre-cuda-target").value="7.1";byId("pre-cuda-save").click()');
      await until('!byId("cuda-prelaunch-dialog") && !isRefreshing && !refreshQueued');
      const pre=(await data()).control;
      assert.equal(pre.slots.find(s=>s.slot_id===slot).cuda_profile.target_gib,7.1);
      assert(!pre.instances.some(i=>i.slot_id===slot&&!i.released));
    }
    await click(slot,'Старт CUDA');await ready(slot);
  }
  browser.setDialogAcceptance(false);
  state=await data();
  const active=state.control.instances.filter(i=>!i.released);
  assert.equal(active.length,4);
  assert.equal(active.filter(i=>i.mode==='cuda').length,2);
  assert.equal(new Set(active.map(i=>i.instance_id)).size,4);
  assert.equal(new Set(state.control.slots.map(s=>s.api_port)).size,5);
  assert(state.control.slots.every(s=>s.api_port!==host.ipv6_occupied_port));
  const sendPayload=(item,message,id)=>({manager_id:'qa-manager',slot_id:item.slot_id,model_id:item.model_id,instance_id:item.instance_id,chat_id:item.slot_id==='slot2'?chatA:chatB,message,request_id:id});
  const one=twins.find(i=>i.slot_id==='slot2'),two=twins.find(i=>i.slot_id==='slot3');
  // Real simultaneous Client -> TLS Manager -> independent fake Colibri APIs.
  const pair=await evaluate(`Promise.all(${JSON.stringify([sendPayload(one,'instance one','a'.repeat(32)),sendPayload(two,'instance two','b'.repeat(32))])}.map(body=>pairingPost("/api/chat/send",body)))`);
  assert.equal(pair[0].messages.at(-2).content,'instance one');assert.equal(pair[1].messages.at(-2).content,'instance two');
  assert(!pair[0].messages.some(m=>m.content==='instance two'));
  const concurrency=await(await fetch(host.upstream+'/__qa/metrics')).json();
  assert.equal(concurrency.max_parallel_normal,2);
  await click('slot2','Стоп');
  mark('slot2_stop_requested');
  const uiProbe=await armFault('null');
  // STOP may temporarily saturate the real TLS snapshot path. An untagged
  // transport timeout is not evidence that the tagged fault was consumed.
  // Require an eventual healthy untagged response, then prove the exact
  // armed probe is still present and returned to the intended UI refresh.
  const bystander=await waitStatus('untagged status after stop; armed null probe',()=>true);
  assert.equal(bystander.control,true,'An untagged background status must recover');
  const uiNull=await refreshWithProbe(uiProbe);
  assert.deepEqual(uiNull,{busy:false,targeted:1,saw_null:true});
  await evaluate('refresh(true)');
  await until('!isRefreshing && !refreshQueued');
  assert.deepEqual(browser.errors,[],'Transient null status must not crash UI refresh');
  // Probe IDs bind every fault to the intended request, despite background refreshes.
  for(const mode of ['null','partial','503','delay','disconnect']){
    const probe=await armFault(mode);
    const background=await waitStatus('untagged status; armed '+mode+' probe',()=>true);
    assert.equal(background.control,true,'Untagged status did not recover '+mode);
    const observed=await status(probe);
    assert.equal(observed.http,mode==='disconnect'?0:mode==='503'?503:200);
    if(mode==='null')assert.equal(observed.kind,'null');
    if(mode==='partial'){
      assert.equal(observed.control,false);
      assert.equal((await status(probe)).http,409,'Consumed probe must not replay');
    }
    if(mode==='503')assert.equal(observed.control,false);
    if(mode==='disconnect')assert.equal(observed.kind,'network_error');
  }
  await waitStatus('stopped slot2',s=>s.instances?.some(i=>i.slot==='slot2'&&i.state==='STOPPED'));
  mark('slot2_stopped');
  const rejection=await evaluate(`pairingPost("/api/chat/send",${JSON.stringify(sendPayload(one,'stopped','c'.repeat(32)))}).then(()=>"unexpected",e=>e.message)`);
  assert.match(rejection,/slot_process_unverified|instance_not_ready|model_not_running/);
  state=await data();assert.equal(state.control.instances.find(i=>i.instance_id===two.instance_id).state,'READY');
  await fetch(host.upstream+'/__qa/reload');
  await browser.call('Page.reload');
  await until('document.querySelectorAll(".working-slot").length===5');
  mark('page_reloaded');
  state=await data();assert.equal(state.control.slots.find(s=>s.slot_id==='slot3').model_key,'kat');
  assert.equal(state.control.slots.find(s=>s.slot_id==='slot5').mode,'cuda');
  const storedA=await(await fetch(host.url+'/api/chat/history?chat_id='+chatA)).json();
  const storedB=await(await fetch(host.url+'/api/chat/history?chat_id='+chatB)).json();
  assert(storedA.messages.some(m=>m.content==='qa-ui-one'));
  assert(!storedA.messages.some(m=>m.content==='qa-ui-two'));
  assert(storedB.messages.some(m=>m.content==='qa-ui-two'));
  assert(!storedB.messages.some(m=>m.content==='qa-ui-one'));
  await evaluate('showChats()');
  await until(`chatItems.some(c=>c.chat_id===${JSON.stringify(chatA)}) &&
    chatItems.some(c=>c.chat_id===${JSON.stringify(chatB)})`);
  await evaluate(`selectChat(${JSON.stringify(chatA)})`);
  await until('byId("chat-messages").textContent.includes("qa-ui-one")');
  assert.equal(await evaluate('byId("chat-send").disabled'),true,'Stopped model must not accept a chat');
  await evaluate('byId("chat-context-preset").value="16384";byId("chat-context-preset").dispatchEvent(new Event("change"))');
  await until('!chatMutation && currentChat().context_tokens===16384');
  await evaluate(`selectChat(${JSON.stringify(chatB)})`);
  await until('byId("chat-messages").textContent.includes("qa-ui-two")');
  assert.equal(await evaluate("currentChat().context_tokens"),65536);
  assert.equal(await evaluate('byId("chat-send").disabled'),false,'Other model remains available');
  await evaluate('showOverview()');
  // A burst of unavailable snapshots must hit a finite deadline, never READY.
  const burstProbe=await armFault('503',12);
  const boundedStart=performance.now();
  await assert.rejects(waitStatus('injected 503 burst',()=>true,250,burstProbe),/Status deadline injected 503 burst/);
  const boundedFailureMs=Math.round(performance.now()-boundedStart);
  await waitStatus('recovered after 503 burst',()=>true);
  mark('status_recovered');
  const history=await evaluate(`api("/api/chat/history?"+new URLSearchParams(${JSON.stringify({chat_id:chatB})}))`);
  assert.equal(history.messages.at(-2).content,'instance two');
  // Risk cancellation is a user decision, not a capability/role escalation.
  await fetch(host.upstream+'/__qa/low_ram');await evaluate('refresh()');
  assert.match(await evaluate(`${action('slot2','Старт CPU')}.dataset.tip`),/Ожидаемый остаток RAM/);
  const dialogsBeforeRisk=browser.dialogs.length;
  await click('slot2','Старт CPU');
  await until('!slotPending.has("qa-manager:slot2")');
  state=await data();assert(!state.control.instances.some(i=>i.slot_id==='slot2'&&!i.released));
  assert.equal(browser.dialogs.length,dialogsBeforeRisk+1,"The cancelled CPU start must display its own risk confirmation");
  browser.setDialogAcceptance(true);
  await click('slot2','Старт CPU');await ready('slot2');
  assert.equal(browser.dialogs.length,dialogsBeforeRisk+2,"The accepted CPU start must display a separate risk confirmation");
  state=await data();assert.equal(state.slots.find(s=>s.slot_id==='slot2').context_tokens,16384);
  assert.equal(state.slots.find(s=>s.slot_id==='slot3').context_tokens,32768);
  await until('document.querySelector("[data-slot-id=slot2] .slot-context")?.textContent.replace(/\\s/g,"").includes("16384") && document.querySelector("[data-slot-id=slot3] .slot-context")?.textContent.replace(/\\s/g,"").includes("32768")');
  assert.equal(await evaluate('document.querySelector("[data-slot-id=slot2] .slot-memory").nextElementSibling.classList.contains("slot-context")'),true);
  await fetch(host.upstream+'/__qa/normal_ram');
  await evaluate('showChats()');
  await until('!byId("chat-new").disabled');
  await uiChat('slot4','qa-cuda-settings',3);
  await until('!byId("chat-cuda-panel").classList.contains("hidden")');
  assert.equal(await evaluate('byId("cuda-budget").value'),"");
  assert.equal(await evaluate('byId("cuda-target").value'),"7.1");
  const beforeProfile=(await data()).control.instances.find(i=>i.slot_id==='slot4'&&!i.released);
  await evaluate('byId("cuda-budget").value="10";byId("cuda-budget").dispatchEvent(new Event("input"));byId("cuda-target").value="7.2";byId("cuda-target").dispatchEvent(new Event("input"));byId("cuda-gpu-mode").value="full";byId("cuda-gpu-mode").dispatchEvent(new Event("change"));byId("cuda-save").click()');
  await until('!cudaSaving && !cudaDirty && byId("cuda-save-status").textContent.includes("Стоп → Старт")');
  const savedProfile=(await data()).control;
  assert.equal(savedProfile.slots.find(s=>s.slot_id==='slot4').cuda_profile.budget_gib,10);
  assert.equal(savedProfile.slots.find(s=>s.slot_id==='slot4').cuda_profile.target_gib,7.2);
  assert.equal(savedProfile.slots.find(s=>s.slot_id==='slot4').cuda_profile.gpu_mode,'full');
  assert.deepEqual(savedProfile.slots.find(s=>s.slot_id==='slot4').cuda_profile.gpu_ids,[]);
  assert.equal(await evaluate('byId("cuda-gpu-mode").value'),"full");
  assert.equal(savedProfile.gpu_selection.gpu_restart_supported,true);
  await until('!byId("chat-restart").disabled');
  assert.deepEqual(savedProfile.slots.find(s=>s.slot_id==='slot5').cuda_profile,{budget_gib:null,chain:false,rows:null,target_gib:null});
  assert.equal(savedProfile.instances.find(i=>i.slot_id==='slot4'&&!i.released).instance_id,beforeProfile.instance_id);
  assert.deepEqual(beforeProfile.cuda_profile,{budget_gib:null,chain:false,rows:null,target_gib:7.1});
  assert.deepEqual(savedProfile.instances.find(i=>i.slot_id==='slot4'&&!i.released).cuda_profile,beforeProfile.cuda_profile);
  await evaluate(`selectChat(${JSON.stringify(chatB)})`);
  assert.equal(await evaluate('byId("chat-cuda-panel").classList.contains("hidden")'),true);
  await evaluate('showOverview()');
  // New explicit groups coexist with legacy profiles only after all legacy
  // managed CUDA instances have released. Existing CPU chats remain untouched.
  const A='GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',B='GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
  const reserveUi=await evaluate(`(()=>{
    const holder=document.createElement("div"),picker=gpuPicker(holder,"qa-reserve",()=>{});
    const devices=[{uuid:"GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",name:"A",compute_capability:"8.9",index:0,total_gib:16,free_gib:15,used_gib:1},
                   {uuid:"GPU-bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",name:"B",compute_capability:"8.6",index:1,total_gib:8,free_gib:7,used_gib:1}];
    // Real checkbox activation dispatches input/change only in a connected DOM.
    // Keep the production listeners intact and exercise actual .click().
    document.body.append(holder);
    try {
      picker.update({gpu_mode:"full",gpu_ids:[]},{devices,per_device_reserves:true},true);
      const toggle=holder.querySelector("#qa-reserve-gpu-reserve-enabled");
      if(!toggle.isConnected||toggle.disabled)throw Error("Reserve toggle not interactive");
      toggle.click();
      const inputs=holder.querySelectorAll("[data-gpu-reserve]");
      if(inputs.length!==2)throw Error("Expected two reserve inputs after checking toggle");
      inputs[0].value="3";inputs[0].dispatchEvent(new Event("input"));
      inputs[1].value="1";inputs[1].dispatchEvent(new Event("input"));
      const before=picker.current(), both=Object.values(before.gpu_reserves_gib).sort((a,b)=>a-b);
      const checks=holder.querySelectorAll("[data-gpu-id]");
      checks[1].click();
      const p=picker.current();
      return {both,count:p.gpu_ids.length,reserve:p.gpu_reserves_gib[p.gpu_ids[0]],mode:p.gpu_mode,preview:gpuPreview(p,{devices}).common_weight_cap_gib};
    } finally {holder.remove();}
  })()`);
  assert.deepEqual(reserveUi,{both:[1,3],count:1,reserve:3,mode:"full",preview:10});
  const uiGpuNegative=await evaluate(`(()=>{
    const holder=document.createElement("div"),picker=gpuPicker(holder,"qa-gpu",()=>{});
    const profile={gpu_mode:"manual",gpu_ids:["GPU-aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"]};
    picker.update(profile,{devices:null,legacy_active:false},true);
    const missing=holder.querySelector("[data-gpu-id]");
    const preserved=missing.checked && missing.dataset.gpuId===profile.gpu_ids[0] &&
      picker.current().gpu_ids[0]===profile.gpu_ids[0];
    picker.update(profile,null,true,false);
    const disabled=holder.querySelector("select").disabled;
    const emptyInvalid=!validCudaProfile({budget_gib:null,chain:false,rows:null,target_gib:null,
      gpu_mode:"manual",gpu_ids:[]},[]);
    return {preserved,disabled,emptyInvalid};
  })()`);
  assert.deepEqual(uiGpuNegative,{preserved:true,disabled:true,emptyInvalid:true});
  browser.setDialogAcceptance(true);
  async function stopGpu(slot) {
    await click(slot,'Стоп');
    await waitStatus('GPU release '+slot,s=>s.instances?.some(i=>i.slot===slot&&i.released&&i.state==='STOPPED'));
    await evaluate('refresh(true)');await until('!isRefreshing && !refreshQueued');
  }
  async function saveGpu(slot,mode,ids=[]) {
    await until(`Boolean(document.querySelector('[data-slot-id="${slot}"] .slot-cuda-config'))`);
    await evaluate(`document.querySelector('[data-slot-id="${slot}"] .slot-cuda-config').click()`);
    await evaluate(`{const mode=byId('pre-cuda-gpu-mode');mode.value=${JSON.stringify(mode)};mode.dispatchEvent(new Event('change'));}`);
    for(const id of ids)await evaluate(`{const c=[...byId('pre-cuda-gpu-devices').querySelectorAll('[data-gpu-id]')].find(c=>c.dataset.gpuId===${JSON.stringify(id)});if(!c.checked)c.click();}`);
    await evaluate('byId("pre-cuda-save").click()');
    await until('!byId("cuda-prelaunch-dialog") && !isRefreshing && !refreshQueued');
  }
  await stopGpu('slot4');await stopGpu('slot5');
  await click('slot4','Старт CUDA');await ready('slot4');
  let gpuState=(await data()).control;
  assert.deepEqual(gpuState.instances.find(i=>i.slot_id==='slot4'&&!i.released).gpu_placement,[A,B]);
  assert(gpuState.gpu_selection.devices.every(d=>d.reserved));
  await stopGpu('slot4');
  await saveGpu('slot5','manual',[B]);
  await click('slot5','Старт CUDA');await ready('slot5');
  await saveGpu('slot4','auto');
  await click('slot4','Старт CUDA');await ready('slot4');
  gpuState=(await data()).control;
  assert.deepEqual(gpuState.instances.find(i=>i.slot_id==='slot5'&&!i.released).gpu_placement,[B]);
  assert.deepEqual(gpuState.instances.find(i=>i.slot_id==='slot4'&&!i.released).gpu_placement,[A]);
  assert.equal(gpuState.slots.find(s=>s.slot_id==='slot4').cuda_profile.gpu_mode,'auto');
  assert.deepEqual(gpuState.slots.find(s=>s.slot_id==='slot5').cuda_profile.gpu_ids,[B]);
  await stopGpu('slot4');
  assert.equal((await data()).control.instances.find(i=>i.slot_id==='slot5'&&!i.released).state,'READY');
  await stopGpu('slot5');
  // The real prelaunch dialog must persist the allowlist and individual
  // reserves through Client -> authenticated Manager -> SQLite -> UI reload.
  await until('Boolean(document.querySelector(\'[data-slot-id="slot4"] .slot-cuda-config\'))');
  await evaluate('document.querySelector(\'[data-slot-id="slot4"] .slot-cuda-config\').click()');
  await evaluate(`{const mode=byId('pre-cuda-gpu-mode');mode.value="full";mode.dispatchEvent(new Event("change"));byId('pre-cuda-gpu-reserve-enabled').click();}`);
  await until('byId("pre-cuda-gpu-devices")?.querySelectorAll("[data-gpu-reserve]").length===2');
  await evaluate(`{const box=byId("pre-cuda-gpu-devices");for(const [id,n] of [[${JSON.stringify(A)},3],[${JSON.stringify(B)},1]]){const input=[...box.querySelectorAll("[data-gpu-reserve]")].find(x=>x.dataset.gpuReserve===id);input.value=String(n);input.dispatchEvent(new Event("input"));}const check=[...box.querySelectorAll("[data-gpu-id]")].find(x=>x.dataset.gpuId===${JSON.stringify(B)});if(check.checked)check.click();}`);
  await evaluate('byId("pre-cuda-save").click()');
  await until('!byId("cuda-prelaunch-dialog") && !isRefreshing && !refreshQueued');
  let reserveState=(await data()).control;
  let savedReserve=reserveState.slots.find(s=>s.slot_id==='slot4').cuda_profile;
  assert.equal(savedReserve.gpu_mode,'full');
  assert.deepEqual(savedReserve.gpu_ids,[A]);
  assert.deepEqual(savedReserve.gpu_reserves_gib,{[A]:3});
  await evaluate('document.querySelector(\'[data-slot-id="slot4"] .slot-cuda-config\').click()');
  assert.equal(await evaluate('byId("pre-cuda-gpu-reserve-enabled").checked'),true);
  assert.equal(await evaluate(`[...byId("pre-cuda-gpu-devices").querySelectorAll("[data-gpu-reserve]")].find(x=>x.dataset.gpuReserve===${JSON.stringify(A)}).value`),"3");
  await evaluate('byId("cuda-prelaunch-dialog").close()');
  await until('!byId("cuda-prelaunch-dialog")');
  await click('slot4','Старт CUDA');await ready('slot4');
  reserveState=(await data()).control;
  assert.deepEqual(reserveState.instances.find(i=>i.slot_id==='slot4'&&!i.released).gpu_placement,[A]);
  await stopGpu('slot4');
  mark('per_gpu_reserve_ui_roundtrip');
  mark('multi_gpu_ui_roundtrip');
  assert.deepEqual(browser.errors,[]);
  await evaluate('refresh(true)');
  await until('!isRefreshing && !refreshQueued');
  await browser.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false});
  const layout=await browser.call('Page.getLayoutMetrics');
  const screenshot=await browser.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,
    clip:{x:0,y:0,width:1440,height:Math.ceil(layout.cssContentSize.height),scale:1}});
  await fs.writeFile(path.join(process.env.UL_QA_ROOT || here,'stream_slots_browser.png'),Buffer.from(screenshot.data,'base64'));
  console.log(JSON.stringify({status:'PASS',scope:'SOURCE API + SQLite + TLS + Chrome; fake engines/resources',
    default_slots:3,persisted_slots:5,simultaneous_same_model_cpu:2,simultaneous_same_model_cuda:2,
    unique_instance_ids:true,ipv6_listener_skipped:true,concurrent_chats_isolated:true,
    stop_one_preserves_other:true,controller_and_browser_reload:true,history_preserved:true,
    two_ui_chats_bound_and_persisted:true,per_message_metrics_visible:true,
    context_override_end_to_end:16384,risk_cancel_and_confirm:true,multi_gpu_ui_roundtrip:true,per_gpu_reserve_ui_roundtrip:true,status_faults:['null','partial','503','delay','disconnect','bounded_503_burst'],
    status_samples:statusTrace.length,status_classes:[...new Set(statusTrace.map(s=>s.kind+':'+s.http))],
    phase_trace:phaseTrace,bounded_failure_ms:boundedFailureMs,status_trace:statusTrace,
    console_errors:browser.errors},null,2));
}catch(error){
  if(browser)console.error(JSON.stringify({phase_trace:phaseTrace,status_trace:statusTrace.slice(-12),browser_errors:browser.errors,
    dom:await browser.evaluate('({rows:document.querySelectorAll(".working-slot").length,refreshing:isRefreshing,queued:refreshQueued})').catch(e=>({error_class:e.name}))}));
  throw error;
}finally{
  if(browser)await browser.close();
  if(fixture&&fixture.exitCode===null){fixture.stdin.write('stop\n');for(let i=0;i<80&&fixture.exitCode===null;i++)await delay(100);if(fixture.exitCode===null)fixture.kill();}
  if(!process.env.UL_QA_ROOT)for(let i=0;i<10;i++){try{assert(path.resolve(root).startsWith(path.resolve(here)+path.sep));await fs.rm(root,{recursive:true,force:true});break;}catch{await delay(200);}}
}
