import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {formatBytes, selectRows} from '../static/model.mjs';

// Browser boundary is simulated so a pending destructive request can be held
// deterministically; the actual application state machine executes unchanged.
async function application() {
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
    setInterval(){},setTimeout(){},clearTimeout(){},navigator:{},
    fetch:async path=>path.endsWith('/terminate') ? pending : {ok:true,json:async()=>({ready:false,warnings:[],connections:[],processes:[]})},
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
