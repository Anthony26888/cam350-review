from typing import List, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QDialog, QDialogButtonBox, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton, QSpinBox,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from models.review import ReviewRecord
from services.gerber.panel_detector import detect_panel
from services.panelize_service import (
    PanelBlock, PanelConfig, PanelError, transform_point,
)
from ui.i18n import tr

_ROTATED_BG = "#E11D48"
_ROTATED_FG = "#FFFFFF"
_MAX_BLOCKS = 40


class PanelizeDialog(QDialog):
    """Collect explicit per-block origins and 180° flags, return a PanelConfig.

    Block 1 (index 0) is the base board; its origin is locked at (0, 0).
    Other blocks get absolute origins typed by hand, so no grid pitch or
    board size is needed. The dialog never mutates records; the caller
    applies the config through services.panelize_service.panelize_records().
    """

    def __init__(
        self,
        records: List[ReviewRecord],
        parent=None,
        config: Optional[PanelConfig] = None,
        gko_path: str = "",
    ) -> None:
        super().__init__(parent)
        self._records = list(records or [])
        self._gko_path = gko_path or ""
        self._config = config if config is not None else PanelConfig()
        self._syncing = False
        if not self._config.blocks:
            self._config.blocks = [PanelBlock(index=0, origin_x=0.0, origin_y=0.0)]
        self._config.blocks.sort(key=lambda b: b.index)
        self.panel_config: Optional[PanelConfig] = None
        self._block_buttons: List[QPushButton] = []

        self.setWindowTitle(tr("Panelize - Multiply Board Coordinates"))
        self.setMinimumWidth(640)
        self._build_ui()
        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._refresh_preview()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_boards_group())
        layout.addWidget(self._build_blocks_group())
        layout.addWidget(self._build_preview_group())

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText(tr("Apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _build_boards_group(self) -> QGroupBox:
        group = QGroupBox(tr("Boards"))
        layout = QVBoxLayout(group)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel(tr("Number of boards:")))
        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, _MAX_BLOCKS)
        self._spin_count.valueChanged.connect(self._on_count_changed)
        count_row.addWidget(self._spin_count)
        count_row.addWidget(QLabel(tr("Block 1 is the base board at (0, 0).")))
        count_row.addStretch(1)
        layout.addLayout(count_row)

        detect_row = QHBoxLayout()
        detect_btn = QPushButton(tr("Detect from GKO"))
        detect_btn.clicked.connect(self._detect_from_gko)
        detect_row.addWidget(detect_btn)
        detect_row.addWidget(QLabel(tr("Fill block origins from the GKO outline.")))
        detect_row.addStretch(1)
        layout.addLayout(detect_row)

        self._origins_table = QTableWidget(0, 3)
        self._origins_table.setHorizontalHeaderLabels([
            tr("Block"), tr("Origin X (mm)"), tr("Origin Y (mm)"),
        ])
        self._origins_table.verticalHeader().setVisible(False)
        self._origins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._origins_table.setMaximumHeight(180)
        self._origins_table.setEditTriggers(QTableWidget.AllEditTriggers)
        self._origins_table.cellChanged.connect(self._on_origin_edited)
        hint = QLabel(
            tr("Normal block: enter its bottom-left corner. "
               "Flipped (180°) block: enter its top-right corner.")
        )
        hint.setWordWrap(True)
        layout.addWidget(self._origins_table)
        layout.addWidget(hint)

        self._chk_rename = QCheckBox(
            tr("Rename designators (C1 \u2192 C1_2, C1_3, ...)")
        )
        self._chk_rename.setChecked(True)
        self._chk_rename.stateChanged.connect(self._on_rename_toggled)
        layout.addWidget(self._chk_rename)
        return group

    def _build_blocks_group(self) -> QGroupBox:
        group = QGroupBox(tr("Board Orientation"))
        layout = QVBoxLayout(group)
        hint = QLabel(tr("Click a board to flip it 180°."))
        layout.addWidget(hint)

        self._blocks_holder = QWidget()
        self._blocks_layout = QGridLayout(self._blocks_holder)
        self._blocks_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._blocks_holder)
        return group

    def _build_preview_group(self) -> QGroupBox:
        group = QGroupBox(tr("Preview"))
        layout = QVBoxLayout(group)
        self._label_result = QLabel()
        layout.addWidget(self._label_result)

        self._preview_table = QTableWidget(0, 5)
        self._preview_table.setHorizontalHeaderLabels([
            tr("Designator"), tr("Block"), tr("X"), tr("Y"), tr("Rotation"),
        ])
        self._preview_table.verticalHeader().setVisible(False)
        self._preview_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self._preview_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._preview_table.setMaximumHeight(180)
        layout.addWidget(self._preview_table)
        return group

    # ------------------------------------------------------------------ #
    # state sync
    # ------------------------------------------------------------------ #
    def _sync_widgets_from_config(self) -> None:
        self._syncing = True
        try:
            self._spin_count.setValue(max(len(self._config.blocks), 1))
            self._chk_rename.setChecked(bool(self._config.rename_designators))
            self._sync_origins_table()
        finally:
            self._syncing = False

    def _sync_origins_table(self) -> None:
        blocks = sorted(self._config.blocks, key=lambda b: b.index)
        table = self._origins_table
        table.setRowCount(len(blocks))
        for row, b in enumerate(blocks):
            name = QTableWidgetItem(f"B{b.index + 1}")
            name.setFlags(name.flags() & ~Qt.ItemIsEditable)
            table.setItem(row, 0, name)
            for col, value in ((1, b.origin_x), (2, b.origin_y)):
                item = QTableWidgetItem(f"{value:.4f}")
                if b.index == 0:
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    item.setToolTip(tr("Block 1 is the base board at (0, 0)."))
                table.setItem(row, col, item)

    def _detect_from_gko(self) -> None:
        if not self._gko_path:
            QMessageBox.information(
                self, tr("Panelize"),
                tr("No GKO file loaded. Select one in the gerber file dialog first."),
            )
            return
        try:
            info = detect_panel(self._gko_path)
        except Exception as e:  # noqa: BLE001 - show any read/parse error
            QMessageBox.critical(self, tr("Panelize"), f"Error: {e}")
            return
        if info.kind == "single" or not info.instances:
            QMessageBox.information(
                self, tr("Panelize"),
                tr("No panel detected (single board). Coordinates stay unchanged."),
            )
            return
        kept_flips = {b.index: b.rotation for b in self._config.blocks}
        raw = sorted(info.instances, key=lambda i: i.k)
        base_ox, base_oy = raw[0].origin
        blocks = []
        for inst in raw:
            blocks.append(PanelBlock(
                index=inst.k,
                origin_x=inst.origin[0] - base_ox,
                origin_y=inst.origin[1] - base_oy,
                rotation=kept_flips.get(inst.k, 0),
                designator=inst.sub_name or "",
            ))
        blocks.sort(key=lambda b: b.index)
        # Keep the base board at (0, 0) so every cloned coordinate stays
        # non-negative and the block-1 cell in the table matches this.
        self._config.blocks = blocks
        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._refresh_preview()

    def _on_count_changed(self, count: int) -> None:
        if self._syncing:
            return
        cfg = self._config
        blocks = sorted(cfg.blocks, key=lambda b: b.index)
        if count < len(blocks):
            blocks = blocks[:count]
        else:
            next_index = max([b.index for b in blocks], default=-1) + 1
            while len(blocks) < count:
                blocks.append(PanelBlock(index=next_index))
                next_index += 1
        cfg.blocks = blocks
        self._syncing = True
        try:
            self._sync_origins_table()
        finally:
            self._syncing = False
        self._refresh_block_buttons()
        self._refresh_preview()

    def _on_rename_toggled(self, _state=None) -> None:
        if self._syncing:
            return
        self._config.rename_designators = self._chk_rename.isChecked()
        self._refresh_preview()

    def _on_origin_edited(self, row: int, col: int) -> None:
        if self._syncing or col == 0:
            return
        blocks = sorted(self._config.blocks, key=lambda b: b.index)
        if row < 0 or row >= len(blocks):
            return
        block = blocks[row]
        item = self._origins_table.item(row, col)
        try:
            value = float((item.text() if item is not None else "").strip())
        except ValueError:
            value = None
        if value is None:
            self._syncing = True
            try:
                current = block.origin_x if col == 1 else block.origin_y
                if item is not None:
                    item.setText(f"{current:.4f}")
            finally:
                self._syncing = False
            return
        if col == 1:
            block.origin_x = value
        else:
            block.origin_y = value
        self._refresh_block_buttons()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # block buttons
    # ------------------------------------------------------------------ #
    def _clear_blocks_layout(self) -> None:
        while self._blocks_layout.count():
            item = self._blocks_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _refresh_block_buttons(self) -> None:
        self._clear_blocks_layout()
        self._block_buttons = []
        per_row = 6
        for pos, b in enumerate(sorted(self._config.blocks, key=lambda x: x.index)):
            btn = QPushButton()
            btn.setMinimumSize(72, 44)
            btn.setToolTip(
                tr("Block {b}: origin=({x:.4f}, {y:.4f}), rotation={rot}\u00b0",
                   b=b.index, x=b.origin_x, y=b.origin_y, rot=b.rotation)
            )
            btn.clicked.connect(lambda _=False, idx=b.index: self._on_block_clicked(idx))
            self._refresh_block_button_style(btn, b)
            self._blocks_layout.addWidget(btn, pos // per_row, pos % per_row)
            self._block_buttons.append(btn)

    def _refresh_block_button_style(self, btn: QPushButton, block: PanelBlock) -> None:
        text = f"B{block.index + 1}"
        if block.designator:
            text += f"\n{block.designator}"
        if block.rotation:
            text += "\n\u21bb180\u00b0"
            btn.setStyleSheet(
                f"background-color:{_ROTATED_BG}; color:{_ROTATED_FG};"
            )
        else:
            text += "\n0\u00b0"
            btn.setStyleSheet("")
        btn.setText(text)

    def _on_block_clicked(self, block_index: int) -> None:
        if block_index == 0:
            return  # base board stays at 0°
        block = self._config.block_by_index(block_index)
        if block is None:
            return
        block.rotation = 0 if block.rotation else 180
        self._refresh_block_buttons()
        self._refresh_preview()

    # ------------------------------------------------------------------ #
    # preview
    # ------------------------------------------------------------------ #
    def _get_eff(self, rec: ReviewRecord):
        x = rec.new_x if rec.new_x is not None else rec.old_x
        y = rec.new_y if rec.new_y is not None else rec.old_y
        r = rec.new_rotation if rec.new_rotation is not None else rec.old_rotation
        return x, y, r

    def _display_designator(self, rec: ReviewRecord, block: PanelBlock) -> str:
        if self._config.rename_designators and block.index != 0:
            base = rec.base_designator or rec.designator
            return f"{base}_{block.index + 1}"
        return rec.designator

    def _preview_rows(self) -> List[tuple]:
        cfg = self._config
        sample = self._records[:3]
        rows: List[tuple] = []
        for b in cfg.blocks:
            for rec in sample:
                x, y, r = self._get_eff(rec)
                px, py = transform_point(x, y, cfg, b)
                pr = (r + b.rotation) % 360
                rows.append((self._display_designator(rec, b), b.index, px, py, pr))
        return rows

    def _refresh_preview(self) -> None:
        try:
            rows = self._preview_rows()
        except PanelError as e:
            self._label_result.setText(str(e))
            self._preview_table.setRowCount(0)
            self._preview_table.setColumnCount(5)
            return
        total = len(self._records) * self._config.count
        self._label_result.setText(
            tr("Result: {boards} boards \u00d7 {parts} components = {total} records",
               boards=self._config.count, parts=len(self._records), total=total)
        )
        rows = self._preview_rows()
        rows = rows[:40]
        self._preview_table.setRowCount(len(rows))
        self._preview_table.setColumnCount(5)
        for row_idx, vals in enumerate(rows):
            for col_idx, val in enumerate(vals):
                item = QTableWidgetItem(str(val))
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self._preview_table.setItem(row_idx, col_idx, item)

    def _on_accept(self) -> None:
        cfg = self._config
        if cfg.count < 1:
            QMessageBox.warning(self, tr("Panelize"), tr("No boards defined."))
            return
        if not self._records:
            QMessageBox.warning(
                self, tr("Panelize"), tr("No records to panelize.")
            )
            return
        self.panel_config = cfg
        self.accept()
