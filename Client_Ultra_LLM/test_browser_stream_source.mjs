// Chrome -> SOURCE Web Client -> pinned TLS SOURCE Manager -> gated fake SSE.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
import {chromeSession,delay} from './browser_qa_helpers.mjs';
const here=path.dirname(fileURLToPath(import.meta.url));
const root=await fs.mkdtemp(path.join(process.env.UL_QA_ROOT || here,'.stream-source-qa-'));
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
  await evaluate('document.getElementById("chat-new").click()');
  await until('Boolean(currentChat()) && !chatMutation');
  await until('document.getElementById("chat-send").disabled===false');
  assert.equal(await evaluate('Boolean(currentChat().model_id)'),true);
  const input='document.getElementById("chat-input")';
  const focus=()=>evaluate(input+'.focus()');
  const value=()=>evaluate(input+'.value');
  const typeText=text=>browser.call('Input.insertText',{text});
  const pressEnter=async (modifiers=0,autoRepeat=false)=>{
    const key={key:'Enter',code:'Enter',windowsVirtualKeyCode:13,modifiers};
    await browser.call('Input.dispatchKeyEvent',{...key,type:'keyDown',text:'\r',unmodifiedText:'\r',autoRepeat});
    await browser.call('Input.dispatchKeyEvent',{...key,type:'keyUp'});
  };
  const metricsFromUpstream=async ()=>(await fetch(host.upstream+'/__qa/metrics')).json();
  await evaluate(`window.qaSubmits=0;
    document.getElementById("chat-form").addEventListener("submit",()=>window.qaSubmits++);
    ${input}.focus()`);
  await typeText('   ');
  await pressEnter();
  assert.equal(await value(),'   ','Blank Enter must keep the draft');
  await evaluate(input+'.select()');
  await typeText('QA repeated key');
  await pressEnter(0,true);
  assert.equal(await value(),'QA repeated key','Auto-repeat must not insert a newline or submit');
  await pressEnter(8);
  assert.equal(await value(),'QA repeated key\n','Shift+Enter must insert a newline');
  await evaluate(input+'.select()');
  await browser.call('Input.imeSetComposition',{text:'かな',selectionStart:2,selectionEnd:2});
  await pressEnter();
  await typeText('仮名');
  assert.match(await value(),/仮名/,'IME-confirmed text must stay in the draft');
  const legacyIME=await evaluate(`${input}.dispatchEvent(new KeyboardEvent("keydown",{
    key:"Enter",code:"Enter",keyCode:229,bubbles:true,cancelable:true
  }))`);
  assert.equal(legacyIME,true,'Chromium IME commit fallback must keep the native event');
  assert.equal(await evaluate('window.qaSubmits'),0,'Blank, repeat, Shift and IME must not submit');
  assert.equal((await metricsFromUpstream()).requests,0);
  assert.equal(await evaluate(`document.activeElement===${input}`),true);
  await evaluate(`document.getElementById("chat-thinking").checked=true;
    document.getElementById("chat-effort").value="high";
    document.getElementById("chat-max-tokens").value="2048";
    ${input}.select()`);
  const pasted='QA fixture prompt\nMultiline text inserted in one browser input event';
  await typeText(pasted);
  assert.equal(await value(),pasted);
  await pressEnter();
  assert.equal(await evaluate('window.qaSubmits'),1,'Plain Enter must submit the form exactly once');
  await until('document.querySelector(".reasoning-text")?.textContent.includes("Отдельное рассуждение 🧠")');
  assert.equal(await evaluate(input+'.disabled'),true);
  await pressEnter();
  await pressEnter(0,true);
  // A direct duplicate submit must hit the same busy guard as the button.
  await evaluate('document.getElementById("chat-form").requestSubmit()');
  assert.equal((await metricsFromUpstream()).requests,1,'Busy or double submit must not reach the engine');
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
  assert.equal(before.generation_options.context_compaction,'off');
  await fetch(host.upstream+'/__qa/done');
  await until('document.getElementById("chat-messages").textContent.includes("и завершение") && !document.getElementById("chat-send").disabled');
  assert.equal(await value(),'');
  assert.equal(await evaluate(`document.activeElement===${input}`),true,'Keyboard focus must return to the chat input');
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
  const chatId=await evaluate('chatSelected');
  const saved=await(await fetch(host.url+'/api/chat/history?chat_id='+chatId)).json();
  assert(saved.messages.some(row=>row.reasoning_content));
  const directPayload={model:'qa-model',messages:[...saved.messages.map(({role,content})=>({role,content})),{role:'user',content:'QA comparison'}],
    stream:true,context_compaction:'off',stream_options:{include_usage:true},enable_thinking:true,reasoning_effort:'high',max_tokens:2048};
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

  const timeOrigin=await evaluate('performance.timeOrigin');
  await browser.call('Page.reload');
  await until(`performance.timeOrigin > ${timeOrigin} && typeof showChats === "function" &&
    document.querySelectorAll(".manager").length===1`);
  await evaluate('showChats()');
  await until('!document.getElementById("chat-send").disabled && document.getElementById("chat-messages").textContent.includes("QA comparison")');
  assert.equal(await evaluate(`document.getElementById("chat-messages").textContent.includes(${JSON.stringify(pasted)})`),true);
  assert.equal(await evaluate('document.getElementById("chat-messages").getAttribute("aria-live")'),'polite');

  const retryDraft='QA text kept on network error';
  await focus();
  await typeText(retryDraft);
  await browser.call('Network.enable');
  await browser.call('Network.setBlockedURLs',{urls:[host.url+'/api/chat/stream']});
  try{
    await pressEnter();
    await until('document.getElementById("chat-notice").textContent.startsWith("Ошибка ответа:") && !document.getElementById("chat-send").disabled');
    assert.equal(await value(),retryDraft,'Network error must keep the exact draft');
    assert.equal(await evaluate(`document.activeElement===${input}`),true,'Network error must restore keyboard focus');
    assert.equal((await metricsFromUpstream()).requests,3);
  }finally{await browser.call('Network.setBlockedURLs',{urls:[]});}
  assert.equal(await evaluate('byId("chat-send").closest(".chat-input-wrap")===byId("chat-input").closest(".chat-input-wrap")'),true);
  assert.equal(await evaluate('byId("chat-send").dataset.icon'),"enter");
  await evaluate('document.getElementById("chat-send").click()');
  await until(`document.getElementById("chat-messages").textContent.includes(${JSON.stringify(retryDraft)})
    && !document.getElementById("chat-send").disabled`);
  assert.equal(await value(),'');
  assert.equal((await metricsFromUpstream()).requests,4,'Clicking Send must recover with exactly one request');
  assert.deepEqual(browser.errors,[]);
  console.log(JSON.stringify({status:'PASS',chain:'Chrome / SOURCE Client / verified TLS SOURCE Manager / fake Colibri',
    first_before_done:true,fragmented_utf8_json:true,separate_reasoning:true,thinking_controls:true,
    persisted_reasoning:true,requests:comparison.requests,metrics,
    comparison:{identical_upstream_payload:true,direct,routed_with_history:warmMetrics,kind:'fake-model-only'},
    keyboard:{plain_enter_once:true,shift_newline:true,ime_composition:true,ime_229:true,blank:true,repeat:true,
      busy_and_duplicate:true,multiline_input:true,restored_focus:true,history_after_reload:true,
      accessibility_live_region:true,blocked_request_retains_draft:true,send_button_recovery:true,total_upstream_requests:4},
    console_errors:browser.errors},null,2));
}finally{
  if(browser)await browser.close();
  if(fixture&&fixture.exitCode===null){fixture.stdin.write('stop\n');for(let i=0;i<40&&fixture.exitCode===null;i++)await delay(100);if(fixture.exitCode===null)fixture.kill();}
  if(!process.env.UL_QA_ROOT)for(let i=0;i<10;i++){try{assert(path.resolve(root).startsWith(path.resolve(here)+path.sep));await fs.rm(root,{recursive:true,force:true});break;}catch{await delay(200);}}
}
