// Chrome -> local Client -> TLS Manager -> synthetic Colibri, fresh profile per run.
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import net from 'node:net';
import path from 'node:path';
import readline from 'node:readline';
import {spawn} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {chromeSession, delay} from './browser_qa_helpers.mjs';

const here = path.dirname(fileURLToPath(import.meta.url));
const qaRoot = process.env.UL_QA_ROOT || path.resolve(here, '../Test/ci');
await fs.mkdir(qaRoot, {recursive:true});
const root = await fs.mkdtemp(path.join(qaRoot, 'chat-ux-'));
const fixture = spawn('py',['-3.12','-X','utf8','-B',path.join(here,'offline_stream_host.py'),path.join(root,'fixture'),'--chat-ux'],
  {windowsHide:true, stdio:['pipe','pipe','pipe']});
const output = readline.createInterface({input:fixture.stdout});
let stderr = '';
fixture.stderr.on('data', chunk => { stderr += chunk; });
const exit = new Promise(resolve => fixture.once('exit', resolve));
let browser, host;
let portable;
const portableExe = process.env.UL_QA_PORTABLE;
const portableProfile = path.join(root,'portable-profile');
const started = performance.now();
const results = {};
const nextLine = () => new Promise((resolve,reject) => {
  const deadline = setTimeout(() => {output.off('line', got); reject(Error('Fixture deadline: '+stderr));}, 15000);
  function got(line) { clearTimeout(deadline); resolve(line); }
  output.once('line', got);
});
function closed(url) {
  return new Promise((resolve,reject) => {
    const socket = net.connect(Number(new URL(url).port),'127.0.0.1');
    socket.once('connect', () => { socket.destroy(); reject(Error('Fixture listener remained open')); });
    socket.once('error', error => error.code === 'ECONNREFUSED' ? resolve(true) : reject(error));
    socket.setTimeout(2000, () => { socket.destroy(); reject(Error('Listener audit timeout')); });
  });
}
async function startPortable(port = 0) {
  const process = spawn(portableExe,['--config-dir',portableProfile,'--no-browser','--port',String(port)],
    {windowsHide:true,stdio:'ignore'});
  const exit = new Promise(resolve => process.once('exit',resolve));
  portable = {process,exit};
  for (let i=0;i<200;i++) {
    if (process.exitCode !== null) throw Error('Portable start failed: '+process.exitCode);
    try {
      const portFile = await fs.readFile(path.join(portableProfile,'.web-client.port'),'ascii');
      const url = 'http://127.0.0.1:'+Number(portFile);
      if ((await fetch(url+'/api/config')).ok) {
        portable.url = url;
        return url;
      }
    } catch {}
    await delay(50);
  }
  throw Error('Portable start deadline');
}
async function stopPortable(url) {
  const {csrf} = await (await fetch(url+'/api/session')).json();
  const response = await fetch(url+'/api/shutdown',{method:'POST',headers:{Origin:url,'X-Ultra-CSRF':csrf}});
  assert.equal(response.status,200);
  const timeout = setTimeout(()=>portable.process.kill(),5000);
  try { assert.equal(await portable.exit,0); } finally { clearTimeout(timeout); }
}
try {
  host = JSON.parse(await nextLine());
  if (portableExe) {
    host.fixtureClient = host.url;
    host.url = await startPortable();
    for (const name of ['managers.json','qa-cert.pem','qa-token.txt']) {
      await fs.copyFile(path.join(root,'fixture',name),path.join(portableProfile,name));
    }
  }
  browser = await chromeSession(host.url, path.join(root,'chrome'));
  const {evaluate, until, call} = browser;
  await until('document.querySelectorAll(".manager").length===1');
  const activate = async () => {
    await evaluate('showChats()');
    await until('!byId("chat-new").disabled');
  };
  const query = async (id, kind = 'history') => {
    const response = await fetch(host.url+'/api/chat/'+kind+'?chat_id='+id);
    assert.equal(response.status, 200);
    return response.json();
  };
  const command = async name => assert.equal((await fetch(host.upstream+'/__qa/'+name)).status, 204);
  const getPayload = async () => (await fetch(host.upstream+'/__qa/payload')).json();
  const send = async text => evaluate('byId("chat-input").value='+JSON.stringify(text)+'; byId("chat-form").requestSubmit()');
  const ready = async () => until('byId("chat-send").type==="submit" && !byId("chat-send").disabled');
  const saved = async text => until('byId("chat-messages").textContent.includes('+JSON.stringify(text)+') && byId("chat-send").type==="submit" && !byId("chat-send").disabled');
  const create = async count => {
    await evaluate('byId("chat-new").click()');
    await until('document.querySelectorAll(".chat-choice").length==='+count);
    await ready();
    assert.equal(await evaluate('currentChat().manager_id'),"qa-manager");
    assert.equal(await evaluate('Boolean(currentChat().model_id)'),true);
    return evaluate('chatSelected');
  };
  const select = async id => evaluate('selectChat('+JSON.stringify(id)+')');
  const geometry = () => evaluate('({top:window.scrollY,height:document.documentElement.scrollHeight,client:window.innerHeight,distance:scrollDistance(),innerOverflow:getComputedStyle(chatHolder).overflowY,composerBottom:Math.round(byId("chat-form").getBoundingClientRect().bottom)})');
  const cardAction = (id, op) => evaluate(`document.querySelector('.chat-choice[data-chat-id=${JSON.stringify(id)}] [data-action=${JSON.stringify(op)}]').click()`);

  await activate();
  const a = await create(1);
  await call('Emulation.setDeviceMetricsOverride',{width:780,height:620,deviceScaleFactor:1,mobile:false});
  await evaluate('document.body.style.zoom="110%"');
  await send('qa-long');
  await until('document.querySelector(".reasoning-text")?.textContent.length>500 && scrollDistance()<=3');
  const reasoning = await geometry();
  assert(reasoning.height > reasoning.client * 2 && reasoning.top > 0);
  assert.equal(reasoning.innerOverflow,'visible');
  assert(Math.abs(reasoning.composerBottom - 620) < 3);
  await evaluate('refresh(true)');
  assert.equal(await evaluate('byId("chat-state").textContent'),'Модель отвечает');
  assert.equal(await evaluate('byId("chat-send").type'),"button");
  assert.equal(await evaluate('byId("chat-send").getAttribute("aria-label")'),"Стоп");
  assert.equal(await evaluate('byId("chat-send").dataset.icon'),"stop");
  assert.equal(await evaluate('byId("chat-stream").disabled'),true);
  await evaluate('byId("chat-new").click()');
  await until('document.querySelectorAll(".chat-choice").length===2');
  const b = await evaluate('chatSelected');
  assert.equal(await evaluate('byId("chat-manager").value'),"qa-manager");
  assert.equal(await evaluate('Boolean(currentChat().model_id)'),false);
  assert.equal(await evaluate('byId("chat-model").options.length'),0);
  assert.notEqual(a,b);
  assert.equal(await evaluate('byId("chat-send").disabled'),true);
  assert.equal(await evaluate('chatHolder.querySelector(".chat-bubble")===null'),true);
  await select(a);
  await until('document.querySelector(".reasoning-text")?.textContent.length>500 && scrollDistance()<=3');
  await command('answer');
  await until('chatHolder.textContent.includes("Первая часть ответа") && scrollDistance()<=3');
  const answer = await geometry();
  assert(answer.height > reasoning.height);
  await evaluate('window.dispatchEvent(new WheelEvent("wheel",{deltaY:-500,bubbles:true}));window.scrollTo(0,10)');
  await until('!followStream');
  await command('wave');
  await until('chatHolder.textContent.includes("Вторая часть ответа")');
  const paused = await geometry();
  assert(paused.top <= 12 && paused.height > answer.height && paused.distance > 500);
  assert.equal(paused.innerOverflow,'visible');
  await evaluate('byId("chat-latest").click()');
  await until('scrollDistance()<=3');
  await command('done');
  await until('streamMetrics.browser_total_ms != null && byId("chat-state").textContent.includes("занята")');
  await ready();
  // Desktop layout: the page owns vertical scrolling, the chat list sticks,
  // and the composer remains fixed to the actual chat column.
  await call('Emulation.setDeviceMetricsOverride',{width:1440,height:800,deviceScaleFactor:1,mobile:false});
  await evaluate('updateComposerPosition(); pinToBottom()');
  await until('Math.abs(byId("chat-form").getBoundingClientRect().bottom-window.innerHeight)<3');
  const desktop = await evaluate('({form:getComputedStyle(byId("chat-form")).position,side:getComputedStyle(document.querySelector(".chat-sources")).position,inside:getComputedStyle(chatHolder).overflowY,formLeft:byId("chat-form").getBoundingClientRect().left,panelLeft:chatPanel.getBoundingClientRect().left,formWidth:byId("chat-form").getBoundingClientRect().width,panelWidth:chatPanel.getBoundingClientRect().width})');
  assert.deepEqual([desktop.form,desktop.side,desktop.inside],['fixed','sticky','visible']);
  assert(Math.abs(desktop.formLeft-desktop.panelLeft)<2 && Math.abs(desktop.formWidth-desktop.panelWidth)<2);
  await evaluate('window.scrollTo(0,document.querySelector(".chat-layout").getBoundingClientRect().top+window.scrollY+110)');
  await until('window.scrollY>100');
  const sideTop = await evaluate('document.querySelector(".chat-sources").getBoundingClientRect().top');
  assert(sideTop>=14 && sideTop<=18,'Chat sidebar should remain sticky while reading');
  await evaluate('byId("chat-latest").click()');
  await until('scrollDistance()<=3');
  await call('Emulation.setDeviceMetricsOverride',{width:780,height:620,deviceScaleFactor:1,mobile:false});
  await evaluate('updateComposerPosition(); pinToBottom()');
  const first = await query(a,'metrics');
  assert.equal(first.results[0].usage.prompt_tokens,17);
  assert.equal(first.results[0].usage.completion_tokens,8);
  assert(first.results[0].first_fragment_ms > 0 && first.results[0].generation_ms > 0);
  assert.match(await evaluate('byId("chat-timer").textContent'),/17 \/ 8/);
  const footnotes = () => evaluate('[...chatHolder.querySelectorAll(".chat-message-metrics")].map(el=>el.textContent)');
  const firstFootnotes = await footnotes();
  assert.equal(firstFootnotes.length,2);
  assert.equal(firstFootnotes[0],firstFootnotes[1]);
  assert.match(firstFootnotes[0],/Первый фрагмент .*Генерация .*Всего .*17 \/ 8.*Маршрут Colibri/);
  const readyMs = await evaluate('streamMetrics.browser_slot_ready_ms - streamMetrics.browser_total_ms');
  assert(readyMs > 0 && readyMs < 5000);
  const checks = await evaluate('streamMetrics.browser_slot_checks');
  assert(checks.includes('busy') && checks.at(-1)==='ready_unreserved');
  results.scroll = {reasoning, answer, paused};
  results.scheduler_release_ms = readyMs;
  results.scheduler_checks = checks;
  results.synthetic_usage = first.results[0].usage;

  await evaluate('byId("chat-detach-model").click()');
  await until('!chatMutation && !currentChat().model_id');
  await select(b);
  await evaluate('changeChat("target",{target:targetFields(chatTargets.find(t=>t.engine_state==="ready"))})');
  await ready();
  await send('qa-b');
  await saved('Ответ qa-b');
  const isolated = await getPayload();
  assert.equal(isolated.context_compaction,'off');
  assert.deepEqual(isolated.messages,[{role:'user',content:'qa-b'}]);
  await evaluate('byId("chat-detach-model").click()');
  await until('!chatMutation && !currentChat().model_id');
  await select(a);
  await evaluate('changeChat("target",{target:targetFields(chatTargets.find(t=>t.engine_state==="ready"))})');
  await saved('qa-long');
  await send('qa-context');
  await saved('Ответ qa-context');
  const forwarded = (await getPayload()).messages;
  assert.equal(forwarded.length,3);
  assert(forwarded[1].content.includes('Первая часть ответа'));
  assert(forwarded.every(m => Object.keys(m).sort().join() === 'content,role'));
  assert(!JSON.stringify(forwarded).includes('Фрагмент рассуждения'));
  assert.equal((await query(b)).messages.length,2);
  const afterContext = await footnotes();
  assert.deepEqual(afterContext.slice(0,2),firstFootnotes);
  assert.match(afterContext[2],/31 \/ 4/);
  assert.equal(afterContext[2],afterContext[3]);

  await evaluate('byId("chat-history-messages").value=0; byId("chat-history-messages").dispatchEvent(new Event("change"))');
  await until('currentChat().settings.max_messages===0');
  await ready();
  await send('qa-zero');
  await saved('Ответ qa-zero');
  assert.deepEqual((await getPayload()).messages,[{role:'user',content:'qa-zero'}]);
  assert.equal((await query(a)).messages.length,6);
  await evaluate('changeChat("settings",{context:{max_messages:20,max_chars:200000}})');
  await evaluate('changeChat("reset")');
  await send('qa-reset');
  await saved('Ответ qa-reset');
  assert.deepEqual((await getPayload()).messages,[{role:'user',content:'qa-reset'}]);
  assert.equal((await query(a)).messages.length,8);
  await evaluate('changeChat("resume")');

  browser.setDialogAcceptance(false);
  await cardAction(a, 'clear');
  assert.equal((await query(a)).messages.length,8);
  browser.setDialogAcceptance(true);
  await cardAction(a, 'clear');
  await until('currentChat().can_restore && !chatHolder.querySelector(".chat-bubble")');
  assert.equal((await query(b)).messages.length,2);
  await cardAction(a, 'restore');
  await saved('Ответ qa-reset');
  await evaluate('changeChat("rename",{title:"QA archive A"})');
  await until('byId("chat-title").textContent==="QA archive A"');
  const aBeforeInactive = (await query(a)).messages.length;
  await evaluate('window.__qaPrompt=window.prompt;window.prompt=()=>"QA B renamed"');
  await cardAction(b, 'rename');
  await until('chatItems.find(c=>c.chat_id==='+JSON.stringify(b)+').title==="QA B renamed"');
  await evaluate('window.prompt=window.__qaPrompt;delete window.__qaPrompt');
  await cardAction(b, 'reset');
  await until('chatItems.find(c=>c.chat_id==='+JSON.stringify(b)+').context_after>0');
  await cardAction(b, 'resume');
  await until('chatItems.find(c=>c.chat_id==='+JSON.stringify(b)+').context_after===0');
  await cardAction(b, 'clear');
  await until('chatItems.find(c=>c.chat_id==='+JSON.stringify(b)+').can_restore');
  assert.equal((await query(a)).messages.length,aBeforeInactive);
  assert.equal((await query(b)).messages.length,0);
  assert.equal(await evaluate('chatSelected'),a);
  await cardAction(b, 'restore');
  await until('!chatItems.find(c=>c.chat_id==='+JSON.stringify(b)+').can_restore');
  assert.equal((await query(b)).messages.length,2);
  results.independence_and_history = true;

  await send('qa-cancel');
  await until('byId("chat-send").type==="button" && !byId("chat-send").disabled && chatHolder.textContent.includes("Фрагмент рассуждения") && conversation(chatSelected).request.first != null');
  await evaluate('byId("chat-send").click()');
  await until('byId("chat-notice").textContent.includes("отменён")');
  await ready();
  assert.equal((await query(a)).messages.length,8);
  await send('qa-truncated');
  await until('byId("chat-notice").textContent.startsWith("Ошибка ответа")');
  await ready();
  assert.equal((await query(a)).messages.length,8);
  const terminal = (await query(a,'metrics')).results;
  assert.equal(terminal[0].state,'failed');
  assert.equal(terminal[1].state,'cancelled');
  await evaluate('byId("chat-stream").checked=false');
  await send('qa-no-usage');
  await until('byId("chat-timer").textContent.includes("нет данных / нет данных") && !byId("chat-send").disabled');
  assert.equal((await getPayload()).context_compaction,'off');
  assert.deepEqual((await query(a,'metrics')).results[0].usage,{});
  const beforeRestart = (await query(a)).messages;
  assert(beforeRestart.every(m=>m.created_at && m.created_at.endsWith('+00:00')));
  const beforeRestartFootnotes = await footnotes();
  assert.equal(beforeRestartFootnotes.length,beforeRestart.length);
  assert.match(beforeRestartFootnotes.at(-1),/Первый фрагмент нет данных.*Токены вход \/ выход нет данных \/ нет данных/);
  results.terminal_paths = ['done','cancelled','truncated','no usage'];
  const grip=await evaluate('(() => {const r=byId("chat-input-resize").getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,height:byId("chat-input").getBoundingClientRect().height}})()');
  assert.equal(await evaluate(`document.elementFromPoint(${grip.x},${grip.y})?.closest('#chat-input-resize')?.id`),'chat-input-resize');
  await call('Input.dispatchMouseEvent',{type:'mousePressed',x:grip.x,y:grip.y,button:'left',clickCount:1});
  assert.equal(await evaluate('inputResizeStart !== null'),true);
  for (let step=1;step<=5;step++) {
    await call('Input.dispatchMouseEvent',{type:'mouseMoved',x:grip.x,y:grip.y-20*step,button:'left',buttons:1});
    await new Promise(resolve=>setTimeout(resolve,20));
  }
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',x:grip.x,y:grip.y-100,button:'left',clickCount:1});
  const resizeProbe=await evaluate('({height:byId("chat-input").getBoundingClientRect().height,style:byId("chat-input").style.height,start:inputResizeStart})');
  assert(resizeProbe.height>grip.height+40,JSON.stringify({grip,resizeProbe}));
  await until('byId("chat-input").getBoundingClientRect().height>'+String(grip.height+40));
  results.mouse_resize = true;
  await evaluate('byId("chat-input").style.height="200px"');
  await until('composerHeight()>190 && Math.abs(byId("chat-form").getBoundingClientRect().bottom-window.innerHeight)<3');
  await until('scrollDistance()<=3');
  assert.equal(await evaluate('getComputedStyle(chatHolder).overflowY'), 'visible');
  assert.equal(await evaluate('document.documentElement.scrollHeight>window.innerHeight'),true);
  await evaluate('byId("chat-input").style.height=""');

  if (portableExe) {
    await stopPortable(host.url);
    assert.equal(await startPortable(Number(new URL(host.url).port)),host.url);
  } else {
    const line = nextLine();
    fixture.stdin.write('restart-client\n');
    assert.equal(await line,'client-restarted');
  }
  const before = await evaluate('performance.timeOrigin');
  await call('Page.reload');
  await until('performance.timeOrigin>'+before+' && document.querySelectorAll(".manager").length===1');
  await activate();
  await saved('qa-no-usage');
  await until('scrollDistance()<=3'); // reload opens at the latest message without manual scrolling
  await until('Math.abs(window.scrollY-(document.documentElement.scrollHeight-window.innerHeight))<3');
  assert.equal(await evaluate('chatSelected'),a);
  assert.equal(await evaluate('byId("chat-title").textContent'),'QA archive A');
  assert.deepEqual((await query(a)).messages,beforeRestart);
  assert.deepEqual(await footnotes(),beforeRestartFootnotes);
  const popoutPoint=await evaluate('(() => {const b=byId("chat-popout");b.scrollIntoView({block:"center"});const r=b.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2}})()');
  await call('Input.dispatchMouseEvent',{type:'mousePressed',...popoutPoint,button:'left',clickCount:1});
  await call('Input.dispatchMouseEvent',{type:'mouseReleased',...popoutPoint,button:'left',clickCount:1});
  let popped;
  for (let i=0;i<60 && !popped;i++) {
    popped=(await call('Target.getTargets')).targetInfos.find(t=>t.type==='page' && t.url.endsWith('#chat='+a));
    if (!popped) await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert(popped,'Detached chat window did not open');
  const attached=await call('Target.attachToTarget',{targetId:popped.targetId,flatten:true});
  await call('Runtime.enable',{},attached.sessionId);
  let detachedChat;
  for (let i=0;i<60;i++) {
    detachedChat=(await call('Runtime.evaluate',{expression:'typeof chatSelected === "undefined" ? "" : chatSelected',returnByValue:true},attached.sessionId)).result.value;
    if (detachedChat===a) break;
    await new Promise(resolve=>setTimeout(resolve,50));
  }
  assert.equal(detachedChat,a,'Detached window must open the same chat_id');
  results.popout_chat_id = true;
  results.per_message_measurements = {rows:beforeRestartFootnotes.length, separate_exchanges:true, persisted:true};
  await evaluate('byId("chat-statistics").open=true');
  await until('byId("chat-stat-results").textContent.includes("Отменён")');
  results.restart_and_time = true;

  await command('stop_model');
  await evaluate('refresh(true)');
  await until('byId("chat-send").disabled && byId("chat-state").textContent.includes("недоступна")');
  assert.equal((await query(a)).messages.length,beforeRestart.length);
  await command('change_model');
  await evaluate('refresh(true)');
  await evaluate('changeChat("target",{target:{manager_id:"qa-manager",slot_id:"slot1",model_id:"qa-other"}})');
  await ready();
  assert.equal((await query(a)).messages.length,beforeRestart.length);
  await command('manager_down');
  await evaluate('refresh(true)');
  await until('byId("chat-send").disabled && byId("chat-state").textContent.includes("недоступна")');
  await select(b);
  await until('chatHolder.textContent.includes("Ответ qa-b")');
  await until('Math.abs(window.scrollY-(document.documentElement.scrollHeight-window.innerHeight))<3');
  await select(a);
  await until('Math.abs(window.scrollY-(document.documentElement.scrollHeight-window.innerHeight))<3');
  await cardAction(b, 'delete');
  await until('document.querySelectorAll(".chat-choice").length===1');
  assert.equal((await fetch(host.url+'/api/chat/history?chat_id='+b)).status,404);
  assert.equal(await evaluate('chatSelected'),a);
  const denied = await fetch(host.url+'/api/chats',{method:'POST',headers:{'Content-Type':'application/json'},body:'{"op":"create"}'});
  assert.equal(denied.status,403);
  const invalidContext = await evaluate('pairingPost("/api/chats",{op:"settings",chat_id:chatSelected,context:{max_messages:-1,max_chars:100}}).then(()=>null,e=>e.message)');
  assert.equal(invalidContext,'invalid_context_policy');
  assert.deepEqual(browser.errors,[]);
  results.offline_and_validation = true;
} catch (error) {
  if (browser) {
    const scroll = await browser.evaluate('({top:chatHolder.scrollTop, height:chatHolder.scrollHeight, client:chatHolder.clientHeight, follow:followStream, busy:!!conversation(chatSelected).request})')
      .catch(() => null);
    console.error(JSON.stringify({scroll, javascript_errors:browser.errors}));
  }
  throw error;
} finally {
  try {
    if (browser) await browser.close();
    if (portable?.process.exitCode === null && !portable.process.signalCode) {
      try {
        if (portable.url) await stopPortable(portable.url);
      } finally {
        if (portable.process.exitCode === null) portable.process.kill();
      }
    }
  } finally {
    output.close();
    if (fixture.exitCode === null) fixture.stdin.end('stop\n');
    const timeout = setTimeout(() => fixture.kill(), 6000);
    try { assert.equal(await exit,0); } finally {clearTimeout(timeout);}
    if (host) results.closed_ports = await Promise.all([host.url,host.upstream,host.manager,host.fixtureClient].filter(Boolean).map(closed));
  }
}
console.log(JSON.stringify({status:'PASS', scope:'Chrome / '+(portableExe ? 'portable EXE' : 'SOURCE Client')+' / TLS SOURCE Manager / synthetic Colibri',
  seconds:(performance.now()-started)/1000, results}));
