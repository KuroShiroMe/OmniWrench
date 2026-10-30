"""Screenshots für Store und Home (scripts/render_screenshots.py) - Fake-Assistent statt echter Anbieter
(gemeinsamer Aufbau in scripts/ai_shots.py)."""

from __future__ import annotations

from ai_shots import open_tool


def render(shot):
    _win, tool = open_tool(shot)
    m = tool.page
    m.save_servers([
        {"id": "fs", "name": "Filesystem (docs share)", "transport": "stdio", "command": "npx",
         "args": "-y @modelcontextprotocol/server-filesystem D:/Docs", "enabled": True, "trusted": True},
        {"id": "tickets", "name": "Ticket system", "transport": "http", "url": "https://tickets.contoso.example/mcp",
         "enabled": True, "trusted": False},
    ])
    m.status = {"fs": {"state": "ok", "version": "2026-07-28"}, "tickets": {"state": "ok", "version": "2025-11-25"}}
    m.registered = {"fs": ["read_file", "list_directory", "search_files"], "tickets": ["find_ticket", "add_comment"]}
    m.render()
    shot.save("mcp", tool.root)
