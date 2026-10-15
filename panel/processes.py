"""Process identities and guarded termination, independent of the HTTP layer."""

import math
import os

import psutil


class PanelError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


_PROTECTED_PIDS = {0, 4, os.getpid()}
_PROTECTED_PIDS.update(p.pid for p in psutil.Process().parents())
_CRITICAL_NAMES = {
    'system', 'registry', 'secure system', 'memory compression', 'smss.exe',
    'csrss.exe', 'wininit.exe', 'winlogon.exe', 'lsass.exe', 'services.exe',
    'svchost.exe', 'lsaiso.exe',
}


def protection_reason(pid, name):
    if pid in _PROTECTED_PIDS:
        return '系统进程、面板自身或面板的启动进程受到保护'
    if name.lower() in _CRITICAL_NAMES:
        return 'Windows 关键系统进程受到保护'
    if name.lower() == 'qtwebengineprocess.exe':
        try:
            if any(parent.pid == os.getpid() for parent in psutil.Process(pid).parents()):
                return '面板的桌面渲染进程受到保护'
        except psutil.Error:
            pass
    return None


def _read(process, field):
    try:
        return getattr(process, field)()
    except (psutil.AccessDenied, psutil.ZombieProcess):
        return None


def process_detail(pid):
    try:
        process = psutil.Process(pid)
        with process.oneshot():
            name = process.name()
            memory = _read(process, 'memory_info')
            return {
                'pid': pid, 'name': name, 'create_time': process.create_time(),
                'exe': _read(process, 'exe'), 'username': _read(process, 'username'),
                'cmdline': _read(process, 'cmdline'), 'status': _read(process, 'status'),
                'memory': memory.rss if memory else None,
                'protected_reason': protection_reason(pid, name),
            }
    except psutil.NoSuchProcess:
        raise PanelError(404, '进程已退出，请刷新列表') from None
    except psutil.AccessDenied:
        raise PanelError(403, '没有权限读取此进程，可尝试以管理员身份启动面板') from None


def _terminate_windows(pid, created):
    # Keep a single Windows handle from identity check to termination. A PID
    # reused between lookups must never cause a different process to be killed.
    import ctypes
    from ctypes import wintypes

    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetProcessTimes.restype = wintypes.BOOL
    kernel.IsProcessCritical.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
    kernel.IsProcessCritical.restype = wintypes.BOOL
    kernel.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    kernel.TerminateProcess.restype = wintypes.BOOL
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.WaitForSingleObject.restype = wintypes.DWORD
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.CloseHandle.restype = wintypes.BOOL
    handle = kernel.OpenProcess(0x1000 | 0x0001 | 0x100000, False, pid)
    if not handle:
        if ctypes.get_last_error() == 87:
            raise PanelError(404, '进程已退出，请刷新列表')
        raise PanelError(403, '没有权限结束此进程，可尝试以管理员身份启动面板')
    try:
        times = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)):
            raise PanelError(403, '无法验证进程身份，操作已取消')
        ticks = (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime
        actual_created = ticks / 10_000_000 - 11_644_473_600
        if abs(actual_created - created) > 0.001:
            raise PanelError(409, '进程身份已变化，请刷新后重新选择')
        critical = wintypes.BOOL()
        if not kernel.IsProcessCritical(handle, ctypes.byref(critical)):
            raise PanelError(403, '无法确认进程保护状态，操作已取消')
        if critical.value:
            raise PanelError(403, 'Windows 关键系统进程受到保护')
        if not kernel.TerminateProcess(handle, 1):
            raise PanelError(403, '无法结束此进程，可能需要管理员权限')
        return kernel.WaitForSingleObject(handle, 3000) == 0
    finally:
        kernel.CloseHandle(handle)


def terminate_process(pid, create_time):
    if type(pid) is not int or pid < 0:
        raise PanelError(400, 'PID 必须是非负整数')
    if pid in _PROTECTED_PIDS:
        raise PanelError(403, '系统进程、面板自身或面板的启动进程受到保护')
    if type(create_time) not in (int, float) or not math.isfinite(create_time) or create_time <= 0:
        raise PanelError(400, '缺少有效的进程启动时间，请刷新后重试')
    try:
        process = psutil.Process(pid)
        if abs(process.create_time() - create_time) > 0.001:
            raise PanelError(409, '进程身份已变化，请刷新后重新选择')
        name = process.name()
        reason = protection_reason(pid, name)
        if reason:
            raise PanelError(403, reason)
        if os.name == 'nt':
            ended = _terminate_windows(pid, create_time)
        else:
            process.terminate()
            try:
                process.wait(timeout=3)
                ended = True
            except psutil.TimeoutExpired:
                ended = False
        return {'pid': pid, 'name': name, 'terminated': ended,
                'message': '进程已结束，端口列表已更新' if ended else '已发送结束请求，进程正在退出'}
    except psutil.NoSuchProcess:
        raise PanelError(404, '进程已退出，请刷新列表') from None
    except psutil.AccessDenied:
        raise PanelError(403, '没有权限结束此进程，可尝试以管理员身份启动面板') from None
