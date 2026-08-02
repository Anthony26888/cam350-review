from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QFormLayout, QDoubleSpinBox,
    QCheckBox, QDialogButtonBox, QGroupBox, QTextEdit, QLabel,
)


class BatchEditDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Batch Edit - Offset Values")
        self.setModal(True)
        self.setMinimumWidth(380)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        group = QGroupBox("Offset Values (applied to selected records)")
        form = QFormLayout(group)

        self._apply_x = QCheckBox("Apply X offset")
        self._offset_x = QDoubleSpinBox()
        self._offset_x.setRange(-999999.0, 999999.0)
        self._offset_x.setDecimals(4)
        self._offset_x.setEnabled(False)
        self._apply_x.toggled.connect(self._offset_x.setEnabled)

        self._negative_x = QCheckBox("Make new X negative")

        self._apply_y = QCheckBox("Apply Y offset")
        self._offset_y = QDoubleSpinBox()
        self._offset_y.setRange(-999999.0, 999999.0)
        self._offset_y.setDecimals(4)
        self._offset_y.setEnabled(False)
        self._apply_y.toggled.connect(self._offset_y.setEnabled)

        self._negative_y = QCheckBox("Make new Y negative")

        self._apply_rotation = QCheckBox("Apply Rotation offset")
        self._offset_rotation = QDoubleSpinBox()
        self._offset_rotation.setRange(-999999.0, 999999.0)
        self._offset_rotation.setDecimals(4)
        self._offset_rotation.setEnabled(False)
        self._apply_rotation.toggled.connect(self._offset_rotation.setEnabled)

        self._remark = QTextEdit()
        self._remark.setMaximumHeight(80)
        self._remark.setPlaceholderText("Enter remark (applied to all selected)...")

        form.addRow(self._apply_x, self._offset_x)
        form.addRow("", self._negative_x)
        form.addRow(self._apply_y, self._offset_y)
        form.addRow("", self._negative_y)
        form.addRow(self._apply_rotation, self._offset_rotation)
        form.addRow("Remark:", self._remark)
        layout.addWidget(group)

        info = QLabel("New value = current value + offset\nMake new X/Y negative flips the sign of the resulting coordinate")
        info.setStyleSheet("color: #666; font-style: italic;")
        layout.addWidget(info)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @property
    def is_apply_x(self) -> bool:
        return self._apply_x.isChecked()

    @property
    def is_apply_y(self) -> bool:
        return self._apply_y.isChecked()

    @property
    def is_apply_rotation(self) -> bool:
        return self._apply_rotation.isChecked()

    @property
    def offset_x(self) -> float:
        return self._offset_x.value()

    @property
    def is_negative_x(self) -> bool:
        return self._negative_x.isChecked()

    @property
    def offset_y(self) -> float:
        return self._offset_y.value()

    @property
    def is_negative_y(self) -> bool:
        return self._negative_y.isChecked()

    @property
    def offset_rotation(self) -> float:
        return self._offset_rotation.value()

    @property
    def remark(self) -> str:
        return self._remark.toPlainText().strip()
