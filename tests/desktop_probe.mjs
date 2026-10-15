// Inspect the actual packaged Qt page through its test-only loopback debugger.
import assert from 'node:assert/strict';
import { setTimeout as delay } from 'node:timers/promises';

const [endpoint, origin] = process.argv.slice(2);
let target;
for (let attempt = 0; attempt < 150; attempt++) {
  try {
    const targets = await (await fetch(`${endpoint}/json/list`)).json();
    target = targets.find(page => page.type === 'page' && page.url.startsWith(origin));
    if (target) break;
  } catch {}
  await delay(200);
}
assert(target, 'Packaged desktop page did not start');
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, {once: true});
  socket.addEventListener('error', reject, {once: true});
});
let sequence = 0;
const pending = new Map();
socket.addEventListener('message', event => {
  const message = JSON.parse(event.data);
  if (pending.has(message.id)) {
    const {resolve, reject} = pending.get(message.id);
    pending.delete(message.id);
    message.error ? reject(new Error(JSON.stringify(message.error))) : resolve(message.result);
  }
});
function evaluate(expression) {
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    pending.set(id, {resolve: result => {
      if (result.exceptionDetails) reject(new Error(JSON.stringify(result.exceptionDetails)));
      else resolve(result.result.value);
    }, reject});
    socket.send(JSON.stringify({id, method: 'Runtime.evaluate',
      params: {expression, returnByValue: true, awaitPromise: true}}));
  });
}
try {
  let ready = false;
  for (let attempt = 0; attempt < 150; attempt++) {
    ready = await evaluate(`document.querySelector('#connection-text')?.textContent === '实时连接'
      && /^\\d/.test(document.querySelector('#cpu-value')?.textContent || '')
      && !document.querySelector('#table-body .loading-ring')`);
    if (ready) break;
    await delay(200);
  }
  assert(ready, 'Packaged dashboard did not render live data');
  const fuzzy = await evaluate(`(async () => {
    const {selectRows} = await import('/static/model.mjs');
    const snapshot = {connections: [
      {pid: 1, port: 8080, name: 'java.exe'},
      {pid: 2, port: 48080, name: 'node.exe'}], processes: []};
    return {fuzzy: selectRows(snapshot, {query: '80'}).total,
      exact: selectRows(snapshot, {query: ':8080'}).total};
  })()`);
  assert.deepEqual(fuzzy, {fuzzy: 2, exact: 1});
  assert.equal(await evaluate(`document.title`), 'Portside · 本机进程控制台');
  console.log(JSON.stringify({live_dashboard_rendered: true, packaged_fuzzy_search: true}));
} finally {
  socket.close();
}
