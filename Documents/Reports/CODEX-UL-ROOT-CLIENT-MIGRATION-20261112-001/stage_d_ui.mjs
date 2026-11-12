// Real installed Client + existing Manager, read-only; never sends a chat/model control request.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
import {chromeSession} from '../../../Client_Ultra_LLM/browser_qa_helpers.mjs';
const report=path.dirname(fileURLToPath(import.meta.url));
const repo=path.resolve(report,'../../..');
const lifecycle=JSON.parse(await fs.readFile(path.join(report,'stage_d_lifecycle.json'),'utf8'));
assert.equal(lifecycle.status,'PASS');
const profile=await fs.mkdtemp(path.join(repo,'Test/ClientMigration_20261112/StageD/','live-chrome-'));
const browser=await chromeSession(lifecycle.final_url,profile);
try{
  const {evaluate,until}=browser;
  await until('typeof chatSnapshot!=="undefined" && chatSnapshot?.managers.some(m=>m.status==="online") && document.querySelectorAll(".manager").length===1');
  const state=await evaluate('({url:location.origin,title:document.title,managers:chatSnapshot.managers.map(m=>({id:m.manager_id,status:m.status,slot_count:m.data?.slots?.length,inventory_count:m.data?.models?.length,streaming:m.data?.chat?.streaming===true,dynamic_slots:Array.isArray(m.data?.control?.slots)})),catalog_rows:document.querySelectorAll(".manager-model-row").length,control_buttons:[...document.querySelectorAll(".manager-model-action")].map(b=>({label:b.textContent,disabled:b.disabled})),thinking_control:!!document.getElementById("chat-thinking"),reasoning_control:!!document.getElementById("chat-show-reasoning")})');
  assert.equal(state.url,lifecycle.final_url);assert(state.catalog_rows>=3);
  assert(state.managers.some(m=>m.status==='online'&&m.slot_count===3&&m.inventory_count===2));
  assert(state.control_buttons.every(b=>b.disabled));assert(state.thinking_control&&state.reasoning_control);
  assert.deepEqual(browser.errors,[]);
  await browser.call('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  const layout=await browser.call('Page.getLayoutMetrics');
  const screenshot=await browser.call('Page.captureScreenshot',{format:'png',captureBeyondViewport:true,clip:{x:0,y:0,width:1440,height:Math.ceil(layout.cssContentSize.height),scale:1}});
  await fs.writeFile(path.join(report,'stage_d_live_overview.png'),Buffer.from(screenshot.data,'base64'));
  const result={status:'PASS',scope:'Real Production Client / real Manager GET / separate test Chrome DOM',state,
    console_errors:browser.errors,history_content_read_or_exported:false,model_generation:false,model_control:false,
    manager_gate:'Existing Manager has no stream v2 or dynamic slots; no feature emulation',qa_chrome_profile:profile};
  await fs.writeFile(path.join(report,'stage_d_ui.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
}finally{await browser.close();}
