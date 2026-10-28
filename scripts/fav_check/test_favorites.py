"""Server-Favoriten der Tools MS DHCP / MS DNS Extended Management ohne Windows prüfen.

    python scripts/fav_check/test_favorites.py

Speicher (Zusammenführen, fremde Abschnitte wie "ai" bleiben, Kopien), Anmeldemaske <-> Favorit,
Verweis auf gespeicherte Anmeldedaten, Wiederherstellen beim Start und die Anmeldung über einen
Favoriten mit den Fake-Backends der Screenshots (DHCP: Ansicht IPv6, DNS: weitere Server + DHCP-Abgleich).
"""

from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scripts import render_screenshots as rs  # noqa: E402  (Temp-Home, offscreen, Shot-Hilfen)

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.manifest import ToolManifest  # noqa: E402
from omniwrench.core.tool_manager import ToolManager  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

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


class FakeSettings:
    def __init__(self):
        self.values = {}

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


def test_store(fv):
    st = FakeSettings()
    store = fv.FavoriteStore(st)
    check(store.items() == [] and store.last() == "", "leer")
    a = store.save({"name": "RZ", "server": "rz-dhcp01", "login": {"mode": "manual", "user": "CORP\\adm"},
                    "options": {"auto_scan": False}})
    b = store.save({"name": "Lab", "server": "lab01"})
    check([i["name"] for i in store.items()] == ["RZ", "Lab"], "Reihenfolge")
    check(store.get(b)["login"]["mode"] == "sso" and store.get(b)["ai"] == {}, "Standardwerte")
    # fremde Abschnitte und Schlüssel bleiben beim Überschreiben erhalten
    store.set_section(a, "ai", {"level": 2, "pseudo": True})
    raw = st.values[fv.KEY]
    raw["items"][0]["future"] = {"x": 1}
    raw["items"][0]["options"]["later"] = "keep"
    st.values[fv.KEY] = raw
    store.save({"id": a, "server": "rz-dhcp02", "login": {"mode": "sso"}, "options": {"auto_scan": True}})
    fa = store.get(a)
    check(fa["server"] == "rz-dhcp02" and fa["login"] == {"mode": "sso"}, "login ersetzt")
    check(fa["ai"] == {"level": 2, "pseudo": True} and store.section(a, "ai")["level"] == 2, "ai bleibt")
    check(fa["future"] == {"x": 1} and fa["options"] == {"auto_scan": True, "later": "keep"}, "Fremdschlüssel bleiben")
    # Kopien: Ändern des Ergebnisses ändert den Speicher nicht
    fa["name"] = "kaputt"
    store.items()[0]["options"]["auto_scan"] = False
    check(store.get(a)["name"] == "RZ" and store.get(a)["options"]["auto_scan"] is True, "Kopien")
    check(store.find_name(" rz ")["id"] == a and store.find_name("x") is None, "find_name")
    store.move(b, -1)
    check([i["id"] for i in store.items()] == [b, a], "move")
    store.move(b, -5)
    check([i["id"] for i in store.items()] == [b, a], "move Grenze")
    store.set_last(a)
    store.remove(a)
    check(store.last() == "" and [i["id"] for i in store.items()] == [b], "remove + last")
    # kaputte/alte Werte
    st.values[fv.KEY] = {"items": [{"id": "f-1", "server": "s", "login": {"mode": "bogus"}, "options": None}, {"x": 1}]}
    it = store.items()
    check(len(it) == 1 and it[0]["name"] == "s" and it[0]["login"]["mode"] == "sso" and it[0]["options"] == {},
          "Normalisierung")
    st.values[fv.KEY] = ["unsinn"]
    check(store.items() == [], "unbrauchbarer Wert")
    # Verweise auf Anmeldedaten, nie das Passwort
    items = [{"name": "A", "username": "u1", "password": "geheim"}, {"name": "B", "username": "u2", "ref": "local:42"}]
    check(fv.cred_key(items[0]) == {"name": "A", "username": "u1"}, "cred_key manuell ohne Passwort")
    check(fv.cred_key(items[1]) == {"ref": "local:42"}, "cred_key Verweis")
    check(fv.match_cred(items, {"ref": "local:42"}) == 1 and fv.match_cred(items, {"name": "A", "username": "u1"}) == 0,
          "match_cred")
    check(fv.match_cred(items, {"ref": "local:1"}) == -1 and fv.match_cred(items, {}) == -1, "match_cred fehlt")
    opts = fv._options_from({"opt.servers": "dc02, DC02;dmz-dns01\n", "opt.dhcp_server": "dhcp01"},
                            [{"key": "servers", "type": "list"}, {"key": "dhcp_server"}])
    check(opts == {"servers": ["dc02", "dmz-dns01"], "dhcp_server": "dhcp01"}, "Listenfeld")


def fake_dialog(name, extra=None):
    def ask(parent, tr, store, fav, extra_fields, title):
        return {"name": name, "server": fav["server"], "note": "Notiz", "options": dict(extra or {})}
    return ask


def test_dhcp(manager):
    shot = place(manager, "ms_dhcp_extended")
    render = manager._import_module(manager.get(shot.tool_id), "screenshots.render")
    tool_mod = shot.module("tool")
    fv = shot.module("favorites")
    test_store(fv)
    tool_mod.MsDhcpExtended.backend_factory = render.FakeBackend
    shot.settings.set("auto_refresh", 0)
    shot.settings.set("credential", {"items": [{"name": "DHCP-Admin", "username": "CORP\\dhcpadm", "password": "x"},
                                               {"name": "Zweit", "username": "CORP\\other", "password": "y"}],
                                     "selected": 0})
    tool, _ = shot.create()
    check(tool.fav_bar.current() is None and tool.fav_bar.combo.count() == 1, "ohne Favoriten")
    # Favorit aus der Anmeldemaske: gespeicherte Anmeldedaten (zweiter Eintrag)
    tool.server.setEditText(render.PRIMARY)
    tool.m_vault.setChecked(True)
    tool.cred_field.combo.setCurrentIndex(1)
    tool.auto_partner.setChecked(False)
    tool.auto_scan.setChecked(False)
    fv.edit_dialog = fake_dialog("Zentrale")
    fid = tool.fav_bar.save_new()
    fav = tool.favs.get(fid)
    check(fav["name"] == "Zentrale" and fav["server"] == render.PRIMARY and fav["note"] == "Notiz", "gespeichert")
    check(fav["login"] == {"mode": "vault", "cred": {"name": "Zweit", "username": "CORP\\other"}}, "Verweis gespeichert")
    check("password" not in str(fav) and "y" not in fav["login"]["cred"].values(), "kein Passwort")
    check(fav["options"] == {"auto_partner": False, "auto_scan": False, "family": 4}, "Optionen")
    check(tool.fav_bar.current_id() == fid and tool.favs.last() == fid, "ausgewählt")
    # zweiter Favorit: andere Anmeldedaten
    tool.fav_bar.select("")
    tool.server.setEditText("dhcp-lab")
    tool.m_manual.setChecked(True)
    tool.user.setText("LAB\\admin")
    tool.password.setText("geheim")
    tool.auto_scan.setChecked(True)
    fv.edit_dialog = fake_dialog("Labor")
    fid2 = tool.fav_bar.save_new()
    check(tool.favs.get(fid2)["login"] == {"mode": "manual", "user": "LAB\\admin"}, "manuell ohne Passwort")
    # Wählen füllt die Maske
    tool.fav_bar.select(fid)
    check(tool.server.currentText() == render.PRIMARY and tool.m_vault.isChecked(), "Server + Modus")
    check(tool.cred_field.combo.currentIndex() == 1 and not tool.auto_partner.isChecked(), "Zugang + Partner")
    tool.fav_bar.select(fid2)
    check(tool.m_manual.isChecked() and tool.user.text() == "LAB\\admin" and tool.password.text() == "", "manuell")
    # Server von Hand geändert -> kein Favorit mehr
    tool.server.setEditText("anderer")
    check(tool.fav_bar.current() is None and tool.favs.last() == "", "Handänderung")
    # Zugang gelöscht -> Hinweis
    tool.favs.save({"id": fid2, "login": {"mode": "vault", "cred": {"ref": "local:weg"}}})
    tool.fav_bar.refresh()
    tool.fav_bar.select(fid2)
    check(tool.login_status.text() == tool.tr("fav.cred_missing"), "Zugang fehlt")
    # Überschreiben behält ai und Notiz
    tool.favs.set_section(fid, "ai", {"level": 1})
    tool.fav_bar.select(fid)
    tool.auto_partner.setChecked(True)
    tool.fav_bar.overwrite()
    fav = tool.favs.get(fid)
    check(fav["options"]["auto_partner"] is True and fav["ai"] == {"level": 1} and fav["note"] == "Notiz", "überschreiben")
    # Anmeldung über Favorit stellt die gespeicherte Ansicht (IPv6) ein
    tool.favs.save({"id": fid, "login": {"mode": "sso"}, "options": {"family": 6, "auto_scan": False}})
    tool.fav_bar.refresh()
    tool.fav_bar.select("")
    tool.fav_bar.select(fid)
    check(tool.m_sso.isChecked(), "sso")
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "DHCP-Anmeldung")
    check(tool.family == 6, "Ansicht IPv6 aus dem Favoriten")
    # neue Instanz: zuletzt gewählter Favorit ist wieder da
    tool2, _ = shot.create()
    check(tool2.fav_bar.current_id() == fid and tool2.server.currentText() == render.PRIMARY, "wiederhergestellt")
    shot.close()


def test_dns(manager):
    shot = place(manager, "ms_dns_extended")
    render = manager._import_module(manager.get(shot.tool_id), "screenshots.render")
    tool_mod = shot.module("tool")
    fv = shot.module("favorites")
    tool_mod.MsDnsExtended.backend_factory = render._fake_backend(shot)
    shot.settings.set("auto_refresh", 0)
    tool, _ = shot.create()
    tool.server.setEditText(render.DC1)
    tool.m_sso.setChecked(True)
    tool.auto_discover.setChecked(False)
    tool.auto_scan.setChecked(False)
    fv.edit_dialog = fake_dialog("Domäne", {"servers": ["DMZ-DNS01", render.DC1], "dhcp_server": "dhcp01.corp.example"})
    fid = tool.fav_bar.save_new()
    fav = tool.favs.get(fid)
    check(fav["options"] == {"auto_discover": False, "auto_scan": False, "servers": ["DMZ-DNS01", render.DC1],
                             "dhcp_server": "dhcp01.corp.example"}, "DNS-Optionen")
    # Überschreiben aus der Maske behält die Dialog-Optionen
    tool.fav_bar.overwrite()
    check(tool.favs.get(fid)["options"]["servers"] == ["DMZ-DNS01", render.DC1], "Dialog-Optionen bleiben")
    tool._login_clicked()
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "DNS-Anmeldung")
    check(set(tool.svc.servers) == {render.DC1, "dmz-dns01"}, f"weitere Server: {list(tool.svc.servers)}")
    check(tool.svc.dhcp_server == "dhcp01.corp.example", "DHCP-Server aus dem Favoriten")
    shot.close()


def main() -> int:
    paths.ensure_dirs()
    QMessageBox.exec = lambda self: QMessageBox.StandardButton.Yes   # Rückfragen (Überschreiben) bestätigen
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    from omniwrench.app import apply_language
    apply_language(app, "de")
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="fav-check")
    credentials.init(vault)
    manager = ToolManager(vault)
    check(filecmp.cmp(ROOT / "tools/ms_dhcp_extended/favorites.py", ROOT / "tools/ms_dns_extended/favorites.py",
                      shallow=False), "favorites.py in beiden Tools gleich")
    test_dhcp(manager)
    test_dns(manager)
    print(f"OK: {OK} Prüfungen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
