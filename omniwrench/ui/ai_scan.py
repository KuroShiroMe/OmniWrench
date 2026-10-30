"""„Fähigkeiten prüfen“: was eine Verbindung kann, mit welchen Modellen, und wie viel Volumen der Anbieter meldet."""

from __future__ import annotations

import html
import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

from omniwrench.ai import scan
from omniwrench.ai.connections import Connection, ConnectionStore
from omniwrench.core.i18n import tr

from . import theme
from .widgets import make_button
from .workers import run_async

STATUS_ICON = {"ok": "✔", "missing": "✖", "unknown": "?", "error": "⚠"}


def status_text(status: str) -> str:
    return f"{STATUS_ICON.get(status, '?')} {tr(f'ai.scan.status_{status}')}"


def kind_text(kind: str) -> str:
    return tr(f"ai.scan.kind_{kind}")


def volume_text(result: dict | None) -> str:
    """Kurzfassung für Tabellen: Guthaben oder verbleibende Anfragen, sonst leer."""
    if not result:
        return ""
    acc = result.get("account") or {}
    parts = []
    if acc.get("balance") is not None:
        parts.append(tr("ai.scan.balance", value=acc["balance"], currency=acc.get("currency", "")))
    if acc.get("remaining") is not None:
        parts.append(tr("ai.scan.remaining", value=acc["remaining"], currency=acc.get("currency", "")))
    req = (result.get("limits") or {}).get("requests") or {}
    if req.get("remaining") is not None:
        parts.append(tr("ai.scan.requests_left", left=req["remaining"], limit=req.get("limit", "?")))
    return " · ".join(str(p) for p in parts)


def report_html(conn: Connection, result: dict) -> str:
    c = theme.current
    color = {"ok": c["success"], "missing": c["danger"], "error": c["danger"], "unknown": c["muted"]}
    when = time.strftime("%d.%m.%Y %H:%M", time.localtime(result.get("ts", 0)))
    out = [f"<h3>{html.escape(conn.name)}</h3>", f"<p style='color:{c['muted']}'>{tr('ai.scan.when', when=when)}"]
    if result.get("models") is not None:
        out.append(" · " + tr("ai.model.count", count=result["models"]))
    out.append("</p><table cellspacing='0' cellpadding='4' width='100%'>")
    out.append(f"<tr><th align='left'>{tr('ai.scan.col_function')}</th><th align='left'>{tr('ai.scan.col_status')}"
               f"</th><th align='left'>{tr('ai.scan.col_models')}</th><th align='left'>{tr('ai.req.label')}</th></tr>")
    for kind, k in (result.get("kinds") or {}).items():
        models = ", ".join(k.get("models") or [])
        if len(models) > 160:
            models = models[:157] + "…"
        req = tr(f"ai.req.{k['requires']}") if k.get("requires") else ""
        out.append(f"<tr><td><b>{kind_text(kind)}</b></td>"
                   f"<td style='color:{color.get(k.get('status'), c['muted'])}'>{status_text(k.get('status', ''))}</td>"
                   f"<td>{html.escape(models)}</td><td style='color:{c['muted']}'>{html.escape(req)}</td></tr>")
    out.append("</table>")
    if not result.get("kinds"):
        out.append(f"<p>{tr('ai.scan.nothing')}</p>")
    out.append(f"<h4>{tr('ai.scan.volume')}</h4>")
    vol = volume_text(result)
    limits = result.get("limits") or {}
    lines = []
    if vol:
        lines.append(html.escape(vol))
    tok = limits.get("tokens") or {}
    if tok.get("remaining") is not None:
        lines.append(tr("ai.scan.tokens_left", left=tok["remaining"], limit=tok.get("limit", "?")))
    for what in ("requests", "tokens"):
        if (limits.get(what) or {}).get("reset"):
            lines.append(tr("ai.scan.reset", what=tr(f"ai.scan.{what}"), when=limits[what]["reset"]))
    if (result.get("account") or {}).get("free_tier"):
        lines.append(tr("ai.scan.free_tier"))
    if not lines:
        lines.append(tr("ai.scan.no_volume"))
    if result.get("usage_url"):
        lines.append(f"<a href='{html.escape(result['usage_url'])}'>{tr('ai.scan.usage_page')}</a>")
    out.append("<p>" + "<br>".join(lines) + "</p>")
    out.append(f"<p style='color:{c['muted']}'>{tr('ai.scan.hint')}</p>")
    if result.get("errors"):
        out.append(f"<p style='color:{c['danger']}'>⚠ " + "<br>".join(html.escape(e[:300]) for e in result["errors"])
                   + "</p>")
    return "".join(out)


class ScanDialog(QDialog):
    def __init__(self, store: ConnectionStore, conn: Connection, parent=None, run: bool = True):
        super().__init__(parent)
        self.store = store
        self.conn = conn
        self.setWindowTitle(tr("ai.scan.title", name=conn.name))
        self.resize(720, 520)
        lay = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(True)
        lay.addWidget(self.view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        self.again = make_button("↻ " + tr("ai.scan.run"), on_click=self.run)
        buttons.addButton(self.again, QDialogButtonBox.ButtonRole.ActionRole)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        last = scan.last(store.settings, conn.id)
        if last:
            self.view.setHtml(report_html(conn, last))
        if run or not last:
            self.run()

    def run(self) -> None:
        self.again.setEnabled(False)
        self.view.setHtml(f"<p>{tr('ai.scan.running', name=html.escape(self.conn.name))}</p>")

        def done(result):
            self.again.setEnabled(True)
            self.view.setHtml(report_html(self.conn, result))

        def failed(err: str):
            self.again.setEnabled(True)
            self.view.setHtml(f"<p style='color:{theme.current['danger']}'>⚠ {html.escape(err)}</p>")

        run_async(lambda: scan.scan(self.store, self.conn), done, failed)
        self.view.setAlignment(Qt.AlignmentFlag.AlignLeft)
