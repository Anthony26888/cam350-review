import os
from typing import Dict, List, Tuple

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QFormLayout, QWidget,
)

from ui.i18n import tr
from ui.style import err_color, muted_color, txt_color

_FILTERS = {
    "gerberGko": ("Select GKO file", "Gerber Files (*.gko *.GKO *.gbr *.GBR);;All Files (*.*)"),
    "gerberGtp": ("Select GTP file", "Gerber Files (*.gtp *.GTP *.gpt *.GPT *.gbr *.GBR);;All Files (*.*)"),
    "gerberGbp": ("Select GBP file", "Gerber Files (*.gbp *.GBP *.gpb *.GPB *.gbr *.GBR);;All Files (*.*)"),
    "gerberGto": ("Select GTO file", "Gerber Files (*.gto *.GTO *.gbr *.GBR);;All Files (*.*)"),
    "gerberGbo": ("Select GBO file", "Gerber Files (*.gbo *.GBO *.gbr *.GBR);;All Files (*.*)"),
}

_LABELS: List[Tuple[str, str]] = [
    ("gerberGko", "GKO (Outline) *:"),
    ("gerberGtp", "GTP (Top Paste):"),
    ("gerberGbp", "GBP (Bottom Paste):"),
    ("gerberGto", "GTO (Top Overlay / Silkscreen):"),
    ("gerberGbo", "GBO (Bottom Overlay / Silkscreen):"),
]


class GerberFileDialog(QDialog):
    """Let the user review/change the Gerber files used by Gerber View."""

    def __init__(self, paths: Dict[str, str], config_mgr=None, parent=None) -> None:
        super().__init__(parent)
        self._config_mgr = config_mgr
        self._paths: Dict[str, str] = {}
        self._labels: Dict[str, QLabel] = {}

        self.setWindowTitle(tr("Select Gerber Files"))
        layout = QVBoxLayout(self)

        form = QFormLayout()
        for key, label in _LABELS:
            row = QHBoxLayout()
            lbl = QLabel()
            row.addWidget(lbl, 1)
            btn = QPushButton(tr("Browse..."))
            btn.clicked.connect(lambda _=False, k=key: self._browse(k))
            row.addWidget(btn)
            form.addRow(tr(label), row)
            self._labels[key] = lbl
        layout.addLayout(form)

        info = QLabel(
            tr("* GKO is required (Gerber Outline).\n"
               "GTP/GBP help detect offsets more accurately (recommended).\n"
               "GTO/GBO (names/designators on the board) are only used for display in Gerber View.")
        )
        info.setStyleSheet(f"color: {muted_color()}; font-style: italic; margin-top: 8px;")
        layout.addWidget(info)

        btn_layout = QHBoxLayout()
        self._btn_next = QPushButton(tr("Next ▶"))
        self._btn_next.clicked.connect(self._on_next)
        btn_cancel = QPushButton(tr("Cancel"))
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_next)
        btn_layout.addWidget(btn_cancel)
        layout.addLayout(btn_layout)

        for key, path in (paths or {}).items():
            if key in self._labels and path and os.path.exists(path):
                self._paths[key] = path
        self._sync_labels()

    def _browse(self, key: str) -> None:
        title, file_filter = _FILTERS[key]
        path, _ = QFileDialog.getOpenFileName(self, tr(title), "", file_filter)
        if path:
            self._paths[key] = path
            if self._config_mgr is not None:
                self._config_mgr.update(**{key: path})
            self._sync_labels()

    def _sync_labels(self) -> None:
        for key, label in self._labels.items():
            path = self._paths.get(key)
            if path:
                label.setText(os.path.basename(path))
                label.setStyleSheet(f"color: {txt_color()};")
                label.setToolTip(path)
            else:
                label.setText(tr("(not selected)"))
                label.setStyleSheet(f"color: {err_color()}; font-weight: bold;")

    def _on_next(self) -> None:
        if not self._paths.get("gerberGko"):
            QMessageBox.warning(self, tr("Warning"), tr("Please select the GKO (Outline) file."))
            return
        self.accept()

    def selected_paths(self) -> Dict[str, str]:
        return {k: v for k, v in self._paths.items() if v and os.path.exists(v)}
