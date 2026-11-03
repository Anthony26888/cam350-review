"""Generate assets/icon.png from assets/icon.ico for Linux packaging."""

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "icon.ico"
TARGET = ROOT / "assets" / "icon.png"
SIZE = 256


def main() -> None:
    image = QImage(str(SOURCE))
    if image.isNull():
        raise SystemExit(f"Cannot read {SOURCE}")
    image = image.convertToFormat(QImage.Format_ARGB32)
    if image.width() != SIZE or image.height() != SIZE:
        image = image.scaled(
            SIZE, SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation
        )
    if not image.save(str(TARGET), "PNG"):
        raise SystemExit(f"Cannot write {TARGET}")
    print(TARGET)


if __name__ == "__main__":
    main()
