"""Screenshots für Store und Home (scripts/render_screenshots.py) - Fake-Assistent statt echter Anbieter
(gemeinsamer Aufbau in scripts/ai_shots.py)."""

from __future__ import annotations

from ai_shots import IMAGES, open_tool


def render(shot):
    _win, tool = open_tool(shot)
    img = tool.page
    img.refresh()
    img.reload_gallery()
    img.prompt.setPlainText(IMAGES[0][0])
    if img.gallery.count():
        img.gallery.setCurrentRow(0)
        img._preview(img.gallery.item(0))
    shot.save("images", tool.root)
