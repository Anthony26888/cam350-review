import os
from typing import Optional, List, Dict, Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QProgressBar, QGroupBox,
    QFormLayout, QRadioButton, QButtonGroup, QCheckBox,
    QTextEdit, QWidget, QApplication,
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal

MACRO_SWITCH_DELAY_S = 5

from config.config_manager import ConfigManager
from database.pcb_info_repo import PcbInfoRepo
from models.pcb_info import PcbInfo
from models.pickplace import PickPlaceData, PickPlaceComponent
from models.review import ReviewRecord
from services.cam350_controller import Cam350Controller
from services.gerber.gerber_parser import parse_flashes
from services.gerber.panel_detector import detect_panel, PanelInfo
from services.gerber.origin_aligner import AlignResult, align_instance
from services.gerber.offset_applier import (
    ComponentTransform, apply_all_transforms, round_coord, _layer_frame,
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
            self.progress.emit("Phát hiện panel từ GKO...", 5)
            panel_info = detect_panel(self._gko_path)

            self.progress.emit(f"Phát hiện: {panel_info.kind}, {panel_info.count} instance(s)", 10)

            gtp_pts = None
            gbp_pts = None

            if self._gtp_path and os.path.exists(self._gtp_path):
                self.progress.emit("Đọc GTP (Top Paste)...", 15)
                gtp_pts = parse_flashes(self._gtp_path)

            if self._gbp_path and os.path.exists(self._gbp_path):
                self.progress.emit("Đọc GBP (Bottom Paste)...", 20)
                gbp_pts = parse_flashes(self._gbp_path)

            scale = 0.0254 if self._mil_to_mm else 1.0

            self.progress.emit("Tính toán offset cho từng instance...", 30)

            align_results = {}

            comps = self._pickplace.components
            top_comps = [c for c in comps if _layer_frame(c.layer) == "top"]
            bot_comps = [c for c in comps if _layer_frame(c.layer) == "bottom"]

            total_instances = panel_info.count
            for i, instance in enumerate(panel_info.instances):
                pct = 30 + int((i / total_instances) * 40)
                self.progress.emit(
                    f"Instance {i + 1}/{total_instances}: {instance.sub_name or 'board'}...", pct
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

            self.progress.emit("Tạo transforms...", 80)

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

            self.progress.emit("Hoàn tất tính toán.", 100)
            self.finished.emit(align_results, transforms, panel_info, self._origin_mode, self._rotation_angle)

        except Exception as e:
            self.progress.emit(f"Lỗi: {e}", -1)


class OriginAlignWizard(QDialog):
    def __init__(
        self,
        pickplace_data: PickPlaceData,
        records: List[ReviewRecord],
        apply_callback: Callable,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._pickplace_data = pickplace_data
        self._records = records
        self._apply_callback = apply_callback
        self._config_mgr = ConfigManager.instance()
        self._cam350 = Cam350Controller()

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

        self._btn_back = QPushButton("◀ Back")
        self._btn_back.clicked.connect(self._on_back)
        self._btn_back.setMinimumHeight(36)
        self._btn_back.setVisible(False)

        self._btn_next = QPushButton("Next ▶")
        self._btn_next.clicked.connect(self._on_next)
        self._btn_next.setMinimumHeight(36)

        self._btn_cancel = QPushButton("Cancel")
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
            self._step_result,
        ]

        if step < len(steps):
            steps[step]()

        self._btn_back.setVisible(step > 0 and step < len(steps) - 1)
        self._btn_next.setText("Finish" if step == len(steps) - 1 else "Next ▶")
        self._btn_cancel.setVisible(step < len(steps) - 1)

    def _step_files(self) -> None:
        self._lbl_title.setText("Step 1/6: Chọn file Gerber")

        group = QGroupBox("Gerber Files")
        form = QFormLayout(group)

        gko_layout = QHBoxLayout()
        self._lbl_gko = QLabel("(chưa chọn)")
        self._lbl_gko.setStyleSheet("color: #888;")
        btn_gko = QPushButton("Browse...")
        btn_gko.clicked.connect(self._browse_gko)
        gko_layout.addWidget(self._lbl_gko, 1)
        gko_layout.addWidget(btn_gko)
        form.addRow("GKO (Outline) *:", gko_layout)

        gtp_layout = QHBoxLayout()
        self._lbl_gtp = QLabel("(không bắt buộc)")
        self._lbl_gtp.setStyleSheet("color: #888;")
        btn_gtp = QPushButton("Browse...")
        btn_gtp.clicked.connect(self._browse_gtp)
        gtp_layout.addWidget(self._lbl_gtp, 1)
        gtp_layout.addWidget(btn_gtp)
        form.addRow("GTP (Top Paste):", gtp_layout)

        gbp_layout = QHBoxLayout()
        self._lbl_gbp = QLabel("(không bắt buộc)")
        self._lbl_gbp.setStyleSheet("color: #888;")
        btn_gbp = QPushButton("Browse...")
        btn_gbp.clicked.connect(self._browse_gbp)
        gbp_layout.addWidget(self._lbl_gbp, 1)
        gbp_layout.addWidget(btn_gbp)
        form.addRow("GBP (Bottom Paste):", gbp_layout)

        gto_layout = QHBoxLayout()
        self._lbl_gto = QLabel("(không bắt buộc)")
        self._lbl_gto.setStyleSheet("color: #888;")
        btn_gto = QPushButton("Browse...")
        btn_gto.clicked.connect(self._browse_gto)
        gto_layout.addWidget(self._lbl_gto, 1)
        gto_layout.addWidget(btn_gto)
        form.addRow("GTO (Top Overlay / Silkscreen):", gto_layout)

        gbo_layout = QHBoxLayout()
        self._lbl_gbo = QLabel("(không bắt buộc)")
        self._lbl_gbo.setStyleSheet("color: #888;")
        btn_gbo = QPushButton("Browse...")
        btn_gbo.clicked.connect(self._browse_gbo)
        gbo_layout.addWidget(self._lbl_gbo, 1)
        gbo_layout.addWidget(btn_gbo)
        form.addRow("GBO (Bottom Overlay / Silkscreen):", gbo_layout)

        info = QLabel(
            "* GKO là bắt buộc (Gerber Outline).\n"
            "GTP/GBP giúp dò offset chính xác hơn (khuyến nghị).\n"
            "GTO/GBO (tên/designator trên board) chỉ dùng để hiển thị trong Gerber View."
        )
        info.setStyleSheet("color: #666; font-style: italic; margin-top: 8px;")

        self._content_area.addWidget(group)
        self._content_area.addWidget(info)

    def _step_panel_check(self) -> None:
        self._lbl_title.setText("Step 2/6: Kết quả phát hiện Panel")

        panel_info = self._panel_info
        if not panel_info:
            return

        pox, poy = panel_info.panel_origin

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumHeight(200)

        _mm_to_mil = 1.0 / 0.0254

        lines = []
        lines.append(f"Loại: {'Panel Kiểu A (step-repeat)' if panel_info.kind == 'A' else 'Panel Kiểu B (nhiều block)' if panel_info.kind == 'B' else 'Board đơn'}")
        lines.append(f"Số instance: {panel_info.count}")
        lines.append(f"")
        lines.append(f"Panel Origin: ({pox:.4f}, {poy:.4f}) mm  ({pox * _mm_to_mil:.2f}, {poy * _mm_to_mil:.2f}) mil")
        lines.append(f"Panel Width:  {panel_info.panel_w:.4f} mm  ({panel_info.panel_w * _mm_to_mil:.2f} mil)")
        lines.append(f"Panel Height: {panel_info.panel_h:.4f} mm  ({panel_info.panel_h * _mm_to_mil:.2f} mil)")
        lines.append(f"")

        for inst in panel_info.instances:
            ox, oy = inst.origin
            layer_tag = f" [layer: {inst.sub_name}]" if inst.sub_name else ""
            lines.append(
                f"  Instance {inst.k}{layer_tag}:"
            )
            lines.append(
                f"    origin=({ox - pox:.4f}, {oy - poy:.4f}) mm  "
                f"({(ox - pox) * _mm_to_mil:.2f}, {(oy - poy) * _mm_to_mil:.2f}) mil"
            )
            lines.append(
                f"    w={inst.w:.4f} mm ({inst.w * _mm_to_mil:.2f} mil)  "
                f"h={inst.h:.4f} mm ({inst.h * _mm_to_mil:.2f} mil)"
            )

        text.setText("\n".join(lines))
        self._content_area.addWidget(text)

        if panel_info.is_panel:
            info = QLabel(
                "Panel đã được phát hiện. Bước tiếp theo cho phép chọn chế độ gốc toạ độ."
            )
            info.setStyleSheet("color: #006600; font-weight: bold; margin-top: 8px;")
            self._content_area.addWidget(info)

    def _step_options(self) -> None:
        self._lbl_title.setText("Step 3/6: Tuỳ chọn xoay và đơn vị")

        panel_info = self._panel_info
        if not panel_info:
            return

        rot_group = QGroupBox("Xoay Panel/Board")
        rot_layout = QVBoxLayout(rot_group)

        self._rot_group = QButtonGroup(self)
        angles = [(0, "0° (không xoay) — mặc định"), (90, "90°")]
        self._rb_rot = {}
        for val, label in angles:
            rb = QRadioButton(label)
            if val == 0:
                rb.setChecked(True)
            self._rot_group.addButton(rb, val)
            self._rb_rot[val] = rb
            rot_layout.addWidget(rb)
        self._content_area.addWidget(rot_group)

        self._rot_layer_group = QGroupBox("Chọn layer áp dụng công thức xoay 90°")
        layer_layout = QVBoxLayout(self._rot_layer_group)
        self._chk_rot_top = QCheckBox("Top layer — công thức 90°: (x, -(H-y))")
        self._chk_rot_top.setChecked(True)
        self._chk_rot_bottom = QCheckBox("Bottom layer — công thức 90°: (x, y)")
        self._chk_rot_bottom.setChecked(False)
        layer_layout.addWidget(self._chk_rot_top)
        layer_layout.addWidget(self._chk_rot_bottom)
        self._content_area.addWidget(self._rot_layer_group)

        def _toggle_rot_layers(checked: bool) -> None:
            self._rot_layer_group.setVisible(checked)
            self._rot_layer_group.setEnabled(checked)

        self._rb_rot[90].toggled.connect(_toggle_rot_layers)
        _toggle_rot_layers(self._rb_rot[90].isChecked())

        unit_group = QGroupBox("Đơn vị toạ độ PickPlace")
        unit_layout = QVBoxLayout(unit_group)

        self._rb_unit_mm = QRadioButton("mm (milimét) — mặc định")
        self._rb_unit_mm.setChecked(True)
        self._rb_unit_mil = QRadioButton("mil (chuyển đổi sang mm: * 0.0254)")

        unit_layout.addWidget(self._rb_unit_mm)
        unit_layout.addWidget(self._rb_unit_mil)
        self._content_area.addWidget(unit_group)

    def _step_run(self) -> None:
        self._lbl_title.setText("Step 4/6: Đang tính toán offset...")

        self._progress_bar.setVisible(True)
        self._lbl_progress.setVisible(True)
        self._progress_bar.setValue(0)
        self._lbl_progress.setText("Bắt đầu tính toán...")

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

        self._lbl_title.setText("Step 4/6: Đang cập nhật dữ liệu...")

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
            self._lbl_progress.setText(f"Đã cập nhật {updated_count}/{total}")
            if i % 30 == 0:
                QApplication.processEvents()

        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(100)
        self._lbl_progress.setText(f"Hoàn tất! {updated_count} components đã được căn chỉnh.")

        self._worker_done = True
        self._btn_next.setEnabled(True)
        self._btn_next.setText("Next ▶")
        self._btn_back.setEnabled(True)
        self._btn_cancel.setEnabled(True)

    def _step_macro(self) -> None:
        self._lbl_title.setText("Step 5/6: Lấy Panel Origin từ CAM350 (Macro)")

        layer_group = QGroupBox("Layer")
        layer_layout = QVBoxLayout(layer_group)

        self._rb_layer_top = QRadioButton("Top layer (mặc định)")
        self._rb_layer_top.setChecked(True)
        self._rb_layer_bottom = QRadioButton("Bottom layer")

        self._layer_group = QButtonGroup(self)
        self._layer_group.addButton(self._rb_layer_top)
        self._layer_group.addButton(self._rb_layer_bottom)

        layer_layout.addWidget(self._rb_layer_top)
        layer_layout.addWidget(self._rb_layer_bottom)
        self._content_area.addWidget(layer_group)

        group = QGroupBox("Macro")
        layout = QVBoxLayout(group)

        info = QLabel(
            "Nhấn nút bên dưới để chạy macro trên CAM350:\n"
            "1. Sau khi bấm Run Macro, app đợi 5 giây — hãy chuyển sang cửa sổ CAM350 trong lúc đó\n"
            "2. Nếu Step 2 chọn xoay 90°: chương trình bấm Ctrl+Alt+R để xoay board 90° trước\n"
            "3. Top layer: Ctrl+Alt+X (hiện marker Space Origin) → jump tới Panel Origin (từ Step 2)\n"
            "4. Bottom layer: Ctrl+Alt+B (xem Bottom) → Ctrl+Alt+X → jump tới tọa độ biến đổi tương ứng\n"
            "5. Xác nhận thông báo hiện lên bằng phím Enter\n"
            "\n"
            "Lưu ý: CAM350 phải đang hiển thị đơn vị mm để tọa độ jump chính xác."
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #666; padding: 4px 0;")
        layout.addWidget(info)

        self._btn_run_macro = QPushButton("Run Macro ▶")
        self._btn_run_macro.setMinimumHeight(36)
        self._btn_run_macro.setStyleSheet("background-color: #0D9488; color: white; font-weight: bold;")
        self._btn_run_macro.clicked.connect(self._run_macro)
        layout.addWidget(self._btn_run_macro)

        self._lbl_macro_status = QLabel("Chưa chạy.")
        self._lbl_macro_status.setWordWrap(True)
        self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #006600; background: #f0fff0; padding: 8px; border: 1px solid #ccc;")
        layout.addWidget(self._lbl_macro_status)

        self._content_area.addWidget(group)

        cfg = self._config_mgr.config
        if (not cfg.xTextbox.x) or (not cfg.yTextbox.x):
            self._btn_run_macro.setEnabled(False)
            self._lbl_macro_status.setText("CAM350 chưa được calibrate. Vui lòng chạy Calibration Wizard trước.")
            self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #cc0000; background: #fff0f0; padding: 8px; border: 1px solid #ccc;")
            return
        else:
            if self._macro_x is None:
                return
            if self._macro_y is None:
                return
            layer_label = "Top" if self._macro_layer == "top" else "Bottom"
            self._lbl_macro_status.setText(f"Đã lấy Panel Origin ({layer_label}): X = {self._macro_x:.4f}, Y = {self._macro_y:.4f}")
            return

    def _run_macro(self) -> None:
        if self._macro_running:
            return
        self._macro_running = True
        self._btn_run_macro.setEnabled(False)
        self._btn_next.setEnabled(False)
        self._btn_back.setEnabled(False)
        self._btn_cancel.setEnabled(False)

        self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #006600; background: #f0fff0; padding: 8px; border: 1px solid #ccc;")

        self._macro_countdown = MACRO_SWITCH_DELAY_S
        self._lbl_macro_status.setText(f"Vui lòng chuyển sang cửa sổ CAM350 trong {self._macro_countdown} giây...")
        QApplication.processEvents()
        self._macro_timer.start(1000)

    def _tick_macro_countdown(self) -> None:
        self._macro_countdown -= 1
        if self._macro_countdown <= 0:
            self._macro_timer.stop()
            self._execute_macro()
            return
        self._lbl_macro_status.setText(f"Vui lòng chuyển sang cửa sổ CAM350 trong {self._macro_countdown} giây...")

    def _execute_macro(self) -> None:
        self._lbl_macro_status.setText("Đang chạy macro trên CAM350...")
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
            error = "Chưa có dữ liệu Panel Origin từ Step 2."

        self._lbl_macro_status.setText(f"Đang chạy macro trên CAM350... (layer={layer}, angle={angle_deg}°, jump=({ox}, {oy}))")
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
            self._lbl_macro_status.setText(f"Macro thất bại: {error}")
            self._lbl_macro_status.setStyleSheet("font-size: 12px; color: #cc0000; background: #fff0f0; padding: 8px; border: 1px solid #ccc;")
            return

        self._macro_layer = layer
        self._macro_x = ox
        self._macro_y = oy
        layer_label = "Top" if layer == "top" else "Bottom"
        self._lbl_macro_status.setText(f"Đã lấy Panel Origin ({layer_label}): X = {ox:.4f}, Y = {oy:.4f}")

    def _step_result(self) -> None:
        self._lbl_title.setText("Step 6/6: Kết quả Alignment")

        self._result_text.setVisible(True)

        _mm_to_mil = 1.0 / 0.0254

        lines = []
        lines.append(f"Chế độ gốc: {'Panel Origin' if self._origin_mode == 'panel' else 'Board Origin'}")
        lines.append(f"Xoay: {self._rotation_angle}°")
        lines.append(f"Chuyển đổi mil→mm: {'Có (×0.0254)' if self._mil_to_mm else 'Không'}")
        lines.append(f"")

        pox, poy = self._panel_info.panel_origin
        if self._origin_mode == 'panel':
            w = self._panel_info.panel_w
            h = self._panel_info.panel_h
            ox, oy = 0.0, 0.0
            label = 'Panel'
        else:
            w = self._panel_info.instances[0].w
            h = self._panel_info.instances[0].h
            ox = self._panel_info.instances[0].origin[0] - pox
            oy = self._panel_info.instances[0].origin[1] - poy
            label = 'Board'
        lines.append(f"{label} Width:  {w:.4f} mm  ({w * _mm_to_mil:.2f} mil)")
        lines.append(f"{label} Height: {h:.4f} mm  ({h * _mm_to_mil:.2f} mil)")
        lines.append(f"{label} Origin: ({ox:.4f}, {oy:.4f}) mm  ({ox * _mm_to_mil:.2f}, {oy * _mm_to_mil:.2f}) mil")
        lines.append(f"")
        lines.append(f"Kết quả offset từng instance:")
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
            lines.append(f"Instance {k}:")
            lines.append(f"  Board Width:  {inst.w:.4f} mm ({inst.w * _mm_to_mil:.2f} mil)")
            lines.append(f"  Board Height: {inst.h:.4f} mm ({inst.h * _mm_to_mil:.2f} mil)")
            lines.append(f"  Board Origin: ({ox:.4f}, {oy:.4f}) mm  ({ox * _mm_to_mil:.2f}, {oy * _mm_to_mil:.2f}) mil")
            for lk, r in results.items():
                layer_label = "Top" if lk == "top" else ("Bottom" if lk == "bottom" else "Gộp")
                lines.append(f"  [{layer_label}] Offset X: {r.offset_x:.4f} mm")
                lines.append(f"  [{layer_label}] Offset Y: {r.offset_y:.4f} mm")
                lines.append(f"  [{layer_label}] Offset Rotation: {r.rotation_angle:.0f}°")
                lines.append(f"  [{layer_label}] Matched: {r.n_matched}/{r.n_total}, Residual: {r.median_residual:.6f} mm")
            lines.append(f"")

        total_unmodified = sum(
            1 for tf in self._transforms
            if tf.new_x is None and tf.new_y is None and tf.new_rotation is None
        )
        total_modified = len(self._transforms) - total_unmodified
        lines.append(f"Tổng số components: {len(self._transforms)}")
        lines.append(f"Đã căn chỉnh: {total_modified}")
        lines.append(f"Bỏ qua (không thay đổi): {total_unmodified}")

        self._result_text.setText("\n".join(lines))

    def _browse_gko(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file GKO", "", "Gerber Files (*.gko *.GKO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gko_path = path
            self._lbl_gko.setText(os.path.basename(path))
            self._lbl_gko.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGko=path)

    def _browse_gtp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file GTP", "", "Gerber Files (*.gtp *.GTP *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gtp_path = path
            self._lbl_gtp.setText(os.path.basename(path))
            self._lbl_gtp.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGtp=path)

    def _browse_gbp(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file GBP", "", "Gerber Files (*.gbp *.GBP *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gbp_path = path
            self._lbl_gbp.setText(os.path.basename(path))
            self._lbl_gbp.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGbp=path)

    def _browse_gto(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file GTO", "", "Gerber Files (*.gto *.GTO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gto_path = path
            self._lbl_gto.setText(os.path.basename(path))
            self._lbl_gto.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGto=path)

    def _browse_gbo(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Chọn file GBO", "", "Gerber Files (*.gbo *.GBO *.gbr *.GBR);;All Files (*.*)")
        if path:
            self._gbo_path = path
            self._lbl_gbo.setText(os.path.basename(path))
            self._lbl_gbo.setStyleSheet("color: #000;")
            self._config_mgr.update(gerberGbo=path)

    def _on_next(self) -> None:
        if self._step_index == 0:
            if not self._gko_path:
                QMessageBox.warning(self, "Warning", "Vui lòng chọn file GKO (Outline).")
                return
            self._lbl_title.setText("Đang phân tích Gerber...")
            try:
                self._panel_info = detect_panel(self._gko_path)
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Không thể đọc GKO: {e}")
                return
            self._show_step(1)
            return
        elif self._step_index == 1:
            self._show_step(2)
            return
        elif self._step_index == 2:
            self._chosen_rotation_angle = self._rot_group.checkedId() if self._rot_group else 0
            self._chosen_mil_to_mm = self._rb_unit_mil.isChecked()
            if getattr(self, "_chk_rot_top", None) is not None:
                self._chosen_rot_layers["top"] = self._chk_rot_top.isChecked()
                self._chosen_rot_layers["bottom"] = self._chk_rot_bottom.isChecked()
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