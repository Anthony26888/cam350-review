import os

from PySide6.QtWidgets import QDialog

from license.activation_dialog import ActivationDialog
from license.fingerprint import get_hwid
from license.state import (
    get_max_seen_date,
    is_clock_rollback,
    load_license_key,
    save_hwid,
    today_iso,
    update_max_seen,
)
from license.verify import verify_license_key

_SKIP_ENV = "CAM350_REVIEW_SKIP_LICENSE"


def license_gate() -> bool:
    if os.environ.get(_SKIP_ENV):
        return True

    hwid = get_hwid()
    save_hwid(hwid)

    key = load_license_key()
    ok, reason, _ = verify_license_key(key, hwid)

    if ok:
        today = today_iso()
        if is_clock_rollback(today, get_max_seen_date()):
            ok = False
            reason = "clock_rollback"
        else:
            update_max_seen(today)

    if ok:
        return True

    dialog = ActivationDialog(hwid=hwid, reason=reason)
    return dialog.exec() == QDialog.Accepted
