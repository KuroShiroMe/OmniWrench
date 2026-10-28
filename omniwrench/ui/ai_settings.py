"""Einstellungen der KI-Assistenten: Verbindungen, Hinzufügen-Dialog und Datenablage."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QTimer, Qt, QUrl
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QSplitter, QStackedWidget, QTableWidget,
    QTableWidgetItem, QToolButton, QVBoxLayout, QWidget,
)

from omniwrench.ai import adapters, oauth, providers, storage
from omniwrench.ai.chat import error_text
from omniwrench.ai.connections import Connection, ConnectionStore
from omniwrench.core import credentials
from omniwrench.core.i18n import tr

from . import theme
from .credentials import CredentialPickerDialog
from .scaling import fit_to_screen
from .widgets import label, make_button
from .workers import run_async

CAPS = ("chat", "tools", "vision", "image", "music", "video", "speech", "web_search")
REGIONS = ("EU", "LOCAL")


def provider_name(p: providers.Provider | None, fallback: str = "") -> str:
    if p is None:
        return fallback
    return tr(f"ai.provider.{p.id}", default=p.name)


def caps_text(p: providers.Provider | None) -> str:
    if p is None:
        return ""
    return ", ".join(tr(f"ai.cap.{c}") for c in p.capabilities if c in CAPS)


def auth_text(kind: str) -> str:
    return tr(f"ai.auth.{kind}")


def note_text(p: providers.Provider) -> str:
    parts = []
    if p.removed or p.status != "active":
        parts.append(tr(f"ai.note.{p.status_note}") if p.status_note else tr("ai.status.unavailable"))
    if p.note:
        parts.append(tr(f"ai.note.{p.note}"))
    return "\n".join(parts)


def ensure_catalog_update(settings) -> None:
    """Anbieterliste aus den Store-Repositories im Hintergrund aktualisieren."""
    urls = [r.get("url", "") for r in settings.get("repositories", []) if r.get("enabled", True) and r.get("url")]
    run_async(lambda: providers.update_from_store(urls), lambda _: None, lambda _: None)


# =============================================================== Verbindungen
class AIConnectionsPage(QWidget):
    """Liste der verbundenen Assistenten. Änderungen gelten sofort (Anmeldungen laufen live)."""

    def __init__(self, settings, vault, parent=None):
        super().__init__(parent)
        self.store = ConnectionStore(settings, vault)
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.conn.title"), "CardTitle"))
        lay.addWidget(label(tr("ai.conn.hint"), "Muted", wrap=True))
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("ai.conn.col_name"), tr("ai.conn.col_provider"),
                                              tr("ai.conn.col_auth"), tr("ai.conn.col_caps"),
                                              tr("ai.conn.col_status")])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        lay.addWidget(self.table, 1)
        row = QHBoxLayout()
        row.addWidget(make_button("＋ " + tr("ai.conn.add"), primary=True, on_click=self.add))
        row.addWidget(make_button(tr("ai.conn.edit"), on_click=self.edit))
        row.addWidget(make_button("★ " + tr("ai.conn.make_primary"), on_click=self.make_primary))
        up = make_button("▲", on_click=lambda: self._move(-1))
        down = make_button("▼", on_click=lambda: self._move(1))
        for b in (up, down):
            b.setFixedWidth(36)
        row.addWidget(up)
        row.addWidget(down)
        row.addStretch()
        row.addWidget(make_button(tr("common.remove"), danger=True, on_click=self.remove))
        lay.addLayout(row)
        ask_row = QHBoxLayout()
        ask_row.addWidget(QLabel(tr("ai.ask.mode")))
        self.ask_mode = QComboBox()
        for mode in ("primary", "active", "ask"):
            self.ask_mode.addItem(tr(f"ai.ask.mode_{mode}"), mode)
        self.ask_mode.setCurrentIndex(max(self.ask_mode.findData(settings.get("ai_ask_mode", "primary")), 0))
        self.ask_mode.currentIndexChanged.connect(
            lambda *_: settings.set("ai_ask_mode", self.ask_mode.currentData()))
        ask_row.addWidget(self.ask_mode, 1)
        lay.addLayout(ask_row)
        self.catalog_info = label("", "Muted", wrap=True)
        lay.addWidget(self.catalog_info)
        self.refresh()

    def refresh(self, select: str = "") -> None:
        conns = self.store.list()
        primary = self.store.primary_id()
        danger = QBrush(QColor(theme.current["danger"]))
        self.table.setRowCount(len(conns))
        for r, c in enumerate(conns):
            info = c.info
            status_ok = self.store.is_signed_in(c)
            status = tr("ai.status.ready") if status_ok else tr("ai.status.signed_out")
            if info is None:
                status = tr("ai.status.unknown_provider")
            elif info.removed:
                status = tr("ai.status.removed")
            values = [("★ " if c.id == primary else "") + c.name, provider_name(info, c.provider),
                      auth_text(c.auth), caps_text(info), status]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setData(Qt.ItemDataRole.UserRole, c.id)
                if info is None or info.removed:
                    item.setForeground(danger)
                    item.setToolTip(note_text(info) if info else "")
                elif col == 4 and not status_ok:
                    item.setForeground(QBrush(QColor(theme.current["warning"])))
                self.table.setItem(r, col, item)
            if c.id == select:
                self.table.selectRow(r)
        self.catalog_info.setText(tr("ai.conn.catalog_info", count=len(providers.all_providers()),
                                     date=providers.updated()))

    def _current(self) -> Connection | None:
        r = self.table.currentRow()
        item = self.table.item(r, 0) if r >= 0 else None
        return self.store.get(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def add(self) -> None:
        dlg = ConnectionDialog(self.store, None, self)
        if dlg.exec():
            self.refresh(dlg.conn.id)

    def edit(self) -> None:
        conn = self._current()
        if conn:
            dlg = ConnectionDialog(self.store, conn, self)
            if dlg.exec():
                self.refresh(conn.id)

    def make_primary(self) -> None:
        conn = self._current()
        if conn:
            self.store.set_primary(conn.id)
            self.refresh(conn.id)

    def _move(self, delta: int) -> None:
        conn = self._current()
        if conn:
            self.store.move(conn.id, delta)
            self.refresh(conn.id)

    def remove(self) -> None:
        conn = self._current()
        if not conn:
            return
        if QMessageBox.question(self, tr("common.remove"), tr("ai.conn.remove_confirm", name=conn.name)) \
                != QMessageBox.StandardButton.Yes:
            return
        self.store.remove(conn.id)
        self.refresh()


# ========================================================= Anbieter wählen
class ProviderPicker(QWidget):
    """Kategorien links, Filter oben, Anbieter als Liste; Doppelklick wählt aus."""

    def __init__(self, on_pick, parent=None):
        super().__init__(parent)
        self.on_pick = on_pick
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        filters = QHBoxLayout()
        self.search = QLineEdit(placeholderText="🔍  " + tr("ai.add.search"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh)
        filters.addWidget(self.search, 2)
        self.cap = QComboBox()
        self.cap.addItem(tr("ai.add.any_capability"), "")
        for c in CAPS:
            self.cap.addItem(tr(f"ai.cap.{c}"), c)
        self.auth = QComboBox()
        self.auth.addItem(tr("ai.add.any_auth"), "")
        for a in ("browser", providers.AUTH_API_KEY, providers.AUTH_NONE):
            self.auth.addItem(tr(f"ai.add.auth_{a}"), a)
        self.region = QComboBox()
        self.region.addItem(tr("ai.add.any_region"), "")
        for r in REGIONS:
            self.region.addItem(tr(f"ai.add.region_{r.lower()}"), r)
        for combo in (self.cap, self.auth, self.region):
            combo.currentIndexChanged.connect(self.refresh)
            filters.addWidget(combo, 1)
        lay.addLayout(filters)
        split = QSplitter()
        self.cats = QListWidget()
        for cat in ["all"] + providers.categories():
            item = QListWidgetItem(tr(f"ai.cat.{cat}"))
            item.setData(Qt.ItemDataRole.UserRole, cat)
            self.cats.addItem(item)
        self.cats.setCurrentRow(1 if self.cats.count() > 1 else 0)
        self.cats.currentRowChanged.connect(self.refresh)
        self.cats.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(self.cats)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(self._picked)
        self.list.currentItemChanged.connect(self._show)
        split.addWidget(self.list)
        split.setSizes([180, 520])
        lay.addWidget(split, 1)
        self.details = label("", "Muted", wrap=True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details.setOpenExternalLinks(True)
        self.details.setMinimumHeight(60)
        lay.addWidget(self.details)
        self.refresh()

    def _matches(self, p: providers.Provider) -> bool:
        cat = self.cats.currentItem().data(Qt.ItemDataRole.UserRole) if self.cats.currentItem() else "all"
        if cat == "recommended":
            if not p.recommended:
                return False
        elif cat != "all" and cat not in p.categories:
            return False
        text = self.search.text().strip().lower()
        if text and text not in f"{p.name} {p.vendor} {p.id} {' '.join(p.models)}".lower():
            return False
        if self.cap.currentData() and not p.has(self.cap.currentData()):
            return False
        auth = self.auth.currentData()
        if auth == "browser" and not any(a in providers.OAUTH_KINDS for a in p.auth):
            return False
        if auth in (providers.AUTH_API_KEY, providers.AUTH_NONE) and auth not in p.auth:
            return False
        region = self.region.currentData()
        if region and p.country != region:
            return False
        return True

    def refresh(self) -> None:
        self.list.clear()
        danger, muted = QColor(theme.current["danger"]), QColor(theme.current["muted"])
        items = sorted((p for p in providers.all_providers() if self._matches(p)),
                       key=lambda p: (p.status != "active", not p.recommended, p.id.startswith("custom"),
                                      provider_name(p).lower()))
        for p in items:
            text = provider_name(p)
            if p.vendor and p.vendor not in text:
                text += f"  ·  {p.vendor}"
            sub = caps_text(p)
            if p.removed:
                sub = tr("ai.status.removed")
            elif not p.available:
                sub = tr("ai.status.unavailable")
            item = QListWidgetItem(f"{'★ ' if p.recommended and p.available else ''}{text}\n{sub}")
            item.setData(Qt.ItemDataRole.UserRole, p.id)
            if p.removed:
                item.setForeground(danger)
            elif not p.available:
                item.setForeground(muted)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.details.setText(tr("ai.add.none_found"))

    def _show(self, item) -> None:
        p = providers.get(item.data(Qt.ItemDataRole.UserRole)) if item else None
        if not p:
            return
        lines = [f"<b>{provider_name(p)}</b> · {', '.join(auth_text(a) for a in p.auth) or '–'}"]
        if p.models:
            lines.append(tr("ai.add.models", models=", ".join(p.models[:6])))
        note = note_text(p)
        if note:
            color = theme.current["danger"] if p.removed else theme.current["warning"]
            lines.append(f"<span style='color:{color}'>{note.replace(chr(10), '<br>')}</span>")
        if p.docs_url:
            lines.append(f"<a href='{p.docs_url}'>{tr('ai.add.docs')}</a>")
        self.details.setText("<br>".join(lines))

    def _picked(self, item) -> None:
        p = providers.get(item.data(Qt.ItemDataRole.UserRole))
        if p:
            self.on_pick(p)

    def current(self) -> providers.Provider | None:
        item = self.list.currentItem()
        return providers.get(item.data(Qt.ItemDataRole.UserRole)) if item else None


# ======================================================= Verbindung bearbeiten
class ConnectionDialog(QDialog):
    """Neue Verbindung (erst Anbieter wählen) oder bestehende bearbeiten."""

    def __init__(self, store: ConnectionStore, conn: Connection | None, parent=None):
        super().__init__(parent)
        self.store = store
        self.is_new = conn is None
        self.conn = conn or Connection(id=store.new_id(), name="", provider="")
        self._stop = threading.Event()
        self._busy = False
        self.setWindowTitle(tr("ai.add.title") if self.is_new else tr("ai.edit.title", name=self.conn.name))
        fit_to_screen(self, 820, 600)
        lay = QVBoxLayout(self)
        self.stack = QStackedWidget()
        self.picker = ProviderPicker(self._choose)
        self.stack.addWidget(self.picker)
        self.form_host = QWidget()
        self.stack.addWidget(self.form_host)
        lay.addWidget(self.stack, 1)
        row = QHBoxLayout()
        self.back = make_button("‹ " + tr("ai.add.back"), on_click=lambda: self.stack.setCurrentIndex(0))
        row.addWidget(self.back)
        row.addStretch()
        self.next_btn = make_button(tr("ai.add.next"), primary=True,
                                    on_click=lambda: self.picker.current() and self._choose(self.picker.current()))
        row.addWidget(self.next_btn)
        self.save_btn = make_button(tr("common.save"), primary=True, on_click=self._save)
        row.addWidget(self.save_btn)
        row.addWidget(make_button(tr("common.cancel"), on_click=self.reject))
        lay.addLayout(row)
        self.stack.currentChanged.connect(self._page_changed)
        if self.is_new:
            self.stack.setCurrentIndex(0)
            self._page_changed(0)
        else:
            self._build_form(self.conn.info)
            self.stack.setCurrentIndex(1)
            self._page_changed(1)

    def _page_changed(self, idx: int) -> None:
        self.back.setVisible(idx == 1 and self.is_new)
        self.next_btn.setVisible(idx == 0)
        self.save_btn.setVisible(idx == 1)

    def _choose(self, p: providers.Provider) -> None:
        if not p.available:
            QMessageBox.information(self, provider_name(p), note_text(p) or tr("ai.status.unavailable"))
            return
        if p.id != self.conn.provider:
            self.conn = Connection(id=self.conn.id, name="", provider=p.id, auth=p.auth[0],
                                   model=p.models[0] if p.models else "")
        self._build_form(p)
        self.stack.setCurrentIndex(1)

    # ------------------------------------------------------------- Formular
    def _build_form(self, p: providers.Provider | None) -> None:
        old = self.form_host.layout()
        if old is not None:
            QWidget().setLayout(old)   # altes Layout samt Widgets verwerfen
        self.p = p
        secrets = self.store.secrets(self.conn.id)
        outer = QVBoxLayout(self.form_host)
        outer.setContentsMargins(0, 0, 0, 0)
        title = label(provider_name(p, self.conn.provider), "PageTitle")
        outer.addWidget(title)
        if p is not None:
            note = note_text(p)
            if note:
                n = label(note, "Notice", wrap=True)
                outer.addWidget(n)
        form = QFormLayout()
        outer.addLayout(form)
        self.name = QLineEdit(self.conn.name or self.store.unique_name(provider_name(p, self.conn.provider),
                                                                       self.conn.id))
        form.addRow(tr("ai.edit.name"), self.name)

        self.auth = QComboBox()
        for a in (p.auth if p else [self.conn.auth]):
            self.auth.addItem(auth_text(a), a)
        self.auth.setCurrentIndex(max(self.auth.findData(self.conn.auth), 0))
        self.auth.currentIndexChanged.connect(self._auth_changed)
        form.addRow(tr("ai.edit.auth"), self.auth)

        # API-Schlüssel
        self.key_box = QWidget()
        kl = QHBoxLayout(self.key_box)
        kl.setContentsMargins(0, 0, 0, 0)
        self.key = QLineEdit(secrets.get("api_key", "") if not self.conn.key_ref else "")
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText(tr("ai.edit.key_placeholder"))
        kl.addWidget(self.key, 1)
        self.key_ref = self.conn.key_ref
        self.key_from_pwm = make_button("🔑 " + tr("ai.edit.key_from_pwm"), on_click=self._pick_key)
        kl.addWidget(self.key_from_pwm)
        self.key_row_label = tr("ai.edit.key")
        form.addRow(self.key_row_label, self.key_box)
        self.key_info = label("", "Muted", wrap=True)
        self.key_info.setOpenExternalLinks(True)
        form.addRow("", self.key_info)

        # Anmeldung im Browser
        self.login_box = QWidget()
        ll = QHBoxLayout(self.login_box)
        ll.setContentsMargins(0, 0, 0, 0)
        self.login_btn = make_button("🌐 " + tr("ai.edit.login"), primary=True, on_click=self._login)
        self.logout_btn = make_button(tr("ai.edit.logout"), on_click=self._logout)
        self.login_status = label("", "Muted", wrap=True)
        ll.addWidget(self.login_btn)
        ll.addWidget(self.logout_btn)
        ll.addWidget(self.login_status, 1)
        form.addRow(tr("ai.edit.login_row"), self.login_box)

        # Entra / eigenes OAuth
        self.oauth_box = QWidget()
        of = QFormLayout(self.oauth_box)
        of.setContentsMargins(0, 0, 0, 0)
        o = self.conn.oauth or {}
        self.o_client = QLineEdit(o.get("client_id", ""))
        self.o_auth = QLineEdit(o.get("auth_url", ""))
        self.o_auth.setPlaceholderText("https://…/authorize")
        self.o_token = QLineEdit(o.get("token_url", ""))
        self.o_token.setPlaceholderText("https://…/token")
        self.o_scopes = QLineEdit(o.get("scopes", ""))
        self.o_scopes.setPlaceholderText("openid offline_access …")
        self.o_secret = QLineEdit(secrets.get("oauth_client_secret", ""))
        self.o_secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.o_secret.setPlaceholderText(tr("ai.edit.optional"))
        of.addRow(tr("ai.edit.client_id"), self.o_client)
        of.addRow(tr("ai.edit.auth_url"), self.o_auth)
        of.addRow(tr("ai.edit.token_url"), self.o_token)
        of.addRow(tr("ai.edit.scopes"), self.o_scopes)
        of.addRow(tr("ai.edit.client_secret"), self.o_secret)
        of.addRow("", label(tr("ai.edit.redirect_hint"), "Muted", wrap=True))
        form.addRow(self.oauth_box)
        self.entra_box = QWidget()
        ef = QFormLayout(self.entra_box)
        ef.setContentsMargins(0, 0, 0, 0)
        e = self.conn.entra or {}
        self.e_tenant = QLineEdit(e.get("tenant", ""))
        self.e_tenant.setPlaceholderText(oauth.ENTRA_DEFAULT_TENANT)
        self.e_client = QLineEdit(e.get("client_id", ""))
        self.e_client.setPlaceholderText(oauth.ENTRA_DEFAULT_CLIENT)
        ef.addRow(tr("ai.edit.tenant"), self.e_tenant)
        ef.addRow(tr("ai.edit.client_id"), self.e_client)
        ef.addRow("", label(tr("ai.edit.entra_hint"), "Muted", wrap=True))
        form.addRow(self.entra_box)

        # Adresse und Modell
        self.base_url = QLineEdit(self.conn.base_url or (p.base_url if p else ""))
        self.base_url.setPlaceholderText("https://…/v1")
        self.base_url_label = tr("ai.edit.base_url")
        form.addRow(self.base_url_label, self.base_url)
        self._base_url_row_visible = p is None or p.base_url_editable or not p.base_url or "localhost" in p.base_url
        self.base_url.setVisible(self._base_url_row_visible)
        form.labelForField(self.base_url).setVisible(self._base_url_row_visible)

        mrow = QHBoxLayout()
        self.model = QComboBox()
        self.model.setEditable(True)
        models = list(dict.fromkeys((p.models if p else []) + list(self.conn.models)))
        self.model.addItems(models)
        self.model.setCurrentText(self.conn.model or (models[0] if models else ""))
        mrow.addWidget(self.model, 1)
        self.load_models_btn = make_button(tr("ai.edit.load_models"), on_click=self._load_models)
        mrow.addWidget(self.load_models_btn)
        self.model_label = tr("ai.edit.model")
        form.addRow(self.model_label, mrow)

        trow = QHBoxLayout()
        trow.addWidget(make_button(tr("ai.edit.test"), on_click=self._test))
        self.test_status = label("", "Muted", wrap=True)
        trow.addWidget(self.test_status, 1)
        form.addRow("", trow)
        outer.addStretch()
        self.form = form
        self._auth_changed()

    def _auth_changed(self) -> None:
        a = self.auth.currentData()
        p = self.p
        is_key = a == providers.AUTH_API_KEY
        browser = a in providers.OAUTH_KINDS
        for w, on in ((self.key_box, is_key), (self.key_info, is_key), (self.login_box, browser),
                      (self.oauth_box, a == providers.AUTH_CUSTOM), (self.entra_box, a == providers.AUTH_ENTRA)):
            w.setVisible(on)
            lbl = self.form.labelForField(w)
            if lbl is not None:
                lbl.setVisible(on)
        if is_key:
            parts = []
            if self.key_ref:
                parts.append(tr("ai.edit.key_ref", name=self._ref_name()))
            if p and p.key_url:
                parts.append(f"<a href='{p.key_url}'>{tr('ai.edit.key_link')}</a>")
            self.key_info.setText(" · ".join(parts))
            self.key.setEnabled(not self.key_ref)
        if browser:
            self._update_login_status()

    def _ref_name(self) -> str:
        provider_id, _, cred_id = self.key_ref.partition(":")
        try:
            if provider_id == credentials.LocalProvider.id:
                cred = credentials.manager().local.get(cred_id)
                if cred:
                    return cred.name
        except Exception:  # noqa: BLE001
            pass
        return self.key_ref

    def _pick_key(self) -> None:
        if self.key_ref:
            self.key_ref = ""
            self.key_from_pwm.setText("🔑 " + tr("ai.edit.key_from_pwm"))
            self._auth_changed()
            return
        dlg = CredentialPickerDialog(self)
        if dlg.exec() and dlg.selected:
            self.key_ref = dlg.selected.ref
            self.key.clear()
            self.key_from_pwm.setText(tr("ai.edit.key_unlink"))
            self._auth_changed()

    def _update_login_status(self) -> None:
        conn = self._collect()
        signed = self.store.is_signed_in(conn)
        if conn.auth == providers.AUTH_OPENROUTER:
            signed = bool(self.store.secrets(conn.id).get("api_key"))
        account = self.store.secrets(conn.id).get("account", "")
        self.login_status.setText(tr("ai.edit.signed_in", account=account) if signed and account
                                  else tr("ai.edit.signed_in_plain") if signed else tr("ai.edit.not_signed_in"))
        self.logout_btn.setVisible(signed)
        self.login_btn.setText("🌐 " + (tr("ai.edit.relogin") if signed else tr("ai.edit.login")))

    # --------------------------------------------------------------- Werte
    def _collect(self) -> Connection:
        c = Connection.from_dict(self.conn.to_dict())
        c.name = self.name.text().strip() or provider_name(self.p, c.provider)
        c.auth = self.auth.currentData() or c.auth
        url = self.base_url.text().strip()
        c.base_url = url if url and (not self.p or url != self.p.base_url) else ""
        c.model = self.model.currentText().strip()
        c.models = [self.model.itemText(i) for i in range(self.model.count())
                    if not self.p or self.model.itemText(i) not in self.p.models][:200]
        c.key_ref = self.key_ref if c.auth == providers.AUTH_API_KEY else ""
        if c.auth == providers.AUTH_CUSTOM:
            c.oauth = {"client_id": self.o_client.text().strip(), "auth_url": self.o_auth.text().strip(),
                       "token_url": self.o_token.text().strip(), "scopes": self.o_scopes.text().strip()}
        if c.auth == providers.AUTH_ENTRA:
            c.entra = {"tenant": self.e_tenant.text().strip(), "client_id": self.e_client.text().strip()}
        return c

    def _store_secret_fields(self, c: Connection) -> None:
        if c.auth == providers.AUTH_API_KEY:
            key = self.key.text().strip()
            if c.key_ref:
                self.store.update_secrets(c.id, api_key="")
            elif key != self.store.secrets(c.id).get("api_key", ""):
                self.store.update_secrets(c.id, api_key=key)
        if c.auth == providers.AUTH_CUSTOM:
            self.store.update_secrets(c.id, oauth_client_secret=self.o_secret.text().strip())

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.form_host.setEnabled(not busy)
        self.save_btn.setEnabled(not busy)

    def _login(self) -> None:
        c = self._collect()
        self._store_secret_fields(c)
        self._stop.clear()
        self._set_busy(True)
        self.login_status.setText(tr("ai.edit.login_running"))

        def opener(url: str) -> None:
            QTimer.singleShot(0, self, lambda: QDesktopServices.openUrl(QUrl(url)))

        def done(_):
            self._set_busy(False)
            self._update_login_status()

        def failed(err):
            self._set_busy(False)
            self.login_status.setText("⚠ " + err)

        run_async(lambda: oauth.login(self.store, c, self._stop, opener), done, failed)

    def _logout(self) -> None:
        c = self._collect()
        if c.auth == providers.AUTH_OPENROUTER:
            self.store.update_secrets(c.id, api_key="")
        else:
            oauth.logout(self.store, c)
        self._update_login_status()

    def _adapter_task(self, fn):
        c = self._collect()
        self._store_secret_fields(c)

        def task():
            return fn(adapters.for_connection(self.store, c))
        return task

    def _load_models(self) -> None:
        self.test_status.setText(tr("ai.edit.loading_models"))

        def done(models):
            current = self.model.currentText()
            self.model.clear()
            self.model.addItems(models or (self.p.models if self.p else []))
            self.model.setCurrentText(current or (models[0] if models else ""))
            self.test_status.setText(tr("ai.edit.models_loaded", count=len(models)))

        run_async(self._adapter_task(lambda a: a.list_models()), done, self._show_error)

    def _test(self) -> None:
        self.test_status.setText(tr("ai.edit.testing"))
        ok = theme.current["success"]
        run_async(self._adapter_task(lambda a: a.test()),
                  lambda info: self.test_status.setText(
                      f"<span style='color:{ok}'>✔ {tr('ai.edit.test_ok')}</span>"
                      + (" · " + tr("ai.edit.models_loaded", count=info) if info else "")),
                  self._show_error)

    def _show_error(self, err: str) -> None:
        self.test_status.setText(f"<span style='color:{theme.current['danger']}'>⚠ {err}</span>")

    def _save(self) -> None:
        c = self._collect()
        if not c.model and self.p and self.p.api not in ("graph_copilot",):
            QMessageBox.information(self, self.windowTitle(), tr("ai.edit.need_model"))
            return
        c.name = self.store.unique_name(c.name, c.id)
        self._store_secret_fields(c)
        self.store.save(c)
        self.conn = c
        self.accept()

    def reject(self) -> None:
        self._stop.set()
        if self.is_new and self.store.get(self.conn.id) is None:
            self.store.set_secrets(self.conn.id, {})   # Anmeldung eines verworfenen Eintrags entfernen
        super().reject()


# ============================================================== Datenablage
class AIStoragePage(QWidget):
    def __init__(self, settings, vault, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.storage = storage.Storage(settings, vault)
        self.old_paths = self.storage.all_paths()
        lay = QVBoxLayout(self)
        lay.addWidget(label(tr("ai.store.title"), "CardTitle"))
        lay.addWidget(label(tr("ai.store.hint"), "Muted", wrap=True))
        form = QFormLayout()
        self.mode = QComboBox()
        for m in storage.MODES:
            self.mode.addItem(tr(f"ai.store.mode_{m}"), m)
        self.mode.setCurrentIndex(max(self.mode.findData(self.storage.mode), 0))
        self.mode.currentIndexChanged.connect(self._mode_changed)
        form.addRow(tr("ai.store.mode"), self.mode)
        rrow = QHBoxLayout()
        self.root = QLineEdit(str(self.storage.root))
        self.root.textChanged.connect(self._fill_table)
        rrow.addWidget(self.root, 1)
        rrow.addWidget(make_button("…", on_click=lambda: self._browse(self.root)))
        self.root_row = QWidget()
        self.root_row.setLayout(rrow)
        rrow.setContentsMargins(0, 0, 0, 0)
        form.addRow(tr("ai.store.root"), self.root_row)
        lay.addLayout(form)
        self.form = form

        self.table = QTableWidget(len(storage.TYPES), 4)
        self.table.setHorizontalHeaderLabels([tr("ai.store.col_type"), tr("ai.store.col_folder"),
                                              tr("ai.store.col_format"), ""])
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.edits: dict[str, QLineEdit] = {}
        custom = settings.get(storage.PATHS_KEY) or {}
        for r, kind in enumerate(storage.TYPES):
            self.table.setItem(r, 0, QTableWidgetItem(tr(f"ai.store.type_{kind}")))
            edit = QLineEdit(custom.get(kind, ""))
            edit.setFrame(False)
            self.edits[kind] = edit
            self.table.setCellWidget(r, 1, edit)
            self.table.setItem(r, 2, QTableWidgetItem(storage.FORMATS[kind]))
            btns = QWidget()
            bl = QHBoxLayout(btns)
            bl.setContentsMargins(2, 0, 2, 0)
            browse = QToolButton(text="…")
            browse.setToolTip(tr("ai.store.change"))
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            opener = QToolButton(text="📂")
            opener.setToolTip(tr("ai.store.open"))
            opener.clicked.connect(lambda _=False, k=kind: self._open(k))
            bl.addWidget(browse)
            bl.addWidget(opener)
            self.table.setCellWidget(r, 3, btns)
            self.table.setRowHeight(r, 30)
        lay.addWidget(self.table, 1)

        self.encrypt = QCheckBox(tr("ai.store.encrypt"))
        self.encrypt.setChecked(self.storage.encrypt)
        lay.addWidget(self.encrypt)
        lay.addWidget(label(tr("ai.store.encrypt_hint"), "Notice", wrap=True))
        self._mode_changed()

    def _mode_changed(self) -> None:
        mode = self.mode.currentData()
        self.root_row.setVisible(mode == "central")
        self.form.labelForField(self.root_row).setVisible(mode == "central")
        self._fill_table()

    def _fill_table(self) -> None:
        mode = self.mode.currentData()
        root = Path(self.root.text().strip() or storage.default_root())
        for kind, edit in self.edits.items():
            if mode == "documents":
                default = self.storage.default_path(kind, "documents")
            else:
                default = root / storage.SUBDIRS[kind]
            edit.setPlaceholderText(str(default))
            edit.setReadOnly(mode != "per_type")
            if mode != "per_type":
                edit.setText("")
            self.table.cellWidget(storage.TYPES.index(kind), 3).layout().itemAt(0).widget() \
                .setEnabled(mode == "per_type")

    def _browse(self, edit: QLineEdit) -> None:
        start = edit.text() or edit.placeholderText()
        path = QFileDialog.getExistingDirectory(self, tr("ai.store.change"), start)
        if path:
            edit.setText(path)

    def _open(self, kind: str) -> None:
        edit = self.edits[kind]
        path = Path(edit.text() or edit.placeholderText())
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save(self) -> None:
        s = self.settings
        s.set(storage.MODE_KEY, self.mode.currentData(), save=False)
        root = self.root.text().strip()
        s.set(storage.ROOT_KEY, root if root and Path(root) != storage.default_root() else "", save=False)
        s.set(storage.PATHS_KEY, {k: e.text().strip() for k, e in self.edits.items() if e.text().strip()},
              save=False)
        old_encrypt = self.storage.encrypt
        s.set(storage.ENCRYPT_KEY, self.encrypt.isChecked(), save=False)
        s.save()
        new_paths = self.storage.all_paths()
        moved = [k for k in storage.TYPES if new_paths[k] != self.old_paths[k]
                 and self.old_paths[k].is_dir() and any(self.old_paths[k].iterdir())]
        if moved and QMessageBox.question(
                self, tr("ai.store.title"),
                tr("ai.store.move_question", types=", ".join(tr(f"ai.store.type_{k}") for k in moved))) \
                == QMessageBox.StandardButton.Yes:
            for k in moved:
                storage.Storage.move_tree(self.old_paths[k], new_paths[k])
        if old_encrypt != self.encrypt.isChecked():
            self.storage.convert_all(self.encrypt.isChecked())


# ================================================================ KI-Zugriff
class AIAccessPage(QWidget):
    """Was Assistenten sehen dürfen: Stufe, Verfremdung, Ausnahmen je Assistent.

    source "app" = Hauptprogramm, sonst Tool-ID (erbt ohne eigene Einstellung vom Hauptprogramm).
    Gespeichert wird mit save() (beim Speichern des Dialogs).
    """

    def __init__(self, settings, vault, source: str = "app", parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QButtonGroup, QFrame, QRadioButton, QScrollArea
        from omniwrench.ai import access
        self.settings = settings
        self.source = source
        self.access = access
        self.store = ConnectionStore(settings, vault)
        is_app = source == "app"
        self.cfg = access.app_config(settings) if is_app else access.tool_config(settings, source)
        app_level = access.app_config(settings)["level"]
        outer = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(label(tr("ai.access.title_app") if is_app else tr("ai.access.title_tool"), "CardTitle"))
        left.addWidget(label(tr("ai.access.hint"), "Muted", wrap=True))
        self.group = QButtonGroup(self)
        options = [] if is_app else [(None, tr("ai.access.inherit", level=tr(f"ai.level.{app_level}")),
                                      tr("ai.access.inherit_desc"))]
        options += [(lv, tr(f"ai.level.{lv}"), tr(f"ai.level.{lv}_desc")) for lv in access.LEVELS]
        current = self.cfg.get("level")
        for value, text, desc in options:
            box = QFrame()
            box.setObjectName("ToolCard")
            bl = QVBoxLayout(box)
            bl.setContentsMargins(10, 6, 10, 6)
            bl.setSpacing(0)
            rb = QRadioButton(text)
            rb.setProperty("level", -1 if value is None else value)
            rb.setChecked(value == current)
            self.group.addButton(rb)
            bl.addWidget(rb)
            d = label(desc, "Muted", wrap=True)
            d.setContentsMargins(24, 0, 0, 0)
            bl.addWidget(d)
            left.addWidget(box)
        left.addStretch()
        outer.addLayout(left, 3)

        right = QVBoxLayout()
        right.addWidget(label(tr("ai.access.pseudo"), "CardTitle"))
        right.addWidget(label(tr("ai.access.pseudo_hint"), "Muted", wrap=True))
        self.kind_boxes: dict[str, QCheckBox] = {}
        if is_app:
            self.pseudo = QCheckBox(tr("ai.access.pseudo_on"))
            self.pseudo.setChecked(bool(self.cfg.get("pseudo", True)))
            right.addWidget(self.pseudo)
            for kind in access.PSEUDO_KINDS:
                cb = QCheckBox(tr(f"ai.pseudo.{kind}"))
                cb.setChecked(bool(self.cfg["pseudo_kinds"].get(kind, True)))
                cb.setContentsMargins(18, 0, 0, 0)
                cb.toggled.connect(self._preview)
                self.kind_boxes[kind] = cb
                right.addWidget(cb)
            self.pseudo.toggled.connect(lambda on: [c.setEnabled(on) for c in self.kind_boxes.values()])
            self.pseudo.toggled.connect(self._preview)
            for c in self.kind_boxes.values():
                c.setEnabled(self.pseudo.isChecked())
        else:
            self.pseudo = QComboBox()
            app_on = access.app_config(settings).get("pseudo", True)
            self.pseudo.addItem(tr("ai.access.pseudo_inherit",
                                   state=tr("ai.access.on") if app_on else tr("ai.access.off")), None)
            self.pseudo.addItem(tr("ai.access.on"), True)
            self.pseudo.addItem(tr("ai.access.off"), False)
            self.pseudo.setCurrentIndex(max(self.pseudo.findData(self.cfg.get("pseudo")), 0))
            self.pseudo.currentIndexChanged.connect(self._preview)
            right.addWidget(self.pseudo)
        right.addWidget(label(tr("ai.access.preview"), "CardTitle"))
        self.preview = label("", "", wrap=True)
        self.preview.setTextFormat(Qt.TextFormat.PlainText)
        self.preview.setStyleSheet(f"font-family: Consolas, monospace; background: {theme.current['surface']};"
                                   f" border: 1px solid {theme.current['border']}; border-radius: 6px; padding: 6px;")
        right.addWidget(self.preview)
        right.addWidget(label(tr("ai.access.preview_hint"), "Muted", wrap=True))
        right.addStretch()
        self.exceptions = dict(self.cfg.get("exceptions") or {})
        self.exc_btn = make_button("", on_click=self._edit_exceptions)
        right.addWidget(self.exc_btn)
        self._update_exc_button()
        outer.addLayout(right, 2)
        self._preview()

    def _pseudo_on(self) -> bool:
        if self.source == "app":
            return self.pseudo.isChecked()
        value = self.pseudo.currentData()
        return bool(self.access.app_config(self.settings).get("pseudo", True)) if value is None else bool(value)

    def _preview(self, *_):
        from omniwrench.ai.pseudo import Pseudonymizer
        kinds = ({k: c.isChecked() for k, c in self.kind_boxes.items()} if self.kind_boxes
                 else self.access.pseudo_kinds(self.settings))
        p = Pseudonymizer({}, kinds, enabled=self._pseudo_on())
        sample = ("Lease 192.168.20.57 · dc01.corp.contoso.local\n"
                  "MAC 00-15-5D-0A-12-34 · CONTOSO\\m.muster\n"
                  "Server 192.168.20.10 · Maske 255.255.255.0")
        self.preview.setText(p.encode(sample))

    def _update_exc_button(self) -> None:
        n = len(self.exceptions)
        self.exc_btn.setText(tr("ai.access.exceptions_count", count=n) if n else tr("ai.access.exceptions"))

    def _edit_exceptions(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("ai.access.exceptions"))
        lay = QVBoxLayout(dlg)
        lay.addWidget(label(tr("ai.access.exceptions_hint"), "Muted", wrap=True))
        form = QFormLayout()
        combos = {}
        from omniwrench.ai.mcp_server import CONN_ID as MCP_ID
        # Externe Programme über den MCP-Server des KI-Studios zählen wie ein eigener Assistent
        entries = [(c.id, c.name) for c in self.store.list()] + [(MCP_ID, tr("ai.access.mcp_server"))]
        for cid, name in entries:
            combo = QComboBox()
            combo.addItem(tr("ai.access.no_exception"), None)
            for lv in self.access.LEVELS:
                combo.addItem(tr(f"ai.level.{lv}"), lv)
            combo.setCurrentIndex(max(combo.findData(self.exceptions.get(cid)), 0))
            combos[cid] = combo
            form.addRow(name, combo)
        if len(combos) == 1:
            lay.addWidget(label(tr("ai.access.no_assistants"), "Muted", wrap=True))
        lay.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        lay.addWidget(buttons)
        if dlg.exec():
            self.exceptions = {cid: cb.currentData() for cid, cb in combos.items() if cb.currentData() is not None}
            self._update_exc_button()

    def save(self) -> None:
        btn = self.group.checkedButton()
        lv = btn.property("level") if btn else None
        cfg = dict(self.cfg)
        cfg["level"] = None if lv in (None, -1) else int(lv)
        cfg["exceptions"] = self.exceptions
        if self.source == "app":
            cfg["pseudo"] = self.pseudo.isChecked()
            cfg["pseudo_kinds"] = {k: c.isChecked() for k, c in self.kind_boxes.items()}
            if cfg["level"] is None:
                cfg["level"] = self.access.DEFAULT_LEVEL
            self.access.set_app_config(self.settings, cfg)
        else:
            cfg["pseudo"] = self.pseudo.currentData()
            self.access.set_tool_config(self.settings, self.source, cfg)
