from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QGroupBox, QFormLayout, QFrame, QSizePolicy,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QFont

from models.review import ReviewRecord
from ui.i18n import tr

try:
    from models.history import HistoryEntry
except Exception:  # pragma: no cover - for minimal test envs
    HistoryEntry = object  # type: ignore


def share_percents(top: int, bottom: int, missing: int, total: int):
    """Integer percents summing to 100 (remainder goes to the largest part)."""
    counts = [max(int(top), 0), max(int(bottom), 0), max(int(missing), 0)]
    total = max(int(total), sum(counts))
    if total <= 0:
        return (0, 0, 0)
    raw = [c * 100.0 / total for c in counts]
    out = [int(v) for v in raw]
    rest = 100 - sum(out)
    order = sorted(range(3), key=lambda i: (raw[i], -i), reverse=True)
    for i in order:
        if rest <= 0:
            break
        if counts[i] > 0:
            out[i] += 1
            rest -= 1
    return tuple(out)


def share_legend_text(top: int, bottom: int, missing: int, total: int) -> str:
    t, b, m = share_percents(top, bottom, missing, total)
    return f"Top {t}% · Bottom {b}% · Missing {m}%"


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
        self._build_bom_summary_section()
        self._build_info_stack()
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
        self._info_group = QGroupBox(tr("Component Information"))
        info_layout = QFormLayout(self._info_group)

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

    def _build_info_stack(self) -> None:
        # Information and BOM Summary share one slot so both cards always
        # have identical geometry; only one page is visible at a time.
        self._info_stack = QStackedWidget()
        self._info_stack.addWidget(self._info_group)
        self._info_stack.addWidget(self._bom_summary_group)
        self._info_stack.setCurrentIndex(0)
        self._layout.addWidget(self._info_stack)

    def show_info_card(self) -> None:
        self._info_stack.setCurrentIndex(0)

    def show_bom_summary_card(self) -> None:
        self._info_stack.setCurrentIndex(1)

    def _build_bom_summary_section(self) -> None:
        self._bom_summary_group = QGroupBox(tr("BOM Summary"))
        form = QFormLayout(self._bom_summary_group)
        selectable = Qt.TextSelectableByMouse
        self._lbl_bom_mpn = QLabel("-")
        bold = QFont()
        bold.setBold(True)
        self._lbl_bom_mpn.setFont(bold)
        self._lbl_bom_mpn.setWordWrap(True)
        self._lbl_bom_mpn.setTextInteractionFlags(selectable)
        self._lbl_bom_qty = QLabel("-")
        self._lbl_bom_qty.setTextInteractionFlags(selectable)
        self._lbl_bom_top_cap = QLabel(tr("Top ({n} pcs):", n=0))
        self._lbl_bom_top = QLabel("-")
        self._lbl_bom_top.setWordWrap(True)
        self._lbl_bom_top.setTextInteractionFlags(selectable)
        self._lbl_bom_bottom_cap = QLabel(tr("Bottom ({n} pcs):", n=0))
        self._lbl_bom_bottom = QLabel("-")
        self._lbl_bom_bottom.setWordWrap(True)
        self._lbl_bom_bottom.setTextFormat(Qt.RichText)
        self._lbl_bom_bottom.setTextInteractionFlags(selectable)
        self._lbl_bom_missing_cap = QLabel(tr("Missing ({n} pcs):", n=0))
        self._lbl_bom_missing = QLabel("-")
        self._lbl_bom_missing.setWordWrap(True)
        self._lbl_bom_missing.setTextInteractionFlags(selectable)
        self._lbl_bom_share = QLabel("-")
        self._lbl_bom_share.setWordWrap(True)
        self._lbl_bom_share.setTextInteractionFlags(selectable)
        form.addRow(tr("MPN:"), self._lbl_bom_mpn)
        form.addRow(tr("Qty:"), self._lbl_bom_qty)
        form.addRow(self._lbl_bom_top_cap, self._lbl_bom_top)
        form.addRow(self._lbl_bom_bottom_cap, self._lbl_bom_bottom)
        form.addRow(self._lbl_bom_missing_cap, self._lbl_bom_missing)
        form.addRow(tr("Share:"), self._lbl_bom_share)

    def display_bom_summary(self, summary) -> None:
        self._lbl_bom_mpn.setText(summary.mpn if summary.mpn else "-")
        self._lbl_bom_qty.setText(f"{summary.quantity} pcs")
        self._lbl_bom_top_cap.setText(tr("Top ({n} pcs):", n=len(summary.top)))
        self._lbl_bom_top.setText(
            ", ".join(summary.top) if summary.top else "-")
        self._lbl_bom_bottom_cap.setText(
            tr("Bottom ({n} pcs):", n=len(summary.bottom)))
        bot_names = ", ".join(
            f'<span style="color:#DC2626;">{d}</span>'
            for d in summary.bottom) if summary.bottom else "-"
        self._lbl_bom_bottom.setText(bot_names)
        miss = list(summary.missing) + [
            f"{d} (mixed)" for d in summary.mixed_layers]
        self._lbl_bom_missing_cap.setText(
            tr("Missing ({n} pcs):", n=len(miss)))
        self._lbl_bom_missing.setText(", ".join(miss) if miss else "-")
        self._lbl_bom_share.setText(share_legend_text(
            len(summary.top), len(summary.bottom), len(miss),
            len(summary.top) + len(summary.bottom) + len(miss)))
        self.show_bom_summary_card()

    def clear_bom_summary(self) -> None:
        self._lbl_bom_mpn.setText("-")
        self._lbl_bom_qty.setText("-")
        self._lbl_bom_top_cap.setText(tr("Top ({n} pcs):", n=0))
        self._lbl_bom_top.setText("-")
        self._lbl_bom_bottom_cap.setText(tr("Bottom ({n} pcs):", n=0))
        self._lbl_bom_bottom.setText("-")
        self._lbl_bom_missing_cap.setText(tr("Missing ({n} pcs):", n=0))
        self._lbl_bom_missing.setText("-")
        self._lbl_bom_share.setText("-")
        self.show_info_card()

    def set_history_title(self, text: str) -> None:
        self._lbl_hist_title.setText(text)

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
        self.clear_bom_summary()

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
        self.clear_bom_summary()
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
    mo, mn = (getattr(e, "mpn_old", "") or "").strip(), (getattr(e, "mpn_new", "") or "").strip()
    if mo or mn:
        if not mo and mn:
            parts.append(f"MPN: {mn}")
        elif mo and not mn:
            parts.append(f"MPN: {mo} -> -")
        elif mo != mn:
            parts.append(f"MPN: {mo}->{mn}")
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
