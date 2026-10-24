from typing import List, Optional, Tuple

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QPushButton, QFileDialog, QDoubleSpinBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QButtonGroup,
    QDialogButtonBox,
)
from PySide6.QtCore import Qt, Signal

from models.pickplace import PickPlaceData
from services.eco_diff import EcoDiff
from services.pickplace_reader import (
    PickPlaceReader, STANDARD_MAPPING, STANDARD_REQUIRED,
)
from ui.i18n import tr
from ui.mapping_dialog import ColumnMappingDialog


def _fmt(v: float) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return ""
    return str(int(f)) if f == int(f) else f"{f:.4f}"


class EcoPickDialog(QDialog):
    """Pick the NEW PickPlace file + tolerances for an ECO compare."""

    def __init__(
        self,
        old_count: int,
        old_source: str,
        move_tol: float,
        rot_tol: float,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._reader = PickPlaceReader()
        self._file_path = ""
        self._data: Optional[PickPlaceData] = None
        self.setWindowTitle(tr("Compare Revisions (ECO)"))
        self.setModal(True)
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Old (current session): {n} records from {src}",
                                    n=old_count, src=old_source or "-")))
        file_row = QHBoxLayout()
        self._file_label = QLabel(tr("(not selected)"))
        browse = QPushButton(tr("Browse..."))
        browse.clicked.connect(self._browse)
        file_row.addWidget(self._file_label, 1)
        file_row.addWidget(browse)
        layout.addLayout(file_row)
        self._mapping_label = QLabel("")
        layout.addWidget(self._mapping_label)

        form = QFormLayout()
        self._spin_move = QDoubleSpinBox()
        self._spin_move.setRange(0.0, 100.0)
        self._spin_move.setDecimals(3)
        self._spin_move.setValue(move_tol)
        self._spin_rot = QDoubleSpinBox()
        self._spin_rot.setRange(0.0, 180.0)
        self._spin_rot.setDecimals(2)
        self._spin_rot.setValue(rot_tol)
        form.addRow(tr("Move tol (mm):"), self._spin_move)
        form.addRow(tr("Rotation tol (°):"), self._spin_rot)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText(tr("Compare"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open New PickPlace File"), "", "Excel Files (*.xlsx)")
        if file_path:
            self._file_path = file_path
            self._file_label.setText(file_path)
            self._mapping_label.setText("")
            self._data = None

    def _on_accept(self) -> None:
        if not self._file_path:
            return
        try:
            headers = self._reader.read_headers(self._file_path)
        except (ValueError, FileNotFoundError) as e:
            self._mapping_label.setText(str(e))
            return
        mapping = dict(STANDARD_MAPPING)
        required = list(STANDARD_REQUIRED)
        if not all(h in headers for h in STANDARD_MAPPING.values()):
            dialog = ColumnMappingDialog(self._file_path, headers, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            mapping = dialog.column_mapping
            required = dialog.required_fields
            self._mapping_label.setText(tr("Custom column mapping applied."))
        try:
            self._data = self._reader.read_with_mapping(
                self._file_path, mapping, required=required)
        except (ValueError, FileNotFoundError) as e:
            self._mapping_label.setText(str(e))
            return
        self.accept()

    @property
    def data(self) -> Optional[PickPlaceData]:
        return self._data

    @property
    def tolerances(self) -> Tuple[float, float]:
        return self._spin_move.value(), self._spin_rot.value()


class EcoResultDialog(QDialog):
    """Modeless ECO result browser: filter groups, locate rows, apply."""

    locate_requested = Signal(str)
    export_requested = Signal()
    apply_requested = Signal()

    def __init__(self, diff: EcoDiff, old_count: int, new_count: int,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._diff = diff
        self.setWindowTitle(tr("ECO Result"))
        self.resize(760, 480)

        layout = QVBoxLayout(self)
        a, r, m, p = diff.counts
        layout.addWidget(QLabel(
            tr("Old {old} ({old_u} codes) → New {new} ({new_u} codes): "
               "+{a} added · −{r} removed · ~{m} moved · ⇄{p} MPN · "
               "⧉{d} duplicated",
               old=old_count, old_u=diff.old_unique,
               new=new_count, new_u=diff.new_unique,
               a=a, r=r, m=m, p=p, d=diff.duplicate_count)))

        btn_row = QHBoxLayout()
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._btns = {}
        for key, label in (("added", tr("Added")),
                           ("removed", tr("Removed")),
                           ("moved", tr("Moved")),
                           ("mpn", tr("MPN changed")),
                           ("dup", tr("Duplicates"))):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(32)
            self._group.addButton(btn)
            self._btns[key] = btn
            btn_row.addWidget(btn)
            btn.clicked.connect(lambda _=False, k=key: self._show_group(k))
        layout.addLayout(btn_row)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(
            [tr("Designator"), tr("Old"), tr("New"), tr("Change")])
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.cellClicked.connect(self._on_cell_clicked)
        layout.addWidget(self._table, 1)

        action_row = QHBoxLayout()
        self._btn_export = QPushButton(tr("Export ECO Report..."))
        self._btn_export.clicked.connect(self.export_requested.emit)
        self._btn_apply = QPushButton(tr("Apply to current session"))
        self._btn_apply.setMinimumHeight(36)
        self._btn_apply.clicked.connect(self.apply_requested.emit)
        self._btn_close = QPushButton(tr("Close"))
        self._btn_close.clicked.connect(self.close)
        action_row.addWidget(self._btn_export)
        action_row.addStretch(1)
        action_row.addWidget(self._btn_close)
        action_row.addWidget(self._btn_apply)
        layout.addLayout(action_row)

        self._rows: List[Tuple[str, str]] = []
        groups = {"added": diff.added, "removed": diff.removed,
                  "moved": diff.moved, "mpn": diff.mpn_changed,
                  "dup": diff.old_duplicates + diff.new_duplicates}
        first = next((k for k in ("added", "removed", "moved", "mpn", "dup")
                      if groups[k]), "added")
        self._btns[first].setChecked(True)
        self._show_group(first)

    def _show_group(self, key: str) -> None:
        diff = self._diff
        rows: List[Tuple[str, str, str, str]] = []
        if key == "added":
            rows = [(a.designator, "-", f"{_fmt(a.x)}, {_fmt(a.y)} / {_fmt(a.rotation)}"
                     + (f" · {a.mpn}" if a.mpn else ""), tr("+new")) for a in diff.added]
        elif key == "removed":
            rows = [(x.designator, f"{_fmt(x.x)}, {_fmt(x.y)} / {_fmt(x.rotation)}",
                     "-", tr("−gone")) for x in diff.removed]
        elif key == "moved":
            rows = [(v.designator, f"{_fmt(v.old_x)}, {_fmt(v.old_y)} / {_fmt(v.old_rotation)}",
                     f"{_fmt(v.new_x)}, {_fmt(v.new_y)} / {_fmt(v.new_rotation)}",
                     f"ΔX{v.dx:+g} ΔY{v.dy:+g} ΔR{v.drot:+g}°") for v in diff.moved]
        elif key == "dup":
            rows = [(d.designator, tr("Old") if d.side == "old" else tr("New"),
                     f"×{d.count}", tr("duplicated")) for d in
                    (diff.old_duplicates + diff.new_duplicates)]
        else:
            rows = [(c.designator, c.old_mpn, c.new_mpn, "MPN") for c in diff.mpn_changed]
        self._rows = [(r[0], key) for r in rows]
        self._table.clearContents()
        self._table.setRowCount(len(rows))
        for i, (des, old, new, delta) in enumerate(rows):
            for j, val in enumerate((des, old, new, delta)):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._table.setItem(i, j, item)
        self._table.resizeRowsToContents()

    def _on_cell_clicked(self, row: int, _col: int) -> None:
        if 0 <= row < len(self._rows):
            des, group = self._rows[row]
            if group != "added":
                self.locate_requested.emit(des)
