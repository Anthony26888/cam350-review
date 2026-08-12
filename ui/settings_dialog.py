from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QPushButton, QHBoxLayout,
    QGroupBox, QFormLayout, QSpinBox, QMessageBox, QLineEdit,
    QLabel, QComboBox, QApplication,
)

from config.config_manager import ConfigManager
from services.cam350_controller import Cam350Controller
from ui.i18n import tr, set_language
from ui.style import apply_theme


class SettingsDialog(QDialog):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config_mgr = ConfigManager.instance()
        self._cam350 = Cam350Controller()
        self.setWindowTitle(tr("Settings"))
        self.setModal(True)
        self.setMinimumWidth(450)
        self._build_ui()
        self._load_config()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        config_group = QGroupBox(tr("Configuration"))
        config_layout = QFormLayout(config_group)

        self._txt_window_title = QLineEdit()
        config_layout.addRow(tr("Window Title:"), self._txt_window_title)

        self._spin_delay = QSpinBox()
        self._spin_delay.setRange(50, 2000)
        self._spin_delay.setSuffix(" ms")
        config_layout.addRow(tr("Jump Delay:"), self._spin_delay)

        self._combo_theme = QComboBox()
        self._combo_theme.addItem(tr("Light"), userData="light")
        self._combo_theme.addItem(tr("Dark"), userData="dark")
        config_layout.addRow(tr("Theme:"), self._combo_theme)

        self._combo_language = QComboBox()
        self._combo_language.addItem(tr("English"), userData="en")
        self._combo_language.addItem(tr("Vietnamese"), userData="vi")
        config_layout.addRow(tr("Language:"), self._combo_language)

        self._lbl_x = QLabel("(0, 0)")
        config_layout.addRow(tr("X Textbox:"), self._lbl_x)

        self._lbl_y = QLabel("(0, 0)")
        config_layout.addRow(tr("Y Textbox:"), self._lbl_y)

        self._lbl_goto = QLabel("(0, 0)")
        config_layout.addRow(tr("Go Button:"), self._lbl_goto)

        layout.addWidget(config_group)

        actions_group = QGroupBox(tr("Actions"))
        actions_layout = QVBoxLayout(actions_group)

        btn_calibrate = QPushButton(tr("Run Calibration Wizard"))
        btn_calibrate.clicked.connect(self._run_calibration)

        btn_test = QPushButton(tr("Test CAM350 Connection"))
        btn_test.clicked.connect(self._test_connection)

        btn_jump = QPushButton(tr("Test Jump (X=0, Y=0)"))
        btn_jump.clicked.connect(self._test_jump)

        btn_reset = QPushButton(tr("Reset Configuration"))
        btn_reset.clicked.connect(self._reset_config)

        actions_layout.addWidget(btn_calibrate)
        actions_layout.addWidget(btn_test)
        actions_layout.addWidget(btn_jump)
        actions_layout.addWidget(btn_reset)

        layout.addWidget(actions_group)

        btn_layout = QHBoxLayout()
        btn_save = QPushButton(tr("Save"))
        btn_save.clicked.connect(self._save_config)
        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(self.close)
        btn_layout.addWidget(btn_save)
        btn_layout.addWidget(btn_close)
        layout.addLayout(btn_layout)

    def _load_config(self) -> None:
        cfg = self._config_mgr.config
        self._txt_window_title.setText(cfg.windowTitle)
        self._spin_delay.setValue(cfg.delay)
        self._set_combo_data(self._combo_theme, cfg.theme)
        self._set_combo_data(self._combo_language, cfg.language)
        self._lbl_x.setText(f"({cfg.xTextbox.x}, {cfg.xTextbox.y})")
        self._lbl_y.setText(f"({cfg.yTextbox.x}, {cfg.yTextbox.y})")
        self._lbl_goto.setText(f"({cfg.gotoButton.x}, {cfg.gotoButton.y})")

    @staticmethod
    def _set_combo_data(combo: QComboBox, value: str) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                break

    def _run_calibration(self) -> None:
        from ui.calibration_wizard import CalibrationWizard
        wizard = CalibrationWizard(self)
        wizard.show()

    def _test_connection(self) -> None:
        if self._cam350.is_running():
            QMessageBox.information(self, tr("Success"), tr("CAM350 is running and connected."))
        else:
            QMessageBox.warning(self, tr("Error"), tr("CAM350 not found. Ensure it is running."))

    def _test_jump(self) -> None:
        if self._cam350.test_jump():
            QMessageBox.information(self, tr("Success"), tr("Jump test successful."))
        else:
            QMessageBox.warning(self, tr("Error"), tr("Jump test failed. Check calibration."))

    def _reset_config(self) -> None:
        reply = QMessageBox.question(
            self, tr("Confirm Reset"),
            tr("Reset all configuration to defaults?"),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            from models.config import AppConfig
            self._config_mgr.config = AppConfig()
            self._load_config()
            QMessageBox.information(self, tr("Success"), tr("Configuration reset."))

    def _save_config(self) -> None:
        old_theme = self._config_mgr.config.theme
        self._config_mgr.update(
            windowTitle=self._txt_window_title.text().strip(),
            delay=self._spin_delay.value(),
            theme=self._combo_theme.currentData() or "light",
            language=self._combo_language.currentData() or "en",
        )
        set_language(self._config_mgr.config.language)
        if self._config_mgr.config.theme != old_theme:
            app = QApplication.instance()
            if app is not None:
                apply_theme(app, self._config_mgr.config.theme)
        QMessageBox.information(self, tr("Success"), tr("Settings saved."))
