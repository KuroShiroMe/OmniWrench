"""Pixelizer – Bilder: Bilder mit den verbundenen Bild-Anbietern erzeugen, mit Referenzbildern und Galerie.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .images import ImagesTab


class Pixelizer(AITool):
    CLANK_KEYS = ("image_models",)
    CLANK_DEFAULTS = {"image_connection": "image"}

    def make_page(self) -> QWidget:
        page = ImagesTab(self)
        page.to_chat.connect(self.services.send_file_to_chat)
        return page
