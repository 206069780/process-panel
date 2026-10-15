"""Small native startup animation, independent of the embedded web page."""

from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPen
from PySide6.QtWidgets import QPushButton, QWidget


class StartupSplash(QWidget):
    cancelled = Signal()

    def __init__(self):
        super().__init__(None, Qt.WindowType.SplashScreen | Qt.WindowType.FramelessWindowHint)
        self.setWindowTitle('Portside · 正在启动')
        self.setFixedSize(480, 340)
        self.icon = QIcon(str(Path(__file__).resolve().parent.parent / 'static' / 'favicon.svg'))
        self.setWindowIcon(self.icon)
        self.status = '正在启动工作台…'
        self._finished = False
        self.clock = QElapsedTimer()
        self.clock.start()
        self.animation = QTimer(self)
        self.animation.setInterval(25)
        self.animation.timeout.connect(self.update)
        self.cancel_button = QPushButton('×', self)
        self.cancel_button.setGeometry(434, 10, 34, 34)
        self.cancel_button.setAccessibleName('取消启动')
        self.cancel_button.setToolTip('取消启动')
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setStyleSheet('''
            QPushButton { color: #82908f; border: 0; border-radius: 8px;
                          background: transparent; font: 24px "Segoe UI"; }
            QPushButton:hover { color: #f1f5f3; background: #273136; }
            QPushButton:focus { border: 1px solid #82e9b9; }
        ''')
        self.cancel_button.clicked.connect(self.close)

    def showEvent(self, event):
        super().showEvent(event)
        self.animation.start()

    def set_status(self, text):
        self.status = text
        self.update()

    def finish(self):
        self._finished = True
        self.animation.stop()
        self.hide()

    def closeEvent(self, event):
        self.animation.stop()
        super().closeEvent(event)
        if not self._finished:
            self.cancelled.emit()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor('#10171b'))
        painter.setPen(QPen(QColor('#2a393b'), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        painter.setFont(QFont('Microsoft YaHei UI', 10))
        painter.setPen(QColor('#829995'))
        painter.drawText(26, 32, '本机进程工作台')
        ring = QRectF(192, 52, 96, 96)
        painter.setPen(QPen(QColor('#223d34'), 3))
        painter.drawEllipse(ring)
        pen = QPen(QColor('#82e9b9'), 3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        angle = (self.clock.elapsed() * .24) % 360
        painter.drawArc(ring, int(-angle * 16), 100 * 16)
        self.icon.paint(painter, 212, 72, 56, 56)
        painter.setFont(QFont('Segoe UI', 26, QFont.Weight.Bold))
        painter.setPen(QColor('#edf7f1'))
        painter.drawText(QRectF(0, 166, 480, 42), Qt.AlignmentFlag.AlignCenter, 'Portside')
        painter.setFont(QFont('Microsoft YaHei UI', 11))
        painter.setPen(QColor('#9baca9'))
        painter.drawText(QRectF(0, 211, 480, 28), Qt.AlignmentFlag.AlignCenter, '进程与端口，尽在掌握')
        painter.setFont(QFont('Microsoft YaHei UI', 9))
        painter.setPen(QColor('#82e9b9'))
        painter.drawText(QRectF(0, 258, 480, 24), Qt.AlignmentFlag.AlignCenter, self.status)
        track = QRectF(48, 300, 384, 4)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor('#24332f'))
        painter.drawRoundedRect(track, 2, 2)
        painter.setClipRect(track)
        position = (self.clock.elapsed() % 1500) / 1500 * 504 - 120
        gradient = QLinearGradient(48 + position, 0, 168 + position, 0)
        gradient.setColorAt(0, QColor('#24332f'))
        gradient.setColorAt(.5, QColor('#82e9b9'))
        gradient.setColorAt(1, QColor('#24332f'))
        painter.setBrush(gradient)
        painter.drawRoundedRect(QRectF(48 + position, 300, 120, 4), 2, 2)
