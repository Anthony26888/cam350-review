import pytest

from services.datasheet_service import DatasheetService


def test_search_empty():
    assert DatasheetService.search("") == ""
    assert DatasheetService.search("   ") == ""


def test_google_url_builder():
    url = DatasheetService._search_google("LM358")
    assert "LM358" in url
    assert "datasheet" in url


def test_digikey_fallback_url():
    url = DatasheetService._search_digikey("LM358")
    assert "digikey.com" in url
    assert "LM358" in url
