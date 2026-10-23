"""Seite „Ereignisprotokoll“: Konfigurationsänderungen am DHCP-Server (wer, wann, was) mit Lesehilfe.

Quelle ist das Protokoll Microsoft-Windows-Dhcp-Server/Operational des gewählten Servers (eventlog.py). Zu jedem
Ereignis zeigt die Seite Bereich, Aktion, Scope (mit Name) und betroffenes Objekt, darunter alle Details und
einen Hinweis, was die Änderung bedeutet. Ist das Protokoll nicht lesbar (Recht fehlt, Firewall), erscheint ein
Hinweis mit Link auf die Einrichtungsanleitung im Wiki.

Das Laden läuft in einem eigenen Thread neben den übrigen Abläufen (nicht über den Runner): Abruf und Lesehilfe
passieren im Hintergrund, die Oberfläche bleibt bedienbar, und ein langsamer Server sperrt keine anderen Seiten.
"""

from __future__ import annotations

import datetime
import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QSplitter, QVBoxLayout, QWidget,
)

from omniwrench.ui import theme

from omniwrench.sdk import run_async

from . import eventlog
from .service import EventLogError, UserError
from .ui_base import ButtonBar, Grid, tint

WIKI_SETUP = "https://github.com/KuroShiroMe/OmniWrench/wiki/Tool-MS-DHCP-Extended-Management#ereignisprotokoll-einrichten"
PERIODS = (1, 24, 24 * 7, 24 * 30)      # Stunden
AREAS = ("scope", "option", "optiondef", "reservation", "exclusion", "failover", "policy", "filter", "class",
         "superscope", "server", "other")
MAX_EVENTS = 2000


class EventsPage(QWidget):
    def __init__(self, ctl, parent=None):
        super().__init__(parent)
        self.ctl = ctl
        tr = self.tr = ctl.tr
        self.svc = ctl.svc
        self.events: list[dict] = []
        self.loaded_for: str | None = None      # Server, für den zuletzt geladen wurde
        self.loading = False
        self._gen = 0                           # Ladevorgang; ältere Ergebnisse (Abmelden, neues Laden) verwerfen
        self._pending: list[dict] = []          # neue Ereignisse aus der Aktualisierung während des Ladens
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)

        self.err_box = QFrame()
        self.err_box.setObjectName("evterr")
        eb = QHBoxLayout(self.err_box)
        eb.setContentsMargins(12, 8, 12, 8)
        self.err_text = QLabel("")
        self.err_text.setWordWrap(True)
        self.err_text.setTextFormat(Qt.TextFormat.RichText)
        self.err_text.setOpenExternalLinks(True)
        self.err_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        eb.addWidget(self.err_text, 1)
        self.err_box.hide()
        lay.addWidget(self.err_box)

        top = QHBoxLayout()
        top.addWidget(QLabel(tr("evt.server")))
        self.server = QComboBox()
        self.server.setMinimumContentsLength(18)
        top.addWidget(self.server)
        top.addWidget(QLabel(tr("evt.period")))
        self.period = QComboBox()
        for h in PERIODS:
            self.period.addItem(tr(f"evt.period.{h}"), h)
        self.period.setCurrentIndex(1)
        top.addWidget(self.period)
        top.addWidget(QLabel(tr("evt.area")))
        self.area = QComboBox()
        self.area.addItem(tr("evt.area_all"), "")
        for a in AREAS:
            self.area.addItem(tr(f"evt.a.{a}"), a)
        self.area.currentIndexChanged.connect(self._apply_filter)
        top.addWidget(self.area)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("evt.filter"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        top.addWidget(self.filter, 1)
        self.bar = ButtonBar([("Load", tr("evt.load"))], primary=("Load",))
        self.bar.action.connect(lambda _a: self.load())
        top.addWidget(self.bar)
        lay.addLayout(top)

        split = QSplitter(Qt.Orientation.Vertical)
        acts = [("OpenScope", tr("evt.open_scope"), ""), "-", ("CopyCell", tr("ui.copy_cell"), "Ctrl+C")]
        self.grid = Grid([("time", tr("evt.col.time"), "text"), ("user", tr("evt.col.user"), "text"),
                          ("area_t", tr("evt.col.area"), "text"), ("action_t", tr("evt.col.action"), "text"),
                          ("scope_t", tr("evt.col.scope"), "text"), ("obj", tr("evt.col.obj"), "text"),
                          ("id", tr("evt.col.id"), "int"), ("text", tr("evt.col.text"), "text")],
                         key_fn=lambda r: str(r.get("record")), actions=acts, default_action="OpenScope", stretch="text")
        self.grid.tooltip_fn = lambda r: r.get("text") or ""
        self.grid.action.connect(self._action)
        self.grid.itemSelectionChanged.connect(self._show_detail)
        split.addWidget(self.grid)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setPlaceholderText(tr("evt.detail_hint"))
        split.addWidget(self.detail)
        split.setStretchFactor(0, 4)
        split.setStretchFactor(1, 1)
        lay.addWidget(split, 1)
        self.count = QLabel("")
        self.count.setStyleSheet(f"color:{theme.current['muted']};")
        lay.addWidget(self.count)

    # --- Daten ---------------------------------------------------------------------------------------
    def refresh(self) -> None:
        """Serverliste nach Anmeldung/Änderung der Partner auffrischen (lädt nichts)."""
        cur = self.server.currentText()
        names = [s for s in [self.svc.server] + self.svc.partners() if s]
        self.server.blockSignals(True)
        self.server.clear()
        self.server.addItems(names)
        if cur in names:
            self.server.setCurrentText(cur)
        self.server.blockSignals(False)

    def reset(self) -> None:
        self._gen += 1
        self._set_loading(False)
        self.loaded_for = None
        self.err_box.hide()
        self.set_events([])

    def on_shown(self) -> None:
        """Beim ersten Öffnen der Seite (und nach einem Serverwechsel) automatisch laden."""
        if self.svc.server and self.loaded_for != self.server.currentText():
            self.load()

    def load(self) -> None:
        """Ereignisse im Hintergrund lesen und aufbereiten; das Ergebnis kommt in _loaded im GUI-Thread an."""
        tr, svc = self.tr, self.svc
        server = self.server.currentText() or svc.server
        if not server:
            return
        hours = int(self.period.currentData() or 24)
        since = eventlog.iso_utc(datetime.datetime.now() - datetime.timedelta(hours=hours))
        self._gen += 1
        gen = self._gen
        self.loaded_for = server
        self._pending = []
        self._set_loading(True, tr("evt.loading", server=server))
        ctx = self._context()          # Momentaufnahme der Scopes/Definitionen für den Hintergrund-Thread

        def work():
            try:
                items = svc.events(server, since, MAX_EVENTS)
            except EventLogError as e:
                return ("err", e.code, str(e))
            except UserError as e:
                return ("err", 0, str(e))
            return ("ok", items, self._rows(items, ctx))

        run_async(work, lambda res: self._loaded(gen, server, res),
                  lambda text: self._loaded(gen, server, ("err", 0, text)))

    def _loaded(self, gen: int, server: str, res: tuple) -> None:
        if gen != self._gen:            # inzwischen abgemeldet oder neu geladen
            return
        self._set_loading(False)
        if res[0] == "err":
            self.set_events([])
            self._show_error(server, res[1], res[2])
            return
        self.err_box.hide()
        self.set_events(res[1], res[2])
        pending, self._pending = self._pending, []
        if pending:
            self.add_events(pending)
        self.svc.log(self.tr("log.events_loaded", n=len(res[1]), server=server))

    def _set_loading(self, on: bool, text: str = "") -> None:
        self.loading = on
        self.bar.setEnabled(not on)
        self.server.setEnabled(not on)
        self.period.setEnabled(not on)
        if on:
            self.count.setText(text)

    def add_events(self, items: list[dict]) -> None:
        """Neue Ereignisse aus der automatischen Aktualisierung (nur für den verbundenen Server) vorne einfügen."""
        if self.loaded_for is None or not self.svc.is_local(self.loaded_for):
            return
        if self.loading:
            self._pending = items + self._pending
            return
        have = {e.get("record") for e in self.events}
        new = [e for e in items if e.get("record") not in have]
        if new:
            self.set_events(new + self.events)

    def _context(self) -> tuple[list[tuple[str, str]], dict[str, str], dict[int, str]]:
        svc = self.svc
        scopes = [(s["id"], s["mask"]) for s in svc.scopes if s.get("id") and s.get("mask")]
        names = {s["id"]: s.get("name") or "" for s in svc.scopes}
        opts = {k[1]: d["name"] for k, d in svc.defs.items() if not k[0] and d.get("name")}   # Standardklasse
        return scopes, names, opts

    def _rows(self, items: list[dict], ctx) -> list[dict]:
        """Lesehilfe je Ereignis (läuft auch im Hintergrund-Thread, nutzt nur die Momentaufnahme ctx)."""
        tr = self.tr
        scopes, names, opts = ctx
        rows = []
        for ev in items:
            c = eventlog.classify(ev, scopes)
            sc = c["scope"]
            if c["area"] in ("option", "optiondef") and c["obj"][:3].isdigit():
                name = opts.get(int(c["obj"][:3]))       # Optionsname zur Nummer
                if name:
                    c["obj"] = c["obj"].replace(c["obj"][:3], f"{c['obj'][:3]} {name}", 1)
            rows.append(dict(ev, **c, area_t=tr(f"evt.a.{c['area']}"), action_t=tr(f"evt.act.{c['action']}"),
                             scope_t=f"{sc}  {names.get(sc, '')}".strip() if sc else ""))
        return rows

    def set_events(self, items: list[dict], rows: list[dict] | None = None) -> None:
        self.events = list(items)
        if rows is None:
            rows = self._rows(self.events, self._context())
        self.grid.set_rows(rows)
        self.grid.autosize(260)
        self._apply_filter()

    def _apply_filter(self) -> None:
        area = self.area.currentData() or ""
        q = self.filter.text().strip().lower()
        shown = 0
        for v in range(self.grid.rowCount()):
            r = self.grid.row_at(v)
            if r is None:
                continue
            hay = " ".join(str(r.get(k) or "") for k in ("time", "user", "area_t", "action_t", "scope_t", "obj", "text",
                                                         "id")).lower()
            ok = (not area or r.get("area") == area) and (not q or q in hay)
            self.grid.setRowHidden(v, not ok)
            shown += ok
        self.count.setText(self.tr("evt.count", n=shown, total=len(self.events), server=self.loaded_for or "–"))

    # --- Anzeige -------------------------------------------------------------------------------------
    def _show_error(self, server: str, code: int, text: str) -> None:
        tr = self.tr
        key = "evt.err_access" if code == 5 else "evt.err_rpc" if code in (1722, 1753, 1726, 1727) else \
            "evt.err_channel" if code in (15007, 15002) else "evt.err_other"
        c = theme.current
        self.err_box.setStyleSheet(f"QFrame#evterr {{ border:1px solid {c['warning']}; border-radius:6px;"
                                   f" background:{tint(c['warning'], 30).name(QColor.NameFormat.HexArgb)}; }}")
        self.err_text.setText(
            f"<b>{html.escape(tr('evt.err_title', server=server))}</b><br>{html.escape(tr(key, server=server))}"
            f"<br><span style='color:{c['muted']}'>{html.escape(text)}</span>"
            f"<br><a href='{WIKI_SETUP}'>{html.escape(tr('evt.err_link'))}</a>")
        self.err_box.show()
        self.count.setText(tr("evt.count", n=0, total=0, server=server))

    def _show_detail(self) -> None:
        r = self.grid.current()
        if not r:
            self.detail.clear()
            return
        tr = self.tr
        lines = [tr("evt.d.time", time=r.get("time", "")), tr("evt.d.user", user=r.get("user") or "?", sid=r.get("sid") or "–"),
                 tr("evt.d.event", id=r.get("id"), level=tr(f"evt.level.{r.get('level', 4)}"), computer=r.get("computer") or "–"),
                 tr("evt.d.what", area=r.get("area_t", ""), action=r.get("action_t", ""))]
        if r.get("scope_t"):
            lines.append(tr("evt.d.scope", scope=r["scope_t"]))
        if r.get("obj"):
            lines.append(tr("evt.d.obj", obj=r["obj"]))
        lines += ["", r.get("text") or ""]
        if r.get("fields"):
            lines += ["", tr("evt.d.fields")] + [f"  {k}: {v}" for k, v in r["fields"]]
        lines += ["", tr(f"evt.hint.{r.get('area', 'other')}")]
        self.detail.setPlainText("\n".join(lines))

    def _action(self, a: str) -> None:
        r = self.grid.current()
        if a == "OpenScope" and r and r.get("scope") and self.loaded_for and self.svc.is_local(self.loaded_for):
            if any(s["id"] == r["scope"] for s in self.svc.scopes):
                self.ctl.open_scope(r["scope"])
