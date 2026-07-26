from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QMessageBox, QSpinBox, QFormLayout, QGroupBox, QLineEdit,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeyEvent
import pyautogui
import win32gui

from config.config_manager import ConfigManager
from models.config import AppConfig, Point


class CalibrationWizard(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config_mgr = ConfigManager.instance()
        self._step_index: int = 0
        self._positions: list = [Point(), Point()]
        self._window_title: str = ""
        self._countdown: int = 0

        self.setWindowTitle("Calibration Wizard")
        self.setMinimumWidth(520)
        self.setWindowFlags(Qt.Window | Qt.WindowStaysOnTopHint | Qt.WindowCloseButtonHint)

        self._build_ui()
        self._show_step(0)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        self._lbl_title = QLabel()
        self._lbl_title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self._lbl_title)

        self._lbl_instruction = QLabel()
        self._lbl_instruction.setWordWrap(True)
        self._lbl_instruction.setStyleSheet("font-size: 14px; padding: 10px;")
        layout.addWidget(self._lbl_instruction)

        self._lbl_position = QLabel("No positions captured yet.")
        self._lbl_position.setWordWrap(True)
        self._lbl_position.setStyleSheet(
            "font-size: 12px; color: #006600; background: #f0fff0; padding: 8px; border: 1px solid #ccc;"
        )
        layout.addWidget(self._lbl_position)

        self._lbl_countdown = QLabel()
        self._lbl_countdown.setAlignment(Qt.AlignCenter)
        self._lbl_countdown.setStyleSheet(
            "font-size: 48px; font-weight: bold; color: #cc0000;"
        )
        self._lbl_countdown.setVisible(False)
        layout.addWidget(self._lbl_countdown)

        self._window_title_layout = QHBoxLayout()
        self._window_title_layout.setContentsMargins(0, 0, 0, 0)
        self._lbl_window_title = QLabel("Window title:")
        self._lbl_window_title.setVisible(False)
        self._txt_window_title = QLineEdit()
        self._txt_window_title.setPlaceholderText("e.g. CAM350 V15")
        self._txt_window_title.setVisible(False)
        self._btn_detect_title = QPushButton("Detect")
        self._btn_detect_title.clicked.connect(self._detect_title)
        self._btn_detect_title.setVisible(False)
        self._window_title_layout.addWidget(self._lbl_window_title)
        self._window_title_layout.addWidget(self._txt_window_title, 1)
        self._window_title_layout.addWidget(self._btn_detect_title)
        layout.addLayout(self._window_title_layout)

        self._delay_group = QGroupBox("Delay Settings")
        delay_layout = QFormLayout(self._delay_group)
        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(50, 2000)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.setValue(self._config_mgr.config.delay)
        delay_layout.addRow("Jump delay:", self._delay_spin)
        layout.addWidget(self._delay_group)

        btn_layout = QHBoxLayout()
        self._btn_capture = QPushButton("Start Capture (3s countdown)")
        self._btn_capture.clicked.connect(self._start_countdown)
        self._btn_capture.setMinimumHeight(40)

        self._btn_skip = QPushButton("Skip")
        self._btn_skip.clicked.connect(self._skip_step)

        self._btn_save = QPushButton("Save && Close")
        self._btn_save.clicked.connect(self._save_and_close)
        self._btn_save.setVisible(False)

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self.close)

        btn_layout.addWidget(self._btn_capture)
        btn_layout.addWidget(self._btn_skip)
        btn_layout.addWidget(self._btn_save)
        btn_layout.addWidget(self._btn_cancel)
        layout.addLayout(btn_layout)

        self._countdown_timer = QTimer(self)
        self._countdown_timer.timeout.connect(self._tick_countdown)

    def _show_step(self, step: int) -> None:
        self._countdown_timer.stop()
        self._lbl_countdown.setVisible(False)
        self._btn_capture.setEnabled(True)

        if step >= 3:
            self._finish()
            return

        if step < 2:
            name, instruction = [
                ("X Textbox", "1. Move mouse over CAM350 X textbox\n2. Click 'Start Capture'\n3. Wait 3 seconds - position auto-saved"),
                ("Y Textbox", "1. Move mouse over CAM350 Y textbox\n2. Click 'Start Capture'\n3. Wait 3 seconds - position auto-saved"),
            ][step]
            self._lbl_title.setText(f"Step {step + 1} of 3: {name}")
            self._lbl_instruction.setText(instruction)
            self._btn_capture.setText("Start Capture (3s countdown)")
        else:
            self._lbl_title.setText("Step 3 of 3: CAM350 Window")
            self._lbl_instruction.setText("Activate CAM350 window, then click 'Detect', or type window title manually:")

        self._refresh_status()
        self._btn_capture.setVisible(True)
        self._btn_skip.setVisible(step < 2)
        self._btn_save.setVisible(step == 2)

        is_window_step = (step == 2)
        self._lbl_window_title.setVisible(is_window_step)
        self._txt_window_title.setVisible(is_window_step)
        self._btn_detect_title.setVisible(is_window_step)
        if is_window_step:
            self._txt_window_title.setText(self._window_title)
            self._btn_capture.setVisible(False)

    def _refresh_status(self) -> None:
        lines = []
        for i in range(2):
            pos = self._positions[i]
            if pos.x or pos.y:
                label = "X Textbox" if i == 0 else "Y Textbox"
                lines.append(f"✓ {label}: ({pos.x}, {pos.y})")
        if self._window_title:
            lines.append(f"✓ Window: {self._window_title}")
        if self._step_index < 2:
            pos = self._positions[self._step_index]
            if not pos.x and not pos.y:
                label = "X Textbox" if self._step_index == 0 else "Y Textbox"
                lines.append(f"? {label}: not set")
        elif self._step_index == 2 and not self._window_title:
            lines.append("? Window title: not set")

        self._lbl_position.setText("\n".join(lines) if lines else "No positions captured yet.")

    def _start_countdown(self) -> None:
        self._countdown = 3
        self._lbl_countdown.setText(str(self._countdown))
        self._lbl_countdown.setVisible(True)
        self._btn_capture.setEnabled(False)
        self._btn_capture.setText("Capturing in 3s...")
        self._countdown_timer.start(1000)

    def _tick_countdown(self) -> None:
        self._countdown -= 1
        if self._countdown <= 0:
            self._countdown_timer.stop()
            self._capture_position()
        else:
            self._lbl_countdown.setText(str(self._countdown))
            self._btn_capture.setText(f"Capturing in {self._countdown}s...")

    def _capture_position(self) -> None:
        x, y = pyautogui.position()
        self._positions[self._step_index] = Point(x=int(x), y=int(y))
        self._step_index += 1
        self._show_step(self._step_index)

    def _detect_title(self) -> None:
        hwnd = win32gui.GetForegroundWindow()
        if hwnd:
            title = win32gui.GetWindowText(hwnd)
            self._txt_window_title.setText(title)
            self._window_title = title
            self._refresh_status()
        else:
            QMessageBox.warning(self, "Warning", "No active window detected.")

    def _skip_step(self) -> None:
        self._step_index += 1
        self._show_step(self._step_index)

    def _finish(self) -> None:
        self._lbl_title.setText("Calibration Complete")
        self._lbl_instruction.setText("All positions captured. Review and click Save & Close.")
        self._lbl_window_title.setVisible(False)
        self._txt_window_title.setVisible(False)
        self._btn_detect_title.setVisible(False)
        self._refresh_status()
        self._btn_capture.setVisible(False)
        self._btn_skip.setVisible(False)
        self._btn_save.setVisible(True)

    def _save_and_close(self) -> None:
        self._window_title = self._txt_window_title.text().strip()
        config = AppConfig(
            windowTitle=self._window_title,
            xTextbox=self._positions[0],
            yTextbox=self._positions[1],
            delay=self._delay_spin.value(),
        )
        self._config_mgr.config = config
        QMessageBox.information(self, "Success", "Calibration saved successfully.")
        self.close()
