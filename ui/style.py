APP_STYLE = "Fusion"

ACCENT = "#0D9488"
ACCENT_HOVER = "#0F766E"
ACCENT_PRESSED = "#115E59"
ACCENT_LIGHT = "#CCFBF1"

QSS_LIGHT = """
* {
    font-family: "Segoe UI";
    font-size: 10pt;
    color: #0F172A;
}

QMainWindow {
    background-color: #F8FAFC;
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
    margin-top: 14px;
    padding: 12px;
    font-weight: bold;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
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

QLabel#stat_total { color: #0D9488; font-weight: bold; padding: 0 4px; }
QLabel#stat_pending { color: #0F172A; font-weight: bold; padding: 0 4px; }
QLabel#stat_ok { color: #166534; font-weight: bold; padding: 0 4px; }
QLabel#stat_edit { color: #EA580C; font-weight: bold; padding: 0 4px; }
QLabel#stat_align { color: #3B82F6; font-weight: bold; padding: 0 4px; }
QLabel#stat_sep { color: #CBD5E1; padding: 0 2px; }

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
