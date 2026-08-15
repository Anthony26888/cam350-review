import json

from license.registry import LicenseRegistry, days_left_of, status_of


def test_status_of():
    assert status_of("2026-09-15", today="2026-09-15", warning_days=30) == "expiring"
    assert status_of("2026-10-20", today="2026-09-15", warning_days=30) == "valid"
    assert status_of("2026-09-01", today="2026-09-15", warning_days=30) == "expired"
    assert status_of("2026-10-15", today="2026-09-15", warning_days=14) == "valid"
    assert status_of("", today="2026-09-15") == "invalid"


def test_days_left_of():
    assert days_left_of("2026-09-20", today="2026-09-15") == 5
    assert days_left_of("2026-09-01", today="2026-09-15") == -14
    assert days_left_of("bad-date") == 0


def test_registry_round_trip(tmp_path):
    path = tmp_path / "licenses.json"
    reg = LicenseRegistry(path)
    reg.warning_days = 45
    reg.add("HWID1", "Cty A", "2027-01-01", device="Máy 1", notes="ok")
    reg.add("HWID2", "Cty B", "2027-06-01")
    assert len(reg.all()) == 2

    reloaded = LicenseRegistry(path)
    assert reloaded.warning_days == 45
    assert len(reloaded.all()) == 2
    assert reloaded.find_by_hwid("HWID1")["customer"] == "Cty A"
    assert reloaded.find_by_hwid("HWID1")["device"] == "Máy 1"


def test_registry_update_delete(tmp_path):
    path = tmp_path / "licenses.json"
    reg = LicenseRegistry(path)
    rec = reg.add("HWID1", "Cty A", "2027-01-01")
    reg.update(rec["id"], customer="Cty A2", notes="edited")
    assert reg.find_by_hwid("HWID1")["customer"] == "Cty A2"
    assert reg.find_by_hwid("HWID1")["notes"] == "edited"
    assert reg.delete(rec["id"]) is True
    assert len(reg.all()) == 0
    assert reg.delete(rec["id"]) is False


def test_registry_renew_updates_and_appends_history(tmp_path):
    path = tmp_path / "licenses.json"
    reg = LicenseRegistry(path)
    rec = reg.add("HWID1", "Cty A", "2026-09-01", key="OLDKEY")
    updated = reg.renew(rec["id"], 30, "NEWKEY", when="2026-08-15T10:00:00")
    assert updated["expiry"] == "2026-10-01"
    assert updated["key"] == "NEWKEY"
    renewals = updated["renewals"]
    assert len(renewals) == 1
    assert renewals[0]["old_expiry"] == "2026-09-01"
    assert renewals[0]["new_expiry"] == "2026-10-01"
    assert renewals[0]["days"] == 30
    assert renewals[0]["old_key"] == "OLDKEY"
    assert renewals[0]["new_key"] == "NEWKEY"


def test_registry_renew_from_past_expiry_uses_today(tmp_path, monkeypatch):
    import license.registry as reg_mod

    class FakeDate:
        @staticmethod
        def today():
            from datetime import date
            return date(2026, 9, 15)

        @staticmethod
        def fromisoformat(value):
            from datetime import date
            return date.fromisoformat(value)

    monkeypatch.setattr(reg_mod, "date", FakeDate)
    path = tmp_path / "licenses.json"
    reg = LicenseRegistry(path)
    rec = reg.add("HWID1", "Cty A", "2026-01-01")
    updated = reg.renew(rec["id"], 30, "NEWKEY")
    assert updated["expiry"] == "2026-10-15"


def test_registry_missing_file_empty(tmp_path):
    reg = LicenseRegistry(tmp_path / "nope.json")
    assert reg.all() == []
    assert reg.warning_days == 30


def test_registry_corrupt_file_falls_back_empty(tmp_path):
    path = tmp_path / "licenses.json"
    path.write_text("{not valid json")
    reg = LicenseRegistry(path)
    assert reg.all() == []


def test_registry_json_structure(tmp_path):
    path = tmp_path / "licenses.json"
    reg = LicenseRegistry(path)
    reg.add("HWID1", "Cty A", "2027-01-01")
    reg.renew(reg.all()[0]["id"], 90, "NEWKEY")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["warning_days"] == 30
    assert len(data["licenses"]) == 1
    assert len(data["licenses"][0]["renewals"]) == 1
    assert data["licenses"][0]["hwid"] == "HWID1"
