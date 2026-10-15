"""Win32 assertions for the real distributed desktop window."""

import ctypes
from ctypes import wintypes
import time


user32 = ctypes.WinDLL('user32', use_last_error=True)
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.EnumChildWindows.argtypes = [wintypes.HWND, callback_type, wintypes.LPARAM]
user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]


def window_for_pid(pid):
    found = []

    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value.startswith('Portside · 进程与端口工作台'):
                found.append(hwnd)
        return True

    user32.EnumWindows(inspect, 0)
    return found[0] if found else None


def startup_error(pid):
    messages = []

    @callback_type
    def inspect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            title = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, title, len(title))
            if title.value == 'Portside':
                @callback_type
                def child(control, _):
                    text = ctypes.create_unicode_buffer(4096)
                    user32.GetWindowTextW(control, text, len(text))
                    if text.value.startswith('启动失败：'):
                        messages.append(text.value)
                    return True
                user32.EnumChildWindows(hwnd, child, 0)
        return True

    user32.EnumWindows(inspect, 0)
    return '\n'.join(messages)


def wait_until(predicate, message, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.1)
    raise AssertionError(message)


def minimize(hwnd):
    user32.ShowWindow(hwnd, 6)
    wait_until(lambda: user32.IsIconic(hwnd), 'Window did not minimize')


def close(hwnd):
    assert user32.PostMessageW(hwnd, 0x0010, 0, 0), 'WM_CLOSE failed'


def screenshot(hwnd, path):
    from PIL import ImageGrab
    ImageGrab.grab(window=hwnd).save(path)
