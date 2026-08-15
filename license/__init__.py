try:
    from license.fingerprint import get_hwid
except ImportError:
    get_hwid = None
from license.verify import verify_license_key

__all__ = ["get_hwid", "verify_license_key"]
