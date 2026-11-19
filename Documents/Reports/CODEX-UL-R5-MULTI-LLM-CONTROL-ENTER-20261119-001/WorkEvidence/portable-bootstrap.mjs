// Local, synthetic packaged-client QA. Copy into the task's QA source mirror.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import fs from 'node:fs/promises';
import path from 'node:path';
import {delay} from './browser_qa_helpers.mjs';

export async function bootstrapPortable(root) {
  const task = 'CODEX-UL-R5-MULTI-LLM-CONTROL-ENTER-20261119-001';
  const taskRoot = await fs.realpath(process.env.UL_QA_TASK_ROOT);
  const candidate = await fs.realpath(process.env.UL_QA_PORTABLE_EXE);
  const localAppData = await fs.realpath(process.env.LOCALAPPDATA);
  assert.equal(path.basename(taskRoot), task);
  assert(candidate.startsWith(path.join(taskRoot, 'build', 'Client') + path.sep));
  assert(localAppData.startsWith(path.join(taskRoot, 'scratch') + path.sep));
  assert.equal(path.basename(candidate), 'UltraLLMClient.exe');
  const profile = path.join(localAppData, 'UltraLLM', 'Client');
  const portFile = path.join(profile, '.web-client.port');
  const args = ['--no-browser', '--config-dir', profile];
  const run = () => spawn(candidate, args, {cwd:localAppData, windowsHide:true, stdio:'ignore'});
  const first = run();
  await once(first, 'spawn', {signal:AbortSignal.timeout(8000)});
  let url;
  let duplicate;
  const close = async () => {
    for (const child of [duplicate, first]) {
      if (child?.exitCode === null && child.signalCode === null) {
        const exited = once(child, 'exit', {signal:AbortSignal.timeout(6000)});
        child.kill();
        await exited;
      }
    }
    if (url) await assert.rejects(fetch(url, {signal:AbortSignal.timeout(2500)}));
  };
  try {
    const deadline = performance.now() + 15000;
    let port;
    while (performance.now() < deadline && first.exitCode === null) {
      try { port = Number(await fs.readFile(portFile,'utf8')); break; }
      catch (error) { if (error.code !== 'ENOENT') throw error; }
      await delay(100);
    }
    assert(Number.isInteger(port) && port > 0 && port < 65536, 'Isolated packaged Client listener missing');
    url = 'http://127.0.0.1:' + port;
    // These are the synthetic profile and credential of the loopback fixture.
    for (const name of ['managers.json', 'qa-cert.pem', 'qa-token.txt']) {
      await fs.copyFile(path.join(root, 'fixture', name), path.join(profile, name));
    }
    duplicate = run();
    const [secondExit] = await once(duplicate, 'exit', {signal:AbortSignal.timeout(8000)});
    assert.equal(secondExit, 0, 'Duplicate launch must exit');
    assert.equal(Number(await fs.readFile(portFile,'utf8')), port);
    assert.equal(first.exitCode, null);
    const status = await fetch(url + '/api/status', {signal:AbortSignal.timeout(7000)});
    assert.equal(status.status, 200);
    const snapshot = await status.json();
    assert.equal(snapshot.managers.length, 1);
    assert.equal(snapshot.managers[0].manager_id, 'qa-manager');
    assert.equal(snapshot.managers[0].status, 'online');
    console.log(JSON.stringify({isolated_exe:true, pid:first.pid, port, duplicate_exit:secondExit, manager:'synthetic TLS'}));
    return {url, close};
  } catch (error) {
    await close();
    throw error;
  }
}
