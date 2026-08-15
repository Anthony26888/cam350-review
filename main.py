import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QEvent, QObject, QTimer
from PySide6.QtWidgets import QWidget

from license.gate import license_gate
from config.config_manager import ConfigManager
from ui.main_window import MainWindow
from ui.i18n import set_language
from ui.style import APP_STYLE, apply_theme
from utils.dwm_theme import set_titlebar_theme
from utils.version import APP_MUTEX


def _acquire_single_instance() -> bool:
    try:
        import win32api
        import win32event
        import winerror
    except ImportError:
        return True
    global _app_mutex
    _app_mutex = win32event.CreateMutex(None, False, APP_MUTEX)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        return False
    return True


_app_mutex = None


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

    if not _acquire_single_instance():
        return

    _config_mgr = ConfigManager.instance()
    set_language(_config_mgr.config.language)
    apply_theme(app, _config_mgr.config.theme)
    _title_theme_filter = TitleBarThemeFilter(app)
    app.installEventFilter(_title_theme_filter)

    if not license_gate():
        return

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
