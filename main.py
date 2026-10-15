"""Run the standalone desktop dashboard: python main.py [--port 8765]."""

import argparse
import ctypes
from pathlib import Path
import sys

from panel.desktop import InstanceLock, RuntimeRegistry, is_admin
from panel.server import PanelServer


def main():
    parser = argparse.ArgumentParser(description='本机进程与端口控制面板')
    parser.add_argument('--port', type=int, default=8765, help='本机端口；占用时自动选空闲端口')
    # Accept legacy flags; desktop mode never opens an external browser.
    parser.add_argument('--no-browser', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--no-tray', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--runtime-dir', type=Path, help='运行状态目录，用于隔离自动化检查')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('端口必须在 0 到 65535 之间')
    registry = RuntimeRegistry(args.runtime_dir)
    admin = is_admin()
    lock = InstanceLock(admin, registry.root)
    server = None
    try:
        if not lock.primary:
            from panel.window import activate_existing
            if activate_existing(lock.name):
                return
            # Retry ownership: the previous process may have exited during startup.
            lock.close()
            lock = InstanceLock(admin, registry.root)
            if not lock.primary:
                raise RuntimeError('已有窗口暂时无法响应，请稍后重试')
        try:
            server = PanelServer(port=args.port)
        except OSError:
            server = PanelServer(port=0)
        server.monitor.start()
        registry.register(server.origin, admin)
        if sys.stdout:
            print(f'Process Panel: {server.origin}', flush=True)
        from panel.window import run_desktop
        run_desktop(server, lock.name)
    except KeyboardInterrupt:
        pass
    finally:
        if server:
            server.server_close()
            server.monitor.close()
            registry.unregister()
        lock.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if getattr(sys, 'frozen', False):
            ctypes.windll.user32.MessageBoxW(None, f'启动失败：{error}', 'Portside', 0x10)
        else:
            raise
