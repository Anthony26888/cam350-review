import os
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QMessageBox

from models.review import ReviewRecord
from services.gerber.origin_aligner import AlignResult
from services.gerber.panel_detector import BoardInstance, PanelInfo
from services.prescreen import (
    KIND_ROT,
    PrescreenIssue,
    pack_prescreen_ctx,
)
import ui.main_window as mw
import ui.origin_align_wizard as wiz


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# Dialog-level tests (fake worker injected at ui.origin_align_wizard)
# ---------------------------------------------------------------------------

class _FakeWorker:
    instances = []

    def __init__(self, gko, gtp, gbp, records, cfg, dismissed=None, ctx=None,
                 parent=None):
        self.args = (gko, gtp, gbp, records, cfg, set(dismissed or ()), ctx)
        self.signals = {}
        type(self).instances.append(self)

    def isRunning(self):
        return False

    def start(self):
        self.started = True

    def emit_finished(self, issues):
        self.signals["finished"](list(issues))

    def emit_failed(self, msg):
        self.signals["failed"](msg)


class _Sig:
    def __init__(self, owner, name):
        self._owner = owner
        self._name = name

    def connect(self, fn):
        self._owner.signals[self._name] = fn


for _n in ("progress", "stats_ready", "finished", "failed"):
    setattr(_FakeWorker, _n, property(
        lambda self, _n=_n: _Sig(self, _n),
        lambda self, v, _n=_n: self.signals.__setitem__(_n, v),
    ))


def _rec(des, rot=0.0):
    return ReviewRecord(designator=des, old_x=1.0, old_y=2.0, old_rotation=rot)


def _live_ctx():
    panel = PanelInfo(
        kind="S",
        instances=[BoardInstance(origin=(0.0, 0.0), w=50.0, h=40.0, k=0)],
        panel_origin=(0.0, 0.0), panel_w=50.0, panel_h=40.0,
    )
    return {
        "align_results": {0: {"top": AlignResult(offset_x=1.0, offset_y=2.0)}},
        "panel_info": panel,
        "origin_mode": "panel",
        "rotation_angle": 0,
        "rot_layers": {"top": True, "bottom": False},
    }


def _live_bundle(gko="g.gko"):
    return (gko, "p.gtp", "b.gbp", _live_ctx())


@pytest.fixture()
def gko_file(tmp_path):
    p = tmp_path / "board.gko"
    p.write_text("%MOMM*%\n", encoding="ascii")
    return str(p)


class _CfgMgr:
    class config:
        pass


def _dialog(records, bundle="LIVE", dismissed=None):
    if bundle == "LIVE":
        bundle = _live_bundle()
    d = wiz.PrescreenCheckDialog(
        records, lambda: bundle, dismissed or set(), parent=None,
    )
    return d


@pytest.fixture()
def fake_worker(monkeypatch):
    _FakeWorker.instances = []
    monkeypatch.setattr(wiz, "PrescreenWorker", _FakeWorker)
    return _FakeWorker


@pytest.fixture()
def cfg_holder(monkeypatch):
    from services.prescreen import PrescreenConfig as PC
    holder = types.SimpleNamespace(config=types.SimpleNamespace(prescreen=PC()))
    monkeypatch.setattr(wiz, "ConfigManager", types.SimpleNamespace(instance=lambda: holder))
    return holder


def test_dialog_initial_placeholder(app):
    d = _dialog([_rec("C1")])
    assert "Not run yet" in d._summary.text()
    assert d._btn_run.isEnabled()


def test_dialog_without_bundle_shows_note_no_worker(app, fake_worker):
    d = _dialog([_rec("C1")], bundle=None)
    d._run_check()
    assert fake_worker.instances == []
    assert "Align" in d._summary.text()
    assert "#DC2626" in d._summary.styleSheet()


def test_dialog_run_passes_live_records_and_dismissed(app, fake_worker, cfg_holder, gko_file):
    recs = [_rec("C1"), _rec("C2")]
    dismissed = {"ROT:C9:1.000:2.000"}
    d = _dialog(recs, bundle=_live_bundle(gko_file), dismissed=dismissed)
    d._run_check()
    assert len(fake_worker.instances) == 1
    gko, gtp, gbp, got_recs, cfg, got_dismissed, ctx = fake_worker.instances[0].args
    assert gko == gko_file and (gtp, gbp) == ("p.gtp", "b.gbp")
    assert got_recs is recs                       # live reference
    assert isinstance(ctx, dict) and ctx["origin_mode"] == "panel"
    assert got_dismissed == dismissed
    assert not d._btn_run.isEnabled()             # locked while running


def test_dialog_double_click_while_running_ignored(app, fake_worker, cfg_holder):
    d = _dialog([_rec("C1")])
    d._run_check()

    class _Busy:
        def __init__(self):
            self.signals = {}

        def isRunning(self):
            return True

    d._worker = _Busy()
    before = len(fake_worker.instances)
    d._run_check()
    assert len(fake_worker.instances) == before


def test_dialog_finished_shows_totals_and_emits(app, fake_worker, cfg_holder, gko_file):
    recs = [_rec("C1"), _rec("C2")]
    d = _dialog(recs, bundle=_live_bundle(gko_file))
    got = []
    d.checks_finished.connect(got.append)
    d._run_check()
    issues = [
        PrescreenIssue(kind=KIND_ROT, index=1, designator="C2", x=1.0, y=2.0),
    ]
    fake_worker.instances[0].emit_finished(issues)
    text = d._summary.text()
    assert "ROT : 1" in text and "PAD : 0" in text
    assert "Total: 1 / 2" in text
    assert d._btn_run.isEnabled()
    assert got and got[0][0].designator == "C2"


def test_dialog_failed_shows_error_and_reenables(app, fake_worker, cfg_holder, gko_file):
    d = _dialog([_rec("C1")], bundle=_live_bundle(gko_file))
    d._run_check()
    fake_worker.instances[0].emit_failed("boom")
    assert "boom" in d._summary.text()
    assert d._btn_run.isEnabled()
    assert d._worker is None


def test_dialog_stale_generation_ignored(app, fake_worker, cfg_holder, gko_file):
    d = _dialog([_rec("C1")], bundle=_live_bundle(gko_file))
    got = []
    d.checks_finished.connect(got.append)
    d._run_check()
    w1 = fake_worker.instances[0]
    d._generation += 1                # simulate a newer run superseding it
    w1.emit_finished([PrescreenIssue(kind=KIND_ROT, index=0, designator="C1",
                                     x=1.0, y=2.0)])
    assert got == []


# ---------------------------------------------------------------------------
# MainWindow wiring tests (holder pattern)
# ---------------------------------------------------------------------------

class _MB:
    instances = []

    @staticmethod
    def warning(*args, **kwargs):
        _MB.instances.append(("warning", args))


class _Label:
    def __init__(self):
        self.text = ""

    def setText(self, t):
        self.text = t


class _Btn:
    def __init__(self, enabled=False):
        self.enabled = enabled

    def setEnabled(self, e):
        self.enabled = e

    def isEnabled(self):
        return self.enabled


class _Table:
    def update_all_rows(self):
        pass

    def update_record_row(self, idx):
        pass


def _mw_holder(records, bundle=None):
    h = types.SimpleNamespace()
    h._records = records
    h._prescreen_dismissed = set()
    h._prescreen_bundle = bundle
    h._prescreen_ctx_packed = None
    h._prescreen_dialog = None
    h._status_label = _Label()
    h._btn_run_check = _Btn(enabled=True)
    h._table_widget = _Table()
    h._gerber_viewer = None
    for name in ["_open_prescreen_dialog", "_apply_prescreen_issues",
                 "_on_prescreen_dialog_closed", "_close_prescreen_dialog",
                 "_apply_prescreen_result", "_sync_viewer_flags",
                 "_current_flagged_indices", "_restore_prescreen_bundle"]:
        setattr(h, name, getattr(mw.MainWindow, name).__get__(h))
    return h


@pytest.fixture()
def mb(monkeypatch):
    _MB.instances = []
    monkeypatch.setattr(mw, "QMessageBox", _MB)
    return _MB


def test_open_dialog_requires_records(app, mb):
    h = _mw_holder([])
    h._open_prescreen_dialog()
    assert mb.instances and mb.instances[0][0] == "warning"
    assert h._prescreen_dialog is None


def test_apply_prescreen_issues_updates_flags_and_status(app):
    recs = [_rec("C1"), _rec("C2")]
    h = _mw_holder(recs)
    issues = [PrescreenIssue(kind=KIND_ROT, index=1, designator="C2",
                             x=1.0, y=2.0)]
    h._apply_prescreen_issues(issues)
    assert recs[1].prescreen_flags == [KIND_ROT]
    assert "Pre-screen" in h._status_label.text


def test_close_prescreen_dialog_tolerates_missing_attr(app):
    h = types.SimpleNamespace()   # no attribute at all
    mw.MainWindow._close_prescreen_dialog.__get__(h)()
    assert getattr(h, "_prescreen_dialog", None) is None


def test_restore_bundle_enables_session_rerun(app, tmp_path):
    gko = tmp_path / "board.gko"
    gko.write_text("%MOMM*%\n", encoding="ascii")

    class _Cfg:
        gerberGko = str(gko)
        gerberGtp = ""
        gerberGbp = ""

    session = types.SimpleNamespace(prescreen_ctx=pack_prescreen_ctx(_live_ctx()))
    h = _mw_holder([_rec("C1")])
    h._config_mgr = types.SimpleNamespace(config=_Cfg())
    h._restore_prescreen_bundle(session)
    assert h._prescreen_bundle is not None
    assert h._btn_run_check.isEnabled() is True
