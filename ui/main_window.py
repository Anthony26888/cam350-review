import math
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QMessageBox, QFileDialog, QStatusBar,
    QLabel, QSplitter, QMenuBar, QMenu, QToolBar,
    QApplication, QDialog, QProgressDialog, QStyle,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize
from PySide6.QtGui import (
    QAction, QKeySequence, QIcon, QPixmap, QPainter, QColor, QPen,
)

from config.config_manager import ConfigManager
from database.review_repo import ReviewRepo
from license.info import license_summary
from models.review import ReviewRecord
from models.pickplace import PickPlaceData, PickPlaceComponent, COLUMN_FIELDS
from services.pickplace_reader import PickPlaceReader, STANDARD_MAPPING
from services.cam350_controller import Cam350Controller
from services.export_service import ExportService
from services.datasheet_service import DatasheetService
from services.session_service import SessionService
from ui.table_widget import TableWidget
from ui.review_panel import ReviewPanel
from ui.edit_dialog import EditDialog
from ui.batch_edit_dialog import BatchEditDialog
from ui.mapping_dialog import ColumnMappingDialog
from ui.settings_dialog import SettingsDialog
from ui.calibration_wizard import CalibrationWizard
from ui.origin_align_wizard import OriginAlignWizard
from ui.gerber_viewer import GerberViewer
from ui.i18n import tr
from utils.path_utils import resource_path
from utils.version import APP_VERSION
from ui.jump_popup import JumpPopup


def _icon_stroke() -> str:
    try:
        if ConfigManager.instance().config.theme == "dark":
            return "#CBD5E1"
    except Exception:
        pass
    return "#334155"


def _icon_stroke_disabled() -> str:
    try:
        if ConfigManager.instance().config.theme == "dark":
            return "#475569"
    except Exception:
        pass
    return "#94A3B8"


def _paint_icon(draw, size: int = 26) -> QIcon:
    icon = QIcon()
    for mode, color in (
        (QIcon.Mode.Normal, _icon_stroke()),
        (QIcon.Mode.Disabled, _icon_stroke_disabled()),
    ):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(color), 1.6))
        p.setBrush(Qt.NoBrush)
        draw(p, size)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def _board_icon() -> QIcon:
    def _d(p, s):
        p.drawRoundedRect(1.5, 1.5, s - 3, s - 3, 2.0, 2.0)
        p.setPen(QPen(QColor("#0EA5E9"), 1.2))
        p.drawLine(s * 0.3, s * 0.42, s * 0.7, s * 0.42)
        p.drawLine(s * 0.5, s * 0.42, s * 0.5, s * 0.72)
        p.setBrush(QColor("#0EA5E9"))
        p.setPen(Qt.NoPen)
        for x, y in ((s * 0.42, s * 0.36), (s * 0.58, s * 0.62)):
            p.drawRect(x, y, s * 0.15, s * 0.12)
    return _paint_icon(_d)


def _doc_icon() -> QIcon:
    def _d(p, s):
        p.drawRect(2.5, 1.5, s - 7, s - 3)
        for y in (s * 0.3, s * 0.5, s * 0.7):
            p.drawLine(s * 0.2, y, s * 0.62, y)
    return _paint_icon(_d)


def _grid_icon() -> QIcon:
    def _d(p, s):
        p.drawRect(1.5, 1.5, s - 3, s - 3)
        for i in range(1, 4):
            y = 1.5 + i * (s - 3) / 4.0
            x = 1.5 + i * (s - 3) / 4.0
            p.drawLine(1.5, y, s - 1.5, y)
            p.drawLine(x, 1.5, x, s - 1.5)
    return _paint_icon(_d)


def _chip_icon() -> QIcon:
    def _d(p, s):
        p.drawRect(s * 0.25, s * 0.25, s * 0.5, s * 0.5)
        for i in range(3):
            t = s * (0.3 + i * 0.2)
            p.drawLine(s * 0.1, t, s * 0.25, t)
            p.drawLine(s * 0.75, t, s * 0.9, t)
            p.drawLine(t, s * 0.1, t, s * 0.25)
            p.drawLine(t, s * 0.75, t, s * 0.9)
    return _paint_icon(_d)


def _gear_icon() -> QIcon:
    def _d(p, s):
        c = s / 2.0
        for i in range(8):
            a = math.radians(i * 45.0)
            dx, dy = math.cos(a), math.sin(a)
            p.drawLine(c + dx * 4.5, c + dy * 4.5, c + dx * 9.0, c + dy * 9.0)
        p.drawEllipse(2.5, 2.5, s - 5, s - 5)
        p.drawEllipse(c - 2.2, c - 2.2, 4.4, 4.4)
    return _paint_icon(_d)


def _export_icon() -> QIcon:
    def _d(p, s):
        p.drawRect(2.0, 1.5, s - 9, s - 7)
        for y in (s * 0.28, s * 0.46):
            p.drawLine(s * 0.2, y, s * 0.55, y)
        p.drawLine(s * 0.62, s * 0.5, s - 2.0, s * 0.5)
        p.drawLine(s - 2.5, s * 0.36, s - 0.5, s * 0.5)
        p.drawLine(s - 2.5, s * 0.64, s - 0.5, s * 0.5)
    return _paint_icon(_d)


class DatasheetWorker(QThread):
    finished_search = Signal(str, str)
    error = Signal(str)

    def __init__(self, mpn: str, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mpn = mpn

    def run(self) -> None:
        try:
            url = DatasheetService.search(self._mpn)
            self.finished_search.emit(self._mpn, url)
        except Exception as e:
            self.error.emit(str(e))


class ExportWorker(QThread):
    finished_ok = Signal(str)
    finished_err = Signal(str)

    def __init__(
        self, func: Any, args: tuple, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(parent)
        self._func = func
        self._args = args

    def run(self) -> None:
        try:
            path = self._func(*self._args)
            self.finished_ok.emit(path)
        except Exception as e:
            self.finished_err.emit(str(e))


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
        self._gerber_viewer: Optional[QWidget] = None
        self._gerber_view_settings: Dict[str, Any] = {}
        self._current_index: int = -1
        self._session_service = SessionService()
        self._session_file: Optional[str] = None
        self._dirty = False
        self._jump_popup: Optional[JumpPopup] = None
        self._toolbar: Optional[QToolBar] = None

        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self._undo_action: Optional[QAction] = None
        self._redo_action: Optional[QAction] = None
        self._datasheet_worker: Optional[DatasheetWorker] = None
        self._export_worker: Optional[ExportWorker] = None

        self.setWindowTitle("CAM350 Review Assistant")
        self.setWindowIcon(QIcon(resource_path("assets/icon.ico")))
        self.setMinimumSize(1200, 700)

        self._build_menus()
        self._build_ui()
        self._build_statusbar()
        self._setup_shortcuts()
        self._restore_state()

    def _build_menus(self) -> None:
        menubar = self._menubar = QMenuBar()

        file_menu = menubar.addMenu(tr("&File"))

        new_action = QAction(tr("New Session"), self)
        new_action.setShortcut(QKeySequence.New)
        new_action.triggered.connect(self._new_session)
        file_menu.addAction(new_action)

        open_session_action = QAction(tr("Open Session..."), self)
        open_session_action.setShortcut(QKeySequence("Ctrl+O"))
        open_session_action.triggered.connect(self._open_session)
        file_menu.addAction(open_session_action)

        save_action = QAction(tr("Save Session"), self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_session)
        file_menu.addAction(save_action)

        save_as_action = QAction(tr("Save Session As..."), self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_session_as)
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        open_pickplace_action = QAction(tr("Open PickPlace Excel..."), self)
        open_pickplace_action.setShortcut(QKeySequence("Ctrl+W"))
        open_pickplace_action.triggered.connect(self._open_file)
        file_menu.addAction(open_pickplace_action)

        open_pickplace_mapped_action = QAction(tr("Open PickPlace with Mapping..."), self)
        open_pickplace_mapped_action.triggered.connect(self._open_file_mapped)
        file_menu.addAction(open_pickplace_mapped_action)

        export_menu = file_menu.addMenu(tr("&Export"))
        export_report_action = QAction(tr("Export Review Report"), self)
        export_report_action.triggered.connect(self._export_report)
        export_menu.addAction(export_report_action)

        export_fixed_action = QAction(tr("Export PickPlace Fixed"), self)
        export_fixed_action.triggered.connect(self._export_fixed)
        export_menu.addAction(export_fixed_action)

        file_menu.addSeparator()
        exit_action = QAction(tr("Exit"), self)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        edit_menu = menubar.addMenu(tr("&Edit"))
        self._undo_action = QAction(tr("Undo"), self)
        self._undo_action.setShortcut(QKeySequence.Undo)
        self._undo_action.triggered.connect(self._undo)
        self._undo_action.setEnabled(False)
        edit_menu.addAction(self._undo_action)

        self._redo_action = QAction(tr("Redo"), self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._redo_action.triggered.connect(self._redo)
        self._redo_action.setEnabled(False)
        edit_menu.addAction(self._redo_action)

        tools_menu = menubar.addMenu(tr("&Tools"))
        align_action = QAction(tr("Align PickPlace Origin..."), self)
        align_action.triggered.connect(self._align_origin)
        tools_menu.addAction(align_action)

        gerber_check_action = QAction(tr("Gerber View..."), self)
        gerber_check_action.triggered.connect(self._open_gerber_check)
        tools_menu.addAction(gerber_check_action)
        self._gerber_check_action = gerber_check_action

        tools_menu.addSeparator()

        pcb_info_action = QAction(tr("PCB Info..."), self)
        pcb_info_action.triggered.connect(self._open_pcb_info)
        tools_menu.addAction(pcb_info_action)

        tools_menu.addSeparator()

        calibrate_action = QAction(tr("Calibration Wizard"), self)
        calibrate_action.triggered.connect(self._open_calibration)
        tools_menu.addAction(calibrate_action)

        settings_action = QAction(tr("Settings"), self)
        settings_action.triggered.connect(self._open_settings)
        tools_menu.addAction(settings_action)

        help_menu = menubar.addMenu(tr("&Help"))
        about_action = QAction(tr("About"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)

        toolbar = QToolBar("Main Toolbar")
        self._toolbar = toolbar
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(24, 24))

        def _std_button(tip: str, icon_factory: Callable[[], QIcon]) -> QPushButton:
            btn = QPushButton()
            btn.setToolTip(tip)
            btn.setIcon(icon_factory())
            btn.setFixedSize(34, 30)
            return btn

        spi = self.style().standardIcon
        icon_sources: List[tuple[QPushButton, Callable[[], QIcon]]] = []

        def _register(btn: QPushButton, factory: Callable[[], QIcon]) -> QPushButton:
            icon_sources.append((btn, factory))
            return btn

        btn_new = _register(
            _std_button(tr("New Session (Ctrl+N)"), lambda: spi(QStyle.StandardPixmap.SP_FileIcon)),
            lambda: spi(QStyle.StandardPixmap.SP_FileIcon),
        )
        btn_new.clicked.connect(self._new_session)

        btn_open_session = _register(
            _std_button(tr("Open Session (Ctrl+O)"), lambda: spi(QStyle.StandardPixmap.SP_DialogOpenButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogOpenButton),
        )
        btn_open_session.clicked.connect(self._open_session)

        btn_save = _register(
            _std_button(tr("Save Session (Ctrl+S)"), lambda: spi(QStyle.StandardPixmap.SP_DialogSaveButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        btn_save.clicked.connect(self._save_session)

        self._btn_open = _register(_std_button(tr("Open PickPlace Excel"), _grid_icon), _grid_icon)
        self._btn_open.clicked.connect(self._open_file)

        self._btn_align = _register(
            _std_button(tr("Align PickPlace Origin"), lambda: spi(QStyle.StandardPixmap.SP_BrowserReload)),
            lambda: spi(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._btn_align.clicked.connect(self._align_origin)
        self._btn_align.setEnabled(False)

        self._btn_gerber_check = _register(_std_button(tr("Gerber View"), _board_icon), _board_icon)
        self._btn_gerber_check.clicked.connect(self._open_gerber_check)
        self._btn_gerber_check.setEnabled(False)

        self._btn_export_report = _register(_std_button(tr("Export Review Report"), _doc_icon), _doc_icon)
        self._btn_export_report.clicked.connect(self._export_report)
        self._btn_export_report.setEnabled(False)

        self._btn_export_fixed = _register(_std_button(tr("Export PickPlace Fixed"), _export_icon), _export_icon)
        self._btn_export_fixed.clicked.connect(self._export_fixed)
        self._btn_export_fixed.setEnabled(False)

        self._btn_batch_edit = _register(
            _std_button(tr("Batch Edit"), lambda: spi(QStyle.StandardPixmap.SP_FileDialogInfoView)),
            lambda: spi(QStyle.StandardPixmap.SP_FileDialogInfoView),
        )
        self._btn_batch_edit.clicked.connect(self._batch_edit)
        self._btn_batch_edit.setEnabled(False)

        self._btn_pcb_info = _register(_std_button(tr("PCB Info"), _chip_icon), _chip_icon)
        self._btn_pcb_info.clicked.connect(self._open_pcb_info)

        self._btn_ok_checked = _register(
            _std_button(tr("OK Checked"), lambda: spi(QStyle.StandardPixmap.SP_DialogApplyButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        self._btn_ok_checked.setObjectName("success")
        self._btn_ok_checked.setEnabled(False)

        self._btn_delete = _register(
            _std_button(tr("Delete Selected"), lambda: spi(QStyle.StandardPixmap.SP_TrashIcon)),
            lambda: spi(QStyle.StandardPixmap.SP_TrashIcon),
        )
        self._btn_delete.setObjectName("danger")
        self._btn_delete.setEnabled(False)

        self._btn_settings = _register(_std_button(tr("Settings"), _gear_icon), _gear_icon)
        self._btn_settings.clicked.connect(self._open_settings)

        self._toolbar_icon_sources = icon_sources

        toolbar.addWidget(btn_new)
        toolbar.addWidget(btn_open_session)
        toolbar.addWidget(btn_save)
        toolbar.addSeparator()
        toolbar.addWidget(self._btn_open)
        toolbar.addWidget(self._btn_align)
        toolbar.addWidget(self._btn_gerber_check)
        toolbar.addSeparator()
        toolbar.addWidget(self._btn_export_report)
        toolbar.addWidget(self._btn_export_fixed)
        toolbar.addSeparator()
        toolbar.addWidget(self._btn_batch_edit)
        toolbar.addWidget(self._btn_pcb_info)
        toolbar.addWidget(self._btn_ok_checked)
        toolbar.addWidget(self._btn_delete)
        toolbar.addSeparator()
        toolbar.addWidget(self._btn_settings)

        self.addToolBar(toolbar)

        self.setMenuBar(self._menubar)

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
        self._review_panel.datasheet_requested.connect(self._search_datasheet)

        splitter.addWidget(self._table_widget)
        splitter.addWidget(self._review_panel)
        splitter.setSizes([700, 500])

        main_layout.addWidget(splitter)

    def _apply_toolbar_icons(self) -> None:
        for btn, factory in getattr(self, "_toolbar_icon_sources", []):
            btn.setIcon(factory())

    def refresh_icons(self) -> None:
        self._apply_toolbar_icons()

    def _build_statusbar(self) -> None:
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)
        self._status_label = QLabel(tr("Ready"))
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

        self._status_label.setText(tr("No session to restore. Open a PickPlace file or load a session."))

    def _clear_all(self) -> None:
        self._dirty = False
        self._repo.delete_all()
        self._records = []
        self._pickplace_data = None
        self._gerber_viewer = None
        self._current_index = -1
        self._session_file = None
        self._table_widget.set_records([])
        self._review_panel.set_record_list([])
        self._review_panel.clear_record()
        self._btn_export_report.setEnabled(False)
        self._btn_export_fixed.setEnabled(False)
        self._btn_batch_edit.setEnabled(False)
        self._btn_ok_checked.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._btn_align.setEnabled(False)
        self._clear_gerber_config()
        self._update_gerber_view_button()
        self._update_progress()
        self._status_label.setText(tr("Ready"))
        from database.pcb_info_repo import PcbInfoRepo
        try:
            PcbInfoRepo().clear()
        except RuntimeError:
            pass

    def _clear_gerber_config(self) -> None:
        self._config_mgr.update(
            gerberGko="", gerberGtp="", gerberGbp="",
            gerberGto="", gerberGbo="",
        )

    @staticmethod
    def _current_pcb_info_dict() -> Optional[dict]:
        from database.pcb_info_repo import PcbInfoRepo
        try:
            pcb = PcbInfoRepo().load()
        except RuntimeError:
            return None
        if not pcb.has_data():
            return None
        return pcb.to_dict()

    def _update_gerber_view_button(self) -> None:
        enabled = bool(self._records)
        self._btn_gerber_check.setEnabled(enabled)
        self._gerber_check_action.setEnabled(enabled)

    @staticmethod
    def _restore_pcb_info(session) -> None:
        from database.pcb_info_repo import PcbInfoRepo
        from models.pcb_info import PcbInfo
        repo = PcbInfoRepo()
        if session.pcb_info:
            try:
                repo.save(PcbInfo.from_dict(session.pcb_info))
                return
            except RuntimeError:
                pass
        try:
            repo.clear()
        except RuntimeError:
            pass

    def _restore_session_gerber(self, session) -> None:
        paths = {
            "gerberGko": getattr(session, "gerberGko", ""),
            "gerberGtp": getattr(session, "gerberGtp", ""),
            "gerberGbp": getattr(session, "gerberGbp", ""),
            "gerberGto": getattr(session, "gerberGto", ""),
            "gerberGbo": getattr(session, "gerberGbo", ""),
        }
        embedded = getattr(session, "gerber_files", None) or {}
        if embedded:
            paths = self._materialize_embedded_gerber(paths, embedded)
        paths = {k: v for k, v in paths.items() if v}
        if paths:
            self._config_mgr.update(**paths)
        else:
            self._config_mgr.update(
                gerberGko="", gerberGtp="", gerberGbp="",
                gerberGto="", gerberGbo="",
            )

    @staticmethod
    def _materialize_embedded_gerber(paths: Dict[str, str], embedded: Dict[str, str]) -> Dict[str, str]:
        from services.session_service import decompress_text
        from utils.path_utils import user_data_dir

        tmp_dir = os.path.join(user_data_dir(), "tmp_gerber")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
        except OSError:
            return paths
        for key, payload in embedded.items():
            if not payload:
                continue
            if paths.get(key) and os.path.exists(paths[key]):
                continue
            try:
                text = decompress_text(payload)
            except Exception:
                continue
            ext = {
                "gerberGko": "gko", "gerberGtp": "gtp", "gerberGbp": "gbp",
                "gerberGto": "gto", "gerberGbo": "gbo",
            }.get(key, "gbr")
            try:
                target = os.path.join(tmp_dir, f"{key}.{ext}")
                with open(target, "w", encoding="utf-8") as f:
                    f.write(text)
                paths[key] = target
            except (IOError, OSError):
                continue
        return paths

    def _existing_gerber_paths(self) -> Dict[str, str]:
        cfg = self._config_mgr.config
        out = {}
        for key in ("gerberGko", "gerberGtp", "gerberGbp", "gerberGto", "gerberGbo"):
            val = getattr(cfg, key, "")
            if val and os.path.exists(val):
                out[key] = val
        return out

    @staticmethod
    def _collect_gerber_files(paths: Dict[str, str]) -> Dict[str, str]:
        from services.session_service import compress_text

        out = {}
        for key, path in (paths or {}).items():
            if not path or not os.path.exists(path):
                continue
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    out[key] = compress_text(f.read())
            except (IOError, OSError):
                continue
        return out

    @staticmethod
    def _build_pickplace_data_from_records(records: List[ReviewRecord]) -> PickPlaceData:
        components = []
        raw_data = []
        seen = set()
        for r in records:
            if r.designator in seen:
                continue
            seen.add(r.designator)
            comp = PickPlaceComponent(
                designator=r.designator,
                mpn=r.mpn,
                layer=r.layer,
                x=r.old_x,
                y=r.old_y,
                rotation=r.old_rotation,
                row=r.row_index,
            )
            components.append(comp)
            raw_data.append({
                "Designator": r.designator,
                "MPN": r.mpn,
                "Layer": r.layer,
                "X": r.old_x,
                "Y": r.old_y,
                "Rotation": r.old_rotation,
            })
        return PickPlaceData(
            headers=["Designator", "MPN", "Layer", "X", "Y", "Rotation"],
            components=components,
            raw_data=raw_data,
        )

    def _new_session(self) -> None:
        if self._dirty and self._records:
            reply = QMessageBox.question(
                self, tr("New Session"),
                tr("Current session not saved. Discard?"),
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        self._clear_all()
        self._status_label.setText(tr("New session created"))

    def _open_session(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open Session"), "",
            "CAM350 Review Files (*.cam350review);;All Files (*.*)"
        )
        if not file_path:
            return

        try:
            session = self._session_service.load(file_path)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to load session: {e}", e=str(e)))
            return

        if not session.records:
            QMessageBox.warning(self, tr("Warning"), tr("Session file is empty."))
            return

        records = self._session_service.list_to_records(session.records)

        self._clear_all()

        self._repo.delete_all()
        for r in records:
            r.id = self._repo.insert(r)

        self._records = self._repo.get_all()
        self._records = [r for r in self._records if r.status != "Deleted"]
        self._session_file = file_path
        self._pickplace_data = None
        self._restore_pcb_info(session)
        self._restore_session_gerber(session)
        self._gerber_view_settings = dict(session.gerber_view or {})

        if session.source_file:
            try:
                if session.column_mapping:
                    self._pickplace_data = self._reader.read_with_mapping(
                        session.source_file, session.column_mapping
                    )
                else:
                    self._pickplace_data = self._reader.read(session.source_file)
            except (FileNotFoundError, ValueError):
                self._pickplace_data = None

        if self._pickplace_data is None and records:
            self._pickplace_data = self._build_pickplace_data_from_records(records)

        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._btn_export_report.setEnabled(True)
        self._btn_export_fixed.setEnabled(self._pickplace_data is not None)
        self._btn_batch_edit.setEnabled(True)
        self._btn_ok_checked.setEnabled(True)
        self._btn_delete.setEnabled(True)
        self._btn_align.setEnabled(True)
        self._update_gerber_view_button()

        if self._records:
            target = min(session.current_index, len(self._records) - 1)
            self._select_and_display(target)

        self._update_progress()
        self._dirty = False
        self._status_label.setText(tr("Loaded session: {name}", name=os.path.basename(file_path)))

    def _save_session_as(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Warning"), tr("No data to save."))
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Save Session As"), "",
            "CAM350 Review Files (*.cam350review);;All Files (*.*)"
        )
        if not file_path:
            return

        if not file_path.endswith(".cam350review"):
            file_path += ".cam350review"

        deleted_records = [r for r in self._repo.get_all() if r.status == "Deleted"]
        source_file = self._config_mgr.config.lastFile if self._pickplace_data else ""
        gerber = self._existing_gerber_paths()
        gerber_files = self._collect_gerber_files(gerber)
        self._session_service.save(
            file_path, self._records + deleted_records,
            source_file=source_file,
            current_index=max(self._current_index, 0),
            pcb_info=self._current_pcb_info_dict(),
            gerberGko=gerber.get("gerberGko", ""),
            gerberGtp=gerber.get("gerberGtp", ""),
            gerberGbp=gerber.get("gerberGbp", ""),
            gerberGto=gerber.get("gerberGto", ""),
            gerberGbo=gerber.get("gerberGbo", ""),
            gerber_view=self._current_gerber_view_settings(),
            column_mapping=self._pickplace_data.column_mapping if self._pickplace_data else None,
            gerber_files=gerber_files,
        )
        self._session_file = file_path
        self._config_mgr.update(lastSessionFile=file_path)
        self._dirty = False
        self._status_label.setText(tr("Session saved: {name}", name=os.path.basename(file_path)))

    def _save_session(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Warning"), tr("No data to save."))
            return

        if self._session_file:
            deleted_records = [r for r in self._repo.get_all() if r.status == "Deleted"]
            source_file = self._config_mgr.config.lastFile if self._pickplace_data else ""
            gerber = self._existing_gerber_paths()
            gerber_files = self._collect_gerber_files(gerber)
            self._session_service.save(
                self._session_file, self._records + deleted_records,
                source_file=source_file,
                current_index=max(self._current_index, 0),
                pcb_info=self._current_pcb_info_dict(),
                gerberGko=gerber.get("gerberGko", ""),
                gerberGtp=gerber.get("gerberGtp", ""),
                gerberGbp=gerber.get("gerberGbp", ""),
                gerberGto=gerber.get("gerberGto", ""),
                gerberGbo=gerber.get("gerberGbo", ""),
                gerber_view=self._current_gerber_view_settings(),
                column_mapping=self._pickplace_data.column_mapping if self._pickplace_data else None,
                gerber_files=gerber_files,
            )
            self._config_mgr.update(lastSessionFile=self._session_file)
            self._dirty = False
            self._status_label.setText(tr("Session saved: {name}", name=os.path.basename(self._session_file)))
        else:
            self._save_session_as()

    def _open_file(self) -> None:
        self._open_file_with_mapping(force=False)

    def _open_file_mapped(self) -> None:
        self._open_file_with_mapping(force=True)

    def _open_file_with_mapping(self, force: bool = False) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open PickPlace File"), "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return

        try:
            headers = self._reader.read_headers(file_path)
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        mapping = None
        required = None
        is_standard = all(
            header in headers for header in STANDARD_MAPPING.values()
        )
        if force or not is_standard:
            dialog = ColumnMappingDialog(file_path, headers, parent=self)
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            mapping = dialog.column_mapping
            required = dialog.required_fields

        try:
            if mapping:
                data = self._reader.read_with_mapping(
                    file_path, mapping, required=required
                )
            else:
                data = self._reader.read(file_path)
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        self._apply_loaded_pickplace(data, file_path)

    def _apply_loaded_pickplace(self, data: PickPlaceData, file_path: str) -> None:
        self._pickplace_data = data
        self._config_mgr.update(lastFile=file_path)
        self._clear_gerber_config()

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

        self._dirty = True
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._btn_export_report.setEnabled(True)
        self._btn_export_fixed.setEnabled(True)
        self._btn_batch_edit.setEnabled(True)
        self._btn_ok_checked.setEnabled(True)
        self._btn_delete.setEnabled(True)
        self._btn_align.setEnabled(True)
        self._update_gerber_view_button()

        if self._records:
            self._select_and_display(0)

        self._update_progress()
        self._status_label.setText(
            tr("Loaded {count} components from {name}",
               count=len(data.components), name=os.path.basename(file_path))
        )

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
        self._show_jump_popup()
        self._popup_jump(index)

    def _on_filter_changed(self, filtered: int, total: int) -> None:
        self._search_count_label.setText(f"Showing {filtered} / {total}")

    def _previous(self) -> None:
        if self._current_index > 0:
            self._select_and_display(self._current_index - 1)

    def _next(self) -> None:
        if self._current_index < len(self._records) - 1:
            self._select_and_display(self._current_index + 1)

    def _show_jump_popup(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        if self._jump_popup is None:
            self._jump_popup = JumpPopup()
            self._jump_popup.jump_requested.connect(self._popup_jump)
            self._jump_popup.ok_requested.connect(self._popup_ok)
            self._jump_popup.save_requested.connect(self._popup_save)
            self._jump_popup.delete_requested.connect(self._popup_delete)
        self._jump_popup.show_at(self._records, self._current_index)

    def _popup_jump(self, index: int) -> None:
        if index < 0 or index >= len(self._records):
            return
        self._select_and_display(index)
        record = self._records[index]
        jump_x = record.new_x if record.new_x is not None else record.old_x
        jump_y = record.new_y if record.new_y is not None else record.old_y
        try:
            self._cam350.jump_to(jump_x, jump_y)
            self._status_label.setText(
                tr("Jumped to {des}: ({x}, {y})", des=record.designator, x=jump_x, y=jump_y)
            )
        except RuntimeError as e:
            QMessageBox.warning(self, tr("CAM350 Error"), str(e))
        except Exception:
            self._status_label.setText(tr("Jump cancelled (mouse moved to corner)"))

    def _popup_ok(self, index: int) -> None:
        self._select_and_display(index)
        self._mark_ok()
        if self._jump_popup:
            self._jump_popup.refresh_row(index)
            self._jump_popup.navigate_to(self._current_index)

    def _popup_save(self, index: int, new_x: float, new_y: float, new_rot: float, remark: str) -> None:
        if index < 0 or index >= len(self._records):
            return
        record = self._records[index]
        self._push_undo()
        record.new_x = new_x
        record.new_y = new_y
        record.new_rotation = new_rot
        record.remark = remark
        record.status = "Edited"
        record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._repo.update(record)
        self._table_widget.update_record_row(index)
        self._update_progress()
        self._config_mgr.update(lastReviewId=record.id)
        self._status_label.setText(tr("{des}: Edited", des=record.designator))
        if self._jump_popup:
            self._jump_popup.refresh_row(index)
            self._jump_popup.navigate_to(index)

    def _popup_delete(self, index: int) -> None:
        if index < 0 or index >= len(self._records):
            return
        record = self._records[index]
        reply = QMessageBox.question(
            self, tr("Delete Record"),
            tr("Delete {des}?", des=record.designator),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._push_undo()
        self._repo.delete_by_id(record.id)
        self._records.pop(index)
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._update_progress()
        self._status_label.setText(tr("Deleted {des}", des=record.designator))
        if not self._records:
            if self._jump_popup:
                self._jump_popup.close()
            self._clear_all()
        else:
            new_index = min(index, len(self._records) - 1)
            self._select_and_display(new_index)
            if self._jump_popup:
                self._jump_popup.show_at(self._records, new_index)

    def _jump_cam350(self) -> None:
        self._show_jump_popup()
        self._popup_jump(self._current_index)

    def _mark_ok(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        self._push_undo()
        record.status = "OK"
        if record.new_x is None:
            record.new_x = record.old_x
        if record.new_y is None:
            record.new_y = record.old_y
        if record.new_rotation is None:
            record.new_rotation = record.old_rotation
        record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._repo.update(record)
        self._table_widget.update_record_row(self._current_index)
        self._update_progress()
        self._config_mgr.update(lastReviewId=record.id)
        self._status_label.setText(tr("{des}: OK", des=record.designator))
        QApplication.processEvents()
        self._next()

    def _mark_edit(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        before = self._record_snapshot()
        dialog = EditDialog(record, self)
        if dialog.exec():
            self._push_undo(before)
            record.status = "Edited"
            record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._repo.update(record)
            self._table_widget.update_record_row(self._current_index)
            self._update_progress()
            self._config_mgr.update(lastReviewId=record.id)
            self._status_label.setText(tr("{des}: Edited", des=record.designator))
            QApplication.processEvents()
            self._next()

    def _update_progress(self) -> None:
        if not self._records:
            self._review_panel.update_stats(0, 0, 0, 0, 0)
            return
        total = len(self._records)
        ok_count = sum(1 for r in self._records if r.status == "OK")
        edit_count = sum(1 for r in self._records if r.status == "Edited")
        pending_count = sum(1 for r in self._records if r.status == "Pending")
        align_count = sum(1 for r in self._records if r.status == "Aligned")
        self._review_panel.update_stats(total, ok_count, edit_count, pending_count, align_count)


    def _export_report(self) -> None:
        all_records = self._repo.get_all()
        if not all_records:
            QMessageBox.warning(self, tr("Warning"), tr("No data to export."))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"Review_Report_{timestamp}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export Review Report"), default_name,
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
        self._set_exporting(True)
        worker = ExportWorker(
            self._exporter.export_report, (all_records, file_path), self
        )
        worker.finished_ok.connect(self._on_export_done)
        worker.finished_err.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _export_fixed(self) -> None:
        if not self._records or self._pickplace_data is None:
            QMessageBox.warning(self, tr("Warning"), tr("No data to export. Load a file first."))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"PickPlace_Fixed_{timestamp}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export PickPlace Fixed"), default_name,
            "CSV Files (*.csv);;All Files (*.*)"
        )
        if not file_path:
            return
        self._set_exporting(True)
        from database.pcb_info_repo import PcbInfoRepo
        pcb_info = PcbInfoRepo().load()
        worker = ExportWorker(
            self._exporter.export_pickplace_fixed,
            (self._records, self._pickplace_data, file_path, pcb_info), self
        )
        worker.finished_ok.connect(self._on_export_done)
        worker.finished_err.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _set_exporting(self, exporting: bool) -> None:
        self._btn_export_report.setEnabled(not exporting)
        self._btn_export_fixed.setEnabled(not exporting)
        if exporting:
            self._status_label.setText(tr("Exporting..."))

    def _on_export_done(self, file_path: str) -> None:
        self._set_exporting(False)
        self._status_label.setText(tr("Export complete"))
        QMessageBox.information(self, tr("Success"), tr("File exported:\n{path}", path=file_path))

    def _on_export_error(self, message: str) -> None:
        self._set_exporting(False)
        self._status_label.setText(tr("Export failed"))
        QMessageBox.critical(self, tr("Export Error"), message)

    def _search_datasheet(self, mpn: str) -> None:
        if not mpn:
            return
        if self._datasheet_worker and self._datasheet_worker.isRunning():
            return
        self._status_label.setText(tr("Searching datasheet for {mpn}...", mpn=mpn))
        self._review_panel.set_datasheet("Searching...")
        self._review_panel.set_datasheet_searching(True)
        worker = DatasheetWorker(mpn, self)
        worker.finished_search.connect(self._on_datasheet_finished)
        worker.error.connect(self._on_datasheet_error)
        self._datasheet_worker = worker
        worker.start()

    def _on_datasheet_finished(self, mpn: str, url: str) -> None:
        self._review_panel.set_datasheet_searching(False)
        record = self._records[self._current_index] if 0 <= self._current_index < len(self._records) else None
        if url:
            if record:
                record.datasheet = url
                self._dirty = True
                self._repo.update(record)
            self._review_panel.set_datasheet(url)
            self._status_label.setText(tr("Datasheet found for {mpn}", mpn=mpn))
        else:
            self._review_panel.set_datasheet("")
            self._status_label.setText(tr("No datasheet found for {mpn}", mpn=mpn))

    def _on_datasheet_error(self, message: str) -> None:
        self._review_panel.set_datasheet_searching(False)
        self._review_panel.set_datasheet("")
        self._status_label.setText(tr("Datasheet search error: {message}", message=message))

    def _batch_edit(self) -> None:
        indices = self._table_widget.get_checked_indices()
        if not indices:
            QMessageBox.warning(self, tr("Warning"), tr("No records selected. Check records in the table first."))
            return
        dialog = BatchEditDialog(self)
        if not dialog.exec():
            return

        summary = []
        if dialog.is_apply_x:
            summary.append(f"X offset: {dialog.offset_x}")
        if dialog.is_apply_y:
            summary.append(f"Y offset: {dialog.offset_y}")
        if dialog.is_apply_rotation:
            summary.append(f"Rotation offset: {dialog.offset_rotation}")
        if dialog.is_negative_x:
            summary.append("Make new X negative")
        if dialog.is_negative_y:
            summary.append("Make new Y negative")
        if dialog.remark:
            summary.append(f"Remark: {dialog.remark}")
        if not summary:
            return
        reply = QMessageBox.question(
            self, tr("Confirm Batch Edit"),
            tr("Apply the following to {n} selected records?\n\n- {list}",
               n=len(indices), list="\n- ".join(summary)),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._push_undo()
        progress = QProgressDialog(
            tr("Applying batch edit..."), "Cancel", 0, len(indices), self
        )
        progress.setWindowTitle(tr("Batch Edit"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for count, idx in enumerate(indices, start=1):
            if progress.wasCanceled():
                break
            record = self._records[idx]
            if dialog.is_apply_x:
                base_x = record.new_x if record.new_x is not None else record.old_x
                record.new_x = round(base_x + dialog.offset_x, 4)
            if dialog.is_apply_y:
                base_y = record.new_y if record.new_y is not None else record.old_y
                record.new_y = round(base_y + dialog.offset_y, 4)
            if dialog.is_apply_rotation:
                base_r = record.new_rotation if record.new_rotation is not None else record.old_rotation
                record.new_rotation = round(base_r + dialog.offset_rotation, 4)
            if dialog.is_negative_x:
                base_x = record.new_x if record.new_x is not None else record.old_x
                record.new_x = round(-base_x, 4)
            if dialog.is_negative_y:
                base_y = record.new_y if record.new_y is not None else record.old_y
                record.new_y = round(-base_y, 4)
            if dialog.remark:
                record.remark = dialog.remark
            record.status = "Edited"
            record.review_time = timestamp
            self._repo.update(record)
            self._table_widget.update_record_row(idx)
            progress.setValue(count)
            QApplication.processEvents()
        progress.close()
        self._update_progress()
        self._status_label.setText(tr("Batch edited {n} records", n=len(indices)))

    def _mark_checked_ok(self) -> None:
        indices = self._table_widget.get_checked_indices()
        if not indices:
            QMessageBox.warning(self, tr("Warning"), tr("No records selected."))
            return
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._push_undo()
        progress = QProgressDialog(
            tr("Marking records as OK..."), "Cancel", 0, len(indices), self
        )
        progress.setWindowTitle(tr("Mark OK"))
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)
        for count, idx in enumerate(indices, start=1):
            if progress.wasCanceled():
                break
            record = self._records[idx]
            record.status = "OK"
            if record.new_x is None:
                record.new_x = record.old_x
            if record.new_y is None:
                record.new_y = record.old_y
            if record.new_rotation is None:
                record.new_rotation = record.old_rotation
            record.review_time = timestamp
            self._repo.update(record)
            self._table_widget.update_record_row(idx)
            progress.setValue(count)
            QApplication.processEvents()
        progress.close()
        self._table_widget.clear_checked()
        self._update_progress()
        self._status_label.setText(tr("Marked OK: {n} records", n=len(indices)))

    def _delete_selected(self) -> None:
        indices = self._table_widget.get_checked_indices()
        if not indices:
            QMessageBox.warning(self, tr("Warning"), tr("No records selected. Check records in the table first."))
            return
        reply = QMessageBox.question(
            self, tr("Delete Records"),
            tr("Delete {n} selected records?", n=len(indices)),
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._push_undo()
        for idx in sorted(indices, reverse=True):
            record = self._records[idx]
            record.status = "Deleted"
            self._repo.update(record)
            self._records.pop(idx)
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._update_progress()
        if not self._records:
            self._current_index = -1
            self._session_file = None
            self._review_panel.set_record_list([])
            self._btn_export_report.setEnabled(True)
            self._btn_export_fixed.setEnabled(False)
            self._btn_batch_edit.setEnabled(False)
            self._btn_ok_checked.setEnabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_align.setEnabled(False)
            self._update_gerber_view_button()
            self._status_label.setText(tr("All records deleted"))
        else:
            new_index = min(self._current_index, len(self._records) - 1)
            self._select_and_display(new_index)
            self._status_label.setText(tr("Deleted {n} records", n=len(indices)))

    def _show_about(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("About CAM350 Review Assistant"))
        dlg.setFixedSize(420, 350)
        layout = QVBoxLayout(dlg)

        logo = QLabel()
        pixmap = QPixmap(resource_path("assets/icon.ico"))
        if not pixmap.isNull():
            logo.setPixmap(pixmap.scaled(64, 64, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            logo.setAlignment(Qt.AlignCenter)
            layout.addWidget(logo)

        title = QLabel("<h2 style='text-align:center;'>CAM350 Review Assistant</h2>")
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)

        info = QLabel(
            "<p><b>Version:</b> " + APP_VERSION + "</p>"
            "<p><b>License:</b> " + license_summary().replace("|", "<br>") + "</p>"
            "<p><b>Description:</b> A tool for reviewing and editing PickPlace data, "
            "aligning component origins, and exporting fixed position files for CAM350.</p>"
            "<hr>"
            "<p><b>Created by:</b> Nguyễn Hải Đăng</p>"
            "<p><b>Phone:</b> +84908799042</p>"
            "<p><b>Email:</b> <a href='mailto:haidang34821@gmail.com'>haidang34821@gmail.com</a></p>"
        )
        info.setOpenExternalLinks(True)
        info.setWordWrap(True)
        layout.addWidget(info)

        btn_close = QPushButton(tr("Close"))
        btn_close.clicked.connect(dlg.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignCenter)

        dlg.exec()

    def _open_settings(self) -> None:
        old_language = self._config_mgr.config.language
        dialog = SettingsDialog(self)
        dialog.exec()
        if self._config_mgr.config.language != old_language:
            self._rebuild_for_language()

    def _rebuild_for_language(self) -> None:
        records = self._records
        current_index = self._current_index
        session_file = self._session_file
        dirty = self._dirty
        pickplace_data = self._pickplace_data
        gerber_view_settings = self._gerber_view_settings
        undo_stack = self._undo_stack
        redo_stack = self._redo_stack

        if self._jump_popup is not None:
            self._jump_popup.close()
            self._jump_popup = None
        if self._gerber_viewer is not None:
            self._gerber_viewer.close()
            self._gerber_viewer = None

        if self._toolbar is not None:
            self.removeToolBar(self._toolbar)
            self._toolbar.deleteLater()
            self._toolbar = None
        central = self.centralWidget()
        if central is not None:
            self.setCentralWidget(QWidget())
            central.deleteLater()

        self._build_menus()
        self._build_ui()
        self._build_statusbar()

        self._records = records
        self._pickplace_data = pickplace_data
        self._current_index = current_index
        self._session_file = session_file
        self._dirty = dirty
        self._gerber_view_settings = gerber_view_settings
        self._undo_stack = undo_stack
        self._redo_stack = redo_stack

        has_records = bool(records)
        self._btn_export_report.setEnabled(has_records)
        self._btn_export_fixed.setEnabled(has_records)
        self._btn_batch_edit.setEnabled(has_records)
        self._btn_ok_checked.setEnabled(has_records)
        self._btn_delete.setEnabled(has_records)
        self._btn_align.setEnabled(has_records)
        self._undo_action.setEnabled(bool(undo_stack))
        self._redo_action.setEnabled(bool(redo_stack))
        self._update_gerber_view_button()

        self._table_widget.set_records(records)
        self._review_panel.set_record_list(records)
        if 0 <= current_index < len(records):
            self._review_panel.display_record(
                records[current_index], current_index, len(records)
            )
        else:
            self._review_panel.clear_record()
        self._update_progress()
        self._status_label.setText(tr("Ready"))

    def _open_pcb_info(self) -> None:
        from ui.pcb_info_dialog import PcbInfoDialog
        dialog = PcbInfoDialog(self)
        dialog.exec()

    def _open_calibration(self) -> None:
        wizard = CalibrationWizard(self)
        wizard.show()

    def _align_origin(self) -> None:
        if self._pickplace_data is None:
            QMessageBox.warning(self, tr("Warning"), tr("Please open a PickPlace file first."))
            return

        self._push_undo()
        wizard = OriginAlignWizard(
            self._pickplace_data, self._records, self._apply_align_record, self
        )
        wizard.exec()
        self._update_progress()
        self._update_gerber_view_button()
        self._review_panel.set_record_list(self._records)
        if self._current_index >= 0 and self._current_index < len(self._records):
            self._review_panel.display_record(
                self._records[self._current_index],
                self._current_index, len(self._records),
            )

    def _open_gerber_check(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Warning"), tr("No data. Open a PickPlace file or load a session first."))
            return

        cfg = self._config_mgr.config
        gko = cfg.gerberGko if os.path.exists(cfg.gerberGko) else ""
        gtp = cfg.gerberGtp if os.path.exists(cfg.gerberGtp) else ""
        gbp = cfg.gerberGbp if os.path.exists(cfg.gerberGbp) else ""
        gto = cfg.gerberGto if os.path.exists(cfg.gerberGto) else ""
        gbo = cfg.gerberGbo if os.path.exists(cfg.gerberGbo) else ""

        if not gko:
            gko, _ = QFileDialog.getOpenFileName(
                self, tr("Select GKO file (Outline)"), "",
                "Gerber Files (*.gko *.GKO *.gbr *.GBR);;All Files (*.*)"
            )
            if not gko:
                return
            self._config_mgr.update(gerberGko=gko)
        if not gtp:
            gtp, _ = QFileDialog.getOpenFileName(
                self, tr("Select GTP file (Top Paste - optional)"), "",
                "Gerber Files (*.gtp *.GTP *.gbr *.GBR);;All Files (*.*)"
            )
            self._config_mgr.update(gerberGtp=gtp)
        if not gbp:
            gbp, _ = QFileDialog.getOpenFileName(
                self, tr("Select GBP file (Bottom Paste - optional)"), "",
                "Gerber Files (*.gbp *.GBP *.gbr *.GBR);;All Files (*.*)"
            )
            self._config_mgr.update(gerberGbp=gbp)
        if not gto:
            gto, _ = QFileDialog.getOpenFileName(
                self, tr("Select GTO file (Silkscreen - optional)"), "",
                "Gerber Files (*.gto *.GTO *.gbr *.GBR);;All Files (*.*)"
            )
            self._config_mgr.update(gerberGto=gto)
        if not gbo:
            gbo, _ = QFileDialog.getOpenFileName(
                self, tr("Select GBO file (Bottom Silkscreen - optional)"), "",
                "Gerber Files (*.gbo *.GBO *.gbr *.GBR);;All Files (*.*)"
            )
            self._config_mgr.update(gerberGbo=gbo)

        viewer = GerberViewer(
            self._records, gko, gtp, gbp, gto, gbo,
            display_settings=self._gerber_view_settings,
        )
        viewer.settings_saved.connect(self._on_gerber_view_settings_saved)
        frame = self.frameGeometry()
        view_frame = viewer.frameGeometry()
        view_frame.moveCenter(frame.center())
        viewer.move(view_frame.topLeft())
        self._gerber_viewer = viewer
        viewer.destroyed.connect(self._on_gerber_viewer_closed)
        viewer.show()

    def _on_gerber_viewer_closed(self, *_args: Any) -> None:
        if self._gerber_viewer is not None:
            self._gerber_viewer = None

    def _current_gerber_view_settings(self) -> Dict[str, Any]:
        viewer = getattr(self, "_gerber_viewer", None)
        if viewer is not None and hasattr(viewer, "display_settings"):
            return viewer.display_settings()
        return dict(self._gerber_view_settings)

    def _on_gerber_view_settings_saved(self, settings: dict) -> None:
        self._gerber_view_settings = dict(settings or {})
        if self._session_file and self._records:
            self._save_session()

    def _apply_align_record(
        self, designator: str, new_x: Optional[float],
        new_y: Optional[float], new_rotation: Optional[float],
    ) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = self._find_record(designator)
        if record is None:
            return
        if new_x is not None:
            record.new_x = new_x
        if new_y is not None:
            record.new_y = new_y
        if new_rotation is not None:
            record.new_rotation = new_rotation
        if record.status == "Pending":
            record.status = "Aligned"
        record.review_time = timestamp
        self._repo.update(record)
        self._table_widget.update_record_row(self._records.index(record))

    def _find_record(self, designator: str) -> Optional[ReviewRecord]:
        for r in self._records:
            if r.designator == designator:
                return r
        return None

    def _record_snapshot(self) -> List[Dict[str, Any]]:
        return SessionService.records_to_list(self._records)

    def _push_undo(self, before: Optional[List[Dict[str, Any]]] = None) -> None:
        self._dirty = True
        self._undo_stack.append(before if before is not None else self._record_snapshot())
        if len(self._undo_stack) > 50:
            self._undo_stack.pop(0)
        self._redo_stack.clear()
        self._update_undo_actions()

    def _restore_records(self, snap: List[Dict[str, Any]]) -> None:
        records = SessionService.list_to_records(snap)
        self._repo.delete_all()
        for r in records:
            r.id = self._repo.insert(r)
        self._records = self._repo.get_all()
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        if self._records:
            target = min(self._current_index, len(self._records) - 1)
            self._select_and_display(target)
        else:
            self._current_index = -1
            self._review_panel.set_record_list([])
        self._update_progress()

    def _update_undo_actions(self) -> None:
        if self._undo_action:
            self._undo_action.setEnabled(bool(self._undo_stack))
        if self._redo_action:
            self._redo_action.setEnabled(bool(self._redo_stack))

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        self._dirty = True
        self._redo_stack.append(self._record_snapshot())
        snap = self._undo_stack.pop()
        self._restore_records(snap)
        self._update_undo_actions()
        self._status_label.setText(tr("Undo: restored previous state"))

    def _redo(self) -> None:
        if not self._redo_stack:
            return
        self._dirty = True
        self._undo_stack.append(self._record_snapshot())
        snap = self._redo_stack.pop()
        self._restore_records(snap)
        self._update_undo_actions()
        self._status_label.setText(tr("Redo: restored next state"))

    def _focus_search(self) -> None:
        self._table_widget._search_input.setFocus()

    def closeEvent(self, event) -> None:
        try:
            if self._dirty and self._records:
                reply = QMessageBox.question(
                    self, tr("Save Session"),
                    tr("Save current session before closing?\n"
                       "Yes: save session file\n"
                       "No: discard all changes"),
                    QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                )
                if reply == QMessageBox.Cancel:
                    event.ignore()
                    return
                if reply == QMessageBox.Yes:
                    self._save_session()
                    cfg = self._config_mgr.config
                    cfg.lastSessionFile = self._session_file or ""
                    self._config_mgr.save()
                elif reply == QMessageBox.No:
                    self._repo.delete_all()
                    cfg = self._config_mgr.config
                    cfg.lastSessionFile = ""
                    self._config_mgr.save()

                self._clear_all()

            cfg = self._config_mgr.config
            geo = self.saveGeometry()
            cfg.geometry = bytes(geo).hex()
            self._config_mgr.save()
        except Exception:
            pass

        from database.pcb_info_repo import PcbInfoRepo
        try:
            PcbInfoRepo().clear()
        except RuntimeError:
            pass
        super().closeEvent(event)
