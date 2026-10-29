"""Q-Force – Gruppenchat: Mehrere Assistenten besprechen ein Thema reihum, mit Bremsen und Zusammenfassung.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .grouptab import GroupTab


class QForce(AITool):
    CLANK_KEYS = ("group_options",)
    CLANK_DEFAULTS = {}

    def make_page(self) -> QWidget:
        page = GroupTab(self)
        return page
