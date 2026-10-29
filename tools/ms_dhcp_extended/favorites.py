"""Server-Favoriten: Server mit Anmeldung und Verbindungseinstellungen speichern, in Ordnern ordnen und auf der
Anmeldeseite aus einer ausklappbaren Liste wählen.

Gespeichert in der Tool-Einstellung "favorites" (Klartext, ohne Passwörter):

    {"version": 2, "last": "<id>",
     "panel": {"open": true, "collapsed": ["<ordner-id>", …]},
     "folders": [{"id": "d-1a2b3c4d", "name": "Kunde A", "parent": ""}],          # parent "" = oberste Ebene
     "items": [
        {"id": "f-1a2b3c4d", "name": "Rechenzentrum", "folder": "d-1a2b3c4d", "server": "rz-dhcp01", "note": "",
         "login": {"mode": "sso" | "vault" | "stored" | "manual",
                   "user": "...",                                         # bei "stored" und "manual"
                   "cred": {"ref", "name", "username"} | {"name", "username"}},   # bei "vault", nur Verweis
         "options": {...},     # toolspezifisch (Partner verbinden, Prüfung, …)
         "ai": {}}]}           # reserviert für die KI-Einstellungen je Server

Anmeldearten: "sso" angemeldeter Benutzer, "vault" Eintrag aus dem Passwortmanager (Verweis), "stored" Benutzer und
Kennwort des Favoriten (Kennwort verschlüsselt im Tresor unter context.secrets "fav:<id>"), "manual" nur der
Benutzer, Kennwort bei jeder Anmeldung. Reihenfolge = Reihenfolge der Listen.

Unbekannte Schlüssel bleiben beim Speichern erhalten. Weitere Abschnitte liest und schreibt man mit
section()/set_section(). Die Datei ist in beiden Server-Tools gleich (Kopie, damit die Tools unabhängig bleiben).
"""

from __future__ import annotations

import copy
import uuid

from PySide6.QtCore import QEvent, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QFrame, QGridLayout,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMenu, QRadioButton, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from omniwrench.ui import theme
from omniwrench.ui.widgets import library_icon

from .ui_base import bold_label, confirm, help_icon, warn

KEY = "favorites"
VERSION = 2
MAX_FAVORITES = 500
MODES = ("sso", "vault", "stored", "manual")
ROLE_KIND = Qt.ItemDataRole.UserRole          # "fav" | "folder"
ROLE_ID = Qt.ItemDataRole.UserRole + 1


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def cred_key(item: dict | None) -> dict:
    """Woran ein Eintrag aus dem Passwortmanager wiedererkannt wird – nie das Passwort."""
    if not item:
        return {}
    if item.get("ref"):
        return {"ref": item["ref"], "name": item.get("name", ""), "username": item.get("username", "")}
    return {"name": item.get("name", ""), "username": item.get("username", "")}


def match_cred(items: list[dict], key: dict | None) -> int:
    """Index des Zugangs aus der Liste des Anmeldefelds, der zum Verweis passt (-1 = nicht vorhanden)."""
    if not key:
        return -1
    for i, it in enumerate(items):
        if key.get("ref"):
            if it.get("ref") == key["ref"]:
                return i
        elif not it.get("ref") and it.get("name", "") == key.get("name", "") \
                and it.get("username", "") == key.get("username", ""):
            return i
    return -1


def _merge(old: dict, new: dict) -> dict:
    """new über old legen; Unterabschnitte (dict) werden zusammengeführt, damit Fremdschlüssel bleiben."""
    out = copy.deepcopy(old)
    for k, v in new.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict) and k != "login":
            out[k] = _merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


class FavoriteStore:
    """Liest und schreibt Favoriten und Ordner. Gibt immer Kopien heraus (ToolSettingsStore vergleicht Werte).

    secrets: context.secrets des Tools (verschlüsselter Bereich im Tresor) für die Kennwörter der Favoriten.
    """

    def __init__(self, settings, secrets=None):
        self.settings = settings
        self.secrets = secrets

    # --- Rohdaten -------------------------------------------------------------------------------------
    def _data(self) -> dict:
        raw = self.settings.get(KEY)
        data = copy.deepcopy(raw) if isinstance(raw, dict) else {}
        folders = [f for f in data.get("folders") or [] if isinstance(f, dict) and f.get("id")]
        fids = {f["id"] for f in folders}
        for f in folders:
            f["name"] = str(f.get("name") or "?")
            if f.get("parent") not in fids or f.get("parent") == f["id"]:
                f["parent"] = ""
        items = [i for i in data.get("items") or [] if isinstance(i, dict) and i.get("id")]
        for i in items:
            i.setdefault("server", "")
            i["name"] = i.get("name") or i["server"]
            i.setdefault("note", "")
            if i.get("folder") not in fids:
                i["folder"] = ""
            login = i.get("login") if isinstance(i.get("login"), dict) else {}
            if login.get("mode") not in MODES:
                login["mode"] = "sso"
            i["login"] = login
            i["options"] = i.get("options") if isinstance(i.get("options"), dict) else {}
            i["ai"] = i.get("ai") if isinstance(i.get("ai"), dict) else {}
        panel = data.get("panel") if isinstance(data.get("panel"), dict) else {}
        panel.setdefault("open", True)
        panel["collapsed"] = [c for c in panel.get("collapsed") or [] if c in fids]
        data.update(folders=folders, items=items, panel=panel, version=max(int(data.get("version") or 1), VERSION))
        data.setdefault("last", "")
        return data

    def _write(self, data: dict) -> None:
        self.settings.set(KEY, data)

    # --- Favoriten ------------------------------------------------------------------------------------
    def items(self) -> list[dict]:
        return self._data()["items"]

    def get(self, fid: str) -> dict | None:
        return next((i for i in self.items() if i["id"] == fid), None)

    def save(self, fav: dict) -> str:
        """Legt an (ohne/unbekannte id) oder führt mit dem vorhandenen Favoriten zusammen. Liefert die id.

        Ein Schlüssel "password" wird nie in die Einstellungen geschrieben: bei Anmeldeart "stored" landet er
        verschlüsselt im Tresor (None/fehlend = Kennwort unverändert lassen), bei jeder anderen Art wird ein
        gespeichertes Kennwort gelöscht.
        """
        fav = dict(fav)
        password = fav.pop("password", None)
        data = self._data()
        fid = fav.get("id") or ""
        for idx, cur in enumerate(data["items"]):
            if cur["id"] == fid:
                data["items"][idx] = merged = _merge(cur, fav)
                break
        else:
            if len(data["items"]) >= MAX_FAVORITES:
                raise ValueError("too many favorites")
            fid = _new_id("f")
            merged = _merge({"name": "", "folder": "", "server": "", "note": "", "login": {"mode": "sso"},
                             "options": {}, "ai": {}}, fav)
            merged["id"] = fid
            data["items"].append(merged)
        self._write(data)
        if merged["login"].get("mode") == "stored":
            if password is not None:
                self.set_password(fid, password)
        else:
            self.set_password(fid, None)
        return fid

    def remove(self, fid: str) -> None:
        data = self._data()
        data["items"] = [i for i in data["items"] if i["id"] != fid]
        if data["last"] == fid:
            data["last"] = ""
        self._write(data)
        self.set_password(fid, None)

    def duplicate(self, fid: str, name: str) -> str | None:
        fav = self.get(fid)
        if not fav:
            return None
        new = {k: v for k, v in fav.items() if k != "id"}
        new["name"] = name
        nid = self.save(new)
        if fav["login"].get("mode") == "stored":
            self.set_password(nid, self.password(fid))
        return nid

    # --- Kennwort je Favorit (verschlüsselt im Tresor) ------------------------------------------------
    def password(self, fid: str) -> str | None:
        if self.secrets is None:
            return None
        val = self.secrets.get(f"fav:{fid}")
        return val.get("password") if isinstance(val, dict) else None

    def password_lost(self, fid: str) -> bool:
        """True, wenn das Kennwort beim Zurücksetzen des Masterpassworts verloren ging."""
        return bool(self.secrets is not None and self.secrets.is_lost(f"fav:{fid}"))

    def set_password(self, fid: str, password: str | None) -> None:
        if self.secrets is None:
            return
        if password is None:
            if self.secrets.get(f"fav:{fid}") is not None or self.secrets.is_lost(f"fav:{fid}"):
                self.secrets.delete(f"fav:{fid}")
        else:
            self.secrets.set(f"fav:{fid}", {"password": password})

    # --- Ordner ---------------------------------------------------------------------------------------
    def folders(self) -> list[dict]:
        return self._data()["folders"]

    def add_folder(self, name: str, parent: str = "") -> str:
        data = self._data()
        did = _new_id("d")
        data["folders"].append({"id": did, "name": name, "parent": parent if parent in
                                {f["id"] for f in data["folders"]} else ""})
        self._write(data)
        return did

    def rename_folder(self, did: str, name: str) -> None:
        data = self._data()
        for f in data["folders"]:
            if f["id"] == did:
                f["name"] = name
        self._write(data)

    def remove_folder(self, did: str) -> None:
        """Löscht den Ordner; Inhalt (Favoriten und Unterordner) wandert eine Ebene nach oben."""
        data = self._data()
        folder = next((f for f in data["folders"] if f["id"] == did), None)
        if not folder:
            return
        for f in data["folders"]:
            if f["parent"] == did:
                f["parent"] = folder["parent"]
        for i in data["items"]:
            if i["folder"] == did:
                i["folder"] = folder["parent"]
        data["folders"] = [f for f in data["folders"] if f["id"] != did]
        self._write(data)

    def descendants(self, did: str) -> set[str]:
        out, todo = set(), [did]
        folders = self.folders()
        while todo:
            cur = todo.pop()
            for f in folders:
                if f["parent"] == cur and f["id"] not in out:
                    out.add(f["id"])
                    todo.append(f["id"])
        return out

    def folder_path(self, did: str) -> str:
        names, seen = [], set()
        by_id = {f["id"]: f for f in self.folders()}
        while did in by_id and did not in seen:
            seen.add(did)
            names.insert(0, by_id[did]["name"])
            did = by_id[did]["parent"]
        return " / ".join(names)

    def set_structure(self, folders: list[tuple[str, str]], items: list[tuple[str, str]]) -> None:
        """Neue Anordnung aus der Liste (Ziehen und Ablegen): [(ordner-id, parent)], [(favorit-id, ordner)]."""
        data = self._data()
        by_f = {f["id"]: f for f in data["folders"]}
        by_i = {i["id"]: i for i in data["items"]}
        known = set(by_f)
        new_f = []
        for did, parent in folders:
            if did in by_f:
                by_f[did]["parent"] = parent if parent in known and parent != did else ""
                new_f.append(by_f.pop(did))
        new_i = []
        for fid, folder in items:
            if fid in by_i:
                by_i[fid]["folder"] = folder if folder in known else ""
                new_i.append(by_i.pop(fid))
        data["folders"] = new_f + list(by_f.values())
        data["items"] = new_i + list(by_i.values())
        self._write(data)

    # --- Zustand --------------------------------------------------------------------------------------
    def last(self) -> str:
        return self._data()["last"]

    def set_last(self, fid: str) -> None:
        data = self._data()
        if data["last"] != fid:
            data["last"] = fid
            self._write(data)

    def panel(self) -> dict:
        return self._data()["panel"]

    def set_panel(self, **values) -> None:
        data = self._data()
        new = dict(data["panel"], **values)
        if new != data["panel"]:
            data["panel"] = new
            self._write(data)

    def section(self, fid: str, name: str) -> dict:
        fav = self.get(fid)
        val = fav.get(name) if fav else None
        return val if isinstance(val, dict) else {}

    def set_section(self, fid: str, name: str, value: dict) -> None:
        data = self._data()
        for i in data["items"]:
            if i["id"] == fid:
                i[name] = copy.deepcopy(value)
                self._write(data)
                return


# --- Texte ------------------------------------------------------------------------------------------------

def summary(tr, fav: dict, store: FavoriteStore | None = None) -> str:
    """Kurzbeschreibung für Tooltips."""
    login = fav.get("login") or {}
    mode = login.get("mode", "sso")
    if mode == "stored":
        how = tr("fav.mode_stored", user=login.get("user") or "–")
        if store is not None and store.password_lost(fav["id"]):
            how += " ❗"
    elif mode == "manual":
        how = tr("fav.mode_manual", user=login.get("user") or "–")
    elif mode == "vault":
        c = login.get("cred") or {}
        how = tr("fav.mode_vault", cred=c.get("name") or c.get("username") or c.get("ref") or "–")
    else:
        how = tr("fav.mode_sso")
    lines = [tr("fav.server") + ": " + (fav.get("server") or "–"), how]
    if store is not None and fav.get("folder"):
        lines.insert(0, tr("fav.folder") + ": " + store.folder_path(fav["folder"]))
    if fav.get("note"):
        lines.append(fav["note"])
    return "\n".join(lines)


# --- Favorit-Dialog ---------------------------------------------------------------------------------------

class FavoriteDialog(QDialog):
    """Favorit anlegen oder bearbeiten: Name, Ordner, Server, Anmeldung (inkl. eigenem Kennwort), Notiz, Optionen.

    option_fields: [{"key", "label", "type": "check" | "text" | "list" | "choice", "items": [(wert, text)],
    "default"}] – toolspezifische Verbindungseinstellungen. cred_items(): Einträge des Anmeldefelds des Tools.
    result: Favorit (dict, ggf. mit "password") nach OK.
    """

    def __init__(self, parent, tr, store: FavoriteStore, fav: dict, option_fields: list[dict], cred_items,
                 title: str):
        super().__init__(parent)
        self.tr, self.store, self.fav = tr, store, fav
        self.option_fields = option_fields
        self.result: dict | None = None
        self.setWindowTitle(title)
        self.setMinimumWidth(600)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.name = QLineEdit(fav.get("name", ""))
        form.addRow(tr("fav.name"), self.name)
        self.folder = QComboBox()
        self.folder.addItem(tr("fav.root"), "")
        for f in sorted(store.folders(), key=lambda f: store.folder_path(f["id"]).lower()):
            self.folder.addItem(library_icon("folder", 16), store.folder_path(f["id"]), f["id"])
        self.folder.setCurrentIndex(max(0, self.folder.findData(fav.get("folder", ""))))
        form.addRow(tr("fav.folder"), self.folder)
        self.server = QLineEdit(fav.get("server", ""))
        self.server.setPlaceholderText(tr("login.server_ph"))
        form.addRow(tr("fav.server"), self.server)

        login = fav.get("login") or {}
        mode = login.get("mode", "sso")
        box = QVBoxLayout()
        box.setSpacing(4)
        self.modes = QButtonGroup(self)
        self.m = {}
        for i, key in enumerate(MODES):
            rb = QRadioButton(tr("fav.login_" + key))
            self.modes.addButton(rb, i)
            self.m[key] = rb
            box.addWidget(rb)
            if key == "vault":
                row = QHBoxLayout()
                self.cred = QComboBox()
                self._cred_items = [cred_key(it) for it in (cred_items() if cred_items else [])]
                own = login.get("cred") or {}
                if own and match_cred(self._cred_items, own) < 0:
                    self._cred_items.append(cred_key(own))
                self._fill_creds(own)
                row.addWidget(self.cred, 1)
                pick = QToolButton()
                pick.setIcon(library_icon("key-round", 16))
                pick.setToolTip(tr("fav.pick_cred"))
                pick.clicked.connect(self._pick)
                row.addWidget(pick)
                self.cred_row = QWidget()
                self.cred_row.setLayout(row)
                row.setContentsMargins(22, 0, 0, 0)
                box.addWidget(self.cred_row)
            if key == "stored":
                grid = QGridLayout()
                grid.setContentsMargins(22, 0, 0, 0)
                self.s_user = QLineEdit(login.get("user", "") if mode == "stored" else "")
                self.s_user.setPlaceholderText(tr("login.user_ph"))
                self.s_pw = QLineEdit()
                self.s_pw.setEchoMode(QLineEdit.EchoMode.Password)
                has_pw = bool(fav.get("id")) and store.password(fav["id"]) is not None
                self._pw_given = fav.get("password")
                if self._pw_given:
                    self.s_pw.setText(self._pw_given)
                self.s_pw.setPlaceholderText(tr("fav.pw_keep") if has_pw else tr("login.password"))
                self._has_pw = has_pw
                show = QToolButton()
                show.setIcon(library_icon("eye", 16))
                show.setCheckable(True)
                show.setToolTip(tr("fav.pw_show"))
                show.toggled.connect(lambda on: self.s_pw.setEchoMode(
                    QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
                grid.addWidget(self.s_user, 0, 0)
                grid.addWidget(self.s_pw, 0, 1)
                grid.addWidget(show, 0, 2)
                lost = bool(fav.get("id")) and store.password_lost(fav["id"])
                note = QLabel(tr("fav.pw_lost") if lost else tr("fav.pw_hint"))
                note.setWordWrap(True)
                note.setStyleSheet(f"color:{theme.current['danger' if lost else 'muted']};")
                grid.addWidget(note, 1, 0, 1, 3)
                self.stored_row = QWidget()
                self.stored_row.setLayout(grid)
                box.addWidget(self.stored_row)
            if key == "manual":
                self.m_user = QLineEdit(login.get("user", "") if mode == "manual" else "")
                self.m_user.setPlaceholderText(tr("login.user_ph"))
                w = QWidget()
                hl = QHBoxLayout(w)
                hl.setContentsMargins(22, 0, 0, 0)
                hl.addWidget(self.m_user)
                self.manual_row = w
                box.addWidget(w)
        self.m.get(mode, self.m["sso"]).setChecked(True)
        self.modes.idToggled.connect(lambda *_: self._mode_changed())
        form.addRow(tr("login.auth"), box)
        self.note = QLineEdit(fav.get("note", ""))
        form.addRow(tr("fav.note"), self.note)

        self.opt_widgets: dict[str, QWidget] = {}
        opts = fav.get("options") or {}
        for f in option_fields:
            v = opts.get(f["key"], f.get("default"))
            t = f.get("type", "text")
            if t == "check":
                w = QCheckBox(f["label"])
                w.setChecked(bool(v))
                form.addRow("", w)
            elif t == "choice":
                w = QComboBox()
                for val, text in f.get("items") or []:
                    w.addItem(text, val)
                w.setCurrentIndex(max(0, w.findData(v)))
                form.addRow(f["label"], w)
            else:
                w = QLineEdit(", ".join(v or []) if t == "list" else str(v or ""))
                if f.get("placeholder"):
                    w.setPlaceholderText(f["placeholder"])
                form.addRow(f["label"], w)
            self.opt_widgets[f["key"]] = w
        lay.addLayout(form)
        self.err = QLabel("")
        self.err.setWordWrap(True)
        self.err.setStyleSheet(f"color:{theme.current['danger']};")
        self.err.hide()
        lay.addWidget(self.err)
        bb = QDialogButtonBox()
        ok = bb.addButton(tr("ui.ok"), QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setDefault(True)
        bb.addButton(tr("ui.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addWidget(help_icon(tr("fav.hint")))
        row.addWidget(bb, 1)
        lay.addLayout(row)
        self._mode_changed()

    def _fill_creds(self, select: dict) -> None:
        self.cred.clear()
        for it in self._cred_items:
            text = it.get("name") or it.get("username") or it.get("ref") or "?"
            if it.get("username") and it["username"] != text:
                text += f"  —  {it['username']}"
            self.cred.addItem(library_icon("key-round" if it.get("ref") else "pencil", 16), text)
        if not self._cred_items:
            self.cred.addItem(self.tr("fav.no_cred"))
        self.cred.setCurrentIndex(max(0, match_cred(self._cred_items, select)))

    def _pick(self) -> None:
        from omniwrench.ui.credentials import pick_credential
        c = pick_credential(self)
        if not c:
            return
        key = {"ref": c.ref, "name": c.name, "username": c.username}
        if match_cred(self._cred_items, key) < 0:
            self._cred_items.append(key)
        self._fill_creds(key)
        self.m["vault"].setChecked(True)

    def _mode(self) -> str:
        return next(k for k, rb in self.m.items() if rb.isChecked())

    def _mode_changed(self) -> None:
        mode = self._mode()
        self.cred_row.setEnabled(mode == "vault")
        self.stored_row.setEnabled(mode == "stored")
        self.manual_row.setEnabled(mode == "manual")

    def values(self) -> dict:
        mode = self._mode()
        login: dict = {"mode": mode}
        out = {"name": self.name.text().strip(), "folder": self.folder.currentData() or "",
               "server": self.server.text().strip(), "note": self.note.text().strip(), "login": login}
        if mode == "vault":
            idx = self.cred.currentIndex()
            login["cred"] = self._cred_items[idx] if 0 <= idx < len(self._cred_items) else {}
        elif mode == "stored":
            login["user"] = self.s_user.text().strip()
            pw = self.s_pw.text()
            out["password"] = pw or None          # leer = vorhandenes Kennwort unverändert lassen
        elif mode == "manual":
            login["user"] = self.m_user.text().strip()
        opts = {}
        for f in self.option_fields:
            w, t = self.opt_widgets[f["key"]], f.get("type", "text")
            if t == "check":
                opts[f["key"]] = w.isChecked()
            elif t == "choice":
                opts[f["key"]] = w.currentData()
            elif t == "list":
                seen: list[str] = []
                for s in w.text().replace(";", ",").split(","):
                    s = s.strip()
                    if s and s.lower() not in (x.lower() for x in seen):
                        seen.append(s)
                opts[f["key"]] = seen
            else:
                opts[f["key"]] = w.text().strip()
        out["options"] = opts
        return out

    def validate(self, v: dict) -> str | None:
        tr = self.tr
        if not v["name"]:
            return tr("fav.err_name")
        if not v["server"]:
            return tr("fav.err_server")
        mode = v["login"]["mode"]
        if mode == "vault" and not v["login"].get("cred"):
            return tr("fav.err_cred")
        if mode in ("stored", "manual") and not v["login"].get("user"):
            return tr("login.err_user")
        if mode == "stored" and v.get("password") is None and not self._has_pw:
            return tr("fav.err_pw")
        return None

    def _accept(self) -> None:
        v = self.values()
        msg = self.validate(v)
        if msg:
            self.err.setText(msg)
            self.err.show()
            return
        self.result = v
        self.accept()


# --- Seitenleiste ---------------------------------------------------------------------------------------

def _act(menu: QMenu, icon: str, text: str, slot):
    """Menüeintrag mit Symbol (die Überladung addAction(icon, text, slot) ist unzuverlässig)."""
    a = menu.addAction(text, slot)
    a.setIcon(library_icon(icon, 16))
    return a


class _Tree(QTreeWidget):
    dropped = Signal()

    def dropEvent(self, event):    # noqa: N802 (Qt)
        super().dropEvent(event)
        QTimer.singleShot(0, self.dropped.emit)


class FavoritesPanel(QWidget):
    """Ausklappbare Favoritenliste links neben der Anmeldemaske, mit Ordnern.

    * Klick füllt die Anmeldemaske (Signal applied), Doppelklick meldet direkt an (Signal activated).
    * Kopfzeile: neuer Favorit, neuer Ordner, einklappen; Suchfeld; Kontextmenü; Ziehen und Ablegen.
    * star_button(): Stern-Knopf für das Serverfeld (aktuelle Maske speichern / Favorit überschreiben).

    capture() liefert {"server", "login", "options"[, "password"]} aus der Anmeldemaske.
    """

    applied = Signal(object)      # Favorit (dict) oder None
    activated = Signal(object)    # Favorit (dict) – Doppelklick: anmelden

    def __init__(self, tr, store: FavoriteStore, capture, option_fields: list[dict] | None = None, cred_items=None,
                 parent=None):
        super().__init__(parent)
        self.tr, self.store, self.capture = tr, store, capture
        self.option_fields = option_fields or []
        self.cred_items = cred_items
        self._star: QToolButton | None = None
        self._current = ""
        c = theme.current
        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 0, 8)
        outer.setSpacing(0)
        # eingeklappt: schmale Leiste mit Knopf
        self.strip = QToolButton()
        self.strip.setIcon(library_icon("panel-left-open", 18))
        self.strip.setToolTip(tr("fav.panel_open"))
        self.strip.setText(tr("fav.title"))
        self.strip.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.strip.setAutoRaise(True)
        self.strip.clicked.connect(lambda: self.set_open(True))
        outer.addWidget(self.strip, 0, Qt.AlignmentFlag.AlignTop)
        # ausgeklappt
        self.body = QFrame()
        self.body.setObjectName("favpanel")
        self.body.setStyleSheet(f"QFrame#favpanel {{ border:1px solid {c['border']}; border-radius:8px;"
                                f" background:{c['surface']}; }}")
        self.body.setMinimumWidth(240)
        self.body.setMaximumWidth(340)
        bl = QVBoxLayout(self.body)
        bl.setContentsMargins(10, 8, 10, 10)
        bl.setSpacing(6)
        head = QHBoxLayout()
        head.addWidget(bold_label(tr("fav.title")))
        head.addStretch(1)
        for icon, tip, slot in (("plus", "fav.new", lambda: self.new_favorite(from_form=False)),
                                ("folder-plus", "fav.new_folder", lambda: self.new_folder()),
                                ("panel-left-close", "fav.panel_close", lambda: self.set_open(False))):
            b = QToolButton()
            b.setIcon(library_icon(icon, 16))
            b.setToolTip(tr(tip))
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            head.addWidget(b)
        bl.addLayout(head)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("fav.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)
        bl.addWidget(self.search)
        self.tree = _Tree()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(14)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemClicked.connect(self._clicked)
        self.tree.itemActivated.connect(self._activated)
        self.tree.itemExpanded.connect(lambda _i: self._save_collapsed())
        self.tree.itemCollapsed.connect(lambda _i: self._save_collapsed())
        self.tree.dropped.connect(self._dropped)
        self.tree.installEventFilter(self)
        bl.addWidget(self.tree, 1)
        self.empty = QLabel(tr("fav.empty"))
        self.empty.setWordWrap(True)
        self.empty.setStyleSheet(f"color:{c['muted']};")
        bl.addWidget(self.empty)
        outer.addWidget(self.body)
        self.refresh()
        self.set_open(bool(self.store.panel().get("open", True)), save=False)

    # --- Aufbau der Liste ----------------------------------------------------------------------------
    def refresh(self, select: str | None = None) -> None:
        if select is None:
            select = self._current
        collapsed = set(self.store.panel().get("collapsed") or [])
        self.tree.blockSignals(True)
        self.tree.clear()
        nodes: dict[str, QTreeWidgetItem] = {}
        folders = self.store.folders()
        pending = list(folders)
        while pending:                      # Eltern vor Kindern anlegen (Reihenfolge bleibt erhalten)
            rest = []
            for f in pending:
                if f["parent"] and f["parent"] not in nodes:
                    rest.append(f)
                    continue
                it = QTreeWidgetItem([f["name"]])
                it.setIcon(0, library_icon("folder", 16, theme.current["muted"]))
                it.setData(0, ROLE_KIND, "folder")
                it.setData(0, ROLE_ID, f["id"])
                it.setFlags(it.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
                (nodes[f["parent"]] if f["parent"] else self.tree.invisibleRootItem()).addChild(it)
                nodes[f["id"]] = it
            if len(rest) == len(pending):   # Zyklus: Rest auf oberste Ebene
                for f in rest:
                    f["parent"] = ""
            pending = rest
        sel_item = None
        for fav in self.store.items():
            it = QTreeWidgetItem([fav["name"]])
            it.setIcon(0, library_icon("star", 16, theme.current["accent"]))
            it.setToolTip(0, summary(self.tr, fav, self.store))
            it.setData(0, ROLE_KIND, "fav")
            it.setData(0, ROLE_ID, fav["id"])
            it.setFlags((it.flags() | Qt.ItemFlag.ItemIsDragEnabled) & ~Qt.ItemFlag.ItemIsDropEnabled)
            (nodes.get(fav["folder"]) or self.tree.invisibleRootItem()).addChild(it)
            if fav["id"] == select:
                sel_item = it
        for did, it in nodes.items():
            it.setExpanded(did not in collapsed)
        self.tree.invisibleRootItem().setFlags(self.tree.invisibleRootItem().flags() | Qt.ItemFlag.ItemIsDropEnabled)
        if sel_item:
            self.tree.setCurrentItem(sel_item)
            p = sel_item.parent()
            while p:
                p.setExpanded(True)
                p = p.parent()
        self._current = select if sel_item else ""
        self.tree.blockSignals(False)
        self.empty.setVisible(not folders and not self.store.items())
        self._filter(self.search.text())
        self._update_star()

    def _filter(self, text: str) -> None:
        t = text.strip().lower()

        def visit(it: QTreeWidgetItem) -> bool:
            any_child = False
            for i in range(it.childCount()):
                any_child = visit(it.child(i)) or any_child
            if it is self.tree.invisibleRootItem():
                return any_child
            if it.data(0, ROLE_KIND) == "fav":
                fav = self.store.get(it.data(0, ROLE_ID)) or {}
                hit = not t or t in (fav.get("name", "") + " " + fav.get("server", "") + " "
                                     + fav.get("note", "")).lower()
            else:
                hit = not t or any_child or t in it.text(0).lower()
            it.setHidden(not hit)
            if t and any_child:
                it.setExpanded(True)
            return hit
        visit(self.tree.invisibleRootItem())

    def _save_collapsed(self) -> None:
        if self.search.text().strip():
            return                       # Suche klappt auf, das soll nicht gespeichert werden
        collapsed = []

        def visit(it):
            for i in range(it.childCount()):
                ch = it.child(i)
                if ch.data(0, ROLE_KIND) == "folder":
                    if not ch.isExpanded():
                        collapsed.append(ch.data(0, ROLE_ID))
                    visit(ch)
        visit(self.tree.invisibleRootItem())
        self.store.set_panel(collapsed=collapsed)

    def _dropped(self) -> None:
        folders, items = [], []

        def visit(it, parent: str):
            for i in range(it.childCount()):
                ch = it.child(i)
                if ch.data(0, ROLE_KIND) == "folder":
                    folders.append((ch.data(0, ROLE_ID), parent))
                    visit(ch, ch.data(0, ROLE_ID))
                else:
                    items.append((ch.data(0, ROLE_ID), parent))
                    visit(ch, parent)       # falls Qt doch etwas unter einen Favoriten gelegt hat
        visit(self.tree.invisibleRootItem(), "")
        self.store.set_structure(folders, items)
        self.refresh()

    # --- Auf- und Zuklappen --------------------------------------------------------------------------
    def set_open(self, on: bool, save: bool = True) -> None:
        self.body.setVisible(on)
        self.strip.setVisible(not on)
        if save:
            self.store.set_panel(open=on)

    def is_open(self) -> bool:
        return self.body.isVisible() if self.isVisible() else bool(self.store.panel().get("open", True))

    # --- Auswahl -------------------------------------------------------------------------------------
    def current_id(self) -> str:
        return self._current

    def current(self) -> dict | None:
        return self.store.get(self._current) if self._current else None

    def select(self, fid: str, apply: bool = True) -> None:
        """Favorit auswählen ("" = keiner); apply=True füllt die Anmeldemaske."""
        fav = self.store.get(fid) if fid else None
        self._current = fav["id"] if fav else ""
        self.store.set_last(self._current)
        self.refresh(self._current)
        if not fav:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
        if apply:
            self.applied.emit(fav)
        self._update_star()

    def restore(self) -> None:
        """Beim Start den zuletzt gewählten Favoriten wieder einsetzen (füllt die Maske)."""
        fid = self.store.last()
        if fid and self.store.get(fid):
            self.select(fid)

    def server_edited(self, server: str) -> None:
        """Wird der Server von Hand geändert, gilt der Favorit nicht mehr."""
        fav = self.current()
        if fav and fav["server"].strip().lower() != server.strip().lower():
            self.select("", apply=False)
        self._update_star(server)

    def _clicked(self, it: QTreeWidgetItem, _col: int = 0) -> None:
        if it.data(0, ROLE_KIND) == "fav":
            self.select(it.data(0, ROLE_ID))

    def _activated(self, it: QTreeWidgetItem, _col: int = 0) -> None:
        if it.data(0, ROLE_KIND) == "fav":
            fid = it.data(0, ROLE_ID)
            if fid != self._current:
                self.select(fid)
            fav = self.current()
            if fav:
                self.activated.emit(fav)

    def eventFilter(self, obj, event):    # noqa: N802 (Qt)
        if obj is self.tree and event.type() == QEvent.Type.KeyPress:
            it = self.tree.currentItem()
            if it and event.key() == Qt.Key.Key_Delete:
                self._delete(it)
                return True
            if it and event.key() == Qt.Key.Key_F2:
                self._edit(it)
                return True
        return super().eventFilter(obj, event)

    # --- Kontextmenü ---------------------------------------------------------------------------------
    def _menu(self, pos) -> None:
        tr = self.tr
        it = self.tree.itemAt(pos)
        m = QMenu(self)
        folder = ""
        if it and it.data(0, ROLE_KIND) == "fav":
            fid = it.data(0, ROLE_ID)
            _act(m, "log-in", tr("fav.connect"), lambda: self._activated(it))
            _act(m, "pencil", tr("fav.edit"), lambda: self._edit(it))
            _act(m, "copy", tr("fav.duplicate"), lambda: self._duplicate(fid))
            mv = m.addMenu(tr("fav.move_to"))
            mv.setIcon(library_icon("folder", 16))
            mv.addAction(tr("fav.root"), lambda: self._move(fid, ""))
            for f in sorted(self.store.folders(), key=lambda f: self.store.folder_path(f["id"]).lower()):
                mv.addAction(self.store.folder_path(f["id"]), lambda d=f["id"]: self._move(fid, d))
            m.addSeparator()
            _act(m, "trash-2", tr("fav.delete"), lambda: self._delete(it))
            folder = (self.store.get(fid) or {}).get("folder", "")
        elif it:
            folder = it.data(0, ROLE_ID)
            _act(m, "plus", tr("fav.new_here"), lambda: self.new_favorite(False, folder))
            _act(m, "folder-plus", tr("fav.new_subfolder"), lambda: self.new_folder(folder))
            _act(m, "pencil", tr("fav.rename"), lambda: self._edit(it))
            m.addSeparator()
            _act(m, "trash-2", tr("fav.delete_folder"), lambda: self._delete(it))
        else:
            _act(m, "plus", tr("fav.new"), lambda: self.new_favorite(False))
            _act(m, "folder-plus", tr("fav.new_folder"), lambda: self.new_folder())
        m.exec(self.tree.viewport().mapToGlobal(pos))

    # --- Aktionen ------------------------------------------------------------------------------------
    def _dialog(self, fav: dict, title: str) -> dict | None:
        dlg = FavoriteDialog(self, self.tr, self.store, fav, self.option_fields, self.cred_items, title)
        return dlg.result if dlg.exec() == QDialog.DialogCode.Accepted else None

    def new_favorite(self, from_form: bool = True, folder: str | None = None) -> str | None:
        """Neuer Favorit – aus der Anmeldemaske (Stern) oder leer (Plus in der Liste)."""
        if len(self.store.items()) >= MAX_FAVORITES:
            warn(self, self.tr("fav.new"), self.tr("fav.err_max", n=MAX_FAVORITES))
            return None
        draft: dict = {"folder": folder if folder is not None else (self.current() or {}).get("folder", "")}
        if from_form:
            cur = self.capture()
            draft.update(cur)
            draft["name"] = cur.get("server", "")
        v = self._dialog(draft, self.tr("fav.new_title"))
        if not v:
            return None
        fid = self.store.save(v)
        self.select(fid, apply=not from_form)
        return fid

    def new_folder(self, parent: str = "") -> str | None:
        name, ok = QInputDialog.getText(self, self.tr("fav.new_folder"), self.tr("fav.folder_name"))
        if not ok or not name.strip():
            return None
        did = self.store.add_folder(name.strip(), parent)
        self.refresh()
        return did

    def _edit(self, it: QTreeWidgetItem) -> None:
        if it.data(0, ROLE_KIND) == "folder":
            did = it.data(0, ROLE_ID)
            name, ok = QInputDialog.getText(self, self.tr("fav.rename"), self.tr("fav.folder_name"), text=it.text(0))
            if ok and name.strip():
                self.store.rename_folder(did, name.strip())
                self.refresh()
            return
        fid = it.data(0, ROLE_ID)
        fav = self.store.get(fid)
        if not fav:
            return
        v = self._dialog(fav, self.tr("fav.edit_title"))
        if v:
            self.store.save(dict(v, id=fid))
            self.select(fid, apply=fid == self._current)

    def _duplicate(self, fid: str) -> None:
        fav = self.store.get(fid)
        if fav:
            nid = self.store.duplicate(fid, self.tr("fav.copy_of", name=fav["name"]))
            self.refresh(self._current)
            if nid:
                it = self._find(nid)
                if it:
                    self._edit(it)

    def _move(self, fid: str, folder: str) -> None:
        self.store.save({"id": fid, "folder": folder})
        self.refresh()

    def _delete(self, it: QTreeWidgetItem) -> None:
        tr = self.tr
        if it.data(0, ROLE_KIND) == "folder":
            if confirm(self, tr("fav.delete_folder"), tr("fav.delete_folder_q", name=it.text(0))):
                self.store.remove_folder(it.data(0, ROLE_ID))
                self.refresh()
            return
        fid = it.data(0, ROLE_ID)
        if confirm(self, tr("fav.delete"), tr("fav.delete_q", name=it.text(0))):
            self.store.remove(fid)
            if fid == self._current:
                self._current = ""
            self.refresh()

    def _find(self, fid: str) -> QTreeWidgetItem | None:
        def visit(it):
            for i in range(it.childCount()):
                ch = it.child(i)
                if ch.data(0, ROLE_ID) == fid:
                    return ch
                hit = visit(ch)
                if hit:
                    return hit
            return None
        return visit(self.tree.invisibleRootItem())

    # --- Stern am Serverfeld ------------------------------------------------------------------------
    def star_button(self) -> QToolButton:
        b = QToolButton()
        b.setAutoRaise(True)
        b.clicked.connect(self._star_clicked)
        self._star = b
        self._update_star()
        return b

    def _update_star(self, server: str | None = None) -> None:
        if not self._star:
            return
        fav = self.current()
        on = bool(fav)
        self._star.setIcon(library_icon("star", 18, theme.current["accent"] if on else theme.current["muted"]))
        self._star.setToolTip(self.tr("fav.star_on", name=fav["name"]) if on else self.tr("fav.star_off"))

    def _star_clicked(self) -> None:
        fav = self.current()
        if not fav:
            self.new_favorite(from_form=True)
            return
        tr = self.tr
        m = QMenu(self)
        m.addAction(tr("fav.save_over", name=fav["name"]), self.overwrite)
        m.addAction(tr("fav.save_new"), lambda: self.new_favorite(from_form=True))
        m.addAction(tr("fav.edit"), lambda: (it := self._find(fav["id"])) and self._edit(it))
        m.exec(self._star.mapToGlobal(self._star.rect().bottomLeft()))

    def overwrite(self) -> None:
        fav = self.current()
        if not fav:
            return
        cur = self.capture()
        if not confirm(self, self.tr("fav.save_tip"), self.tr("fav.overwrite_q", name=fav["name"])):
            return
        upd = {"id": fav["id"], "server": cur.get("server") or fav["server"], "login": cur.get("login") or {},
               "options": cur.get("options") or {}}
        if "password" in cur:
            upd["password"] = cur["password"]
        self.store.save(upd)
        self.refresh(fav["id"])
