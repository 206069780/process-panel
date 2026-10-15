"""Thread-safe cached system snapshots. No HTTP or UI dependencies."""

import copy
import ctypes
import os
import platform
import socket
import threading
import time

import psutil

from .processes import protection_reason


class Monitor:
    def __init__(self, interval=2):
        self.interval = interval
        self._lock = threading.Lock()
        self._refresh_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._data = {'ready': False, 'system': {}, 'connections': [], 'processes': [], 'warnings': []}
        psutil.cpu_percent(None)

    def refresh(self):
        with self._refresh_lock:
            data = self._collect()
            with self._lock:
                self._data = data
            return copy.deepcopy(data)

    def snapshot(self):
        with self._lock:
            return copy.deepcopy(self._data)

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, daemon=True, name='system-sampler')
            self._thread.start()

    def close(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)

    def _run(self):
        while not self._stop.is_set():
            try:
                self.refresh()
            except Exception:
                # Retain the last snapshot and make the failure visible.
                with self._lock:
                    self._data = {**self._data, 'warnings': ['系统数据采集失败，正在重试']}
            self._stop.wait(self.interval)

    def _collect(self):
        processes = []
        cpus = psutil.cpu_count() or 1
        for process in psutil.process_iter(['pid', 'name', 'create_time', 'memory_info'], ad_value=None):
            try:
                info = process.info
                name = info['name'] or '未知进程'
                memory = info['memory_info']
                processes.append({
                    'pid': info['pid'], 'name': name, 'create_time': info['create_time'],
                    'memory': memory.rss if memory else None,
                    'cpu': round(min(100, process.cpu_percent(None) / cpus), 1),
                    'ports': [], 'protected_reason': protection_reason(info['pid'], name),
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                continue
        owners = {p['pid']: p for p in processes}
        warnings = []
        connections = []
        try:
            raw_connections = psutil.net_connections(kind='inet')
        except psutil.AccessDenied:
            raw_connections = []
            warnings.append('端口数据访问受限，请以管理员身份重新启动面板')
        for connection in raw_connections:
            if not connection.laddr:
                continue
            owner = owners.get(connection.pid)
            protocol = 'TCP' if connection.type == socket.SOCK_STREAM else 'UDP'
            entry = {
                'protocol': protocol, 'address': connection.laddr.ip, 'port': connection.laddr.port,
                'remote_address': connection.raddr.ip if connection.raddr else None,
                'remote_port': connection.raddr.port if connection.raddr else None,
                'state': connection.status if protocol == 'TCP' else 'BOUND',
                'pid': connection.pid, 'name': owner['name'] if owner else '未知 / 已退出',
                'create_time': owner['create_time'] if owner else None,
                'memory': owner['memory'] if owner else None,
                'cpu': owner['cpu'] if owner else None,
                'protected_reason': owner['protected_reason'] if owner else '进程信息不可用',
            }
            connections.append(entry)
            if owner:
                owner['ports'].append(connection.laddr.port)
        for process in processes:
            process['ports'] = sorted(set(process['ports']))
        memory = psutil.virtual_memory()
        listeners = {(c['protocol'], c['port']) for c in connections if c['state'] in ('LISTEN', 'BOUND')}
        admin = bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == 'nt' else os.geteuid() == 0
        return {
            'ready': True, 'updated_at': time.time(), 'warnings': warnings,
            'system': {
                'hostname': socket.gethostname(), 'platform': f'{platform.system()} {platform.release()}',
                'cpu_percent': psutil.cpu_percent(None), 'cpu_count': cpus,
                'memory_percent': memory.percent, 'memory_used': memory.used, 'memory_total': memory.total,
                'process_count': len(processes), 'listen_count': len(listeners),
                'tcp_count': sum(c['protocol'] == 'TCP' for c in connections),
                'udp_count': sum(c['protocol'] == 'UDP' for c in connections),
                'uptime': time.time() - psutil.boot_time(), 'admin': admin,
            },
            'processes': sorted(processes, key=lambda p: p['pid']),
            'connections': sorted(connections, key=lambda c: (c['port'], c['protocol'], c['pid'] or 0)),
        }
