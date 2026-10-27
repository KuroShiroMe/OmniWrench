"""Screenshots für Store und Home (scripts/render_screenshots.py) - nur die eingebaute Lucide-Bibliothek."""


def _pick(shot, tool, name):
    tool.search.setText(name)
    tool._apply_filter()
    for row in range(tool.proxy.rowCount()):
        index = tool.proxy.index(row, 0)
        if index.data(tool.model.REF).name == name:
            tool.view.setCurrentIndex(index)
            break
    shot.wait(0.3)


def render(shot):
    tool, _ = shot.create()
    shot.wait(0.5)
    _pick(shot, tool, "server")
    tool.search.setText("server")
    tool._apply_filter()
    shot.save("browse")

    _pick(shot, tool, "shield-check")
    tool.color_btn.set_color("#ffffff")
    tool.bg.setCurrentIndex(tool.bg.findData("circle"))
    tool.bg_color.set_color("#10b981")
    tool.stroke.setValue(2.5)
    tool._refresh_preview()
    tool.search.setText("shield")
    tool._apply_filter()
    shot.save("style")
