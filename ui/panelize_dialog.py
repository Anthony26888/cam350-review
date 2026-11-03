from typing import List, Optional
import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog,
    QDialogButtonBox, QDoubleSpinBox, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QMessageBox, QPushButton,
    QRadioButton, QScrollArea, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from models.review import ReviewRecord
from services.gerber.panel_detector import detect_panel
from services.panelize_service import (
    PanelBlock, PanelConfig, PanelError, transform_point,
)
from ui.i18n import tr

_ROTATED_BG = "#E11D48"
_ROTATED_FG = "#FFFFFF"
_MAX_BLOCKS = 500


class PanelizeDialog(QDialog):
    """Collect explicit per-block origins and 180° flags, return a PanelConfig.

    Supports two workflows:
      1. Grid Matrix: user specifies Nx, Ny, dx, dy, and rotation pattern to auto-generate
         coordinates for up to 500 boards in seconds.
      2. Manual / Custom: user sets board count manually, pastes from Excel/clipboard,
         detects from GKO outline, or types origins row by row.

    Layout is structured into two columns:
      - Left column: Configuration & Input (mode toggle, grid settings, manual count, quick tools)
      - Right column: Visual Orientation map (scrollable), Coordinates Table, and Output Preview.
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
        self.setMinimumSize(960, 680)
        self.resize(1000, 720)

        self._build_ui()
        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._update_summary()

    def _build_ui(self) -> None:
        root_layout = QVBoxLayout(self)

        columns_layout = QHBoxLayout()
        root_layout.addLayout(columns_layout, 1)

        left_widget = self._build_left_column()
        left_widget.setMinimumWidth(320)
        left_widget.setMaximumWidth(400)
        columns_layout.addWidget(left_widget, 0)

        right_widget = self._build_right_column()
        columns_layout.addWidget(right_widget, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.button(QDialogButtonBox.Ok).setText(tr("Apply"))
        buttons.button(QDialogButtonBox.Cancel).setText(tr("Cancel"))
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root_layout.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # Left Column: Configuration & Input
    # ------------------------------------------------------------------ #
    def _build_left_column(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # Mode Selector
        mode_group = QGroupBox(tr("Mode"))
        mode_layout = QVBoxLayout(mode_group)
        self._rb_grid = QRadioButton(tr("Grid Matrix (Auto)"))
        self._rb_manual = QRadioButton(tr("Manual / Custom"))
        self._rb_grid.setChecked(True)

        self._mode_btn_group = QButtonGroup(self)
        self._mode_btn_group.addButton(self._rb_grid, 0)
        self._mode_btn_group.addButton(self._rb_manual, 1)
        self._mode_btn_group.idToggled.connect(self._on_mode_toggled)

        mode_layout.addWidget(self._rb_grid)
        mode_layout.addWidget(self._rb_manual)
        layout.addWidget(mode_group)

        # Grid Settings
        self._grid_group = QGroupBox(tr("Grid Settings"))
        grid_vbox = QVBoxLayout(self._grid_group)

        nx_ny_layout = QGridLayout()
        nx_ny_layout.addWidget(QLabel(tr("Columns (Nx):")), 0, 0)
        self._spin_nx = QSpinBox()
        self._spin_nx.setRange(1, 100)
        self._spin_nx.setValue(max(getattr(self._config, "nx", 2), 1))
        self._spin_nx.valueChanged.connect(self._update_grid_total_label)
        nx_ny_layout.addWidget(self._spin_nx, 0, 1)

        nx_ny_layout.addWidget(QLabel(tr("Rows (Ny):")), 1, 0)
        self._spin_ny = QSpinBox()
        self._spin_ny.setRange(1, 100)
        self._spin_ny.setValue(max(getattr(self._config, "ny", 2), 1))
        self._spin_ny.valueChanged.connect(self._update_grid_total_label)
        nx_ny_layout.addWidget(self._spin_ny, 1, 1)

        nx_ny_layout.addWidget(QLabel(tr("Pitch X (dx):")), 2, 0)
        self._spin_dx = QDoubleSpinBox()
        self._spin_dx.setRange(-9999.0, 9999.0)
        self._spin_dx.setDecimals(4)
        self._spin_dx.setSuffix(" mm")
        self._spin_dx.setValue(getattr(self._config, "dx", 0.0))
        nx_ny_layout.addWidget(self._spin_dx, 2, 1)

        nx_ny_layout.addWidget(QLabel(tr("Pitch Y (dy):")), 3, 0)
        self._spin_dy = QDoubleSpinBox()
        self._spin_dy.setRange(-9999.0, 9999.0)
        self._spin_dy.setDecimals(4)
        self._spin_dy.setSuffix(" mm")
        self._spin_dy.setValue(getattr(self._config, "dy", 0.0))
        nx_ny_layout.addWidget(self._spin_dy, 3, 1)

        grid_vbox.addLayout(nx_ny_layout)

        rot_layout = QHBoxLayout()
        rot_layout.addWidget(QLabel(tr("Rotation Pattern:")))
        self._combo_pattern = QComboBox()
        self._combo_pattern.addItems([
            tr("All 0°"),
            tr("Even rows 180°"),
            tr("Even columns 180°"),
            tr("Checkerboard 180°"),
        ])
        rot_layout.addWidget(self._combo_pattern)
        grid_vbox.addLayout(rot_layout)

        self._lbl_grid_total = QLabel()
        self._update_grid_total_label()
        grid_vbox.addWidget(self._lbl_grid_total)

        btn_generate = QPushButton(tr("Generate Grid"))
        btn_generate.setStyleSheet("font-weight: bold; padding: 6px;")
        btn_generate.clicked.connect(self._generate_from_grid)
        grid_vbox.addWidget(btn_generate)

        layout.addWidget(self._grid_group)

        # Manual Settings
        self._manual_group = QGroupBox(tr("Boards"))
        manual_vbox = QVBoxLayout(self._manual_group)
        count_row = QHBoxLayout()
        count_row.addWidget(QLabel(tr("Number of boards:")))
        self._spin_count = QSpinBox()
        self._spin_count.setRange(1, _MAX_BLOCKS)
        self._spin_count.valueChanged.connect(self._on_count_changed)
        count_row.addWidget(self._spin_count)
        manual_vbox.addLayout(count_row)
        lbl_hint = QLabel(tr("Block 1 is the base board at (0, 0)."))
        lbl_hint.setStyleSheet("color: gray;")
        manual_vbox.addWidget(lbl_hint)
        layout.addWidget(self._manual_group)
        self._manual_group.setVisible(False)

        # Quick Tools
        tools_group = QGroupBox(tr("Quick Tools"))
        tools_layout = QVBoxLayout(tools_group)

        btn_paste = QPushButton(tr("Paste from Clipboard"))
        btn_paste.setToolTip(tr("Paste coordinates (X, Y) copied from Excel or text."))
        btn_paste.clicked.connect(self._paste_from_clipboard)
        tools_layout.addWidget(btn_paste)

        btn_detect = QPushButton(tr("Detect from GKO"))
        btn_detect.setToolTip(tr("Fill block origins from the GKO outline."))
        btn_detect.clicked.connect(self._detect_from_gko)
        tools_layout.addWidget(btn_detect)

        layout.addWidget(tools_group)

        # Rename Option
        self._chk_rename = QCheckBox(
            tr("Rename designators (C1 → C1_2, C1_3, ...)")
        )
        self._chk_rename.setChecked(True)
        self._chk_rename.stateChanged.connect(self._on_rename_toggled)
        layout.addWidget(self._chk_rename)

        layout.addStretch(1)
        return container

    # ------------------------------------------------------------------ #
    # Right Column: Orientation, Table, Preview
    # ------------------------------------------------------------------ #
    def _build_right_column(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        # 1. Orientation Map
        orient_group = QGroupBox(tr("Board Orientation"))
        orient_layout = QVBoxLayout(orient_group)
        orient_hint = QLabel(tr("Click a board to flip it 180°."))
        orient_layout.addWidget(orient_hint)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(280)

        self._blocks_holder = QWidget()
        self._blocks_layout = QGridLayout(self._blocks_holder)
        self._blocks_layout.setContentsMargins(6, 6, 6, 6)
        self._blocks_layout.setSpacing(6)
        scroll_area.setWidget(self._blocks_holder)
        orient_layout.addWidget(scroll_area)

        layout.addWidget(orient_group, 3)

        # 2. Coordinates Table
        table_group = QGroupBox(tr("Boards Table"))
        table_layout = QVBoxLayout(table_group)

        self._origins_table = QTableWidget(0, 3)
        self._origins_table.setHorizontalHeaderLabels([
            tr("Block"), tr("Origin X (mm)"), tr("Origin Y (mm)"),
        ])
        self._origins_table.verticalHeader().setVisible(False)
        self._origins_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._origins_table.setMinimumHeight(200)
        self._origins_table.setEditTriggers(QTableWidget.AllEditTriggers)
        self._origins_table.cellChanged.connect(self._on_origin_edited)
        table_layout.addWidget(self._origins_table)

        hint = QLabel(
            tr("Normal block: enter its bottom-left corner. "
               "Flipped (180°) block: enter its top-right corner.")
        )
        hint.setStyleSheet("color: gray; font-size: 11px;")
        hint.setWordWrap(True)
        table_layout.addWidget(hint)

        self._label_result = QLabel()
        self._label_result.setStyleSheet("font-weight: bold; color: #0284C7; margin-top: 4px;")
        table_layout.addWidget(self._label_result)

        layout.addWidget(table_group, 2)
        return container

    # ------------------------------------------------------------------ #
    # Mode & Grid generation
    # ------------------------------------------------------------------ #
    def _on_mode_toggled(self, btn_id: int, checked: bool) -> None:
        if not checked:
            return
        is_grid = (btn_id == 0)
        self._grid_group.setVisible(is_grid)
        self._manual_group.setVisible(not is_grid)

    def _update_grid_total_label(self) -> None:
        nx = self._spin_nx.value()
        ny = self._spin_ny.value()
        total = nx * ny
        self._lbl_grid_total.setText(tr("Total: {n} boards", n=total))

    def _generate_from_grid(self) -> None:
        nx = self._spin_nx.value()
        ny = self._spin_ny.value()
        dx = self._spin_dx.value()
        dy = self._spin_dy.value()
        pattern_idx = self._combo_pattern.currentIndex()

        blocks: List[PanelBlock] = []
        for ky in range(ny):
            for kx in range(nx):
                k = ky * nx + kx
                rot = 0
                if k != 0:
                    if pattern_idx == 1:  # Even rows 180°
                        rot = 180 if (ky % 2 == 1) else 0
                    elif pattern_idx == 2:  # Even columns 180°
                        rot = 180 if (kx % 2 == 1) else 0
                    elif pattern_idx == 3:  # Checkerboard
                        rot = 180 if ((kx + ky) % 2 == 1) else 0
                blocks.append(PanelBlock(
                    index=k,
                    origin_x=round(kx * dx, 6),
                    origin_y=round(ky * dy, 6),
                    rotation=rot,
                ))

        self._config.nx = nx
        self._config.ny = ny
        self._config.dx = dx
        self._config.dy = dy
        self._config.blocks = blocks

        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._update_summary()

    def _paste_from_clipboard(self) -> None:
        text = QApplication.clipboard().text()
        if not text or not text.strip():
            QMessageBox.information(
                self, tr("Paste from Clipboard"),
                tr("No valid coordinates found in clipboard. Format expected: X, Y or X [tab] Y")
            )
            return

        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        parsed_coords = []
        for line in lines:
            parts = re.split(r"[\t,;\s]+", line)
            if len(parts) >= 2:
                try:
                    px = float(parts[0])
                    py = float(parts[1])
                    parsed_coords.append((px, py))
                except ValueError:
                    continue

        if not parsed_coords:
            QMessageBox.warning(
                self, tr("Paste from Clipboard"),
                tr("No valid coordinates found in clipboard. Format expected: X, Y or X [tab] Y")
            )
            return

        if len(parsed_coords) > _MAX_BLOCKS:
            parsed_coords = parsed_coords[:_MAX_BLOCKS]

        kept_rot = {b.index: b.rotation for b in self._config.blocks}
        blocks = []
        for idx, (px, py) in enumerate(parsed_coords):
            blocks.append(PanelBlock(
                index=idx,
                origin_x=0.0 if idx == 0 else px,
                origin_y=0.0 if idx == 0 else py,
                rotation=kept_rot.get(idx, 0),
            ))

        self._config.blocks = blocks
        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._update_summary()

    # ------------------------------------------------------------------ #
    # State synchronization
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
        except Exception as e:
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
        self._config.blocks = blocks
        self._sync_widgets_from_config()
        self._refresh_block_buttons()
        self._update_summary()

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
        self._update_summary()

    def _on_rename_toggled(self, _state=None) -> None:
        if self._syncing:
            return
        self._config.rename_designators = self._chk_rename.isChecked()
        self._update_summary()

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
        self._update_summary()

    # ------------------------------------------------------------------ #
    # Orientation Buttons
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

        cfg = self._config
        per_row = cfg.nx if (cfg.nx > 1 and cfg.nx * cfg.ny == len(cfg.blocks)) else 8
        per_row = max(min(per_row, 12), 4)

        for pos, b in enumerate(sorted(self._config.blocks, key=lambda x: x.index)):
            btn = QPushButton()
            btn.setMinimumSize(64, 44)
            btn.setToolTip(
                tr("Block {b}: origin=({x:.4f}, {y:.4f}), rotation={rot}°",
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
            text += "\n↻180°"
            btn.setStyleSheet(
                f"background-color:{_ROTATED_BG}; color:{_ROTATED_FG}; font-size:11px; font-weight:bold; border-radius:4px; padding:3px;"
            )
        else:
            text += "\n0°"
            btn.setStyleSheet("font-size:11px; border-radius:4px; padding:3px;")
        btn.setText(text)

    def _on_block_clicked(self, block_index: int) -> None:
        if block_index == 0:
            return
        block = self._config.block_by_index(block_index)
        if block is None:
            return
        block.rotation = 0 if block.rotation else 180
        self._refresh_block_buttons()
        self._update_summary()

    # ------------------------------------------------------------------ #
    # Summary & Accept
    # ------------------------------------------------------------------ #
    def _update_summary(self) -> None:
        total = len(self._records) * self._config.count
        self._label_result.setText(
            tr("Result: {boards} boards × {parts} components = {total} records",
               boards=self._config.count, parts=len(self._records), total=total)
        )

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
