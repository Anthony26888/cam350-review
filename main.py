import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from license.gate import license_gate
from ui.main_window import MainWindow
from ui.style import APP_STYLE, QSS_LIGHT


def main() -> None:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("CAM350 Review Assistant")
    app.setOrganizationName("CAM350Review")
    app.setStyle(APP_STYLE)
    app.setStyleSheet(QSS_LIGHT)

    if not license_gate():
        return

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
