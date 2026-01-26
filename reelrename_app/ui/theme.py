from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt


def dark_palette() -> QPalette:
    p = QPalette()

    p.setColor(QPalette.Window, QColor(30, 30, 30))
    p.setColor(QPalette.WindowText, Qt.white)
    p.setColor(QPalette.Base, QColor(24, 24, 24))
    p.setColor(QPalette.AlternateBase, QColor(40, 40, 40))
    p.setColor(QPalette.ToolTipBase, Qt.white)
    p.setColor(QPalette.ToolTipText, Qt.white)
    p.setColor(QPalette.Text, Qt.white)
    p.setColor(QPalette.Button, QColor(45, 45, 45))
    p.setColor(QPalette.ButtonText, Qt.white)
    p.setColor(QPalette.BrightText, Qt.red)
    p.setColor(QPalette.Highlight, QColor(88, 130, 255))
    p.setColor(QPalette.HighlightedText, Qt.black)

    return p


def light_palette() -> QPalette:
    return QPalette()  # Qt default light theme
