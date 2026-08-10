import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget

from license.gate import license_gate
from ui.main_window import MainWindow
from ui.style import APP_STYLE, QSS_LIGHT
from utils.dwm_theme import set_titlebar_theme


class TitleBarThemeFilter(QObject):
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Show and isinstance(obj, QWidget) and obj.isWindow():
            hwnd = int(obj.winId())
            QTimer.singleShot(0, lambda hwnd=hwnd: set_titlebar_theme(hwnd))
        return super().eventFilter(obj, event)


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("CAM350 Review Assistant")
    app.setOrganizationName("CAM350Review")
    app.setStyle(APP_STYLE)
    app.setStyleSheet(QSS_LIGHT)
    _title_theme_filter = TitleBarThemeFilter(app)
    app.installEventFilter(_title_theme_filter)

    if not license_gate():
        return

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
