"""KI-Dienste des Hauptprogramms für Tools (ToolContext.ai_services(), ab 0.9.0).

Ein KI-Tool wie das KI-Studio nutzt dieselben Verbindungen, dieselbe Datenablage (inkl. Verschlüsselung)
und dasselbe Chat-Widget wie die Chatleiste, statt sie nachzubauen.
"""

from __future__ import annotations

from typing import Callable

from omniwrench.ai import access
from omniwrench.ai.connections import ConnectionStore
from omniwrench.ai.storage import Storage


class AIServices:
    def __init__(self, window):
        self.window = window
        self.settings = window.settings
        self.vault = window.vault
        self.connections = ConnectionStore(window.settings, window.vault)
        self.storage = Storage(window.settings, window.vault)

    def chat_widget(self, system_extra: Callable[[], str] | None = None):
        """Chat-Widget wie die Chatleiste, eingebettet (ohne eigenen Verlauf/Projektauswahl).
        Steuerung: set_project(), open_thread(id, projekt), new_chat(), ask(); Signal threadSaved."""
        from .ai_panel import AIPanel
        return AIPanel(self.window, embedded=True, system_extra=system_extra)

    def open_options(self) -> None:
        self.window.open_app_settings(initial_tab="ai")

    def level(self, source: str, conn_id: str = "") -> int:
        return access.level(self.settings, source, conn_id)
