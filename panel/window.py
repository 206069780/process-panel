"""Standalone desktop shell. No external browser or WebView2 installation."""

import ctypes
import os
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QEvent, Qt, QUrl, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication, QMainWindow, QMessageBox
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView


class LocalPage(QWebEnginePage):
    def __init__(self, profile, origin, parent):
        super().__init__(profile, parent)
        self.origin = QUrl(origin)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        return (url.scheme(), url.host(), url.port()) == (
            self.origin.scheme(), self.origin.host(), self.origin.port())

    def createWindow(self, window_type):
        return None


class DashboardWindow(QMainWindow):
    def __init__(self, origin):
        super().__init__()
        self.setWindowTitle('Portside · 进程与端口工作台')
        self.setWindowIcon(QIcon(str(Path(__file__).resolve().parent.parent / 'static' / 'favicon.svg')))
        self.resize(1480, 960)
        self.setMinimumSize(900, 650)
        self.view = QWebEngineView(self)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        # An unnamed profile is memory-only; process information is not cached to disk.
        self.profile = QWebEngineProfile(self)
        self.page = LocalPage(self.profile, origin, self.view)
        self.view.setPage(self.page)
        self.setCentralWidget(self.view)
        self.page.setBackgroundColor('#101318')
        settings = self.page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanOpenWindows, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.JavascriptCanAccessClipboard, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        settings.setAttribute(QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True)
        self.page.fullScreenRequested.connect(self._fullscreen)
        self.view.loadFinished.connect(self._loaded)
        shortcut = QAction(self)
        shortcut.setShortcut(QKeySequence('F11'))
        shortcut.triggered.connect(self._toggle_fullscreen)
        self.addAction(shortcut)
        self.escape_action = QAction(self)
        self.escape_action.setShortcut(QKeySequence('Esc'))
        self.escape_action.setEnabled(False)
        self.escape_action.triggered.connect(self._exit_fullscreen)
        self.addAction(self.escape_action)
        self.view.load(QUrl(origin))

    def _loaded(self, ok):
        if not ok:
            QMessageBox.warning(self, 'Portside', '面板加载失败，请关闭程序后重新打开。')

    def bring_to_front(self):
        if self.isMinimized():
            self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.show()
        self.raise_()
        self.activateWindow()

    def _fullscreen(self, request):
        request.accept()
        self.showFullScreen() if request.toggleOn() else self.showNormal()
        self.escape_action.setEnabled(request.toggleOn())

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self._exit_fullscreen()
        else:
            self.showFullScreen()
            self.escape_action.setEnabled(True)

    def _exit_fullscreen(self):
        if self.isFullScreen():
            self.page.runJavaScript('if (document.fullscreenElement) document.exitFullscreen()')
            self.showNormal()
            self.escape_action.setEnabled(False)

    def dispose(self):
        # Delete the page before its profile (Qt requires this destruction order).
        self.page.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


class DesktopChannel:
    """Only the mutex owner may remove a stale IPC endpoint and listen."""

    def __init__(self, name, activate):
        self.name = name
        self.activate = activate
        self.server = QLocalServer()
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.sockets = set()
        QLocalServer.removeServer(name)
        if not self.server.listen(name):
            raise RuntimeError('无法创建桌面窗口通信通道：' + self.server.errorString())
        self.server.newConnection.connect(self._connected)

    def _connected(self):
        while self.server.hasPendingConnections():
            socket = self.server.nextPendingConnection()
            self.sockets.add(socket)
            buffer = bytearray()

            def receive(current=socket, data=buffer):
                data.extend(bytes(current.readAll()))
                if len(data) > 64:
                    current.abort()
                elif bytes(data) == b'activate\n':
                    self.activate()
                    current.write(b'ok\n')
                    current.flush()
                    current.disconnectFromServer()

            socket.readyRead.connect(receive)
            socket.disconnected.connect(lambda current=socket: self._disconnected(current))
            socket.write(f'{os.getpid()}\n'.encode())
            socket.flush()
            QTimer.singleShot(5000, socket, socket.abort)
            if socket.bytesAvailable():
                receive()

    def _disconnected(self, socket):
        self.sockets.discard(socket)
        socket.deleteLater()

    def close(self):
        for socket in tuple(self.sockets):
            socket.abort()
        self.server.close()


def activate_existing(name, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(name)
        if socket.waitForConnected(200):
            if not socket.bytesAvailable():
                socket.waitForReadyRead(2000)
            pid = bytes(socket.readAll()).strip()
            if pid.isdigit() and os.name == 'nt':
                ctypes.windll.user32.AllowSetForegroundWindow(int(pid))
            socket.write(b'activate\n')
            socket.waitForBytesWritten(2000)
            if not socket.bytesAvailable():
                socket.waitForReadyRead(3000)
            acknowledged = bytes(socket.readAll()).strip() == b'ok'
            socket.abort()
            if acknowledged:
                return True
        socket.abort()
        time.sleep(.1)
    return False


def run_desktop(server, name):
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName('Portside')
    app.setOrganizationName('Portside')
    app.setQuitOnLastWindowClosed(True)
    window = DashboardWindow(server.origin)
    channel = DesktopChannel(name, window.bring_to_front)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .2},
                              daemon=True, name='panel-http')
    thread.start()
    try:
        window.show()
        return app.exec()
    finally:
        channel.close()
        window.close()
        window.dispose()
        server.shutdown()
        thread.join(timeout=5)
