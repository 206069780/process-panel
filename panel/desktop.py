"""Desktop instance discovery. Runtime records never contain API credentials."""

import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys

import psutil


def is_admin():
    return bool(ctypes.windll.shell32.IsUserAnAdmin()) if os.name == 'nt' else os.geteuid() == 0


class RuntimeRegistry:
    def __init__(self, root=None):
        if root is None:
            root = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'Portside' / 'runtime' if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent.parent / '.runtime'
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / f'{os.getpid()}.json'

    def find_existing(self, admin=None):
        for path in self.root.glob('*.json'):
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data, dict) or type(data.get('pid')) is not int or data['pid'] <= 0:
                    continue
                created = data.get('create_time')
                if type(created) not in (int, float) or not math.isfinite(created):
                    continue
                match = re.fullmatch(r'http://127\.0\.0\.1:(\d{1,5})', data.get('origin', ''))
                if not match or not 0 < int(match[1]) <= 65535:
                    continue
                if admin is not None and data.get('admin') is not admin:
                    continue
                process = psutil.Process(data['pid'])
                if abs(process.create_time() - created) > .001:
                    continue
                if getattr(sys, 'frozen', False):
                    if os.path.normcase(process.exe()) != os.path.normcase(sys.executable):
                        continue
                else:
                    entry = Path(__file__).resolve().parent.parent / 'main.py'
                    cwd = Path(process.cwd())
                    if not any((cwd / argument).resolve() == entry for argument in process.cmdline()[1:]):
                        continue
                return data
            except (ValueError, TypeError, OSError, psutil.Error):
                continue
        return None

    def register(self, origin, admin):
        data = {'pid': os.getpid(), 'create_time': psutil.Process().create_time(), 'origin': origin, 'admin': admin}
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(data), encoding='utf-8')
        temporary.replace(self.path)

    def unregister(self):
        self.path.unlink(missing_ok=True)


class InstanceLock:
    """Own the mutex, allowing recovery after an interrupted startup."""

    def __init__(self, admin, runtime_dir=None):
        self.handle = None
        self.primary = True
        scope = str(Path(runtime_dir or RuntimeRegistry().root).resolve())
        identity = os.path.normcase(str(Path(sys.executable).resolve()) + scope) + str(admin)
        self.name = 'Portside-' + hashlib.sha256(identity.encode()).hexdigest()[:24]
        if os.name == 'nt':
            from ctypes import wintypes
            self.kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            self.kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            self.kernel.CreateMutexW.restype = wintypes.HANDLE
            self.kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            self.kernel.CloseHandle.restype = wintypes.BOOL
            self.kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            self.kernel.WaitForSingleObject.restype = wintypes.DWORD
            self.kernel.ReleaseMutex.argtypes = [wintypes.HANDLE]
            self.kernel.ReleaseMutex.restype = wintypes.BOOL
            self.handle = self.kernel.CreateMutexW(None, False, f'Local\\{self.name}')
            if not self.handle:
                raise OSError('无法初始化程序实例')
            result = self.kernel.WaitForSingleObject(self.handle, 0)
            if result not in (0, 0x80, 0x102):
                self.kernel.CloseHandle(self.handle)
                self.handle = None
                raise OSError('无法获取程序实例锁')
            self.primary = result in (0, 0x80)

    def close(self):
        if self.handle:
            if self.primary:
                self.kernel.ReleaseMutex(self.handle)
            self.kernel.CloseHandle(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
