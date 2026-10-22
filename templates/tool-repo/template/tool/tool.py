"""__TOOL_NAME__ – Beispiel-Tool: löst einen Hostnamen auf und listet die Adressen.

Zeigt die wichtigsten Bausteine: Einstellungen lesen, Texte übersetzen, Arbeit im Hintergrund
(run_async) und Meldungen in der Statusleiste. Anleitung:
https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung
"""

from __future__ import annotations

import socket

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget

from omniwrench.sdk import ToolBase, run_async


def resolve(host: str, limit: int) -> list[str]:
    """Läuft im Hintergrund-Thread: hier keine Widgets anfassen."""
    infos = socket.getaddrinfo(host, None)
    addresses = sorted({info[4][0] for info in infos})
    return addresses[:limit]


class Tool(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        root = QWidget(parent)
        lay = QVBoxLayout(root)

        row = QHBoxLayout()
        self.host = QLineEdit(self.context.settings.get("default_host") or "",
                              placeholderText=tr("ui.host_placeholder", "Host name"))
        self.host.returnPressed.connect(self._run)
        row.addWidget(self.host, 1)
        self.button = QPushButton(tr("ui.run", "Resolve"))
        self.button.clicked.connect(self._run)
        row.addWidget(self.button)
        lay.addLayout(row)

        self.status = QLabel()
        lay.addWidget(self.status)
        self.results = QListWidget()
        lay.addWidget(self.results, 1)
        return root

    def _run(self) -> None:
        host = self.host.text().strip()
        if not host:
            return
        self.button.setEnabled(False)
        self.status.setText(self.context.tr("ui.running", "Resolving …"))
        limit = int(self.context.settings.get("max_results", 50))
        run_async(lambda: resolve(host, limit), self._done, self._failed)

    def _done(self, addresses: list[str]) -> None:
        self.button.setEnabled(True)
        self.results.clear()
        self.results.addItems(addresses)
        self.status.setText(self.context.tr("ui.found", "{count} address(es)", count=len(addresses)))
        self.context.notify(self.context.tr("ui.found", "{count} address(es)", count=len(addresses)))

    def _failed(self, error: str) -> None:
        self.button.setEnabled(True)
        self.status.setText(self.context.tr("ui.error", "Error: {error}", error=error))

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "default_host" in changed_keys and not self.host.text():
            self.host.setText(self.context.settings.get("default_host") or "")
