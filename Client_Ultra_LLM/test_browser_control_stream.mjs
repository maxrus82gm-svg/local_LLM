// Real Chrome DOM/stream checks on an ephemeral fake Client API. No live profile.
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';

const here=path.dirname(fileURLToPath(import.meta.url));
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const tmp=await fs.mkdtemp(path.join(process.env.UL_QA_ROOT || here,'.chrome-qa-'));
let chrome,ws,server,release;
let phase='STOPPED', lastControl=null, streamBody=null;
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
      engine_state:i===0||i===1&&phase==='READY'?'ready':'not_running',availability:i===0||i===1&&phase==='READY'?'ready_unreserved':'not_running'})),
    control:{models:[{...model,modes:{...model.modes,cpu:{available:phase==='STOPPED'}}}],
      instances:phase==='STOPPED'?[]:[{instance_id:'f'.repeat(32),model_key:'kat',model_id:'ultra-slot2-kat-cpu',mode:'cpu',slot_id:'slot2',state:phase,can_stop:phase==='READY'}]}}},
    {manager_id:'manager-a',name:'Manager A',status:'online',data:{host:'QA A',memory:{state:'unknown'},models:[],slots:[],
      control:{models:[],instances:[]}}}]};
}
try {
  server=http.createServer(async(req,res)=>{
    let raw='';for await(const b of req)raw+=b;
    const json=(data,status=200)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(data));};
    if(req.url==='/api/session')return json({csrf:'QA-CSRF'});
    if(req.url==='/api/config')return json({configured:true});
    if(req.url==='/api/status'){markOnce('first_status_request');return json(snapshot());}
    if(req.url==='/api/chats'){
      if(req.method==='GET')return json({chats});
      const command=JSON.parse(raw);
      if(command.op==='create'){
        const row={chat_id:'a'.repeat(32),title:'Новый чат',settings:{}};
        chats.push(row);return json(row);
      }
      Object.assign(chats[0],command.target);
      return json(chats[0]);
    }
    if(req.url.startsWith('/api/chat/history?'))return json({messages:[]});
    if(req.url.startsWith('/api/chat/metrics?'))return json({results:[]});
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
    if(req.url==='/api/chat/send')return json({messages:[{role:'assistant',content:'Обычный ответ'}]});
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
  let port;
  for(let i=0;i<100;i++){
    try{port=Number((await fs.readFile(path.join(tmp,'DevToolsActivePort'),'utf8')).split('\n')[0]);break;}catch{}
    await delay(100);
  }
  assert(port,'Chrome DevTools did not start');
  mark('devtools_port_ready');
  const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  mark('cdp_connected');
  let id=0;const pending=new Map();
  ws.onmessage=e=>{const msg=JSON.parse(e.data);if(msg.id){const p=pending.get(msg.id);pending.delete(msg.id);
    if(msg.error)p.reject(Error(msg.error.message));else p.resolve(msg.result);}
    if(msg.method==='Runtime.exceptionThrown')errors.push(msg.params.exceptionDetails.text);};
  const call=(method,params={})=>new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));});
  await call('Runtime.enable');
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
  assert.equal(await evaluate('document.querySelectorAll(".manager-model-row").length'),2);
  assert.equal(await evaluate('document.querySelectorAll("#slot-table").length'),0);
  results.push('PASS: two Manager identities, five slots, one model list per Manager');
  const buttons='[...document.querySelectorAll(".manager-model-row")].find(x=>x.textContent.includes("KAT-Coder")).querySelectorAll("button")';
  assert.deepEqual(await evaluate(`Array.from(${buttons}).map(b=>b.disabled)`),[false,true,true]);
  assert.match(await evaluate(`${buttons}[1].title`),/vram_telemetry_unknown/);
  await evaluate(`${buttons}[0].click()`);
  await until('document.querySelector(".manager-model-scroll").textContent.includes("STARTING")');
  assert.equal(lastControl.manager_id,'manager-b');assert.equal(lastControl.op,'start');assert.equal(lastControl.mode,'cpu');
  assert.match(lastControl.request_id,/^[a-f0-9]{32}$/);
  results.push('PASS: CPU/disabled CUDA reason, STARTING, correct Manager identity');
  phase='READY';await evaluate('refresh()');
  assert.equal(await evaluate('document.querySelectorAll(".manager-model-row").length'),2,'Owned API model must not duplicate catalog row');
  assert.equal(await evaluate(`${buttons}[2].disabled`),false);
  await evaluate(`${buttons}[2].click()`);
  await until('document.querySelector(".manager-model-scroll").textContent.includes("STOPPING")');
  assert.equal(lastControl.instance_id,'f'.repeat(32));
  results.push('PASS: STOPPING and stable owned instance_id');
  phase='READY';await evaluate('refresh().then(showChats)');
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===1');
  await evaluate('(() => { const select=byId("chat-target"); select.value=[...select.options].find(o=>o.text.includes("ultra-slot2-kat-cpu")).value; select.dispatchEvent(new Event("change")); })()');
  await until('byId("chat-send").disabled===false');
  await delay(150);
  const started=performance.now();
  await evaluate('document.getElementById("chat-input").value="Привет";document.getElementById("chat-form").requestSubmit()');
  await until('document.getElementById("chat-messages").textContent.includes("Первый фрагмент")');
  const firstMs=Math.round(performance.now()-started);
  assert(release,'No upstream release gate');
  assert.equal(await evaluate('document.getElementById("chat-messages").textContent.includes("и конец")'),false);
  assert.equal(streamBody.manager_id,'manager-b');assert.equal(streamBody.model_id,'ultra-slot2-kat-cpu');
  release();release=null;
  await until('byId("chat-messages").textContent.includes("Первый фрагмент и конец") && !byId("chat-send").disabled');
  results.push(`PASS: visible real HTTP fragments before completion, browser_first_fragment_ms=${firstMs} (fake model)`);
  await evaluate('document.getElementById("chat-stream").checked=false;document.getElementById("chat-input").value="Обычный";document.getElementById("chat-form").requestSubmit()');
  await until('document.getElementById("chat-messages").textContent.includes("Обычный ответ")');
  results.push('PASS: ordinary chat independent from streaming');
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
