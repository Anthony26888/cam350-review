from typing import Dict, List, Optional, Set, Tuple

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyle,
)
from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QColor, QTextDocument

from models.bom import BomRow
from ui.i18n import tr

_COLUMNS = ["No", "Designator", "MPN", "Description", "Quantity", "Note",
            "Missing Pickplace"]

_DESIGNATOR_COLUMN = 1
_DESIGNATOR_WIDTH = 300
_MISSING_COLUMN = 6
_MISSING_WIDTH = 170

_RED = QColor("#DC2626")
_QTY_WARN_BG = QColor("#FEF3C7")

_BOM_DESIGNATOR_HTML_ROLE = Qt.UserRole + 1


def designator_cell_html(names: List[str], bottom_keys: Set[str]) -> str:
    """Rich text for a Designator cell: only Bottom designators red."""
    parts: List[str] = []
    for name in names:
        label = name.strip()
        if not label:
            continue
        if label.upper() in bottom_keys:
            parts.append(f'<span style="color:#DC2626;">{label}</span>')
        else:
            parts.append(label)
    return ", ".join(parts)


class BomDesignatorDelegate(QStyledItemDelegate):
    """Paints per-designator Bottom highlighting (rich text, wraps)."""

    def paint(self, painter, option, index) -> None:
        html = index.data(_BOM_DESIGNATOR_HTML_ROLE)
        if not html:
            super().paint(painter, option, index)
            return
        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        doc = QTextDocument()
        doc.setHtml(html)
        doc.setTextWidth(option.rect.width())
        painter.translate(option.rect.topLeft())
        doc.drawContents(
            painter, QRectF(0, 0, option.rect.width(), option.rect.height()))
        painter.restore()

    def sizeHint(self, option, index):
        html = index.data(_BOM_DESIGNATOR_HTML_ROLE)
        if not html:
            return super().sizeHint(option, index)
        doc = QTextDocument()
        doc.setHtml(html)
        width = max(option.rect.width(), 1) if option.rect.width() > 0 else 300
        doc.setTextWidth(width)
        size = super().sizeHint(option, index)
        size.setHeight(max(int(doc.size().height()) + 4, size.height()))
        return size


class BomTableWidget(QWidget):
    bom_row_selected = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: List[BomRow] = []
        self._visible_rows: List[BomRow] = []
        self._missing: Dict[int, List[str]] = {}
        self._bottom_keys: Set[str] = set()
        self._qty_warn: Set[int] = set()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(4)
        self._search = QLineEdit()
        self._search.setPlaceholderText(tr("Search..."))
        self._search.textChanged.connect(self._refresh)
        top.addWidget(self._search, 1)
        self._count = QLabel("")
        top.addWidget(self._count)
        layout.addLayout(top)

        self._table = QTableWidget(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels([tr(c) for c in _COLUMNS])
        self._table.setAlternatingRowColors(True)
        self._table.setWordWrap(True)
        self._table.setTextElideMode(Qt.ElideNone)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.cellClicked.connect(self._on_cell_clicked)
        header = self._table.horizontalHeader()
        # Every column user-resizable: Interactive keeps manual widths across
        # refreshes; initial widths are set once on first data render.
        # The last column stretches to absorb leftover viewport space so no
        # blank non-header gap shows when columns are narrower than the view.
        for col in range(len(_COLUMNS)):
            header.setSectionResizeMode(col, QHeaderView.Interactive)
        header.setStretchLastSection(True)
        self._table.setColumnWidth(_DESIGNATOR_COLUMN, _DESIGNATOR_WIDTH)
        self._table.setColumnWidth(_MISSING_COLUMN, _MISSING_WIDTH)
        self._table.setItemDelegateForColumn(
            _DESIGNATOR_COLUMN, BomDesignatorDelegate(self._table))
        self._sized_once = False
        layout.addWidget(self._table, 1)
        self._show_placeholder()

    # -- data -----------------------------------------------------------
    def set_bom_rows(
        self, rows: List[BomRow],
        missing: Optional[Dict[int, List[str]]] = None,
        bottom_keys: Optional[Set[str]] = None,
        qty_warn: Optional[Set[int]] = None,
    ) -> None:
        self._rows = list(rows)
        if missing is not None:
            self._missing = dict(missing)
        if bottom_keys is not None:
            self._bottom_keys = {k.upper() for k in bottom_keys}
        if qty_warn is not None:
            self._qty_warn = set(qty_warn)
        self._refresh()

    def set_compare(self, missing: Dict[int, List[str]],
                    bottom_keys: Set[str], qty_warn: Set[int]) -> None:
        self._missing = dict(missing)
        self._bottom_keys = {k.upper() for k in bottom_keys}
        self._qty_warn = set(qty_warn)
        self._refresh()

    def clear(self) -> None:
        self._rows = []
        self._visible_rows = []
        self._missing = {}
        self._bottom_keys = set()
        self._qty_warn = set()
        self._search.clear()
        self._show_placeholder()

    # -- render ---------------------------------------------------------
    def _show_placeholder(self) -> None:
        self._table.clearContents()
        self._table.setRowCount(1)
        item = QTableWidgetItem(tr("No BOM data. Use File -> Open BOM Excel..."))
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        self._table.setItem(0, 0, item)
        self._table.setSpan(0, 0, 1, len(_COLUMNS))
        self._count.setText("")

    def _refresh(self) -> None:
        query = self._search.text().strip().lower()
        rows = self._rows
        if query:
            rows = [r for r in rows if query in (
                f"{r.stt} {r.designator_display} {r.mpn} "
                f"{r.description} {r.note}".lower()
            )]
        try:
            self._table.clearSpans()
        except Exception:
            pass
        if not rows:
            self._visible_rows = []
            if self._rows:
                self._table.clearContents()
                self._table.setRowCount(0)
                self._count.setText(f"0 / {len(self._rows)}")
            else:
                self._show_placeholder()
            return
        self._visible_rows = list(rows)
        self._table.clearContents()
        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            missing = self._missing.get(r.stt, [])
            # spaces after commas give the word-wrap clean break points
            wrapped_des = ", ".join(
                d.strip() for d in r.designator_display.split(",") if d.strip()
            )
            cells = [
                str(r.stt),
                wrapped_des,
                r.mpn,
                r.description,
                r.quantity_raw or (str(r.quantity) if r.quantity else ""),
                r.note,
                ", ".join(missing),
            ]
            for j, val in enumerate(cells):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                self._table.setItem(i, j, item)
            # per-designator Bottom red via the rich-text delegate: only the
            # Bottom designators turn red, the rest stay normal
            names = [d.strip() for d in r.designator_display.split(",") if d.strip()]
            if not names:
                names = [d.strip() for d in r.designators if d.strip()]
            des_item = self._table.item(i, 1)
            if des_item is not None:
                des_item.setData(
                    _BOM_DESIGNATOR_HTML_ROLE,
                    designator_cell_html(names, self._bottom_keys))
            if r.stt in self._qty_warn:
                qty_item = self._table.item(i, 4)
                if qty_item is not None:
                    qty_item.setBackground(_QTY_WARN_BG)
                    qty_item.setToolTip(tr(
                        "BOM quantity {q} differs from {n} designators",
                        q=r.quantity, n=len(r.designators)))
        self._table.resizeRowsToContents()
        if not self._sized_once:
            self._table.resizeColumnsToContents()
            self._table.setColumnWidth(_DESIGNATOR_COLUMN, _DESIGNATOR_WIDTH)
            self._table.setColumnWidth(_MISSING_COLUMN, _MISSING_WIDTH)
            self._sized_once = True
        self._count.setText(f"{len(rows)} / {len(self._rows)}")

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        # expand the clicked row to its full wrapped height and bring it
        # into view, so long Designator/Missing lists are never cut off
        if 0 <= row < self._table.rowCount():
            self._table.resizeRowToContents(row)
            item = self._table.item(row, 0)
            if item is not None:
                self._table.scrollToItem(item)
        if 0 <= row < len(self._visible_rows):
            self.bom_row_selected.emit(self._visible_rows[row].stt)

    def showEvent(self, event) -> None:  # noqa: N802 (Qt override)
        super().showEvent(event)
        self.refit_rows()

    def refit_rows(self) -> None:
        # Refit row heights only when actually visible: measuring while the
        # BOM tab is hidden yields oversized rows (fixed on next click).
        if not self.isVisible():
            return
        self._table.resizeRowsToContents()

    def row_count(self) -> int:
        return self._table.rowCount()
