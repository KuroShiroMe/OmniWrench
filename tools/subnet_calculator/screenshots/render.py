"""Screenshots für Store und Home (scripts/render_screenshots.py)."""


def render(shot):
    tool, _ = shot.create()
    tool.input.setText("10.20.0.0/16")
    tool.new_prefix.setValue(20)
    shot.save("overview")

    tool.input.setText("2001:db8:4f00::1/48")
    tool.new_prefix.setValue(52)
    shot.save("ipv6")
