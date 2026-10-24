"""Let the user choose the folder that holds the Gerber files.

A CAM job puts the layers of a board in one folder.  The dialog looks at
the folder, finds the files that hold artwork and shows them as the
layers of the picture, the way the reference viewer does.  The user can
take a layer away, add a file that was not found, and choose the files
that are not in the folder.
"""

import os
from typing import Dict, List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView, QDialog, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from services.gerber.layer_scan import LayerInfo, layer_from_file, scan_folder
from ui.i18n import tr
from ui.style import muted_color

#: The columns of the table of the layers.
_COL_NAME = 0
_COL_FILE = 1
_COL_ROLE = 2
_COL_SIDE = 3

_ROLE_TEXT = {
    "profile": "outline",
    "copper": "copper",
    "mask": "mask",
    "paste": "paste",
    "silk": "silk",
    "drill": "drill",
    "other": "other",
}


class GerberFileDialog(QDialog):
    """Let the user pick the folder and the layers of the Gerber picture."""

    def __init__(self, folder: str = "", layers: Optional[List[LayerInfo]] = None,
                 config_mgr=None, parent=None) -> None:
        super().__init__(parent)
        self._config_mgr = config_mgr
        self._folder = folder or ""
        self._layers: List[LayerInfo] = list(layers or [])
        self._manual: List[LayerInfo] = []

        self.setWindowTitle(tr("Select Gerber Files"))
        self.resize(760, 460)
        layout = QVBoxLayout(self)

        # --- the folder ---
        folder_row = QHBoxLayout()
        folder_row.addWidget(QLabel(tr("Folder:")))
        self._edit_folder = QWidget()
        from PySide6.QtWidgets import QLineEdit
        self._line_folder = QLineEdit(self._folder)
        self._line_folder.setReadOnly(True)
        folder_row.addWidget(self._line_folder, 1)
        btn_browse = QPushButton(tr("Browse..."))
        btn_browse.clicked.connect(self._browse)
        folder_row.addWidget(btn_browse)
        btn_scan = QPushButton(tr("Rescan"))
        btn_scan.clicked.connect(self._rescan)
        folder_row.addWidget(btn_scan)
        layout.addLayout(folder_row)

        # --- the layers ---
        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [tr("Layer"), tr("File"), tr("Type"), tr("Side")])
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_FILE, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table, 1)

        # --- the buttons of the list ---
        list_row = QHBoxLayout()
        self._lbl_info = QLabel()
        self._lbl_info.setStyleSheet(f"color: {muted_color()};")
        list_row.addWidget(self._lbl_info, 1)
        btn_add = QPushButton(tr("Add file..."))
        btn_add.clicked.connect(self._add_file)
        list_row.addWidget(btn_add)
        btn_remove = QPushButton(tr("Remove"))
        btn_remove.clicked.connect(self._remove_layer)
        list_row.addWidget(btn_remove)
        layout.addLayout(list_row)

        info = QLabel(
            tr("Every file of the folder that holds artwork becomes a layer.\n"
               "The name of a layer is taken from the attributes of the file when "
               "it has them, and from the name of the file when it has not.")
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

        if not self._layers and self._folder:
            self._rescan()
        else:
            self._sync_table()

    # ------------------------------------------------------------------
    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(
            self, tr("Select the folder of the Gerber files"), self._folder)
        if folder:
            self._folder = folder
            self._rescan()

    def _rescan(self) -> None:
        """Look at the folder again and fill the table."""
        self._folder = self._line_folder.text().strip() or self._folder
        self._layers = scan_folder(self._folder)
        self._manual = []
        self._sync_table()
        if self._config_mgr is not None and self._folder:
            self._config_mgr.update(gerberFolder=self._folder)

    def _add_file(self) -> None:
        """Add a file that was not found in the folder."""
        path, _selected = QFileDialog.getOpenFileName(
            self, tr("Add a Gerber file"), self._folder,
            tr("Gerber and drill files (*.gbr *.GBR *.gko *.GKO *.gtp *.GTP "
               "*.gbp *.GBP *.gto *.GTO *.gbo *.GBO *.gts *.GTS *.gbs *.GBS "
               "*.gtl *.GTL *.gbl *.GBL *.drl *.DRL *.xln *.XLN *.txt *.TXT);;"
               "All Files (*.*)"))
        if not path:
            return
        layer = layer_from_file(path)
        if layer is None:
            QMessageBox.warning(self, tr("Warning"),
                                tr("This file holds no artwork."))
            return
        self._manual.append(layer)
        self._layers.append(layer)
        self._sync_table()

    def _remove_layer(self) -> None:
        """Take the selected layer away."""
        row = self._table.currentRow()
        if row < 0 or row >= len(self._layers):
            return
        layer = self._layers.pop(row)
        if layer in self._manual:
            self._manual.remove(layer)
        self._sync_table()

    # ------------------------------------------------------------------
    def _sync_table(self) -> None:
        """Fill the table with the layers."""
        self._table.setRowCount(len(self._layers))
        for row, layer in enumerate(self._layers):
            name = QTableWidgetItem(layer.name)
            name.setToolTip(layer.path)
            self._table.setItem(row, _COL_NAME, name)
            file_item = QTableWidgetItem(layer.file_name)
            file_item.setToolTip(layer.path)
            self._table.setItem(row, _COL_FILE, file_item)
            role = QTableWidgetItem(
                tr(_ROLE_TEXT.get(layer.role, layer.role)))
            self._table.setItem(row, _COL_ROLE, role)
            side = QTableWidgetItem(layer.side)
            self._table.setItem(row, _COL_SIDE, side)
        count = len(self._layers)
        self._lbl_info.setText(tr("{n} files found · {m} layers",
                                  n=count, m=count))
        self._btn_next.setEnabled(count > 0)

    def _on_next(self) -> None:
        if not self._layers:
            QMessageBox.warning(
                self, tr("Warning"),
                tr("No file of this folder holds artwork. Choose another folder."))
            return
        self.accept()

    # ------------------------------------------------------------------
    def selected_folder(self) -> str:
        """The folder the user chose."""
        return self._folder

    def selected_layers(self) -> List[LayerInfo]:
        """The layers the user kept."""
        return list(self._layers)
