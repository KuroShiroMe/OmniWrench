"""PDF-Export eines oder mehrerer Zielberichte – über QPdfWriter/QTextDocument, ohne Zusatzbibliothek."""

from __future__ import annotations

import html
from datetime import datetime

from PySide6.QtCore import QMarginsF
from PySide6.QtGui import QPageLayout, QPageSize, QPdfWriter, QTextDocument

from . import findings as fx
from . import portinfo

LEVEL_COLOR = {fx.ERROR: "#c0392b", fx.WARN: "#b8860b", fx.INFO: "#2563eb", fx.OK: "#157347"}


def _esc(value) -> str:
    return html.escape(str(value), quote=False)


def _rows(rows: list[tuple[str, str]]) -> str:
    cells = "".join(
        f"<tr><td class='k'>{_esc(k)}</td><td class='v'>{_esc(v)}</td></tr>" for k, v in rows if v not in ("", None)
    )
    return f"<table class='kv'>{cells}</table>" if cells else ""


def _finding_rows(result, tr) -> str:
    out = []
    for f in result.findings:
        params = dict(f.params)
        if f.port:
            params.setdefault("port", f.port)
        title = _esc(tr(f"fx.{f.id}.title", **params))
        detail = _esc(tr(f"fx.{f.id}.detail", **params))
        port = f" · Port {f.port}" if f.port else ""
        out.append(f"<tr><td class='lvl' style='color:{LEVEL_COLOR[f.level]}'>&#9679; "
                   f"{_esc(tr('level.' + f.level))}</td><td><b>{title}</b>{port}<br>"
                   f"<span class='muted'>{detail}</span></td></tr>")
    return f"<table class='find'>{''.join(out)}</table>" if out else ""


def _target_section(result, tr, lang: str) -> str:
    raw = result.raw
    parts = [f"<h2>{_esc(result.label)}</h2>"]

    # Steckbrief
    addr = raw.get("address", {})
    rev = raw.get("reverse", {})
    asn = raw.get("asn", {})
    nb = raw.get("netbios", {})
    ident = [(tr("g.input"), result.target.label), (tr("g.ip"), result.ip or "–")]
    if addr:
        ident.append((tr("g.ip_class"), tr("class." + addr.get("class", "public"))))
    if rev.get("ptr"):
        ident.append((tr("g.ptr"), ", ".join(rev["ptr"])))
    if nb.get("computer"):
        ident.append((tr("g.netbios_name"), nb["computer"]))
    if nb.get("domain"):
        ident.append((tr("g.netbios_domain"), nb["domain"]))
    if asn.get("asn"):
        ident.append((tr("g.asn"), f"AS{asn['asn']} {asn.get('owner', '')}".strip()))
    parts.append(f"<h3>{_esc(tr('cat.profile'))}</h3>" + _rows(ident))

    # Befunde
    fr = _finding_rows(result, tr)
    if fr:
        parts.append(f"<h3>{_esc(tr('cat.findings'))}</h3>" + fr)

    # Konnektivität / Ping
    ping = raw.get("ping", {})
    if ping and not ping.get("unavailable"):
        prows = [(tr("g.ping_sent_recv"), f"{ping.get('received', 0)}/{ping.get('sent', 0)}"),
                 (tr("g.ping_loss"), f"{ping.get('loss_pct', 0)} %")]
        if ping.get("received"):
            prows += [(tr("g.ping_rtt"), f"{ping.get('min', 0)} / {ping.get('avg', 0)} / {ping.get('max', 0)} ms"),
                      (tr("g.ping_jitter"), f"{ping.get('jitter', 0)} ms")]
            if ping.get("ttl"):
                prows.append((tr("g.ping_ttl"), f"{ping['ttl']} ({tr('g.hops')}: {ping.get('hops', '?')})"))
        parts.append(f"<h3>{_esc(tr('cat.connectivity'))}</h3>" + _rows(prows))

    # Ports
    openp = raw.get("tcp", {}).get("open", {})
    if openp:
        cells = []
        for port in sorted(openp):
            meta = portinfo.describe(port, "tcp", lang.split("_")[0] if lang.split("_")[0] in ("de", "en") else "en")
            cells.append(f"<tr><td class='mono'>{port}/tcp</td><td>{_esc(meta.get('name', ''))}</td>"
                         f"<td class='muted'>{_esc(meta.get('description', ''))}</td></tr>")
        parts.append(f"<h3>{_esc(tr('cat.ports'))}</h3><table class='ports'>"
                     f"<tr><th>Port</th><th>{_esc(tr('ports.col_service'))}</th><th></th></tr>"
                     f"{''.join(cells)}</table>")

    # DNS
    dns = raw.get("dns", {})
    records = dns.get("records", {})
    if records:
        cells = []
        for rtype, data in records.items():
            for value in data.get("values", []):
                cells.append(f"<tr><td class='mono'>{_esc(rtype)}</td><td class='mono'>{_esc(value)}</td></tr>")
        if cells:
            parts.append(f"<h3>{_esc(tr('cat.dns'))}</h3><table class='ports'>{''.join(cells)}</table>")
    return "".join(parts)


def report_html(results: list, tr, lang: str) -> str:
    when = datetime.now().strftime("%Y-%m-%d %H:%M")
    css = """
    body{font-family:'Segoe UI',Arial,sans-serif;color:#1a1a1a;font-size:10pt;}
    h1{font-size:17pt;margin:0 0 2px 0;} h2{font-size:14pt;margin:18px 0 2px 0;border-bottom:1px solid #ccc;}
    h3{font-size:11pt;margin:12px 0 2px 0;color:#444;}
    table{border-collapse:collapse;width:100%;margin:2px 0 6px 0;}
    td,th{padding:2px 6px;vertical-align:top;text-align:left;}
    table.kv td.k{color:#666;width:34%;} table.find td.lvl{width:20%;white-space:nowrap;}
    table.ports th{background:#f0f0f0;font-size:9pt;} table.ports td,table.find td{border-top:1px solid #eee;}
    .muted{color:#777;} .mono{font-family:'Consolas',monospace;}
    .sub{color:#777;font-size:9pt;margin-bottom:8px;}
    """
    body = "".join(_target_section(r, tr, lang) for r in results)
    heading = _esc(results[0].label) if len(results) == 1 else f"{len(results)} {_esc(tr('list.target'))}"
    return (f"<html><head><style>{css}</style></head><body>"
            f"<h1>NetProbe · {heading}</h1><div class='sub'>DarkMatter OmniWrench · {when}</div>"
            f"{body}</body></html>")


def export_pdf(path: str, results: list, tr, lang: str) -> None:
    writer = QPdfWriter(path)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageMargins(QMarginsF(15, 15, 15, 15), QPageLayout.Unit.Millimeter)
    writer.setTitle("NetProbe Report")
    doc = QTextDocument()
    doc.setHtml(report_html(results, tr, lang))
    doc.setPageSize(writer.pageLayout().paintRectPixels(writer.resolution()).size())
    doc.print_(writer)
