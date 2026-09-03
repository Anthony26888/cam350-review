import ui.style as style


def test_dark_menu_disabled_rule():
    assert "QMenu::item:disabled" in style.QSS_DARK
    assert "color: #64748B;" in style.QSS_DARK


def test_light_menu_disabled_rule():
    assert "QMenu::item:disabled" in style.QSS_LIGHT
    assert "color: #94A3B8;" in style.QSS_LIGHT