from typing import Dict, List, Optional

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QFormLayout,
    QComboBox, QLabel, QDialogButtonBox,
)

from services.bom_reader import BOM_FIELDS, guess_bom_mapping
from ui.i18n import tr

_FIELD_LABELS = {
    "designator": "Designator",
    "mpn": "MPN",
    "description": "Description",
    "quantity": "Quantity",
    "note": "Note",
}

_NONE_ITEM = "—"


class BomMappingDialog(QDialog):
    """Choose which Excel header maps to each BOM field."""

    def __init__(
        self,
        file_path: str,
        headers: List[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._file_path = file_path
        self._headers = list(dict.fromkeys([h for h in headers if h]))
        self.setWindowTitle(tr("BOM Column Mapping"))
        self.setModal(True)
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(file_path))

        form = QFormLayout()
        self._combos: Dict[str, QComboBox] = {}
        guessed = guess_bom_mapping(self._headers)
        for field in BOM_FIELDS:
            combo = QComboBox()
            combo.addItem(_NONE_ITEM)
            combo.addItems(self._headers)
            target = guessed.get(field, "")
            if target:
                idx = combo.findText(target)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            elif field == "designator" and self._headers:
                combo.setCurrentIndex(1 if len(self._headers) > 1 else 0)
            self._combos[field] = combo
            label = _FIELD_LABELS[field]
            if field == "designator":
                label += " *"
            form.addRow(label, combo)
        layout.addLayout(form)
        layout.addWidget(QLabel(tr("Designator column is required.")))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        if not self.column_mapping.get("designator"):
            return
        self.accept()

    @property
    def column_mapping(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        for field, combo in self._combos.items():
            text = combo.currentText()
            if text and text != _NONE_ITEM:
                mapping[field] = text
        return mapping

