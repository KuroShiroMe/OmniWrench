"""Infobot – Dokumente: Dokumente mit einem Assistenten schreiben und als HTML, PDF oder ODT exportieren.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .documents import DocumentsTab


class Infobot(AITool):
    CLANK_KEYS = ()
    CLANK_DEFAULTS = {"doc_connection": "docs"}

    def make_page(self) -> QWidget:
        page = DocumentsTab(self)
        return page
