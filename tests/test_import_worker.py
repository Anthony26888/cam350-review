import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication

from ui.main_window import ImportWorker


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _run(worker, app, timeout=3000):
    worker.start()
    assert worker.wait(timeout)
    app.processEvents()


def test_import_worker_emits_progress_and_result(app):
    seen = []
    results = []

    def _work(report):
        report(1, 2)
        report(2, 2)
        return "ok"

    worker = ImportWorker(_work, "Reading rows...")
    worker.progress.connect(
        lambda label, done, total: seen.append((label, done, total)))
    worker.finished_ok.connect(results.append)
    _run(worker, app)

    assert seen == [("Reading rows...", 1, 2), ("Reading rows...", 2, 2)]
    assert results == ["ok"]


def test_import_worker_emits_error(app):
    errors = []

    def _work(_report):
        raise ValueError("bad file")

    worker = ImportWorker(_work, "Reading...")
    worker.finished_err.connect(errors.append)
    _run(worker, app)

    assert errors == ["bad file"]


def test_import_worker_can_be_cancelled_before_run(app):
    cancelled = []

    worker = ImportWorker(lambda report: report(1, 1), "Reading...")
    worker.cancelled.connect(lambda: cancelled.append(True))
    worker.cancel()
    _run(worker, app)

    assert cancelled == [True]
