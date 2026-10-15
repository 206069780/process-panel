import {formatBytes, selectRows} from './model.mjs';

const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="panel-token"]').content;
const state = {
  snapshot: {ready: false, connections: [], processes: []}, view: 'ports', query: '',
  protocol: 'all', state: 'listening', sortKey: 'port', sortDir: 'asc', page: 1, pageSize: 12,
  automatic: true, busy: false, online: false, terminating: false, selected: null, target: null,
  cpuHistory: [], memoryHistory: [], lastSample: 0,
};
const dateTime = new Intl.DateTimeFormat('zh-CN', {hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false});
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const icon = name => `<svg class="icon" aria-hidden="true"><use href="#i-${name}"/></svg>`;
let toastTimer;

function toast(message, error = false) {
  clearTimeout(toastTimer);
  $('toast').textContent = message;
  $('toast').className = `toast${error ? ' error' : ''}`;
  toastTimer = setTimeout(() => $('toast').classList.add('hidden'), error ? 6500 : 4000);
}

async function api(path, body) {
  const response = await fetch(path, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {'X-Panel-Token': token, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(20000), cache: 'no-store', credentials: 'omit',
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || '请求未完成，请重试');
  return data;
}

function avatar(name) {
  const text = String(name || '?').toLowerCase();
  const [kind, label] = text.includes('node') ? ['node', 'N'] : text.includes('python') ? ['python', 'Py'] :
    text.includes('java') ? ['java', 'J'] : /chrome|edge|firefox/.test(text) ? ['browser', 'B'] : ['', text.slice(0, 2).toUpperCase()];
  return `<span class="process-avatar ${kind}">${esc(label)}</span>`;
}

function sparkline(id, values) {
  if (!values.length) return;
  const points = values.map((value, i) => `${i * 120 / Math.max(1, values.length - 1)},${28 - value * .25}`).join(' ');
  $(id).innerHTML = `<polyline points="${points}" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>`;
}

function renderMetrics() {
  const {system: s, updated_at: updated} = state.snapshot;
  if (!s || !state.snapshot.ready) return;
  $('cpu-value').textContent = s.cpu_percent.toFixed(1);
  $('memory-value').textContent = s.memory_percent.toFixed(1);
  $('process-value').textContent = s.process_count;
  $('port-value').textContent = s.listen_count;
  $('cpu-meta').textContent = `${s.cpu_count} 个逻辑处理器`;
  $('memory-meta').textContent = `${formatBytes(s.memory_used)} / ${formatBytes(s.memory_total)}`;
  $('nav-ports').textContent = s.listen_count;
  $('nav-processes').textContent = s.process_count;
  $('ports-tab-count').textContent = state.snapshot.connections.length;
  $('processes-tab-count').textContent = s.process_count;
  $('sidebar-host').textContent = s.hostname;
  $('machine-name').textContent = s.hostname;
  $('machine-os').textContent = s.platform;
  const hours = Math.floor(s.uptime / 3600);
  $('machine-uptime').textContent = `${Math.floor(hours / 24)} 天 ${hours % 24} 小时`;
  $('machine-permission').textContent = s.admin ? '管理员' : '普通用户';
  $('machine-permission').classList.toggle('admin', s.admin);
  const total = s.tcp_count + s.udp_count;
  $('network-total').textContent = total;
  $('tcp-count').textContent = s.tcp_count;
  $('udp-count').textContent = s.udp_count;
  $('tcp-bar').style.width = `${total ? s.tcp_count / total * 100 : 0}%`;
  $('udp-bar').style.width = `${total ? s.udp_count / total * 100 : 0}%`;
  $('updated-at').textContent = `最近更新 ${dateTime.format(updated * 1000)}`;
  if (state.lastSample !== updated) {
    state.lastSample = updated;
    state.cpuHistory.push(s.cpu_percent);
    state.memoryHistory.push(s.memory_percent);
    if (state.cpuHistory.length > 30) { state.cpuHistory.shift(); state.memoryHistory.shift(); }
    sparkline('cpu-chart', state.cpuHistory);
    sparkline('memory-chart', state.memoryHistory);
  }
  const top = [...state.snapshot.processes].filter(p => p.memory != null && p.pid > 4).sort((a, b) => b.memory - a.memory).slice(0, 5);
  $('top-processes').innerHTML = top.map(p => `<div class="top-process">${avatar(p.name)}<div><button class="top-process-name" data-detail-pid="${p.pid}" title="查看 ${esc(p.name)} 详情">${esc(p.name)}</button><div class="rank-progress"><span style="width:${Math.max(3, p.memory / (top[0]?.memory || 1) * 100)}%"></span></div></div><span class="top-process-amount">${formatBytes(p.memory)}</span></div>`).join('');
}

function setConnection(online) {
  state.online = online;
  $('connection-state').classList.toggle('offline', !online);
  $('connection-text').textContent = online ? state.snapshot.ready ? '实时连接' : '采集中' : '连接中断';
  $('footer-dot').style.background = online ? 'var(--mint)' : 'var(--red)';
}

function setNotice(message) {
  $('notice').textContent = message;
  $('notice').classList.toggle('hidden', !message);
}

async function loadData(force = false) {
  if (state.busy || state.terminating) return;
  state.busy = true;
  $('refresh-button').disabled = true;
  if (force) $('refresh-button').classList.add('spinning');
  try {
    const snapshot = await api(force ? '/api/refresh' : '/api/snapshot', force ? {} : undefined);
    if (!state.snapshot.updated_at || !snapshot.updated_at || snapshot.updated_at >= state.snapshot.updated_at) state.snapshot = snapshot;
    setConnection(true);
    const warnings = [...(snapshot.warnings || [])];
    if (snapshot.updated_at && Date.now() / 1000 - snapshot.updated_at > 10) warnings.push('当前数据已超过 10 秒未更新，系统正在重新采集');
    setNotice(warnings.join('；'));
    if (snapshot.ready) { renderMetrics(); renderTable(); }
    if (force) toast('数据已刷新');
  } catch (error) {
    setConnection(false);
    setNotice(error.name === 'TimeoutError' ? '读取超时，请稍后刷新' : `无法读取数据：${error.message}。请确认启动窗口中的服务仍在运行。`);
    if (force) toast('刷新失败，请检查本地服务', true);
  } finally {
    state.busy = false;
    $('refresh-button').disabled = false;
    $('refresh-button').classList.remove('spinning');
  }
}

function sortable(label, key) {
  const active = state.sortKey === key;
  return `<th scope="col" aria-sort="${active ? state.sortDir === 'asc' ? 'ascending' : 'descending' : 'none'}"><button data-sort="${key}" aria-pressed="${active}">${label}<span class="sort-arrow">${active ? state.sortDir === 'asc' ? '↑' : '↓' : '↕'}</span></button></th>`;
}

function connectionBadge(row) {
  const label = {LISTEN: '监听中', BOUND: '已绑定', ESTABLISHED: '已连接', TIME_WAIT: '等待关闭', CLOSE_WAIT: '等待关闭', SYN_SENT: '连接中', FIN_WAIT1: '正在关闭', FIN_WAIT2: '正在关闭'}[row.state] || row.state;
  const kind = row.state === 'ESTABLISHED' ? 'established' : ['LISTEN', 'BOUND'].includes(row.state) ? '' : 'other';
  return `<span class="state-badge ${kind}" title="${esc(row.state)}"><span class="mini-dot"></span>${esc(label)}</span>`;
}

function actions(row, index) {
  const blocked = row.protected_reason || !row.create_time || row.pid == null;
  return `<div class="row-actions"><button class="text-button" data-action="detail" data-row="${index}" ${row.pid == null ? 'disabled' : ''}>详情</button><span class="action-divider"></span><button class="text-button kill" data-action="kill" data-row="${index}" ${blocked ? 'disabled' : ''} title="${esc(blocked ? row.protected_reason || '无法验证进程身份' : `结束 ${row.name}`)}">${row.protected_reason ? '受保护' : '结束'}</button></div>`;
}

let displayedRows = [];
function renderTable() {
  if (!state.snapshot.ready) return;
  const focused = document.activeElement;
  const focusRow = focused?.closest('#table-body [data-row]');
  const focusIdentity = focusRow ? displayedRows[Number(focusRow.dataset.row)] : null;
  const focusAction = focusRow?.dataset.action;
  const result = selectRows(state.snapshot, state);
  displayedRows = result.rows;
  state.page = result.page;
  const portsView = state.view === 'ports';
  const newHead = portsView
    ? `<tr>${sortable('端口', 'port')}${sortable('协议', 'protocol')}<th scope="col">本地地址</th>${sortable('进程 / PID', 'name')}${sortable('状态', 'state')}${sortable('内存', 'memory')}<th scope="col">操作</th></tr>`
    : `<tr>${sortable('进程名称', 'name')}${sortable('PID', 'pid')}<th scope="col">占用端口</th>${sortable('CPU', 'cpu')}${sortable('内存', 'memory')}<th scope="col">操作</th></tr>`;
  if ($('table-head').innerHTML !== newHead) $('table-head').innerHTML = newHead;
  if (!result.rows.length) {
    $('table-body').innerHTML = `<tr><td colspan="${portsView ? 7 : 6}"><div class="empty-state">${icon('search')}<strong>没有找到匹配的${portsView ? '端口' : '进程'}</strong><p>试试其他端口号、PID 或进程名称，<br>也可以调整协议和状态筛选。</p><button class="button" data-reset>清除筛选</button></div></td></tr>`;
  } else {
    $('table-body').innerHTML = result.rows.map((row, index) => {
      const process = `<div class="process-cell">${avatar(row.name)}<div><button class="process-name" data-action="detail" data-row="${index}" title="${esc(row.name)}" ${row.pid == null ? 'disabled' : ''}>${esc(row.name)}</button>${portsView ? `<div class="pid-label">PID ${row.pid ?? '—'}</div>` : ''}</div></div>`;
      if (portsView) return `<tr><td><span class="port-number">${row.port}</span></td><td><span class="protocol-badge ${row.protocol === 'UDP' ? 'udp' : ''}">${row.protocol}</span></td><td class="address mono" title="${esc(row.address)}${row.remote_address ? ` → ${esc(row.remote_address)}:${row.remote_port}` : ''}">${esc(row.address)}</td><td>${process}</td><td>${connectionBadge(row)}</td><td class="mono muted">${formatBytes(row.memory)}</td><td>${actions(row, index)}</td></tr>`;
      const ports = row.ports.slice(0, 3).join(', ') + (row.ports.length > 3 ? ` +${row.ports.length - 3}` : '');
      return `<tr><td>${process}</td><td class="mono">${row.pid}</td><td class="mono address" title="${row.ports.join(', ')}">${ports || '—'}</td><td class="mono">${row.cpu == null ? '—' : row.cpu.toFixed(1) + '%'}</td><td class="mono">${formatBytes(row.memory)}</td><td>${actions(row, index)}</td></tr>`;
    }).join('');
  }
  if (focusIdentity && focusAction) {
    const index = displayedRows.findIndex(row => row.pid === focusIdentity.pid && row.create_time === focusIdentity.create_time && row.port === focusIdentity.port);
    $('table-body').querySelector(`[data-row="${index}"][data-action="${focusAction}"]`)?.focus({preventScroll: true});
  }
  const from = result.total ? (result.page - 1) * state.pageSize + 1 : 0;
  const to = Math.min(result.page * state.pageSize, result.total);
  $('result-summary').innerHTML = `共 <strong>${result.total}</strong> 条${portsView ? '端口记录' : '进程'}<span class="muted"> · ${from}–${to}</span>`;
  $('page-label').textContent = `${result.page} / ${result.pageCount}`;
  $('previous-page').disabled = result.page <= 1;
  $('next-page').disabled = result.page >= result.pageCount;
  $('protocol-filter').classList.toggle('hidden', !portsView);
  $('state-filter').classList.toggle('hidden', !portsView);
  $('clear-filters').classList.toggle('hidden', !state.query && state.protocol === 'all' && state.state === 'listening');
  document.querySelectorAll('[data-port]').forEach(b => b.classList.toggle('active', state.query === `:${b.dataset.port}`));
}

function changeView(view) {
  state.view = view;
  state.page = 1;
  state.sortKey = view === 'ports' ? 'port' : 'memory';
  state.sortDir = view === 'ports' ? 'asc' : 'desc';
  document.querySelectorAll('[data-view]').forEach(button => {
    const active = button.dataset.view === view;
    button.classList.toggle('active', active);
    if (button.hasAttribute('role')) button.setAttribute('aria-selected', String(active));
  });
  renderTable();
}

function resetFilters() {
  Object.assign(state, {query: '', protocol: 'all', state: 'listening', page: 1});
  $('search').value = '';
  $('protocol-filter').value = 'all';
  $('state-filter').value = 'listening';
  renderTable();
}

function rowPorts(row) {
  return [...new Set(state.snapshot.connections.filter(c => c.pid === row.pid && c.create_time === row.create_time).map(c => `${c.protocol} :${c.port}`))];
}

let detailSequence = 0;
async function showDetail(row) {
  const sequence = ++detailSequence;
  $('detail-title').textContent = row.name || '进程详情';
  $('detail-content').innerHTML = '<div class="empty-state"><span class="loading-ring"></span><strong>正在读取进程详情</strong></div>';
  $('detail-terminate').disabled = true;
  $('copy-detail').disabled = true;
  state.selected = null;
  if (!$('detail-dialog').open) $('detail-dialog').showModal();
  try {
    const detail = await api(`/api/processes/${row.pid}`);
    if (sequence !== detailSequence || !$('detail-dialog').open) return;
    if (row.create_time && Math.abs(detail.create_time - row.create_time) > .001) throw new Error('进程身份已变化，请刷新后重新选择');
    state.selected = detail;
    $('detail-title').textContent = detail.name;
    const ports = [...new Set(detail.connections.map(c => `${c.protocol} :${c.port}`))];
    const field = (label, value, wide = false, raw = false) => `<div class="detail-field${wide ? ' wide' : ''}"><dt>${label}</dt><dd>${raw ? value : esc(value ?? '无权限读取')}</dd></div>`;
    $('detail-content').innerHTML = `<dl class="detail-grid">${field('进程 ID', detail.pid)}${field('内存使用', formatBytes(detail.memory))}${field('启动时间', new Date(detail.create_time * 1000).toLocaleString('zh-CN'))}${field('所属用户', detail.username)}${field('可执行文件', `<div class="code-block">${esc(detail.exe || '无权限读取')}</div>`, true, true)}${field('启动命令', `<div class="code-block">${esc(detail.cmdline == null ? '无权限读取' : detail.cmdline.join(' '))}</div>`, true, true)}${field('当前占用端口', ports.length ? `<div class="detail-ports">${ports.map(p => `<span>${esc(p)}</span>`).join('')}</div>` : '此快照中无端口记录', true, true)}</dl>${detail.protected_reason ? `<p class="protected-note">${icon('shield')} ${esc(detail.protected_reason)}</p>` : ''}`;
    $('detail-terminate').disabled = !!detail.protected_reason;
    $('detail-terminate').title = detail.protected_reason || '';
    $('copy-detail').disabled = false;
  } catch (error) {
    if (sequence === detailSequence && $('detail-dialog').open) $('detail-content').innerHTML = `<p class="inline-error">${esc(error.message)}</p>`;
  }
}

function showTerminate(row) {
  if (state.terminating || !row || row.protected_reason || !row.create_time || row.pid == null) return;
  state.target = {...row};
  const ports = rowPorts(row);
  $('terminate-target').innerHTML = `<strong>${esc(row.name)}</strong><p class="mono">PID ${row.pid}</p><p>占用端口：${ports.length ? esc(ports.slice(0, 12).join('、')) + (ports.length > 12 ? ` 等 ${ports.length} 个` : '') : '此快照中无端口记录'}</p>`;
  $('terminate-error').classList.add('hidden');
  $('confirm-terminate').disabled = false;
  $('confirm-terminate').textContent = '确认结束进程';
  if (!$('terminate-dialog').open) $('terminate-dialog').showModal();
  $('cancel-terminate').focus();
}

async function confirmTerminate() {
  if (state.terminating || !state.target) return;
  state.terminating = true;
  const target = state.target;
  $('confirm-terminate').disabled = true;
  document.querySelectorAll('[data-close="terminate-dialog"]').forEach(button => { button.disabled = true; });
  $('confirm-terminate').textContent = '正在结束…';
  $('terminate-error').classList.add('hidden');
  try {
    const result = await api(`/api/processes/${target.pid}/terminate`, {create_time: target.create_time});
    $('terminate-dialog').close();
    $('detail-dialog').close();
    toast(`${target.name} (PID ${target.pid})：${result.message}`);
  } catch (error) {
    $('terminate-error').textContent = error.name === 'TimeoutError' ? '等待结果超时，请刷新确认进程状态' : error.message;
    $('terminate-error').classList.remove('hidden');
  } finally {
    state.terminating = false;
    document.querySelectorAll('[data-close="terminate-dialog"]').forEach(button => { button.disabled = false; });
    $('confirm-terminate').disabled = false;
    $('confirm-terminate').textContent = '确认结束进程';
    await loadData();
  }
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => changeView(button.dataset.view)));
$('search').addEventListener('input', event => { state.query = event.target.value; state.page = 1; renderTable(); });
for (const [id, key] of [['protocol-filter', 'protocol'], ['state-filter', 'state'], ['page-size', 'pageSize']]) {
  $(id).addEventListener('change', event => { state[key] = key === 'pageSize' ? Number(event.target.value) : event.target.value; state.page = 1; renderTable(); });
}
$('clear-filters').addEventListener('click', resetFilters);
document.querySelectorAll('[data-port]').forEach(button => button.addEventListener('click', () => { state.query = `:${button.dataset.port}`; $('search').value = state.query; state.page = 1; renderTable(); }));
$('table-head').addEventListener('click', event => {
  const button = event.target.closest('[data-sort]');
  if (!button) return;
  state.sortDir = state.sortKey === button.dataset.sort && state.sortDir === 'asc' ? 'desc' : 'asc';
  state.sortKey = button.dataset.sort;
  renderTable();
});
$('table-body').addEventListener('click', event => {
  if (event.target.closest('[data-reset]')) return resetFilters();
  const button = event.target.closest('[data-action]');
  if (!button || button.disabled) return;
  const row = displayedRows[Number(button.dataset.row)];
  if (row) button.dataset.action === 'detail' ? showDetail(row) : showTerminate(row);
});
$('top-processes').addEventListener('click', event => {
  const button = event.target.closest('[data-detail-pid]');
  const process = state.snapshot.processes.find(p => p.pid === Number(button?.dataset.detailPid));
  if (process) showDetail(process);
});
$('previous-page').addEventListener('click', () => { state.page--; renderTable(); });
$('next-page').addEventListener('click', () => { state.page++; renderTable(); });
$('show-memory-processes').addEventListener('click', () => { resetFilters(); changeView('processes'); });
$('auto-refresh').addEventListener('change', event => {
  state.automatic = event.target.checked;
  $('sampling-text').textContent = state.automatic ? '每 2 秒采集' : '页面更新已暂停';
  if (state.automatic) loadData();
});
$('refresh-button').addEventListener('click', () => loadData(true));
$('help-button').addEventListener('click', () => $('help-dialog').showModal());
$('fullscreen-button').addEventListener('click', async () => {
  try { document.fullscreenElement ? await document.exitFullscreen() : await document.documentElement.requestFullscreen(); }
  catch { toast('切换全屏失败，可使用 F11', true); }
});
document.querySelectorAll('[data-close]').forEach(button => button.addEventListener('click', () => {
  if (button.dataset.close === 'terminate-dialog' && state.terminating) return;
  $(button.dataset.close).close();
}));
$('detail-terminate').addEventListener('click', () => showTerminate(state.selected));
$('confirm-terminate').addEventListener('click', confirmTerminate);
$('copy-detail').addEventListener('click', async () => {
  const detail = state.selected;
  if (!detail) return;
  try {
    await navigator.clipboard.writeText(`进程：${detail.name}\nPID：${detail.pid}\n启动时间：${new Date(detail.create_time * 1000).toLocaleString('zh-CN')}\n路径：${detail.exe || '无权限读取'}\n命令：${detail.cmdline?.join(' ') || '无权限读取'}\n端口：${rowPorts(detail).join(', ') || '无'}`);
    toast('进程信息已复制');
  } catch { toast('复制失败，请重试', true); }
});
document.querySelectorAll('dialog').forEach(dialog => {
  dialog.addEventListener('cancel', event => { if (state.terminating && dialog.id === 'terminate-dialog') event.preventDefault(); });
});
document.addEventListener('keydown', event => {
  if (event.key === '/' && !document.querySelector('dialog[open]') && !['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement.tagName)) { event.preventDefault(); $('search').focus(); }
});
$('current-date').textContent = new Date().toLocaleDateString('zh-CN', {year: 'numeric', month: '2-digit', day: '2-digit'});
setInterval(() => { if (state.automatic && !document.hidden) loadData(); }, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden && state.automatic) loadData(); });
loadData();
