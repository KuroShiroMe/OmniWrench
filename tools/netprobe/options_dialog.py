"""Optionsdialog: Tests nach Kategorie ein-/ausschalten und Parameter einstellen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .engine import CATEGORIES, DEFAULT_OPTIONS, TESTS


class OptionsDialog(QDialog):
    def __init__(self, options: dict, tr, parent=None, link_ctl=None):
        """`link_ctl` (optional) steuert den eingebauten Gegenstellen-Server und den Mini-Tool-Export.

        Erwartet die Methoden ``export(opts, parent)``, ``toggle_serve(opts, parent)``, ``serve_running()``
        und ``serve_info()`` – bereitgestellt vom Tool, damit der Server den Dialog überlebt.
        """
        super().__init__(parent)
        self.tr = tr
        self.link_ctl = link_ctl
        self.setWindowTitle(tr("opt.title"))
        self._opts = DEFAULT_OPTIONS | options
        tests = DEFAULT_OPTIONS["tests"] | options.get("tests", {})
        self.checks: dict[str, QCheckBox] = {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)

        # Tests nach Kategorie (der Leitungstest bekommt unten einen eigenen Abschnitt)
        by_cat: dict[str, list] = {c: [] for c in CATEGORIES}
        for t in TESTS:
            by_cat.setdefault(t.category, []).append(t)
        for cat in CATEGORIES:
            if cat == "link":
                continue
            box = QGroupBox(tr("cat." + cat))
            grid = QVBoxLayout(box)
            head = QHBoxLayout()
            all_btn = QCheckBox(tr("opt.toggle_all"))
            all_btn.setTristate(True)
            head.addWidget(all_btn)
            head.addStretch(1)
            grid.addLayout(head)
            cat_checks = []
            for t in by_cat[cat]:
                cb = QCheckBox(tr("test." + t.id))
                cb.setChecked(bool(tests.get(t.id, t.default)))
                cb.setToolTip(tr("test." + t.id + ".hint", default=""))
                self.checks[t.id] = cb
                cat_checks.append(cb)
                grid.addWidget(cb)
                cb.stateChanged.connect(lambda _s, b=all_btn, cc=cat_checks: self._sync_head(b, cc))
            all_btn.clicked.connect(lambda _c, cc=cat_checks, b=all_btn: self._toggle_all(b, cc))
            self._sync_head(all_btn, cat_checks)
            lay.addWidget(box)

        # Parameter
        params = QGroupBox(tr("opt.params"))
        form = QFormLayout(params)
        self.port_profile = QComboBox()
        for key in ("quick", "standard", "extended", "full", "custom"):
            self.port_profile.addItem(tr("profile." + key), key)
        self.port_profile.setCurrentIndex(max(0, self.port_profile.findData(self._opts["port_profile"])))
        self.port_profile.currentIndexChanged.connect(self._update_custom)
        form.addRow(tr("opt.port_profile"), self.port_profile)
        self.custom_ports = QLineEdit(self._opts["custom_ports"])
        self.custom_ports.setPlaceholderText("80, 443, 8000-8100")
        form.addRow(tr("opt.custom_ports"), self.custom_ports)
        self.ping_count = self._spin(1, 100, self._opts["ping_count"])
        form.addRow(tr("opt.ping_count"), self.ping_count)
        self.ping_warmup = self._spin(0, 10, self._opts["ping_warmup"])
        form.addRow(tr("opt.ping_warmup"), self.ping_warmup)
        self.ping_timeout = self._spin(200, 10000, self._opts["ping_timeout_ms"], " ms", 100)
        form.addRow(tr("opt.ping_timeout"), self.ping_timeout)
        self.ping_interval = self._spin(0, 5000, self._opts["ping_interval_ms"], " ms", 50)
        form.addRow(tr("opt.ping_interval"), self.ping_interval)
        self.port_timeout = self._spin(100, 10000, self._opts["port_timeout_ms"], " ms", 100)
        form.addRow(tr("opt.port_timeout"), self.port_timeout)
        self.dns_timeout = self._spin(500, 20000, self._opts["dns_timeout_ms"], " ms", 500)
        form.addRow(tr("opt.dns_timeout"), self.dns_timeout)
        self.max_hosts = self._spin(1, 256, self._opts["max_hosts"])
        form.addRow(tr("opt.max_hosts"), self.max_hosts)
        self.max_sockets = self._spin(16, 2000, self._opts["max_sockets"], "", 10)
        form.addRow(tr("opt.max_sockets"), self.max_sockets)
        self.max_hops = self._spin(5, 64, self._opts["max_hops"])
        form.addRow(tr("opt.max_hops"), self.max_hops)
        self.only_alive = QCheckBox(tr("opt.only_alive"))
        self.only_alive.setChecked(self._opts["only_alive"])
        form.addRow("", self.only_alive)
        self.oui_download = QCheckBox(tr("opt.oui_download"))
        self.oui_download.setChecked(self._opts["oui_download"])
        form.addRow("", self.oui_download)
        lay.addWidget(params)
        self._update_custom()

        lay.addWidget(self._link_section())

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset = buttons.addButton(tr("opt.reset"), QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self._reset)
        outer.addWidget(buttons)
        self.resize(560, 640)

    def _link_section(self) -> QGroupBox:
        """Abschnitt Leitungstest: Gegenstelle, Messungen, Mini-Tool-Export und eingebauter Server."""
        tr = self.tr
        o = self._opts
        box = QGroupBox(tr("cat.link"))
        v = QVBoxLayout(box)
        v.addWidget(self._wrap_note(tr("link.section_hint")))

        self.checks["link"] = QCheckBox(tr("link.enable"))
        self.checks["link"].setChecked(bool(o["tests"].get("link", False)))
        v.addWidget(self.checks["link"])

        form = QFormLayout()
        self.link_port = self._spin(1, 65535, o["link_port"], "", 1)
        form.addRow(tr("link.port"), self.link_port)
        token_row = QHBoxLayout()
        self.link_token = QLineEdit(str(o.get("link_token", "")))
        self.link_token.setPlaceholderText(tr("link.token_hint"))
        gen = QPushButton(tr("link.token_new"))
        gen.clicked.connect(self._new_token)
        token_row.addWidget(self.link_token, 1)
        token_row.addWidget(gen)
        tw = QWidget()
        tw.setLayout(token_row)
        form.addRow(tr("link.token"), tw)
        self.link_seconds = self._spin(1, 60, o["link_seconds"], " s", 1)
        form.addRow(tr("link.seconds"), self.link_seconds)
        self.link_connections = self._spin(1, 64, o["link_connections"], "", 1)
        form.addRow(tr("link.connections"), self.link_connections)
        self.link_scan_ports = QLineEdit(str(o.get("link_scan_ports", "")))
        self.link_scan_ports.setPlaceholderText(tr("link.scan_ports_hint"))
        form.addRow(tr("link.scan_ports"), self.link_scan_ports)
        v.addLayout(form)

        measures = QHBoxLayout()
        self.link_latency = QCheckBox(tr("link.latency"))
        self.link_download = QCheckBox(tr("link.download"))
        self.link_upload = QCheckBox(tr("link.upload"))
        self.link_load = QCheckBox(tr("link.load"))
        self.link_portscan = QCheckBox(tr("link.portscan"))
        for cb, key in ((self.link_latency, "link_latency"), (self.link_download, "link_download"),
                        (self.link_upload, "link_upload"), (self.link_load, "link_load"),
                        (self.link_portscan, "link_portscan")):
            cb.setChecked(bool(o.get(key, True)))
            measures.addWidget(cb)
        measures.addStretch(1)
        v.addLayout(measures)

        # Mini-Tool-Export (eigenständige Datei ohne Python / als Skript) und eingebauter Gegenstellen-Server
        actions = QHBoxLayout()
        self.export_exe_btn = QPushButton(tr("link.export_exe"))
        self.export_exe_btn.clicked.connect(self._export_binary)
        self.export_py_btn = QPushButton(tr("link.export_script"))
        self.export_py_btn.clicked.connect(self._export_script)
        self.serve_btn = QPushButton()
        self.serve_btn.clicked.connect(self._toggle_serve)
        actions.addWidget(self.export_exe_btn)
        actions.addWidget(self.export_py_btn)
        actions.addWidget(self.serve_btn)
        actions.addStretch(1)
        v.addLayout(actions)
        self.serve_status = QLabel()
        self.serve_status.setStyleSheet("color:#9ca3af;")
        self.serve_status.setWordWrap(True)
        v.addWidget(self.serve_status)
        if self.link_ctl is None:
            self.export_exe_btn.setEnabled(False)
            self.export_py_btn.setEnabled(False)
            self.serve_btn.setEnabled(False)
        else:
            has_binary = self.link_ctl.agent_binary() is not None
            self.export_exe_btn.setEnabled(has_binary)
            if not has_binary:
                self.export_exe_btn.setToolTip(self.tr("link.export_exe_missing"))
        self._refresh_serve()
        return box

    def _wrap_note(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color:#9ca3af;")
        return lbl

    def _new_token(self) -> None:
        from .linkagent import new_token
        self.link_token.setText(new_token())

    def _export_binary(self) -> None:
        if self.link_ctl is not None:
            self.link_ctl.export_binary(self._collect(), self)

    def _export_script(self) -> None:
        if self.link_ctl is not None:
            self.link_ctl.export_script(self._collect(), self)

    def _toggle_serve(self) -> None:
        if self.link_ctl is not None:
            self.link_ctl.toggle_serve(self._collect(), self)
            self._refresh_serve()

    def _refresh_serve(self) -> None:
        running = bool(self.link_ctl and self.link_ctl.serve_running())
        self.serve_btn.setText(self.tr("link.serve_stop") if running else self.tr("link.serve_start"))
        if self.link_ctl is None:
            self.serve_status.setText(self.tr("link.serve_unavailable"))
        elif running:
            self.serve_status.setText(self.link_ctl.serve_info())
        else:
            self.serve_status.setText(self.tr("link.serve_idle"))

    def _spin(self, lo, hi, value, suffix="", step=1):
        s = QSpinBox()
        s.setRange(lo, hi)
        s.setValue(int(value))
        s.setSingleStep(step)
        if suffix:
            s.setSuffix(suffix)
        return s

    def _toggle_all(self, head: QCheckBox, checks: list[QCheckBox]) -> None:
        target = head.checkState() != Qt.CheckState.Unchecked
        for cb in checks:
            cb.setChecked(target)

    def _sync_head(self, head: QCheckBox, checks: list[QCheckBox]) -> None:
        n = sum(cb.isChecked() for cb in checks)
        head.blockSignals(True)
        head.setCheckState(Qt.CheckState.Checked if n == len(checks)
                           else Qt.CheckState.Unchecked if n == 0 else Qt.CheckState.PartiallyChecked)
        head.blockSignals(False)

    def _update_custom(self) -> None:
        self.custom_ports.setEnabled(self.port_profile.currentData() == "custom")

    def _reset(self) -> None:
        for t in TESTS:
            self.checks[t.id].setChecked(t.default)
        self.port_profile.setCurrentIndex(self.port_profile.findData("standard"))
        self.ping_count.setValue(DEFAULT_OPTIONS["ping_count"])
        self.ping_warmup.setValue(DEFAULT_OPTIONS["ping_warmup"])
        self.ping_timeout.setValue(DEFAULT_OPTIONS["ping_timeout_ms"])
        self.ping_interval.setValue(DEFAULT_OPTIONS["ping_interval_ms"])
        self.port_timeout.setValue(DEFAULT_OPTIONS["port_timeout_ms"])
        self.dns_timeout.setValue(DEFAULT_OPTIONS["dns_timeout_ms"])
        self.max_hosts.setValue(DEFAULT_OPTIONS["max_hosts"])
        self.max_sockets.setValue(DEFAULT_OPTIONS["max_sockets"])
        self.max_hops.setValue(DEFAULT_OPTIONS["max_hops"])
        self.only_alive.setChecked(DEFAULT_OPTIONS["only_alive"])
        self.oui_download.setChecked(DEFAULT_OPTIONS["oui_download"])
        self.link_port.setValue(DEFAULT_OPTIONS["link_port"])
        self.link_seconds.setValue(DEFAULT_OPTIONS["link_seconds"])
        self.link_connections.setValue(DEFAULT_OPTIONS["link_connections"])
        self.link_scan_ports.setText(DEFAULT_OPTIONS["link_scan_ports"])
        for cb, key in ((self.link_latency, "link_latency"), (self.link_download, "link_download"),
                        (self.link_upload, "link_upload"), (self.link_load, "link_load"),
                        (self.link_portscan, "link_portscan")):
            cb.setChecked(DEFAULT_OPTIONS[key])
        # Token bewusst stehen lassen (muss mit der Gegenstelle übereinstimmen).

    def _collect(self) -> dict:
        return {
            "tests": {t.id: self.checks[t.id].isChecked() for t in TESTS},
            "port_profile": self.port_profile.currentData(),
            "custom_ports": self.custom_ports.text(),
            "ping_count": self.ping_count.value(),
            "ping_warmup": self.ping_warmup.value(),
            "ping_timeout_ms": self.ping_timeout.value(),
            "ping_interval_ms": self.ping_interval.value(),
            "port_timeout_ms": self.port_timeout.value(),
            "dns_timeout_ms": self.dns_timeout.value(),
            "max_hosts": self.max_hosts.value(),
            "max_sockets": self.max_sockets.value(),
            "max_hops": self.max_hops.value(),
            "only_alive": self.only_alive.isChecked(),
            "oui_download": self.oui_download.isChecked(),
            "link_port": self.link_port.value(),
            "link_token": self.link_token.text().strip(),
            "link_seconds": self.link_seconds.value(),
            "link_connections": self.link_connections.value(),
            "link_scan_ports": self.link_scan_ports.text(),
            "link_latency": self.link_latency.isChecked(),
            "link_download": self.link_download.isChecked(),
            "link_upload": self.link_upload.isChecked(),
            "link_load": self.link_load.isChecked(),
            "link_portscan": self.link_portscan.isChecked(),
        }

    def result(self) -> dict:
        return self._collect()
