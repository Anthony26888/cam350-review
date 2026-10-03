from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLineEdit, QComboBox,
    QHeaderView, QTableWidget, QTableWidgetItem, QHBoxLayout,
    QDoubleSpinBox, QLabel, QPushButton, QStyle, QMenu,
    QDialog, QFormLayout, QGroupBox,
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QBrush

from models.review import ReviewRecord
from ui.i18n import tr
from ui.style import status_bg_colors, status_text_colors

_BLOCK_COLUMN = 3
_FLAGS_COLUMN = 9
_STATUS_COLUMN = 10
_CHECK_COLUMN = 11
_REMARK_COLUMN = 12

_COLUMNS = ["", "No", "Designator", "Block", "MPN", "Layer", "X", "Y", "Rotation", "Flags", "Status", "Checked", "Remark"]

_BLOCK_COLORS = [
    QColor("#2563EB"),
    QColor("#7C3AED"),
    QColor("#DB2777"),
    QColor("#0891B2"),
    QColor("#65A30D"),
    QColor("#C2410C"),
    QColor("#4F46E5"),
    QColor("#0F766E"),
    QColor("#B45309"),
    QColor("#1D4ED8"),
]

_FLAG_COLOR = QColor("#F59E0B")

_FLAG_DESCRIPTIONS = {
    "ROT": ("Unusual rotation", "góc xoay bất thường"),
    "PAD": ("Does not match paste pad", "không khớp pad paste"),
    "DUP": ("Duplicate coordinates", "trùng tọa độ với linh kiện khác"),
    "OUT": ("Outside board outline", "nằm ngoài outline board"),
}


def flag_kind_tooltip(kind: str) -> str:
    name_en, name_vi = _FLAG_DESCRIPTIONS.get(kind, (kind, kind))
    return f"{kind} = {name_vi}"


def _block_color(block: int) -> Optional[QColor]:
    if block <= 0:
        return None
    return _BLOCK_COLORS[(block - 1) % len(_BLOCK_COLORS)]


_RANGE_MIN = -999999.0
_RANGE_MAX = 999999.0

_ICON_CHECKED: Optional[QIcon] = None
_ICON_UNCHECKED: Optional[QIcon] = None


def _build_check_icon(checked: bool) -> QIcon:
    pm = QPixmap(16, 16)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    if checked:
        pen = QPen(QColor("#22C55E"), 2.2)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        path = QPainterPath()
        path.moveTo(3.0, 8.5)
        path.lineTo(6.5, 12.0)
        path.lineTo(13.0, 4.0)
        p.drawPath(path)
    else:
        p.setBrush(QColor("#F97316"))
        p.setPen(Qt.NoPen)
        p.drawEllipse(4.0, 4.0, 8.0, 8.0)
    p.end()
    return QIcon(pm)


def _check_icon(checked: bool) -> QIcon:
    global _ICON_CHECKED, _ICON_UNCHECKED
    if _ICON_CHECKED is None:
        _ICON_CHECKED = _build_check_icon(True)
    if _ICON_UNCHECKED is None:
        _ICON_UNCHECKED = _build_check_icon(False)
    return _ICON_CHECKED if checked else _ICON_UNCHECKED


class TableWidget(QWidget):
    record_selected = Signal(int)
    jump_requested = Signal(int)
    filter_changed = Signal(int, int)
    flag_dismiss_requested = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._records: List[ReviewRecord] = []
        self._filtered: List[int] = []
        self._checked_set: set[int] = set()

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(3)

        filter_layout = QHBoxLayout()
        filter_layout.setSpacing(4)

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText(tr("Search..."))
        self._search_input.textChanged.connect(self._on_search)

        self._layer_filter = QComboBox()
        self._layer_filter.addItem(tr("All"), userData=None)
        self._layer_filter.currentIndexChanged.connect(self._on_filter)
        self._layer_filter.setMinimumWidth(100)
        self._layer_filter.setMaximumWidth(150)

        self._status_filter = QComboBox()
        for _status in ["All", "Pending", "OK", "Edited", "Aligned"]:
            self._status_filter.addItem(tr(_status), userData=_status)
        self._status_filter.currentTextChanged.connect(self._on_filter)
        self._status_filter.setMinimumWidth(100)
        self._status_filter.setMaximumWidth(150)

        self._checked_filter = QComboBox()
        for _check in ["All", "Checked", "Unchecked"]:
            self._checked_filter.addItem(tr(_check), userData=_check)
        self._checked_filter.currentTextChanged.connect(self._on_filter)
        self._checked_filter.setMinimumWidth(100)
        self._checked_filter.setMaximumWidth(150)

        self._block_filter = QComboBox()
        self._block_filter.addItem(tr("All"), userData=None)
        self._block_filter.currentIndexChanged.connect(self._on_filter)
        self._block_filter.setMinimumWidth(80)
        self._block_filter.setMaximumWidth(120)

        self._x_min = QDoubleSpinBox()
        self._x_min.setRange(_RANGE_MIN, _RANGE_MAX)
        self._x_min.setValue(_RANGE_MIN)
        self._x_min.setDecimals(1)
        self._x_min.setFixedWidth(80)
        self._x_min.editingFinished.connect(self._on_filter)

        self._x_max = QDoubleSpinBox()
        self._x_max.setRange(_RANGE_MIN, _RANGE_MAX)
        self._x_max.setValue(_RANGE_MAX)
        self._x_max.setDecimals(1)
        self._x_max.setFixedWidth(80)
        self._x_max.editingFinished.connect(self._on_filter)

        self._y_min = QDoubleSpinBox()
        self._y_min.setRange(_RANGE_MIN, _RANGE_MAX)
        self._y_min.setValue(_RANGE_MIN)
        self._y_min.setDecimals(1)
        self._y_min.setFixedWidth(80)
        self._y_min.editingFinished.connect(self._on_filter)

        self._y_max = QDoubleSpinBox()
        self._y_max.setRange(_RANGE_MIN, _RANGE_MAX)
        self._y_max.setValue(_RANGE_MAX)
        self._y_max.setDecimals(1)
        self._y_max.setFixedWidth(80)
        self._y_max.editingFinished.connect(self._on_filter)

        filter_layout.addWidget(self._search_input, 1)
        self._btn_filters = QPushButton(tr("Filters…"))
        self._btn_filters.setFixedWidth(80)
        self._btn_filters.setToolTip(tr("Open filters dialog"))
        self._btn_filters.clicked.connect(self._toggle_filter_dialog)
        self._btn_clear = QPushButton()
        self._btn_clear.setIconSize(QSize(14, 14))
        self._btn_clear.setFixedWidth(24)
        self._btn_clear.setToolTip(tr("Clear all filters"))
        self._btn_clear.clicked.connect(self._clear_filters)
        self.refresh_icons()
        filter_layout.addWidget(self._btn_filters)
        filter_layout.addWidget(self._btn_clear)
        self._layout.addLayout(filter_layout)

        self._filter_dialog = None

        self._table = QTableWidget()
        self._table.setColumnCount(len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([tr(c) for c in _COLUMNS])
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setSelectionMode(QTableWidget.SingleSelection)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._table.cellClicked.connect(self._on_click)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        self._table.itemChanged.connect(self._on_item_changed)
        self._table.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self._table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)

        self._layout.addWidget(self._table)

    def refresh_icons(self) -> None:
        self._btn_clear.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_LineEditClearButton)
        )

    def set_records(self, records: List[ReviewRecord]) -> None:
        self._records = records
        self._checked_set.clear()
        self._reload_layer_filter()
        self._reload_block_filter()
        self._apply_filters()

    def _reload_layer_filter(self) -> None:
        prev = self._layer_filter.currentData()
        layers: dict = {}
        for rec in self._records:
            key = rec.layer.strip().lower()
            if key and key not in layers:
                layers[key] = rec.layer.strip()
        self._layer_filter.blockSignals(True)
        self._layer_filter.clear()
        self._layer_filter.addItem(tr("All"), userData=None)
        for key, label in layers.items():
            self._layer_filter.addItem(label, userData=label)
        self._layer_filter.blockSignals(False)
        if prev is not None:
            idx = self._layer_filter.findData(prev)
            if idx >= 0:
                self._layer_filter.setCurrentIndex(idx)

    def _reload_block_filter(self) -> None:
        prev = self._block_filter.currentData()
        blocks = sorted({r.block for r in self._records if r.block > 0})
        self._block_filter.blockSignals(True)
        self._block_filter.clear()
        self._block_filter.addItem(tr("All"), userData=None)
        for b in blocks:
            self._block_filter.addItem(str(b), userData=b)
        self._block_filter.blockSignals(False)
        if prev is not None and prev in blocks:
            idx = self._block_filter.findData(prev)
            if idx >= 0:
                self._block_filter.setCurrentIndex(idx)

    def _apply_filters(self) -> None:
        search_text = self._search_input.text().strip().lower()
        layer_filter = self._layer_filter.currentData()
        status_filter = self._status_filter.currentData() or "All"
        checked_filter = self._checked_filter.currentData() or "All"
        block_filter = self._block_filter.currentData()
        x_min = self._x_min.value()
        x_max = self._x_max.value()
        y_min = self._y_min.value()
        y_max = self._y_max.value()
        has_x_filter = x_min <= x_max and (x_min != _RANGE_MIN or x_max != _RANGE_MAX)
        has_y_filter = y_min <= y_max and (y_min != _RANGE_MIN or y_max != _RANGE_MAX)

        self._filtered = []
        for i, rec in enumerate(self._records):
            if block_filter is not None and rec.block != block_filter:
                continue
            if layer_filter and rec.layer.strip().lower() != layer_filter.lower():
                continue
            if status_filter != "All" and rec.status != status_filter:
                continue
            if checked_filter == "Checked" and not rec.checked:
                continue
            if checked_filter == "Unchecked" and rec.checked:
                continue
            if search_text:
                fields = [
                    rec.designator.lower(),
                    rec.mpn.lower(),
                    rec.layer.lower(),
                ]
                if not any(search_text in f for f in fields):
                    continue
            rx = rec.new_x if rec.new_x is not None else rec.old_x
            ry = rec.new_y if rec.new_y is not None else rec.old_y
            if has_x_filter and not (x_min <= rx <= x_max):
                continue
            if has_y_filter and not (y_min <= ry <= y_max):
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

    def _bulk_fill_begin(self):
        """Disable per-cell column re-measuring during mass row writes.

        With ResizeToContents active, every setItem() makes the header
        re-measure the whole column -> O(n^2). Swapping to Interactive for
        the duration and doing ONE resizeColumnsToContents() at the end
        produces identical visuals at O(n).
        """
        header = self._table.horizontalHeader()
        state = {
            "header": header,
            "mode": header.sectionResizeMode(0),
            "updates": self._table.updatesEnabled(),
        }
        header.setSectionResizeMode(QHeaderView.Interactive)
        self._table.setUpdatesEnabled(False)
        self._table.blockSignals(True)
        return state

    def _bulk_fill_end(self, state) -> None:
        self._table.resizeColumnsToContents()
        self._table.blockSignals(False)
        self._table.setUpdatesEnabled(state["updates"])
        state["header"].setSectionResizeMode(state["mode"])

    def _refresh_table(self) -> None:
        text_colors = self._status_text_colors()
        bg_colors = self._status_bg_colors()
        state = self._bulk_fill_begin()
        try:
            self._table.setRowCount(len(self._filtered))
            for row, idx in enumerate(self._filtered):
                self._set_row_values(row, idx,
                                     text_colors=text_colors,
                                     bg_colors=bg_colors)
        finally:
            self._bulk_fill_end(state)

    def _status_text_colors(self) -> dict:
        from config.config_manager import ConfigManager
        return status_text_colors(ConfigManager.instance().config.theme)

    def _status_bg_colors(self) -> dict:
        from config.config_manager import ConfigManager
        return status_bg_colors(ConfigManager.instance().config.theme)

    def _set_row_values(self, row: int, idx: int,
                        text_colors: dict = None, bg_colors: dict = None) -> None:
        rec = self._records[idx]
        if text_colors is None:
            text_colors = self._status_text_colors()
        if bg_colors is None:
            bg_colors = self._status_bg_colors()

        check_item = QTableWidgetItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        check_item.setCheckState(Qt.Checked if idx in self._checked_set else Qt.Unchecked)
        check_item.setData(Qt.UserRole, idx)
        self._table.setItem(row, 0, check_item)

        values = [
            str(idx + 1),
            rec.designator,
            str(rec.block) if rec.block else "",
            rec.mpn,
            rec.layer,
            self._display_x(rec),
            self._display_y(rec),
            self._display_rotation(rec),
        ]

        for col, val in enumerate(values):
            item = QTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            item.setData(Qt.UserRole, idx)
            self._table.setItem(row, col + 1, item)

        block_color = _block_color(rec.block)
        if block_color:
            block_item = QTableWidgetItem(str(rec.block))
            block_item.setFlags(block_item.flags() & ~Qt.ItemIsEditable)
            block_item.setData(Qt.UserRole, idx)
            block_item.setForeground(block_color)
            block_item.setToolTip(tr("Panel block {b}", b=rec.block))
            self._table.setItem(row, _BLOCK_COLUMN, block_item)

        flags_item = QTableWidgetItem("·".join(rec.prescreen_flags))
        flags_item.setFlags(flags_item.flags() & ~Qt.ItemIsEditable)
        flags_item.setData(Qt.UserRole, idx)
        if rec.prescreen_flags:
            flags_item.setForeground(QBrush(_FLAG_COLOR))
            flags_item.setToolTip(
                "\n".join(flag_kind_tooltip(k) for k in rec.prescreen_flags)
            )
        self._table.setItem(row, _FLAGS_COLUMN, flags_item)

        status_item = QTableWidgetItem(tr(rec.status))
        status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
        status_item.setData(Qt.UserRole, idx)
        text_color = text_colors.get(rec.status)
        if text_color:
            status_item.setForeground(text_color)
        self._table.setItem(row, _STATUS_COLUMN, status_item)

        check_item = QTableWidgetItem()
        check_item.setFlags(check_item.flags() & ~Qt.ItemIsEditable)
        check_item.setData(Qt.UserRole, idx)
        check_item.setIcon(_check_icon(rec.checked))
        self._table.setItem(row, _CHECK_COLUMN, check_item)

        remark_item = QTableWidgetItem(rec.remark)
        remark_item.setFlags(remark_item.flags() & ~Qt.ItemIsEditable)
        remark_item.setData(Qt.UserRole, idx)
        self._table.setItem(row, _REMARK_COLUMN, remark_item)

        color = bg_colors.get(rec.status)
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

    def clear_checked(self) -> None:
        self._checked_set.clear()
        self._table.blockSignals(True)
        for row in range(self._table.rowCount()):
            item = self._table.item(row, 0)
            if item:
                item.setCheckState(Qt.Unchecked)
        self._table.blockSignals(False)

    def update_record_row(self, record_index: int) -> None:
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                self._set_row_values(row, idx)
                break

    def update_all_rows(self) -> None:
        text_colors = self._status_text_colors()
        bg_colors = self._status_bg_colors()
        state = self._bulk_fill_begin()
        try:
            for row, idx in enumerate(self._filtered):
                self._set_row_values(row, idx,
                                     text_colors=text_colors,
                                     bg_colors=bg_colors)
        finally:
            self._bulk_fill_end(state)

    def _on_context_menu(self, pos) -> None:
        row = self._table.rowAt(pos.y())
        if not (0 <= row < len(self._filtered)):
            return
        idx = self._filtered[row]
        rec = self._records[idx]
        if not rec.prescreen_flags:
            return
        menu = QMenu(self)
        act = menu.addAction(tr("Dismiss flag"))
        chosen = menu.exec(self._table.viewport().mapToGlobal(pos))
        if chosen is act:
            self.flag_dismiss_requested.emit(idx)

    def update_record_status(self, record_index: int, status: str) -> None:
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                item = QTableWidgetItem(status)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setData(Qt.UserRole, idx)
                text_color = self._status_text_colors().get(status)
                if text_color:
                    item.setForeground(text_color)
                self._table.setItem(row, _STATUS_COLUMN, item)
                color = self._status_bg_colors().get(status)
                if color:
                    for col in range(len(_COLUMNS)):
                        cell = self._table.item(row, col)
                        if cell:
                            cell.setBackground(color)
                break

    def update_record_checked(self, record_index: int) -> None:
        if self._checked_filter.currentData() != "All":
            self._apply_filters()
            return
        for row, idx in enumerate(self._filtered):
            if idx == record_index:
                item = self._table.item(row, _CHECK_COLUMN)
                if item is not None:
                    item.setIcon(_check_icon(self._records[idx].checked))
                break

    def _clear_filters(self) -> None:
        self._search_input.clear()
        self._layer_filter.setCurrentIndex(0)
        self._status_filter.setCurrentIndex(0)
        self._checked_filter.setCurrentIndex(0)
        self._block_filter.setCurrentIndex(0)
        self._x_min.setValue(_RANGE_MIN)
        self._x_max.setValue(_RANGE_MAX)
        self._y_min.setValue(_RANGE_MIN)
        self._y_max.setValue(_RANGE_MAX)
        self._apply_filters()

    def _build_filter_dialog(self) -> QDialog:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Filters"))
        dlg.setWindowFlags(Qt.Dialog)
        dlg.setWindowModality(Qt.NonModal)
        dlg.setMinimumWidth(360)
        layout = QVBoxLayout(dlg)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        # Attribute group
        attr_group = QGroupBox(tr("Attribute filters"))
        attr_layout = QFormLayout(attr_group)
        attr_layout.setContentsMargins(8, 8, 8, 8)
        attr_layout.addRow(tr("Layer:"), self._layer_filter)
        attr_layout.addRow(tr("Status:"), self._status_filter)
        attr_layout.addRow(tr("Block:"), self._block_filter)
        attr_layout.addRow(tr("Checked:"), self._checked_filter)
        layout.addWidget(attr_group)

        # Range group
        range_group = QGroupBox(tr("Coordinate range"))
        range_layout = QFormLayout(range_group)
        range_layout.setContentsMargins(8, 8, 8, 8)
        x_widget = QWidget()
        x_layout = QHBoxLayout(x_widget)
        x_layout.setContentsMargins(0, 0, 0, 0)
        x_layout.setSpacing(4)
        x_layout.addWidget(self._x_min)
        x_layout.addWidget(QLabel(tr("~")))
        x_layout.addWidget(self._x_max)
        x_layout.addStretch(1)
        y_widget = QWidget()
        y_layout = QHBoxLayout(y_widget)
        y_layout.setContentsMargins(0, 0, 0, 0)
        y_layout.setSpacing(4)
        y_layout.addWidget(self._y_min)
        y_layout.addWidget(QLabel(tr("~")))
        y_layout.addWidget(self._y_max)
        y_layout.addStretch(1)
        range_layout.addRow(tr("X:"), x_widget)
        range_layout.addRow(tr("Y:"), y_widget)
        layout.addWidget(range_group)

        btn_row = QHBoxLayout()
        btn_clear = QPushButton(tr("Clear filters"))
        btn_clear.clicked.connect(self._clear_filters)
        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(dlg.hide)
        btn_row.addWidget(btn_clear, 1)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        dlg.adjustSize()
        dlg.setMaximumSize(dlg.sizeHint())
        return dlg

    def _toggle_filter_dialog(self) -> None:
        if self._filter_dialog is None:
            self._filter_dialog = self._build_filter_dialog()
        if self._filter_dialog.isVisible():
            self._filter_dialog.hide()
        else:
            self._filter_dialog.show()
            self._filter_dialog.raise_()
            self._filter_dialog.activateWindow()

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
