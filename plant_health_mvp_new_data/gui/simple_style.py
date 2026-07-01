"""Plain dark Qt styling shared by the student-style apps."""

SIMPLE_DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #202020;
    color: #eeeeee;
    font-size: 10pt;
}
QLineEdit, QDoubleSpinBox, QSpinBox, QPlainTextEdit, QTextEdit, QTableWidget, QComboBox {
    background: #2b2b2b;
    color: #eeeeee;
    border: 1px solid #777777;
    padding: 2px;
}
QPushButton {
    background: #333333;
    color: #eeeeee;
    border: 1px solid #888888;
    padding: 4px;
}
QPushButton:pressed {
    background: #444444;
}
QTabWidget::pane {
    border: 1px solid #777777;
}
QTabBar::tab {
    background: #2b2b2b;
    border: 1px solid #777777;
    padding: 4px 8px;
}
QTabBar::tab:selected {
    background: #444444;
}
QHeaderView::section {
    background: #333333;
    color: #eeeeee;
    border: 1px solid #777777;
}
QSlider::groove:horizontal {
    height: 5px;
    background: #777777;
}
QSlider::handle:horizontal {
    width: 12px;
    margin: -4px 0;
    background: #dddddd;
    border: 1px solid #999999;
}
QCheckBox {
    spacing: 4px;
}
"""


def set_simple_margins(layout, margin: int = 4, spacing: int = 4) -> None:
    """Apply small, plain margins to Qt layouts."""

    layout.setContentsMargins(margin, margin, margin, margin)
    layout.setSpacing(spacing)

