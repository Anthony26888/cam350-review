from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFormLayout, QFrame, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Signal, Qt

from models.review import ReviewRecord
from ui.i18n import tr

try:
    from models.history import HistoryEntry
except Exception:  # pragma: no cover - for minimal test envs
    HistoryEntry = object  # type: ignore


class ReviewPanel(QWidget):
    # Kept for backward compatibility (shortcuts in MainWindow still use
    # the same slots). No buttons emit them anymore since Actions was removed.
    previous_requested = Signal()
    next_requested = Signal()
    jump_requested = Signal()
    ok_requested = Signal()
    edit_requested = Signal()
    datasheet_requested = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_index: int = -1
        self._total: int = 0

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)

        self._build_stats_section()
        self._build_info_section()
        self._layout.addSpacing(10)
        self._build_history_section()

    def _build_stats_section(self) -> None:
        stats_row = QHBoxLayout()
        stats_row.setSpacing(8)
        self._stat_labels: Dict[str, QLabel] = {}
        for caption, obj in (
            (tr("Total"), "stat_total"),
            (tr("Pending"), "stat_pending"),
            (tr("OK"), "stat_ok"),
            (tr("Edit"), "stat_edit"),
            (tr("Aligned"), "stat_align"),
        ):
            card = QFrame()
            card.setObjectName("stat_card")
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(6, 6, 6, 6)
            card_layout.setSpacing(2)
            cap = QLabel(caption)
            cap.setObjectName("stat_card_caption")
            cap.setAlignment(Qt.AlignCenter)
            value = QLabel("0")
            value.setObjectName(obj)
            value.setAlignment(Qt.AlignCenter)
            card_layout.addWidget(cap)
            card_layout.addWidget(value)
            self._stat_labels[obj] = value
            stats_row.addWidget(card, 1)
        self._layout.addLayout(stats_row)

    def update_stats(
        self, total: int, ok: int, edit: int, pending: int, aligned: int
    ) -> None:
        values = {
            "stat_total": total,
            "stat_pending": pending,
            "stat_ok": ok,
            "stat_edit": edit,
            "stat_align": aligned,
        }
        for obj, v in values.items():
            label = self._stat_labels.get(obj)
            if label is not None:
                label.setText(str(v))

    def _build_info_section(self) -> None:
        info_group = QGroupBox(tr("Component Information"))
        info_layout = QFormLayout(info_group)

        selectable = Qt.TextSelectableByMouse
        self._lbl_designator = QLabel("-")
        self._lbl_designator.setObjectName("title")
        self._lbl_designator.setTextInteractionFlags(selectable)
        self._lbl_mpn = QLabel("-")
        self._lbl_mpn.setTextInteractionFlags(selectable)
        self._lbl_layer = QLabel("-")
        self._lbl_layer.setTextInteractionFlags(selectable)
        self._lbl_old_x = QLabel("-")
        self._lbl_old_x.setTextInteractionFlags(selectable)
        self._lbl_old_y = QLabel("-")
        self._lbl_old_y.setTextInteractionFlags(selectable)
        self._lbl_old_rot = QLabel("-")
        self._lbl_old_rot.setTextInteractionFlags(selectable)
        self._lbl_new_x = QLabel("")
        self._lbl_new_x.setTextInteractionFlags(selectable)
        self._lbl_new_y = QLabel("")
        self._lbl_new_y.setTextInteractionFlags(selectable)
        self._lbl_new_rot = QLabel("")
        self._lbl_new_rot.setTextInteractionFlags(selectable)
        for lbl in (self._lbl_new_x, self._lbl_new_y, self._lbl_new_rot):
            lbl.setObjectName("newval")
        self._lbl_status = QLabel("-")
        self._lbl_status.setTextInteractionFlags(selectable)
        self._lbl_datasheet = QLabel("-")
        self._lbl_datasheet.setTextInteractionFlags(
            Qt.LinksAccessibleByMouse | Qt.TextSelectableByMouse
        )
        self._lbl_datasheet.setOpenExternalLinks(True)
        self._lbl_datasheet.setTextFormat(Qt.RichText)
        self._lbl_remark = QLabel("-")
        self._lbl_remark.setWordWrap(True)
        self._lbl_remark.setTextInteractionFlags(selectable)
        self._lbl_progress = QLabel("-")
        self._lbl_progress.setTextInteractionFlags(selectable)

        info_layout.addRow(tr("Designator:"), self._lbl_designator)
        info_layout.addRow(tr("MPN:"), self._lbl_mpn)
        info_layout.addRow(tr("Layer:"), self._lbl_layer)
        info_layout.addRow(tr("Original X:"), self._lbl_old_x)
        info_layout.addRow(tr("Original Y:"), self._lbl_old_y)
        info_layout.addRow(tr("Original Rotation:"), self._lbl_old_rot)
        info_layout.addRow(tr("New X:"), self._lbl_new_x)
        info_layout.addRow(tr("New Y:"), self._lbl_new_y)
        info_layout.addRow(tr("New Rotation:"), self._lbl_new_rot)
        info_layout.addRow(tr("Status:"), self._lbl_status)
        info_layout.addRow(tr("Datasheet:"), self._lbl_datasheet)
        info_layout.addRow(tr("Remark:"), self._lbl_remark)
        info_layout.addRow(tr("Progress:"), self._lbl_progress)

        self._layout.addWidget(info_group)

    def _build_history_section(self) -> None:
        hist_group = QGroupBox(tr("History"))
        hist_layout = QVBoxLayout(hist_group)

        self._lbl_hist_title = QLabel("-")
        self._lbl_hist_title.setObjectName("title")
        self._lbl_hist_title.setTextInteractionFlags(Qt.TextSelectableByMouse)
        hist_layout.addWidget(self._lbl_hist_title)

        self._history_table = QTableWidget(0, 3)
        self._history_table.setHorizontalHeaderLabels(
            [tr("Time"), tr("Step"), tr("Changes")]
        )
        self._history_table.setAlternatingRowColors(True)
        self._history_table.setWordWrap(True)
        self._history_table.setTextElideMode(Qt.ElideNone)
        self._history_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._history_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._history_table.verticalHeader().setVisible(False)
        self._history_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        header = self._history_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        self._history_table.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Expanding
        )
        self._history_table.setMinimumHeight(180)
        hist_layout.addWidget(self._history_table, 1)

        self._layout.addWidget(hist_group, 1)

    def refresh_icons(self) -> None:
        # No action buttons anymore; kept for compatibility.
        return

    def set_datasheet(self, url: str) -> None:
        if url and url != "Searching...":
            self._lbl_datasheet.setText(tr('<a href="{url}">View Datasheet</a>', url=url))
        else:
            self._lbl_datasheet.setText(url if url else tr("Not found"))

    def set_datasheet_searching(self, searching: bool) -> None:
        # No button to disable anymore; kept for compatibility.
        return

    def display_record(self, record: ReviewRecord, index: int, total: int, progress_text: str = "") -> None:
        self._current_index = index
        self._total = total

        self._lbl_designator.setText(record.designator)
        self._lbl_mpn.setText(record.mpn)
        self._lbl_layer.setText(record.layer)
        self._lbl_old_x.setText(_fmt(record.old_x))
        self._lbl_old_y.setText(_fmt(record.old_y))
        self._lbl_old_rot.setText(_fmt(record.old_rotation))

        changed_x = record.new_x is not None and record.new_x != record.old_x
        changed_y = record.new_y is not None and record.new_y != record.old_y
        changed_rot = record.new_rotation is not None and record.new_rotation != record.old_rotation

        self._lbl_new_x.setText(_fmt(record.new_x) if changed_x else "")
        self._lbl_new_y.setText(_fmt(record.new_y) if changed_y else "")
        self._lbl_new_rot.setText(_fmt(record.new_rotation) if changed_rot else "")

        self._lbl_status.setText(tr(record.status))

        self._lbl_remark.setText(record.remark if record.remark else "-")

        if record.datasheet:
            self._lbl_datasheet.setText(tr('<a href="{url}">View Datasheet</a>', url=record.datasheet))
        else:
            self._lbl_datasheet.setText("-")

        if progress_text:
            self._lbl_progress.setText(progress_text)
        else:
            ok_count = sum(1 for r in self._get_records() if r.status == "OK")
            edit_count = sum(1 for r in self._get_records() if r.status == "Edited")
            t = max(len(self._get_records()), 1)
            reviewed = ok_count + edit_count
            pct = int(reviewed / t * 100)
            self._lbl_progress.setText(
                tr("{reviewed}/{total} ({pct}%) - OK: {ok} | Edited: {edited}",
                   reviewed=reviewed, total=t, pct=pct, ok=ok_count, edited=edit_count)
            )

        self._lbl_hist_title.setText(record.designator)

    def reload_history(self, entries: List) -> None:
        table = self._history_table
        try:
            table.clearSpans()
        except Exception:
            pass
        table.clearContents()
        if not entries:
            table.setRowCount(1)
            item = QTableWidgetItem(tr("No history"))
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            table.setItem(0, 0, item)
            table.setSpan(0, 0, 1, 3)
            return
        table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            time_item = QTableWidgetItem(history_time_short(e))
            step_item = QTableWidgetItem(getattr(e, "action", "") or "")
            change_item = QTableWidgetItem(history_change_text(e))
            for item in (time_item, step_item, change_item):
                item.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, time_item)
            table.setItem(row, 1, step_item)
            table.setItem(row, 2, change_item)
        table.resizeRowsToContents()

    def set_record_list(self, records: List[ReviewRecord]) -> None:
        self._record_list = records

    def clear_record(self) -> None:
        self._current_index = -1
        self._total = 0
        self._lbl_designator.setText("-")
        self._lbl_mpn.setText("-")
        self._lbl_layer.setText("-")
        self._lbl_old_x.setText("-")
        self._lbl_old_y.setText("-")
        self._lbl_old_rot.setText("-")
        self._lbl_new_x.setText("")
        self._lbl_new_y.setText("")
        self._lbl_new_rot.setText("")
        self._lbl_status.setText("-")
        self._lbl_remark.setText("-")
        self._lbl_datasheet.setText("-")
        self._lbl_progress.setText("-")
        self._lbl_hist_title.setText("-")
        table = self._history_table
        try:
            table.clearSpans()
        except Exception:
            pass
        table.clearContents()
        table.setRowCount(1)
        item = QTableWidgetItem(tr("No history"))
        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
        table.setItem(0, 0, item)
        table.setSpan(0, 0, 1, 3)

    def _get_records(self) -> List[ReviewRecord]:
        return getattr(self, "_record_list", [])


def format_history_entry(e) -> str:
    """One line: [time] action | what changed (old->new). Kept for compat/tests."""
    when = getattr(e, "created_at", "") or ""
    action = getattr(e, "action", "") or ""
    changes = history_change_text(e)
    head = f"{when} | {action}".strip(" |")
    return f"{head} | {changes}" if head else changes


def history_time_short(e) -> str:
    when = (getattr(e, "created_at", "") or "").strip()
    if " " in when:
        return when.split(" ")[-1]
    return when


def history_change_text(e) -> str:
    """Only the 'what changed' part for the Changes column."""
    parts: List[str] = []
    ox, nx = getattr(e, "old_x", None), getattr(e, "new_x", None)
    oy, ny = getattr(e, "old_y", None), getattr(e, "new_y", None)
    orot, nrot = getattr(e, "old_rotation", None), getattr(e, "new_rotation", None)
    parts.append(_fmt_change("X", ox, nx))
    parts.append(_fmt_change("Y", oy, ny))
    parts.append(_fmt_change("Rot", orot, nrot, suffix="°"))
    parts = [p for p in parts if p]
    remark = (getattr(e, "remark", "") or "").strip()
    if remark:
        parts.append(f"Remark: {remark}")
    if not parts:
        return tr("No value change")
    return ", ".join(parts)


def _fmt_change(name: str, old, new, suffix: str = "") -> str:
    if not _changed(old, new):
        return ""
    if old is None and new is not None:
        return f"{name}: {_fmt(new)}{suffix}"
    if new is None and old is not None:
        return f"{name}: {_fmt(old)}{suffix} -> -"
    return f"{name}: {_fmt(old)}{suffix}->{_fmt(new)}{suffix}"


def _changed(a, b) -> bool:
    if a is None and b is None:
        return False
    if a is None or b is None:
        return True
    try:
        return abs(float(a) - float(b)) >= 1e-9
    except (TypeError, ValueError):
        return a != b


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}"
