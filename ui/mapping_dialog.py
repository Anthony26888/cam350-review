from typing import List, Dict, Optional

import openpyxl
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QComboBox, QCheckBox, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QDialogButtonBox, QInputDialog, QMessageBox,
    QHeaderView,
)
from PySide6.QtCore import Qt

from config.config_manager import ConfigManager
from models.pickplace import COLUMN_FIELDS
from services.pickplace_reader import guess_mapping, MIN_REQUIRED
from ui.i18n import tr

_FIELD_LABELS = {
    "designator": "Designator",
    "mpn": "MPN",
    "layer": "Layer",
    "x": "X",
    "y": "Y",
    "rotation": "Rotation",
}

_NONE_ITEM = "—"


class ColumnMappingDialog(QDialog):
    def __init__(
        self,
        file_path: str,
        headers: List[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._headers = list(dict.fromkeys([h for h in headers if h]))
        self._config_mgr = ConfigManager.instance()
        self._combos: Dict[str, QComboBox] = {}
        self._optional_required: Dict[str, QCheckBox] = {}

        self.setWindowTitle(tr("Column Mapping"))
        self.setModal(True)
        self.setMinimumWidth(620)
        self._build_ui()
        self._load_profile_presets()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel(tr("Profile:")))
        self._profile_combo = QComboBox()
        self._profile_combo.setMinimumWidth(180)
        self._profile_combo.currentIndexChanged.connect(self._on_profile_selected)
        profile_row.addWidget(self._profile_combo, 1)
        self._btn_load = QPushButton(tr("Load"))
        self._btn_load.clicked.connect(self._on_load_profile)
        self._btn_save = QPushButton(tr("Save Profile"))
        self._btn_save.clicked.connect(self._on_save_profile)
        profile_row.addWidget(self._btn_load)
        profile_row.addWidget(self._btn_save)
        layout.addLayout(profile_row)

        group = QGroupBox(tr("Map source columns to fields"))
        form = QFormLayout(group)
        for field in COLUMN_FIELDS:
            combo = QComboBox()
            combo.addItem(_NONE_ITEM)
            combo.addItems(self._headers)
            self._combos[field] = combo

            row_widget = QWidget()
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(combo, 1)
            if field not in MIN_REQUIRED:
                chk = QCheckBox(tr("Required"))
                row_layout.addWidget(chk)
                self._optional_required[field] = chk
            else:
                label = QLabel(tr("Required"))
                label.setStyleSheet("color: #888;")
                row_layout.addWidget(label)

            form.addRow(tr(_FIELD_LABELS[field]), row_widget)
        layout.addWidget(group)

        auto_row = QHBoxLayout()
        self._btn_guess = QPushButton(tr("Auto-guess"))
        self._btn_guess.clicked.connect(self._on_guess)
        auto_row.addWidget(self._btn_guess)
        auto_row.addStretch(1)
        layout.addLayout(auto_row)

        preview_label = QLabel(tr("Preview:"))
        layout.addWidget(preview_label)

        self._preview = QTableWidget()
        self._preview.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview.setSelectionMode(QTableWidget.NoSelection)
        self._preview.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._preview.verticalHeader().setVisible(False)
        layout.addWidget(self._preview, 1)
        self._load_preview()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_preview(self) -> None:
        try:
            workbook = openpyxl.load_workbook(
                self._file_path, read_only=True, data_only=True
            )
        except Exception:
            return
        try:
            sheet = workbook.active
            rows: List[List[str]] = []
            for i, row in enumerate(sheet.iter_rows(max_row=11, values_only=True)):
                rows.append(["" if v is None else str(v) for v in row])
        finally:
            workbook.close()

        if not rows:
            return
        self._preview.setColumnCount(len(rows[0]))
        self._preview.setHorizontalHeaderLabels(rows[0])
        self._preview.setRowCount(len(rows) - 1)
        for r in range(1, len(rows)):
            for c in range(len(rows[r])):
                item = QTableWidgetItem(rows[r][c])
                item.setTextAlignment(Qt.AlignCenter)
                self._preview.setItem(r - 1, c, item)

    def _load_profile_presets(self) -> None:
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItem(_NONE_ITEM)
        profiles = self._config_mgr.config.columnProfiles
        for name in profiles:
            self._profile_combo.addItem(name)
        self._profile_combo.blockSignals(False)

    def _on_profile_selected(self) -> None:
        name = self._profile_combo.currentText()
        if not name or name == _NONE_ITEM:
            return
        profiles = self._config_mgr.config.columnProfiles
        mapping = profiles.get(name)
        if mapping:
            self._apply_mapping(mapping)

    def _on_load_profile(self) -> None:
        self._on_profile_selected()

    def _on_save_profile(self) -> None:
        mapping = self._current_mapping()
        name, ok = QInputDialog.getText(
            self, tr("Save Profile"), tr("Profile name:"), text=self._profile_combo.currentText()
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        profiles = dict(self._config_mgr.config.columnProfiles)
        profiles[name] = mapping
        self._config_mgr.update(columnProfiles=profiles, lastColumnProfile=name)
        self._load_profile_presets()
        self._profile_combo.setCurrentText(name)

    def _on_guess(self) -> None:
        guessed = guess_mapping(self._headers)
        if guessed:
            self._apply_mapping(guessed)
            self._mark_required_guessed(guessed)

    def _mark_required_guessed(self, mapping: Dict[str, str]) -> None:
        for field in self._optional_required:
            if field in mapping:
                self._optional_required[field].setChecked(True)

    def _apply_mapping(self, mapping: Dict[str, str]) -> None:
        for field, header in mapping.items():
            combo = self._combos.get(field)
            if combo is None:
                continue
            idx = combo.findText(header)
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def _current_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for field, combo in self._combos.items():
            header = combo.currentText()
            if header and header != _NONE_ITEM:
                mapping[field] = header
        return mapping

    def _required_fields(self) -> List[str]:
        mapping = self._current_mapping()
        required = []
        for field in COLUMN_FIELDS:
            if field in MIN_REQUIRED:
                required.append(field)
            elif self._optional_required.get(field, None) is not None and \
                    self._optional_required[field].isChecked():
                required.append(field)
        return [f for f in required if f in mapping]

    def _on_accept(self) -> None:
        missing = [f for f in MIN_REQUIRED if f not in self._current_mapping()]
        if missing:
            names = ", ".join(tr(_FIELD_LABELS[f]) for f in missing)
            QMessageBox.warning(
                self, tr("Warning"),
                tr("The following fields are required: {names}", names=names),
            )
            return
        self.accept()

    @property
    def column_mapping(self) -> Dict[str, str]:
        return self._current_mapping()

    @property
    def required_fields(self) -> List[str]:
        return self._required_fields()
