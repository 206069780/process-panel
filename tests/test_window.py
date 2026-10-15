"""Exercise the actual desktop rendering and IPC, without launching a browser."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
import psutil

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from panel.server import PanelServer


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def wait_until(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(.02)
        self.fail('Desktop condition timed out')

    def javascript(self, page, source):
        values = []
        page.runJavaScript(source, values.append)
        self.wait_until(lambda: bool(values))
        return values[0]

    def test_startup_animation_changes_frames_and_finishes_immediately(self):
        import importlib.util
        self.assertIsNotNone(importlib.util.find_spec('panel.splash'), 'Native startup animation is missing')
        from panel import splash as startup
        splash = startup.StartupSplash()
        try:
            splash.show()
            self.app.processEvents()
            self.assertTrue(splash.isVisible())
            first = splash.grab().toImage()
            QTest.qWait(180)
            self.assertNotEqual(first, splash.grab().toImage())
            output = Path(__file__).resolve().parent.parent / '.runtime' / 'startup-preview.png'
            self.assertTrue(splash.grab().save(str(output)))
            splash.finish()
            self.assertFalse(splash.isVisible())
            self.assertFalse(splash.animation.isActive())
        finally:
            splash.close()

    def test_startup_cancel_before_initialization_does_not_create_dashboard(self):
        from panel import window
        self.assertTrue(hasattr(window, 'DesktopStartup'), 'Desktop startup handoff is missing')
        from panel.window import DesktopStartup
        startup = DesktopStartup('http://127.0.0.1:1')
        with patch('panel.window.DashboardWindow') as dashboard:
            startup.start()
            QTest.mouseClick(startup.splash.cancel_button, Qt.MouseButton.LeftButton)
            self.app.processEvents()
            self.assertFalse(startup.splash.isVisible())
            self.assertFalse(startup.splash.animation.isActive())
            dashboard.assert_not_called()

    def test_startup_failure_closes_animation_and_preserves_error(self):
        from panel import window
        self.assertTrue(hasattr(window, 'DesktopStartup'), 'Desktop startup handoff is missing')
        from panel.window import DesktopStartup
        startup = DesktopStartup('http://127.0.0.1:1')
        with patch('panel.window.DashboardWindow', side_effect=RuntimeError('initialization failed')):
            startup.start()
            self.wait_until(lambda: startup.error is not None)
            self.assertIsInstance(startup.error, RuntimeError)
            self.assertFalse(startup.splash.isVisible())
            self.assertFalse(startup.splash.animation.isActive())

    def test_page_load_failure_reveals_window_and_closes_animation(self):
        import socket
        from panel.window import DesktopStartup
        with socket.socket() as unused:
            unused.bind(('127.0.0.1', 0))
            origin = f'http://127.0.0.1:{unused.getsockname()[1]}'
            startup = DesktopStartup(origin)
            try:
                with patch('panel.window.QMessageBox.warning') as warning:
                    startup.start()
                    self.wait_until(lambda: warning.called)
                    self.assertTrue(startup.window.isVisible())
                    self.assertFalse(startup.splash.isVisible())
                    self.assertFalse(startup.splash.animation.isActive())
            finally:
                startup.stop()
                if startup.window:
                    startup.window.dispose()

    def test_real_dashboard_renders_restores_and_accepts_activation(self):
        from panel.window import DesktopStartup, DesktopChannel
        server = PanelServer()
        server.monitor.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        startup = DesktopStartup(server.origin)
        channel = DesktopChannel(f'Portside-test-{os.getpid()}', startup.bring_to_front)
        window = None
        try:
            startup.start()
            self.assertTrue(startup.splash.isVisible())
            self.wait_until(lambda: startup.window is not None)
            window = startup.window
            self.wait_until(lambda: self.javascript(window.view.page(),
                "document.querySelector('#connection-text')?.textContent") == '实时连接')
            self.assertTrue(window.isVisible())
            self.assertFalse(startup.splash.isVisible())
            self.assertFalse(startup.splash.animation.isActive())
            self.assertFalse(window.escape_action.isEnabled())
            window._toggle_fullscreen()
            self.assertTrue(window.isFullScreen())
            self.assertTrue(window.escape_action.isEnabled())
            window._exit_fullscreen()
            self.assertFalse(window.isFullScreen())
            self.assertFalse(window.escape_action.isEnabled())
            self.assertFalse(window.view.page().acceptNavigationRequest(
                __import__('PySide6.QtCore', fromlist=['QUrl']).QUrl('https://example.com'),
                window.view.page().NavigationType.NavigationTypeLinkClicked, True))
            self.assertEqual(self.javascript(window.view.page(), "document.title"), 'Portside · 本机进程控制台')
            self.assertTrue(self.javascript(window.view.page(),
                "document.querySelectorAll('#table-body tr').length > 0"))
            self.javascript(window.view.page(), "document.querySelector('#table-body [data-action=detail]').click(); true")
            self.wait_until(lambda: self.javascript(window.view.page(),
                "!!document.querySelector('#detail-content .detail-grid')"))
            window.activateWindow()
            window.view.setFocus()
            rect = json.loads(self.javascript(window.view.page(),
                "JSON.stringify(document.querySelector('#copy-detail').getBoundingClientRect().toJSON())"))
            QTest.mouseClick(window.view.focusProxy(), Qt.MouseButton.LeftButton,
                             pos=QPoint(int(rect['x'] + rect['width']/2), int(rect['y'] + rect['height']/2)))
            self.wait_until(lambda: QApplication.clipboard().text().startswith('进程：'))
            self.javascript(window.view.page(), "document.querySelector('#detail-dialog').close(); true")
            from panel.processes import protection_reason
            renderers = [p for p in psutil.Process().children(recursive=True)
                         if p.name().lower() == 'qtwebengineprocess.exe']
            self.assertTrue(renderers, 'Embedded desktop renderer did not start')
            for renderer in renderers:
                self.assertIsNotNone(protection_reason(renderer.pid, renderer.name()))
            window.showMinimized()
            self.app.processEvents()
            script = ('from panel.window import activate_existing; '
                      f'raise SystemExit(0 if activate_existing({channel.name!r}, timeout=5) else 1)')
            duplicate = subprocess.Popen([str(Path(sys.executable)), '-c', script],
                                         creationflags=subprocess.CREATE_NO_WINDOW)
            self.wait_until(lambda: duplicate.poll() is not None)
            self.assertEqual(duplicate.returncode, 0)
            self.assertFalse(window.isMinimized())
            self.assertTrue(window.isVisible())
            self.javascript(window.view.page(), "document.querySelector('#search').value=':65534'; document.querySelector('#search').dispatchEvent(new Event('input')); true")
            self.assertIn('65534', self.javascript(window.view.page(), "document.querySelector('#search').value"))
            self.javascript(window.view.page(), "document.querySelector('#search').value=''; document.querySelector('#search').dispatchEvent(new Event('input')); true")
            output = Path(__file__).resolve().parent.parent / '.runtime' / 'desktop-preview.png'
            output.parent.mkdir(exist_ok=True)
            self.assertTrue(window.grab().save(str(output)))
        finally:
            channel.close()
            startup.stop()
            if window:
                window.dispose()
            self.app.processEvents()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            server.monitor.close()


if __name__ == '__main__':
    unittest.main()
