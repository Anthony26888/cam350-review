import os
from typing import Optional, List, Dict, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox,
    QFormLayout, QRadioButton, QButtonGroup,
    QTextEdit, QWidget, QApplication,
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal

MACRO_SWITCH_DELAY_S = 5

from config.config_manager import ConfigManager
from database.pcb_info_repo import PcbInfoRepo
from ui.i18n import tr
from ui.style import err_bg, err_color, muted_color, pos_bg, pos_color, txt_color
from models.pcb_info import PcbInfo
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from services.cam350_controller import Cam350Controller
from services.gerber.gerber_parser import (
    parse_flashes,
    parse_gerber_points,
)
from services.gerber.panel_detector import detect_panel, PanelInfo
from services.prescreen import (
    KIND_DUP,
    KIND_OUT,
    KIND_PAD,
    KIND_ROT,
    PrescreenConfig,
    assign_instance_by_y,
    compute_pad_stats,
    eff_rotation,
    eff_x,
    eff_y,
    run_prescreen,
    summarize,
    transform_points_through_align,
)
from services.gerber.origin_aligner import AlignResult, align_instance
from services.gerber.offset_applier import (
    ComponentTransform, apply_all_transforms, round_coord, _layer_frame,
    GKO_PRIORITY_TOL,
)


class AlignWorker(QThread):
    progress = Signal(str, int)
    finished = Signal(dict, list, PanelInfo, str, bool)

    def __init__(
        self,
        gko_path: str,
        gtp_path: Optional[str],
        gbp_path: Optional[str],
        pickplace: PickPlaceData,
        origin_mode: str,
        rotation_angle: int = 0,
        mil_to_mm: bool = False,
        detect_rotation: bool = False,
        rot_layers: Optional[dict] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._gko_path = gko_path
        self._gtp_path = gtp_path
        self._gbp_path = gbp_path
        self._pickplace = pickplace
        self._origin_mode = origin_mode
        self._rotation_angle = rotation_angle
        self._mil_to_mm = mil_to_mm
        self._detect_rotation = detect_rotation
        self._rot_layers = rot_layers if rot_layers is not None else {"top": True, "bottom": False}

    def run(self) -> None:
        try:
            self.progress.emit(tr("Detecting panel from GKO..."), 5)
            panel_info = detect_panel(self._gko_path)

            self.progress.emit(tr("Detected: {kind}, {count} instance(s)", kind=panel_info.kind, count=panel_info.count), 10)

            gtp_pts = None
            gbp_pts = None

            if self._gtp_path and os.path.exists(self._gtp_path):
                self.progress.emit(tr("Reading GTP (Top Paste)..."), 15)
                gtp_pts = parse_flashes(self._gtp_path)

            if self._gbp_path and os.path.exists(self._gbp_path):
                self.progress.emit(tr("Reading GBP (Bottom Paste)..."), 20)
                gbp_pts = parse_flashes(self._gbp_path)

            scale = 0.0254 if self._mil_to_mm else 1.0

            self.progress.emit(tr("Computing offset for each instance..."), 30)

            align_results = {}

            comps = self._pickplace.components
            top_comps = [c for c in comps if _layer_frame(c.layer) == "top"]
            bot_comps = [c for c in comps if _layer_frame(c.layer) == "bottom"]

            total_instances = panel_info.count
            for i, instance in enumerate(panel_info.instances):
                pct = 30 + int((i / total_instances) * 40)
                self.progress.emit(
                    tr("Instance {current}/{total}: {name}...",
                       current=i + 1, total=total_instances, name=instance.sub_name or tr("board")),
                    pct
                )

                layer_results = {}

                if top_comps:
                    top_xs = [c.x * scale for c in top_comps]
                    top_ys = [c.y * scale for c in top_comps]
                    res_top = align_instance(
                        instance, top_xs, top_ys,
                        gtp_pts=gtp_pts,
                        layer="top",
                        is_panel=panel_info.is_panel,
                        dy_mm=panel_info.dy_mm,
                        board_h=instance.h,
                        detect_rotation=self._detect_rotation,
                    )
                    res_top.n_total = len(top_comps)
                    layer_results["top"] = res_top

                if bot_comps:
                    bot_xs = [c.x * scale for c in bot_comps]
                    bot_ys = [c.y * scale for c in bot_comps]
                    res_bot = align_instance(
                        instance, bot_xs, bot_ys,
                        gbp_pts=gbp_pts,
                        layer="bottom",
                        is_panel=panel_info.is_panel,
                        dy_mm=panel_info.dy_mm,
                        board_h=instance.h,
                        detect_rotation=self._detect_rotation,
                    )
                    res_bot.n_total = len(bot_comps)
                    layer_results["bottom"] = res_bot

                align_results[i] = layer_results

            self.progress.emit(tr("Creating transforms..."), 80)

            transforms = []
            for c in self._pickplace.components:
                k = 0
                if panel_info.is_panel and panel_info.count > 1:
                    cy_mm = c.y * scale
                    best_k, best_dist = 0, float('inf')
                    for inst in panel_info.instances:
                        inst_mid_y = inst.origin[1] + inst.h / 2
                        d = abs(cy_mm - inst_mid_y)
                        if d < best_dist:
                            best_dist, best_k = d, inst.k
                    k = best_k
                c.panel_instance = k

                tf = ComponentTransform(
                    designator=c.designator,
                    layer=c.layer,
                    orig_x=c.x * scale,
                    orig_y=c.y * scale,
                    orig_rotation=c.rotation,
                    instance_k=k,
                )
                transforms.append(tf)

            apply_all_transforms(
                transforms, panel_info, align_results,
                origin_mode=self._origin_mode,
                rotation_angle=self._rotation_angle,
                rot_layers=self._rot_layers,
            )

            self.progress.emit(tr("Calculation complete."), 100)
            self.finished.emit(align_results, transforms, panel_info, self._origin_mode, self._rotation_angle)

        except Exception as e:
            self.progress.emit(tr("Error: {e}", e=e), -1)


class PrescreenWorker(QThread):
    progress = Signal(str, int)
    stats_ready = Signal(dict)
    finished = Signal(list)
    failed = Signal(str)

    def __init__(
        self,
        gko_path,
        gtp_path,
        gbp_path,
        records: List[ReviewRecord],
        cfg: PrescreenConfig,
        dismissed=None,
        ctx=None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._gko_path = gko_path
        self._gtp_path = gtp_path
        self._gbp_path = gbp_path
        self._records = records
        self._cfg = cfg
        self._dismissed = set(dismissed or ())
        self._ctx = ctx or {}

    def run(self) -> None:
        try:
            align_results = self._ctx.get("align_results") or {}
            panel_info = self._ctx.get("panel_info")
            origin_mode = self._ctx.get("origin_mode", "panel")
            rotation_angle = int(self._ctx.get("rotation_angle") or 0)
            rot_layers = self._ctx.get("rot_layers") or {"top": True, "bottom": False}

            outline_bbox = None
            if self._gko_path and os.path.exists(self._gko_path):
                self.progress.emit(tr("Reading GKO (outline)..."), 15)
                pts = parse_gerber_points(self._gko_path, codes=('1', '2'))
                if pts:
                    xs = [p.x_mm for p in pts]
                    ys = [p.y_mm for p in pts]
                    corners = [
                        (min(xs), min(ys)), (min(xs), max(ys)),
                        (max(xs), min(ys)), (max(xs), max(ys)),
                    ]
                    tcorners = transform_points_through_align(
                        corners, "top", align_results=align_results,
                        panel_info=panel_info, origin_mode=origin_mode,
                        rotation_angle=rotation_angle, rot_layers=rot_layers,
                    )
                    xs = [p[0] for p in tcorners]
                    ys = [p[1] for p in tcorners]
                    outline_bbox = (min(xs), min(ys), max(xs), max(ys))

            paste_top = None
            if self._gtp_path and os.path.exists(self._gtp_path):
                self.progress.emit(tr("Reading GTP (Top Paste)..."), 45)
                raw = [(p.x_mm, p.y_mm) for p in parse_flashes(self._gtp_path)]
                ks = [assign_instance_by_y(y, panel_info) for _, y in raw]
                paste_top = transform_points_through_align(
                    raw, "top", align_results=align_results,
                    panel_info=panel_info, origin_mode=origin_mode,
                    rotation_angle=rotation_angle, rot_layers=rot_layers,
                    instance_ks=ks,
                )
            paste_bottom = None
            if self._gbp_path and os.path.exists(self._gbp_path):
                self.progress.emit(tr("Reading GBP (Bottom Paste)..."), 65)
                raw = [(p.x_mm, p.y_mm) for p in parse_flashes(self._gbp_path)]
                ks = [assign_instance_by_y(y, panel_info) for _, y in raw]
                paste_bottom = transform_points_through_align(
                    raw, "bottom", align_results=align_results,
                    panel_info=panel_info, origin_mode=origin_mode,
                    rotation_angle=rotation_angle, rot_layers=rot_layers,
                    instance_ks=ks,
                )

            self.progress.emit(tr("Running pre-screen checks..."), 85)
            coords = [(eff_x(r), eff_y(r)) for r in self._records]
            rots = [eff_rotation(r) for r in self._records]
            issues = run_prescreen(
                self._records,
                paste_top=paste_top,
                paste_bottom=paste_bottom,
                outline_bbox=outline_bbox,
                cfg=self._cfg,
                dismissed=self._dismissed,
                coords=coords,
                rots=rots,
            )
            stats = compute_pad_stats(
                self._records, coords=coords,
                paste_top=paste_top, paste_bottom=paste_bottom,
            )
            self.progress.emit(tr("Done."), 100)
            self.stats_ready.emit(stats)
            self.finished.emit(issues)
            self.progress.emit(tr("Done."), 100)
            self.finished.emit(issues)
        except Exception as e:
            self.failed.emit(str(e))


class OriginAlignWizard(QDialog):
    def __init__(
        self,
        pickplace_data: PickPlaceData,
        records: List[ReviewRecord],
        apply_callback: Callable,
        parent: Optional[QWidget] = None,
        dismissed=None,
        flush_cb: Optional[Callable] = None,
    ) -> None:
        super().__init__(parent)
        self._pickplace_data = pickplace_data
        self._records = records
        self._apply_callback = apply_callback
        self._flush_cb = flush_cb
        self._config_mgr = ConfigManager.instance()
        self._cam350 = Cam350Controller()
        self._dismissed = set(dismissed or ())

        self._gko_path = None
        self._gtp_path = None
        self._gbp_path = None
        self._gto_path = None
        self._gbo_path = None
        self._panel_info = None
        self._origin_mode = 'panel'
        self._rotation_angle = 0
        self._chosen_rotation_angle = 0
        self._chosen_rot_layers = {"top": True, "bottom": False}
        self._mil_to_mm = False
        self._chosen_mil_to_mm = False
        self._detect_rotation = False
        self._align_results = {}
        self._transforms = []
        self._worker_done = False
        self._macro_x = None
        self._macro_y = None
        self._macro_layer = 'top'
        self._macro_running = False
        self._macro_countdown = 0
        self._macro_timer = QTimer(self)
        self._prescreen_issues = None
        self._prescreen_worker = None
        self._prescreen_ctx = None
        self._prescreen_stats = None
        self._prescreen_generation = 0

        self._macro_timer.timeout.connect(self._tick_macro_countdown)

        self.setWindowTitle("Align PickPlace Origin")
        self.setMinimumSize(650, 500)
        self.setModal(True)

        self._build_ui()
        self._show_step(0)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self._lbl_title)

        self._content_area = QVBoxLayout()
        layout.addLayout(self._content_area)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setVisible(False)
        layout.addWidget(self._progress_bar)

        self._lbl_progress = QLabel("")
        self._lbl_progress.setVisible(False)
        layout.addWidget(self._lbl_progress)

        self._result_text = QTextEdit()
        self._result_text.setReadOnly(True)
        self._result_text.setVisible(False)
        layout.addWidget(self._result_text)

        btn_layout = QHBoxLayout()

        self._btn_back = QPushButton(tr("◀ Back"))
        self._btn_back.clicked.connect(self._on_back)
        self._btn_back.setMinimumHeight(36)
        self._btn_back.setVisible(False)

        self._btn_next = QPushButton(tr("Next ▶"))
        self._btn_next.clicked.connect(self._on_next)
        self._btn_next.setMinimumHeight(36)

        self._btn_cancel = QPushButton(tr("Cancel"))
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_cancel.setMinimumHeight(36)

        btn_layout.addWidget(self._btn_back)
        btn_layout.addStretch()
        btn_layout.addWidget(self._btn_cancel)
        btn_layout.addWidget(self._btn_next)
        layout.addLayout(btn_layout)

        self._step_index = 0

    def _clear_content(self) -> None:
        while self._content_area.count():
            item = self._content_area.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def _show_step(self, step: int) -> None:
        self._macro_timer.stop()
        self._clear_content()
        self._step_index = step
        self._result_text.setVisible(False)
        self._progress_bar.setVisible(False)
        self._lbl_progress.setVisible(False)

        steps = [
            self._step_files,
            self._step_panel_check,
            self._step_options,
            self._step_run,
            self._step_macro,
            self._step_prescreen,
            self._step_result,
        ]

        if step < len(steps):
            steps[step]()

        self._btn_back.setVisible(step > 0 and step < len(steps) - 1)
        self._btn_next.setText(tr("Finish") if step == len(steps) - 1 else tr("Next ▶"))
        self._btn_cancel.setVisible(step < len(steps) - 1)

    def _step_files(self) -> None:
        self._lbl_title.setText(tr("Step 1/7: Select Gerber Files"))

        group = QGroupBox(tr("Gerber Files"))
        form = QFormLayout(group)

        gko_layout = QHBoxLayout()
        self._lbl_gko = QLabel(tr("(not selected)"))
        self._lbl_gko.setStyleSheet(f"color: {muted_color()};")
        btn_gko = QPushButton(tr("Browse..."))
        btn_gko.clicked.connect(self._browse_gko)
        gko_layout.addWidget(self._lbl_gko, 1)
        gko_layout.addWidget(btn_gko)
        form.addRow(tr("GKO (Outline) *:"), gko_layout)

        gtp_layout = QHBoxLayout()
        self._lbl_gtp = QLabel(tr("(optional)"))
        self._lbl_gtp.setStyleSheet(f"color: {muted_color()};")
        btn_gtp = QPushButton(tr("Browse..."))
        btn_gtp.clicked.connect(self._browse_gtp)
        gtp_layout.addWidget(self._lbl_gtp, 1)
        gtp_layout.addWidget(btn_gtp)
        form.addRow(tr("GTP (Top Paste):"), gtp_layout)

        gbp_layout = QHBoxLayout()
        self._lbl_gbp = QLabel(tr("(optional)"))
        self._lbl_gbp.setStyleSheet(f"color: {muted_color()};")
        btn_gbp = QPushButton(tr("Browse..."))
        btn_gbp.clicked.connect(self._browse_gbp)
        gbp_layout.addWidget(self._lbl_gbp, 1)
        gbp_layout.addWidget(btn_gbp)
        form.addRow(tr("GBP (Bottom Paste):"), gbp_layout)

        gto_layout = QHBoxLayout()
        self._lbl_gto = QLabel(tr("(optional)"))
        self._lbl_gto.setStyleSheet(f"color: {muted_color()};")
        btn_gto = QPushButton(tr("Browse..."))
        btn_gto.clicked.connect(self._browse_gto)
        gto_layout.addWidget(self._lbl_gto, 1)
        gto_layout.addWidget(btn_gto)
        form.addRow(tr("GTO (Top Overlay / Silkscreen):"), gto_layout)

        gbo_layout = QHBoxLayout()
        self._lbl_gbo = QLabel(tr("(optional)"))
        self._lbl_gbo.setStyleSheet(f"color: {muted_color()};")
        btn_gbo = QPushButton(tr("Browse..."))
        btn_gbo.clicked.connect(self._browse_gbo)
        gbo_layout.addWidget(self._lbl_gbo, 1)
        gbo_layout.addWidget(btn_gbo)
        form.addRow(tr("GBO (Bottom Overlay / Silkscreen):"), gbo_layout)

        info = QLabel(
            tr("* GKO is required (Gerber Outline).\n"
               "GTP/GBP help detect offsets more accurately (recommended).\n"
               "GTO/GBO (names/designators on the board) are only used for display in Gerber View.")
        )
        info.setStyleSheet(f"color: {muted_color()}; font-style: italic; margin-top: 8px;")

        self._content_area.addWidget(group)
        self._content_area.addWidget(info)

    def _step_panel_check(self) -> None:
        self._lbl_title.setText(tr("Step 2/7: Panel Detection Result"))

        panel_info = self._panel_info
        if not panel_info:
            return

        pox, poy = panel_info.panel_origin

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(200)

        _mm_to_mil = 1.0 / 0.0254

        if panel_info.kind == 'A':
            kind_label = tr("Panel Type A (step-repeat)")
        elif panel_info.kind == 'B':
            kind_label = tr("Panel Type B (multiple blocks)")
        else:
            kind_label = tr("Single board")

        lines = []
        lines.append(tr("Type: {kind}", kind=kind_label))
        lines.append(tr("Instances: {count}", count=panel_info.count))
        lines.append(f"")
        lines.append(tr("Panel Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
                        x=pox, y=poy, xm=pox * _mm_to_mil, ym=poy * _mm_to_mil))
        lines.append(tr("Panel Width:  {w:.4f} mm  ({wm:.2f} mil)",
                        w=panel_info.panel_w, wm=panel_info.panel_w * _mm_to_mil))
        lines.append(tr("Panel Height: {h:.4f} mm  ({hm:.2f} mil)",
                        h=panel_info.panel_h, hm=panel_info.panel_h * _mm_to_mil))
        lines.append(f"")

        for inst in panel_info.instances:
            ox, oy = inst.origin
            layer_tag = tr(" [layer: {name}]", name=inst.sub_name) if inst.sub_name else ""
            lines.append(
                tr("  Instance {k}{tag}:", k=inst.k, tag=layer_tag)
            )
            lines.append(
                tr("    origin=({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
                   x=ox - pox, y=oy - poy, xm=(ox - pox) * _mm_to_mil, ym=(oy - poy) * _mm_to_mil)
            )
            lines.append(
                tr("    w={w:.4f} mm ({wm:.2f} mil)  h={h:.4f} mm ({hm:.2f} mil)",
                   w=inst.w, wm=inst.w * _mm_to_mil, h=inst.h, hm=inst.h * _mm_to_mil)
            )

        text.setText("\n".join(lines))
        self._content_area.addWidget(text)

        if panel_info.is_panel:
            info = QLabel(
                tr("Panel detected. The next step lets you choose the origin mode.")
            )
            info.setStyleSheet("color: {pos_color()}; font-weight: bold; margin-top: 8px;")
            self._content_area.addWidget(info)

    def _step_options(self) -> None:
        self._lbl_title.setText(tr("Step 3/7: Rotation and Unit Options"))

        panel_info = self._panel_info
        if not panel_info:
            return

        rot_group = QGroupBox(tr("Rotate Panel/Board"))
        rot_layout = QVBoxLayout(rot_group)

        self._rot_group = QButtonGroup(self)
        angles = [(0, tr("0° (no rotation) - default")), (90, "90°")]
        self._rb_rot = {}
        for val, label in angles:
            rb = QRadioButton(label)
            if val == 0:
                rb.setChecked(True)
            self._rot_group.addButton(rb, val)
            self._rb_rot[val] = rb
            rot_layout.addWidget(rb)
        self._content_area.addWidget(rot_group)

        self._rot_layer_group = QGroupBox(tr("Select layer to apply 90° rotation formula"))
        layer_layout = QVBoxLayout(self._rot_layer_group)
        self._rb_rot_top = QRadioButton(tr("Top layer - 90° formula: (H-y, x)"))
        self._rb_rot_bottom = QRadioButton(tr("Bottom layer - 90° formula: (y, x)"))
        self._rot_layer_btns = QButtonGroup(self)
        self._rot_layer_btns.addButton(self._rb_rot_top)
        self._rot_layer_btns.addButton(self._rb_rot_bottom)
        self._rb_rot_top.setChecked(True)
        layer_layout.addWidget(self._rb_rot_top)
        layer_layout.addWidget(self._rb_rot_bottom)
        self._content_area.addWidget(self._rot_layer_group)

        def _toggle_rot_layers(checked: bool) -> None:
            self._rot_layer_group.setVisible(checked)
            self._rot_layer_group.setEnabled(checked)

        self._rb_rot[90].toggled.connect(_toggle_rot_layers)
        _toggle_rot_layers(self._rb_rot[90].isChecked())

        unit_group = QGroupBox(tr("PickPlace coordinate units"))
        unit_layout = QVBoxLayout(unit_group)

        self._rb_unit_mm = QRadioButton(tr("mm (millimeters) - default"))
        self._rb_unit_mm.setChecked(True)
        self._rb_unit_mil = QRadioButton(tr("mil (convert to mm: * 0.0254)"))

        unit_layout.addWidget(self._rb_unit_mm)
        unit_layout.addWidget(self._rb_unit_mil)
        self._content_area.addWidget(unit_group)

    def _step_run(self) -> None:
        self._lbl_title.setText(tr("Step 4/7: Computing offsets..."))

        self._progress_bar.setVisible(True)
        self._lbl_progress.setVisible(True)
        self._progress_bar.setValue(0)
        self._lbl_progress.setText(tr("Starting computation..."))

        self._btn_next.setEnabled(False)
        self._btn_back.setEnabled(False)
        self._btn_cancel.setEnabled(False)

        self._rotation_angle = self._chosen_rotation_angle
        self._mil_to_mm = self._chosen_mil_to_mm

        self._worker = AlignWorker(
            gko_path=self._gko_path,
            gtp_path=self._gtp_path,
            gbp_path=self._gbp_path,
            pickplace=self._pickplace_data,
            origin_mode=self._origin_mode,
            rotation_angle=self._rotation_angle,
            mil_to_mm=self._mil_to_mm,
            detect_rotation=self._detect_rotation,
            rot_layers=self._chosen_rot_layers,
        )
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.finished.connect(self._on_worker_finished)
        self._worker.start()

    def _on_worker_progress(self, message: str, pct: int) -> None:
        self._lbl_progress.setText(message)
        if pct >= 0:
            self._progress_bar.setValue(pct)
            return

    def _on_worker_finished(
        self,
        align_results: dict,
        transforms: list,
        panel_info: PanelInfo,
        origin_mode: str,
        rotation_angle: int,
    ) -> None:
        self._align_results = align_results
        self._transforms = transforms
        self._panel_info = panel_info
        self._origin_mode = origin_mode
        self._rotation_angle = rotation_angle
        self._prescreen_ctx = {
            "align_results": align_results,
            "panel_info": panel_info,
            "origin_mode": origin_mode,
            "rotation_angle": rotation_angle,
            "rot_layers": dict(self._chosen_rot_layers),
        }

        self._lbl_title.setText(tr("Step 4/7: Updating data..."))

        total = len(transforms)
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(0)

        updated_count = 0
        for i, tf in enumerate(transforms):
            if tf.new_x is None and tf.new_y is None and tf.new_rotation is None:
                continue

            self._apply_callback(
                tf.designator,
                round_coord(tf.new_x) if tf.new_x is not None else None,
                round_coord(tf.new_y) if tf.new_y is not None else None,
                round_coord(tf.new_rotation) if tf.new_rotation is not None else None,
            )
            updated_count += 1

            self._progress_bar.setValue(i + 1)
            self._lbl_progress.setText(tr("Updated {count}/{total}", count=updated_count, total=total))
            if i % 30 == 0:
                QApplication.processEvents()

        if self._flush_cb is not None:
            try:
                self._flush_cb()
            except Exception:
                pass

        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(100)
        self._lbl_progress.setText(tr("Done! {count} components aligned.", count=updated_count))

        self._worker_done = True
        self._btn_next.setEnabled(True)
        self._btn_next.setText(tr("Next ▶"))
        self._btn_back.setEnabled(True)
        self._btn_cancel.setEnabled(True)

    def _step_macro(self) -> None:
        self._lbl_title.setText(tr("Step 5/7: Get Panel Origin from CAM350 (Macro)"))

        layer_group = QGroupBox(tr("Layer"))
        layer_layout = QVBoxLayout(layer_group)

        self._rb_layer_top = QRadioButton(tr("Top layer (default)"))
        self._rb_layer_top.setChecked(True)
        self._rb_layer_bottom = QRadioButton(tr("Bottom layer"))

        self._layer_group = QButtonGroup(self)
        self._layer_group.addButton(self._rb_layer_top)
        self._layer_group.addButton(self._rb_layer_bottom)

        layer_layout.addWidget(self._rb_layer_top)
        layer_layout.addWidget(self._rb_layer_bottom)
        self._content_area.addWidget(layer_group)

        group = QGroupBox(tr("Macro"))
        layout = QVBoxLayout(group)

        info = QLabel(
            tr("Press the button below to run the macro on CAM350:\n"
               "1. After pressing Run Macro, the app waits 5 seconds - switch to the CAM350 window in the meantime\n"
               "2. If Step 2 selected 90° rotation: the program presses Ctrl+Alt+R to rotate the board 90° first\n"
               "3. Top layer: Ctrl+Alt+X (show Space Origin marker) -> jump to Panel Origin (from Step 2)\n"
               "4. Bottom layer: Ctrl+Alt+B (view Bottom) -> Ctrl+Alt+X -> jump to the transformed coordinates\n"
               "5. Confirm the dialog that appears by pressing Enter\n"
               "\n"
               "Note: CAM350 must be displaying mm units for accurate jumps.")
        )
        info.setWordWrap(True)
        info.setStyleSheet(f"color: {muted_color()}; padding: 4px 0;")
        layout.addWidget(info)

        self._btn_run_macro = QPushButton(tr("Run Macro ▶"))
        self._btn_run_macro.setMinimumHeight(36)
        self._btn_run_macro.setStyleSheet("background-color: #0D9488; color: white; font-weight: bold;")
        self._btn_run_macro.clicked.connect(self._run_macro)
        layout.addWidget(self._btn_run_macro)

        self._lbl_macro_status = QLabel(tr("Not run yet."))
        self._lbl_macro_status.setWordWrap(True)
        self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #006600; background: {pos_bg()}; padding: 8px; border: 1px solid #ccc;")
        layout.addWidget(self._lbl_macro_status)

        self._content_area.addWidget(group)

        cfg = self._config_mgr.config
        if (not cfg.xTextbox.x) or (not cfg.yTextbox.x):
            self._btn_run_macro.setEnabled(False)
            self._lbl_macro_status.setText(tr("CAM350 is not calibrated. Please run the Calibration Wizard first."))
            self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #cc0000; background: {err_bg()}; padding: 8px; border: 1px solid #ccc;")
            return
        else:
            if self._macro_x is None:
                return
            if self._macro_y is None:
                return
            layer_label = tr("Top") if self._macro_layer == "top" else tr("Bottom")
            self._lbl_macro_status.setText(tr("Got Panel Origin ({layer}): X = {x:.4f}, Y = {y:.4f}",
                                              layer=layer_label, x=self._macro_x, y=self._macro_y))
            return

    def _run_macro(self) -> None:
        if self._macro_running:
            return
        self._macro_running = True
        self._btn_run_macro.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_back.setEnabled(False)
        self._btn_cancel.setEnabled(False)

        self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #006600; background: {pos_bg()}; padding: 8px; border: 1px solid #ccc;")

        self._macro_countdown = MACRO_SWITCH_DELAY_S
        self._lbl_macro_status.setText(tr("Please switch to the CAM350 window in {n} seconds...", n=self._macro_countdown))
        QApplication.processEvents()
        self._macro_timer.start(1000)

    def _tick_macro_countdown(self) -> None:
        self._macro_countdown -= 1
        if self._macro_countdown <= 0:
            self._macro_timer.stop()
            self._execute_macro()
            return
        self._lbl_macro_status.setText(tr("Please switch to the CAM350 window in {n} seconds...", n=self._macro_countdown))

    def _execute_macro(self) -> None:
        self._lbl_macro_status.setText(tr("Running macro on CAM350..."))
        QApplication.processEvents()

        layer = "bottom" if self._rb_layer_bottom.isChecked() else "top"
        error = None
        ox = oy = None
        angle_deg = int(self._chosen_rotation_angle or self._rotation_angle or 0)
        try:
            pox, poy = self._panel_info.panel_origin
            pw = self._panel_info.panel_w
            ph = self._panel_info.panel_h
            if angle_deg == 90:
                if layer == "bottom":
                    ox, oy = pox, poy
                else:
                    ox, oy = pox, ph + poy
            else:
                if layer == "bottom":
                    ox, oy = pox + pw, poy
                else:
                    ox, oy = pox, poy
        except (AttributeError, TypeError):
            error = tr("No Panel Origin data from Step 2.")

        self._lbl_macro_status.setText(
            tr("Running macro on CAM350... (layer={layer}, angle={angle}°, jump=({ox}, {oy}))",
               layer=layer, angle=angle_deg, ox=ox, oy=oy)
        )
        QApplication.processEvents()

        if error is None:
            try:
                self._cam350.run_origin_macro(ox, oy, layer=layer, angle_deg=angle_deg)
            except RuntimeError as e:
                error = str(e)
            except Exception as e:
                error = str(e)

        self._macro_running = False
        self._btn_run_macro.setEnabled(True)
        self._btn_next.setEnabled(True)
        self._btn_back.setEnabled(True)
        self._btn_cancel.setEnabled(True)

        if error is not None:
            self._lbl_macro_status.setText(tr("Macro failed: {error}", error=error))
            self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #cc0000; background: {err_bg()}; padding: 8px; border: 1px solid #ccc;")
            return

        self._macro_layer = layer
        self._macro_x = ox
        self._macro_y = oy
        layer_label = tr("Top") if layer == "top" else tr("Bottom")
        self._lbl_macro_status.setText(tr("Got Panel Origin ({layer}): X = {x:.4f}, Y = {y:.4f}",
                                          layer=layer_label, x=ox, y=oy))

    def _step_prescreen(self) -> None:
        self._lbl_title.setText(tr("Step 6/7: Pre-screen Check"))

        page = QWidget()
        v = QVBoxLayout(page)

        self._btn_run_prescreen = QPushButton(tr("▶ Run Check"))
        self._btn_run_prescreen.setMinimumHeight(36)
        self._btn_run_prescreen.setStyleSheet(
            "background-color: #0D9488; color: white; font-weight: bold;"
        )
        self._btn_run_prescreen.clicked.connect(self._run_prescreen_check)
        v.addWidget(self._btn_run_prescreen, 0, Qt.AlignHCenter)

        self._prescreen_summary = QLabel(tr("Not run yet. Press Run Check to scan the board."))
        self._prescreen_summary.setWordWrap(True)
        self._prescreen_summary.setStyleSheet("font-size: 14px; padding: 6px 0;")
        v.addWidget(self._prescreen_summary)

        cfg = self._config_mgr.config.prescreen
        legend = QGroupBox(tr("Legend"))
        lv = QVBoxLayout(legend)
        legend_items = [
            (tr("🔁 ROT = Rotation — unusual rotation"),
             tr("(differs more than {dev:g}\u00b0 from the majority of the same MPN)", dev=cfg.rot_dev)),
            (tr("📍 PAD = Pad — PickPlace block offset vs paste"),
             tr("(median nearest-pad distance above {tol:g} mm)", tol=cfg.pad_median_tol)),
            (tr("📌 DUP = Duplicate — two components share coordinates"),
             tr("(within {tol:g} mm)", tol=cfg.dup_tol)),
            (tr("⬛ OUT = Out of outline — component outside board outline"),
             tr("(more than {margin:g} mm beyond the board edge)", margin=cfg.out_margin)),
        ]
        for title, desc in legend_items:
            lbl = QLabel(f"{title}<br><span style='color:#666;'>{desc}</span>")
            lbl.setWordWrap(True)
            lv.addWidget(lbl)
        tip = QLabel(tr("💡 Details: check the Flags column in the main table "
                        "and dashed orange frames in Gerber View."))
        tip.setWordWrap(True)
        tip.setStyleSheet(f"color:{muted_color()}; padding-top:4px;")
        lv.addWidget(tip)
        v.addWidget(legend)
        v.addStretch(1)

        self._content_area.addWidget(page)

    def _unreliable_align_layers(self) -> set:
        """Layers whose alignment was overridden by GKO-priority (untrusted)."""
        layers = set()
        results = (self._prescreen_ctx or {}).get("align_results") or {}
        for res_map in results.values():
            if isinstance(res_map, dict):
                for lk, res in res_map.items():
                    if getattr(res, "gko_priority", False):
                        layers.add(lk)
            elif getattr(res_map, "gko_priority", False):
                layers.add("top")
        return layers

    def _run_prescreen_check(self) -> None:
        if getattr(self, "_prescreen_worker", None) is not None and \
                self._prescreen_worker.isRunning():
            return
        self._btn_run_prescreen.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_back.setEnabled(False)
        self._progress_bar.setVisible(True)
        self._lbl_progress.setVisible(True)
        self._progress_bar.setValue(0)
        self._lbl_progress.setText(tr("Starting pre-screen..."))

        cfg = PrescreenConfig(**vars(self._config_mgr.config.prescreen))
        self._prescreen_generation += 1
        gen = self._prescreen_generation

        self._prescreen_worker = PrescreenWorker(
            self._gko_path, self._gtp_path, self._gbp_path,
            self._records, cfg, self._dismissed,
            ctx=self._prescreen_ctx, parent=None,
        )
        worker = self._prescreen_worker
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(lambda *_: worker.deleteLater())
        worker.progress.connect(self._on_worker_progress)
        worker.stats_ready.connect(self._on_prescreen_stats)
        worker.finished.connect(lambda issues, g=gen: self._on_prescreen_finished(issues, g))
        worker.failed.connect(lambda msg, g=gen: self._on_prescreen_failed(msg, g))
        worker.start()

    def _detach_prescreen_worker(self) -> None:
        """Invalidate in-flight results (e.g. dialog is closing)."""
        self._prescreen_generation += 1
        if self._prescreen_worker is not None:
            try:
                self._prescreen_worker.disconnect(self)
            except (RuntimeError, TypeError):
                pass

    def reject(self) -> None:
        self._detach_prescreen_worker()
        super().reject()

    def closeEvent(self, ev) -> None:
        self._detach_prescreen_worker()
        super().closeEvent(ev)

    def _on_prescreen_stats(self, stats: dict) -> None:
        self._prescreen_stats = stats

    def _on_prescreen_finished(self, issues: list, gen: int = -1) -> None:
        if gen != -1 and gen != self._prescreen_generation:
            return
        self._prescreen_worker = None
        self._prescreen_issues = issues
        self._progress_bar.setVisible(False)
        self._lbl_progress.setVisible(False)
        self._btn_run_prescreen.setEnabled(True)
        self._btn_next.setEnabled(True)
        self._btn_back.setEnabled(True)

        counts = summarize(issues)
        total = counts["TOTAL"]
        rec_count = len(self._records) if self._records else 0
        warn_lines = []
        for lk in sorted(self._unreliable_align_layers()):
            layer_label = tr("Top") if lk == "top" else tr("Bottom")
            warn_lines.append(tr(
                "⚠ Layer {layer}: alignment unreliable — PAD/OUT results may be inaccurate.",
                layer=layer_label,
            ))
        if total == 0:
            text = tr("✅ No issues found.") + f" ({rec_count})"
        else:
            lines = [
                tr("🔁 ROT : {n}", n=counts[KIND_ROT]) +
                "      " + tr("📌 DUP : {n}", n=counts[KIND_DUP]),
                tr("📍 PAD : {n}", n=counts[KIND_PAD]) +
                "      " + tr("⬛ OUT : {n}", n=counts[KIND_OUT]),
                tr("Total: {total} / {rec_count} components",
                   total=total, rec_count=rec_count),
            ]
            text = "\n".join(lines)
        st = self._prescreen_stats or {}
        if st.get("n"):
            gauge = tr("📎 Paste match (median): {v} mm over {n} components",
                       v=f"{st['median_mm']:.2f}", n=st["n"])
        else:
            gauge = tr("📎 Paste match: no paste data")
        text = text + "\n" + gauge
        if warn_lines:
            text = text + "\n" + "\n".join(warn_lines)
        self._prescreen_summary.setText(text)
        if total == 0 and not warn_lines:
            self._prescreen_summary.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #16A34A; padding: 6px 0;"
            )
        else:
            self._prescreen_summary.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #D97706; padding: 6px 0;"
            )

    def _on_prescreen_failed(self, message: str, gen: int = -1) -> None:
        if gen != -1 and gen != self._prescreen_generation:
            return
        self._prescreen_worker = None
        self._progress_bar.setVisible(False)
        self._lbl_progress.setVisible(False)
        self._btn_run_prescreen.setEnabled(True)
        self._btn_next.setEnabled(True)
        self._btn_back.setEnabled(True)
        self._prescreen_summary.setText(tr("Pre-screen failed: {message}", message=message))
        self._prescreen_summary.setStyleSheet(
            "font-size: 13px; color: #DC2626; padding: 6px 0;"
        )

    def get_prescreen_result(self):
        return self._prescreen_issues

    def get_prescreen_context(self):
        """(gko, gtp, gbp, ctx) captured after alignment finished.

        ctx is None until the align worker completes; the toolbar Re-check
        button uses this to re-run the same pipeline on edited records.
        """
        return self._gko_path, self._gtp_path, self._gbp_path, self._prescreen_ctx

    def _step_result(self) -> None:
        self._lbl_title.setText(tr("Step 7/7: Alignment Result"))

        self._result_text.setVisible(True)

        _mm_to_mil = 1.0 / 0.0254

        origin_mode_label = tr("Panel Origin") if self._origin_mode == 'panel' else tr("Board Origin")
        mil_conv = tr("Yes (×0.0254)") if self._mil_to_mm else tr("No")

        lines = []
        lines.append(tr("Origin mode: {mode}", mode=origin_mode_label))
        lines.append(tr("Rotation: {angle}°", angle=self._rotation_angle))
        lines.append(tr("mil→mm conversion: {value}", value=mil_conv))
        lines.append(f"")

        pox, poy = self._panel_info.panel_origin
        if self._origin_mode == 'panel':
            w = self._panel_info.panel_w
            h = self._panel_info.panel_h
            ox, oy = 0.0, 0.0
            label = tr('Panel')
        else:
            w = self._panel_info.instances[0].w
            h = self._panel_info.instances[0].h
            ox = self._panel_info.instances[0].origin[0] - pox
            oy = self._panel_info.instances[0].origin[1] - poy
            label = tr('Board')
        lines.append(tr("{label} Width:  {w:.4f} mm  ({wm:.2f} mil)", label=label, w=w, wm=w * _mm_to_mil))
        lines.append(tr("{label} Height: {h:.4f} mm  ({hm:.2f} mil)", label=label, h=h, hm=h * _mm_to_mil))
        lines.append(tr("{label} Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
                        label=label, x=ox, y=oy, xm=ox * _mm_to_mil, ym=oy * _mm_to_mil))
        lines.append(f"")
        lines.append(tr("Per-instance offset results:"))
        lines.append(f"")

        pox, poy = self._panel_info.panel_origin
        for k in sorted(self._align_results.keys()):
            results = self._align_results[k]
            if isinstance(results, dict):
                results = {lk: rr for lk, rr in results.items() if rr.n_total > 0}
            else:
                results = {None: results} if results.n_total > 0 else {}
            if not results:
                continue
            inst = self._panel_info.instances[k]
            ox = inst.origin[0] - pox
            oy = inst.origin[1] - poy
            lines.append(tr("Instance {k}:", k=k))
            lines.append(tr("  Board Width:  {w:.4f} mm ({wm:.2f} mil)", w=inst.w, wm=inst.w * _mm_to_mil))
            lines.append(tr("  Board Height: {h:.4f} mm ({hm:.2f} mil)", h=inst.h, hm=inst.h * _mm_to_mil))
            lines.append(tr("  Board Origin: ({x:.4f}, {y:.4f}) mm  ({xm:.2f}, {ym:.2f}) mil",
                            x=ox, y=oy, xm=ox * _mm_to_mil, ym=oy * _mm_to_mil))
            for lk, r in results.items():
                layer_label = tr("Top") if lk == "top" else (tr("Bottom") if lk == "bottom" else tr("Combined"))
                lines.append(tr("  [{layer}] Offset X: {v:.4f} mm", layer=layer_label, v=r.offset_x))
                lines.append(tr("  [{layer}] Offset Y: {v:.4f} mm", layer=layer_label, v=r.offset_y))
                lines.append(tr("  [{layer}] Offset Rotation: {v:.0f}°", layer=layer_label, v=r.rotation_angle))
                lines.append(tr("  [{layer}] Matched: {m}/{total}, Residual: {r:.6f} mm",
                                layer=layer_label, m=r.n_matched, total=r.n_total, r=r.median_residual))
                if r.gko_priority:
                    lines.append(tr("  [{layer}] WARNING: pad offset (GTP) lệch gốc GKO > {tol} mm; "
                                    "đã ưu tiên GKO — tọa độ giữ nguyên theo file nguồn.",
                                    layer=layer_label, tol=GKO_PRIORITY_TOL))
            lines.append(f"")

        total_unmodified = sum(
            1 for tf in self._transforms
            if tf.new_x is None and tf.new_y is None and tf.new_rotation is None
        )
        total_modified = len(self._transforms) - total_unmodified
        lines.append(tr("Total components: {count}", count=len(self._transforms)))
        lines.append(tr("Aligned: {count}", count=total_modified))
        lines.append(tr("Skipped (unchanged): {count}", count=total_unmodified))

        self._result_text.setText("\n".join(lines))

    def _browse_gko(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select GKO file"), "", "Gerber Files (*.gko *.GKO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gko_path = path
            self._lbl_gko.setText(os.path.basename(path))
            self._lbl_gko.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGko=path)

    def _browse_gtp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select GTP file"), "", "Gerber Files (*.gtp *.GTP *.gpt *.GPT *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gtp_path = path
            self._lbl_gtp.setText(os.path.basename(path))
            self._lbl_gtp.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGtp=path)

    def _browse_gbp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select GBP file"), "", "Gerber Files (*.gbp *.GBP *.gpb *.GPB *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gbp_path = path
            self._lbl_gbp.setText(os.path.basename(path))
            self._lbl_gbp.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGbp=path)

    def _browse_gto(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select GTO file"), "", "Gerber Files (*.gto *.GTO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gto_path = path
            self._lbl_gto.setText(os.path.basename(path))
            self._lbl_gto.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGto=path)

    def _browse_gbo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("Select GBO file"), "", "Gerber Files (*.gbo *.GBO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gbo_path = path
            self._lbl_gbo.setText(os.path.basename(path))
            self._lbl_gbo.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGbo=path)

    def _on_next(self) -> None:
        if self._step_index == 0:
            if not self._gko_path:
                QMessageBox.warning(self, tr("Warning"), tr("Please select the GKO (Outline) file."))
                return
            self._lbl_title.setText(tr("Analyzing Gerber..."))
            try:
                self._panel_info = detect_panel(self._gko_path)
            except Exception as e:
                QMessageBox.critical(self, tr("Error"), tr("Cannot read GKO: {e}", e=e))
                return
            self._show_step(1)
            return
        elif self._step_index == 1:
            self._show_step(2)
            return
        elif self._step_index == 2:
            self._chosen_rotation_angle = self._rot_group.checkedId() if self._rot_group else 0
            self._chosen_mil_to_mm = self._rb_unit_mil.isChecked()
            if getattr(self, "_rb_rot_top", None) is not None:
                self._chosen_rot_layers["top"] = self._rb_rot_top.isChecked()
                self._chosen_rot_layers["bottom"] = self._rb_rot_bottom.isChecked()
            self._show_step(3)
            return
        elif self._step_index == 3:
            if self._worker_done:
                self._show_step(4)
                return
            else:
                self._step_run()
                return
        elif self._step_index == 4:
            self._show_step(5)
            return
        elif self._step_index == 5:
            self._show_step(6)
            return
        elif self._step_index == 6:
            self._save_panel_to_pcb_info()
            self.accept()
            return
        return

    def _save_panel_to_pcb_info(self) -> None:
        if self._panel_info is None:
            return
        pcb = PcbInfoRepo().load()
        pcb.board_width = float(self._panel_info.panel_w)
        pcb.board_height = float(self._panel_info.panel_h)
        pcb.working_area_width = pcb.board_width
        try:
            PcbInfoRepo().save(pcb)
        except RuntimeError:
            return

    def _on_back(self) -> None:
        if self._step_index > 0:
            self._show_step(self._step_index - 1)
            return

    def get_results(self) -> tuple:
        return self._transforms, self._panel_info


class PrescreenCheckDialog(QDialog):
    """Standalone re-run panel for the pre-screen (toolbar Run Check button).

    Non-modal: fix components in Gerber View, then press Run Check again.
    Owns its PrescreenWorker + generation counter; emits checks_finished so
    the main window can apply flags to the table/viewer.
    """

    checks_finished = Signal(list)

    def __init__(
        self,
        records,
        get_bundle,
        dismissed,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._records = records
        self._get_bundle = get_bundle      # () -> (gko, gtp, gbp, ctx) | None
        self._dismissed = dismissed        # live set reference
        self._worker = None
        self._generation = 0
        self._stats = {}

        self.setWindowTitle(tr("Pre-screen Check"))
        self.setMinimumWidth(430)
        v = QVBoxLayout(self)
        v.setContentsMargins(16, 16, 16, 16)
        v.setSpacing(10)

        self._btn_run = QPushButton(tr("▶ Run Check"))
        self._btn_run.setMinimumHeight(36)
        self._btn_run.setStyleSheet(
            "font-size: 15px; font-weight: bold;"
            "background-color: #0D9488; color: white; border-radius: 6px;"
        )
        self._btn_run.clicked.connect(self._run_check)
        v.addWidget(self._btn_run, 0, Qt.AlignHCenter)

        self._summary = QLabel(tr("Not run yet. Press Run Check to scan the board."))
        self._summary.setWordWrap(True)
        self._summary.setStyleSheet("font-size: 14px; padding: 6px 0;")
        v.addWidget(self._summary)

        self._progress = QLabel("")
        self._progress.setVisible(False)
        v.addWidget(self._progress)

        hint = QLabel(tr("💡 Details: check the Flags column in the main table "
                         "and dashed orange frames in Gerber View."))
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{muted_color()}; padding-top:4px;")
        v.addWidget(hint)

        row = QHBoxLayout()
        row.addStretch(1)
        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(self.close)
        row.addWidget(btn_close)
        v.addLayout(row)

    # ------------------------------------------------------------------ run

    def _unreliable_layers(self) -> set:
        bundle = self._get_bundle() or (None, None, None, None)
        ctx = bundle[3] or {}
        out = set()
        for _k, layer_results in (ctx.get("align_results") or {}).items():
            for layer, res in (layer_results or {}).items():
                try:
                    n_total = getattr(res, "n_total", 0) or 0
                    ratio = (getattr(res, "n_matched", 0) / n_total) if n_total else 0.0
                    unreliable = (
                        getattr(res, "gko_priority", False)
                        and (n_total == 0 or ratio < 0.5
                             or getattr(res, "median_residual", 0.0) > 0.5)
                    )
                    if unreliable:
                        out.add(layer)
                except AttributeError:
                    continue
        return out

    def _show_note(self, text: str, color: str = "#DC2626") -> None:
        self._progress.setVisible(False)
        self._summary.setText(text)
        self._summary.setStyleSheet(f"font-size: 14px; color: {color}; padding: 6px 0;")

    def _run_check(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        bundle = self._get_bundle()
        if not bundle or bundle[3] is None:
            self._show_note(tr("Run Align PickPlace Origin once to enable Run Check."))
            return
        gko, gtp, gbp, ctx = bundle
        if not gko or not os.path.exists(gko):
            self._show_note(tr("Gerber outline file (GKO) is missing — run Align PickPlace Origin again."))
            return

        cfg = PrescreenConfig(**vars(ConfigManager.instance().config.prescreen))
        self._generation += 1
        gen = self._generation
        self._btn_run.setEnabled(False)
        self._progress.setVisible(True)
        self._progress.setText(tr("Starting pre-screen..."))

        worker = PrescreenWorker(
            gko, gtp, gbp, self._records, cfg,
            dismissed=set(self._dismissed), ctx=ctx, parent=None,
        )
        self._worker = worker
        worker.progress.connect(self._on_progress)
        worker.stats_ready.connect(self._on_stats)
        worker.finished.connect(lambda issues, g=gen: self._on_finished(issues, g))
        worker.failed.connect(lambda msg, g=gen: self._on_failed(msg, g))
        worker.start()

    # ------------------------------------------------------------- handlers

    def _detach_worker(self) -> None:
        self._generation += 1
        if self._worker is not None:
            try:
                self._worker.disconnect(self)
            except (RuntimeError, TypeError):
                pass

    def closeEvent(self, ev) -> None:
        self._detach_worker()
        super().closeEvent(ev)

    def reject(self) -> None:
        self._detach_worker()
        super().reject()

    def _on_progress(self, message: str, _pct: int) -> None:
        self._progress.setText(message)

    def _on_stats(self, stats: dict) -> None:
        self._stats = stats

    def _on_finished(self, issues: list, gen: int = -1) -> None:
        if gen != -1 and gen != self._generation:
            return
        self._worker = None
        self._btn_run.setEnabled(True)
        self._progress.setVisible(False)

        counts = summarize(issues)
        total = counts["TOTAL"]
        rec_count = len(self._records) if self._records else 0
        warn_lines = []
        for lk in sorted(self._unreliable_layers()):
            layer_label = tr("Top") if lk == "top" else tr("Bottom")
            warn_lines.append(tr(
                "⚠ Layer {layer}: alignment unreliable — PAD/OUT results may be inaccurate.",
                layer=layer_label,
            ))
        if total == 0:
            text = tr("✅ No issues found.") + f" ({rec_count})"
        else:
            lines = [
                tr("🔁 ROT : {n}", n=counts[KIND_ROT]) +
                "      " + tr("📌 DUP : {n}", n=counts[KIND_DUP]),
                tr("📍 PAD : {n}", n=counts[KIND_PAD]) +
                "      " + tr("⬛ OUT : {n}", n=counts[KIND_OUT]),
                tr("Total: {total} / {rec_count} components",
                   total=total, rec_count=rec_count),
            ]
            text = "\n".join(lines)
        st = self._stats or {}
        if st.get("n"):
            gauge = tr("📎 Paste match (median): {v} mm over {n} components",
                       v=f"{st['median_mm']:.2f}", n=st["n"])
        else:
            gauge = tr("📎 Paste match: no paste data")
        text = text + "\n" + gauge
        if warn_lines:
            text = text + "\n" + "\n".join(warn_lines)
        self._summary.setText(text)
        if total == 0 and not warn_lines:
            self._summary.setStyleSheet(
                "font-size: 15px; font-weight: bold; color: #16A34A; padding: 6px 0;"
            )
        else:
            self._summary.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #D97706; padding: 6px 0;"
            )
        self.checks_finished.emit(list(issues))

    def _on_failed(self, message: str, gen: int = -1) -> None:
        if gen != -1 and gen != self._generation:
            return
        self._worker = None
        self._btn_run.setEnabled(True)
        self._show_note(tr("Pre-screen failed: {message}", message=message))
