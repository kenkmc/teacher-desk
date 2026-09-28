APP_QSS = """
QMainWindow, QWidget {
    background: #f4f1ea;
    color: #2c2416;
    font-size: 10pt;
}
QListWidget#ModuleList {
    background: #2f3e46;
    color: #edf0f2;
    border: none;
    padding: 8px 0;
    outline: none;
}
QListWidget#ModuleList::item {
    padding: 10px 16px;
    margin: 2px 8px;
    border-radius: 6px;
}
QListWidget#ModuleList::item:selected {
    background: #52796f;
    color: white;
}
QListWidget#ModuleList::item:hover {
    background: #3d5a54;
}
QLabel#TitleLabel {
    font-size: 16pt;
    font-weight: 600;
    color: #1d3557;
}
QLabel#HintLabel {
    color: #5c5346;
}
QPushButton {
    background: #52796f;
    color: white;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
}
QPushButton:hover {
    background: #3d5a54;
}
QPushButton:disabled {
    background: #b7c4c0;
}
QPushButton#QuitButton {
    background: #a33a32;
    margin: 8px 12px 0 12px;
}
QPushButton#QuitButton:hover {
    background: #842d27;
}
QLineEdit, QSpinBox, QComboBox, QPlainTextEdit, QDateEdit {
    background: white;
    border: 1px solid #cfc6b8;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 26px;
}
QTableWidget, QListWidget {
    background: white;
    border: 1px solid #cfc6b8;
    border-radius: 4px;
}
QGroupBox {
    font-weight: 600;
    border: 1px solid #d9d0c3;
    border-radius: 8px;
    margin-top: 12px;
    padding: 12px 8px 8px 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
QStatusBar {
    background: #e7e0d5;
}
"""
