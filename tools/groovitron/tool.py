"""Groovitron – Musik: Musik mit den verbundenen Anbietern erzeugen, abspielen und mit ffmpeg bearbeiten.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool
from omniwrench.ui.ai_media import MediaTab


class Groovitron(AITool):
    CLANK_KEYS = ("music_models", "ffmpeg_path")
    CLANK_DEFAULTS = {"music_connection": "music"}

    def make_page(self) -> QWidget:
        page = MediaTab(self, "music")
        return page
