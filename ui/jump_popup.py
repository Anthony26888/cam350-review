from typing import List, Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QFrame, QTableWidget, QTableWidgetItem, QHeaderView,
    QLineEdit, QDoubleSpinBox, QTextEdit, QScrollArea, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap, QResizeEvent

from models.review import ReviewRecord
from utils.path_utils import resource_path


class _FitWidthLabel(QLabel):
    def __init__(self, pixmap: QPixmap, tooltip: str, parent=None):
        super().__init__(parent)
        self._source = pixmap
        self.setToolTip(tooltip)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMaximumHeight(240)
        self._update_pixmap()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._update_pixmap()

    def _update_pixmap(self) -> None:
        width = self.width()
        if width <= 0 or self._source.isNull():
            return
        max_h = self.maximumHeight()
        self.setPixmap(
            self._source.scaled(
                width, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

class JumpPopup(QWidget):
    jump_requested = Signal(int)
    ok_requested = Signal(int)
    save_requested = Signal(int, float, float, float, str)
    delete_requested = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[ReviewRecord] = []
        self._filtered: List[int] = []
        self._current_index: int = 0

        self.setWindowTitle("Component Info")
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowMinimizeButtonHint | Qt.WindowCloseButtonHint | Qt.CustomizeWindowHint)
        self.setMinimumWidth(520)

        self.setStyleSheet("""
            QLabel#title {
                font-weight: bold;
                color: #0D9488;
                padding: 4px;
            }
            QLabel#field {
                font-weight: bold;
                color: #0F172A;
            }
            QLabel#value {
                color: #334155;
            }
            QPushButton#jump {
                background-color: #0D9488;
                color: white;
                font-weight: bold;
            }
            QPushButton#jump:hover {
                background-color: #0F766E;
            }
            QPushButton#ok {
                background-color: #16A34A;
                color: white;
            }
            QPushButton#ok:hover {
                background-color: #15803D;
            }
            QPushButton#save {
                background-color: #F59E0B;
                color: white;
            }
            QPushButton#save:hover {
                background-color: #D97706;
            }
            QPushButton#nav {
                background-color: #FFFFFF;
                border: 1px solid #E2E8F0;
                font-weight: bold;
            }
            QPushButton#nav:hover {
                background-color: #F1F5F9;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # Title
        title_layout = QHBoxLayout()
        self._lbl_title = QLabel("Component Info")
        self._lbl_title.setObjectName("title")
        title_layout.addWidget(self._lbl_title)
        title_layout.addStretch()

        self._btn_prev = QPushButton("◀ Prev")
        self._btn_prev.setObjectName("nav")
        self._btn_prev.clicked.connect(self._on_prev)
        self._btn_next = QPushButton("Next ▶")
        self._btn_next.setObjectName("nav")
        self._btn_next.clicked.connect(self._on_next)
        title_layout.addWidget(self._btn_prev)
        title_layout.addWidget(self._btn_next)
        layout.addLayout(title_layout)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)

        # Info form
        form = QFormLayout()
        form.setSpacing(2)

        self._lbl_des = QLabel("")
        self._lbl_des.setObjectName("value")
        lbl_des_title = QLabel("Designator:")
        lbl_des_title.setObjectName("field")
        form.addRow(lbl_des_title, self._lbl_des)

        self._lbl_mpn = QLabel("")
        self._lbl_mpn.setObjectName("value")
        lbl_mpn_title = QLabel("MPN:")
        lbl_mpn_title.setObjectName("field")
        form.addRow(lbl_mpn_title, self._lbl_mpn)

        self._lbl_layer = QLabel("")
        self._lbl_layer.setObjectName("value")
        lbl_layer_title = QLabel("Layer:")
        lbl_layer_title.setObjectName("field")
        form.addRow(lbl_layer_title, self._lbl_layer)

        self._lbl_old_xy = QLabel("")
        self._lbl_old_xy.setObjectName("value")
        lbl_old_title = QLabel("Old X/Y:")
        lbl_old_title.setObjectName("field")
        form.addRow(lbl_old_title, self._lbl_old_xy)

        self._lbl_old_rot = QLabel("")
        self._lbl_old_rot.setObjectName("value")
        lbl_old_rot_title = QLabel("Old Rot:")
        lbl_old_rot_title.setObjectName("field")
        form.addRow(lbl_old_rot_title, self._lbl_old_rot)

        self._spin_new_x = QDoubleSpinBox()
        self._spin_new_x.setRange(-999999.0, 999999.0)
        self._spin_new_x.setDecimals(4)
        self._spin_new_x.setStyleSheet("color: #0D9488; font-weight: bold;")

        self._spin_new_y = QDoubleSpinBox()
        self._spin_new_y.setRange(-999999.0, 999999.0)
        self._spin_new_y.setDecimals(4)
        self._spin_new_y.setStyleSheet("color: #0D9488; font-weight: bold;")

        new_xy_layout = QHBoxLayout()
        new_xy_layout.setSpacing(2)
        new_xy_layout.addWidget(QLabel("X:"))
        new_xy_layout.addWidget(self._spin_new_x, 1)
        new_xy_layout.addWidget(QLabel("Y:"))
        new_xy_layout.addWidget(self._spin_new_y, 1)

        lbl_new_title = QLabel("New X/Y:")
        lbl_new_title.setObjectName("field")
        form.addRow(lbl_new_title, new_xy_layout)

        self._spin_new_rot = QDoubleSpinBox()
        self._spin_new_rot.setRange(-999999.0, 999999.0)
        self._spin_new_rot.setDecimals(4)
        self._spin_new_rot.setSuffix("°")
        self._spin_new_rot.setStyleSheet("color: #0D9488; font-weight: bold;")

        lbl_new_rot_title = QLabel("New Rot:")
        lbl_new_rot_title.setObjectName("field")
        form.addRow(lbl_new_rot_title, self._spin_new_rot)

        # Rotation reference image
        rot_guide_box = QVBoxLayout()
        rot_guide_caption = QLabel("Rotation Guide")
        rot_guide_caption.setObjectName("field")
        rot_guide_box.addWidget(rot_guide_caption)
        rot_guide_box.addWidget(self._rotation_image("rotation-guide.png", "Rotation guide"))
        form.addRow(rot_guide_box)

        self._remark = QTextEdit()
        self._remark.setMaximumHeight(60)
        self._remark.setPlaceholderText("Remark...")
        lbl_remark_title = QLabel("Remark:")
        lbl_remark_title.setObjectName("field")
        form.addRow(lbl_remark_title, self._remark)

        self._lbl_status = QLabel("")
        self._lbl_status.setObjectName("value")
        lbl_status_title = QLabel("Status:")
        lbl_status_title.setObjectName("field")
        form.addRow(lbl_status_title, self._lbl_status)

        layout.addLayout(form)

        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line2)

        # Action buttons
        self._btn_jump = QPushButton("Jump to CAM350")
        self._btn_jump.setObjectName("jump")
        self._btn_jump.clicked.connect(lambda: self.jump_requested.emit(self._current_index))

        self._btn_ok = QPushButton("OK")
        self._btn_ok.setObjectName("ok")
        self._btn_ok.clicked.connect(lambda: self.ok_requested.emit(self._current_index))

        self._btn_save = QPushButton("Save")
        self._btn_save.setObjectName("save")
        self._btn_save.clicked.connect(self._on_save)

        self._btn_delete = QPushButton("Delete")
        self._btn_delete.setStyleSheet("background-color: #DC2626; color: white;")
        self._btn_delete.clicked.connect(lambda: self.delete_requested.emit(self._current_index))

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(4)
        btn_layout.addWidget(self._btn_jump)
        btn_layout.addWidget(self._btn_ok)

        split_layout = QHBoxLayout()
        split_layout.setSpacing(4)
        split_layout.addWidget(self._btn_save, 1)
        split_layout.addWidget(self._btn_delete, 1)
        btn_layout.addLayout(split_layout)

        layout.addLayout(btn_layout)

        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line3)

        # Search & Mini table
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Search component...")
        self._search_input.textChanged.connect(self._on_search)
        layout.addWidget(self._search_input)

        self._mini_table = QTableWidget()
        self._mini_table.setColumnCount(3)
        self._mini_table.setHorizontalHeaderLabels(["No", "Designator", "Status"])
        self._mini_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._mini_table.setSelectionMode(QTableWidget.SingleSelection)
        self._mini_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._mini_table.verticalHeader().setVisible(False)
        self._mini_table.horizontalHeader().setStretchLastSection(True)
        self._mini_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._mini_table.setAlternatingRowColors(True)
        self._mini_table.cellDoubleClicked.connect(self._on_table_click)
        layout.addWidget(self._mini_table, 1)

    def _rotation_image(self, filename: str, tooltip: str) -> QLabel:
        pixmap = QPixmap(resource_path(f"assets/{filename}"))
        if pixmap.isNull():
            label = QLabel()
            label.setAlignment(Qt.AlignCenter)
            label.setToolTip(tooltip)
            label.setText(tooltip)
            return label
        return _FitWidthLabel(pixmap, tooltip)

    def set_records(self, records: List[ReviewRecord], current_index: int) -> None:
        self._records = records
        self._current_index = current_index
        self._search_input.clear()
        self._apply_filter()
        self._update_display()

    def refresh_row(self, index: int) -> None:
        if index < 0 or index >= len(self._records):
            return
        if index not in self._filtered:
            return
        row = self._filtered.index(index)
        rec = self._records[index]
        des_item = self._mini_table.item(row, 1)
        status_item = self._mini_table.item(row, 2)
        if des_item and status_item:
            status_item.setText(rec.status or "Pending")
            status_colors = {
                "Pending": QColor(255, 255, 255),
                "OK": QColor(200, 255, 200),
                "Edited": QColor(255, 200, 200),
                "Aligned": QColor(255, 255, 255),
            }
            bg = status_colors.get(rec.status)
            des_item.setBackground(bg)
            status_item.setBackground(bg)

    def navigate_to(self, index: int) -> None:
        if 0 <= index < len(self._records):
            self._current_index = index
            self._update_display()
            if index in self._filtered:
                self._mini_table.selectRow(self._filtered.index(index))

    def _on_save(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        new_x = self._spin_new_x.value()
        new_y = self._spin_new_y.value()
        new_rot = self._spin_new_rot.value()
        remark = self._remark.toPlainText().strip()
        self.save_requested.emit(self._current_index, new_x, new_y, new_rot, remark)

    def _update_display(self) -> None:
        if not self._records or self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        total = len(self._records)

        self._lbl_title.setText(f"Component {self._current_index + 1}/{total} — {record.designator}")
        self._lbl_des.setText(record.designator)
        self._lbl_mpn.setText(record.mpn or "-")
        self._lbl_layer.setText(record.layer or "-")

        self._lbl_old_xy.setText(f"({record.old_x:.4f}, {record.old_y:.4f})")
        self._lbl_old_rot.setText(f"{record.old_rotation:.2f}°" if record.old_rotation is not None else "-")

        nx = record.new_x if record.new_x is not None else record.old_x
        ny = record.new_y if record.new_y is not None else record.old_y
        self._spin_new_x.setValue(nx)
        self._spin_new_y.setValue(ny)

        nr = record.new_rotation if record.new_rotation is not None else record.old_rotation
        self._spin_new_rot.setValue(nr)

        self._remark.setText(record.remark or "")

        self._lbl_status.setText(record.status or "Pending")
        status_colors = {
            "Pending": "#9E9E9E",
            "OK": "#4CAF50",
            "Edited": "#FF9800",
            "Aligned": "#9E9E9E",
        }
        self._lbl_status.setStyleSheet(
            f"color: {status_colors.get(record.status, '#333')}; font-weight: bold;"
        )

        self._mini_table.selectRow(self._current_index)
        self._btn_prev.setEnabled(self._current_index > 0)
        self._btn_next.setEnabled(self._current_index < total - 1)

    def _apply_filter(self) -> None:
        search_text = self._search_input.text().strip().lower()
        if search_text:
            self._filtered = [
                i for i, rec in enumerate(self._records)
                if search_text in rec.designator.lower()
                or search_text in (rec.mpn or "").lower()
            ]
        else:
            self._filtered = list(range(len(self._records)))
        self._refresh_table()

    def _on_search(self) -> None:
        self._apply_filter()

    def _refresh_table(self) -> None:
        self._mini_table.blockSignals(True)
        self._mini_table.setRowCount(len(self._filtered))
        status_colors = {
            "Pending": QColor(255, 255, 255),
            "OK": QColor(200, 255, 200),
            "Edited": QColor(255, 200, 200),
            "Aligned": QColor(255, 255, 255),
        }
        for row, idx in enumerate(self._filtered):
            rec = self._records[idx]
            no_item = QTableWidgetItem(str(idx + 1))
            no_item.setFlags(no_item.flags() & ~Qt.ItemIsEditable)
            no_item.setData(Qt.UserRole, idx)

            des_item = QTableWidgetItem(rec.designator)
            des_item.setFlags(des_item.flags() & ~Qt.ItemIsEditable)
            des_item.setData(Qt.UserRole, idx)

            status_item = QTableWidgetItem(rec.status or "Pending")
            status_item.setFlags(status_item.flags() & ~Qt.ItemIsEditable)
            status_item.setData(Qt.UserRole, idx)

            bg = status_colors.get(rec.status)
            if bg:
                des_item.setBackground(bg)
                status_item.setBackground(bg)

            self._mini_table.setItem(row, 0, no_item)
            self._mini_table.setItem(row, 1, des_item)
            self._mini_table.setItem(row, 2, status_item)
        self._mini_table.blockSignals(False)

    def _on_table_click(self, row: int, _: int) -> None:
        if 0 <= row < len(self._filtered):
            self._current_index = self._filtered[row]
            self._update_display()
            self.jump_requested.emit(self._current_index)

    def _on_prev(self) -> None:
        if self._current_index > 0:
            self._current_index -= 1
            self._update_display()
            self.jump_requested.emit(self._current_index)

    def _on_next(self) -> None:
        if self._current_index < len(self._records) - 1:
            self._current_index += 1
            self._update_display()
            self.jump_requested.emit(self._current_index)

    def show_at(self, records: List[ReviewRecord], index: int) -> None:
        self.set_records(records, index)
        self.show()
        self.raise_()
        self.adjustSize()
        self.setMinimumWidth(self.width())
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            self.resize(min(self.width(), screen.width()), min(self.height(), screen.height()))
            self.move(screen.center() - self.rect().center())
