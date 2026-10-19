"""Optionsdialog: Tests nach Kategorie ein-/ausschalten und Parameter einstellen."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QScrollArea, QSpinBox, QVBoxLayout, QWidget,
)

from .engine import CATEGORIES, DEFAULT_OPTIONS, TESTS


class OptionsDialog(QDialog):
    def __init__(self, options: dict, tr, parent=None):
        super().__init__(parent)
        self.tr = tr
        self.setWindowTitle(tr("opt.title"))
        self._opts = DEFAULT_OPTIONS | options
        tests = DEFAULT_OPTIONS["tests"] | options.get("tests", {})
        self.checks: dict[str, QCheckBox] = {}

        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        lay = QVBoxLayout(inner)

        # Tests nach Kategorie
        by_cat: dict[str, list] = {c: [] for c in CATEGORIES}
        for t in TESTS:
            by_cat[t.category].append(t)
        for cat in CATEGORIES:
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

        scroll.setWidget(inner)
        outer.addWidget(scroll, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        reset = buttons.addButton(tr("opt.reset"), QDialogButtonBox.ButtonRole.ResetRole)
        reset.clicked.connect(self._reset)
        outer.addWidget(buttons)
        self.resize(560, 640)

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

    def result(self) -> dict:
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
        }
