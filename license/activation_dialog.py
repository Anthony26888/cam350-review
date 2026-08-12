from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from license.fingerprint import get_hwid
from license.state import save_license_key
from license.verify import (
    BAD_SIGNATURE,
    EXPIRED,
    MALFORMED,
    WRONG_MACHINE,
    verify_license_key,
)
from ui.i18n import tr

_REASON_TEXT = {
    "": tr("No active license found on this computer."),
    EXPIRED: tr("The license key has expired. Please contact your provider for a renewal."),
    WRONG_MACHINE: tr("The license key does not match this computer."),
    BAD_SIGNATURE: tr("The license key is not valid."),
    MALFORMED: tr("The license key is not valid."),
    "clock_rollback": tr("System clock issue detected. Set the correct date and time, then restart the app."),
}


class ActivationDialog(QDialog):
    def __init__(
        self,
        hwid: Optional[str] = None,
        reason: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._hwid = hwid or get_hwid()
        self._reason = reason
        self.setWindowTitle(tr("License Activation"))
        self.setModal(True)
        self.setMinimumWidth(480)
        self._build_ui()
        self._apply_reason(reason)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        title = QLabel(tr("License Activation"))
        title.setObjectName("title")
        layout.addWidget(title)

        hwid_row = QHBoxLayout()
        hwid_label = QLabel(tr("Machine ID:"))
        self._lbl_hwid = QLabel(self._hwid)
        self._lbl_hwid.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self._lbl_hwid.setObjectName("hwid_value")
        self._btn_copy = QPushButton(tr("Copy"))
        self._btn_copy.clicked.connect(self._copy_hwid)
        hwid_row.addWidget(hwid_label)
        hwid_row.addWidget(self._lbl_hwid, 1)
        hwid_row.addWidget(self._btn_copy)
        layout.addLayout(hwid_row)

        hint = QLabel(tr("Send this Machine ID to your provider to receive a License Key."))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self._lbl_reason = QLabel("")
        self._lbl_reason.setObjectName("reason")
        self._lbl_reason.setWordWrap(True)
        layout.addWidget(self._lbl_reason)

        key_label = QLabel(tr("License Key:"))
        layout.addWidget(key_label)
        self._edit_key = QLineEdit()
        self._edit_key.setPlaceholderText(tr("Paste your license key here"))
        layout.addWidget(self._edit_key)

        buttons = QHBoxLayout()
        self._btn_activate = QPushButton(tr("Activate"))
        self._btn_activate.setObjectName("success")
        self._btn_activate.clicked.connect(self._activate)
        self._btn_exit = QPushButton(tr("Exit"))
        self._btn_exit.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(self._btn_activate)
        buttons.addWidget(self._btn_exit)
        layout.addLayout(buttons)

    def _apply_reason(self, reason: str) -> None:
        text = _REASON_TEXT.get(reason, _REASON_TEXT[""])
        self._lbl_reason.setText(text)

    def _copy_hwid(self) -> None:
        QApplication.clipboard().setText(self._hwid)
        self._btn_copy.setText(tr("Copied!"))
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, lambda: self._btn_copy.setText(tr("Copy")))

    def _activate(self) -> None:
        key = self._edit_key.text().strip()
        if not key:
            QMessageBox.warning(self, tr("License"), tr("Please enter a license key."))
            return
        ok, reason, _ = verify_license_key(key, self._hwid)
        if not ok:
            self._lbl_reason.setText(_REASON_TEXT.get(reason, tr("The license key is not valid.")))
            return
        save_license_key(key)
        self.accept()
