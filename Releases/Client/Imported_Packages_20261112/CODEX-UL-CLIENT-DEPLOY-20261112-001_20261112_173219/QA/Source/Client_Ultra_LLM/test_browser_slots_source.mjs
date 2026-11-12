// Real SOURCE API/SQLite/TLS/Chrome; engines and resource telemetry are fixtures.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromeSession,delay} from './browser_qa_helpers.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=await fs.mkdtemp(path.join(here,'.slots-source-qa-'));
let fixture,browser;
try{
  fixture=spawn('py',['-3.12','-X','utf8','-B',path.join(here,'offline_stream_host.py'),path.join(root,'fixture'),'--control'],{windowsHide:true,stdio:['pipe','pipe','pipe']});
  let output='',stderr='';fixture.stderr.on('data',d=>stderr+=d.toString());
  const host=await new Promise((resolve,reject)=>{
    const deadline=setTimeout(()=>reject(Error('Fixture startup deadline '+stderr)),20000);
    fixture.stdout.on('data',d=>{output+=d.toString();const end=output.indexOf('\n');if(end>=0){clearTimeout(deadline);try{resolve(JSON.parse(output.slice(0,end)));}catch(e){reject(e);}}});
    fixture.on('exit',code=>{if(code)reject(Error(`Fixture ${code}: ${stderr}`));});
  });
  await fetch(host.upstream+'/__qa/benchmark');
  browser=await chromeSession(host.url,path.join(root,'chrome'));
  const {evaluate,until}=browser;
  const data=()=>evaluate('api("/api/status").then(x=>x.managers[0].data)');
  await until('document.querySelectorAll(".working-slot").length===3');
  assert.equal(await evaluate('Boolean(document.querySelector(".slot-catalog").compareDocumentPosition(document.querySelector(".working-slots")) & Node.DOCUMENT_POSITION_FOLLOWING)'),true);
  assert.equal(await evaluate('document.querySelector("[data-slot-id=slot1] select").disabled'),true);
  const row=slot=>`document.querySelector('[data-slot-id="${slot}"]')`;
  const click=async(slot,label)=>evaluate(`[...${row(slot)}.querySelectorAll("button")].find(x=>x.textContent===${JSON.stringify(label)}).click()`);
  async function pick(slot,model){
    await evaluate(`{const e=${row(slot)}.querySelector("select");e.value=${JSON.stringify(model)};e.dispatchEvent(new Event("change"));}`);
    await until(`api("/api/status").then(x=>x.managers[0].data.control.slots.some(s=>s.slot_id===${JSON.stringify(slot)}&&s.model_key===${JSON.stringify(model)}))`);
    await evaluate('refresh()');
    await until(`${row(slot)}.querySelector("select").value===${JSON.stringify(model)} && !slotPending.has("qa-manager:${slot}") && !${row(slot)}.querySelector("button").disabled`);
  }
  async function ready(slot){
    await until(`api("/api/status").then(x=>x.managers[0].data.control.instances.some(i=>i.slot_id===${JSON.stringify(slot)}&&i.state==="READY"))`);
    await evaluate('refresh(true)');
    await until(`${row(slot)}.querySelector(".slot-state").textContent.startsWith("READY") && [...${row(slot)}.querySelectorAll("button")].slice(0,2).every(b=>b.disabled)`);
  }
  await pick('slot2','kat');await click('slot2','Старт CPU');await ready('slot2');
  await pick('slot3','kat');await click('slot3','Старт CPU');await ready('slot3');
  let state=await data();
  const twins=state.control.instances.filter(i=>!i.released&&i.model_key==='kat');
  assert.equal(twins.length,2);assert.notEqual(twins[0].instance_id,twins[1].instance_id);assert.notEqual(twins[0].model_id,twins[1].model_id);
  for(const slot of ['slot4','slot5']){
    await evaluate('document.querySelector(".add-slot").click()');
    await until(`document.querySelector('[data-slot-id="${slot}"]')!==null`);
    await pick(slot,'qwen36');await click(slot,'Старт CUDA');await ready(slot);
  }
  state=await data();
  const active=state.control.instances.filter(i=>!i.released);
  assert.equal(active.length,4);
  assert.equal(active.filter(i=>i.mode==='cuda').length,2);
  assert.equal(new Set(active.map(i=>i.instance_id)).size,4);
  assert.equal(new Set(state.control.slots.map(s=>s.api_port)).size,5);
  assert(state.control.slots.every(s=>s.api_port!==host.ipv6_occupied_port));
  const sendPayload=(item,message,id)=>({manager_id:'qa-manager',slot_id:item.slot_id,model_id:item.model_id,instance_id:item.instance_id,message,request_id:id});
  const one=twins.find(i=>i.slot_id==='slot2'),two=twins.find(i=>i.slot_id==='slot3');
  // Real simultaneous Client -> TLS Manager -> independent fake Colibri APIs.
  const pair=await evaluate(`Promise.all(${JSON.stringify([sendPayload(one,'instance one','a'.repeat(32)),sendPayload(two,'instance two','b'.repeat(32))])}.map(body=>pairingPost("/api/chat/send",body)))`);
  assert.equal(pair[0].messages[0].content,'instance one');assert.equal(pair[1].messages[0].content,'instance two');
  assert(!pair[0].messages.some(m=>m.content==='instance two'));
  const concurrency=await(await fetch(host.upstream+'/__qa/metrics')).json();
  assert.equal(concurrency.max_parallel_normal,2);
  await click('slot2','Стоп');
  await until('api("/api/status").then(x=>x.managers[0].data.control.instances.some(i=>i.slot_id==="slot2"&&i.state==="STOPPED"))');
  const rejection=await evaluate(`pairingPost("/api/chat/send",${JSON.stringify(sendPayload(one,'stopped','c'.repeat(32)))}).then(()=>"unexpected",e=>e.message)`);
  assert.match(rejection,/slot_process_unverified|instance_not_ready|model_not_running/);
  state=await data();assert.equal(state.control.instances.find(i=>i.instance_id===two.instance_id).state,'READY');
  await fetch(host.upstream+'/__qa/reload');
  await browser.call('Page.reload');
  await until('document.querySelectorAll(".working-slot").length===5');
  state=await data();assert.equal(state.control.slots.find(s=>s.slot_id==='slot3').model_key,'kat');
  assert.equal(state.control.slots.find(s=>s.slot_id==='slot5').mode,'cuda');
  const history=await evaluate(`api("/api/chat/history?"+new URLSearchParams(${JSON.stringify({manager_id:'qa-manager',slot_id:two.slot_id,model_id:two.model_id,instance_id:two.instance_id})}))`);
  assert.equal(history.messages[0].content,'instance two');
  // Risk cancellation is a user decision, not a capability/role escalation.
  await fetch(host.upstream+'/__qa/low_ram');await evaluate('refresh()');
  await click('slot2','Старт CPU');
  await until('!slotPending.has("qa-manager:slot2")');
  state=await data();assert(!state.control.instances.some(i=>i.slot_id==='slot2'&&!i.released));
  assert(browser.dialogs.length>=1);
  browser.setDialogAcceptance(true);
  await click('slot2','Старт CPU');await ready('slot2');
  assert(browser.dialogs.length>=2);
  await fetch(host.upstream+'/__qa/normal_ram');
  assert.deepEqual(browser.errors,[]);
  await evaluate('refresh(true)');
  await until('!isRefreshing && !refreshQueued');
  await browser.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false});
  const layout=await browser.call('Page.getLayoutMetrics');
  const screenshot=await browser.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,
    clip:{x:0,y:0,width:1440,height:Math.ceil(layout.cssContentSize.height),scale:1}});
  await fs.writeFile(path.join(here,'stream_slots_browser.png'),Buffer.from(screenshot.data,'base64'));
  console.log(JSON.stringify({status:'PASS',scope:'SOURCE API + SQLite + TLS + Chrome; fake engines/resources',
    default_slots:3,persisted_slots:5,simultaneous_same_model_cpu:2,simultaneous_same_model_cuda:2,
    unique_instance_ids:true,ipv6_listener_skipped:true,concurrent_chats_isolated:true,
    stop_one_preserves_other:true,controller_and_browser_reload:true,history_preserved:true,
    risk_cancel_and_confirm:true,console_errors:browser.errors},null,2));
}catch(error){
  if(browser)console.error(JSON.stringify(await browser.evaluate('({snapshot:chatSnapshot,notice:document.getElementById("notice").textContent,rows:[...document.querySelectorAll(".working-slot")].map(r=>({id:r.dataset.slotId,text:r.textContent,buttons:[...r.querySelectorAll("button")].map(b=>({text:b.textContent,disabled:b.disabled}))}))})')));
  throw error;
}finally{
  if(browser)await browser.close();
  if(fixture&&fixture.exitCode===null){fixture.stdin.write('stop\n');for(let i=0;i<80&&fixture.exitCode===null;i++)await delay(100);if(fixture.exitCode===null)fixture.kill();}
  for(let i=0;i<10;i++){try{assert(path.resolve(root).startsWith(path.resolve(here)+path.sep));await fs.rm(root,{recursive:true,force:true});break;}catch{await delay(200);}}
}
