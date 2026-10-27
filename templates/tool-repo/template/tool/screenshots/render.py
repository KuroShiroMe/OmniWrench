"""Screenshots für Store und Home: python scripts/screenshots.py tools/__TOOL_FOLDER__

render(shot) baut die Oberfläche mit Beispieldaten auf und speichert jedes Bild, das in tool.json unter
"screenshots" steht (shot.save("main") -> screenshots/main.png). Netz- und Systemzugriffe durch feste
Beispielwerte ersetzen: Die Bilder sollen immer gleich aussehen und keine echten Namen zeigen.
Anleitung: https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung-Paketformat#screenshots
"""


def render(shot):
    shot.module("tool").resolve = lambda host, limit: [
        "10.20.1.15", "10.20.1.16", "2001:db8:20:1::15", "2001:db8:20:1::16"][:limit]
    tool, _ = shot.create()
    tool.host.setText("app01.contoso.local")
    tool._run()
    shot.wait_until(lambda: tool.results.count() > 0, 10, "Ergebnis")
    shot.save("main")
