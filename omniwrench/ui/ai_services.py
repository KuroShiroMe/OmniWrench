"""KI-Dienste des Hauptprogramms für Tools (ToolContext.ai_services(), ab 0.9.0).

Ein KI-Tool wie Clank nutzt dieselben Verbindungen, dieselbe Datenablage (inkl. Verschlüsselung)
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

    # --- Standard-Assistent je Funktion (Einstellungen › KI-Assistenten › Funktionen) ---------------------
    def default(self, function: str) -> str:
        """Gemerkter Assistent (Verbindungs-ID oder Offline-Kennung) für eine Funktion, z. B. "image", "tts"."""
        from omniwrench.ai import defaults
        return defaults.get(self.settings, function)

    def set_default(self, function: str, value: str) -> None:
        from omniwrench.ai import defaults
        defaults.set(self.settings, function, value)

    # --- Übergabe an die Chatleiste ------------------------------------------------------------------------
    def send_to_chat(self, name: str, text: str) -> None:
        """Text als Anhang in die Chatleiste legen und sie öffnen (z. B. Dokument, Mitschrift)."""
        self.window.toggle_assistant(True)
        self.window.ai_panel.add_text_attachment(name, text)
        self.window.ai_panel.focus_input()

    def send_file_to_chat(self, path) -> None:
        """Datei (z. B. ein Bild) an die Chatleiste anhängen und sie öffnen."""
        from pathlib import Path
        self.window.toggle_assistant(True)
        self.window.ai_panel.add_attachment(Path(path))
        self.window.ai_panel.focus_input()

    def open_thread(self, thread_id: str, project: str = "") -> None:
        """Einen gespeicherten Chat in der Chatleiste öffnen."""
        self.window.toggle_assistant(True)
        self.window.ai_panel.open_thread(thread_id, project)

    def open_defaults(self) -> None:
        """Einstellungen › KI-Assistenten › Funktionen öffnen."""
        self.window.open_app_settings(initial_tab="ai_defaults")
