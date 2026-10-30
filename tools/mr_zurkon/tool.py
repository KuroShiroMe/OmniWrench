"""Mr. Zurkon – Sprachassistent: Mit dem Assistenten sprechen: Weckwort offline, Spracherkennung und vorgelesene Antworten.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .voice import VoiceTab


class MrZurkon(AITool):
    CLANK_KEYS = ("va_*",)
    CLANK_DEFAULTS = {"va_stt": "va_stt", "va_tts": "va_tts"}

    def make_page(self) -> QWidget:
        page = VoiceTab(self)
        return page
