// Real Chrome DOM/stream checks on an ephemeral fake Client API. No live profile.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const here=path.dirname(fileURLToPath(import.meta.url));
import {waitForDevToolsPort} from './browser_qa_helpers.mjs';
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const tmp=await fs.mkdtemp(path.join(process.env.UL_QA_ROOT || here,'.chrome-qa-'));
let chrome,ws,server,release;
let phase='STOPPED', lastControl=null, streamBody=null, normalBody=null;
let restartRisk=false,restartPosts=0,restartPolls=0,restartNew=false,controlEnabled=false,restartFault='';
let statusDelayNext=0;
let statusCount=0;
const runtimeId=()=> (restartNew?'c':'f').repeat(32);
const chats=[];
const errors=[];
const results=[];
const phaseTrace=[];
const mark=stage=>phaseTrace.push({stage,ms:Date.now()});
const markOnce=stage=>{if(!phaseTrace.some(x=>x.stage===stage))mark(stage);};
const model={key:'kat',name:'KAT-Coder V2.5 Dev',directory_name:'KAT',api_ids:['kat'],
  modes:{cpu:{available:true},cuda:{available:false,reason:'vram_telemetry_unknown'}}};
function snapshot(){
  return {configured:true,managers:[{manager_id:'manager-b',name:'Manager B',status:'online',data:{host:'QA B',
    chat:{streaming:true},memory:{state:'live',ddr_generation:'DDR5',installed_gib:64,free_gib:40},models:[{directory_name:'KAT'}],
    slots:Array.from({length:5},(_,i)=>({slot_id:`slot${i+1}`,models:i===0?['legacy']:i===1&&phase==='READY'?['ultra-slot2-kat-cpu']:[],
      engine_state:i===0||i===1&&phase==='READY'?'ready':'not_running',availability:i===0||i===1&&phase==='READY'?'ready_unreserved':'not_running',...(i===1&&phase==='READY'?{instance_id:runtimeId()}:{})})),
    control:{...(controlEnabled?{control_models:true,slots:[{slot_id:'slot2',revision:1}]}:{}),models:[{...model,modes:{...model.modes,cpu:{available:phase==='STOPPED'}}}],
      instances:phase==='STOPPED'?[]:[{instance_id:runtimeId(),model_key:'kat',model_id:'ultra-slot2-kat-cpu',mode:'cpu',slot_id:'slot2',state:phase,released:false,can_stop:phase==='READY'}]}}},
    {manager_id:'manager-a',name:'Manager A',status:'online',data:{host:'QA A',memory:{state:'unknown'},models:[],chat:{streaming:true},
      slots:[{slot_id:'slot1',models:['ultra-slot2-kat-cpu'],instance_id:'e'.repeat(32),
        engine_state:'ready',availability:'ready_unreserved'}],
      control:{models:[],instances:[]}}}]};
}
try {
  server=http.createServer(async(req,res)=>{
    let raw='';for await(const b of req)raw+=b;
    const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
    if(req.url==='/api/session')return json({csrf:'QA-CSRF'});
    if(req.url==='/api/config')return json({configured:true});
    if(req.url==='/api/status'){
      statusCount++;
      markOnce('first_status_request');const sample=snapshot();const wait=statusDelayNext;statusDelayNext=0;
      if(wait)await delay(wait);
      return json(sample);
    }
    if(req.url==='/api/chats'){
      if(req.method==='GET')return json({chats});
      const command=JSON.parse(raw);
      if(command.op==='create'){
        if(command.target && chats.some(c=>c.manager_id===command.target.manager_id&&c.slot_id===command.target.slot_id))
          return json({error:'chat_target_occupied'},409);
        const row={chat_id:String.fromCharCode(97+chats.length).repeat(32),title:'Новый чат',settings:{},...(command.target||{})};
        chats.unshift(row);return json(row);
      }
      const row=chats.find(item=>item.chat_id===command.chat_id);
      if(!row)return json({error:'chat_not_found'},404);
      if(command.op==='delete'){chats.splice(chats.indexOf(row),1);return json({deleted:true});}
      if(command.op==='target')Object.assign(row,command.target || {manager_id:null,slot_id:null,model_id:null});
      if(command.op==='preferences')row.preferences=command.preferences;
      return json(row);
    }
    if(req.url.startsWith('/api/chat/history?'))return json({messages:[]});
    if(req.url.startsWith('/api/chat/metrics?'))return json({results:[]});
    if(req.url.startsWith('/api/chat/restart?')){
      if(restartFault==='timeout')return json({error:'qa_timeout'},503);
      restartPolls++;
      return json({stage:['WAITING_RELEASE','CHECKING','STARTING','READY'][Math.min(restartPolls-1,3)]});
    }
    if(req.url==='/api/chat/restart'){
      restartPosts++;
      if(restartFault==='timeout')return json({error:'qa_timeout'},503);
      if(restartFault==='error')return json({stage:'ERROR',reason:'qa_runner_error'});
      return json(restartRisk?{stage:'RISK_CONFIRMATION_REQUIRED',risk_token:'qa-risk',warnings:[]}:{stage:'STOPPING'});
    }
    if(req.url==='/api/chat/restart/complete'){
      restartNew=true;
      return json({stage:'READY',new_instance_id:runtimeId()});
    }
    if(req.url==='/api/control'){
      lastControl=JSON.parse(raw);phase=lastControl.op==='start'?'STARTING':'STOPPING';
      return json({state:phase,slot_id:'slot2',instance_id:'f'.repeat(32)});
    }
    if(req.url==='/api/chat/stream'){
      streamBody=JSON.parse(raw);
      res.writeHead(200,{'Content-Type':'application/x-ndjson','Cache-Control':'no-store'});
      res.write(JSON.stringify({type:'meta'})+'\n');
      res.write(JSON.stringify({type:'delta',text:'Первый фрагмент'})+'\n');
      release=()=>{res.write(JSON.stringify({type:'delta',text:' и конец'})+'\n');
        res.end(JSON.stringify({type:'done',messages:[{role:'user',content:streamBody.message},
          {role:'assistant',content:'Первый фрагмент и конец'}]})+'\n');};
      return;
    }
    if(req.url==='/api/chat/send'){normalBody=JSON.parse(raw);return json({messages:[{role:'assistant',content:'Обычный ответ'}]});}
    if(req.url==='/api/chat/cancel')return json({cancelled:true});
    const asset={'/':'index.html','/client.js':'client.js','/client.css':'client.css'}[req.url];
    if(asset){if(asset==='client.js')markOnce('client_script_requested');
      res.writeHead(200,{'Content-Type':asset.endsWith('js')?'application/javascript':asset.endsWith('css')?'text/css':'text/html'});
      return res.end(await fs.readFile(path.join(here,'web_assets',asset)));}
    res.writeHead(404);res.end();
  });
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  mark('fixture_listening');
  const origin=`http://127.0.0.1:${server.address().port}`;
  const executable=process.env.ULTRA_QA_CHROME||'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  chrome=spawn(executable,['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check',
    '--disable-background-networking',`--user-data-dir=${tmp}`,'--remote-debugging-port=0',origin],
    {windowsHide:true,stdio:'ignore'});
  mark('chrome_spawned');
  const port=await waitForDevToolsPort(chrome,tmp);
  mark('devtools_port_ready');
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  mark('cdp_connected');
  let id=0;const pending=new Map(),dialogReplies=[];
  ws.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.id){const p=pending.get(msg.id);pending.delete(msg.id);
    if(msg.error)p.reject(Error(msg.error.message));else p.resolve(msg.result);}
    if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);
    if(msg.method==='Page.javascriptDialogOpening')call('Page.handleJavaScriptDialog',{accept:dialogReplies.shift()===true});};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
  await call('Runtime.enable');
  await call('Page.enable');
  mark('runtime_enabled');
  const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  async function until(expression,description=expression){
    const started=performance.now();
    do{if(await evaluate(expression))return;await delay(50);}while(performance.now()-started<12000);
    const diagnostic=await evaluate(`({ready:document.readyState,manager_cards:document.querySelectorAll('.manager').length,
      chat_cards:document.querySelectorAll('.chat-choice').length,
      ready_chat_models:Array.from(document.querySelectorAll('.chat-choice.is-ready b'),label=>label.textContent),
      asset_js:!!document.querySelector('script[src="/client.js"]')})`).catch(e=>({cdp_error:e.name}));
    throw Error('DOM deadline: '+description+' '+JSON.stringify({elapsed_ms:Math.round(performance.now()-started),
      diagnostic,chrome_exit:chrome.exitCode,js_errors:errors.slice(-3)}));
  }
  await until('document.querySelectorAll(".manager").length===2');
  mark('manager_cards_ready');
  assert.equal(await evaluate('document.querySelectorAll(".manager-model-row").length'),3);
  assert.equal(await evaluate('document.querySelectorAll("#slot-table").length'),0);
  results.push('PASS: two Manager identities, duplicate model IDs, one model list per Manager');
  const buttons='[...document.querySelectorAll(".manager-model-row")].find(x=>x.textContent.includes("KAT-Coder")).querySelectorAll("button")';
  assert.deepEqual(await evaluate(`Array.from(${buttons}).map(b=>b.disabled)`),[false,true,true]);
  assert.match(await evaluate(`${buttons}[1].dataset.tip`),/vram_telemetry_unknown/);
  await evaluate(`${buttons}[0].click()`);
  await until('document.querySelector(".manager-model-scroll").textContent.includes("STARTING")');
  assert.equal(lastControl.manager_id,'manager-b');assert.equal(lastControl.op,'start');assert.equal(lastControl.mode,'cpu');
  assert.match(lastControl.request_id,/^[a-f0-9]{32}$/);
  results.push('PASS: CPU/disabled CUDA reason, STARTING, correct Manager identity');
  phase='READY';await evaluate('refresh()');
  assert.equal(await evaluate('document.querySelectorAll(".manager-model-row").length'),3,'Owned API model must not duplicate catalog row');
  assert.equal(await evaluate(`${buttons}[2].disabled`),false);
  await evaluate(`${buttons}[2].click()`);
  await until('document.querySelector(".manager-model-scroll").textContent.includes("STOPPING")');
  assert.equal(lastControl.instance_id,'f'.repeat(32));
  results.push('PASS: STOPPING and stable owned instance_id');
  phase='READY';await evaluate('refresh().then(showChats)');
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===1');
  assert.equal(await evaluate('currentChat().manager_id'),"manager-b");
  assert.equal(await evaluate('currentChat().slot_id'),"slot1");
  assert.equal(await evaluate('byId("chat-manager").value'),"manager-b");
  assert.notEqual(await evaluate('byId("chat-model").value'),"");
  assert.equal(await evaluate('byId("chat-model").options.length'),2);
  assert.deepEqual(await evaluate('[...byId("chat-manager").options].map(o=>o.text)'),
    ['Выберите Manager','Manager B','Manager A']);
  await evaluate('byId("chat-manager").value="manager-a";byId("chat-manager").dispatchEvent(new Event("change"))');
  assert.match(await evaluate('byId("chat-model").options[0].text'),/^KAT-Coder V2.5 Dev/);
  assert.equal(await evaluate('byId("chat-model").textContent.includes("eeeeeeee")'),false);
  await evaluate('(() => { const manager=byId("chat-manager"); manager.value="manager-b"; manager.dispatchEvent(new Event("change")); const select=byId("chat-model"); select.value=targetKey(chatTargets.find(t=>t.model_id==="ultra-slot2-kat-cpu")); select.dispatchEvent(new Event("change")); })()');
  await until('byId("chat-send").disabled===false');
  await evaluate('localStorage.setItem("ultra.chat.instance."+chatSelected,"f".repeat(32));renderLiveStatus()');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Запущен');
  assert.equal(await evaluate('byId("chat-events-scroll").contains(byId("chat-live-status"))'),false);
  for(const [state,label] of [['STOPPING','Останавливается'],['STARTING','Запускается'],['ERROR','Ошибка'],['STOPPED','Остановлен'],['READY','Запущен']]){
    phase=state;await evaluate('refresh()');
    assert.equal(await evaluate('byId("chat-live-status").textContent'),label,state);
  }
  await evaluate('statusSampleTime=performance.now()-8000;renderLiveStatus()');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Состояние неизвестно');
  await evaluate('refresh()');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Запущен');
  const fallbacks=await evaluate(`(() => {
    const original=chatSnapshot;
    const manager=structuredClone(original);
    manager.managers.find(m=>m.manager_id==='manager-b').status='unreachable';
    chatSnapshot=manager;renderLiveStatus();const offline=byId('chat-live-status').textContent;
    manager.managers.find(m=>m.manager_id==='manager-b').status='online';
    delete manager.managers.find(m=>m.manager_id==='manager-b').data.control;
    renderLiveStatus();const oldBackend=byId('chat-live-status').textContent;
    chatSnapshot=structuredClone(original);
    const own=chatSnapshot.managers.find(m=>m.manager_id==='manager-b');
    const slot=own.data.slots.find(s=>s.slot_id==='slot2');
    slot.instance_id='e'.repeat(32);
    own.data.control.instances.find(i=>i.slot_id==='slot2').instance_id='e'.repeat(32);
    renderLiveStatus();const replaced=byId('chat-live-status').textContent;
    chatSnapshot=original;renderLiveStatus();
    return {offline,oldBackend,replaced};
  })()`);
  assert.deepEqual(fallbacks,{offline:'Нет связи',oldBackend:'Состояние неизвестно',replaced:'Перепривяжите модель'});
  statusDelayNext=250;
  const older=evaluate('readStatus()');
  await delay(40);
  phase='STOPPED';await evaluate('readStatus()');
  await older;
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Остановлен','Older READY response must not overwrite STOPPED');
  phase='READY';await evaluate('refresh()');
  const completionOrder=await evaluate(`(async()=>{
    const originalFetch=window.fetch, sample=structuredClone(chatSnapshot), pending=[];
    const response=ok=>new Response(JSON.stringify(ok?sample:{error:"qa_status_failed"}),{
      status:ok?200:503,headers:{"Content-Type":"application/json"}});
    const status=()=>readStatus().catch(()=>false);
    window.fetch=(input,options)=>input==="/api/status"?
      new Promise(resolve=>pending.push(resolve)):originalFetch.call(window,input,options);
    try {
      statusSampleTime=0;renderChatControls();
      const a=status(), b=status();
      pending[0](response(true));const usable=await a;
      const readyWhilePending=byId("chat-live-status").textContent;
      pending[1](response(false));await b;
      const afterFailure=[byId("chat-live-status").textContent,byId("chat-send").disabled];
      const c=status(),d=status();
      pending[3](response(false));await d;
      pending[2](response(true));const ignored=await c;
      const lateReady=[byId("chat-live-status").textContent,byId("chat-send").disabled];
      const e=status(),f=status();
      pending[5](response(true));await f;
      pending[4](response(false));await e;
      return {usable,readyWhilePending,afterFailure,ignored,lateReady,
        lateFailure:[byId("chat-live-status").textContent,byId("chat-send").disabled]};
    } finally {window.fetch=originalFetch;}
  })()`);
  assert.deepEqual(completionOrder,{usable:true,readyWhilePending:'Запущен',
    afterFailure:['Состояние неизвестно',true],ignored:false,
    lateReady:['Состояние неизвестно',true],lateFailure:['Запущен',false]});
  results.push('PASS: pending newer GET cannot discard completed usable status; newer failure wins; late failure cannot invalidate newer success');
  results.push('PASS: offline, old backend, external replacement, out-of-order snapshots');
  results.push('PASS: selected instance READY/STOPPING/STARTING/ERROR/STOPPED, stale fail-closed; header outside scroll');
  await delay(150);
  const started=performance.now();
  await evaluate('document.getElementById("chat-input").value="Привет";document.getElementById("chat-form").requestSubmit()');
  await until('document.getElementById("chat-messages").textContent.includes("Первый фрагмент")');
  const firstMs=Math.round(performance.now()-started);
  assert(release,'No upstream release gate');
  assert.equal(await evaluate('document.getElementById("chat-messages").textContent.includes("и конец")'),false);
  assert.equal(streamBody.manager_id,'manager-b');assert.equal(streamBody.model_id,'ultra-slot2-kat-cpu');
  assert.equal(streamBody.options.thinking,'on');
  release();release=null;
  await until('byId("chat-messages").textContent.includes("Первый фрагмент и конец") && !byId("chat-send").disabled');
  results.push(`PASS: visible real HTTP fragments before completion, browser_first_fragment_ms=${firstMs} (fake model)`);
  await evaluate('byId("chat-stream").checked=false;byId("chat-thinking").checked=false;byId("chat-effort").value="high";byId("chat-thinking").dispatchEvent(new Event("change"))');
  await until('!chatMutation && currentChat().preferences?.thinking===false');
  assert.equal(await evaluate('byId("chat-effort").disabled'),true);
  await evaluate('byId("chat-input").value="Обычный";byId("chat-form").requestSubmit()');
  await until('document.getElementById("chat-messages").textContent.includes("Обычный ответ")');
  assert.equal(normalBody.options.thinking,'off');assert.equal(normalBody.options.reasoning_effort,'auto');
  results.push('PASS: ordinary chat and explicit thinking off');
  const previousOrigin=await evaluate('performance.timeOrigin');
  await call('Page.reload');
  await until('performance.timeOrigin>'+previousOrigin+' && document.querySelectorAll(".manager").length===2');
  await evaluate('showChats()');
  await until('byId("chat-manager").value==="manager-b" && byId("chat-model").value!==""');
  assert.match(await evaluate('document.querySelector(".chat-choice small").textContent'),/^KAT-Coder V2.5 Dev.*CPU/);
  assert(await evaluate('[...byId("chat-model").options].some(o=>o.text.startsWith("KAT-Coder V2.5 Dev · slot2 · CPU"))'));
  assert.match(await evaluate('document.querySelector(".chat-choice small").textContent'),/slot2.*CPU/);
  assert.equal(await evaluate('modelLabel({model_id:"Qwen3.6-35B-A3B",slot_id:"slot1",manager_id:"manager-a"})'),"Qwen 3.6 · slot1");
  assert.equal(await evaluate('document.querySelector(".chat-choice .chat-mode-confirmed").textContent'),"CPU");
  assert.equal(await evaluate('byId("chat-active-mode").textContent'),"CPU");
  assert.equal(await evaluate('byId("chat-form").contains(byId("chat-model"))'),true);
  assert.equal(await evaluate('byId("chat-form").contains(byId("chat-thinking"))'),true);
  assert.equal(await evaluate('byId("chat-form").contains(byId("chat-effort")) && byId("chat-form").contains(byId("chat-history-messages"))'),true);
  assert.equal(await evaluate('document.querySelector(".chat-inspector").contains(byId("chat-effort")) || document.querySelector(".chat-inspector").contains(byId("chat-history-messages"))'),false);
  assert.equal(await evaluate('document.querySelectorAll("#chat-form .chat-tip[data-tip]").length'),6);
  assert.equal(await evaluate('!!document.getElementById("chat-restart")'),true);
  assert.equal(await evaluate('Boolean(byId("chat-context-tip").dataset.tip)'),true);
  // Let composer layout/focus settle before synthetic hover; scroll dismisses tips.
  await delay(350);
  await evaluate('document.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true}));byId("chat-stream").closest("[data-tip]").dispatchEvent(new PointerEvent("pointerover",{bubbles:true}))');
  await until('byId("chat-floating-tip").matches(":popover-open")');
  assert(await evaluate('byId("chat-floating-tip").getBoundingClientRect().bottom < byId("chat-stream").getBoundingClientRect().top'));
  assert.match(await evaluate('byId("chat-floating-tip").textContent'), /генерации/);
  await evaluate('document.dispatchEvent(new PointerEvent("pointerdown",{bubbles:true}))');
  assert.equal(await evaluate('byId("chat-floating-tip").matches(":popover-open")'),false);

  assert.equal(await evaluate('byId("chat-stream").checked'),false);
  assert.equal(await evaluate('byId("chat-thinking").checked'),false);
  assert.equal(await evaluate('Boolean(document.getElementById("chat-metrics"))'),false);
  await evaluate('byId("chat-manager").value="manager-a";byId("chat-manager").dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('byId("chat-send").disabled'),true);
  assert.equal(await evaluate('currentChat().manager_id'), 'manager-b');
  // A pending Manager change must also block a native form submit, not only Enter/click.
  const previousBody=JSON.stringify(streamBody);
  await evaluate('byId("chat-stream").checked=true;byId("chat-input").value="QA pending target";byId("chat-form").requestSubmit()');
  await delay(250);
  assert.equal(JSON.stringify(streamBody),previousBody);
  assert.equal(await evaluate('Boolean(conversation(chatSelected).request)'),false);
  await evaluate('byId("chat-input").value=""');
  const draftOrigin=await evaluate('performance.timeOrigin');
  await call('Page.reload');
  await until('performance.timeOrigin>'+draftOrigin+' && document.querySelectorAll(".manager").length===2');
  await evaluate('showChats()');
  await until('byId("chat-manager").value==="manager-a" && byId("chat-send").disabled');
  await evaluate('{const select=byId("chat-model");select.value=targetKey(chatTargets.find(t=>t.manager_id==="manager-a"));select.dispatchEvent(new Event("change"))}');
  await until('currentChat().manager_id==="manager-a" && !byId("chat-send").disabled');
  const firstChat=await evaluate('chatSelected');
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===2');
  const secondChat=await evaluate('chatSelected');
  assert.notEqual(firstChat,secondChat);
  assert.equal(await evaluate('currentChat().manager_id'),"manager-b");
  assert.equal(await evaluate('currentChat().slot_id'),"slot1");
  assert.equal(await evaluate('byId("chat-stream").checked && byId("chat-thinking").checked'),true);
  await evaluate('byId("chat-manager").value="manager-b";byId("chat-manager").dispatchEvent(new Event("change"))');
  await evaluate('{const select=byId("chat-model");select.value=targetKey(chatTargets.find(t=>t.manager_id==="manager-b" && t.model_id==="ultra-slot2-kat-cpu"));select.dispatchEvent(new Event("change"))}');
  await until('currentChat().manager_id==="manager-b" && !byId("chat-send").disabled');
  await evaluate('selectChat('+JSON.stringify(firstChat)+')');
  assert.equal(await evaluate('byId("chat-manager").value'),'manager-a');
  await evaluate('selectChat('+JSON.stringify(secondChat)+')');
  assert.equal(await evaluate('byId("chat-manager").value'),'manager-b');
  controlEnabled=true;
  await evaluate('refresh()');
  await evaluate('localStorage.setItem("ultra.chat.instance."+chatSelected,"f".repeat(32));renderLiveStatus()');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Запущен');
  dialogReplies.push(false);
  await evaluate('byId("chat-restart").click()');
  assert.equal(restartPosts,0,'Initial cancel must not dispatch Restart');
  restartRisk=true;dialogReplies.push(true,false);
  await evaluate('byId("chat-restart").click()');
  await until('chatRestartJob===null');
  assert.equal(restartPosts,1,'Risk cancel must not dispatch second POST');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Запущен');
  restartRisk=false;restartFault='error';dialogReplies.push(true);
  await evaluate('byId("chat-restart").click()');
  await until('chatRestartJob===null && byId("chat-live-status").textContent==="Ошибка"');
  restartFault='timeout';dialogReplies.push(true);
  await evaluate('byId("chat-restart").click()');
  await until('chatRestartJob===null && byId("chat-live-status").textContent==="Состояние неизвестно"');
  restartFault='';
  restartRisk=false;restartPolls=0;dialogReplies.push(true);
  await evaluate('byId("chat-restart").click()');
  for (const label of ['Остановка модели…','Ожидание освобождения…','Проверка перед запуском…','Запуск модели…'])
    await until('byId("chat-live-status").textContent==='+JSON.stringify(label),label);
  await until('byId("chat-live-status").textContent==="Перезапуск завершён"');
  assert.equal(restartPosts,4,'Each attempt must use one POST, with no automatic retry');
  assert.equal(await evaluate('chatRestartSuccess.instanceId'), 'c'.repeat(32));
  await evaluate('selectChat('+JSON.stringify(firstChat)+')');
  assert.notEqual(await evaluate('byId("chat-live-status").textContent'),'Перезапуск завершён');
  await evaluate('selectChat('+JSON.stringify(secondChat)+')');
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Перезапуск завершён');
  await delay(1600);
  assert.equal(await evaluate('byId("chat-live-status").textContent'),'Перезапуск завершён');
  await until('byId("chat-live-status").textContent==="Запущен"');
  results.push('PASS: Restart confirmations, ERROR/timeout, stages, exact rebind, 3s success and no duplicate POST');
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===3');
  const thirdChat=await evaluate('chatSelected');
  assert.equal(await evaluate('currentChat().slot_id'),"slot1");
  assert.equal(await evaluate('currentChat().manager_id'),"manager-b");
  assert.equal(await evaluate('byId("chat-model").options.length'),1);
  assert.equal(await evaluate('[...byId("chat-model").options].some(o=>o.value===targetKey(chatTargets.find(t=>t.manager_id==="manager-b"&&t.slot_id==="slot2")))'),false);
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===4 && !chatMutation');
  const draftChat=await evaluate('chatSelected');
  assert.equal(await evaluate('byId("chat-manager").value'),"manager-b");
  assert.equal(await evaluate('byId("chat-model").value'),"");
  assert.equal(await evaluate('byId("chat-model").options.length'),0);
  assert.equal(await evaluate('byId("chat-send").disabled'),true);
  assert.equal(await evaluate('Boolean(currentChat().model_id)'),false);
  await evaluate('changeChat("delete",{confirm:true})');
  await until('!chatMutation && !chatItems.some(c=>c.chat_id==='+JSON.stringify(draftChat)+')');
  await evaluate('selectChat('+JSON.stringify(thirdChat)+')');
  await evaluate('changeChat("delete",{confirm:true})');
  await until('!chatMutation && !chatItems.some(c=>c.chat_id==='+JSON.stringify(thirdChat)+')');
  await evaluate('selectChat('+JSON.stringify(secondChat)+')');
  results.push('PASS: automatic top-to-bottom free slot assignment, full capacity draft, manual override');
  // Real instances of one model have distinct generated model IDs. Use the same DOM
  // renderer with a synthetic third slot and an idle Manager.
  const duplicateResult=await evaluate(`(() => {
    const original=chatSnapshot;
    try {
      const payload=structuredClone(original);
      const m=payload.managers.find(x=>x.manager_id==="manager-b");
      const s=m.data.slots.find(x=>x.slot_id==="slot2");
      s.instance_id="f".repeat(32);
      const duplicate="ultra-slot3-kat-cuda-"+"d".repeat(32);
      Object.assign(m.data.slots.find(x=>x.slot_id==="slot3"),{
        models:[duplicate],instance_id:"d".repeat(32),engine_state:"ready",availability:"ready_unreserved"
      });
      m.data.control.instances.push({instance_id:"d".repeat(32),slot_id:"slot3",model_key:"kat",
        model_id:duplicate,mode:"cuda",state:"READY"});
      payload.managers.push({manager_id:"manager-idle",name:"Idle Manager",status:"online",data:{slots:[]}});
      chatSnapshot=payload;renderChatList(payload);
      const options=[...byId("chat-model").options].map(o=>o.text);
      const idle=[...byId("chat-manager").options].some(o=>o.value==="manager-idle");
      return {options,idle};
    } finally {chatSnapshot=original;renderChatList(original);}
  })()`);
  assert(duplicateResult.options.some(x=>x.includes("slot2")&&!x.includes("CPU")));
  assert(duplicateResult.options.some(x=>x.includes("slot3")&&x.includes("CUDA")));
  assert(!duplicateResult.options.some(x=>x.includes("dddddddd")));
  assert.equal(duplicateResult.idle,true);
  results.push('PASS: distinct runtime IDs share one display name; slot/mode distinguish duplicates; idle Manager visible');
  await evaluate('byId("chat-manager").value="";byId("chat-manager").dispatchEvent(new Event("change"))');
  assert.equal(await evaluate('byId("chat-manager").value'),'');
  assert.equal(await evaluate('byId("chat-send").disabled'),true);
  assert.equal(await evaluate('currentChat().manager_id'),'manager-b');
  const blankOrigin=await evaluate('performance.timeOrigin');
  await call('Page.reload');
  await until('performance.timeOrigin>'+blankOrigin+' && document.querySelectorAll(".manager").length===2');
  await evaluate('showChats()');
  await until('byId("chat-manager").value==="" && byId("chat-send").disabled');
  assert.equal(await evaluate('currentChat().manager_id'),'manager-b');
  results.push('PASS: explicitly empty Manager choice remains a draft after F5; direct submit blocked');
  const pollCount=statusCount;
  await delay(4300);
  const observedPolls=statusCount-pollCount;
  assert(observedPolls>=2 && observedPolls<=4,'Open chat must reuse bounded status cadence');
  results.push(`PASS: open-chat refresh cadence ${observedPolls} GETs in 4.3s, one shared poller`);
  results.push('PASS: dependent Manager/model lists, no silent switch, per-chat F5 persistence');
  assert.deepEqual(errors,[]);
  console.log(JSON.stringify({status:'PASS',browser:'Chrome headless (separate temporary profile)',tests:results,
    phase_trace:phaseTrace,console_errors:errors},null,2));
  await call('Browser.close');
} catch(error) {
  console.error(JSON.stringify({phase_trace:phaseTrace,chrome_exit:chrome?.exitCode,js_errors:errors.slice(-3)}));
  throw error;
} finally {
  if(release)release();
  if(ws)ws.close();
  if(chrome&&chrome.exitCode===null){await delay(500);if(chrome.exitCode===null)chrome.kill();}
  if(server)await new Promise(r=>server.close(r));
  if(!process.env.UL_QA_ROOT)for(let i=0;i<10;i++){try{assert(path.resolve(tmp).startsWith(path.resolve(here)+path.sep));await fs.rm(tmp,{recursive:true,force:true});break;}catch{await delay(200);}}
}
