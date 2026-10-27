"""Screenshots für Store und Home (scripts/render_screenshots.py).

Statt WMI liefert das Fake-Backend aus scripts/dns_check (zwei Domänencontroller und ein DMZ-Server)
die Daten. Es importiert die Tool-Module als tools.ms_dns_extended.*; damit dieselben Klassen benutzt
werden wie in der geladenen Oberfläche, zeigen diese Namen auf die bereits geladenen Module.
"""

import importlib.util
import sys

DC1 = "dc01.corp.example"
DOM = "corp.example"
MODULES = ("dnsutil", "wmidns")


def _fake_backend(shot):
    pkg = sys.modules[shot.module("dnsutil").__name__.rpartition(".")[0]]
    sys.modules.setdefault("tools.ms_dns_extended", pkg)
    for name in MODULES:
        sys.modules[f"tools.ms_dns_extended.{name}"] = shot.module(name)
    # render.py läuft aus einer Kopie; shot.source ist der Tool-Ordner im Repository
    path = shot.source.parents[1] / "scripts" / "dns_check" / "fake_backend.py"
    spec = importlib.util.spec_from_file_location("dns_fake_backend", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.FakeBackend


def render(shot):
    shot.module("tool").MsDnsExtended.backend_factory = _fake_backend(shot)
    tool, _ = shot.create()
    tool.server.setCurrentText(DC1)
    tool.m_sso.setChecked(True)
    tool.auto_discover.setChecked(True)
    tool.auto_scan.setChecked(True)
    tool.check_page.probe.setChecked(True)
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "Anmeldung")
    shot.wait_until(lambda: DC1 in tool.scans, 30, "Prüfung")
    shot.wait(0.5)
    tool.log_view.clear()
    tool.log_view.parentWidget().parentWidget().setSizes([700, 70])  # Protokoll klein halten
    tool.show_page("overview")
    shot.save("overview")
    tool.open_zone(DC1, DOM)
    shot.wait_until(lambda: (DC1, DOM) in tool.tabs and not tool.runner.active, 20, "Zone")
    tool.log_view.clear()
    shot.save("zone")
    tool.show_page("check")
    shot.save("check")
    tool.show_page("events")
    shot.wait(0.8)
    shot.save("events")
