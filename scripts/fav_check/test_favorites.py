"""Server-Favoriten der Tools MS DHCP / MS DNS Extended Management ohne Windows prüfen.

    python scripts/fav_check/test_favorites.py

Speicher (Zusammenführen, fremde Abschnitte wie "ai" bleiben, Kopien), Anmeldemaske <-> Favorit,
Verweis auf gespeicherte Anmeldedaten, Wiederherstellen beim Start und die Anmeldung über einen
Favoriten mit den Fake-Backends der Screenshots (DHCP: Ansicht IPv6, DNS: weitere Server + DHCP-Abgleich).
"""

from __future__ import annotations

import filecmp
import json
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


class FakeSecrets(FakeSettings):
    def __init__(self):
        super().__init__()
        self.lost = set()

    def delete(self, key):
        self.values.pop(key, None)
        self.lost.discard(key)

    def is_lost(self, key):
        return key in self.lost


def test_store(fv):
    st, sec = FakeSettings(), FakeSecrets()
    store = fv.FavoriteStore(st, sec)
    check(store.items() == [] and store.folders() == [] and store.last() == "", "leer")
    a = store.save({"name": "RZ", "server": "rz-dhcp01", "login": {"mode": "stored", "user": "CORP\\adm"},
                    "password": "geheim", "options": {"auto_scan": False}})
    b = store.save({"name": "Lab", "server": "lab01"})
    check([i["name"] for i in store.items()] == ["RZ", "Lab"], "Reihenfolge")
    check(store.get(b)["login"]["mode"] == "sso" and store.get(b)["ai"] == {} and store.get(b)["folder"] == "",
          "Standardwerte")
    # Kennwort nur im Tresor
    check("geheim" not in str(st.values) and store.password(a) == "geheim", "Kennwort im Tresor")
    store.save({"id": a, "note": "x"})
    check(store.password(a) == "geheim", "Kennwort bleibt bei Änderung ohne password")
    store.save({"id": a, "login": {"mode": "stored", "user": "CORP\\adm"}, "password": "neu"})
    check(store.password(a) == "neu", "Kennwort geändert")
    sec.lost.add(f"fav:{a}")
    check(store.password_lost(a), "verloren")
    sec.lost.discard(f"fav:{a}")
    # fremde Abschnitte und Schlüssel bleiben beim Überschreiben erhalten
    store.set_section(a, "ai", {"level": 2, "pseudo": True})
    raw = st.values[fv.KEY]
    raw["items"][0]["future"] = {"x": 1}
    raw["items"][0]["options"]["later"] = "keep"
    st.values[fv.KEY] = raw
    store.save({"id": a, "server": "rz-dhcp02", "login": {"mode": "sso"}, "options": {"auto_scan": True}})
    fa = store.get(a)
    check(fa["server"] == "rz-dhcp02" and fa["login"] == {"mode": "sso"}, "login ersetzt")
    check(store.password(a) is None and f"fav:{a}" not in sec.values, "Kennwort weg bei anderer Anmeldeart")
    check(fa["ai"] == {"level": 2, "pseudo": True} and store.section(a, "ai")["level"] == 2, "ai bleibt")
    check(fa["future"] == {"x": 1} and fa["options"] == {"auto_scan": True, "later": "keep"}, "Fremdschlüssel bleiben")
    fa["name"] = "kaputt"
    store.items()[0]["options"]["auto_scan"] = False
    check(store.get(a)["name"] == "RZ" and store.get(a)["options"]["auto_scan"] is True, "Kopien")
    # Ordner
    ka = store.add_folder("Kunde A")
    st1 = store.add_folder("Standort 1", ka)
    kb = store.add_folder("Kunde B", "gibtsnicht")
    check(store.folder_path(st1) == "Kunde A / Standort 1", "Pfad")
    check(next(f for f in store.folders() if f["id"] == kb)["parent"] == "", "unbekannter Elternordner")
    check(store.descendants(ka) == {st1}, "Unterordner")
    store.save({"id": b, "folder": st1})
    store.rename_folder(ka, "Kunde A GmbH")
    check(store.folder_path(store.get(b)["folder"]) == "Kunde A GmbH / Standort 1", "umbenannt")
    store.remove_folder(st1)
    check(store.get(b)["folder"] == ka, "Inhalt wandert hoch")
    store.set_structure([(kb, ""), (ka, kb)], [(b, ""), (a, kb)])
    check([f["id"] for f in store.folders()] == [kb, ka] and store.folder_path(ka) == "Kunde B / Kunde A GmbH",
          "Struktur Ordner")
    check([i["id"] for i in store.items()] == [b, a] and store.get(a)["folder"] == kb, "Struktur Favoriten")
    store.set_structure([(ka, ka)], [])
    check(next(f for f in store.folders() if f["id"] == ka)["parent"] == "", "Ordner nicht in sich selbst")
    raw = st.values[fv.KEY]
    for f in raw["folders"]:
        if f["id"] == kb:
            f["parent"] = ka
        if f["id"] == ka:
            f["parent"] = kb
    st.values[fv.KEY] = raw
    check(len(store.folders()) == 2, "Zyklus übersteht das Laden")
    # Duplizieren mit Kennwort, Löschen räumt den Tresor
    store.save({"id": a, "login": {"mode": "stored", "user": "u"}, "password": "pw"})
    c = store.duplicate(a, "RZ (Kopie)")
    check(store.password(c) == "pw" and store.get(c)["name"] == "RZ (Kopie)", "Duplikat mit Kennwort")
    store.set_last(c)
    store.remove(c)
    check(store.last() == "" and store.password(c) is None and f"fav:{c}" not in sec.values, "remove + Tresor")
    store.set_panel(open=False, collapsed=[kb, "weg"])
    check(store.panel() == {"open": False, "collapsed": [kb]}, "Leistenzustand")
    # kaputte/alte Werte (Version 1 ohne Ordner)
    st.values[fv.KEY] = {"version": 1, "items": [{"id": "f-1", "server": "s", "login": {"mode": "bogus"},
                                                  "options": None}, {"x": 1}]}
    it = store.items()
    check(len(it) == 1 and it[0]["name"] == "s" and it[0]["login"]["mode"] == "sso" and it[0]["options"] == {}
          and it[0]["folder"] == "", "Normalisierung / Version 1")
    st.values[fv.KEY] = ["unsinn"]
    check(store.items() == [] and store.folders() == [], "unbrauchbarer Wert")
    # Verweise auf Anmeldedaten, nie das Passwort
    items = [{"name": "A", "username": "u1", "password": "geheim"}, {"name": "B", "username": "u2", "ref": "local:42"}]
    check(fv.cred_key(items[0]) == {"name": "A", "username": "u1"}, "cred_key manuell ohne Passwort")
    check(fv.cred_key(items[1]) == {"ref": "local:42", "name": "B", "username": "u2"}, "cred_key Verweis")
    check(fv.match_cred(items, {"ref": "local:42"}) == 1 and fv.match_cred(items, {"name": "A", "username": "u1"}) == 0,
          "match_cred")
    check(fv.match_cred(items, {"ref": "local:1"}) == -1 and fv.match_cred(items, {}) == -1, "match_cred fehlt")


def tree_text(fv, panel):
    out = []

    def visit(it, depth):
        for i in range(it.childCount()):
            ch = it.child(i)
            if ch.isHidden():
                continue
            mark = "/" if ch.data(0, fv.ROLE_KIND) == "folder" else ""
            out.append("  " * depth + ch.text(0) + mark)
            visit(ch, depth + 1)
    visit(panel.tree.invisibleRootItem(), 0)
    return out


def as_dialog(name, extra=None, folder=None):
    """Ersatz für den Favorit-Dialog: übernimmt den Entwurf mit Name/Ordner/Optionen."""
    def dialog(fav, title):
        out = {k: v for k, v in fav.items() if k != "id"}
        out["name"] = name
        out["options"] = dict(fav.get("options") or {}, **(extra or {}))
        if folder is not None:
            out["folder"] = folder
        return out
    return dialog


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
    panel = tool.fav_panel
    check(panel.current() is None and panel.tree.topLevelItemCount() == 0 and panel.empty.isVisible(), "leer")
    # Stern: Favorit aus der Maske mit eingegebenem Kennwort -> Benutzer + Kennwort im Favoriten
    tool.server.setEditText(render.PRIMARY)
    tool.m_manual.setChecked(True)
    tool.user.setText("KUNDE1\\admin")
    tool.password.setText("kunde1-geheim")
    tool.auto_partner.setChecked(False)
    ka = tool.favs.add_folder("Kunde 1")
    panel.refresh()
    panel._dialog = as_dialog("Kunde 1 DHCP", folder=ka)
    fid = panel.new_favorite(from_form=True)
    fav = tool.favs.get(fid)
    check(fav["login"] == {"mode": "stored", "user": "KUNDE1\\admin"} and fav["folder"] == ka, "stored + Ordner")
    check(tool.favs.password(fid) == "kunde1-geheim", "Kennwort im Tresor")
    check("kunde1-geheim" not in json.dumps(shot.settings.get(fv.KEY)), "Kennwort nicht in den Einstellungen")
    check(fav["options"] == {"auto_partner": False, "auto_scan": True, "family": 4}, "Optionen")
    check(tree_text(fv, panel) == ["Kunde 1/", "  Kunde 1 DHCP"] and panel.current_id() == fid, "Baum + Auswahl")
    # zweiter Favorit: Passwortmanager-Eintrag, der noch nicht in der Liste des Tools steht
    fid2 = tool.favs.save({"name": "Kunde 2", "server": "dhcp.kunde2.local",
                           "login": {"mode": "vault", "cred": {"ref": "local:k2", "name": "K2", "username": "K2\\adm"}}})
    panel.refresh()
    panel.select(fid2)
    items = tool.cred_field.value()["items"]
    check(tool.m_vault.isChecked() and len(items) == 3 and items[2]["ref"] == "local:k2"
          and tool.cred_field.combo.currentIndex() == 2, "Verweis übernommen")
    check(tool.password.text() == "", "Kennwortfeld geleert")
    # Klick auf den ersten: Benutzer und Kennwort stehen in der Maske
    panel._clicked(panel._find(fid))
    check(tool.m_manual.isChecked() and tool.user.text() == "KUNDE1\\admin" and tool.password.text() == "kunde1-geheim"
          and not tool.auto_partner.isChecked(), "Maske gefüllt")
    # Kennwort verloren -> Hinweis
    tool.favs.set_password(fid, None)
    panel.select(fid)
    check(tool.password.text() == "" and tool.login_status.text() == tool.tr("fav.pw_missing"), "Kennwort fehlt")
    tool.password.setText("kunde1-geheim")
    panel.overwrite()
    check(tool.favs.password(fid) == "kunde1-geheim", "überschreiben speichert Kennwort")
    # Server von Hand geändert -> kein Favorit, Stern grau
    tool.server.setEditText("anderer")
    check(panel.current() is None and tool.favs.last() == "", "Handänderung")
    # Suche
    panel.search.setText("kunde2")
    check(tree_text(fv, panel) == ["Kunde 2"], f"Suche: {tree_text(fv, panel)}")
    panel.search.setText("")
    # Ziehen und Ablegen: Kunde 2 in den Ordner Kunde 1 an den Anfang
    it2 = panel._find(fid2)
    panel.tree.invisibleRootItem().removeChild(it2)
    panel._find(ka).insertChild(0, it2)
    panel._dropped()
    check(tool.favs.get(fid2)["folder"] == ka and tree_text(fv, panel) == ["Kunde 1/", "  Kunde 2", "  Kunde 1 DHCP"],
          "verschoben")
    # Ordner zuklappen bleibt gespeichert, Leiste einklappen
    panel._find(ka).setExpanded(False)
    check(tool.favs.panel()["collapsed"] == [ka], "zugeklappt gespeichert")
    panel.set_open(False)
    check(tool.favs.panel()["open"] is False and panel.strip.isVisible() and not panel.body.isVisible(), "eingeklappt")
    panel.set_open(True)
    # Ordner löschen: Inhalt bleibt
    tool.favs.remove_folder(ka)
    panel.refresh()
    check(tree_text(fv, panel) == ["Kunde 2", "Kunde 1 DHCP"], "Ordner gelöscht, Favoriten oben")
    # Favorit löschen räumt das Kennwort
    tool.favs.remove(fid2)
    # Doppelklick meldet an und stellt die gespeicherte Ansicht (IPv6) ein
    tool.favs.save({"id": fid, "server": render.PRIMARY, "login": {"mode": "sso"},
                    "options": {"family": 6, "auto_scan": False}})
    tool.favs.set_section(fid, "ai", {"level": 1})
    panel.refresh()
    panel._activated(panel._find(fid))
    shot.wait_until(lambda: tool.stack.currentIndex() == 1 and not tool.runner.active, 30, "DHCP-Anmeldung")
    check(tool.family == 6 and tool.favs.get(fid)["ai"] == {"level": 1}, "Ansicht IPv6 aus dem Favoriten")
    # Favorit-Dialog: Werte und Prüfung
    dlg = fv.FavoriteDialog(tool.root, tool.tr, tool.favs, tool.favs.get(fid), panel.option_fields,
                            tool.fav_cred_items, "t")
    dlg.m["stored"].setChecked(True)
    check(dlg.validate(dlg.values()) == tool.tr("login.err_user"), "Prüfung Benutzer")
    dlg.s_user.setText("u")
    check(dlg.validate(dlg.values()) == tool.tr("fav.err_pw"), "Prüfung Kennwort")
    dlg.s_pw.setText("p")
    dlg.opt_widgets["family"].setCurrentIndex(0)
    v = dlg.values()
    check(dlg.validate(v) is None and v["password"] == "p" and v["options"]["family"] == 4, "Dialogwerte")
    # neue Instanz: zuletzt gewählter Favorit ist wieder da
    tool2, _ = shot.create()
    check(tool2.fav_panel.current_id() == fid and tool2.server.currentText() == render.PRIMARY, "wiederhergestellt")
    shot.close()


def test_dns(manager):
    shot = place(manager, "ms_dns_extended")
    render = manager._import_module(manager.get(shot.tool_id), "screenshots.render")
    tool_mod = shot.module("tool")
    fv = shot.module("favorites")
    tool_mod.MsDnsExtended.backend_factory = render._fake_backend(shot)
    shot.settings.set("auto_refresh", 0)
    tool, _ = shot.create()
    panel = tool.fav_panel
    # Favorit manuell anlegen über den Dialog (Plus in der Liste)
    dlg = fv.FavoriteDialog(tool.root, tool.tr, tool.favs, {}, panel.option_fields, tool.fav_cred_items, "t")
    dlg.name.setText("Domäne")
    dlg.server.setText(render.DC1)
    dlg.opt_widgets["auto_discover"].setChecked(False)
    dlg.opt_widgets["auto_scan"].setChecked(False)
    dlg.opt_widgets["servers"].setText("DMZ-DNS01; dmz-dns01, " + render.DC1)
    dlg.opt_widgets["dhcp_server"].setText("dhcp01.corp.example")
    v = dlg.values()
    check(dlg.validate(v) is None and v["login"] == {"mode": "sso"}, "Dialog sso")
    check(v["options"] == {"auto_discover": False, "auto_scan": False, "servers": ["DMZ-DNS01", render.DC1],
                           "dhcp_server": "dhcp01.corp.example"}, "DNS-Optionen")
    panel._dialog = lambda fav, title: v
    fid = panel.new_favorite(from_form=False)
    check(tool.server.currentText() == render.DC1 and not tool.auto_discover.isChecked(), "Plus füllt die Maske")
    panel.overwrite()
    check(tool.favs.get(fid)["options"]["servers"] == ["DMZ-DNS01", render.DC1], "Dialog-Optionen bleiben")
    panel._activated(panel._find(fid))
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
