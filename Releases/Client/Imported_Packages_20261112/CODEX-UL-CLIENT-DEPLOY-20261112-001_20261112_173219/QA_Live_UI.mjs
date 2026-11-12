// Actual installed Client and actual existing Manager. Read-only; no generation/control POST.
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
import {chromeSession} from './QA/Source/Client_Ultra_LLM/browser_qa_helpers.mjs';
const root=path.dirname(fileURLToPath(import.meta.url));
const installed=JSON.parse(await fs.readFile(path.join(root,'INSTALL.json'),'utf8'));
try{installed.url=JSON.parse(await fs.readFile(path.join(root,'LIFECYCLE.json'),'utf8')).final_url;}catch{}
const temporary=path.join(root,'QA','ActualInstalledChrome_Final');
const browser=await chromeSession(installed.url,temporary);
try{
  const {evaluate,until}=browser;
  await until('document.querySelectorAll(".manager").length>0 && chatSnapshot?.managers.some(m=>m.status==="online")');
  const snapshot=await evaluate('({title:document.title,origin:location.origin,managers:chatSnapshot.managers.map(m=>({id:m.manager_id,status:m.status,slot_count:m.data?.slots?.length,inventory_count:m.data?.models?.length,streaming:m.data?.chat?.streaming===true,dynamic_slots:Array.isArray(m.data?.control?.slots)})),running_metric:document.getElementById("metric-models")?.textContent,catalog_rows:document.querySelectorAll(".manager-model-row").length})');
  assert.equal(snapshot.origin,installed.url);
  assert(snapshot.managers.some(m=>m.status==='online'&&m.slot_count===3));
  assert(snapshot.catalog_rows>=1);
  await browser.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  const layout=await browser.call('Page.getLayoutMetrics');
  const screen=await browser.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:1440,height:Math.ceil(layout.cssContentSize.height),scale:1}});
  await fs.writeFile(path.join(root,'LIVE_CLIENT_OVERVIEW.png'),Buffer.from(screen.data,'base64'));
  await evaluate('showChats()');
  await until('document.querySelectorAll(".chat-bubble").length>0');
  const chat=await evaluate('({displayed_messages:document.querySelectorAll(".chat-bubble").length,choices:document.querySelectorAll(".chat-choice").length,thinking_control:!!document.getElementById("chat-thinking"),reasoning_display_control:!!document.getElementById("chat-show-reasoning"),stream_control:!!document.getElementById("chat-stream"),fallback_ordinary:currentChat()?.streaming===false,send_enabled:!document.getElementById("chat-send").disabled})');
  assert.equal(chat.displayed_messages,34);
  assert(chat.thinking_control && chat.reasoning_display_control && chat.stream_control && chat.fallback_ordinary && chat.send_enabled);
  assert.deepEqual(browser.errors,[]);
  const result={status:'CLIENT DEPLOY PASS / MANAGER VERSION GATE',scope:'Installed EXE / real existing Manager read-only / actual Chrome DOM',snapshot,chat,console_errors:browser.errors,history_content_exported:false,model_generation:'NOT RUN',model_control:'NOT RUN',reasoning_live:'NOT AVAILABLE FROM OLD MANAGER'};
  await fs.writeFile(path.join(root,'LIVE_UI.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
