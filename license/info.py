import os
from datetime import date

from license.fingerprint import get_hwid
from license.state import load_license_key
from license.verify import verify_license_key

_SKIP_ENV = "CAM350_REVIEW_SKIP_LICENSE"


def license_summary() -> str:
    if os.environ.get(_SKIP_ENV):
        return "Evaluation mode (license check disabled)"
    hwid = get_hwid()
    key = load_license_key()
    ok, reason, payload = verify_license_key(key, hwid)
    if not ok or not payload:
        return "No active license"
    customer = payload.get("customer", "")
    expiry = payload.get("expiry", "")
    try:
        days_left = (date.fromisoformat(expiry) - date.today()).days
    except (ValueError, TypeError):
        days_left = 0
    return f"Licensed to {customer} | Expires {expiry} | {days_left} days remaining"
