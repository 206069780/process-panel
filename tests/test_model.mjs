import { test } from 'node:test';
import assert from 'node:assert/strict';
import { selectRows, formatBytes } from '../static/model.mjs';

const snapshot = {
  connections: [
    {pid: 10, name: 'node.exe', port: 3000, protocol: 'TCP', state: 'LISTEN', memory: 200},
    {pid: 20, name: 'python.exe', port: 30001, protocol: 'TCP', state: 'ESTABLISHED', memory: 100},
    {pid: 30, name: 'dns.exe', port: 53, protocol: 'UDP', state: 'BOUND', memory: null},
  ],
  processes: [
    {pid: 10, name: 'node.exe', ports: [3000], memory: 200},
    {pid: 20, name: 'python.exe', ports: [30001], memory: 100},
  ],
};

test('ordinary numeric search matches port fragments', () => {
  assert.deepEqual(selectRows(snapshot, {query: '3000'}).rows.map(r => r.pid), [10, 20]);
  assert.deepEqual(selectRows(snapshot, {query: '00'}).rows.map(r => r.pid), [10, 20]);
});

test('ordinary numeric search matches PID fragments', () => {
  assert.deepEqual(selectRows(snapshot, {query: '2'}).rows.map(r => r.pid), [20]);
});
test('PID search and explicit port search are supported', () => {
  assert.equal(selectRows(snapshot, {query: 'pid:20'}).rows[0].name, 'python.exe');
  assert.equal(selectRows(snapshot, {query: ':53'}).rows[0].name, 'dns.exe');
  assert.deepEqual(selectRows(snapshot, {query: ':3000'}).rows.map(r => r.pid), [10]);
  assert.equal(selectRows(snapshot, {query: 'pid:2'}).total, 0);
});
test('process view can search port fragments', () => {
  assert.deepEqual(selectRows(snapshot, {view: 'processes', query: '3000', sortKey: 'pid', sortDir: 'asc'}).rows.map(r => r.pid), [10, 20]);
});
test('process names match regardless of case', () => {
  assert.equal(selectRows(snapshot, {query: 'PYTHON'}).total, 1);
  assert.equal(selectRows(snapshot, {query: '  THON  '}).rows[0].pid, 20);
});
test('listening filter includes bound UDP endpoints', () => {
  assert.equal(selectRows(snapshot, {state: 'listening'}).total, 2);
});
test('protocol filter is applied', () => {
  assert.equal(selectRows(snapshot, {protocol: 'UDP'}).total, 1);
});
test('null metrics sort last in either direction', () => {
  assert.deepEqual(selectRows(snapshot, {sortKey: 'memory', sortDir: 'desc'}).rows.map(r => r.pid), [10, 20, 30]);
  assert.deepEqual(selectRows(snapshot, {sortKey: 'memory', sortDir: 'asc'}).rows.map(r => r.pid), [20, 10, 30]);
});
test('page numbers are clamped when filters shrink the result', () => {
  const result = selectRows(snapshot, {query: 'node', page: 99, pageSize: 1});
  assert.equal(result.page, 1);
  assert.equal(result.rows.length, 1);
});
test('empty result still has one valid page', () => {
  const result = selectRows(snapshot, {query: 'missing'});
  assert.equal(result.total, 0);
  assert.equal(result.pageCount, 1);
});
test('bytes display handles unavailable and zero values', () => {
  assert.equal(formatBytes(null), '—');
  assert.equal(formatBytes(0), '0 B');
  assert.equal(formatBytes(1024), '1.0 KB');
});
