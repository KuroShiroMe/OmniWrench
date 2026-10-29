"""Screenshots für Store und Home (scripts/render_screenshots.py) - Fake-Assistent statt echter Anbieter
(gemeinsamer Aufbau in scripts/ai_shots.py)."""

from __future__ import annotations

from ai_shots import QUESTION, open_tool


def render(shot):
    _win, tool = open_tool(shot)
    tool.panel.ask(QUESTION)
    shot.wait_until(lambda: not tool.panel._running, what="Antwort des Fake-Assistenten")
    shot.wait(0.5)
    shot.save("chat", tool.root)
