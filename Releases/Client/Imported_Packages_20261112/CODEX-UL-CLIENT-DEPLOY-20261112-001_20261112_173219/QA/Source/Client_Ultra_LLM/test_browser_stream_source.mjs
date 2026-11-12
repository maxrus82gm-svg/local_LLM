// Chrome -> SOURCE Web Client -> pinned TLS SOURCE Manager -> gated fake SSE.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromeSession,delay} from './browser_qa_helpers.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=await fs.mkdtemp(path.join(here,'.stream-source-qa-'));
let fixture, browser;
try{
  fixture=spawn('py',['-3.12','-X','utf8','-B',path.join(here,'offline_stream_host.py'),path.join(root,'fixture')],
    {windowsHide:true,stdio:['pipe','pipe','pipe']});
  let output='',errors='';fixture.stderr.on('data',d=>errors+=d.toString());
  const ready=new Promise((resolve,reject)=>{
    const deadline=setTimeout(()=>reject(Error('Fixture startup deadline '+errors)),20000);
    fixture.stdout.on('data',d=>{output+=d.toString();const end=output.indexOf('\n');if(end>=0){clearTimeout(deadline);try{resolve(JSON.parse(output.slice(0,end)));}catch(e){reject(e);}}});
    fixture.on('exit',code=>{if(code)reject(Error(`Fixture exited ${code}: ${errors}`));});
  });
  const host=await ready;
  browser=await chromeSession(host.url,path.join(root,'chrome'));
  const {evaluate,until}=browser;
  await until('document.querySelectorAll(".manager").length===1');
  await evaluate('showChats()');
  await until('document.getElementById("chat-send").disabled===false');
  await evaluate('document.getElementById("chat-thinking").value="on";document.getElementById("chat-effort").value="high";document.getElementById("chat-max-tokens").value="2048";document.getElementById("chat-input").value="QA fixture prompt";document.getElementById("chat-form").requestSubmit()');
  await until('document.querySelector(".reasoning-text")?.textContent.includes("Отдельное рассуждение 🧠")');
  assert.equal(await evaluate('[...document.querySelectorAll(".chat-bubble > div")].some(x=>x.textContent.includes("Отдельное рассуждение"))'),false);
  assert.equal(await evaluate('document.querySelectorAll(".reasoning-panel.hidden").length'),0);
  await evaluate('document.getElementById("chat-show-reasoning").click()');
  assert.equal(await evaluate('document.querySelectorAll(".reasoning-panel.hidden").length'),1);
  await evaluate('document.getElementById("chat-show-reasoning").click()');
  await fetch(host.upstream+'/__qa/answer');
  await until('document.getElementById("chat-messages").textContent.includes("Первый фрагмент ответа 🌍")');
  assert.equal(await evaluate('document.getElementById("chat-messages").textContent.includes("и завершение")'),false);
  const before=await(await fetch(host.upstream+'/__qa/metrics')).json();
  assert.equal(before.done_released,false);
  assert.equal(before.generation_options.enable_thinking,true);
  assert.equal(before.generation_options.max_tokens,2048);
  assert.equal(before.generation_options.reasoning_effort,'high');
  assert.equal(before.generation_options.stream_options.include_usage,true);
  await fetch(host.upstream+'/__qa/done');
  await until('document.getElementById("chat-messages").textContent.includes("и завершение") && !document.getElementById("chat-send").disabled');
  await delay(100);
  const metrics=await evaluate('streamMetrics');
  for(const key of ['manager_received_unix_ms','manager_preflight_ms','colibri_request_started_unix_ms',
    'colibri_first_fragment_unix_ms','manager_first_forward_unix_ms','client_received_unix_ms',
    'client_emit_unix_ms','client_first_fragment_unix_ms','client_first_fragment_elapsed_ms','colibri_completed_unix_ms'])assert.equal(typeof metrics.route[key],'number',key);
  assert.equal(typeof metrics.browser_first_dom_update_unix_ms,'number');
  assert.equal(typeof metrics.browser_first_paint_opportunity_unix_ms,'number');
  assert.equal(metrics.usage.completion_tokens,5);
  assert(metrics.throughput.completion_tokens_per_second>0);
  assert.match(metrics.throughput.basis,/provider_completion_tokens.*including_prefill/);
  assert.equal(await evaluate('document.querySelector(".reasoning-text").textContent'),'Отдельное рассуждение 🧠');
  await fetch(host.upstream+'/__qa/benchmark');
  const saved=await(await fetch(host.url+'/api/chat/history?manager_id=qa-manager&slot_id=slot1&model_id=qa-model')).json();
  const directPayload={model:'qa-model',messages:[...saved.messages,{role:'user',content:'QA comparison'}],
    stream:true,stream_options:{include_usage:true},enable_thinking:true,reasoning_effort:'high',max_tokens:2048};
  const directStart=performance.now();
  const directResponse=await fetch(host.upstream+'/v1/chat/completions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(directPayload)});
  let directFirst,buffer='';const decoder=new TextDecoder();
  for await(const chunk of directResponse.body){buffer+=decoder.decode(chunk,{stream:true});if(directFirst===undefined&&buffer.includes('\n\n'))directFirst=performance.now()-directStart;}
  const direct={first_fragment_ms:directFirst,total_ms:performance.now()-directStart};
  await evaluate('document.getElementById("chat-input").value="QA comparison";document.getElementById("chat-form").requestSubmit()');
  await until('streamMetrics.context?.sent_history_messages===2 && streamMetrics.browser_total_ms!==undefined && !document.getElementById("chat-send").disabled');
  const warmMetrics=await evaluate('streamMetrics');
  const comparison=await(await fetch(host.upstream+'/__qa/metrics')).json();
  assert.equal(comparison.requests,3);
  assert.equal(comparison.same_last_two_requests,true,'Direct and routed Colibri payloads must be identical');
  assert.deepEqual(browser.errors,[]);
  console.log(JSON.stringify({status:'PASS',chain:'Chrome / SOURCE Client / verified TLS SOURCE Manager / fake Colibri',
    first_before_done:true,fragmented_utf8_json:true,separate_reasoning:true,thinking_controls:true,
    persisted_reasoning:true,requests:comparison.requests,metrics,
    comparison:{identical_upstream_payload:true,direct,routed_with_history:warmMetrics,kind:'fake-model-only'},console_errors:browser.errors},null,2));
}finally{
  if(browser)await browser.close();
  if(fixture&&fixture.exitCode===null){fixture.stdin.write('stop\n');for(let i=0;i<40&&fixture.exitCode===null;i++)await delay(100);if(fixture.exitCode===null)fixture.kill();}
  for(let i=0;i<10;i++){try{assert(path.resolve(root).startsWith(path.resolve(here)+path.sep));await fs.rm(root,{recursive:true,force:true});break;}catch{await delay(200);}}
}
