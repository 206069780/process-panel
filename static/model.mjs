const collator = new Intl.Collator('zh-CN', {numeric: true, sensitivity: 'base'});

export function formatBytes(value) {
  if (value == null || !Number.isFinite(value)) return '—';
  if (value === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(units.length - 1, Math.max(0, Math.floor(Math.log(value) / Math.log(1024))));
  return `${(value / 1024 ** index).toFixed(index ? 1 : 0)} ${units[index]}`;
}

export function selectRows(snapshot, options = {}) {
  const {view = 'ports', protocol = 'all', state = 'all', sortKey = view === 'ports' ? 'port' : 'memory',
    sortDir = view === 'ports' ? 'asc' : 'desc', page = 1, pageSize = 12} = options;
  const query = (options.query || '').trim().toLowerCase();
  let rows = [...(view === 'ports' ? snapshot.connections : snapshot.processes) || []];
  rows = rows.filter(row => {
    if (view === 'ports') {
      if (protocol !== 'all' && row.protocol !== protocol) return false;
      if (state === 'listening' && !['LISTEN', 'BOUND'].includes(row.state)) return false;
      if (state === 'established' && row.state !== 'ESTABLISHED') return false;
    }
    const ports = view === 'ports' ? [row.port] : row.ports;
    if (/^pid:\d+$/.test(query)) return row.pid === Number(query.slice(4));
    if (/^:\d+$/.test(query)) return ports?.includes(Number(query.slice(1)));
    return !query || [row.name, row.pid, ...(ports || []), row.address, row.remote_address]
      .some(value => value != null && String(value).toLowerCase().includes(query));
  });
  rows.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (av == null && bv == null) return 0;
    if (av == null) return 1;
    if (bv == null) return -1;
    const result = typeof av === 'number' ? av - bv : collator.compare(String(av), String(bv));
    return result * (sortDir === 'desc' ? -1 : 1) || (a.pid || 0) - (b.pid || 0);
  });
  const total = rows.length;
  const pageCount = Math.max(1, Math.ceil(total / pageSize));
  const currentPage = Math.min(pageCount, Math.max(1, page));
  return {rows: rows.slice((currentPage - 1) * pageSize, currentPage * pageSize), total, pageCount, page: currentPage};
}
