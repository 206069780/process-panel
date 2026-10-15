"""Embedded dashboard, loaded only after the startup window is painted."""

from pathlib import Path
from PySide6.QtCore import QEvent, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QIcon, QKeySequence
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
    loaded = Signal(bool)
    closed = Signal()

    def __init__(self, origin):
        super().__init__()
        self._closing = False
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
        if self._closing:
            return
        self.loaded.emit(ok)
        if not ok:
            QMessageBox.warning(self, 'Portside', '面板加载失败，请关闭程序后重新打开。')

    def closeEvent(self, event):
        self._closing = True
        super().closeEvent(event)
        self.closed.emit()

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
        # Python signal cycles can be collected on a worker. Destroy Qt objects
        # on the GUI thread, after the page and before any background collection.
        self.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
