import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from ui.gerber_file_dialog import GerberFileDialog


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _dialog(paths=None, config_mgr=None):
    return GerberFileDialog(paths or {}, config_mgr)


def test_dialog_initial_labels_with_paths(app, tmp_path):
    gko = tmp_path / "a.GKO"
    gko.write_text("x")
    gtp = tmp_path / "b.GTP"
    gtp.write_text("x")
    dlg = _dialog({"gerberGko": str(gko), "gerberGtp": str(gtp)})
    assert dlg._labels["gerberGko"].text() == "a.GKO"
    assert dlg._labels["gerberGtp"].text() == "b.GTP"


def test_dialog_initial_labels_missing(app, tmp_path):
    missing = tmp_path / "nope.GKO"
    dlg = _dialog({"gerberGko": str(missing)})
    assert dlg._labels["gerberGko"].text() == "(not selected)"


def test_next_requires_gko(app, monkeypatch):
    warned = []
    monkeypatch.setattr(
        "ui.gerber_file_dialog.QMessageBox.warning",
        lambda *a, **k: warned.append(True),
    )
    dlg = _dialog({})
    dlg._on_next()
    assert warned == [True]
    assert dlg.result() == 0


def test_next_accepts_with_gko(app, monkeypatch, tmp_path):
    gko = tmp_path / "a.GKO"
    gko.write_text("x")
    monkeypatch.setattr(
        "ui.gerber_file_dialog.QMessageBox.warning",
        lambda *a, **k: pytest.fail("should not warn"),
    )
    dlg = _dialog({"gerberGko": str(gko)})
    dlg._on_next()
    assert dlg.result() == 1  # QDialog.Accepted


def test_selected_paths_filters_missing(app, tmp_path):
    existing = tmp_path / "a.GKO"
    existing.write_text("x")
    dlg = _dialog({"gerberGko": str(existing), "gerberGbo": str(tmp_path / "no.GBO")})
    out = dlg.selected_paths()
    assert out == {"gerberGko": str(existing)}


def test_browse_updates_label_and_config(app, monkeypatch, tmp_path):
    class FakeMgr:
        def __init__(self):
            self.updates = {}

        def update(self, **kwargs):
            self.updates.update(kwargs)

    gko = tmp_path / "new.GKO"
    gko.write_text("x")
    mgr = FakeMgr()
    monkeypatch.setattr(
        "ui.gerber_file_dialog.QFileDialog.getOpenFileName",
        lambda *a, **k: (str(gko), ""),
    )
    dlg = _dialog({}, mgr)
    dlg._browse("gerberGko")
    assert dlg._labels["gerberGko"].text() == "new.GKO"
    assert mgr.updates == {"gerberGko": str(gko)}
    assert dlg._paths["gerberGko"] == str(gko)