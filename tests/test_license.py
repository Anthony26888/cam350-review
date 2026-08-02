from datetime import date, timedelta

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

import license.verify as verify_mod
from license.state import is_clock_rollback
from license.verify import verify_license_key


@pytest.fixture()
def private_pem():
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    verify_mod.PUBLIC_KEY_PEM = public_pem
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")


def _make_key(private_pem, hwid="HWID123", expiry=None):
    expiry = expiry or (date.today() + timedelta(days=365)).isoformat()
    return verify_mod.build_license_key(private_pem, hwid, "Test Customer", expiry, "2026-01-01T00:00:00")


def test_valid_key(private_pem):
    key = _make_key(private_pem, hwid="HWID123")
    ok, reason, payload = verify_license_key(key, "HWID123")
    assert ok is True
    assert reason == "valid"
    assert payload["customer"] == "Test Customer"


def test_wrong_machine(private_pem):
    key = _make_key(private_pem, hwid="HWID123")
    ok, reason, _ = verify_license_key(key, "OTHER_MACHINE")
    assert ok is False
    assert reason == "wrong_machine"


def test_expired_key(private_pem):
    expired = (date.today() - timedelta(days=1)).isoformat()
    key = _make_key(private_pem, hwid="HWID123", expiry=expired)
    ok, reason, _ = verify_license_key(key, "HWID123")
    assert ok is False
    assert reason == "expired"


def test_tampered_signature(private_pem):
    key = _make_key(private_pem, hwid="HWID123")
    payload, signature = key.split(".")
    mutated_sig = signature[:20] + ("A" if signature[20] != "A" else "B") + signature[21:]
    ok, reason, _ = verify_license_key(f"{payload}.{mutated_sig}", "HWID123")
    assert ok is False
    assert reason == "bad_signature"


def test_malformed_key(private_pem):
    ok, reason, _ = verify_license_key("not-a-valid-key", "HWID123")
    assert ok is False
    assert reason == "malformed"


def test_clock_rollback():
    assert is_clock_rollback("2026-01-01", None) is False
    assert is_clock_rollback("2026-01-01", "2026-06-01") is True
    assert is_clock_rollback("2026-06-01", "2026-06-01") is False
    assert is_clock_rollback("2026-07-01", "2026-06-01") is False
