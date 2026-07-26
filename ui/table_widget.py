from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QComboBox,
    QHeaderView, QTableWidget, QTableWidgetItem, QHBoxLayout,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from models.review import ReviewRecord

_STATUS_COLORS = {
    "Pending": None,
    "OK": QColor(200, 255, 200),
    "Edited": QColor(255, 200, 200),
}

_COLUMNS = ["", "No", "Designator", "MPN", "Layer", "X", "Y", "Rotation", "Status"]


class TableWidget(QWidget):
    record_selected = Signal(int)
    jump_requested = Signal(int)
    filter_changed = Signal(int, int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._records: List[ReviewRecord] = []
        self._filtered: List[int] = []
        self._checked_set: set[int] = set()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)

        filter_layout = QHBoxLayout()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search (Ctrl+F)...")
        self._search_input.textChanged.connect(self._on_search)

        self._status_filter = QComboBox()
        self._status_filter.addItems(["All", "Pending", "OK", "Edited"])
        self._status_filter.currentTextChanged.connect(self._on_filter)

        filter_layout.addWidget(self._search_input, 3)
        filter_layout.addWidget(self._status_filter, 1)
        self._layout.addLayout(filter_layout)

        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.setStyleSheet(
            "QTableWidget::item:selected { background-color: #d5d5d5; color: black; }"
            "QTableWidget::item:hover { background-color: #e8e8e8; }"
        )
        self._table.cellClicked.connect(self._on_click)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)

        self._layout.addWidget(self._table)

    def set_records(self, records: List[ReviewRecord]) -> None:
        self._records = records
        self._checked_set.clear()
        self._apply_filters()

    def _apply_filters(self) -> None:
        search_text = self._search_input.text().strip().lower()
        status_filter = self._status_filter.currentText()

        self._filtered = []
        for i, rec in enumerate(self._records):
            if status_filter != "All" and rec.status != status_filter:
                continue
            if search_text:
                fields = [
                    rec.designator.lower(),
                    rec.mpn.lower(),
                    rec.layer.lower(),
                ]
                if not any(search_text in f for f in fields):
                    continue
            self._filtered.append(i)

        self._refresh_table()
        self.filter_changed.emit(len(self._filtered), len(self._records))

    @staticmethod
    def _display_x(rec: ReviewRecord) -> str:
        return _format_float(rec.new_x) if rec.new_x is not None else _format_float(rec.old_x)

    @staticmethod
    def _display_y(rec: ReviewRecord) -> str:
        return _format_float(rec.new_y) if rec.new_y is not None else _format_float(rec.old_y)

    @staticmethod
    def _display_rotation(rec: ReviewRecord) -> str:
        return _format_float(rec.new_rotation) if rec.new_rotation is not None else _format_float(rec.old_rotation)

    def _refresh_table(self) -> None:
        self._table.blockSignals(True)
        self._table.setRowCount(len(self._filtered))

        for row, idx in enumerate(self._filtered):
            self._set_row_values(row, idx)
        self._table.blockSignals(False)

    def _set_row_values(self, row: int, idx: int) -> None:
        rec = self._records[idx]

        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check_item.setCheckState(Qt.Checked if idx in self._checked_set else Qt.Unchecked)
        check_item.setData(Qt.UserRole, idx)
        self._table.setItem(row, 0, check_item)

        values = [
            str(idx + 1),
            rec.designator,
            rec.mpn,
            rec.layer,
            self._display_x(rec),
            self._display_y(rec),
            self._display_rotation(rec),
            rec.status,
        ]

        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setData(Qt.UserRole, idx)
            self._table.setItem(row, col + 1, item)

        color = _STATUS_COLORS.get(rec.status)
        if color:
            for col in range(len(_COLUMNS)):
                item = self._table.item(row, col)
                if item:
                    item.setBackground(color)

    def select_record(self, record_index: int) -> None:
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                self._table.selectRow(row)
                self._table.scrollToItem(self._table.item(row, 0))
                break

    def get_selected_record_index(self) -> int:
        current = self._table.currentRow()
        if current >= 0 and current < len(self._filtered):
            return self._filtered[current]
        return 0

    def get_checked_indices(self) -> List[int]:
        return sorted(self._checked_set)

    def update_record_row(self, record_index: int) -> None:
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                self._set_row_values(row, idx)
                break

    def update_record_status(self, record_index: int, status: str) -> None:
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                item = QTableWidgetItem(status)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setData(Qt.UserRole, idx)
                self._table.setItem(row, 8, item)
                color = _STATUS_COLORS.get(status)
                if color:
                    for col in range(len(_COLUMNS)):
                        cell = self._table.item(row, col)
                        if cell:
                            cell.setBackground(color)
                break

    def _on_search(self) -> None:
        self._apply_filters()

    def _on_filter(self) -> None:
        self._apply_filters()

    def _on_click(self, row: int, col: int) -> None:
        if col == 0:
            return
        if row >= 0 and row < len(self._filtered):
            idx = self._filtered[row]
            self.record_selected.emit(idx)

    def _on_double_click(self, row: int, _: int) -> None:
        if row >= 0 and row < len(self._filtered):
            idx = self._filtered[row]
            self.jump_requested.emit(idx)

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        if item.column() == 0:
            idx = item.data(Qt.UserRole)
            if idx is not None:
                if item.checkState() == Qt.Checked:
                    self._checked_set.add(idx)
                else:
                    self._checked_set.discard(idx)

    def _on_header_clicked(self, section: int) -> None:
        if section != 0:
            return
        any_unchecked = any(
            self._table.item(row, 0).checkState() == Qt.Unchecked
            for row in range(self._table.rowCount())
            if self._table.item(row, 0)
        )
        self._table.blockSignals(True)
        if any_unchecked:
            self._checked_set.update(self._filtered)
            for row in range(self._table.rowCount()):
                self._table.item(row, 0).setCheckState(Qt.Checked)
        else:
            self._checked_set.clear()
            for row in range(self._table.rowCount()):
                self._table.item(row, 0).setCheckState(Qt.Unchecked)
        self._table.blockSignals(False)


def _format_float(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return f"{value:.4f}"
