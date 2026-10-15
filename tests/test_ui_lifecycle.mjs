import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {formatBytes, selectRows} from '../static/model.mjs';

// Browser boundary is simulated so a pending destructive request can be held
// deterministically; the actual application state machine executes unchanged.
async function application({clock, snapshot} = {}) {
  const elements = new Map();
  const get = id => {
    if (!elements.has(id)) elements.set(id, {
      id, open:false, disabled:false, textContent:'', value:'', innerHTML:'', style:{},
      dataset:{}, listeners:{}, classList:{add(){},remove(){},toggle(){}},
      addEventListener(type, listener) { this.listeners[type] = listener; },
      showModal() { this.open = true; }, close() { this.open = false; }, focus(){},
      click() { if (!this.disabled) this.listeners.click?.({target:this}); },
    });
    return elements.get(id);
  };
  const cancel = get('cancel-terminate'); cancel.dataset.close = 'terminate-dialog';
  const close = get('close-terminate'); close.dataset.close = 'terminate-dialog';
  let finish;
  const pending = new Promise(resolve => { finish = () => resolve({ok:true,json:async()=>({message:'进程已结束'})}); });
  const context = vm.createContext({
    document:{getElementById:get,querySelector:()=>({content:'test-token'}),
      querySelectorAll:selector=>selector.startsWith('[data-close') ? [cancel, close] : [],
      addEventListener(){},hidden:false},
    formatBytes, selectRows, AbortSignal, Intl, Date, Math, Number, String, Set,
    setInterval:clock?.setInterval.bind(clock) || (()=>{}),
    setTimeout:clock?.setTimeout.bind(clock) || (()=>{}),
    clearTimeout:clock?.clearTimeout.bind(clock) || (()=>{}),navigator:{},
    fetch:async path=>path.endsWith('/terminate') ? pending : {ok:true,json:async()=>snapshot ? snapshot() : ({ready:false,warnings:[],connections:[],processes:[]})},
  });
  const source = (await readFile(new URL('../static/app.js', import.meta.url), 'utf8')).replace(/^import[^\n]+\n/, '');
  vm.runInContext(source, context);
  await new Promise(resolve => setImmediate(resolve));
  return {get, finish, run:script=>vm.runInContext(script,context)};
}

test('pending termination keeps its confirmation open and cannot switch target', async () => {
  const app = await application();
  app.run("showTerminate({pid:101,name:'A.exe',create_time:100})");
  const pending = app.run('confirmTerminate()');
  try {
    app.get('cancel-terminate').click();
    assert.equal(app.get('terminate-dialog').open, true, 'Cancel must not dismiss a request in progress');
    app.get('close-terminate').click();
    assert.equal(app.get('terminate-dialog').open, true, 'Close must not dismiss a request in progress');
    app.run("showTerminate({pid:202,name:'B.exe',create_time:200})");
    assert.equal(app.run('state.target.pid'), 101, 'The active operation must retain its original target');
  } finally {
    app.finish();
    await pending;
  }
  assert.equal(app.get('terminate-dialog').open, false);
  assert.match(app.get('toast').textContent, /A\.exe.*101/);
});

class Clock {
  now = 0;
  nextId = 0;
  jobs = new Map();
  setTimeout(callback, delay) {
    const id = ++this.nextId;
    this.jobs.set(id, {callback, at:this.now + delay});
    return id;
  }
  setInterval(callback, delay) {
    const id = this.setTimeout(callback, delay);
    this.jobs.get(id).interval = delay;
    return id;
  }
  clearTimeout(id) { this.jobs.delete(id); }
  async advance(milliseconds) {
    const target = this.now + milliseconds;
    for (;;) {
      const next = [...this.jobs].filter(([,job])=>job.at <= target).sort((a,b)=>a[1].at-b[1].at)[0];
      if (!next) break;
      const [id, job] = next;
      this.now = job.at;
      this.jobs.delete(id);
      if (job.interval) this.jobs.set(id, {...job, at:this.now + job.interval});
      await job.callback();
      await new Promise(resolve => setImmediate(resolve));
    }
    this.now = target;
  }
}

function readySnapshot() {
  return {ready:true, updated_at:Date.now()/1000, warnings:[],connections:[],processes:[],
    system:{cpu_percent:12.5,memory_percent:30,process_count:0,listen_count:0,cpu_count:4,
      memory_used:1024,memory_total:4096,hostname:'Test PC',platform:'Windows',uptime:100,
      admin:false,tcp_count:0,udp_count:0}};
}

test('initial data appears promptly when the first sample finishes', async () => {
  const clock = new Clock();
  let ready = false;
  let requests = 0;
  const app = await application({clock, snapshot:()=>{
    requests++;
    return ready ? readySnapshot() : {ready:false,warnings:[],connections:[],processes:[]};
  }});
  assert.equal(app.get('connection-text').textContent, '采集中');
  ready = true;
  await clock.advance(500);
  assert.equal(app.get('cpu-value').textContent, '12.5', 'A completed initial sample should appear within 500ms');
  const afterReady = requests;
  await clock.advance(500);
  assert.equal(requests, afterReady, 'Fast initial polling should stop after readiness');
});

test('pausing automatic refresh also pauses initial polling', async () => {
  const clock = new Clock();
  let requests = 0;
  const app = await application({clock, snapshot:()=>{
    requests++;
    return {ready:false,warnings:[],connections:[],processes:[]};
  }});
  app.get('auto-refresh').listeners.change({target:{checked:false}});
  await clock.advance(1000);
  assert.equal(requests, 1);
});
