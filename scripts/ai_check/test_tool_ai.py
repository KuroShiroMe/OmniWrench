"""KI-Funktionen der Tools ohne Windows prüfen (Fake-Backends der Screenshots).

    python scripts/ai_check/test_tool_ai.py

DHCP/DNS: Anmeldung, Funktionen registriert, Lesen (Status, Übersicht, Scope/Zone, Suche), Ändern über den
Runner des Tools, KI-Zugriff aus dem Favoriten (Stufe/Verfremdung bis zum Abmelden), Kontextmenü-Text,
Entfernen beim Schließen. NetProbe/IconForge: Funktionen vorhanden und lesbar.
"""

from __future__ import annotations

import shutil
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, Shot-Hilfen)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from omniwrench.ai import access, functions  # noqa: E402
from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.manifest import ToolManifest  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402
from omniwrench.ui.workers import call_in_gui  # noqa: E402

OK = 0


def check(cond, text):
    global OK
    if not cond:
        raise AssertionError(text)
    OK += 1


def place(manager, name: str) -> rs.Shot:
    source = ROOT / "tools" / name
    manifest = ToolManifest.load(source)
    target = paths.TOOLS_DIR / manifest.id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "_lib", "*.pyc", "*.png"))
    manager.refresh()
    return rs.Shot(manager, manifest.id, source, "de")


def call(shot, name: str, args: dict | None = None, timeout: float = 30):
    """Handler wie der Chat im Hintergrund ausführen, GUI-Thread läuft weiter."""
    fn = functions.get(name)
    check(fn is not None, f"Funktion {name} registriert")
    ctx = functions.CallContext(in_gui=call_in_gui, level=4)
    box: dict = {}

    def run():
        try:
            box["value"] = fn.handler(args or {}, ctx)
        except Exception as e:  # noqa: BLE001
            box["error"] = e
    t = threading.Thread(target=run, daemon=True)
    t.start()
    shot.wait_until(lambda: not t.is_alive(), timeout, f"Funktion {name}")
    if "error" in box:
        raise box["error"]
    return box["value"]


def names(prefix: str) -> set[str]:
    return {f.name for f in functions.all_functions() if f.name.startswith(prefix)}


def test_dhcp(manager):
    shot = place(manager, "ms_dhcp_extended")
    render = manager._import_module(manager.get(shot.tool_id), "screenshots.render")
    tool_mod = shot.module("tool")
    tool_mod.MsDhcpExtended.backend_factory = render.FakeBackend
    shot.settings.set("auto_refresh", 0)
    tool, _ = shot.create()
    check(names("dhcp_") >= {"dhcp_status", "dhcp_overview", "dhcp_scope", "dhcp_find_client", "dhcp_findings",
                             "dhcp_add_reservation", "dhcp_remove_reservation"}, f"DHCP-Funktionen {names('dhcp_')}")
    check(functions.get("dhcp_add_reservation").confirm and functions.get("dhcp_add_reservation").level == 4,
          "Reservierung braucht Bestätigung")
    check(call(shot, "dhcp_status") == {"connected": False}, "Status vor Anmeldung")
    # KI-Zugriff aus der Anmeldemaske (Favorit) gilt erst nach der Anmeldung
    check(tool.ai_row.available, "KI-Zeile sichtbar")
    tool.ai_row.set_value({"level": 4, "pseudo": False})
    check(tool.fav_capture()["ai"] == {"level": 4, "pseudo": False}, "Favorit enthält KI-Zugriff")
    tool.server.setEditText(render.PRIMARY)
    tool.m_sso.setChecked(True)
    tool.auto_partner.setChecked(False)
    tool.auto_scan.setChecked(True)
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "DHCP-Anmeldung")
    shot.wait_until(lambda: tool.scan is not None, 30, "DHCP-Prüfung")
    settings = AppSettings()
    check(access.level(settings, shot.tool_id) == 4 and not access.pseudo_enabled(settings, shot.tool_id),
          "Stufe/Verfremdung aus der Anmeldemaske")
    st = call(shot, "dhcp_status")
    check(st["connected"] and st["server"] == render.PRIMARY and st["ipv4_scopes"] > 0, f"Status {st}")
    ov = call(shot, "dhcp_overview")
    check(ov["total"] == st["ipv4_scopes"] + st["ipv6_scopes"] and ov["check_done"], "Übersicht")
    sid = next(s["id"] for s in ov["items"] if ":" not in s["id"])
    sc = call(shot, "dhcp_scope", {"scope_id": sid})
    check(sc["scope"]["id"] == sid and sc["reservations"] and "items" in sc["leases"], "Scope-Details")
    found = call(shot, "dhcp_findings")
    check(found["check_done"] and found["total"] >= 0, "Befunde")
    res = sc["reservations"][0]
    hits = call(shot, "dhcp_find_client", {"query": res["ip"]})
    check(any(h["ip"] == res["ip"] for h in hits["items"]), f"Client-Suche {hits}")
    mask = next(s for s in render.DATA["scopes"] if s["ScopeId"] == sid)["SubnetMask"]
    import ipaddress
    free = str(ipaddress.ip_network(f"{sid}/{mask}").network_address + 250)
    out = call(shot, "dhcp_add_reservation", {"scope_id": sid, "ip": free, "client_id": "00-15-5d-01-02-03",
                                              "name": "ki-test"})
    check(out["ok"] and out["reservation"]["cid"] == "00-15-5d-01-02-03", f"Reservierung angelegt {out}")
    try:
        call(shot, "dhcp_add_reservation", {"scope_id": sid, "ip": "192.0.2.1", "client_id": "00-11-22-33-44-55"})
        check(False, "Adresse außerhalb des Scopes abgelehnt")
    except Exception as e:  # noqa: BLE001
        check("not an address" in str(e), f"Fehlertext {e}")
    out = call(shot, "dhcp_remove_reservation", {"scope_id": sid, "ip": free})
    check(out["ok"], "Reservierung entfernt")
    # Kontextmenü-Text der Tabellen
    grid = tool.overview.grid if hasattr(tool.overview, "grid") else None
    if grid is not None and grid.rowCount():
        grid.selectRow(0)
        check(sid in grid.selection_text() or grid.selection_text(), "Text der markierten Zeile")
    # Abmelden: Vorgabe weg
    tool.run(tool.logout_flow())
    shot.wait_until(lambda: tool.stack.currentIndex() == 0 and not tool.runner.active, 30, "DHCP-Abmeldung")
    check(access.runtime(shot.tool_id) == {}, "Vorgabe nach Abmelden entfernt")
    instance = shot.instances[-1]
    functions.unregister_owner(instance.context)
    check(not names("dhcp_"), "Funktionen beim Schließen entfernt")
    shot.close()


def test_dns(manager):
    shot = place(manager, "ms_dns_extended")
    render = manager._import_module(manager.get(shot.tool_id), "screenshots.render")
    tool_mod = shot.module("tool")
    tool_mod.MsDnsExtended.backend_factory = render._fake_backend(shot)
    shot.settings.set("auto_refresh", 0)
    tool, _ = shot.create()
    check(names("dns_") >= {"dns_status", "dns_overview", "dns_records", "dns_search", "dns_add_record",
                            "dns_delete_record"}, f"DNS-Funktionen {names('dns_')}")
    tool.server.setEditText(render.DC1)
    tool.m_sso.setChecked(True)
    tool.auto_discover.setChecked(False)
    tool.auto_scan.setChecked(False)
    tool.ai_row.set_value({"level": 3})
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "DNS-Anmeldung")
    check(access.level(AppSettings(), shot.tool_id) == 3, "Stufe aus der Anmeldemaske")
    st = call(shot, "dns_status")
    check(st["connected"] and render.DC1 in st["servers"], f"Status {st}")
    ov = call(shot, "dns_overview")
    zone = next(z["zone"] for z in ov["items"] if z["zone"] == render.DOM)
    recs = call(shot, "dns_records", {"zone": zone})
    check(recs["total"] > 0, "Einträge")
    a = next(r for r in recs["items"] if r["type"] == "A")
    hits = call(shot, "dns_search", {"query": a["value"]})
    check(any(h["name"] == a["name"] for h in hits["items"]), "Suche nach IP")
    out = call(shot, "dns_add_record", {"zone": zone, "name": "ki-test", "type": "A", "value": "10.99.0.5"})
    check(out["ok"] and out["created"]["name"] == f"ki-test.{zone}", f"Eintrag angelegt {out}")
    out = call(shot, "dns_delete_record", {"zone": zone, "name": "ki-test", "type": "A", "value": "10.99.0.5"})
    check(out["ok"], f"Eintrag gelöscht {out}")
    try:
        call(shot, "dns_add_record", {"zone": zone, "name": "x", "type": "A", "value": "kein-ip"})
        check(False, "ungültige IP abgelehnt")
    except Exception:  # noqa: BLE001
        check(True, "ungültige IP abgelehnt")
    shot.close()


def test_simple(manager):
    shot = place(manager, "netprobe")
    shot.create()
    res = call(shot, "netprobe_results")
    check(res["total"] == 0 and functions.get("netprobe_start").confirm, "NetProbe")
    shot.close()
    shot = place(manager, "iconforge")
    shot.create()
    packs = call(shot, "iconforge_packs")
    check(isinstance(packs, list), "IconForge-Pakete")
    if packs:
        hits = call(shot, "iconforge_search", {"query": "server"})
        check(isinstance(hits["items"], list), "IconForge-Suche")
    shot.close()


def main() -> int:
    paths.ensure_dirs()
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Yes
    for kind in ("warning", "critical", "information"):
        setattr(QMessageBox, kind, staticmethod(lambda *a, **k: QMessageBox.StandardButton.Ok))
    QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    apply_language(app, "de")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="ai-check")
    credentials.init(vault)
    manager = ToolManager(vault)
    test_dhcp(manager)
    test_dns(manager)
    test_simple(manager)
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
