"""Exercise the actual desktop rendering and IPC, without launching a browser."""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import unittest
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

    def test_real_dashboard_renders_restores_and_accepts_activation(self):
        from panel.window import DashboardWindow, DesktopChannel
        server = PanelServer()
        server.monitor.start()
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        window = DashboardWindow(server.origin)
        channel = DesktopChannel(f'Portside-test-{os.getpid()}', window.bring_to_front)
        try:
            window.show()
            self.wait_until(lambda: self.javascript(window.view.page(),
                "document.querySelector('#connection-text')?.textContent") == '实时连接')
            self.assertTrue(window.isVisible())
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
            window.close()
            window.dispose()
            self.app.processEvents()
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()
            server.monitor.close()


if __name__ == '__main__':
    unittest.main()
