"""Farbschema und Stylesheet (dunkel/hell)."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

ACCENT = "#3b82f6"

PALETTES = {
    "dark": {
        "bg": "#16181d", "surface": "#1e2128", "surface2": "#262a33", "border": "#323743",
        "text": "#e6e8ec", "muted": "#9aa1ad", "accent": ACCENT, "accent_hover": "#5b9bff",
        "danger": "#ef4444", "success": "#22c55e", "warning": "#f59e0b", "selection": "#2b4a7a",
    },
    "light": {
        "bg": "#f4f5f7", "surface": "#ffffff", "surface2": "#eef0f3", "border": "#d9dce2",
        "text": "#1d2129", "muted": "#626a77", "accent": "#2563eb", "accent_hover": "#3b7bff",
        "danger": "#dc2626", "success": "#16a34a", "warning": "#d97706", "selection": "#cfe0ff",
    },
}

current: dict[str, str] = PALETTES["dark"]


def apply_theme(app: QApplication, name: str = "dark") -> None:
    global current
    current = PALETTES.get(name, PALETTES["dark"])
    c = current
    app.setStyle("Fusion")

    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(c["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(c["surface"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(c["accent"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c["surface2"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(c["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["muted"]))
    pal.setColor(QPalette.ColorRole.Link, QColor(c["accent"]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.ButtonText, QPalette.ColorRole.WindowText):
        pal.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(stylesheet(c))


def stylesheet(c: dict[str, str]) -> str:
    return f"""
    QWidget {{ font-family: "Segoe UI"; font-size: 10pt; }}
    QToolTip {{ background: {c['surface2']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}

    QMenuBar {{ background: {c['bg']}; }}
    QMenuBar::item:selected {{ background: {c['surface2']}; border-radius: 4px; }}
    QMenu {{ background: {c['surface']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['selection']}; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 4px 8px; }}

    QToolBar {{ background: {c['bg']}; border: none; border-bottom: 1px solid {c['border']}; spacing: 2px; padding: 4px; }}
    QToolBar QToolButton {{ padding: 5px 10px; border-radius: 6px; }}
    QToolBar QToolButton:hover {{ background: {c['surface2']}; }}
    QStatusBar {{ background: {c['bg']}; border-top: 1px solid {c['border']}; color: {c['muted']}; }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 5px 8px;
        selection-background-color: {c['accent']};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
    QComboBox QAbstractItemView {{ background: {c['surface']}; border: 1px solid {c['border']}; selection-background-color: {c['selection']}; }}

    QPushButton {{ background: {c['surface2']}; border: 1px solid {c['border']}; border-radius: 6px; padding: 6px 14px; }}
    QPushButton:hover {{ border-color: {c['accent']}; }}
    QPushButton:disabled {{ color: {c['muted']}; }}
    QPushButton[primary="true"] {{ background: {c['accent']}; border-color: {c['accent']}; color: white; font-weight: 600; }}
    QPushButton[primary="true"]:hover {{ background: {c['accent_hover']}; }}
    QPushButton[danger="true"] {{ color: {c['danger']}; }}

    QTreeWidget, QListWidget, QTableWidget {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 6px; outline: none; }}
    QTreeWidget::item, QListWidget::item {{ padding: 4px; border-radius: 4px; }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['surface2']}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
    QHeaderView::section {{ background: {c['surface2']}; border: none; padding: 5px; }}

    QTabWidget::pane {{ border: 1px solid {c['border']}; border-radius: 6px; top: -1px; }}
    QTabBar::tab {{ background: transparent; padding: 7px 14px; border-bottom: 2px solid transparent; }}
    QTabBar::tab:selected {{ border-bottom-color: {c['accent']}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
    QScrollBar::handle:vertical {{ background: {c['border']}; border-radius: 5px; min-height: 30px; }}
    QScrollBar:horizontal {{ background: transparent; height: 10px; }}
    QScrollBar::handle:horizontal {{ background: {c['border']}; border-radius: 5px; min-width: 30px; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QGroupBox {{ border: 1px solid {c['border']}; border-radius: 8px; margin-top: 14px; padding: 10px; }}
    QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {c['muted']}; }}
    QProgressBar {{ background: {c['surface2']}; border: none; border-radius: 4px; height: 8px; text-align: center; }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

    /* --- Eigene Komponenten --- */
    #Sidebar {{ background: {c['surface']}; border-right: 1px solid {c['border']}; }}
    #Sidebar QTreeWidget {{ border: none; background: transparent; }}
    #SidebarNav QPushButton {{ text-align: left; border: none; background: transparent; padding: 8px 10px; }}
    #SidebarNav QPushButton:hover {{ background: {c['surface2']}; }}
    #SectionTitle {{ color: {c['muted']}; font-size: 9pt; font-weight: 600; letter-spacing: 1px; }}
    #PageTitle {{ font-size: 18pt; font-weight: 600; }}
    #PageSubtitle {{ color: {c['muted']}; }}
    #Muted {{ color: {c['muted']}; }}

    #ToolCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    #ToolCard:hover {{ border-color: {c['accent']}; background: {c['surface2']}; }}
    #ToolCard QLabel {{ background: transparent; }}
    #ToolTile {{ background: transparent; border: 1px solid transparent; border-radius: 12px; }}
    #ToolTile:hover {{ background: {c['surface']}; border-color: {c['border']}; }}
    #ToolTile[selected="true"] {{ background: {c['surface2']}; border-color: {c['accent']}; }}
    #ToolTile QLabel {{ background: transparent; }}
    #TileName {{ font-size: 9.5pt; }}
    QLabel#UpdateDot {{ background: {c['warning']}; border-radius: 5px; }}
    #DetailsPanel {{ background: {c['surface']}; border-left: 1px solid {c['border']}; }}
    #DetailsPanel QScrollArea, #DetailsContent {{ background: {c['surface']}; }}
    #IconGrid {{ background: {c['bg']}; border: none; }}
    #IconGrid::item {{ border-radius: 10px; padding: 6px; color: {c['muted']}; }}
    #IconGrid::item:hover {{ background: {c['surface']}; color: {c['text']}; }}
    #IconGrid::item:selected {{ background: {c['selection']}; color: {c['text']}; }}
    /* Vorschau auf hellem Grund: so sehen exportierte Symbole in Visio/Word aus */
    QLabel#IconPreview {{ background: #f4f5f7; border: 1px solid {c['border']}; border-radius: 14px; }}
    QPushButton#FilterChip {{ background: {c['selection']}; border: 1px solid {c['accent']}; border-radius: 13px;
                              padding: 3px 12px; }}
    QPushButton[active="true"] {{ border-color: {c['accent']}; color: {c['accent']}; }}
    QPushButton#FlatButton {{ background: transparent; border: none; padding: 4px 8px; color: {c['muted']}; }}
    QPushButton#FlatButton:hover {{ color: {c['text']}; background: {c['surface2']}; }}

    #CardTitle {{ font-size: 11pt; font-weight: 600; }}
    #StoreCardTitle {{ font-size: 14pt; font-weight: 600; }}
    #CardMeta {{ color: {c['muted']}; font-size: 8.5pt; }}
    #CardDesc {{ color: {c['text']}; }}
    QLabel#Badge {{ background: {c['warning']}; color: #111; border-radius: 8px; padding: 1px 8px; font-size: 8pt; font-weight: 600; }}
    QLabel#BadgeOk {{ background: {c['success']}; color: #0b1a10; border-radius: 8px; padding: 1px 8px; font-size: 8pt; font-weight: 600; }}
    QLabel#BadgeError {{ background: {c['danger']}; color: white; border-radius: 8px; padding: 1px 8px; font-size: 8pt; font-weight: 600; }}

    #LoginCard {{ background: {c['surface']}; border: 1px solid {c['border']}; border-radius: 14px; }}
    #ErrorLabel {{ color: {c['danger']}; }}
    """


def ads_stylesheet(c: dict[str, str] | None = None) -> str:
    """Stylesheet für das Docking-System - muss direkt am CDockManager gesetzt werden,
    da QtAds dort ein eigenes Stylesheet setzt, das sonst Vorrang hat."""
    c = c or current
    return f"""
    ads--CDockContainerWidget {{ background: {c['bg']}; }}
    ads--CDockAreaWidget {{ background: {c['bg']}; }}
    ads--CDockAreaTitleBar {{ background: {c['bg']}; border-bottom: 1px solid {c['border']}; }}
    ads--CDockWidgetTab {{ background: {c['bg']}; border: none; border-top: 2px solid transparent;
                           padding: 4px 6px 4px 8px; }}
    ads--CDockWidgetTab[activeTab="true"] {{ background: {c['surface']}; border-top: 2px solid {c['accent']}; }}
    /* Kein padding am Label: QtAds berechnet die Tab-Breite aus dem Text, Padding schneidet ihn sonst ab */
    ads--CDockWidgetTab QLabel {{ color: {c['muted']}; background: transparent; }}
    ads--CDockWidgetTab[activeTab="true"] QLabel {{ color: {c['text']}; }}
    ads--CDockWidget {{ background: {c['bg']}; }}
    ads--CDockSplitter::handle {{ background: {c['border']}; }}
    """
