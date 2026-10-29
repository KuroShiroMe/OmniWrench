"""Orvus – Zeitpläne: Fragen zu festen Zeiten an einen Assistenten stellen (einmalig, täglich, wöchentlich, alle N Stunden).

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .schedule import ScheduleTab


class Orvus(AITool):
    CLANK_KEYS = ("schedules",)
    CLANK_DEFAULTS = {}

    def make_page(self) -> QWidget:
        page = ScheduleTab(self)
        return page
