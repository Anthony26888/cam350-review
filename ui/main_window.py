import os
import json
import time
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QToolButton, QMessageBox, QFileDialog, QStatusBar,
    QLabel, QSplitter, QMenuBar, QMenu, QToolBar, QTabWidget,
    QApplication, QDialog, QProgressDialog, QStyle, QInputDialog,
)
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QSize, QPointF
from PySide6.QtGui import (
    QAction, QKeySequence, QIcon, QPixmap, QPainter, QColor, QPen,
    QPolygonF,
)

from config.config_manager import ConfigManager
from database.review_repo import ReviewRepo
from database.history_repo import HistoryRepo
from license.info import license_summary
from models.review import ReviewRecord
from models.pickplace import PickPlaceData, PickPlaceComponent, COLUMN_FIELDS
from services.pickplace_reader import PickPlaceReader, STANDARD_MAPPING
from services.bom_reader import BomReader
from services.bom_compare import compare as bom_compare_records, is_bottom_layer
from services.eco_diff import compare_revisions
from models.bom import BomRow
from services.cam350_controller import Cam350Controller
from services.export_service import ExportService
from services.datasheet_service import DatasheetService
from services.session_service import SessionService
from services.prescreen import dismiss_key_for, pack_prescreen_ctx, summarize, unpack_prescreen_ctx
from services.panelize_service import (
    PanelConfig, PanelError, is_panelized, panelize_records,
)
from utils.perf_log import Timer, log_event
from ui.table_widget import TableWidget
from ui.bom_table_widget import BomTableWidget
from ui.bom_dialogs import BomMappingDialog
from ui.eco_diff_dialog import EcoPickDialog, EcoResultDialog
from ui.review_panel import ReviewPanel
from ui.edit_dialog import EditDialog
from ui.batch_edit_dialog import BatchEditDialog
from ui.mapping_dialog import ColumnMappingDialog
from ui.settings_dialog import SettingsDialog
from ui.calibration_wizard import CalibrationWizard
from ui.origin_align_wizard import OriginAlignWizard, PrescreenCheckDialog
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


def _paint_icon_colored(draw, size: int = 26) -> QIcon:
    """Icons with accent colors: colorful when enabled, gray when disabled.

    The Disabled pixmap is re-rendered with a gray accent instead of
    desaturating pixels, so transparency is always preserved.
    `draw` receives (painter, size, accent) where accent is None for the
    colorful Normal state or a QColor for the monochrome Disabled state.
    """
    icon = QIcon()
    for mode, accent in (
        (QIcon.Mode.Normal, None),
        (QIcon.Mode.Disabled, QColor(_icon_stroke_disabled())),
    ):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(QPen(QColor(_icon_stroke() if accent is None else accent), 1.6))
        p.setBrush(Qt.NoBrush)
        draw(p, size, accent)
        p.end()
        icon.addPixmap(pm, mode)
    return icon


def _board_icon() -> QIcon:
    def _d(p, s, accent):
        color = QColor("#0EA5E9") if accent is None else accent
        p.drawRoundedRect(1.5, 1.5, s - 3, s - 3, 2.0, 2.0)
        p.setPen(QPen(color, 1.2))
        p.drawLine(s * 0.3, s * 0.42, s * 0.7, s * 0.42)
        p.drawLine(s * 0.5, s * 0.42, s * 0.5, s * 0.72)
        p.setBrush(color)
        p.setPen(Qt.NoPen)
        for x, y in ((s * 0.42, s * 0.36), (s * 0.58, s * 0.62)):
            p.drawRect(x, y, s * 0.15, s * 0.12)
    return _paint_icon_colored(_d)


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


def _sheet_icon() -> QIcon:
    """Open folder with a spreadsheet peeking out — the PickPlace Excel file."""
    def _d(p, s, accent):
        tab = QColor("#22C55E") if accent is None else accent
        base = p.pen().color()
        # spreadsheet peeking out of the folder
        p.drawRect(s * 0.30, 1.5, s * 0.44, s * 0.46)
        p.drawLine(s * 0.30, s * 0.26, s * 0.74, s * 0.26)
        p.drawLine(s * 0.52, s * 0.08, s * 0.52, s * 0.50)
        # green header strip = the Excel cue
        p.setBrush(tab)
        p.setPen(Qt.NoPen)
        p.drawRect(s * 0.32, s * 0.09, s * 0.40, s * 0.13)
        # open folder body
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(base, 1.6))
        p.drawRoundedRect(1.5, s * 0.42, s - 3, s * 0.50, 2.0, 2.0)
    return _paint_icon_colored(_d)


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


def _wrench_icon() -> QIcon:
    """Open-end wrench (diagonal) — Settings."""
    def _d(p, s):
        cx, cy, r = s * 0.64, s * 0.34, s * 0.21
        # open head: full ring, then clear a wedge facing upper-right
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setCompositionMode(QPainter.CompositionMode_Clear)
        p.setPen(Qt.NoPen)
        p.setBrush(Qt.SolidPattern)
        poly = QPolygonF([
            QPointF(cx, cy),
            QPointF(cx + r * 2.2, cy - r * 0.55),
            QPointF(cx + r * 0.55, cy - r * 2.2),
        ])
        p.drawPolygon(poly)
        p.setCompositionMode(QPainter.CompositionMode_SourceOver)
        # handle toward lower-left with round cap
        handle = QPen(p.pen().color(), 3.2)
        handle.setCapStyle(Qt.RoundCap)
        p.setPen(handle)
        p.drawLine(QPointF(cx - r * 0.4, cy + r * 0.4),
                   QPointF(s * 0.24, s * 0.76))
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


def _prescreen_icon() -> QIcon:
    """Magnifier with a green tick — distinct from the reload (Align) icon."""
    def _d(p, s, accent):
        # magnifier lens
        r = s * 0.30
        cx, cy = s * 0.40, s * 0.40
        lens = QColor("#0D9488") if accent is None else accent
        pen = QPen(lens, 1.8)
        p.setPen(pen)
        p.drawEllipse(QPointF(cx, cy), r, r)
        # handle
        p.drawLine(QPointF(cx + r * 0.72, cy + r * 0.72),
                   QPointF(s - 2.5, s - 2.5))
        # green tick inside the lens
        tick = QPen(QColor("#22C55E") if accent is None else accent, 1.9)
        tick.setCapStyle(Qt.RoundCap)
        tick.setJoinStyle(Qt.RoundJoin)
        p.setPen(tick)
        p.drawLine(QPointF(cx - r * 0.45, cy + r * 0.05),
                   QPointF(cx - r * 0.10, cy + r * 0.42))
        p.drawLine(QPointF(cx - r * 0.10, cy + r * 0.42),
                    QPointF(cx + r * 0.50, cy - r * 0.35))
    return _paint_icon_colored(_d)


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
        self._history_repo = HistoryRepo()
        self._cam350 = Cam350Controller()
        self._reader = PickPlaceReader()
        self._exporter = ExportService()

        self._records: List[ReviewRecord] = []
        self._pickplace_data: Optional[PickPlaceData] = None
        self._bom_rows: List[BomRow] = []
        self._bom_source_file: str = ""
        self._bom_diff = None
        self._gerber_viewer: Optional[QWidget] = None
        self._gerber_view_settings: Dict[str, Any] = {}
        self._current_index: int = -1
        self._session_service = SessionService()
        self._session_file: Optional[str] = None
        self._dirty = False
        self._jump_popup: Optional[JumpPopup] = None
        self._toolbar: Optional[QToolBar] = None
        self._prescreen_dismissed: set = set()
        self._pending_align_writes: List[ReviewRecord] = []
        self._prescreen_bundle: Optional[tuple] = None
        self._prescreen_ctx_packed: Optional[Dict[str, Any]] = None
        self._prescreen_dialog: Optional[PrescreenCheckDialog] = None

        self._undo_stack: List[List[Dict[str, Any]]] = []
        self._redo_stack: List[List[Dict[str, Any]]] = []
        self._undo_action: Optional[QAction] = None
        self._redo_action: Optional[QAction] = None
        self._datasheet_worker: Optional[DatasheetWorker] = None
        self._export_worker: Optional[ExportWorker] = None
        self._panel_config: Optional[PanelConfig] = None
        self._pre_panel_snapshot: Optional[List[Dict[str, Any]]] = None
        self._clear_panelize_action: Optional[QAction] = None
        self._eco_action: Optional[QAction] = None
        self._eco_dialog = None
        self._eco_diff = None

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
        new_action.setEnabled(False)
        self._new_action = new_action
        file_menu.addAction(new_action)

        open_session_action = QAction(tr("Open Session..."), self)
        open_session_action.setShortcut(QKeySequence("Ctrl+O"))
        open_session_action.triggered.connect(self._open_session)
        file_menu.addAction(open_session_action)

        save_action = QAction(tr("Save Session"), self)
        save_action.setShortcut(QKeySequence.Save)
        save_action.triggered.connect(self._save_session)
        save_action.setEnabled(False)
        self._save_action = save_action
        file_menu.addAction(save_action)

        save_as_action = QAction(tr("Save Session As..."), self)
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self._save_session_as)
        save_as_action.setEnabled(False)
        self._save_as_action = save_as_action
        file_menu.addAction(save_as_action)

        file_menu.addSeparator()

        open_pickplace_action = QAction(tr("Open PickPlace Excel..."), self)
        open_pickplace_action.setShortcut(QKeySequence("Ctrl+W"))
        open_pickplace_action.triggered.connect(self._open_file)
        file_menu.addAction(open_pickplace_action)

        open_pickplace_mapped_action = QAction(tr("Open PickPlace with Mapping..."), self)
        open_pickplace_mapped_action.triggered.connect(self._open_file_mapped)
        file_menu.addAction(open_pickplace_mapped_action)

        open_bom_action = QAction(tr("Open BOM Excel..."), self)
        open_bom_action.triggered.connect(self._open_bom)
        file_menu.addAction(open_bom_action)
        self._open_bom_action = open_bom_action

        export_menu = file_menu.addMenu(tr("&Export"))
        export_report_action = QAction(tr("Export Review Report"), self)
        export_report_action.triggered.connect(self._export_report)
        export_report_action.setEnabled(False)
        self._export_report_action = export_report_action
        export_menu.addAction(export_report_action)

        export_fixed_action = QAction(tr("Export PickPlace Fixed"), self)
        export_fixed_action.triggered.connect(self._export_fixed)
        export_fixed_action.setEnabled(False)
        self._export_fixed_action = export_fixed_action
        export_menu.addAction(export_fixed_action)

        export_bom_action = QAction(tr("Export BOM Fixed"), self)
        export_bom_action.triggered.connect(self._export_bom)
        export_bom_action.setEnabled(False)
        self._export_bom_action = export_bom_action
        export_menu.addAction(export_bom_action)

        export_top_action = QAction(tr("Export PickPlace Fixed Top"), self)
        export_top_action.triggered.connect(self._export_fixed_top)
        export_top_action.setEnabled(False)
        self._export_top_action = export_top_action
        export_menu.addAction(export_top_action)

        export_bottom_action = QAction(tr("Export PickPlace Fixed Bottom"), self)
        export_bottom_action.triggered.connect(self._export_fixed_bottom)
        export_bottom_action.setEnabled(False)
        self._export_bottom_action = export_bottom_action
        export_menu.addAction(export_bottom_action)

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
        align_action.setEnabled(False)
        self._align_action = align_action
        tools_menu.addAction(align_action)

        gerber_check_action = QAction(tr("Gerber View..."), self)
        gerber_check_action.triggered.connect(self._open_gerber_check)
        tools_menu.addAction(gerber_check_action)
        self._gerber_check_action = gerber_check_action

        panelize_action = QAction(tr("Panelize..."), self)
        panelize_action.triggered.connect(self._panelize)
        panelize_action.setEnabled(False)
        self._panelize_action = panelize_action
        tools_menu.addAction(panelize_action)

        clear_panelize_action = QAction(tr("Clear Panelize"), self)
        clear_panelize_action.triggered.connect(self._clear_panelize)
        clear_panelize_action.setEnabled(False)
        self._clear_panelize_action = clear_panelize_action
        tools_menu.addAction(clear_panelize_action)

        eco_action = QAction(tr("Compare Revisions (ECO)..."), self)
        eco_action.triggered.connect(self._compare_revisions)
        eco_action.setEnabled(False)
        self._eco_action = eco_action
        tools_menu.addAction(eco_action)

        tools_menu.addSeparator()

        pcb_info_action = QAction(tr("PCB Info..."), self)
        pcb_info_action.triggered.connect(self._open_pcb_info)
        pcb_info_action.setEnabled(False)
        self._pcb_info_action = pcb_info_action
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

        def _std_button(tip: str, label: str, icon_factory: Callable[[], QIcon]) -> QToolButton:
            btn = QToolButton()
            btn.setToolTip(tip)
            btn.setText(label)
            btn.setIcon(icon_factory())
            btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
            btn.setFixedSize(62, 56)
            btn.setStyleSheet("""
                QToolButton {
                    padding: 2px;
                    text-align: center;
                }
                QToolButton:disabled {
                    color: gray;
                }
            """)
            return btn

        spi = self.style().standardIcon
        icon_sources: List[tuple[QToolButton, Callable[[], QIcon]]] = []

        def _register(btn: QToolButton, factory: Callable[[], QIcon]) -> QToolButton:
            icon_sources.append((btn, factory))
            return btn

        btn_new = _register(
            _std_button(tr("New Session (Ctrl+N)"), tr("New"), lambda: spi(QStyle.StandardPixmap.SP_FileIcon)),
            lambda: spi(QStyle.StandardPixmap.SP_FileIcon),
        )
        btn_new.clicked.connect(self._new_session)
        btn_new.setEnabled(False)
        self._btn_new = btn_new

        btn_open_session = _register(
            _std_button(tr("Open Session (Ctrl+O)"), tr("Open"), lambda: spi(QStyle.StandardPixmap.SP_DialogOpenButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogOpenButton),
        )
        btn_open_session.clicked.connect(self._open_session)

        btn_save = _register(
            _std_button(tr("Save Session (Ctrl+S)"), tr("Save"), lambda: spi(QStyle.StandardPixmap.SP_DialogSaveButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogSaveButton),
        )
        btn_save.clicked.connect(self._save_session)
        btn_save.setEnabled(False)
        self._btn_save = btn_save

        self._btn_open = _register(_std_button(tr("Open PickPlace Excel (Ctrl+W)"), tr("Excel"), _sheet_icon), _sheet_icon)
        self._btn_open.clicked.connect(self._open_file)

        self._btn_bom = _register(_std_button(tr("Open BOM Excel"), tr("BOM"), _grid_icon), _grid_icon)
        self._btn_bom.clicked.connect(self._open_bom)

        self._btn_align = _register(
            _std_button(tr("Align PickPlace Origin"), tr("Align"), lambda: spi(QStyle.StandardPixmap.SP_BrowserReload)),
            lambda: spi(QStyle.StandardPixmap.SP_BrowserReload),
        )
        self._btn_align.clicked.connect(self._align_origin)
        self._btn_align.setEnabled(False)

        self._btn_run_check = _register(
            _std_button(tr("Run Check"), tr("Check"), _prescreen_icon),
            _prescreen_icon,
        )
        self._btn_run_check.setToolTip(tr("Re-run the pre-screen check on the current data"))
        self._btn_run_check.clicked.connect(self._open_prescreen_dialog)
        self._btn_run_check.setEnabled(False)

        self._btn_gerber_check = _register(_std_button(tr("Gerber View"), tr("Gerber"), _board_icon), _board_icon)
        self._btn_gerber_check.clicked.connect(self._open_gerber_check)
        self._btn_gerber_check.setEnabled(False)

        self._btn_export_report = _register(_std_button(tr("Export Review Report"), tr("Report"), _doc_icon), _doc_icon)
        self._btn_export_report.clicked.connect(self._export_report)
        self._btn_export_report.setEnabled(False)

        self._btn_export_fixed = _register(_std_button(tr("Export"), tr("Export"), _export_icon), _export_icon)
        self._btn_export_fixed.setEnabled(False)
        self._btn_export_fixed.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        _export_popup = QMenu(self._btn_export_fixed)
        _export_popup.addAction(self._export_fixed_action)
        _export_popup.addAction(self._export_bom_action)
        _export_popup.addSeparator()
        _export_popup.addAction(self._export_top_action)
        _export_popup.addAction(self._export_bottom_action)
        self._btn_export_fixed.setMenu(_export_popup)

        self._btn_batch_edit = _register(
            _std_button(tr("Batch Edit"), tr("Batch"), lambda: spi(QStyle.StandardPixmap.SP_FileDialogInfoView)),
            lambda: spi(QStyle.StandardPixmap.SP_FileDialogInfoView),
        )
        self._btn_batch_edit.clicked.connect(self._batch_edit)
        self._btn_batch_edit.setEnabled(False)

        self._btn_pcb_info = _register(_std_button(tr("PCB Info"), tr("PCB"), _chip_icon), _chip_icon)
        self._btn_pcb_info.clicked.connect(self._open_pcb_info)
        self._btn_pcb_info.setEnabled(False)

        self._btn_ok_checked = _register(
            _std_button(tr("OK Checked"), tr("OK"), lambda: spi(QStyle.StandardPixmap.SP_DialogApplyButton)),
            lambda: spi(QStyle.StandardPixmap.SP_DialogApplyButton),
        )
        self._btn_ok_checked.setObjectName("success")
        self._btn_ok_checked.setEnabled(False)
        self._btn_ok_checked.clicked.connect(self._mark_checked_ok)

        self._btn_delete = _register(
            _std_button(tr("Delete Selected"), tr("Delete"), lambda: spi(QStyle.StandardPixmap.SP_TrashIcon)),
            lambda: spi(QStyle.StandardPixmap.SP_TrashIcon),
        )
        self._btn_delete.setObjectName("danger")
        self._btn_delete.setEnabled(False)
        self._btn_delete.clicked.connect(self._delete_selected)

        self._btn_settings = _register(_std_button(tr("Settings"), tr("Settings"), _wrench_icon), _wrench_icon)
        self._btn_settings.clicked.connect(self._open_settings)

        self._toolbar_icon_sources = icon_sources

        toolbar.addWidget(btn_new)
        toolbar.addWidget(btn_open_session)
        toolbar.addWidget(btn_save)
        toolbar.addSeparator()
        toolbar.addWidget(self._btn_open)
        toolbar.addWidget(self._btn_bom)
        toolbar.addWidget(self._btn_align)
        toolbar.addWidget(self._btn_run_check)
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

        self._table_tabs = QTabWidget()
        self._table_widget = TableWidget()
        self._table_widget.record_selected.connect(self._on_record_selected)
        self._table_widget.jump_requested.connect(self._on_table_jump)
        self._table_widget.filter_changed.connect(self._on_filter_changed)
        self._table_widget.flag_dismiss_requested.connect(self._on_flag_dismiss)
        self._table_tabs.addTab(self._table_widget, tr("PickPlace"))

        self._bom_table = BomTableWidget()
        self._table_tabs.addTab(self._bom_table, tr("BOM"))
        self._table_tabs.setCurrentIndex(0)
        self._table_tabs.currentChanged.connect(self._on_table_tab_changed)
        self._bom_table.bom_row_selected.connect(self._on_bom_row_selected)

        self._review_panel = ReviewPanel()
        self._review_panel.set_record_list([])

        splitter.addWidget(self._table_tabs)
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

    def _close_gerber_viewer(self) -> None:
        viewer = getattr(self, "_gerber_viewer", None)
        if viewer is None:
            return
        try:
            viewer.close()
        except RuntimeError:
            pass
        self._gerber_viewer = None

    def _close_jump_popup(self) -> None:
        popup = getattr(self, "_jump_popup", None)
        if popup is None:
            return
        try:
            popup.close()
        except RuntimeError:
            pass
        self._jump_popup = None

    def _sync_after_mutation(self, focus_index: int = -1) -> None:
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        try:
            self._refresh_bom_compare()
        except AttributeError:
            pass
        self._update_progress()
        if self._records and 0 <= focus_index < len(self._records):
            self._select_and_display(focus_index)
            if self._jump_popup is not None and self._jump_popup.isVisible():
                self._jump_popup.show_at(self._records, focus_index)
            elif self._jump_popup is not None:
                self._jump_popup.set_records(self._records, focus_index)
        elif self._jump_popup is not None and self._jump_popup.isVisible():
            self._jump_popup.close()
        viewer = getattr(self, "_gerber_viewer", None)
        if viewer is not None:
            try:
                viewer.refresh_records(self._records)
            except RuntimeError:
                pass

    def _clear_all(self) -> None:
        self._dirty = False
        self._repo.delete_all()
        try:
            self._history_repo.clear_all()
        except Exception:
            pass
        self._records = []
        self._pickplace_data = None
        self._prescreen_dismissed = set()
        self._prescreen_bundle = None
        self._prescreen_ctx_packed = None
        self._close_prescreen_dialog()
        if hasattr(self, "_btn_run_check"):
            self._btn_run_check.setEnabled(False)
        self._close_gerber_viewer()
        self._close_jump_popup()
        self._current_index = -1
        self._session_file = None
        self._table_widget.set_records([])
        self._review_panel.set_record_list([])
        self._review_panel.clear_record()
        try:
            self._clear_bom()
        except AttributeError:
            pass
        self._btn_export_report.setEnabled(False)
        self._btn_export_fixed.setEnabled(False)
        self._btn_batch_edit.setEnabled(False)
        self._btn_ok_checked.setEnabled(False)
        self._btn_delete.setEnabled(False)
        self._btn_align.setEnabled(False)
        self._btn_pcb_info.setEnabled(False)
        self._btn_new.setEnabled(False)
        self._btn_save.setEnabled(False)
        self._clear_gerber_config()
        self._panel_config = None
        self._pre_panel_snapshot = None
        self._update_gerber_view_button()
        self._sync_action_states()
        self._update_progress()
        self._status_label.setText(tr("Ready"))
        from database.pcb_info_repo import PcbInfoRepo
        try:
            PcbInfoRepo().clear()
        except RuntimeError:
            pass

    def _clear_gerber_config(self) -> None:
        self._config_mgr.update(
            gerberFolder="", gerberLayers=[],
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

    def _sync_action_states(self) -> None:
        self._align_action.setEnabled(self._btn_align.isEnabled())
        self._export_report_action.setEnabled(self._btn_export_report.isEnabled())
        self._export_fixed_action.setEnabled(self._btn_export_fixed.isEnabled())
        for _attr in ("_export_top_action", "_export_bottom_action"):
            if getattr(self, _attr, None) is not None:
                getattr(self, _attr).setEnabled(self._btn_export_fixed.isEnabled())
        self._pcb_info_action.setEnabled(self._btn_pcb_info.isEnabled())
        self._new_action.setEnabled(self._btn_new.isEnabled())
        self._save_action.setEnabled(self._btn_save.isEnabled())
        self._save_as_action.setEnabled(self._btn_save.isEnabled())
        if getattr(self, "_export_bom_action", None) is not None:
            self._export_bom_action.setEnabled(
                bool(getattr(self, "_bom_rows", None))
            )
        if self._panelize_action is not None:
            self._panelize_action.setEnabled(self._btn_export_report.isEnabled())
        if self._clear_panelize_action is not None:
            self._clear_panelize_action.setEnabled(
                bool(self._panel_config) or self._pre_panel_snapshot is not None
            )
        if getattr(self, "_eco_action", None) is not None:
            self._eco_action.setEnabled(bool(self._records))

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
        from services.gerber.layer_scan import layer_from_file

        entries = list(getattr(session, "gerberLayers", []) or [])
        embedded = getattr(session, "gerber_files", None) or {}
        if embedded:
            entries = self._materialize_embedded_gerber(entries, embedded)
        kept = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path", "")
            if path and os.path.exists(path):
                kept.append(entry)
        folder = getattr(session, "gerberFolder", "") or ""
        if kept:
            self._config_mgr.update(gerberFolder=folder, gerberLayers=kept)
        else:
            self._config_mgr.update(gerberFolder="", gerberLayers=[])

    @staticmethod
    def _materialize_embedded_gerber(entries: List[Dict[str, Any]],
                                    embedded: Dict[str, str]) -> List[Dict[str, Any]]:
        from services.gerber.layer_scan import layer_from_file
        from services.session_service import decompress_text
        from utils.path_utils import user_data_dir

        tmp_dir = os.path.join(user_data_dir(), "tmp_gerber")
        try:
            os.makedirs(tmp_dir, exist_ok=True)
        except OSError:
            return entries
        for key, payload in embedded.items():
            if not payload:
                continue
            if any(entry.get("path") == key for entry in entries) \
                    and os.path.exists(key):
                continue
            try:
                text = decompress_text(payload)
            except Exception:
                continue
            try:
                target = os.path.join(tmp_dir, os.path.basename(key) or "layer.gbr")
                with open(target, "w", encoding="utf-8") as f:
                    f.write(text)
            except (IOError, OSError):
                continue
            layer = layer_from_file(target)
            if layer is None:
                continue
            entries.append({
                "path": target,
                "name": layer.name,
                "role": layer.role,
                "side": layer.side,
                "file_name": layer.file_name,
                "is_drill": layer.is_drill,
            })
        return entries

    def _existing_gerber_paths(self) -> Dict[str, str]:
        """The files of the last picture, by the name of their role."""
        out = {}
        for layer in self._existing_gerber_layers():
            out[layer.path] = layer.path
        return out

    def _existing_gerber_layers(self) -> List[Any]:
        """The layers of the last picture, as they were left."""
        from services.gerber.layer_scan import layer_from_file

        cfg = self._config_mgr.config
        layers = []
        for entry in list(getattr(cfg, "gerberLayers", []) or []):
            if not isinstance(entry, dict):
                continue
            path = entry.get("path", "")
            if not path or not os.path.exists(path):
                continue
            layer = layer_from_file(path)
            if layer is not None:
                layers.append(layer)
        if layers:
            return layers
        return self._migrate_gerber_layers()

    def _migrate_gerber_layers(self) -> List[Any]:
        """The layers of a setup that named its files by their role.

        The layers used to be picked one by one, by the role of the file.
        Such a setup is turned into the list of layers it stands for.
        """
        from services.gerber.layer_scan import layer_from_file

        cfg = self._config_mgr.config
        layers = []
        for key in ("gerberGko", "gerberGtp", "gerberGbp", "gerberGto",
                    "gerberGbo", "gerberDrill"):
            path = getattr(cfg, key, "")
            if not path or not os.path.exists(path):
                continue
            layer = layer_from_file(path)
            if layer is not None:
                layers.append(layer)
        return layers

    def _gerber_path_of_role(self, role: str, side: str = "") -> str:
        """The file of the first layer of a role."""
        for layer in self._existing_gerber_layers():
            if layer.role != role:
                continue
            if side and layer.side and layer.side != side:
                continue
            return layer.path
        return ""

    def _existing_gerber_folder(self) -> str:
        """The folder the files of the last picture were taken from."""
        cfg = self._config_mgr.config
        folder = getattr(cfg, "gerberFolder", "") or ""
        if folder and os.path.isdir(folder):
            return folder
        layers = self._existing_gerber_layers()
        if layers:
            return os.path.dirname(layers[0].path)
        return ""

    @staticmethod
    def _layer_entries(layers) -> List[Dict[str, Any]]:
        """The layers, as they are remembered."""
        return [{
            "path": layer.path,
            "name": layer.name,
            "role": layer.role,
            "side": layer.side,
            "file_name": layer.file_name,
            "is_drill": layer.is_drill,
        } for layer in layers]

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
        for r in records:
            comp = PickPlaceComponent(
                designator=r.designator,
                mpn=r.mpn,
                layer=r.layer,
                x=r.old_x,
                y=r.old_y,
                rotation=r.old_rotation,
                row=r.row_index,
                panel_instance=r.block if r.block else None,
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
            session = self._run_with_busy_dialog(
                tr("Reading session..."),
                lambda: self._session_service.load(file_path))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, tr("Error"), tr("Failed to load session: {e}", e=str(e)))
            return

        if not session.records:
            QMessageBox.warning(self, tr("Warning"), tr("Session file is empty."))
            return

        records = self._session_service.list_to_records(session.records)

        self._run_with_busy_dialog(
            tr("Opening session..."),
            lambda: self._restore_session(session, records, file_path))

    def _restore_session(self, session, records, file_path) -> None:
        self._clear_all()

        self._repo.delete_all()
        for r in records:
            r.id = self._repo.insert(r)

        self._records = self._repo.get_all()
        self._records = [r for r in self._records if r.status != "Deleted"]
        self._session_file = file_path
        self._restore_history(getattr(session, "history", None))
        self._restore_bom(getattr(session, "bom_rows", None),
                          getattr(session, "bom_source_file", ""))
        self._pickplace_data = None
        self._restore_pcb_info(session)
        self._restore_session_gerber(session)
        self._gerber_view_settings = dict(session.gerber_view or {})
        self._prescreen_dismissed = set(getattr(session, "prescreen_dismissed", None) or ())
        self._close_prescreen_dialog()
        self._restore_prescreen_bundle(session)
        raw_panel = getattr(session, "panel_config", None)
        self._panel_config = PanelConfig.from_dict(raw_panel) if raw_panel else None
        self._pre_panel_snapshot = None

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
        self._btn_pcb_info.setEnabled(True)
        self._btn_new.setEnabled(True)
        self._btn_save.setEnabled(True)
        if hasattr(self, "_btn_run_check"):
            self._btn_run_check.setEnabled(True)
        self._update_gerber_view_button()
        self._sync_action_states()

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
        gerber = self._existing_gerber_layers()
        gerber_files = self._collect_gerber_files(
            {layer.path: layer.path for layer in gerber})
        self._session_service.save(
            file_path, self._records + deleted_records,
            source_file=source_file,
            current_index=max(self._current_index, 0),
            pcb_info=self._current_pcb_info_dict(),
            gerberFolder=self._existing_gerber_folder(),
            gerberLayers=self._layer_entries(gerber),
            gerber_view=self._current_gerber_view_settings(),
            column_mapping=self._pickplace_data.column_mapping if self._pickplace_data else None,
            gerber_files=gerber_files,
            prescreen_dismissed=sorted(self._prescreen_dismissed),
            prescreen_ctx=self._prescreen_ctx_packed,
            panel_config=self._panel_config.to_dict() if self._panel_config else None,
            history=self._collect_history_dicts(),
            bom_rows=self._collect_bom_dicts(),
            bom_source_file=getattr(self, "_bom_source_file", "") or "",
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
            gerber = self._existing_gerber_layers()
            gerber_files = self._collect_gerber_files(
                {layer.path: layer.path for layer in gerber})
            self._session_service.save(
                self._session_file, self._records + deleted_records,
                source_file=source_file,
                current_index=max(self._current_index, 0),
                pcb_info=self._current_pcb_info_dict(),
            gerberFolder=self._existing_gerber_folder(),
            gerberLayers=self._layer_entries(gerber),
                gerber_view=self._current_gerber_view_settings(),
                column_mapping=self._pickplace_data.column_mapping if self._pickplace_data else None,
                gerber_files=gerber_files,
                prescreen_dismissed=sorted(self._prescreen_dismissed),
                prescreen_ctx=self._prescreen_ctx_packed,
                panel_config=self._panel_config.to_dict() if self._panel_config else None,
                history=self._collect_history_dicts(),
                bom_rows=self._collect_bom_dicts(),
                bom_source_file=getattr(self, "_bom_source_file", "") or "",
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
            headers = self._run_with_busy_dialog(
                tr("Reading file headers..."),
                lambda: self._reader.read_headers(file_path))
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
                data = self._run_with_busy_dialog(
                    tr("Opening PickPlace..."),
                    lambda: self._reader.read_with_mapping(
                        file_path, mapping, required=required))
            else:
                data = self._run_with_busy_dialog(
                    tr("Opening PickPlace..."),
                    lambda: self._reader.read(file_path))
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return

        self._run_with_busy_dialog(
            tr("Loading components..."),
            lambda: self._apply_loaded_pickplace(data, file_path))

    def _apply_loaded_pickplace(self, data: PickPlaceData, file_path: str) -> None:
        self._pickplace_data = data
        self._config_mgr.update(lastFile=file_path)
        self._clear_gerber_config()
        self._panel_config = None
        self._pre_panel_snapshot = None

        self._repo.delete_all()
        try:
            self._history_repo.clear_all()
        except Exception:
            pass
        self._records = []
        import_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            try:
                from models.history import HistoryEntry
                self._history_repo.add(HistoryEntry(
                    designator=record.designator, block=0, action="Import",
                    old_x=None, old_y=None, old_rotation=None,
                    new_x=record.old_x, new_y=record.old_y,
                    new_rotation=record.old_rotation,
                    remark="", created_at=import_ts,
                ))
            except Exception:
                pass

        self._dirty = True
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._btn_export_report.setEnabled(True)
        self._btn_export_fixed.setEnabled(True)
        self._btn_batch_edit.setEnabled(True)
        self._btn_ok_checked.setEnabled(True)
        self._btn_delete.setEnabled(True)
        self._btn_align.setEnabled(True)
        self._btn_pcb_info.setEnabled(True)
        self._btn_new.setEnabled(True)
        self._btn_save.setEnabled(True)
        if hasattr(self, "_btn_run_check"):
            self._btn_run_check.setEnabled(True)
        self._update_gerber_view_button()
        self._sync_action_states()

        if self._records:
            self._select_and_display(0)

        self._update_progress()
        self._status_label.setText(
            tr("Loaded {count} components from {name}",
               count=len(data.components), name=os.path.basename(file_path))
        )
        # Keep an already-loaded BOM and re-compare it against the new
        # records (BOM-first workflow), auto-filling empty MPN values.
        # BOM is only cleared on New Session, session load without BOM,
        # or opening another BOM file.
        try:
            self._refresh_bom_compare()
            filled = self._auto_fill_mpn(silent=True)
            msg = tr("Loaded {count} components from {name}",
                     count=len(data.components),
                     name=os.path.basename(file_path))
            if filled:
                msg = (f"{msg} — "
                       f"{tr('Auto-filled MPN for {n} records', n=filled)}")
            self._status_label.setText(msg)
        except AttributeError:
            pass

    # -- BOM ------------------------------------------------------------
    def _open_bom(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, tr("Open BOM Excel"), "", "Excel Files (*.xlsx)"
        )
        if not file_path:
            return
        try:
            headers = self._run_with_busy_dialog(
                tr("Reading file headers..."),
                lambda: BomReader.read_headers(file_path))
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        dialog = BomMappingDialog(file_path, headers, parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            rows = self._run_with_busy_dialog(
                tr("Opening BOM..."),
                lambda: BomReader.read_with_mapping(
                    file_path, dialog.column_mapping))
        except (ValueError, FileNotFoundError) as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self._run_with_busy_dialog(
            tr("Loading BOM..."),
            lambda: self._apply_bom_rows(rows, file_path))

    def _apply_bom_rows(self, rows: List[BomRow], source_file: str) -> None:
        self._bom_rows = list(rows)
        self._bom_source_file = source_file or ""
        self._dirty = True
        self._refresh_bom_compare()
        self._sync_action_states()
        filled = self._auto_fill_mpn(silent=True)
        msg = tr(
            "Loaded {count} BOM rows from {name}",
            count=len(rows), name=os.path.basename(source_file))
        if filled:
            msg = f"{msg} — {tr('Auto-filled MPN for {n} records', n=filled)}"
        self._status_label.setText(msg)

    def _clear_bom(self) -> None:
        self._bom_rows = []
        self._bom_source_file = ""
        self._bom_diff = None
        try:
            self._bom_table.clear()
        except (AttributeError, RuntimeError):
            pass
        try:
            self._table_widget.clear_bom_overlay()
        except (AttributeError, RuntimeError):
            pass
        self._update_bom_tab_texts(0)
        self._sync_action_states()

    def _pickplace_tuples(self) -> List[tuple]:
        return [(r.designator, r.mpn, r.layer) for r in self._records]

    def _refresh_bom_compare(self) -> None:
        bom_rows = getattr(self, "_bom_rows", None) or []
        records = getattr(self, "_records", None) or []
        table = getattr(self, "_table_widget", None)
        bom_table = getattr(self, "_bom_table", None)
        if not bom_rows:
            self._bom_diff = None
            if table is not None and hasattr(table, "clear_bom_overlay"):
                try:
                    table.clear_bom_overlay()
                except (AttributeError, RuntimeError):
                    pass
            self._update_bom_tab_texts(0)
            return
        try:
            diff = bom_compare_records(
                bom_rows,
                [(r.designator, r.mpn, r.layer) for r in records],
            )
        except Exception:
            return
        self._bom_diff = diff
        if table is not None and hasattr(table, "set_bom_overlay"):
            mismatch = {k: (p, b, s) for k, p, b, s in diff.mpn_mismatch}
            try:
                table.set_bom_overlay({e for e in diff.extra}, mismatch)
            except (AttributeError, RuntimeError, TypeError):
                pass
        if bom_table is not None and hasattr(bom_table, "set_bom_rows"):
            try:
                bom_table.set_bom_rows(bom_rows)
                bottom = {
                    (r.designator or "").strip().upper() for r in records
                    if is_bottom_layer(r.layer)
                }
                missing = {row.stt: miss for row, miss in diff.missing}
                qty_warn = {row.stt for row, _n in diff.qty_notes}
                bom_table.set_compare(missing, bottom, qty_warn)
            except (AttributeError, RuntimeError):
                pass
        self._update_bom_tab_texts(len(diff.extra))

    def _update_bom_tab_texts(self, extra_count: int) -> None:
        tabs = getattr(self, "_table_tabs", None)
        if tabs is None:
            return
        try:
            if extra_count > 0:
                tabs.setTabText(0, tr("PickPlace (Extra: {n})", n=extra_count))
            else:
                tabs.setTabText(0, tr("PickPlace"))
            bom_rows = getattr(self, "_bom_rows", None) or []
            if bom_rows:
                tabs.setTabText(1, tr("BOM ({n})", n=len(bom_rows)))
            else:
                tabs.setTabText(1, tr("BOM"))
        except (AttributeError, RuntimeError):
            pass

    def _auto_fill_mpn(self, fillable: Optional[List[tuple]] = None,
                       silent: bool = False) -> int:
        """Fill empty PickPlace MPN values from the BOM (no prompt)."""
        diff = getattr(self, "_bom_diff", None)
        if fillable is None:
            if diff is None:
                return 0
            fillable = diff.mpn_fillable
        if not fillable:
            return 0
        want = {key: (mpn, stt) for key, mpn, stt in fillable}
        targets = []
        for idx, record in enumerate(self._records):
            for cand in (record.base_designator, record.designator):
                key = (cand or "").strip().upper()
                if key and key in want and not (record.mpn or "").strip():
                    targets.append(idx)
                    break
        if not targets:
            return 0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._push_undo()
        for idx in targets:
            record = self._records[idx]
            mpn = ""
            for cand in (record.base_designator, record.designator):
                key = (cand or "").strip().upper()
                if key and key in want:
                    mpn, _stt = want[key]
                    break
            record.mpn = mpn
            record.review_time = record.review_time or timestamp
            self._repo.update(record)
            self._log_history(record, "BOM", mpn_old="", mpn_new=mpn,
                              created_at=timestamp)
            try:
                self._table_widget.update_record_row(idx)
            except (AttributeError, RuntimeError):
                pass
        self._dirty = True
        self._refresh_bom_compare()
        self._update_progress()
        if not silent:
            conflicts = len(getattr(diff, "conflicts", None) or []) if diff else 0
            msg = tr("Auto-filled MPN for {n} records", n=len(targets))
            if conflicts:
                msg = f"{msg} ({tr('{k} conflicts ignored, first row wins', k=conflicts)})"
            self._status_label.setText(msg)
        return len(targets)

    def _collect_bom_dicts(self) -> List[Dict[str, Any]]:
        try:
            return [r.to_dict() for r in (getattr(self, "_bom_rows", None) or [])]
        except Exception:
            return []

    def _restore_bom(self, raw, source_file: str = "") -> None:
        rows: List[BomRow] = []
        for item in raw or []:
            if isinstance(item, dict):
                try:
                    rows.append(BomRow.from_dict(item))
                except Exception:
                    continue
        self._bom_rows = rows
        self._bom_source_file = source_file or ""
        self._bom_diff = None
        self._refresh_bom_compare()

    def _select_and_display(self, index: int, progress_text: str = "") -> None:
        if not self._records or index < 0 or index >= len(self._records):
            return
        self._current_index = index
        record = self._records[index]
        self._table_widget.select_record(index)
        self._review_panel.display_record(record, index, len(self._records), progress_text)
        self._refresh_history_panel(record)

    def _on_table_tab_changed(self, index: int) -> None:
        # Fit BOM row heights when its tab becomes visible: measuring while
        # hidden produces oversized rows.
        try:
            if index == self._table_tabs.indexOf(self._bom_table):
                self._bom_table.refit_rows()
        except (AttributeError, RuntimeError):
            pass

    def _on_bom_row_selected(self, stt: int) -> None:
        rows = getattr(self, "_bom_rows", None) or []
        row = next((r for r in rows if r.stt == stt), None)
        if row is None:
            return
        layers_of: Dict[str, set] = {}
        keys: set = set()
        for r in getattr(self, "_records", None) or []:
            for cand in (r.designator, r.base_designator):
                key = (cand or "").strip().upper()
                if not key:
                    continue
                keys.add(key)
                layers_of.setdefault(key, set()).add(r.layer or "")
        try:
            from services.bom_compare import summarize_bom_row
            summary = summarize_bom_row(row, layers_of, keys)
            self._review_panel.display_bom_summary(summary)
        except (AttributeError, RuntimeError):
            return
        matched = [d for d in row.designators
                   if (d or "").strip().upper() in keys]
        entries = []
        repo = getattr(self, "_history_repo", None)
        if repo is not None:
            try:
                seen_rows: set = set()
                for r in getattr(self, "_records", None) or []:
                    for cand in (r.designator, r.base_designator):
                        key = (cand or "").strip().upper()
                        if key and key in {m.strip().upper() for m in matched}:
                            tag = (r.designator, int(getattr(r, "block", 0) or 0))
                            if tag not in seen_rows:
                                seen_rows.add(tag)
                                entries.extend(
                                    repo.list_by(tag[0], tag[1], limit=100))
                            break
            except (AttributeError, RuntimeError):
                entries = []
        entries = sorted(entries,
                         key=lambda e: getattr(e, "id", 0),
                         reverse=True)[:20]
        try:
            self._review_panel.set_history_title(
                tr("BOM Row {stt} — {n} records", stt=stt, n=len(matched)))
            self._review_panel.reload_history(entries)
        except (AttributeError, RuntimeError):
            pass

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
        old_x = record.new_x if record.new_x is not None else record.old_x
        old_y = record.new_y if record.new_y is not None else record.old_y
        old_rot = record.new_rotation if record.new_rotation is not None else record.old_rotation
        self._push_undo()
        record.new_x = new_x
        record.new_y = new_y
        record.new_rotation = new_rot
        record.remark = remark
        record.status = "Edited"
        record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._repo.update(record)
        self._log_history(record, "Edit", old_x=old_x, old_y=old_y, old_rot=old_rot)
        self._table_widget.update_record_row(index)
        if index == self._current_index:
            self._refresh_history_panel(record)
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
        box = QMessageBox(self)
        box.setWindowTitle(tr("Delete Record"))
        box.setText(tr("Delete {des}?", des=record.designator))
        box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        box.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        reply = box.exec()
        if reply != QMessageBox.Yes:
            return
        self._push_undo()
        self._log_history(record, "Delete", old_x=record.new_x, old_y=record.new_y,
                           old_rot=record.new_rotation, remark=record.remark or "")
        self._repo.delete_by_id(record.id)
        self._records.pop(index)
        if not self._records:
            self._clear_all()
            return
        self._sync_after_mutation(min(index, len(self._records) - 1))
        self._status_label.setText(tr("Deleted {des}", des=record.designator))

    def _jump_cam350(self) -> None:
        self._show_jump_popup()
        self._popup_jump(self._current_index)

    def _mark_ok(self) -> None:
        if self._current_index < 0 or self._current_index >= len(self._records):
            return
        record = self._records[self._current_index]
        old_x = record.new_x
        old_y = record.new_y
        old_rot = record.new_rotation
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
        self._log_history(record, "OK", old_x=old_x, old_y=old_y, old_rot=old_rot)
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
        old_x = record.new_x
        old_y = record.new_y
        old_rot = record.new_rotation
        old_remark = record.remark
        before = self._record_snapshot()
        dialog = EditDialog(record, self)
        if dialog.exec():
            self._push_undo(before)
            record.status = "Edited"
            record.review_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._repo.update(record)
            # EditDialog already wrote new_x/new_y/rot/remark into record
            self._log_history(record, "Edit", old_x=old_x, old_y=old_y,
                              old_rot=old_rot, remark=old_remark)
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

    def _export_fixed_top(self) -> None:
        self._export_fixed_layer("top")

    def _export_fixed_bottom(self) -> None:
        self._export_fixed_layer("bottom")

    def _export_fixed_layer(self, layer: str) -> None:
        if not self._records or self._pickplace_data is None:
            QMessageBox.warning(self, tr("Warning"), tr("No data to export. Load a file first."))
            return
        from services.bom_compare import is_bottom_layer
        want_bottom = layer == "bottom"
        if not any(is_bottom_layer(r.layer) == want_bottom for r in self._records):
            QMessageBox.warning(
                self, tr("Warning"),
                tr("No Bottom data to export.") if want_bottom
                else tr("No Top data to export."))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        suffix = "Top" if not want_bottom else "Bottom"
        default_name = f"PickPlace_Fixed_{suffix}_{timestamp}.csv"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export PickPlace Fixed {suffix}", suffix=suffix), default_name,
            "CSV Files (*.csv);;All Files (*.*)"
        )
        if not file_path:
            return
        self._set_exporting(True)
        from database.pcb_info_repo import PcbInfoRepo
        pcb_info = PcbInfoRepo().load()
        worker = ExportWorker(
            self._exporter.export_pickplace_fixed_by_layer,
            (list(self._records), self._pickplace_data, file_path,
             layer, pcb_info), self
        )
        worker.finished_ok.connect(self._on_export_done)
        worker.finished_err.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _export_bom(self) -> None:
        bom_rows = getattr(self, "_bom_rows", None) or []
        if not bom_rows:
            QMessageBox.warning(self, tr("Warning"), tr("No BOM data to export."))
            return
        title, accepted = QInputDialog.getText(
            self, tr("Export BOM Fixed"), tr("Enter report title:"))
        if not accepted:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"BOM_Fixed_{timestamp}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export BOM Fixed"), default_name,
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
        diff = getattr(self, "_bom_diff", None)
        missing = ({row.stt: miss for row, miss in diff.missing}
                   if diff is not None else {})
        bottom = set()
        for r in getattr(self, "_records", None) or []:
            if is_bottom_layer(r.layer):
                bottom.add((r.designator or "").strip().upper())
        self._set_exporting(True)
        worker = ExportWorker(
            self._exporter.export_bom_fixed,
            (list(bom_rows), file_path, missing, bottom, title.strip()), self
        )
        worker.finished_ok.connect(self._on_export_done)
        worker.finished_err.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _set_exporting(self, exporting: bool) -> None:
        self._btn_export_report.setEnabled(not exporting)
        self._btn_export_fixed.setEnabled(not exporting)
        if getattr(self, "_export_bom_action", None) is not None:
            has_bom = bool(getattr(self, "_bom_rows", None))
            self._export_bom_action.setEnabled(not exporting and has_bom)
        self._sync_action_states()
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
            old_x, old_y, old_rot = record.new_x, record.new_y, record.new_rotation
            old_remark = record.remark
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
            self._log_history(record, "Batch", old_x=old_x, old_y=old_y,
                              old_rot=old_rot, remark=old_remark,
                              created_at=timestamp)
            self._table_widget.update_record_row(idx)
            progress.setValue(count)
            QApplication.processEvents()
        progress.close()
        self._update_progress()
        self._status_label.setText(tr("Batch edited {n} records", n=len(indices)))
        self._refresh_history_panel()

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
            old_x, old_y, old_rot = record.new_x, record.new_y, record.new_rotation
            record.status = "OK"
            if record.new_x is None:
                record.new_x = record.old_x
            if record.new_y is None:
                record.new_y = record.old_y
            if record.new_rotation is None:
                record.new_rotation = record.old_rotation
            record.review_time = timestamp
            self._repo.update(record)
            self._log_history(record, "OK", old_x=old_x, old_y=old_y,
                              old_rot=old_rot, created_at=timestamp)
            self._table_widget.update_record_row(idx)
            progress.setValue(count)
            QApplication.processEvents()
        progress.close()
        self._table_widget.clear_checked()
        self._update_progress()
        self._status_label.setText(tr("Marked OK: {n} records", n=len(indices)))
        self._refresh_history_panel()

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
            self._log_history(record, "Delete", old_x=record.new_x,
                              old_y=record.new_y, old_rot=record.new_rotation)
            self._records.pop(idx)
        self._table_widget.clear_checked()
        if not self._records:
            self._sync_after_mutation(-1)
            self._session_file = None
            self._btn_export_report.setEnabled(True)
            self._btn_export_fixed.setEnabled(False)
            self._btn_batch_edit.setEnabled(False)
            self._btn_ok_checked.setEnabled(False)
            self._btn_delete.setEnabled(False)
            self._btn_align.setEnabled(False)
            self._btn_pcb_info.setEnabled(False)
            self._btn_new.setEnabled(False)
            self._btn_save.setEnabled(False)
            self._update_gerber_view_button()
            self._sync_action_states()
            self._status_label.setText(tr("All records deleted"))
        else:
            new_index = min(self._current_index, len(self._records) - 1)
            self._sync_after_mutation(new_index)
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

        try:
            from utils._build_info import BUILD_TIME, GIT_HASH
            version_label = f"{APP_VERSION} <span style='color:#888;'>(build {BUILD_TIME}"
            if GIT_HASH:
                version_label += f" · {GIT_HASH}"
            version_label += ")</span>"
        except Exception:
            version_label = APP_VERSION

        info = QLabel(
            "<p><b>Version:</b> " + version_label + "</p>"
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
        bom_rows = list(getattr(self, "_bom_rows", None) or [])
        bom_source_file = getattr(self, "_bom_source_file", "") or ""

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
        self._bom_rows = bom_rows
        self._bom_source_file = bom_source_file
        self._bom_diff = None

        has_records = bool(records)
        self._btn_export_report.setEnabled(has_records)
        self._btn_export_fixed.setEnabled(has_records)
        self._btn_batch_edit.setEnabled(has_records)
        self._btn_ok_checked.setEnabled(has_records)
        self._btn_delete.setEnabled(has_records)
        self._btn_align.setEnabled(has_records)
        self._btn_pcb_info.setEnabled(has_records)
        self._btn_new.setEnabled(has_records)
        self._btn_save.setEnabled(has_records)
        self._undo_action.setEnabled(bool(undo_stack))
        self._redo_action.setEnabled(bool(redo_stack))
        self._update_gerber_view_button()
        self._sync_action_states()

        self._table_widget.set_records(records)
        self._review_panel.set_record_list(records)
        if 0 <= current_index < len(records):
            self._review_panel.display_record(
                records[current_index], current_index, len(records)
            )
            self._refresh_history_panel(records[current_index])
        else:
            self._review_panel.clear_record()
        self._refresh_bom_compare()
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
            self._pickplace_data, self._records, self._apply_align_record, self,
            dismissed=self._prescreen_dismissed,
            flush_cb=self._flush_align_writes,
        )
        wizard.exec()

        def _post_wizard() -> None:
            total_t = Timer()
            t = Timer()
            # Capture align context so the toolbar Run Check can re-run later
            gko, gtp, gbp, ctx = wizard.get_prescreen_context()
            if ctx is not None:
                self._prescreen_bundle = (gko, gtp, gbp, ctx)
                self._prescreen_ctx_packed = pack_prescreen_ctx(ctx)
                if hasattr(self, "_btn_run_check"):
                    self._btn_run_check.setEnabled(True)
            self._apply_prescreen_result(wizard.get_prescreen_result())
            prescreen_ms = t.ms()

            t = Timer()
            self._update_progress()
            progress_ms = t.ms()

            t = Timer()
            self._update_gerber_view_button()
            gerber_btn_ms = t.ms()

            t = Timer()
            self._review_panel.set_record_list(self._records)
            if self._current_index >= 0 and self._current_index < len(self._records):
                self._review_panel.display_record(
                    self._records[self._current_index],
                    self._current_index, len(self._records),
                )
            panel_ms = t.ms()

            log_event(
                "align_finish",
                total_ms=total_t.ms(),
                prescreen_apply_ms=prescreen_ms,
                progress_ms=progress_ms,
                gerber_btn_ms=gerber_btn_ms,
                panel_ms=panel_ms,
                rows=len(self._records),
            )

        QTimer.singleShot(0, lambda: self._run_with_busy_dialog(
            tr("Updating component table..."),
            _post_wizard,
        ))

    def _panelize(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Panelize"), tr("No data to panelize."))
            return
        if is_panelized(self._records):
            QMessageBox.warning(
                self, tr("Panelize"),
                tr("Dữ liệu đã được panelize. Hãy xóa panelize trước "
                   "(Tools > Clear Panelize)."),
            )
            return

        from ui.panelize_dialog import PanelizeDialog

        gko = self._gerber_path_of_role("profile")
        dialog = PanelizeDialog(
            self._records, parent=self,
            config=self._panel_config, gko_path=gko,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        cfg = dialog.panel_config
        if cfg is None:
            return

        try:
            new_records = panelize_records(self._records, cfg)
        except PanelError as e:
            QMessageBox.critical(self, tr("Panelize"), str(e))
            return

        self._pre_panel_snapshot = self._record_snapshot()
        self._push_undo()
        snap = SessionService.records_to_list(new_records)
        self._restore_records(snap)
        self._panel_config = cfg
        self._dirty = True
        self._sync_action_states()
        self._status_label.setText(
            tr("Panelized: {boards} boards × {parts} components = {total} records",
               boards=cfg.count, parts=len(self._records) // max(cfg.count, 1),
               total=len(self._records))
        )

    def _clear_panelize(self) -> None:
        if self._pre_panel_snapshot is not None:
            self._push_undo()
            self._restore_records(list(self._pre_panel_snapshot))
        else:
            base = [r for r in self._records if getattr(r, "block", 0) == 0]
            if not base or len(base) == len(self._records):
                return
            self._push_undo()
            snap = SessionService.records_to_list(base)
            self._restore_records(snap)
        self._panel_config = None
        self._pre_panel_snapshot = None
        self._dirty = True
        self._sync_action_states()
        self._status_label.setText(tr("Panelize cleared"))

    def _compare_revisions(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Warning"), tr("No data to compare."))
            return
        cfg = self._config_mgr.config
        source = ""
        if self._session_file:
            source = os.path.basename(self._session_file)
        elif self._pickplace_data is not None:
            source = os.path.basename(
                getattr(self._pickplace_data, "file_path", ""))
        dialog = EcoPickDialog(
            len(self._records), source or tr("current session"),
            float(getattr(cfg, "ecoMoveTol", 0.01) or 0.01),
            float(getattr(cfg, "ecoRotTol", 1.0) or 1.0),
            parent=self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        data = dialog.data
        if data is None:
            return
        move_tol, rot_tol = dialog.tolerances
        self._config_mgr.update(ecoMoveTol=move_tol, ecoRotTol=rot_tol)
        try:
            diff = self._run_with_busy_dialog(
                tr("Comparing revisions..."),
                lambda: compare_revisions(self._records, data.components,
                                          move_tol, rot_tol))
        except Exception as e:
            QMessageBox.critical(self, tr("Error"), str(e))
            return
        self._eco_diff = diff
        self._eco_new_count = len(data.components)
        if diff.is_empty:
            QMessageBox.information(
                self, tr("Compare Revisions (ECO)"),
                tr("No differences found."))
            return
        self._open_eco_result_dialog()

    def _open_eco_result_dialog(self) -> None:
        diff = getattr(self, "_eco_diff", None)
        if diff is None:
            return
        dlg = getattr(self, "_eco_dialog", None)
        if dlg is not None:
            try:
                if dlg.isVisible():
                    dlg.raise_()
                    dlg.activateWindow()
                    return
            except RuntimeError:
                pass
            self._eco_dialog = None
        dlg = EcoResultDialog(diff, len(self._records),
                              int(getattr(self, "_eco_new_count", 0) or 0),
                              parent=self)
        dlg.locate_requested.connect(self._on_eco_locate)
        dlg.export_requested.connect(self._export_eco_report)
        dlg.apply_requested.connect(self._confirm_apply_eco)
        dlg.finished.connect(self._on_eco_dialog_closed)
        self._eco_dialog = dlg
        dlg.show()

    def _on_eco_dialog_closed(self, *_args) -> None:
        self._eco_dialog = None

    def _on_eco_locate(self, designator: str) -> None:
        key = (designator or "").strip().upper()
        for i, r in enumerate(self._records):
            if (r.designator or "").strip().upper() == key \
                    and not getattr(r, "block", 0):
                self._select_and_display(i)
                viewer = getattr(self, "_gerber_viewer", None)
                if viewer is not None:
                    try:
                        viewer.set_selected(i)
                    except (RuntimeError, AttributeError):
                        pass
                return

    def _confirm_apply_eco(self) -> None:
        from PySide6.QtWidgets import QCheckBox
        diff = getattr(self, "_eco_diff", None)
        if diff is None or diff.is_empty:
            return
        a, r, m, p = diff.counts
        box = QMessageBox(self)
        box.setWindowTitle(tr("Apply ECO to current session"))
        box.setText(tr("+{a} new records (Pending)\n"
                       "−{r} kept with remark \"ECO removed\"\n"
                       "~{m} coordinates updated, back to Pending\n"
                       "⇄{p} MPN updated", a=a, r=r, m=m, p=p))
        export_check = QCheckBox(tr("Export ECO report (.xlsx) after applying"))
        box.setCheckBox(export_check)
        box.setStandardButtons(QMessageBox.Ok | QMessageBox.Cancel)
        if box.exec() != QMessageBox.Ok:
            return
        self._apply_eco_diff(diff)
        if export_check.isChecked():
            self._export_eco_report()

    def _apply_eco_diff(self, diff) -> int:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._push_undo()
        changed = 0
        by_des = {}
        for r in self._records:
            if getattr(r, "block", 0):
                continue
            by_des.setdefault((r.designator or "").strip().upper(), r)
        for item in diff.added:
            record = ReviewRecord(
                designator=item.designator, mpn=item.mpn, layer=item.layer,
                old_x=item.x, old_y=item.y, old_rotation=item.rotation,
                status="Pending", row_index=len(self._records),
            )
            record.id = self._repo.insert(record)
            self._records.append(record)
            self._log_history(record, "Import",
                              created_at=timestamp)
            changed += 1
        for item in diff.removed:
            record = by_des.get(item.designator.strip().upper())
            if record is None:
                continue
            record.remark = ((record.remark + " ") if record.remark else "") \
                + "ECO removed"
            self._repo.update(record)
            self._log_history(record, "ECO", remark="ECO removed",
                              created_at=timestamp)
            changed += 1
        for item in diff.moved:
            record = by_des.get(item.designator.strip().upper())
            if record is None:
                continue
            old_x = record.new_x if record.new_x is not None else record.old_x
            old_y = record.new_y if record.new_y is not None else record.old_y
            old_rot = (record.new_rotation if record.new_rotation is not None
                       else record.old_rotation)
            record.old_x, record.old_y = item.new_x, item.new_y
            record.old_rotation = item.new_rotation
            record.new_x = record.new_y = record.new_rotation = None
            record.status = "Pending"
            record.review_time = timestamp
            self._repo.update(record)
            self._log_history(record, "Edit", old_x=old_x, old_y=old_y,
                              old_rot=old_rot, created_at=timestamp)
            changed += 1
        for item in diff.mpn_changed:
            record = by_des.get(item.designator.strip().upper())
            if record is None:
                continue
            old_mpn = record.mpn or ""
            record.mpn = item.new_mpn
            record.review_time = record.review_time or timestamp
            self._repo.update(record)
            self._log_history(record, "ECO", mpn_old=old_mpn,
                              mpn_new=item.new_mpn, created_at=timestamp)
            changed += 1
        self._dirty = True
        self._table_widget.set_records(self._records)
        self._review_panel.set_record_list(self._records)
        self._sync_after_mutation(
            min(self._current_index, len(self._records) - 1)
            if self._records else -1)
        self._update_progress()
        self._status_label.setText(
            tr("Applied ECO: +{a} −{r} ~{m} ⇄{p}",
               a=len(diff.added), r=len(diff.removed),
               m=len(diff.moved), p=len(diff.mpn_changed)))
        return changed

    def _export_eco_report(self) -> None:
        diff = getattr(self, "_eco_diff", None)
        if diff is None or diff.is_empty:
            QMessageBox.warning(self, tr("Warning"), tr("No ECO data to export."))
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"ECO_Report_{timestamp}.xlsx"
        file_path, _ = QFileDialog.getSaveFileName(
            self, tr("Export ECO Report"), default_name,
            "Excel Files (*.xlsx);;All Files (*.*)"
        )
        if not file_path:
            return
        self._set_exporting(True)
        worker = ExportWorker(
            self._exporter.export_eco_report, (diff, file_path), self
        )
        worker.finished_ok.connect(self._on_export_done)
        worker.finished_err.connect(self._on_export_error)
        self._export_worker = worker
        worker.start()

    def _run_with_busy_dialog(self, text: str, fn: Callable[[], Any],
                              dialog_factory: Optional[Callable] = None) -> Any:
        """Run `fn` behind a modal busy indicator so the app never looks hung.

        Returns fn()'s value. Exceptions propagate after the dialog closes
        so callers keep their existing error handling.
        """
        from PySide6.QtWidgets import QProgressDialog

        if dialog_factory is not None:
            dlg = dialog_factory(text)
        else:
            dlg = QProgressDialog(text, "", 0, 0, self)
            dlg.setWindowTitle(tr("Please wait"))
            dlg.setCancelButton(None)
            dlg.setWindowModality(Qt.ApplicationModal)
            dlg.setMinimumDuration(0)
            dlg.setValue(0)

        QApplication.setOverrideCursor(Qt.WaitCursor)
        QApplication.processEvents()
        try:
            return fn()
        finally:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass
            try:
                dlg.reset()
                dlg.close()
                dlg.deleteLater()
            except RuntimeError:
                pass

    def _apply_prescreen_result(self, issues) -> None:
        if issues is None:
            return
        for r in self._records:
            r.prescreen_flags = []
        flagged = set()
        flag_count = 0
        for iss in issues:
            if 0 <= iss.index < len(self._records):
                rec = self._records[iss.index]
                if iss.kind not in rec.prescreen_flags:
                    rec.prescreen_flags.append(iss.kind)
                    flag_count += 1
                flagged.add(iss.index)
        t = Timer()
        self._table_widget.update_all_rows()
        table_ms = t.ms()
        counts = summarize(issues)
        total = counts["TOTAL"]
        if total:
            self._status_label.setText(tr(
                "⚠ Pre-screen: {total} issue(s) ({rot} ROT · {pad} PAD · {dup} DUP · {out} OUT)",
                total=total, rot=counts["ROT"], pad=counts["PAD"],
                dup=counts["DUP"], out=counts["OUT"],
            ))
        else:
            self._status_label.setText(tr("✅ No issues found."))
        t = Timer()
        self._sync_viewer_flags()
        viewer_ms = t.ms()
        log_event("prescreen_apply", table_ms=table_ms, viewer_sync_ms=viewer_ms,
                  flags=flag_count)

    def _current_flagged_indices(self) -> set:
        return {i for i, r in enumerate(self._records) if r.prescreen_flags}

    def _sync_viewer_flags(self) -> None:
        viewer = self._gerber_viewer
        if viewer is None:
            return
        try:
            viewer.set_flagged_indices(self._current_flagged_indices())
        except RuntimeError:
            pass

    def _on_flag_dismiss(self, record_index: int) -> None:
        if not (0 <= record_index < len(self._records)):
            return
        rec = self._records[record_index]
        for kind in list(rec.prescreen_flags):
            self._prescreen_dismissed.add(dismiss_key_for(kind, rec))
        rec.prescreen_flags = []
        self._table_widget.update_record_row(record_index)
        self._dirty = True
        self._sync_viewer_flags()

    def _restore_prescreen_bundle(self, session) -> None:
        """Rebuild the Run Check bundle from a saved session (if it has one).

        Sessions saved before this feature carry no prescreen_ctx; the button
        then stays disabled until the user runs Align PickPlace Origin once.
        """
        self._prescreen_bundle = None
        self._prescreen_ctx_packed = None
        if hasattr(self, "_btn_run_check"):
            self._btn_run_check.setEnabled(False)
        packed = getattr(session, "prescreen_ctx", None)
        if not packed:
            return
        ctx = unpack_prescreen_ctx(packed)
        if ctx is None:
            return
        gko = self._gerber_path_of_role("profile")
        if not gko or not os.path.exists(gko):
            return
        self._prescreen_bundle = (
            gko,
            self._gerber_path_of_role("paste", "top"),
            self._gerber_path_of_role("paste", "bottom"),
            ctx,
        )
        self._prescreen_ctx_packed = packed
        if hasattr(self, "_btn_run_check"):
            self._btn_run_check.setEnabled(True)

    def _open_prescreen_dialog(self) -> None:
        """Open (or focus) the standalone Pre-screen Check panel."""
        if not self._records:
            QMessageBox.warning(self, tr("Warning"),
                                tr("No data. Open a PickPlace file or load a session first."))
            return
        dlg = self._prescreen_dialog
        if dlg is not None:
            try:
                if dlg.isVisible():
                    dlg.raise_()
                    dlg.activateWindow()
                    return
            except RuntimeError:
                pass
            self._prescreen_dialog = None
        dlg = PrescreenCheckDialog(
            self._records,
            lambda: self._prescreen_bundle,
            self._prescreen_dismissed,
            parent=self,
        )
        dlg.checks_finished.connect(self._apply_prescreen_issues)
        dlg.finished.connect(self._on_prescreen_dialog_closed)
        self._prescreen_dialog = dlg
        dlg.show()

    def _apply_prescreen_issues(self, issues) -> None:
        self._apply_prescreen_result(issues)
        log_event("prescreen_rerun", issues=len(issues or ()), rows=len(self._records))

    def _on_prescreen_dialog_closed(self, *_args) -> None:
        self._prescreen_dialog = None

    def _close_prescreen_dialog(self) -> None:
        dlg = getattr(self, "_prescreen_dialog", None)
        if dlg is not None:
            try:
                dlg.close()
            except RuntimeError:
                pass
            self._prescreen_dialog = None

    def _open_gerber_check(self) -> None:
        if not self._records:
            QMessageBox.warning(self, tr("Warning"), tr("No data. Open a PickPlace file or load a session first."))
            return

        from ui.gerber_file_dialog import GerberFileDialog

        dlg = GerberFileDialog(
            self._existing_gerber_folder(), self._existing_gerber_layers(),
            self._config_mgr, self)
        if dlg.exec() != QDialog.Accepted:
            return
        layers = dlg.selected_layers()
        if not layers:
            return
        self._config_mgr.update(
            gerberFolder=dlg.selected_folder(),
            gerberLayers=self._layer_entries(layers),
        )

        viewer = GerberViewer(
            self._records, layers,
            display_settings=self._gerber_view_settings,
        )
        viewer.settings_saved.connect(self._on_gerber_view_settings_saved)
        viewer.checked_changed.connect(self._on_gerber_component_checked)
        viewer.rotation_edited.connect(self._on_gerber_rotation_edited)
        viewer.status_message.connect(self._status_label.setText)
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

    def _on_gerber_component_checked(self, record_index: int) -> None:
        if 0 <= record_index < len(self._records):
            self._repo.update(self._records[record_index])
            self._table_widget.update_record_checked(record_index)

    def _on_gerber_rotation_edited(self, record_index: int) -> None:
        if 0 <= record_index < len(self._records):
            rec = self._records[record_index]
            self._repo.update(rec)
            # Viewer already set new_rotation + review_time; old unknown here,
            # log with old=None so the line still shows công đoạn + giá trị mới.
            self._log_history(rec, "Edit", old_x=None, old_y=None, old_rot=None)
            self._table_widget.update_record_row(record_index)
            self._update_progress()
            self._status_label.setText(tr("{des}: Edited", des=rec.designator))
            if record_index == self._current_index:
                self._refresh_history_panel(rec)

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
        # Capture once per align batch to log old->new correctly
        if record not in self._pending_align_writes:
            record._align_old = (record.new_x, record.new_y, record.new_rotation,
                                 record.remark)
        if new_x is not None:
            record.new_x = new_x
        if new_y is not None:
            record.new_y = new_y
        if new_rotation is not None:
            record.new_rotation = new_rotation
        if record.status == "Pending":
            record.status = "Aligned"
        record.review_time = timestamp
        # Defer the DB write: wizard flushes everything in ONE transaction
        # at the end of the apply loop (avoids hundreds of fsync commits).
        if record not in self._pending_align_writes:
            self._pending_align_writes.append(record)
        self._table_widget.update_record_row(self._records.index(record))

    def _flush_align_writes(self) -> None:
        pending = list(self._pending_align_writes)
        self._pending_align_writes.clear()
        if not pending:
            return
        t = Timer()
        try:
            self._repo.update_many(pending)
        except RuntimeError:
            return
        for record in pending:
            old = getattr(record, "_align_old", (None, None, None, ""))
            try:
                delattr(record, "_align_old")
            except AttributeError:
                pass
            self._log_history(record, "Align", old_x=old[0], old_y=old[1],
                              old_rot=old[2], remark=old[3])
        self._dirty = True
        log_event("align_db_flush", records=len(pending), ms=t.ms())

    def _find_record(self, designator: str, block: int = 0) -> Optional[ReviewRecord]:
        for r in self._records:
            if r.designator == designator and getattr(r, "block", 0) == block:
                return r
        return None

    def _record_snapshot(self) -> List[Dict[str, Any]]:
        return SessionService.records_to_list(self._records)

    def _log_history(self, record: ReviewRecord, action: str,
                     old_x=None, old_y=None, old_rot=None,
                     remark: str = "", created_at: str = "",
                     mpn_old: str = "", mpn_new: str = "") -> None:
        try:
            from models.history import HistoryEntry
            ts = created_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            entry = HistoryEntry(
                designator=record.designator,
                block=int(getattr(record, "block", 0) or 0),
                action=action,
                old_x=old_x, old_y=old_y, old_rotation=old_rot,
                new_x=record.new_x, new_y=record.new_y,
                new_rotation=record.new_rotation,
                mpn_old=mpn_old, mpn_new=mpn_new,
                remark=remark if remark else (record.remark or ""),
                created_at=ts,
            )
            self._history_repo.add(entry)
        except Exception:
            pass

    def _refresh_history_panel(self, record: Optional[ReviewRecord] = None) -> None:
        try:
            if record is None:
                if 0 <= self._current_index < len(self._records):
                    record = self._records[self._current_index]
                else:
                    return
            entries = self._history_repo.list_by(
                record.designator, int(getattr(record, "block", 0) or 0)
            )
            self._review_panel.reload_history(entries)
        except Exception:
            pass

    def _collect_history_dicts(self) -> List[Dict[str, Any]]:
        try:
            return [e.to_dict() for e in self._history_repo.get_all()]
        except Exception:
            return []

    def _restore_history(self, raw) -> None:
        try:
            self._history_repo.clear_all()
        except Exception:
            return
        if not raw:
            return
        try:
            from models.history import HistoryEntry
            for item in raw:
                if isinstance(item, dict):
                    self._history_repo.add(HistoryEntry.from_dict(item))
        except Exception:
            pass

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
        if not self._records:
            self._current_index = -1
        target = min(self._current_index, len(self._records) - 1) if self._records else -1
        self._sync_after_mutation(target)

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
