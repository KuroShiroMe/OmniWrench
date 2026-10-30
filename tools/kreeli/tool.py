"""Kreeli – Transkription: Live-Transkription von Mikrofon und Systemton mit Sprechererkennung und Zusammenfassung.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .transcript import TranscriptTab


class Kreeli(AITool):
    CLANK_KEYS = ("ts_*",)
    CLANK_DEFAULTS = {"ts_connection": "ts_stt", "ts_summary_connection": "ts_summary"}

    def make_page(self) -> QWidget:
        page = TranscriptTab(self)
        return page
