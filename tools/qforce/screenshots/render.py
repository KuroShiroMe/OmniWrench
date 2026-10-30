"""Screenshots für Store und Home (scripts/render_screenshots.py) - Fake-Assistent statt echter Anbieter
(gemeinsamer Aufbau in scripts/ai_shots.py)."""

from __future__ import annotations

import time

from ai_shots import GROUP, open_tool


def render(shot):
    _win, tool = open_tool(shot)
    g = tool.page
    now = int(time.time())
    parts = [{"id": f"p{i}", "name": n, "connection": "local", "role": ""} for i, (n, _col, _text) in enumerate(GROUP)]
    msgs = [{"role": "user", "content": "Plan the migration of 400 clients to Windows 12 – risks and order.",
             "ts": now - 300}]
    for i, (n, _col, text) in enumerate(GROUP):
        msgs.append({"role": "assistant", "participant": f"p{i}", "name": n, "content": text, "ts": now - 240 + i * 40,
                     "agree": i == 1})
    g.thread = {"format": 1, "kind": "group", "id": "shot", "title": "Windows 12 migration", "created": now,
                "updated": now, "topic": msgs[0]["content"], "participants": parts, "options": {},
                "messages": msgs, "usage": {}, "state": {}}
    g._show_setup(False)
    g.render()
    shot.save("group", tool.root)
