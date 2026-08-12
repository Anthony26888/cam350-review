import ctypes
from ctypes import wintypes
from typing import Dict, Optional

from PySide6.QtCore import QAbstractNativeEventFilter, QObject
from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QGroupBox, QFormLayout, QLineEdit, QDoubleSpinBox, QMessageBox,
    QApplication, QLabel,
)

from database.pcb_info_repo import PcbInfoRepo
from ui.i18n import tr
from models.pcb_info import PcbInfo
from services.cam350_controller import Cam350Controller

HOTKEY_ID = 0x3501
HOTKEY_COMBO = "Ctrl+Alt+Z"
WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000

_user32 = ctypes.windll.user32


class _HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self.callback = callback

    def nativeEventFilter(self, eventType, message):
        try:
            if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
                msg = ctypes.cast(
                    int(message), ctypes.POINTER(wintypes.MSG)
                ).contents
                if msg.message == WM_HOTKEY and msg.wParam == HOTKEY_ID:
                    if self.callback is not None:
                        self.callback()
                    return True, 0
        except Exception:
            pass
        return False, 0


class PcbInfoDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._repo = PcbInfoRepo()
        self._cam350 = Cam350Controller()
        self._hotkey_filter: Optional[_HotkeyFilter] = None
        self.setWindowTitle(tr("PCB Info"))
        self.setModal(True)
        self.setMinimumWidth(520)
        self._boc_edits: Dict[str, QLineEdit] = {}
        self._build_ui()
        self._load()
        self._register_hotkey()

    def _numeric_field(self, decimals: int = 4) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-1000000.0, 1000000.0)
        spin.setDecimals(decimals)
        return spin

    def _boc_row(self, label: str) -> QWidget:
        row = QHBoxLayout()
        row.setSpacing(8)
        edit = QLineEdit()
        edit.setPlaceholderText(tr(label))
        edit.setMinimumWidth(150)
        edit.textChanged.connect(self._update_save_visibility)
        self._boc_edits[label] = edit
        row.addWidget(edit, 1)
        container = QWidget()
        container.setLayout(row)
        return container

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        hint = QLabel(
            tr("Hotkey {hk}: point the mouse at the desired position in CAM350 "
               "then press the hotkey to read coordinates.\n"
               "The macro auto-fills X Boc 1 & Y Boc 1, the 2nd time fills "
               "Boc 2, the 3rd time fills Boc 3. The Save button appears after enough data.",
               hk=HOTKEY_COMBO)
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #0F766E; font-weight: bold; padding: 4px 0;")
        layout.addWidget(hint)

        board_group = QGroupBox(tr("Board"))
        board_form = QFormLayout(board_group)
        self._spin_board_width = self._numeric_field()
        self._spin_board_height = self._numeric_field()
        self._spin_work_width = self._numeric_field()
        self._spin_position = self._numeric_field(decimals=0)
        self._spin_thickness = self._numeric_field()
        board_form.addRow(tr("Board Width:"), self._spin_board_width)
        board_form.addRow(tr("Board Height:"), self._spin_board_height)
        board_form.addRow(tr("Working Area Width:"), self._spin_work_width)
        board_form.addRow(tr("Position Working:"), self._spin_position)
        board_form.addRow(tr("Thickness:"), self._spin_thickness)
        layout.addWidget(board_group)

        self._spin_board_width.valueChanged.connect(self._on_board_width_changed)

        boc_group = QGroupBox(tr("Boc Coordinates (auto-filled by hotkey)"))
        boc_form = QFormLayout(boc_group)
        for label in ("X Boc 1", "Y Boc 1", "X Boc 2", "Y Boc 2", "X Boc 3", "Y Boc 3"):
            boc_form.addRow(tr(label), self._boc_row(label))
        layout.addWidget(boc_group)

        self._lbl_status = QLabel("")
        self._lbl_status.setWordWrap(True)
        self._lbl_status.setStyleSheet("color: #334155;")
        layout.addWidget(self._lbl_status)

        btn_layout = QHBoxLayout()
        self._btn_reset = QPushButton(tr("Reset"))
        self._btn_reset.clicked.connect(self._reset)
        self._btn_save = QPushButton(tr("Save"))
        self._btn_save.setObjectName("primary")
        self._btn_save.clicked.connect(self._save)
        self._btn_save.setVisible(False)
        btn_close = QPushButton(tr("Cancel"))
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(self._btn_reset)
        btn_layout.addWidget(self._btn_save)
        btn_layout.addStretch(1)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _register_hotkey(self) -> None:
        try:
            ok = _user32.RegisterHotKey(
                None, HOTKEY_ID, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("Z")
            )
            if not ok:
                raise RuntimeError("RegisterHotKey returned 0")
        except Exception as e:
            self._lbl_status.setText(tr("Cannot register hotkey {hk}: {e}", hk=HOTKEY_COMBO, e=e))
            return
        self._hotkey_filter = _HotkeyFilter(self._trigger_macro)
        app = QApplication.instance()
        if app is not None:
            app.installNativeEventFilter(self._hotkey_filter)

    def _unregister_hotkey(self) -> None:
        app = QApplication.instance()
        if self._hotkey_filter is not None and app is not None:
            app.removeNativeEventFilter(self._hotkey_filter)
            self._hotkey_filter = None
        try:
            _user32.UnregisterHotKey(None, HOTKEY_ID)
        except Exception:
            pass

    def closeEvent(self, event) -> None:
        self._unregister_hotkey()
        super().closeEvent(event)

    def _on_board_width_changed(self, value: float) -> None:
        self._spin_work_width.setValue(value)

    def _next_boc_index(self) -> Optional[int]:
        for index in (1, 2, 3):
            if not self._boc_edits[f"X Boc {index}"].text().strip() or \
               not self._boc_edits[f"Y Boc {index}"].text().strip():
                return index
        return None

    def _all_filled(self) -> bool:
        return self._next_boc_index() is None

    def _trigger_macro(self) -> None:
        index = self._next_boc_index()
        if index is None:
            self._lbl_status.setText(tr("All 3 Boc positions filled. Press Save to save."))
            return
        try:
            x = self._cam350.read_value("x")
            y = self._cam350.read_value("y")
        except RuntimeError as e:
            QMessageBox.warning(self, tr("Macro Failed"), str(e))
            return
        self._boc_edits[f"X Boc {index}"].setText(self._format_float(x))
        self._boc_edits[f"Y Boc {index}"].setText(self._format_float(y))
        self._lbl_status.setText(tr("Filled Boc {index} (X={x}, Y={y}).",
                                    index=index, x=self._format_float(x), y=self._format_float(y)))
        self._update_save_visibility()

    def _update_save_visibility(self) -> None:
        self._btn_save.setVisible(self._all_filled())

    @staticmethod
    def _format_float(value: float) -> str:
        if value == 0.0:
            return ""
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text else "0"

    @staticmethod
    def _parse_float(text: str) -> float:
        text = text.strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            return 0.0

    def _load(self) -> None:
        pcb = self._repo.load()
        self._spin_board_width.setValue(pcb.board_width)
        self._spin_board_height.setValue(pcb.board_height)
        self._spin_work_width.setValue(pcb.working_area_width)
        self._spin_position.setValue(pcb.position_working)
        self._spin_thickness.setValue(pcb.thickness)
        self._boc_edits["X Boc 1"].setText(self._format_float(pcb.x_boc1))
        self._boc_edits["Y Boc 1"].setText(self._format_float(pcb.y_boc1))
        self._boc_edits["X Boc 2"].setText(self._format_float(pcb.x_boc2))
        self._boc_edits["Y Boc 2"].setText(self._format_float(pcb.y_boc2))
        self._boc_edits["X Boc 3"].setText(self._format_float(pcb.x_boc3))
        self._boc_edits["Y Boc 3"].setText(self._format_float(pcb.y_boc3))
        self._update_save_visibility()

    def _reset(self) -> None:
        reply = QMessageBox.question(
            self, tr("Reset PCB Info"),
            tr("Clear all PCB Info data and restore defaults?"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        try:
            self._repo.clear()
        except RuntimeError as e:
            QMessageBox.critical(self, tr("Reset Failed"), str(e))
            return
        self._load()
        self._lbl_status.setText(tr("Reset to default data."))

    def _save(self) -> None:
        pcb = PcbInfo(
            board_width=self._spin_board_width.value(),
            board_height=self._spin_board_height.value(),
            working_area_width=self._spin_work_width.value(),
            position_working=self._spin_position.value(),
            x_boc1=self._parse_float(self._boc_edits["X Boc 1"].text()),
            y_boc1=self._parse_float(self._boc_edits["Y Boc 1"].text()),
            x_boc2=self._parse_float(self._boc_edits["X Boc 2"].text()),
            y_boc2=self._parse_float(self._boc_edits["Y Boc 2"].text()),
            x_boc3=self._parse_float(self._boc_edits["X Boc 3"].text()),
            y_boc3=self._parse_float(self._boc_edits["Y Boc 3"].text()),
            thickness=self._spin_thickness.value(),
        )
        try:
            self._repo.save(pcb)
        except RuntimeError as e:
            QMessageBox.critical(self, tr("Save Failed"), str(e))
            return
        QMessageBox.information(self, tr("Success"), tr("PCB info saved."))
        self.accept()