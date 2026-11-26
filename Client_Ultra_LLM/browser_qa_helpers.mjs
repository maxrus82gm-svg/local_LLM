import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
export const delay=ms=>new Promise(resolve=>setTimeout(resolve,ms));
// QA-only: independent from Manager/Client runtime networking settings.
export async function waitForDevToolsPort(child,folder){
  const started=performance.now();
  const seconds=Number(globalThis.process.env.UL_QA_CHROME_STARTUP_SECONDS ?? '30');
  if(!Number.isInteger(seconds)||seconds<10||seconds>120)throw Error('Invalid Chrome startup seconds (10–120)');
  let spawnError;
  child.once('error',error=>{spawnError=error;});
  while(performance.now()-started<seconds*1000){
    if(spawnError)throw Error('Chrome spawn failed: '+(spawnError.code||spawnError.name));
    if(child.exitCode!==null||child.signalCode!==null)throw Error('Chrome exited before DevTools: '+(child.exitCode??child.signalCode));
    let port;
    try{port=Number((await fs.readFile(path.join(folder,'DevToolsActivePort'),'utf8')).split('\n')[0]);}catch{}
    if(Number.isInteger(port)&&port>0&&port<=65535)return port;
    await delay(100);
  }
  throw Error('Chrome DevTools startup deadline: '+seconds+'s; elapsed '+Math.round(performance.now()-started)+'ms; exit='+child.exitCode);
}
export async function chromeSession(url,folder){
  const process=spawn('C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',[
    '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-background-networking',
    `--user-data-dir=${folder}`,'--remote-debugging-port=0',url],{windowsHide:true,stdio:'ignore'});
  let ws;
  try{
    const port=await waitForDevToolsPort(process,folder);
    const tabs=await(await fetch(`http://127.0.0.1:${port}/json/list`)).json();
    ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
    await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
    let id=0;const pending=new Map();const errors=[],dialogs=[];let acceptDialogs=false;
    ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);if(!p)return;pending.delete(m.id);clearTimeout(p.timer);
      if(m.error)p.reject(Error(m.error.message));else p.resolve(m.result);}
      if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.text);
      if(m.method==='Page.javascriptDialogOpening'){dialogs.push(m.params.message);call('Page.handleJavaScriptDialog',{accept:acceptDialogs});}};
    const call=(method,params={},sessionId)=>new Promise((resolve,reject)=>{const n=++id;
      const timer=setTimeout(()=>{pending.delete(n);reject(Error(`CDP deadline: ${method}`));},15000);
      pending.set(n,{resolve,reject,timer});ws.send(JSON.stringify({id:n,method,params,...(sessionId?{sessionId}:{})}));});
    await call('Runtime.enable');
    await call('Page.enable');
    const evaluate=async expression=>{const r=await call('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
      if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
    const until=async expression=>{for(let i=0;i<200;i++){if(await evaluate(expression))return;await delay(50);}throw Error(`DOM deadline: ${expression}`);};
    return {call,evaluate,until,errors,dialogs,setDialogAcceptance(value){acceptDialogs=value;},async close(){try{await call('Browser.close');}finally{ws.close();await delay(500);if(process.exitCode===null)process.kill();}}};
  }catch(error){if(ws)ws.close();if(process.exitCode===null)process.kill();throw error;}
}
