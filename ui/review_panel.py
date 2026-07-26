from typing import Optional, List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGroupBox, QFormLayout, QFrame, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt

from models.review import ReviewRecord


class ReviewPanel(QWidget):
    previous_requested = Signal()
    next_requested = Signal()
    jump_requested = Signal()
    ok_requested = Signal()
    edit_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_index: int = -1
        self._total: int = 0

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(10, 10, 10, 10)

        self._build_info_section()
        self._layout.addSpacing(10)
        self._build_nav_section()

    def _build_info_section(self) -> None:
        info_group = QGroupBox("Component Information")
        info_layout = QFormLayout(info_group)

        selectable = Qt.TextSelectableByMouse
        self._lbl_designator = QLabel("-")
        self._lbl_designator.setStyleSheet("font-weight: bold; font-size: 14px;")
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
        self._lbl_status = QLabel("-")
        self._lbl_status.setTextInteractionFlags(selectable)
        self._lbl_progress = QLabel("-")
        self._lbl_progress.setTextInteractionFlags(selectable)

        info_layout.addRow("Designator:", self._lbl_designator)
        info_layout.addRow("MPN:", self._lbl_mpn)
        info_layout.addRow("Layer:", self._lbl_layer)
        info_layout.addRow("Original X:", self._lbl_old_x)
        info_layout.addRow("Original Y:", self._lbl_old_y)
        info_layout.addRow("Original Rotation:", self._lbl_old_rot)
        info_layout.addRow("New X:", self._lbl_new_x)
        info_layout.addRow("New Y:", self._lbl_new_y)
        info_layout.addRow("New Rotation:", self._lbl_new_rot)
        info_layout.addRow("Status:", self._lbl_status)
        info_layout.addRow("Progress:", self._lbl_progress)

        self._layout.addWidget(info_group)

    def _build_nav_section(self) -> None:
        nav_group = QGroupBox("Actions")
        nav_layout = QVBoxLayout(nav_group)

        btn_layout = QHBoxLayout()
        self._btn_prev = QPushButton("◀ Previous")
        self._btn_prev.setMinimumHeight(40)
        self._btn_prev.clicked.connect(self.previous_requested.emit)

        self._btn_next = QPushButton("Next ▶")
        self._btn_next.setMinimumHeight(40)
        self._btn_next.clicked.connect(self.next_requested.emit)

        btn_layout.addWidget(self._btn_prev)
        btn_layout.addWidget(self._btn_next)
        nav_layout.addLayout(btn_layout)

        self._btn_jump = QPushButton("🔍 Jump CAM350")
        self._btn_jump.setMinimumHeight(40)
        self._btn_jump.clicked.connect(self.jump_requested.emit)
        nav_layout.addWidget(self._btn_jump)

        action_layout = QHBoxLayout()
        self._btn_ok = QPushButton("✓ OK (Space)")
        self._btn_ok.setMinimumHeight(40)
        self._btn_ok.clicked.connect(self.ok_requested.emit)

        self._btn_edit = QPushButton("✎ Edit (Ctrl+E)")
        self._btn_edit.setMinimumHeight(40)
        self._btn_edit.clicked.connect(self.edit_requested.emit)

        action_layout.addWidget(self._btn_ok)
        action_layout.addWidget(self._btn_edit)
        nav_layout.addLayout(action_layout)

        self._layout.addWidget(nav_group)

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

        style_red = "color: #cc0000; font-weight: bold;"
        self._lbl_new_x.setText(_fmt(record.new_x) if changed_x else "")
        self._lbl_new_y.setText(_fmt(record.new_y) if changed_y else "")
        self._lbl_new_rot.setText(_fmt(record.new_rotation) if changed_rot else "")
        self._lbl_new_x.setStyleSheet(style_red if changed_x else "")
        self._lbl_new_y.setStyleSheet(style_red if changed_y else "")
        self._lbl_new_rot.setStyleSheet(style_red if changed_rot else "")

        self._lbl_status.setText(record.status)

        if progress_text:
            self._lbl_progress.setText(progress_text)
        else:
            ok_count = sum(1 for r in self._get_records() if r.status == "OK")
            edit_count = sum(1 for r in self._get_records() if r.status == "Edited")
            t = max(len(self._get_records()), 1)
            reviewed = ok_count + edit_count
            pct = int(reviewed / t * 100)
            self._lbl_progress.setText(f"{reviewed}/{t} ({pct}%) - OK: {ok_count} | Edited: {edit_count}")

        self._btn_prev.setEnabled(index > 0)
        self._btn_next.setEnabled(index < total - 1)

    def set_record_list(self, records: List[ReviewRecord]) -> None:
        self._record_list = records

    def _get_records(self) -> List[ReviewRecord]:
        return getattr(self, "_record_list", [])


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return ""
    if v == int(v):
        return str(int(v))
    return f"{v:.4f}"
