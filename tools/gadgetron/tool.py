"""Gadgetron – MCP: MCP-Server anbinden und OmniWrench anderen KI-Programmen als MCP-Server anbieten.

Teil der KI-Tools (Kategorie „KI-Tools“), gebaut mit omniwrench.ui.ai_kit.AITool. Braucht OmniWrench 0.9.0 oder
neuer mit KI-Assistenten (ToolContext.ai_services).
"""

from __future__ import annotations

from PySide6.QtWidgets import QWidget

from omniwrench.ui.ai_kit import AITool

from .mcptab import MCPTab


class Gadgetron(AITool):
    CLANK_KEYS = ("mcp_*",)
    CLANK_DEFAULTS = {}

    def make_page(self) -> QWidget:
        page = MCPTab(self)
        return page

    def take_over_clank(self, old: dict) -> None:
        """Token des MCP-Servers und der angebundenen Server aus dem Tresorbereich von Clank übernehmen."""
        from omniwrench.ai import mcp
        keys = ["mcp_server_token"] + [mcp.secret_key(s["id"]) for s in old.get("mcp_servers") or []
                                       if isinstance(s, dict) and s.get("id")]
        for key in keys:
            value = self.clank_secret(key)
            if value and not self.context.secrets.get(key):
                self.context.secrets.set(key, value)
