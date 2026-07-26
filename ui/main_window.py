import os
import json
from datetime import datetime
from typing import Optional, List

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QMessageBox, QFileDialog, QStatusBar,
    QProgressBar, QLabel, QSplitter, QMenuBar, QMenu,
    QApplication,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QKeySequence

from config.config_manager import ConfigManager
from database.review_repo import ReviewRepo
from models.review import ReviewRecord
from models.pickplace import PickPlaceData
from services.pickplace_reader import PickPlaceReader
from services.cam350_controller import Cam350Controller
from services.export_service import ExportService
from services.session_service import SessionService
from ui.table_widget import TableWidget
from ui.review_panel import ReviewPanel
from ui.edit_dialog import EditDialog
from ui.batch_edit_dialog import BatchEditDialog
from ui.settings_dialog import SettingsDialog
from ui.calibration_wizard import CalibrationWizard


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._config_mgr = ConfigManager.instance()
        self._repo = ReviewRepo()
        self._cam350 = Cam350Controller()
        self._reader = PickPlaceReader()
        self._exporter = ExportService()

        self._records: List[ReviewRecord] = []
        self._pickplace_data: Optional[PickPlaceData] = None
        self._current_index: int = -1
        self._session_service = SessionService()
        self._session_file: Optional[str] = None

        self.setWindowTitle("CAM350 Review Assistant")
        self.setMinimumSize(1200, 700)

        self._build_menus()
        self._build_ui()
        self._build_statusbar()
        self._setup_shortcuts()
        self._restore_state()

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu("&File")

        new_action = QAction("New Session", self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_session)
        file_menu.addAction(new_action)

        open_session_action = QAction("Open Session...", self)
        open_session_action.setShortcut(QKeySequence("Ctrl+O"))
        open_session_action.triggered.connect(self._open_session)
        file_menu.addAction(open_session_action)

        save_action = QAction("Save Session", self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_session)
        file_menu.addAction(save_action)

        save_as_action = QAction("Save Session As...", self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_session_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        open_pickplace_action = QAction("Open PickPlace Excel...", self)
        open_pickplace_action.setShortcut(QKeySequence("Ctrl+W"))
        open_pickplace_action.triggered.connect(self._open_file)
        file_menu.addAction(open_pickplace_action)

        export_menu = file_menu.addMenu("&Export")
        export_report_action = QAction("Export Review Report", self)
        export_report_action.triggered.connect(self._export_report)
        export_menu.addAction(export_report_action)

        export_fixed_action = QAction("Export PickPlace Fixed", self)
        export_fixed_action.triggered.connect(self._export_fixed)
        export_menu.addAction(export_fixed_action)

        file_menu.addSeparator()
        exit_action = QAction("Exit", self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        tools_menu = menubar.addMenu("&Tools")
        calibrate_action = QAction("Calibration Wizard", self)
        calibrate_action.triggered.connect(self._open_calibration)
        tools_menu.addAction(calibrate_action)

        settings_action = QAction("Settings", self)
        settings_action.triggered.connect(self._open_settings)
        tools_menu.addAction(settings_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        toolbar_layout = QHBoxLayout()

        btn_new = QPushButton("📄 New")
        btn_new.clicked.connect(self._new_session)
        btn_new.setMinimumHeight(36)

        btn_open_session = QPushButton("📂 Open Session")
        btn_open_session.clicked.connect(self._open_session)
        btn_open_session.setMinimumHeight(36)

        btn_save = QPushButton("💾 Save")
        btn_save.clicked.connect(self._save_session)
        btn_save.setMinimumHeight(36)

        self._btn_open = QPushButton("📋 Open Excel")
        self._btn_open.clicked.connect(self._open_file)
        self._btn_open.setMinimumHeight(36)

        self._btn_export_report = QPushButton("📊 Export Report")
        self._btn_export_report.clicked.connect(self._export_report)
        self._btn_export_report.setEnabled(False)

        self._btn_export_fixed = QPushButton("📝 Export Fixed")
        self._btn_export_fixed.clicked.connect(self._export_fixed)
        self._btn_export_fixed.setEnabled(False)

        self._btn_batch_edit = QPushButton("✏ Batch Edit")
        self._btn_batch_edit.clicked.connect(self._batch_edit)
        self._btn_batch_edit.setEnabled(False)

        self._btn_delete = QPushButton("🗑 Delete")
        self._btn_delete.clicked.connect(self._delete_selected)
        self._btn_delete.setEnabled(False)

        self._btn_settings = QPushButton("⚙ Settings")
        self._btn_settings.clicked.connect(self._open_settings)

        self._progress_bar = QProgressBar()
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(100)
        self._progress_bar.setValue(0)
        self._progress_bar.setMinimumWidth(200)
        self._progress_bar.setFormat("%v/%m (%p%)")
        self._progress_bar.setTextVisible(True)

        toolbar_layout.addWidget(btn_new)
        toolbar_layout.addWidget(btn_open_session)
        toolbar_layout.addWidget(btn_save)
        toolbar_layout.addWidget(self._btn_open)
        toolbar_layout.addWidget(self._btn_export_report)
        toolbar_layout.addWidget(self._btn_export_fixed)
        toolbar_layout.addWidget(self._btn_batch_edit)
        toolbar_layout.addWidget(self._btn_delete)
        toolbar_layout.addWidget(self._btn_settings)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(QLabel("Progress:"))
        toolbar_layout.addWidget(self._progress_bar)

        main_layout.addLayout(toolbar_layout)

        splitter = QSplitter(Qt.Horizontal)

        self._table_widget = TableWidget()
        self._table_widget.record_selected.connect(self._on_record_selected)
        self._table_widget.jump_requested.connect(self._on_table_jump)
        self._table_widget.filter_changed.connect(self._on_filter_changed)

        self._review_panel = ReviewPanel()
        self._review_panel.previous_requested.connect(self._previous)
        self._review_panel.next_requested.connect(self._next)
        self._review_panel.jump_requested.connect(self._jump_cam350)
        self._review_panel.ok_requested.connect(self._mark_ok)
        self._review_panel.edit_requested.connect(self._mark_edit)

        splitter.addWidget(self._table_widget)
        splitter.addWidget(self._review_panel)
        splitter.setSizes([700, 500])

        main_layout.addWidget(splitter)

    def _build_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel("Ready")
        self._statusbar.addWidget(self._status_label)
        self._search_count_label = QLabel("")
        self._statusbar.addPermanentWidget(self._search_count_label)

    def _setup_shortcuts(self) -> None:
        QAction("Space", self, triggered=self._mark_ok, shortcut=Qt.Key_Space)
        QAction("Ctrl+E", self, triggered=self._mark_edit, shortcut=QKeySequence("Ctrl+E"))
        QAction("Up", self, triggered=self._previous, shortcut=Qt.Key_Up)
        QAction("Down", self, triggered=self._next, shortcut=Qt.Key_Down)
        QAction("Ctrl+F", self, triggered=self._focus_search, shortcut=QKeySequence("Ctrl+F"))

    def _restore_state(self) -> None:
        cfg = self._config_mgr.config

        if cfg.geometry:
            try:
                self.restoreGeometry(bytes.fromhex(cfg.geometry))
            except (ValueError, AttributeError):
                pass

        last_session = cfg.lastSessionFile
        if last_session and os.path.exists(last_session):
            try:
                session = self._session_service.load(last_session)
                if session.records:
                    records = self._session_service.list_to_records(session.records)
                    self._repo.delete_all()
                    for r in records:
                        r.id = self._repo.insert(r)
                    self._records = self._repo.get_all()
                    self._session_file = last_session
                    self._table_widget.set_records(self._records)
                    self._review_panel.set_record_list(self._records)
                    self._btn_export_report.setEnabled(True)
                    self._btn_batch_edit.setEnabled(True)
                    self._btn_delete.setEnabled(True)

                    if session.source_file and os.path.exists(session.source_file):
                        try:
                            self._pickplace_data = self._reader.read(session.source_file)
                            self._btn_export_fixed.setEnabled(True)
                        except (FileNotFoundError, ValueError):
                            pass

                    target = min(session.current_index, len(self._records) - 1)
                    self._select_and_display(target)
                    self._update_progress()
                    self._status_label.setText(f"Restored session: {os.path.basename(last_session)}")
                    return
            except (FileNotFoundError, json.JSONDecodeError):
                pass

        self._status_label.setText("No session to restore. Open a PickPlace file or load a session.")

    def _clear_all(self) -> None:
        self._repo.delete_all()
        self._records = []
        self._pickplace_data = None
        self._current_index = -1
        self._session_file = None
        self._table_widget.set_records([])
        self._review_panel.set_record_list([])
        self._btn_export_report.setEnabled(False)
        self._btn_export_fixed.setEnabled(False)
        self._btn_batch_edit.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._update_progress()
        self._status_label.setText("Ready")

    def _new_session(self) -> None:
        if self._records:
            reply = QMessageBox.question(
                self, "New Session",
                "Current session not saved. Discard?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._clear_all()
        self._status_label.setText("New session created")

    def _open_session(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Session", "",
            "CAM350 Review Files (*.cam350review);;All Files (*.*)"
        )
        if not file_path:
            return

        try:
            session = self._session_service.load(file_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "Error", f"Failed to load session: {e}")
            return

        if not session.records:
            QMessageBox.warning(self, "Warning", "Session file is empty.")
            return

        records = self._session_service.list_to_records(session.records)

        self._clear_all()

        self._repo.delete_all()
        for r in records:
            r.id = self._repo.insert(r)

        self._records = self._repo.get_all()
        self._session_file = file_path
        self._pickplace_data = None

        if session.source_file:
            try:
                self._pickplace_data = self._reader.read(session.source_file)
            except (FileNotFoundError, ValueError):
                self._pickplace_data = None

        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._btn_export_report.setEnabled(True)
        self._btn_export_fixed.setEnabled(self._pickplace_data is not None)
        self._btn_batch_edit.setEnabled(True)
        self._btn_delete.setEnabled(True)

        target = min(session.current_index, len(self._records) - 1)
        self._select_and_display(target)

        self._update_progress()
        self._status_label.setText(f"Loaded session: {os.path.basename(file_path)}")

    def _save_session_as(self) -> None:
        if not self._records:
            QMessageBox.warning(self, "Warning", "No data to save.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Session As", "",
            "CAM350 Review Files (*.cam350review);;All Files (*.*)"
        )
        if not file_path:
            return

        if not file_path.endswith(".cam350review"):
            file_path += ".cam350review"

        source_file = self._config_mgr.config.lastFile if self._pickplace_data else ""
        self._session_service.save(
            file_path, self._records,
            source_file=source_file,
            current_index=max(self._current_index, 0),
        )
        self._session_file = file_path
        self._status_label.setText(f"Session saved: {os.path.basename(file_path)}")

    def _save_session(self) -> None:
        if not self._records:
            QMessageBox.warning(self, "Warning", "No data to save.")
            return

        if self._session_file:
            source_file = self._config_mgr.config.lastFile if self._pickplace_data else ""
            self._session_service.save(
                self._session_file, self._records,
                source_file=source_file,
                current_index=max(self._current_index, 0),
            )
            self._status_label.setText(f"Session saved: {os.path.basename(self._session_file)}")
        else:
            self._save_session_as()

    def _open_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open PickPlace File", "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            data = self._reader.read(file_path)
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, "Error", str(e))
            return

        self._pickplace_data = data
        self._config_mgr.update(lastFile=file_path)

        self._repo.delete_all()
        self._records = []
        for comp in data.components:
            record = ReviewRecord(
                designator=comp.designator,
                mpn=comp.mpn,
                layer=comp.layer,
                old_x=comp.x,
                old_y=comp.y,
                old_rotation=comp.rotation,
                status="Pending",
                row_index=comp.row,
            )
            record.id = self._repo.insert(record)
            self._records.append(record)

        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._btn_export_report.setEnabled(True)
        self._btn_export_fixed.setEnabled(True)
        self._btn_batch_edit.setEnabled(True)
        self._btn_delete.setEnabled(True)

        if self._records:
            self._select_and_display(0)

        self._update_progress()
        self._status_label.setText(f"Loaded {len(data.components)} components from {os.path.basename(file_path)}")

    def _select_and_display(self, index: int, progress_text: str = "") -> None:
        if not self._records or index < 0 or index >= len(self._records):
            return
        self._current_index = index
        record = self._records[index]
        self._table_widget.select_record(index)
        self._review_panel.display_record(record, index, len(self._records), progress_text)

    def _on_record_selected(self, index: int) -> None:
        self._select_and_display(index)

    def _on_table_jump(self, index: int) -> None:
        self._select_and_display(index)
        self._jump_cam350()

    def _on_filter_changed(self, filtered: int, total: int) -> None:
        self._search_count_label.setText(f"Showing {filtered} / {total}")

    def _previous(self) -> None:
        if self._current_index > 0:
            self._select_and_display(self._current_index - 1)

    def _next(self) -> None:
        if self._current_index < len(self._records) - 1:
            self._select_and_display(self._current_index + 1)

    def _jump_cam350(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        jump_x = record.new_x if record.new_x is not None else record.old_x
        jump_y = record.new_y if record.new_y is not None else record.old_y
        try:
            self._cam350.jump_to(jump_x, jump_y)
            self._status_label.setText(f"Jumped to {record.designator}: ({jump_x}, {jump_y})")
        except RuntimeError as e:
            QMessageBox.warning(self, "CAM350 Error", str(e))

    def _mark_ok(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        record.status = "OK"
        record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._repo.update(record)
        self._table_widget.update_record_status(self._current_index, "OK")
        self._update_progress()
        self._config_mgr.update(lastReviewId=record.id)
        self._status_label.setText(f"{record.designator}: OK")
        QApplication.processEvents()
        self._next()

    def _mark_edit(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        dialog = EditDialog(record, self)
        if dialog.exec():
            record.status = "Edited"
            record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._repo.update(record)
            self._table_widget.update_record_row(self._current_index)
            self._update_progress()
            self._config_mgr.update(lastReviewId=record.id)
            self._status_label.setText(f"{record.designator}: Edited")
            QApplication.processEvents()
            self._next()

    def _update_progress(self) -> None:
        if not self._records:
            self._progress_bar.setValue(0)
            return
        ok_count = 0
        edit_count = 0
        for r in self._records:
            if r.status == "OK":
                ok_count += 1
            elif r.status == "Edited":
                edit_count += 1
        reviewed = ok_count + edit_count
        total = len(self._records)
        pct = int(reviewed / total * 100) if total else 0
        self._progress_bar.setMaximum(total)
        self._progress_bar.setValue(reviewed)
        self._progress_bar.setFormat(f"OK: {ok_count}  Edited: {edit_count}  Total: {total}  ({pct}%)")


    def _export_report(self) -> None:
        if not self._records:
            QMessageBox.warning(self, "Warning", "No data to export.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Review_Report_{timestamp}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Review Report", default_name,
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
        try:
            file_path = self._exporter.export_report(self._records, file_path)
            QMessageBox.information(self, "Success", f"Report exported:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _export_fixed(self) -> None:
        if not self._records or self._pickplace_data is None:
            QMessageBox.warning(self, "Warning", "No data to export. Load a file first.")
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"PickPlace_Fixed_{timestamp}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export PickPlace Fixed", default_name,
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
        try:
            file_path = self._exporter.export_pickplace_fixed(
                self._records, self._pickplace_data, file_path
            )
            QMessageBox.information(self, "Success", f"Fixed file exported:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _batch_edit(self) -> None:
        indices = self._table_widget.get_checked_indices()
        if not indices:
            QMessageBox.warning(self, "Warning", "No records selected. Check records in the table first.")
            return
        dialog = BatchEditDialog(self)
        if not dialog.exec():
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        for idx in indices:
            record = self._records[idx]
            if dialog.is_apply_x:
                record.new_x = record.old_x + dialog.offset_x
            if dialog.is_apply_y:
                record.new_y = record.old_y + dialog.offset_y
            if dialog.is_apply_rotation:
                record.new_rotation = record.old_rotation + dialog.offset_rotation
            if dialog.remark:
                record.remark = dialog.remark
            record.status = "Edited"
            record.review_time = timestamp
            self._repo.update(record)
            self._table_widget.update_record_row(idx)
        self._update_progress()
        self._status_label.setText(f"Batch edited {len(indices)} records")

    def _delete_selected(self) -> None:
        indices = self._table_widget.get_checked_indices()
        if not indices:
            QMessageBox.warning(self, "Warning", "No records selected. Check records in the table first.")
            return
        reply = QMessageBox.question(
            self, "Delete Records",
            f"Delete {len(indices)} selected records?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for idx in sorted(indices, reverse=True):
            record = self._records[idx]
            self._repo.delete_by_id(record.id)
            self._records.pop(idx)
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._update_progress()
        if not self._records:
            self._clear_all()
        else:
            new_index = min(self._current_index, len(self._records) - 1)
            self._select_and_display(new_index)
        self._status_label.setText(f"Deleted {len(indices)} records")

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.exec()

    def _open_calibration(self) -> None:
        wizard = CalibrationWizard(self)
        wizard.show()

    def _focus_search(self) -> None:
        self._table_widget._search_input.setFocus()

    def closeEvent(self, event) -> None:
        if self._records:
            reply = QMessageBox.question(
                self, "Save Session",
                "Save current session before closing?\n"
                "Yes: save session file\n"
                "No: discard all changes",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
            )
            if reply == QMessageBox.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.Yes:
                self._save_session()
            elif reply == QMessageBox.No:
                self._repo.delete_all()

        cfg = self._config_mgr.config
        geo = self.saveGeometry()
        cfg.geometry = geo.hex()
        cfg.lastSessionFile = self._session_file or ""
        self._config_mgr.save()
        super().closeEvent(event)
