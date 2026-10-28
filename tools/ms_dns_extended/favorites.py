"""Server-Favoriten: Server mit Anmeldeart und Verbindungseinstellungen speichern und auf der Anmeldeseite wählen.

Gespeichert in der Tool-Einstellung "favorites" (nicht im Tresor, enthält keine Passwörter):

    {"version": 1, "last": "<id>", "items": [
        {"id": "f-1a2b3c4d", "name": "Rechenzentrum", "server": "rz-dhcp01", "note": "",
         "login": {"mode": "sso" | "vault" | "manual", "user": "...",            # user nur bei "manual"
                   "cred": {"ref": "..."} | {"name": "...", "username": "..."}},  # nur bei "vault", Verweis!
         "options": {...},     # toolspezifisch (Partner verbinden, Prüfung, …)
         "ai": {}}]}           # reserviert für die KI-Einstellungen je Server

Unbekannte Schlüssel (z. B. aus neueren Versionen) bleiben beim Speichern erhalten. Weitere Abschnitte
liest und schreibt man mit section()/set_section(). Die Datei ist in beiden Server-Tools gleich
(Kopie, damit die Tools unabhängig bleiben).
"""

from __future__ import annotations

import copy
import uuid

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem, QMenu, QToolButton, QVBoxLayout,
    QWidget,
)

from omniwrench.ui.widgets import library_icon, make_button

from .ui_base import FormDialog, confirm, help_icon, warn

KEY = "favorites"
VERSION = 1
MAX_FAVORITES = 100
MODES = ("sso", "vault", "manual")


def cred_key(item: dict | None) -> dict:
    """Woran ein gespeicherter Zugang wiedererkannt wird – nie das Passwort."""
    if not item:
        return {}
    if item.get("ref"):
        return {"ref": item["ref"]}
    return {"name": item.get("name", ""), "username": item.get("username", "")}


def match_cred(items: list[dict], key: dict | None) -> int:
    """Index des Zugangs aus der Liste des Anmeldefelds, der zum Verweis passt (-1 = nicht mehr vorhanden)."""
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
    """Liest und schreibt die Favoritenliste. Gibt immer Kopien heraus (ToolSettingsStore vergleicht Werte)."""

    def __init__(self, settings):
        self.settings = settings

    def _data(self) -> dict:
        raw = self.settings.get(KEY)
        data = copy.deepcopy(raw) if isinstance(raw, dict) else {}
        items = [i for i in data.get("items") or [] if isinstance(i, dict) and i.get("id")]
        for i in items:
            i.setdefault("name", i.get("server", ""))
            i.setdefault("server", "")
            i.setdefault("note", "")
            login = i.get("login") if isinstance(i.get("login"), dict) else {}
            if login.get("mode") not in MODES:
                login["mode"] = "sso"
            i["login"] = login
            i["options"] = i.get("options") if isinstance(i.get("options"), dict) else {}
            i["ai"] = i.get("ai") if isinstance(i.get("ai"), dict) else {}
        data["items"] = items
        data["version"] = max(int(data.get("version") or VERSION), VERSION)
        data.setdefault("last", "")
        return data

    def _write(self, data: dict) -> None:
        self.settings.set(KEY, data)

    def items(self) -> list[dict]:
        return self._data()["items"]

    def get(self, fid: str) -> dict | None:
        return next((i for i in self.items() if i["id"] == fid), None)

    def find_name(self, name: str) -> dict | None:
        n = name.strip().lower()
        return next((i for i in self.items() if i["name"].strip().lower() == n), None)

    def save(self, fav: dict) -> str:
        """Legt an (ohne/unbekannte id) oder führt mit dem vorhandenen Favoriten zusammen. Liefert die id."""
        data = self._data()
        fid = fav.get("id") or ""
        for idx, cur in enumerate(data["items"]):
            if cur["id"] == fid:
                data["items"][idx] = _merge(cur, fav)
                break
        else:
            if len(data["items"]) >= MAX_FAVORITES:
                raise ValueError("too many favorites")
            fid = "f-" + uuid.uuid4().hex[:8]
            new = _merge({"name": "", "server": "", "note": "", "login": {"mode": "sso"}, "options": {}, "ai": {}}, fav)
            new["id"] = fid
            data["items"].append(new)
        self._write(data)
        return fid

    def remove(self, fid: str) -> None:
        data = self._data()
        data["items"] = [i for i in data["items"] if i["id"] != fid]
        if data["last"] == fid:
            data["last"] = ""
        self._write(data)

    def move(self, fid: str, delta: int) -> None:
        data = self._data()
        ids = [i["id"] for i in data["items"]]
        if fid not in ids:
            return
        a = ids.index(fid)
        b = min(max(a + delta, 0), len(ids) - 1)
        data["items"].insert(b, data["items"].pop(a))
        self._write(data)

    def last(self) -> str:
        return self._data()["last"]

    def set_last(self, fid: str) -> None:
        data = self._data()
        if data["last"] != fid:
            data["last"] = fid
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


# --- Oberfläche -------------------------------------------------------------------------------------------

def _option_fields(tr, extra_fields: list[dict], options: dict) -> list[dict]:
    """extra_fields: FormDialog-Felder für Optionen, die es nur im Favoriten gibt. Typ "list" = kommagetrennt."""
    out = []
    for f in extra_fields:
        g = dict(f, key="opt." + f["key"])
        v = options.get(f["key"], f.get("value"))
        if f.get("type") == "list":
            g["type"] = "text"
            v = ", ".join(v or [])
        g["value"] = v
        out.append(g)
    return out


def _options_from(values: dict, extra_fields: list[dict]) -> dict:
    out = {}
    for f in extra_fields:
        v = values.get("opt." + f["key"])
        if f.get("type") == "list":
            seen: list[str] = []
            for s in (v or "").replace(";", ",").replace("\n", ",").split(","):
                s = s.strip()
                if s and s.lower() not in (x.lower() for x in seen):
                    seen.append(s)
            v = seen
        out[f["key"]] = v
    return out


def edit_dialog(parent, tr, store: FavoriteStore, fav: dict, extra_fields: list[dict], title: str) -> dict | None:
    """Name, Server, Notiz und die zusätzlichen Optionen eines Favoriten. Liefert die geänderten Felder."""
    fields = [{"key": "name", "label": tr("fav.name"), "value": fav.get("name", "")},
              {"key": "server", "label": tr("fav.server"), "value": fav.get("server", "")},
              {"key": "note", "label": tr("fav.note"), "value": fav.get("note", "")}]
    fields += _option_fields(tr, extra_fields, fav.get("options") or {})

    def validate(v: dict) -> str | None:
        if not v["name"]:
            return tr("fav.err_name")
        if not v["server"]:
            return tr("fav.err_server")
        other = store.find_name(v["name"])
        if other and other["id"] != fav.get("id"):
            return tr("fav.err_exists", name=v["name"])
        return None

    v = FormDialog.ask(parent, title, fields, tr, hint=tr("fav.hint"), validate=validate)
    if v is None:
        return None
    return {"name": v["name"], "server": v["server"], "note": v["note"], "options": _options_from(v, extra_fields)}


def summary(tr, fav: dict) -> str:
    """Kurzbeschreibung für Tooltips und die Verwaltung."""
    login = fav.get("login") or {}
    mode = login.get("mode", "sso")
    if mode == "manual":
        how = tr("fav.mode_manual", user=login.get("user") or "–")
    elif mode == "vault":
        c = login.get("cred") or {}
        how = tr("fav.mode_vault", cred=c.get("name") or c.get("username") or c.get("ref") or "–")
    else:
        how = tr("fav.mode_sso")
    lines = [tr("fav.server") + ": " + (fav.get("server") or "–"), how]
    if fav.get("note"):
        lines.append(fav["note"])
    return "\n".join(lines)


class ManageDialog(QDialog):
    """Liste aller Favoriten: bearbeiten, Reihenfolge ändern, löschen."""

    def __init__(self, parent, tr, store: FavoriteStore, extra_fields: list[dict]):
        super().__init__(parent)
        self.tr, self.store, self.extra_fields = tr, store, extra_fields
        self.setWindowTitle(tr("fav.manage_title"))
        self.setMinimumSize(560, 380)
        lay = QVBoxLayout(self)
        row = QHBoxLayout()
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _i: self._edit())
        self.list.currentRowChanged.connect(lambda _r: self._update_buttons())
        row.addWidget(self.list, 1)
        col = QVBoxLayout()
        self.btns = {}
        for key, slot in (("edit", self._edit), ("up", lambda: self._move(-1)), ("down", lambda: self._move(1)),
                          ("delete", self._delete)):
            b = make_button(tr("fav." + key), danger=key == "delete", on_click=slot)
            self.btns[key] = b
            col.addWidget(b)
        col.addStretch(1)
        row.addLayout(col)
        lay.addLayout(row)
        bb = QDialogButtonBox()
        bb.addButton(tr("ui.close"), QDialogButtonBox.ButtonRole.RejectRole)
        bb.rejected.connect(self.accept)
        hl = QHBoxLayout()
        hl.addWidget(help_icon(tr("fav.manage_hint")))
        hl.addWidget(bb, 1)
        lay.addLayout(hl)
        self._fill()

    def _fill(self, select: str | None = None) -> None:
        self.list.clear()
        for fav in self.store.items():
            it = QListWidgetItem(f"{fav['name']}  —  {fav['server']}")
            it.setData(Qt.ItemDataRole.UserRole, fav["id"])
            it.setToolTip(summary(self.tr, fav))
            self.list.addItem(it)
            if fav["id"] == select:
                self.list.setCurrentItem(it)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _current(self) -> str | None:
        it = self.list.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def _update_buttons(self) -> None:
        row, n = self.list.currentRow(), self.list.count()
        for key in ("edit", "delete"):
            self.btns[key].setEnabled(row >= 0)
        self.btns["up"].setEnabled(row > 0)
        self.btns["down"].setEnabled(0 <= row < n - 1)

    def _edit(self) -> None:
        fid = self._current()
        fav = self.store.get(fid) if fid else None
        if not fav:
            return
        v = edit_dialog(self, self.tr, self.store, fav, self.extra_fields, self.tr("fav.edit_title"))
        if v:
            self.store.save(dict(v, id=fid))
            self._fill(fid)

    def _move(self, delta: int) -> None:
        fid = self._current()
        if fid:
            self.store.move(fid, delta)
            self._fill(fid)

    def _delete(self) -> None:
        fid = self._current()
        fav = self.store.get(fid) if fid else None
        if fav and confirm(self, self.tr("fav.delete"), self.tr("fav.delete_q", name=fav["name"])):
            self.store.remove(fid)
            self._fill()


class FavoritesBar(QWidget):
    """[ Favorit ▼ ] [☆ ▾] [Verwalten] – Auswahl füllt die Anmeldemaske über das Signal applied(fav).

    capture() liefert {"server", "login", "options"} aus der Anmeldemaske; extra_fields sind Optionen,
    die nur im Favoriten-Dialog bearbeitet werden (FormDialog-Felder, zusätzlich Typ "list").
    """

    applied = Signal(object)     # Favorit (dict) oder None, wenn "kein Favorit" gewählt wurde

    def __init__(self, tr, store: FavoriteStore, capture, extra_fields: list[dict] | None = None, parent=None):
        super().__init__(parent)
        self.tr, self.store, self.capture = tr, store, capture
        self.extra_fields = extra_fields or []
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self.combo = QComboBox()
        self.combo.setMinimumWidth(200)
        self.combo.setToolTip(tr("fav.combo_tip"))
        self.combo.currentIndexChanged.connect(self._selected)
        lay.addWidget(self.combo, 1)
        self.save_btn = QToolButton()
        self.save_btn.setIcon(library_icon("star", 16))
        self.save_btn.setToolTip(tr("fav.save_tip"))
        self.save_btn.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.save_btn.clicked.connect(self._save_clicked)
        self.menu = QMenu(self.save_btn)
        self.act_new = self.menu.addAction(tr("fav.save_new"))
        self.act_new.triggered.connect(self.save_new)
        self.act_over = self.menu.addAction(tr("fav.save_over"))
        self.act_over.triggered.connect(self.overwrite)
        self.save_btn.setMenu(self.menu)
        lay.addWidget(self.save_btn)
        self.manage_btn = make_button(tr("fav.manage"), on_click=lambda: self.manage())
        lay.addWidget(self.manage_btn)
        self.refresh()

    # --- Liste ----------------------------------------------------------------------------------------
    def refresh(self, select: str | None = None) -> None:
        if select is None:
            select = self.current_id() or ""
        self.combo.blockSignals(True)
        self.combo.clear()
        self.combo.addItem(self.tr("fav.none"), "")
        for fav in self.store.items():
            self.combo.addItem(library_icon("star", 16), f"{fav['name']}  —  {fav['server']}", fav["id"])
            self.combo.setItemData(self.combo.count() - 1, summary(self.tr, fav), Qt.ItemDataRole.ToolTipRole)
        self.combo.setCurrentIndex(max(0, self.combo.findData(select)))
        self.combo.blockSignals(False)
        self._update_actions()

    def current_id(self) -> str:
        return self.combo.currentData() or ""

    def current(self) -> dict | None:
        fid = self.current_id()
        return self.store.get(fid) if fid else None

    def select(self, fid: str, apply: bool = True) -> None:
        idx = max(0, self.combo.findData(fid or ""))
        if not apply:
            self.combo.blockSignals(True)
        self.combo.setCurrentIndex(idx)
        self.combo.blockSignals(False)
        if not apply:
            self.store.set_last(self.current_id())
            self._update_actions()

    def restore(self) -> None:
        """Beim Start den zuletzt gewählten Favoriten wieder einsetzen (füllt die Maske)."""
        fid = self.store.last()
        if fid and self.store.get(fid) and fid != self.current_id():
            self.select(fid)

    def server_edited(self, server: str) -> None:
        """Wird der Server von Hand geändert, gilt der Favorit nicht mehr (Auswahl auf „kein Favorit“)."""
        fav = self.current()
        if fav and fav["server"].strip().lower() != server.strip().lower():
            self.select("", apply=False)

    def _selected(self, _idx: int) -> None:
        fid = self.current_id()
        self.store.set_last(fid)
        self._update_actions()
        self.applied.emit(self.store.get(fid) if fid else None)

    def _update_actions(self) -> None:
        fav = self.current()
        self.act_over.setEnabled(bool(fav))
        self.act_over.setText(self.tr("fav.save_over", name=fav["name"]) if fav else self.tr("fav.save_over", name="–"))
        self.manage_btn.setEnabled(bool(self.store.items()))

    # --- Speichern ------------------------------------------------------------------------------------
    def _save_clicked(self) -> None:
        if self.current():
            self.save_btn.showMenu()
        else:
            self.save_new()

    def save_new(self) -> str | None:
        cur = self.capture()
        if not cur.get("server"):
            warn(self, self.tr("fav.save_new"), self.tr("fav.err_server"))
            return None
        name = cur["server"]
        n = 2
        while self.store.find_name(name):
            name = f"{cur['server']} ({n})"
            n += 1
        draft = dict(cur, name=name, note="")
        v = edit_dialog(self, self.tr, self.store, draft, self.extra_fields, self.tr("fav.new_title"))
        if not v:
            return None
        fav = dict(cur)
        fav.update(name=v["name"], server=v["server"], note=v["note"])
        fav["options"] = dict(cur.get("options") or {}, **v["options"])
        try:
            fid = self.store.save(fav)
        except ValueError:
            warn(self, self.tr("fav.save_new"), self.tr("fav.err_max", n=MAX_FAVORITES))
            return None
        self.refresh(fid)
        self.store.set_last(fid)
        return fid

    def overwrite(self) -> None:
        fav = self.current()
        if not fav:
            return
        cur = self.capture()
        if not confirm(self, self.tr("fav.save_tip"), self.tr("fav.overwrite_q", name=fav["name"])):
            return
        self.store.save({"id": fav["id"], "server": cur.get("server") or fav["server"], "login": cur.get("login") or {},
                         "options": cur.get("options") or {}})
        self.refresh(fav["id"])

    def manage(self) -> None:
        cur = self.current_id()
        ManageDialog(self, self.tr, self.store, self.extra_fields).exec()
        if cur and not self.store.get(cur):
            cur = ""
        self.refresh(cur)
        if not cur:
            self.store.set_last("")
