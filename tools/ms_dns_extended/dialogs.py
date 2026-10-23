"""Dialoge: Eintrag anlegen/bearbeiten, Zone anlegen, Anmeldedaten, DHCP-Server für den Abgleich."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit,
    QRadioButton, QSizePolicy, QSpinBox, QStackedWidget, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from . import dnsutil as du
from .ui_base import MONO, FormDialog, help_icon


def _buttons(dlg: QDialog, tr, ok_label: str | None = None) -> QDialogButtonBox:
    bb = QDialogButtonBox()
    ok = bb.addButton(ok_label or tr("ui.ok"), QDialogButtonBox.ButtonRole.AcceptRole)
    ok.setDefault(True)
    bb.addButton(tr("ui.cancel"), QDialogButtonBox.ButtonRole.RejectRole)
    bb.rejected.connect(dlg.reject)
    return bb


def _err_label() -> QLabel:
    lbl = QLabel("")
    lbl.setWordWrap(True)
    lbl.setStyleSheet(f"color:{theme.current['danger']};")
    lbl.hide()
    return lbl


# --- Eintrag ------------------------------------------------------------------------------------------

class RecordDialog(QDialog):
    """Ein Eintrag je Typ. Liefert (Rec, {"ptr": bool}) über result_rec/result_opts."""

    def __init__(self, parent, tr, zone: str, rec: du.Rec | None = None, rtype: str | None = None,
                 reverse_ok=None, name: str = ""):
        super().__init__(parent)
        self.tr = tr
        self.zone = du.norm(zone)
        self.rec = rec
        self.reverse_ok = reverse_ok or (lambda ip: False)
        self.result_rec: du.Rec | None = None
        self.result_opts: dict = {}
        self.setWindowTitle(tr("rec.edit_title" if rec else "rec.new_title", zone=self.zone))
        self.setMinimumWidth(560)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.type = QComboBox()
        types = du.EDIT_TYPES
        if du.is_reverse_zone(self.zone):
            types = ("PTR",) + tuple(t for t in types if t not in ("PTR", "A", "AAAA"))
        for t in types:
            self.type.addItem(f"{t} – {tr('rtype.' + t)}", t)
        cur = (rec.type if rec else rtype) or types[0]
        self.type.setCurrentIndex(max(0, self.type.findData(cur)))
        self.type.setEnabled(rec is None)
        form.addRow(tr("rec.type"), self.type)
        nrow = QHBoxLayout()
        self.name = QLineEdit(rec.node if rec else name)
        self.name.setPlaceholderText(tr("rec.name_ph"))
        nrow.addWidget(self.name, 1)
        self.suffix = QLabel("." + self.zone)
        self.suffix.setStyleSheet(f"color:{theme.current['muted']};")
        nrow.addWidget(self.suffix)
        form.addRow(tr("rec.name"), nrow)
        self.fqdn = QLabel("")
        self.fqdn.setStyleSheet(f"color:{theme.current['muted']};")
        self.fqdn.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("", self.fqdn)
        self.stack = QStackedWidget()
        self.fields: dict[str, dict[str, QWidget]] = {}
        for t in du.EDIT_TYPES:
            w = QWidget()
            f = QFormLayout(w)
            f.setContentsMargins(0, 0, 0, 0)
            f.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
            ws: dict[str, QWidget] = {}
            for key in du.DATA_FIELDS[t]:
                if key in ("pref", "priority", "weight", "port"):
                    e = QSpinBox()
                    e.setRange(0, 65535)
                    e.setValue({"pref": 10, "priority": 0, "weight": 100, "port": 389}.get(key, 0))
                elif key == "text":
                    e = QPlainTextEdit()
                    e.setFont(MONO)
                    e.setMinimumHeight(90)
                else:
                    e = QLineEdit()
                    e.setPlaceholderText(tr(f"rec.ph.{t}.{key}"))
                    e.setFont(MONO)
                ws[key] = e
                f.addRow(tr(f"rec.f.{key}" if t not in ("CNAME", "PTR", "NS", "MX", "SRV") or key != "host"
                            else f"rec.f.host.{t}"), e)
            self.fields[t] = ws
            self.stack.addWidget(w)
        form.addRow(self.stack)
        trow = QHBoxLayout()
        self.ttl = QLineEdit(du.fmt_ttl(rec.ttl if rec else 3600))
        self.ttl.setMaximumWidth(160)
        trow.addWidget(self.ttl)
        trow.addWidget(help_icon(tr("rec.ttl_hint")))
        trow.addStretch(1)
        form.addRow(tr("rec.ttl"), trow)
        lay.addLayout(form)
        self.dynamic = QCheckBox(tr("rec.dynamic"))
        self.dynamic.setChecked(bool(rec and rec.dynamic))
        drow = QHBoxLayout()
        drow.addWidget(self.dynamic)
        drow.addWidget(help_icon(tr("rec.dynamic_hint")))
        drow.addStretch(1)
        lay.addLayout(drow)
        self.ptr = QCheckBox(tr("rec.ptr"))
        prow = QHBoxLayout()
        prow.addWidget(self.ptr)
        self.ptr_hint = help_icon(tr("rec.ptr_hint"))
        prow.addWidget(self.ptr_hint)
        prow.addStretch(1)
        lay.addLayout(prow)
        self.err = _err_label()
        lay.addWidget(self.err)
        bb = _buttons(self, tr)
        bb.accepted.connect(self._accept)
        lay.addWidget(bb)
        if rec:
            for key, e in self.fields.get(rec.type, {}).items():
                v = rec.data.get(key, "")
                if isinstance(e, QSpinBox):
                    e.setValue(int(v or 0))
                elif isinstance(e, QPlainTextEdit):
                    e.setPlainText(str(v))
                else:
                    e.setText(str(v))
        self.type.currentIndexChanged.connect(self._type_changed)
        self.name.textChanged.connect(self._update)
        for ws in self.fields.values():
            for e in ws.values():
                if isinstance(e, QLineEdit):
                    e.textChanged.connect(self._update)
        self._type_changed()

    def current_type(self) -> str:
        return self.type.currentData()

    def _type_changed(self) -> None:
        t = self.current_type()
        self.stack.setCurrentIndex(du.EDIT_TYPES.index(t))
        # Nur die sichtbare Seite bestimmt die Höhe (sonst Leerraum durch das TXT-Feld)
        for i in range(self.stack.count()):
            pol = QSizePolicy.Policy.Preferred if i == self.stack.currentIndex() else QSizePolicy.Policy.Ignored
            self.stack.widget(i).setSizePolicy(pol, pol)
        self.stack.adjustSize()
        self.adjustSize()
        is_addr = t in ("A", "AAAA")
        self.ptr.setVisible(is_addr)
        self.ptr_hint.setVisible(is_addr)
        self._update()

    def _update(self) -> None:
        tr = self.tr
        node = self.name.text().strip()
        self.fqdn.setText(tr("rec.fqdn", name=du.fqdn(node, self.zone)))
        t = self.current_type()
        if t in ("A", "AAAA"):
            ip = du.parse_ip(self.fields[t]["ip"].text())
            ok = bool(ip) and self.reverse_ok(ip)
            self.ptr.setEnabled(ok)
            if not ok:
                self.ptr.setChecked(False)
            elif self.rec is None and not self.ptr.property("touched"):
                self.ptr.setChecked(True)
            self.ptr.setToolTip("" if ok else tr("rec.ptr_no_zone"))

    def values(self) -> dict:
        t = self.current_type()
        out = {}
        for key, e in self.fields[t].items():
            if isinstance(e, QSpinBox):
                out[key] = e.value()
            elif isinstance(e, QPlainTextEdit):
                # Zeilenumbrüche entfallen (z. B. umbrochen eingefügte DKIM-Schlüssel); lange Texte teilt txt_quote
                out[key] = "".join(x.strip() for x in e.toPlainText().splitlines())
            else:
                out[key] = e.text().strip()
        return out

    def _accept(self) -> None:
        tr = self.tr
        t = self.current_type()
        node = self.name.text().strip()
        if node and node != "@" and not du.valid_hostname(node.rstrip("."), allow_wildcard=True):
            return self._fail(tr("val.name"))
        if t == "CNAME" and node in ("", "@"):
            return self._fail(tr("val.cname_apex"))
        d = self.values()
        msg = du.validate_data(t, d, tr)
        if msg:
            return self._fail(msg)
        try:
            ttl = du.parse_ttl(self.ttl.text())
        except ValueError:
            return self._fail(tr("val.ttl"))
        name = du.fqdn(node, self.zone)
        if not du.in_zone(name, self.zone):
            return self._fail(tr("val.outside", zone=self.zone))
        rec = du.Rec(zone=self.zone, name=name, type=t, data=du.clean_data(t, d), ttl=ttl,
                     ts=(self.rec.ts if self.rec and self.rec.dynamic else du.now_utc()) if self.dynamic.isChecked() else None)
        self.result_rec = rec
        self.result_opts = {"ptr": self.ptr.isVisible() and self.ptr.isEnabled() and self.ptr.isChecked()}
        self.accept()

    def _fail(self, text: str) -> None:
        self.err.setText(text)
        self.err.show()

    @classmethod
    def ask(cls, parent, tr, zone, rec=None, rtype=None, reverse_ok=None, name=""):
        dlg = cls(parent, tr, zone, rec, rtype, reverse_ok, name)
        dlg.ptr.toggled.connect(lambda _on: dlg.ptr.setProperty("touched", True))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_rec, dlg.result_opts
        return None


# --- Zone anlegen -------------------------------------------------------------------------------------

class ZoneDialog(QDialog):
    def __init__(self, parent, tr, ds_available: bool):
        super().__init__(parent)
        self.tr = tr
        self.result_values: dict | None = None
        self.setWindowTitle(tr("zone.new_title"))
        self.setMinimumWidth(580)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        self.kind = QComboBox()
        for z in (du.ZONE_PRIMARY, du.ZONE_SECONDARY, du.ZONE_STUB, du.ZONE_FORWARDER):
            self.kind.addItem(tr(f"ztype.{du.ZONE_TYPE_KEYS[z]}"), z)
        form.addRow(tr("zone.kind"), self.kind)
        dirrow = QHBoxLayout()
        self.fwd = QRadioButton(tr("zone.forward"))
        self.rev = QRadioButton(tr("zone.reverse"))
        self.fwd.setChecked(True)
        dirrow.addWidget(self.fwd)
        dirrow.addWidget(self.rev)
        dirrow.addStretch(1)
        form.addRow(tr("zone.direction"), dirrow)
        self.name = QLineEdit()
        self.name.setPlaceholderText(tr("zone.name_ph"))
        form.addRow(tr("zone.name"), self.name)
        self.network = QLineEdit()
        self.network.setPlaceholderText(tr("zone.network_ph"))
        self.network_row = QWidget()
        nrow = QHBoxLayout(self.network_row)
        nrow.setContentsMargins(0, 0, 0, 0)
        nrow.addWidget(self.network, 1)
        nrow.addWidget(help_icon(tr("zone.network_hint")))
        form.addRow(tr("zone.network"), self.network_row)
        self.result_name = QLabel("")
        self.result_name.setStyleSheet(f"color:{theme.current['muted']};")
        form.addRow("", self.result_name)
        self.ds = QCheckBox(tr("zone.ds"))
        self.ds.setChecked(ds_available)
        self.ds.setEnabled(ds_available)
        self.ds.setToolTip("" if ds_available else tr("zone.ds_unavailable"))
        form.addRow("", self.ds)
        self.file = QLineEdit()
        self.file.setPlaceholderText(tr("zone.file_ph"))
        form.addRow(tr("zone.file"), self.file)
        self.masters = QLineEdit()
        self.masters.setPlaceholderText(tr("zone.masters_ph"))
        form.addRow(tr("zone.masters"), self.masters)
        self.admin = QLineEdit()
        self.admin.setPlaceholderText(tr("zone.admin_ph"))
        form.addRow(tr("zone.admin"), self.admin)
        self.updates = QComboBox()
        for v in (du.UPDATE_SECURE, du.UPDATE_ANY, du.UPDATE_NONE):
            self.updates.addItem(tr(f"upd.{v}"), v)
        form.addRow(tr("zone.updates"), self.updates)
        self.form = form
        lay.addLayout(form)
        self.err = _err_label()
        lay.addWidget(self.err)
        bb = _buttons(self, tr, tr("zone.create"))
        bb.accepted.connect(self._accept)
        lay.addWidget(bb)
        for w in (self.kind,):
            w.currentIndexChanged.connect(self._update)
        for w in (self.fwd, self.rev, self.ds):
            w.toggled.connect(self._update)
        self.name.textChanged.connect(self._update)
        self.network.textChanged.connect(self._update)
        self._update()

    def _set_row(self, w: QWidget, on: bool) -> None:
        self.form.setRowVisible(w, on)

    def _zone_name(self) -> str:
        if self.rev.isChecked() and self.network.text().strip():
            try:
                return du.reverse_zone_for(self.network.text())
            except ValueError:
                return ""
        return du.norm(self.name.text())

    def _update(self) -> None:
        k = self.kind.currentData()
        rev = self.rev.isChecked()
        self.name.setEnabled(not rev or not self.network.text().strip())
        self._set_row(self.network_row, rev)
        self._set_row(self.masters, k != du.ZONE_PRIMARY)
        self._set_row(self.admin, k == du.ZONE_PRIMARY)
        self._set_row(self.updates, k == du.ZONE_PRIMARY)
        self._set_row(self.file, not self.ds.isChecked() and k != du.ZONE_FORWARDER)
        if k == du.ZONE_SECONDARY:
            self.ds.setChecked(False)
            self.ds.setEnabled(False)
        elif self.ds.toolTip() == "":
            self.ds.setEnabled(True)
        n = self._zone_name()
        self.result_name.setText(self.tr("zone.result_name", name=n) if n else "")
        if not self.file.isModified():
            self.file.setText(f"{n}.dns" if n else "")

    def _accept(self) -> None:
        tr = self.tr
        name = self._zone_name()
        if not name:
            return self._fail(tr("val.zone_network") if self.rev.isChecked() else tr("val.zone_name"))
        if not du.valid_hostname(name, allow_wildcard=False):
            return self._fail(tr("val.zone_name"))
        k = self.kind.currentData()
        masters = [x for x in self.masters.text().replace(";", ",").replace(" ", ",").split(",") if x.strip()]
        bad = [m for m in masters if not du.parse_ip(m)]
        if bad:
            return self._fail(tr("val.masters", list=", ".join(bad)))
        if k != du.ZONE_PRIMARY and not masters:
            return self._fail(tr("val.masters_needed"))
        self.result_values = {"name": name, "type": k, "ds": self.ds.isChecked() and k != du.ZONE_SECONDARY,
                              "file": self.file.text().strip() if not self.ds.isChecked() else "",
                              "masters": [du.parse_ip(m) for m in masters], "admin": self.admin.text().strip(),
                              "updates": self.updates.currentData() if k == du.ZONE_PRIMARY else None}
        self.accept()

    def _fail(self, text: str) -> None:
        self.err.setText(text)
        self.err.show()

    @classmethod
    def ask(cls, parent, tr, ds_available: bool) -> dict | None:
        dlg = cls(parent, tr, ds_available)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            return dlg.result_values
        return None


# --- Kleine Abfragen ----------------------------------------------------------------------------------

def credentials_dialog(parent, tr, server: str, user: str = "") -> tuple[str, str] | None:
    v = FormDialog.ask(parent, tr("cred.title", server=server),
                       [{"key": "user", "label": tr("login.user"), "value": user},
                        {"key": "password", "label": tr("login.password"), "type": "password"}], tr,
                       hint=tr("cred.hint"), validate=lambda x: None if x["user"] else tr("login.err_user"))
    return (v["user"], v["password"]) if v else None


def add_server_dialog(parent, tr, suggestions: list[str], user: str) -> dict | None:
    fields = [{"key": "server", "label": tr("srv.add_server"), "type": "combo", "editable": True,
               "items": suggestions, "value": suggestions[0] if suggestions else ""},
              {"key": "mode", "label": tr("srv.add_login"), "type": "combo",
               "items": [("same", tr("srv.add_same", user=user or tr("login.current"))), ("other", tr("srv.add_other"))]},
              {"key": "user", "label": tr("login.user"), "value": user},
              {"key": "password", "label": tr("login.password"), "type": "password"}]
    return FormDialog.ask(parent, tr("srv.add_title"), fields, tr, hint=tr("srv.add_hint"),
                          validate=lambda x: None if x["server"] else tr("login.err_server"))


def dhcp_dialog(parent, tr, server: str, user: str) -> dict | None:
    fields = [{"key": "server", "label": tr("dhcp.server"), "value": server},
              {"key": "mode", "label": tr("srv.add_login"), "type": "combo",
               "items": [("same", tr("dhcp.same")), ("other", tr("srv.add_other"))]},
              {"key": "user", "label": tr("login.user"), "value": user},
              {"key": "password", "label": tr("login.password"), "type": "password"}]
    return FormDialog.ask(parent, tr("dhcp.title"), fields, tr, hint=tr("dhcp.hint"),
                          validate=lambda x: None if x["server"] else tr("login.err_server"))


def ttl_dialog(parent, tr, ttl: int) -> int | None:
    def check(v):
        try:
            du.parse_ttl(v["ttl"])
        except ValueError:
            return tr("val.ttl")
        return None
    v = FormDialog.ask(parent, tr("bulk.ttl_title"), [{"key": "ttl", "label": tr("rec.ttl"), "value": du.fmt_ttl(ttl)}],
                       tr, hint=tr("rec.ttl_hint"), validate=check)
    return du.parse_ttl(v["ttl"]) if v else None


def delete_word_dialog(parent, tr, title: str, text: str, word: str) -> bool:
    v = FormDialog.ask(parent, title, [{"key": "w", "label": tr("del.type_word", word=word)}], tr, hint=text,
                       validate=lambda x: None if x["w"].strip().lower() == word.lower() else tr("del.word_wrong", word=word),
                       ok_label=tr("del.ok"))
    return bool(v)
