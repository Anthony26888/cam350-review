from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QTextEdit, QDialogButtonBox, QLabel, QGroupBox,
)
from PySide6.QtCore import Qt

from models.review import ReviewRecord


class EditDialog(QDialog):
    def __init__(self, record: ReviewRecord, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._record = record
        self.setWindowTitle(f"Edit - {record.designator}")
        self.setModal(True)
        self.setMinimumWidth(400)
        self._build_ui()
        self._load_values()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        original_group = QGroupBox("Original Values")
        original_layout = QFormLayout(original_group)
        original_layout.addRow("Designator:", QLabel(self._record.designator))
        original_layout.addRow("MPN:", QLabel(self._record.mpn))
        original_layout.addRow("Layer:", QLabel(self._record.layer))
        original_layout.addRow("X:", QLabel(str(self._record.old_x)))
        original_layout.addRow("Y:", QLabel(str(self._record.old_y)))
        original_layout.addRow("Rotation:", QLabel(str(self._record.old_rotation)))
        layout.addWidget(original_group)

        edit_group = QGroupBox("Edit Values")
        edit_layout = QFormLayout(edit_group)

        self._new_x = QDoubleSpinBox()
        self._new_x.setRange(-999999.0, 999999.0)
        self._new_x.setDecimals(4)
        self._new_x.setValue(self._record.old_x)

        self._new_y = QDoubleSpinBox()
        self._new_y.setRange(-999999.0, 999999.0)
        self._new_y.setDecimals(4)
        self._new_y.setValue(self._record.old_y)

        self._new_rotation = QDoubleSpinBox()
        self._new_rotation.setRange(-999999.0, 999999.0)
        self._new_rotation.setDecimals(4)
        self._new_rotation.setValue(self._record.old_rotation)

        self._remark = QTextEdit()
        self._remark.setMaximumHeight(80)
        self._remark.setPlaceholderText("Enter remark...")

        edit_layout.addRow("New X:", self._new_x)
        edit_layout.addRow("New Y:", self._new_y)
        edit_layout.addRow("New Rotation:", self._new_rotation)
        edit_layout.addRow("Remark:", self._remark)
        layout.addWidget(edit_group)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _load_values(self) -> None:
        if self._record.new_x is not None:
            self._new_x.setValue(self._record.new_x)
        if self._record.new_y is not None:
            self._new_y.setValue(self._record.new_y)
        if self._record.new_rotation is not None:
            self._new_rotation.setValue(self._record.new_rotation)
        self._remark.setText(self._record.remark)

    def _on_accept(self) -> None:
        self._record.new_x = self._new_x.value()
        self._record.new_y = self._new_y.value()
        self._record.new_rotation = self._new_rotation.value()
        self._record.remark = self._remark.toPlainText().strip()
        self.accept()

    @property
    def record(self) -> ReviewRecord:
        return self._record
