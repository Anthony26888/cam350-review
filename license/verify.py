import base64
import json
from datetime import date
from typing import Any, Dict, Optional, Tuple

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA+6PG7stsk5A7zhT5D7d7z91iCbPajn7XUdche2O+9m4=
-----END PUBLIC KEY-----"""

VALID, MALFORMED, BAD_SIGNATURE, WRONG_MACHINE, EXPIRED = (
    "valid",
    "malformed",
    "bad_signature",
    "wrong_machine",
    "expired",
)


def _b64e(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64d(text: str) -> bytes:
    padded = text + "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def build_license_key(
    private_key_pem: str,
    hwid: str,
    customer: str,
    expiry: str,
    issued_at: str,
) -> str:
    payload: Dict[str, str] = {
        "hwid": hwid,
        "customer": customer,
        "expiry": expiry,
        "issued_at": issued_at,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode(
        "utf-8"
    )
    private_key = serialization.load_pem_private_key(
        private_key_pem.encode("utf-8"), password=None
    )
    signature = private_key.sign(payload_bytes)  # type: ignore[attr-defined]
    return _b64e(payload_bytes) + "." + _b64e(signature)


def _parse_key(key: str) -> Optional[Tuple[Dict[str, str], bytes, bytes]]:
    parts = key.split(".")
    if len(parts) != 2:
        return None
    try:
        payload_bytes = _b64d(parts[0])
        signature = _b64d(parts[1])
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return payload, payload_bytes, signature


def _verify_signature(payload_bytes: bytes, signature: bytes) -> bool:
    try:
        public_key = serialization.load_pem_public_key(
            PUBLIC_KEY_PEM.encode("utf-8")
        )
        public_key.verify(signature, payload_bytes)  # type: ignore[attr-defined]
        return True
    except Exception:
        return False


def verify_license_key(key: str, hwid: str) -> Tuple[bool, str, Optional[Dict[str, str]]]:
    parsed = _parse_key(key)
    if parsed is None:
        return False, MALFORMED, None
    payload, payload_bytes, signature = parsed

    if not _verify_signature(payload_bytes, signature):
        return False, BAD_SIGNATURE, payload

    if payload.get("hwid") != hwid:
        return False, WRONG_MACHINE, payload

    expiry = payload.get("expiry", "")
    if expiry and expiry < date.today().isoformat():
        return False, EXPIRED, payload

    return True, VALID, payload
