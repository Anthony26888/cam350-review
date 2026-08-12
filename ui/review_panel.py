from typing import Optional, List, Dict

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QFormLayout, QFrame, QSizePolicy, QStyle,
)
from PySide6.QtCore import Signal, Qt

from models.review import ReviewRecord
from ui.i18n import tr


class ReviewPanel(QWidget):
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
        self._build_nav_section()

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

    def _build_nav_section(self) -> None:
        nav_group = QGroupBox(tr("Actions"))
        nav_layout = QVBoxLayout(nav_group)

        btn_layout = QHBoxLayout()
        self._btn_prev = QPushButton(tr("Previous"))
        self._btn_prev.setMinimumHeight(40)
        self._btn_prev.setObjectName("action_btn")
        self._btn_prev.clicked.connect(self.previous_requested.emit)

        self._btn_next = QPushButton(tr("Next"))
        self._btn_next.setMinimumHeight(40)
        self._btn_next.setObjectName("action_btn")
        self._btn_next.clicked.connect(self.next_requested.emit)

        btn_layout.addWidget(self._btn_prev)
        btn_layout.addWidget(self._btn_next)
        nav_layout.addLayout(btn_layout)

        self._btn_jump = QPushButton(tr("Jump CAM350"))
        self._btn_jump.setMinimumHeight(40)
        self._btn_jump.setObjectName("action_btn")
        self._btn_jump.clicked.connect(self.jump_requested.emit)
        nav_layout.addWidget(self._btn_jump)

        self._btn_datasheet = QPushButton(tr("Search Datasheet"))
        self._btn_datasheet.setMinimumHeight(40)
        self._btn_datasheet.setObjectName("action_btn")
        self._btn_datasheet.clicked.connect(self._on_datasheet_clicked)
        nav_layout.addWidget(self._btn_datasheet)

        action_layout = QHBoxLayout()
        self._btn_ok = QPushButton(tr("OK (Space)"))
        self._btn_ok.setMinimumHeight(40)
        self._btn_ok.setObjectName("success")
        self._btn_ok.clicked.connect(self.ok_requested.emit)

        self._btn_edit = QPushButton(tr("Edit (Ctrl+E)"))
        self._btn_edit.setMinimumHeight(40)
        self._btn_edit.setObjectName("action_btn")
        self._btn_edit.clicked.connect(self.edit_requested.emit)

        action_layout.addWidget(self._btn_ok)
        action_layout.addWidget(self._btn_edit)
        nav_layout.addLayout(action_layout)

        self._layout.addWidget(nav_group)
        self.refresh_icons()

    def refresh_icons(self) -> None:
        spi = self.style().standardIcon
        self._btn_prev.setIcon(spi(QStyle.StandardPixmap.SP_ArrowBack))
        self._btn_next.setIcon(spi(QStyle.StandardPixmap.SP_ArrowForward))
        self._btn_jump.setIcon(spi(QStyle.StandardPixmap.SP_ArrowForward))
        self._btn_datasheet.setIcon(spi(QStyle.StandardPixmap.SP_DialogHelpButton))
        self._btn_ok.setIcon(spi(QStyle.StandardPixmap.SP_DialogApplyButton))
        self._btn_edit.setIcon(spi(QStyle.StandardPixmap.SP_FileDialogInfoView))

    def _on_datasheet_clicked(self) -> None:
        mpn = self._lbl_mpn.text()
        if mpn and mpn != "-":
            self.datasheet_requested.emit(mpn)

    def set_datasheet(self, url: str) -> None:
        if url and url != "Searching...":
            self._lbl_datasheet.setText(tr('<a href="{url}">View Datasheet</a>', url=url))
        else:
            self._lbl_datasheet.setText(url if url else tr("Not found"))

    def set_datasheet_searching(self, searching: bool) -> None:
        self._btn_datasheet.setEnabled(not searching)

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
        self._btn_datasheet.setEnabled(bool(record.mpn))

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

        self._btn_prev.setEnabled(index > 0)
        self._btn_next.setEnabled(index < total - 1)

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
        self._btn_datasheet.setEnabled(False)
        self._btn_prev.setEnabled(False)
        self._btn_next.setEnabled(False)

    def _get_records(self) -> List[ReviewRecord]:
        return getattr(self, "_record_list", [])


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}"
