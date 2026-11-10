import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

from PySide6.QtWidgets import QApplication

from database.database import Database
import ui.pcb_info_dialog as pcb_info_dialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _dialog(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "pcb_info.db"))
    monkeypatch.setattr(Database, "_instance", db)
    monkeypatch.setattr(pcb_info_dialog, "_user32", None)
    _app()
    return pcb_info_dialog.PcbInfoDialog(), db


def test_save_button_visible_without_boc(tmp_path, monkeypatch):
    dialog, db = _dialog(tmp_path, monkeypatch)
    try:
        assert dialog._btn_save.isVisibleTo(dialog)
        dialog._spin_board_width.setValue(100.0)
        assert dialog._btn_save.isVisibleTo(dialog)
    finally:
        dialog.close()
        db.close()


def test_pcb_info_is_not_hidden_on_non_windows():
    src = (Path(__file__).resolve().parents[1] / "ui" / "main_window.py").read_text(
        encoding="utf-8"
    )
    assert "pcb_info_action.setVisible" not in src
    assert "self._btn_pcb_info.setVisible" not in src


def test_pick_enabled_is_non_modal_and_fills_fields(tmp_path, monkeypatch):
    db = Database(str(tmp_path / "pcb_info.db"))
    monkeypatch.setattr(Database, "_instance", db)
    monkeypatch.setattr(pcb_info_dialog, "_user32", None)
    _app()
    dialog = pcb_info_dialog.PcbInfoDialog(pick_enabled=True)
    try:
        assert dialog.isModal() is False
        dialog.apply_pick("boc1", [(12.5, 34.25)])
        assert dialog._boc_edits["X Boc 1"].text() == "12.5"
        assert dialog._boc_edits["Y Boc 1"].text() == "34.25"
        dialog.apply_pick("boc2", [(-3.0, 4.0)])
        assert dialog._boc_edits["X Boc 2"].text() == "-3"
        assert dialog._boc_edits["Y Boc 2"].text() == "4"
        dialog.apply_pick("board", [(10.0, 5.0), (110.0, 55.0)])
        assert dialog._spin_board_width.value() == 100.0
        assert dialog._spin_board_height.value() == 50.0
        assert dialog._spin_work_width.value() == 100.0
    finally:
        dialog.close()
        db.close()


def test_default_dialog_stays_modal(tmp_path, monkeypatch):
    dialog, db = _dialog(tmp_path, monkeypatch)
    try:
        assert dialog.isModal() is True
    finally:
        dialog.close()
        db.close()
