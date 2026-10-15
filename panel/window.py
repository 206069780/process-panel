"""Standalone desktop shell. No external browser or WebView2 installation."""

import ctypes
import os
import sys
import threading
import time

from PySide6.QtCore import QObject, Qt, QTimer
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from panel.splash import StartupSplash

# Required before QApplication when importing WebEngine after its creation.
if QApplication.instance() is None:
    QApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)


def create_dashboard(origin):
    from panel.web_window import DashboardWindow
    return DashboardWindow(origin)


class DesktopStartup(QObject):
    """Own the splash-to-dashboard handoff and cancellation on the GUI thread."""

    def __init__(self, origin):
        super().__init__()
        self.origin = origin
        self.window = None
        self.error = None
        self.stopped = False
        self.splash = StartupSplash()
        self.splash.cancelled.connect(self.stop)
        self.initialize = QTimer(self)
        self.initialize.setSingleShot(True)
        self.initialize.timeout.connect(self._initialize)

    def start(self):
        self.splash.show()
        # Paint feedback before synchronous WebEngine construction begins.
        self.splash.repaint()
        self.initialize.start(0)

    def _initialize(self):
        if self.stopped:
            return
        try:
            self.window = create_dashboard(self.origin)
            self.window.loaded.connect(self._reveal)
            self.window.closed.connect(self.stop)
            self.splash.set_status('正在加载进程与端口面板…')
        except Exception as error:
            self.error = error
            self.stop()

    def _reveal(self, ok):
        if not self.stopped:
            self.window.show()
            self.splash.finish()

    def bring_to_front(self):
        if self.stopped:
            return
        if self.window and self.window.isVisible():
            self.window.bring_to_front()
        else:
            self.splash.show()
            self.splash.raise_()
            self.splash.activateWindow()

    def stop(self):
        if self.stopped:
            return
        self.stopped = True
        self.initialize.stop()
        self.splash.finish()
        if self.window:
            self.window.close()
        QApplication.instance().quit()


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
    startup = DesktopStartup(server.origin)
    channel = DesktopChannel(name, startup.bring_to_front)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .2},
                              daemon=True, name='panel-http')
    thread.start()
    try:
        startup.start()
        result = app.exec()
        if startup.error:
            raise startup.error
        return result
    finally:
        channel.close()
        startup.stop()
        if startup.window:
            startup.window.dispose()
        server.shutdown()
        thread.join(timeout=5)
