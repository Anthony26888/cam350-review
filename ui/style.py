APP_STYLE = "Fusion"

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette

ACCENT = "#0D9488"
ACCENT_HOVER = "#0F766E"
ACCENT_PRESSED = "#115E59"
ACCENT_LIGHT = "#CCFBF1"

BG = "#0F172A"
BG_SURFACE = "#1E293B"
BG_INPUT = "#0F172A"
BORDER = "#334155"
TEXT = "#E2E8F0"
TEXT_MUTED = "#94A3B8"

QSS_DARK = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #E2E8F0;
}

QMainWindow {
    background-color: #0F172A;
}

QDialog {
    background-color: #111827;
}

QMessageBox {
    background-color: #0F172A;
}

QGroupBox {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 12px 12px 12px;
    padding-top: 18px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: content;
    subcontrol-position: top left;
    left: 12px;
    top: -15px;
    padding: 0 4px;
    color: #2DD4BF;
    font-size: 11pt;
}

QPushButton {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #334155;
    border-color: #475569;
}

QPushButton:pressed {
    background-color: #475569;
}

QPushButton:disabled {
    color: #64748B;
    background-color: #111827;
    border-color: #1E293B;
}

QPushButton#action_btn {
    background-color: #334155;
    border: 1px solid #475569;
    color: #F1F5F9;
}

QPushButton#action_btn:hover {
    background-color: #475569;
    border-color: #64748B;
}

QPushButton#action_btn:pressed {
    background-color: #1E293B;
}

QPushButton#action_btn:disabled {
    color: #64748B;
    background-color: #1E293B;
    border-color: #334155;
}

QPushButton#primary {
    background-color: #0D9488;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#primary:hover {
    background-color: #14B8A6;
}

QPushButton#primary:pressed {
    background-color: #0F766E;
}

QPushButton#danger {
    background-color: #DC2626;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#danger:hover {
    background-color: #EF4444;
}

QPushButton#success {
    background-color: #16A34A;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#success:hover {
    background-color: #22C55E;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background-color: #0F172A;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #0D9488;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #2DD4BF;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #94A3B8;
}

QComboBox QAbstractItemView {
    background-color: #1E293B;
    border: 1px solid #334155;
    selection-background-color: #134E4A;
    selection-color: #E2E8F0;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}

QTableWidget, QTableView {
    background-color: #0F172A;
    alternate-background-color: #111827;
    border: 1px solid #334155;
    border-radius: 6px;
    gridline-color: #334155;
}

QTableWidget::item {
    padding: 4px 6px;
    border: none;
}

QTableWidget::item:hover {
    background-color: #134E4A;
}

QTableWidget::item:selected {
    background-color: #0F766E;
    color: #FFFFFF;
}

QHeaderView::section {
    background-color: #1E293B;
    color: #CBD5E1;
    font-weight: bold;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #334155;
    border-bottom: 1px solid #334155;
}

QTableCornerButton::section {
    background-color: #1E293B;
    border: none;
    border-bottom: 1px solid #334155;
}

QToolBar {
    background-color: #111827;
    border: none;
    border-bottom: 1px solid #334155;
    padding: 4px;
    spacing: 4px;
}

QToolBar QPushButton {
    padding: 6px 10px;
}

QToolBar QPushButton:disabled {
    color: #64748B;
    background-color: #111827;
    border-color: #1E293B;
}

QMenuBar {
    background-color: #111827;
    color: #E2E8F0;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #134E4A;
}

QMenu {
    background-color: #111827;
    border: 1px solid #334155;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #134E4A;
}

QMenu::separator {
    height: 1px;
    background: #334155;
    margin: 4px 8px;
}

QStatusBar {
    background-color: #111827;
    border-top: 1px solid #334155;
    color: #94A3B8;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #475569;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #64748B;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #475569;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #64748B;
}

QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
    border: none;
    height: 0;
    width: 0;
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
}

QToolTip {
    background-color: #1E293B;
    color: #E2E8F0;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 8px;
}

QLabel#title {
    font-size: 14pt;
    font-weight: bold;
    color: #E2E8F0;
}

QLabel#stat_total { color: #2DD4BF; font-weight: bold; font-size: 14pt; }
QLabel#stat_pending { color: #E2E8F0; font-weight: bold; font-size: 14pt; }
QLabel#stat_ok { color: #4ADE80; font-weight: bold; font-size: 14pt; }
QLabel#stat_edit { color: #FB923C; font-weight: bold; font-size: 14pt; }
QLabel#stat_align { color: #60A5FA; font-weight: bold; font-size: 14pt; }
QLabel#stat_sep { color: #475569; padding: 0 2px; }

QFrame#stat_card {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
}

QLabel#stat_card_caption {
    color: #94A3B8;
    font-size: 9pt;
}

QLabel#hwid_value {
    color: #E2E8F0;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11pt;
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 4px;
    padding: 4px 8px;
}
QLabel#hint { color: #94A3B8; font-size: 9pt; }
QLabel#reason { color: #F87171; font-size: 10pt; font-weight: bold; }

QLabel#newval {
    color: #2DD4BF;
    font-weight: bold;
}
"""

QSS_LIGHT = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #0F172A;
}

QMainWindow {
    background-color: #DFE5EC;
}

QDialog {
    background-color: #FFFFFF;
}

QMessageBox {
    background-color: #F8FAFC;
}

QGroupBox {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 12px 12px 12px;
    padding-top: 18px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: content;
    subcontrol-position: top left;
    left: 12px;
    top: -15px;
    padding: 0 4px;
    color: #0D9488;
    font-size: 11pt;
}

QPushButton {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #F1F5F9;
    border-color: #CBD5E1;
}

QPushButton:pressed {
    background-color: #E2E8F0;
}

QPushButton:disabled {
    color: #94A3B8;
    background-color: #F1F5F9;
    border-color: #E2E8F0;
}

QPushButton#action_btn {
    background-color: #F1F5F9;
    border: 1px solid #CBD5E1;
    color: #0F172A;
}

QPushButton#action_btn:hover {
    background-color: #E2E8F0;
    border-color: #94A3B8;
}

QPushButton#action_btn:pressed {
    background-color: #CBD5E1;
}

QPushButton#action_btn:disabled {
    color: #94A3B8;
    background-color: #F8FAFC;
    border-color: #E2E8F0;
}

QPushButton#primary {
    background-color: #0D9488;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#primary:hover {
    background-color: #0F766E;
}

QPushButton#primary:pressed {
    background-color: #115E59;
}

QPushButton#danger {
    background-color: #DC2626;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#danger:hover {
    background-color: #B91C1C;
}

QPushButton#success {
    background-color: #16A34A;
    color: #FFFFFF;
    font-weight: bold;
    border: none;
}

QPushButton#success:hover {
    background-color: #15803D;
}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit {
    background-color: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: #0D9488;
    selection-color: #FFFFFF;
}

QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QTextEdit:focus {
    border: 1px solid #0D9488;
}

QComboBox::drop-down {
    border: none;
    width: 22px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #64748B;
}

QComboBox QAbstractItemView {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    selection-background-color: #CCFBF1;
    selection-color: #0F172A;
}

QSpinBox::up-button, QDoubleSpinBox::up-button,
QSpinBox::down-button, QDoubleSpinBox::down-button {
    width: 18px;
    border: none;
    background: transparent;
}

QTableWidget, QTableView {
    background-color: #FFFFFF;
    alternate-background-color: #F8FAFC;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    gridline-color: #E2E8F0;
}

QTableWidget::item {
    padding: 4px 6px;
    border: none;
}

QTableWidget::item:hover {
    background-color: #F0FDFA;
}

QTableWidget::item:selected {
    background-color: #99F6E4;
    color: #0F172A;
}

QHeaderView::section {
    background-color: #F1F5F9;
    color: #334155;
    font-weight: bold;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid #E2E8F0;
    border-bottom: 1px solid #E2E8F0;
}

QTableCornerButton::section {
    background-color: #F1F5F9;
    border: none;
    border-bottom: 1px solid #E2E8F0;
}

QToolBar {
    background-color: #FFFFFF;
    border: none;
    border-bottom: 1px solid #E2E8F0;
    padding: 4px;
    spacing: 4px;
}

QToolBar QPushButton {
    padding: 6px 10px;
    border-color: #CBD5E1;
}

QToolBar QPushButton:disabled {
    color: #94A3B8;
    background-color: transparent;
    border-color: #E2E8F0;
}

QMenuBar {
    background-color: #FFFFFF;
    color: #0F172A;
}

QMenuBar::item {
    background: transparent;
    padding: 4px 10px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #CCFBF1;
}

QMenu {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 6px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #CCFBF1;
}

QMenu::separator {
    height: 1px;
    background: #E2E8F0;
    margin: 4px 8px;
}

QStatusBar {
    background-color: #FFFFFF;
    border-top: 1px solid #E2E8F0;
    color: #64748B;
}

QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #CBD5E1;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #94A3B8;
}

QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #CBD5E1;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #94A3B8;
}

QScrollBar::add-line, QScrollBar::sub-line {
    background: none;
    border: none;
    height: 0;
    width: 0;
}

QScrollBar::add-page, QScrollBar::sub-page {
    background: none;
}

QToolTip {
    background-color: #0F172A;
    color: #FFFFFF;
    border: none;
    border-radius: 4px;
    padding: 4px 8px;
}

QLabel#title {
    font-size: 14pt;
    font-weight: bold;
    color: #0F172A;
}

QLabel#stat_total { color: #0D9488; font-weight: bold; font-size: 14pt; }
QLabel#stat_pending { color: #0F172A; font-weight: bold; font-size: 14pt; }
QLabel#stat_ok { color: #166534; font-weight: bold; font-size: 14pt; }
QLabel#stat_edit { color: #EA580C; font-weight: bold; font-size: 14pt; }
QLabel#stat_align { color: #3B82F6; font-weight: bold; font-size: 14pt; }
QLabel#stat_sep { color: #CBD5E1; padding: 0 2px; }

QFrame#stat_card {
    background-color: #FFFFFF;
    border: 1px solid #E2E8F0;
    border-radius: 8px;
}

QLabel#stat_card_caption {
    color: #64748B;
    font-size: 9pt;
}

QLabel#hwid_value {
    color: #0F172A;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 11pt;
    background-color: #F1F5F9;
    border: 1px solid #E2E8F0;
    border-radius: 4px;
    padding: 4px 8px;
}
QLabel#hint { color: #64748B; font-size: 9pt; }
QLabel#reason { color: #DC2626; font-size: 10pt; font-weight: bold; }

QLabel#newval {
    color: #0D9488;
    font-weight: bold;
}
"""

_STATUS_BG_COLORS_LIGHT = {
    "Pending": None,
    "OK": QColor(240, 253, 244),
    "Edited": QColor(254, 242, 242),
    "Aligned": QColor(240, 253, 250),
}

_STATUS_TEXT_COLORS_LIGHT = {
    "Pending": None,
    "OK": QColor(22, 101, 52),
    "Edited": QColor(234, 88, 12),
    "Aligned": QColor(59, 130, 246),
}

_DARK_PALETTE = QPalette()
_DARK_PALETTE.setColor(QPalette.Window, QColor("#0F172A"))
_DARK_PALETTE.setColor(QPalette.WindowText, QColor("#E2E8F0"))
_DARK_PALETTE.setColor(QPalette.Base, QColor("#0F172A"))
_DARK_PALETTE.setColor(QPalette.AlternateBase, QColor("#111827"))
_DARK_PALETTE.setColor(QPalette.Text, QColor("#E2E8F0"))
_DARK_PALETTE.setColor(QPalette.Button, QColor("#1E293B"))
_DARK_PALETTE.setColor(QPalette.ButtonText, QColor("#E2E8F0"))
_DARK_PALETTE.setColor(QPalette.ToolTipBase, QColor("#1E293B"))
_DARK_PALETTE.setColor(QPalette.ToolTipText, QColor("#E2E8F0"))
_DARK_PALETTE.setColor(QPalette.Highlight, QColor("#0D9488"))
_DARK_PALETTE.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
_DARK_PALETTE.setColor(QPalette.PlaceholderText, QColor("#64748B"))
_DARK_PALETTE.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#64748B"))
_DARK_PALETTE.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#64748B"))
_DARK_PALETTE.setColor(QPalette.Disabled, QPalette.Text, QColor("#64748B"))

_LIGHT_PALETTE = QPalette()
_LIGHT_PALETTE.setColor(QPalette.Window, QColor("#DFE5EC"))
_LIGHT_PALETTE.setColor(QPalette.WindowText, QColor("#0F172A"))
_LIGHT_PALETTE.setColor(QPalette.Base, QColor("#FFFFFF"))
_LIGHT_PALETTE.setColor(QPalette.AlternateBase, QColor("#F8FAFC"))
_LIGHT_PALETTE.setColor(QPalette.Text, QColor("#0F172A"))
_LIGHT_PALETTE.setColor(QPalette.Button, QColor("#FFFFFF"))
_LIGHT_PALETTE.setColor(QPalette.ButtonText, QColor("#0F172A"))
_LIGHT_PALETTE.setColor(QPalette.ToolTipBase, QColor("#0F172A"))
_LIGHT_PALETTE.setColor(QPalette.ToolTipText, QColor("#FFFFFF"))
_LIGHT_PALETTE.setColor(QPalette.Highlight, QColor("#0D9488"))
_LIGHT_PALETTE.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
_LIGHT_PALETTE.setColor(QPalette.PlaceholderText, QColor("#64748B"))
_LIGHT_PALETTE.setColor(QPalette.Disabled, QPalette.WindowText, QColor("#94A3B8"))
_LIGHT_PALETTE.setColor(QPalette.Disabled, QPalette.ButtonText, QColor("#94A3B8"))
_LIGHT_PALETTE.setColor(QPalette.Disabled, QPalette.Text, QColor("#94A3B8"))

_STATUS_BG_COLORS_DARK = {
    "Pending": None,
    "OK": QColor(20, 83, 45),
    "Edited": QColor(127, 29, 29),
    "Aligned": QColor(12, 74, 110),
}

_STATUS_TEXT_COLORS_DARK = {
    "Pending": None,
    "OK": QColor(74, 222, 128),
    "Edited": QColor(251, 146, 60),
    "Aligned": QColor(96, 165, 250),
}


def apply_theme(app, theme: str) -> None:
    """Apply the global stylesheet + palette for the given theme ('light' or 'dark')."""
    dark = theme == "dark"
    app.setPalette(_DARK_PALETTE if dark else _LIGHT_PALETTE)
    app.setStyleSheet(QSS_DARK if dark else QSS_LIGHT)
    for widget in QApplication.allWidgets():
        refresh = getattr(widget, "refresh_icons", None)
        if callable(refresh):
            refresh()


def status_bg_colors(theme: str) -> dict:
    return _STATUS_BG_COLORS_DARK if theme == "dark" else _STATUS_BG_COLORS_LIGHT


def status_text_colors(theme: str) -> dict:
    return _STATUS_TEXT_COLORS_DARK if theme == "dark" else _STATUS_TEXT_COLORS_LIGHT
