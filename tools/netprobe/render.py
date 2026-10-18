"""Aufbereitung der Rohdaten eines Ziels in Qt-Widgets (ein Widget je Ergebnis-Kategorie)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFormLayout, QFrame, QGroupBox, QHBoxLayout, QLabel, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from . import findings as fx
from . import portinfo

MONO = QFont("Consolas", 10)
LEVEL_COLOR = {fx.ERROR: "#ef4444", fx.WARN: "#f59e0b", fx.INFO: "#3b82f6", fx.OK: "#10b981"}


def _mono(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setFont(MONO)
    lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    lbl.setWordWrap(True)
    return lbl


def _scroll(inner: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(inner)
    return area


def _section(title: str) -> QGroupBox:
    box = QGroupBox(title)
    QVBoxLayout(box)
    return box


def _form(rows: list[tuple[str, str]], tr=None) -> QWidget:
    w = QWidget()
    form = QFormLayout(w)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
    for key, value in rows:
        form.addRow(key + ":", _mono(str(value)))
    return w


class Renderer:
    """Baut die Widgets eines Ziels; `tr` ist die Übersetzungsfunktion des Tools, `lang` dessen Sprache."""

    def __init__(self, tr, lang: str):
        self.tr = tr
        self.lang = lang.split("_")[0] if lang.split("_")[0] in ("de", "en") else "en"

    # ------------------------------------------------------------ Befunde
    def findings_widget(self, result) -> QWidget:
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        counts = {lvl: sum(1 for f in result.findings if f.level == lvl) for lvl in (fx.ERROR, fx.WARN, fx.INFO, fx.OK)}
        summary = QHBoxLayout()
        for lvl in (fx.ERROR, fx.WARN, fx.INFO, fx.OK):
            chip = QLabel(f"  {counts[lvl]} {self.tr('level.' + lvl)}  ")
            chip.setStyleSheet(f"background:{LEVEL_COLOR[lvl]}22;color:{LEVEL_COLOR[lvl]};"
                               f"border:1px solid {LEVEL_COLOR[lvl]}55;border-radius:10px;padding:2px 4px;")
            summary.addWidget(chip)
        summary.addStretch(1)
        lay.addLayout(summary)
        if not result.findings:
            lay.addWidget(QLabel(self.tr("findings.none")))
        for f in result.findings:
            lay.addWidget(self._finding_card(f))
        lay.addStretch(1)
        return _scroll(inner)

    def _finding_card(self, f: fx.Finding) -> QWidget:
        card = QFrame()
        card.setObjectName("FindingCard")
        color = LEVEL_COLOR[f.level]
        card.setStyleSheet(f"#FindingCard{{border-left:3px solid {color};background:rgba(127,127,127,0.06);"
                           f"border-radius:4px;}}")
        row = QHBoxLayout(card)
        row.setContentsMargins(10, 7, 10, 7)
        dot = QLabel("●")
        dot.setStyleSheet(f"color:{color};font-size:14px;")
        dot.setAlignment(Qt.AlignmentFlag.AlignTop)
        row.addWidget(dot)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        params = dict(f.params)
        if f.port:
            params.setdefault("port", f.port)
        title = QLabel(self.tr(f"fx.{f.id}.title", **params))
        title.setStyleSheet("font-weight:600;")
        title.setWordWrap(True)
        detail = QLabel(self.tr(f"fx.{f.id}.detail", **params))
        detail.setWordWrap(True)
        detail.setStyleSheet("color:#9ca3af;")
        texts.addWidget(title)
        texts.addWidget(detail)
        row.addLayout(texts, 1)
        if f.port:
            tag = QLabel(f"Port {f.port}")
            tag.setFont(MONO)
            tag.setStyleSheet("color:#9ca3af;")
            tag.setAlignment(Qt.AlignmentFlag.AlignTop)
            row.addWidget(tag)
        return card

    # ------------------------------------------------------------ Allgemein
    def general_widget(self, result) -> QWidget:
        tr = self.tr
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        raw = result.raw

        addr = raw.get("address", {})
        rows = [(tr("g.input"), result.target.label)]
        if result.target.name:
            res = raw.get("resolve", {})
            rows.append((tr("g.resolved"), ", ".join(res.get("a", []) + res.get("aaaa", [])) or "–"))
        rows.append((tr("g.ip"), result.ip or "–"))
        if addr:
            rows.append((tr("g.ip_class"), tr("class." + addr.get("class", "public"))))
        rev = raw.get("reverse", {})
        if rev.get("ptr"):
            rows.append((tr("g.ptr"), ", ".join(rev["ptr"])))
        asn = raw.get("asn", {})
        if asn.get("asn"):
            rows.append((tr("g.asn"), f"AS{asn['asn']} {asn.get('owner', '')}".strip()))
            if asn.get("country"):
                rows.append((tr("g.country"), asn["country"]))
            if asn.get("prefix"):
                rows.append((tr("g.prefix"), asn["prefix"]))
        mac = raw.get("mac", {})
        if mac.get("mac"):
            vendor = mac.get("vendor", "")
            vendor = tr("g.mac_random") if vendor == "local" else vendor
            rows.append((tr("g.mac"), f"{mac['mac']}  {vendor}".strip()))
        nb = raw.get("netbios", {})
        if nb.get("answer"):
            if nb.get("computer"):
                rows.append((tr("g.netbios_name"), nb["computer"]))
            if nb.get("domain"):
                rows.append((tr("g.netbios_domain"), nb["domain"]))
        box = _section(tr("g.identity"))
        box.layout().addWidget(_form(rows))
        lay.addWidget(box)

        ping = raw.get("ping", {})
        if ping and not ping.get("unavailable"):
            lay.addWidget(self._ping_box(ping))
        mtu = raw.get("mtu", {})
        if mtu.get("mtu"):
            mrows = [(tr("g.mtu"), str(mtu["mtu"])), (tr("g.mtu_payload"), str(mtu.get("payload", "")))]
            if mtu.get("silent_drop"):
                mrows.append((tr("g.mtu_blackhole"), tr("g.yes")))
            mbox = _section(tr("g.mtu_title"))
            mbox.layout().addWidget(_form(mrows))
            lay.addWidget(mbox)
        for key, value in result.errors.items():
            if key in ("ping", "reverse", "mac", "netbios", "asn", "engine", "resolve", "mtu"):
                lay.addWidget(_mono(f"⚠ {key}: {value}"))
        lay.addStretch(1)
        return _scroll(inner)

    def _ping_box(self, ping: dict) -> QGroupBox:
        tr = self.tr
        box = _section(tr("g.ping_title"))
        rows = [
            (tr("g.ping_sent_recv"), f"{ping.get('received', 0)}/{ping.get('sent', 0)}"),
            (tr("g.ping_loss"), f"{ping.get('loss_pct', 0)} %"),
        ]
        if ping.get("received"):
            rows += [
                (tr("g.ping_rtt"), f"{ping.get('min', 0)} / {ping.get('avg', 0)} / {ping.get('max', 0)} ms"),
                (tr("g.ping_median"), f"{ping.get('median', 0)} ms"),
                (tr("g.ping_stdev"), f"{ping.get('stdev', 0)} ms"),
                (tr("g.ping_jitter"), f"{ping.get('jitter', 0)} ms"),
            ]
            if ping.get("ttl"):
                rows.append((tr("g.ping_ttl"), f"{ping['ttl']} ({tr('g.hops')}: {ping.get('hops', '?')}, "
                                               f"{tr('os.' + ping.get('os_guess', 'unix'))})"))
        box.layout().addWidget(_form(rows))
        if ping.get("received"):
            box.layout().addWidget(self._sparkline(ping.get("rtts", [])))
        return box

    def _sparkline(self, values: list[float]) -> QWidget:
        from .spark import Sparkline
        return Sparkline(values)

    # ------------------------------------------------------------ Route
    def route_widget(self, result) -> QWidget:
        tr = self.tr
        tr_data = result.raw.get("traceroute", {})
        hops_info = result.raw.get("hops", {})
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        if tr_data.get("unavailable"):
            lay.addWidget(QLabel(tr("route.unavailable")))
            return _scroll(inner)
        status = tr("route.reached") if tr_data.get("reached") else tr("route.not_reached")
        lay.addWidget(QLabel(f"{status} — {len(tr_data.get('hops', []))} {tr('route.hops')}"))
        tree = QTreeWidget()
        tree.setRootIsDecorated(False)
        tree.setAlternatingRowColors(True)
        tree.setFont(MONO)
        tree.setColumnCount(6)
        tree.setHeaderLabels([tr("route.col_ttl"), tr("route.col_ip"), tr("route.col_name"),
                              tr("route.col_rtt"), tr("route.col_loss"), tr("route.col_asn")])
        for hop in tr_data.get("hops", []):
            info = hops_info.get(hop.get("ip", ""), {})
            rtts = hop.get("rtts") or []
            rtt = f"{min(rtts):.1f}/{sum(rtts)/len(rtts):.1f}/{max(rtts):.1f}" if rtts else "*"
            ping = info.get("ping", {})
            loss = f"{ping.get('loss_pct', '')}%" if ping.get("sent") else ""
            asn = info.get("asn", {})
            asn_txt = f"AS{asn['asn']} {asn.get('owner', '')}".strip() if asn.get("asn") else ""
            name = ", ".join(info.get("ptr", []))
            ip = hop.get("ip") or "*"
            item = QTreeWidgetItem([str(hop["ttl"]), ip, name, rtt, loss, asn_txt])
            if not hop.get("ip"):
                item.setForeground(1, QColor("#9ca3af"))
            if info.get("class") and info["class"] != "public":
                item.setForeground(1, QColor("#3b82f6"))
            tree.addTopLevelItem(item)
        for i in range(5):
            tree.resizeColumnToContents(i)
        lay.addWidget(tree, 1)
        return inner

    # ------------------------------------------------------------ Ports
    def ports_widget(self, result) -> QWidget:
        tr = self.tr
        tcp = result.raw.get("tcp", {})
        banners = result.raw.get("banner", {})
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        openp = tcp.get("open", {})
        head = tr("ports.summary", scanned=tcp.get("scanned", 0), open=len(openp),
                  closed=tcp.get("closed", 0), filtered=tcp.get("filtered", 0))
        lay.addWidget(QLabel(head))
        tree = QTreeWidget()
        tree.setColumnCount(4)
        tree.setHeaderLabels([tr("ports.col_port"), tr("ports.col_service"), tr("ports.col_time"),
                              tr("ports.col_flags")])
        tree.setAlternatingRowColors(True)
        for port in sorted(openp):
            meta = portinfo.describe(port, "tcp", self.lang)
            name = meta.get("name", "")
            flags = " ".join(tr("flag." + fl) for fl in meta.get("flags", []))
            ms = openp[port].get("ms")
            top = QTreeWidgetItem([f"{port}/tcp", name, f"{ms} ms" if ms else "", flags])
            top.setFont(0, MONO)
            if "cleartext" in meta.get("flags", []) or port == 23:
                top.setForeground(3, QColor("#f59e0b"))
            if meta.get("description"):
                desc = QTreeWidgetItem([""])
                desc.setFirstColumnSpanned(True)
                label = QLabel(meta["description"] + self._uses(meta))
                label.setWordWrap(True)
                label.setStyleSheet("color:#9ca3af;padding:2px 0 6px 0;")
                top.addChild(desc)
                tree.setItemWidget(desc, 0, label)
            banner = banners.get(port)
            if banner:
                b = QTreeWidgetItem([""])
                b.setFirstColumnSpanned(True)
                blabel = _mono("» " + banner)
                blabel.setStyleSheet("color:#6b7280;")
                top.addChild(b)
                tree.setItemWidget(b, 0, blabel)
            tree.addTopLevelItem(top)
            top.setExpanded(True)
        for i in range(4):
            tree.resizeColumnToContents(i)
        lay.addWidget(tree, 1)
        if "tcp" in result.errors:
            lay.addWidget(_mono("⚠ " + result.errors["tcp"]))
        return inner

    def _uses(self, meta: dict) -> str:
        uses = meta.get("uses", [])
        if not uses:
            return ""
        return "\n" + self.tr("ports.typical") + " " + "; ".join(uses)

    # ------------------------------------------------------------ Web
    def web_widget(self, result) -> QWidget:
        tr = self.tr
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        http = result.raw.get("http", {})
        tls = result.raw.get("tls", {})
        shown = False
        for port in sorted(set(http) | set(tls)):
            page = http.get(port, {})
            tdata = tls.get(port)
            http_ok = bool(page) and not page.get("error")
            tls_ok = bool(tdata) and not tdata.get("error")
            # Ports ohne verwertbare Web-/TLS-Antwort überspringen (z. B. unbekannte offene Ports,
            # die kein HTTP/TLS sprechen) – sonst entstehen leere "Port …"-Kästen voller Fehler.
            if not http_ok and not tls_ok:
                continue
            box = _section(f"Port {port}")
            vbox = box.layout()
            if http_ok:
                rows = [(tr("web.status"), f"{page.get('status')} {page.get('reason', '')}"),
                        (tr("web.title"), page.get("title", "–")),
                        (tr("web.server"), page.get("headers", {}).get("server", "–")),
                        (tr("web.time"), f"{page.get('time_ms', '')} ms")]
                if page.get("location"):
                    rows.append((tr("web.redirect"), page["location"]))
                missing = page.get("missing_security_headers", [])
                if missing:
                    rows.append((tr("web.missing_headers"), ", ".join(missing)))
                vbox.addWidget(_form(rows))
            if tls_ok:
                vbox.addWidget(self._tls_widget(tdata))
            shown = True
            lay.addWidget(box)
        if not shown:
            lay.addWidget(QLabel(tr("web.none")))
        lay.addStretch(1)
        return _scroll(inner)

    def _tls_widget(self, tdata: dict) -> QWidget:
        tr = self.tr
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(0, 0, 0, 0)
        cert = tdata.get("cert", {})
        versions = tdata.get("versions", {})
        vers = " ".join(f"{k}{'✓' if versions[k] else '✗'}" for k in versions if versions[k] is not None)
        rows = [(tr("web.tls_version"), tdata.get("version", "")),
                (tr("web.tls_cipher"), f"{tdata.get('cipher', '')} ({tdata.get('cipher_bits', '')} bit)"),
                (tr("web.tls_versions"), vers)]
        if cert:
            trusted = {True: tr("web.trusted_yes"), False: tr("web.trusted_no"),
                       None: tr("web.trusted_unknown")}[tdata.get("trusted")]
            rows += [(tr("web.cert_subject"), cert.get("subject", "")),
                     (tr("web.cert_issuer"), cert.get("issuer", "")),
                     (tr("web.cert_valid"), f"{cert.get('not_before', '')[:10]} – {cert.get('not_after', '')[:10]} "
                                            f"({cert.get('days_left')} {tr('web.days')})"),
                     (tr("web.cert_san"), ", ".join(cert.get("san", []))[:300]),
                     (tr("web.cert_key"), f"{cert.get('key', '')} {cert.get('key_bits', '')} / {cert.get('signature', '')}"),
                     (tr("web.cert_trust"), trusted)]
        v.addWidget(_form(rows))
        return w

    # ------------------------------------------------------------ Dienste
    def services_widget(self, result) -> QWidget:
        tr = self.tr
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        shown = False
        raw = result.raw
        smb = raw.get("smb", {})
        if smb and not smb.get("closed") and not smb.get("error"):
            rows = [(tr("svc.smb_dialect"), smb.get("dialect", "")),
                    (tr("svc.smb_signing"), tr("g.yes") if smb.get("signing_required") else tr("g.no")),
                    (tr("svc.smb1"), tr("g.yes") if smb.get("smb1") else tr("g.no"))]
            if smb.get("server_time"):
                rows.append((tr("svc.smb_time"), smb["server_time"]))
            box = _section("SMB")
            box.layout().addWidget(_form(rows))
            lay.addWidget(box)
            shown = True
        rdp = raw.get("rdp", {})
        if rdp and not rdp.get("closed") and not rdp.get("error"):
            rows = [(tr("svc.rdp_security"), rdp.get("selected", "")),
                    (tr("svc.rdp_nla"), tr("g.yes") if rdp.get("nla_required") else tr("g.no"))]
            box = _section("RDP")
            box.layout().addWidget(_form(rows))
            lay.addWidget(box)
            shown = True
        ntp = raw.get("ntp", {})
        if ntp.get("answer"):
            rows = [(tr("svc.ntp_stratum"), str(ntp.get("stratum", ""))),
                    (tr("svc.ntp_ref"), ntp.get("refid", "")),
                    (tr("svc.ntp_offset"), f"{ntp.get('offset_ms', '')} ms")]
            box = _section("NTP")
            box.layout().addWidget(_form(rows))
            lay.addWidget(box)
            shown = True
        ds = raw.get("dnsserver", {})
        if ds.get("answer"):
            rows = [(tr("svc.dns_recursive"), tr("g.yes") if ds.get("recursion_available") else tr("g.no")),
                    (tr("svc.dns_external"), tr("g.yes") if ds.get("resolved_external") else tr("g.no"))]
            box = _section(tr("svc.dns_title"))
            box.layout().addWidget(_form(rows))
            lay.addWidget(box)
            shown = True
        if not shown:
            lay.addWidget(QLabel(tr("svc.none")))
        lay.addStretch(1)
        return _scroll(inner)

    # ------------------------------------------------------------ DNS
    def dns_widget(self, result) -> QWidget:
        tr = self.tr
        dns = result.raw.get("dns", {})
        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(12, 12, 12, 12)
        if not dns:
            lay.addWidget(QLabel(tr("dns.none")))
            return _scroll(inner)
        records = dns.get("records", {})
        rbox = _section(tr("dns.records"))
        tree = QTreeWidget()
        tree.setColumnCount(3)
        tree.setHeaderLabels([tr("dns.type"), tr("dns.value"), "TTL"])
        tree.setFont(MONO)
        for rtype, data in records.items():
            for value in data.get("values", []):
                tree.addTopLevelItem(QTreeWidgetItem([rtype, value, str(data.get("ttl") or "")]))
        for i in range(3):
            tree.resizeColumnToContents(i)
        tree.setMaximumHeight(240)
        rbox.layout().addWidget(tree)
        lay.addWidget(rbox)

        ns = dns.get("ns", [])
        if ns:
            nbox = _section(tr("dns.ns"))
            ntree = QTreeWidget()
            ntree.setColumnCount(4)
            ntree.setHeaderLabels([tr("dns.ns_name"), "IP", tr("dns.ns_serial"), tr("dns.ns_recursive")])
            ntree.setFont(MONO)
            for n in ns:
                ntree.addTopLevelItem(QTreeWidgetItem([n.get("name", ""), ", ".join(n.get("ips", [])),
                                                       str(n.get("serial") or ""),
                                                       tr("g.yes") if n.get("recursive") else ""]))
            for i in range(4):
                ntree.resizeColumnToContents(i)
            ntree.setMaximumHeight(160)
            nbox.layout().addWidget(ntree)
            lay.addWidget(nbox)

        sec = dns.get("dnssec", {})
        mail = dns.get("mail", {})
        meta_rows = [(tr("dns.zone"), dns.get("zone", "")),
                     ("DNSSEC", f"DNSKEY {sec.get('dnskey', 0)}, DS {sec.get('ds', 0)}")]
        if mail.get("spf"):
            meta_rows.append(("SPF", mail["spf"].get("all", "")))
        if mail.get("dmarc"):
            meta_rows.append(("DMARC", mail["dmarc"].get("p", "")))
        if mail.get("dkim_selectors"):
            meta_rows.append(("DKIM", ", ".join(mail["dkim_selectors"])))
        mbox = _section(tr("dns.meta"))
        mbox.layout().addWidget(_form(meta_rows))
        lay.addWidget(mbox)

        if mail.get("mx"):
            mxbox = _section("MX")
            for mx in mail["mx"]:
                mxbox.layout().addWidget(_mono(f"{mx.get('preference', '')}  {mx.get('host', '')}  "
                                               f"{', '.join(mx.get('ips', []))}"))
            lay.addWidget(mxbox)
        lay.addStretch(1)
        return _scroll(inner)

    # ------------------------------------------------------------ Kategorien, die Daten haben
    def category_order(self, result) -> list[str]:
        raw = result.raw
        present = []
        if any(k in raw for k in ("address", "ping", "reverse", "mac", "netbios", "asn", "mtu")) or result.ip:
            present.append("general")
        if raw.get("traceroute", {}).get("hops"):
            present.append("route")
        if raw.get("tcp", {}).get("open") or "tcp" in result.errors:
            present.append("ports")
        http, tls = raw.get("http", {}), raw.get("tls", {})
        if any((http.get(p) and not http.get(p, {}).get("error"))
               or (tls.get(p) and not tls.get(p, {}).get("error"))
               for p in set(http) | set(tls)):
            present.append("web")
        if any(raw.get(k, {}).get("answer") or (raw.get(k) and not raw.get(k, {}).get("closed"))
               for k in ("smb", "rdp", "ntp", "dnsserver")):
            present.append("services")
        if raw.get("dns"):
            present.append("dns")
        present.append("findings")
        return present

    def widget_for(self, category: str, result) -> QWidget:
        return {
            "general": self.general_widget, "route": self.route_widget, "ports": self.ports_widget,
            "web": self.web_widget, "services": self.services_widget, "dns": self.dns_widget,
            "findings": self.findings_widget,
        }[category](result)
