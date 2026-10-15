"""Subnetzrechner für IPv4 und IPv6."""

from __future__ import annotations

import csv
import ipaddress
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSpinBox, QSplitter, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from omniwrench.sdk import ToolBase

THOUSANDS = {"de": ".", "fr": " ", "es": "."}


def parse_network(text: str) -> tuple[ipaddress._BaseNetwork, ipaddress._BaseAddress]:
    """Akzeptiert '10.1.2.3/24', '10.1.2.3 255.255.255.0', '10.1.2.3/255.255.255.0' oder 'fd00::1/64'."""
    text = text.strip().replace(" ", "/", 1) if " " in text.strip() else text.strip()
    if "/" not in text:
        text += "/32" if ":" not in text else "/128"
    iface = ipaddress.ip_interface(text)
    return iface.network, iface.ip


def network_details(net, ip, tr: Callable[..., str], fmt: Callable[[int], str]) -> list[tuple[str, str]]:
    rows = [(tr("d.input"), str(ip)), (tr("d.network"), str(net.network_address)),
            (tr("d.prefix"), f"/{net.prefixlen}")]
    if net.version == 4:
        hosts = net.num_addresses - 2 if net.prefixlen < 31 else net.num_addresses
        first = net.network_address + (1 if net.prefixlen < 31 else 0)
        last = net.broadcast_address - (1 if net.prefixlen < 31 else 0)
        rows += [
            (tr("d.netmask"), str(net.netmask)),
            (tr("d.wildcard"), str(net.hostmask)),
            (tr("d.broadcast"), str(net.broadcast_address)),
            (tr("d.first_host"), str(first)),
            (tr("d.last_host"), str(last)),
            (tr("d.usable_hosts"), fmt(hosts)),
            (tr("d.netmask_binary"), ".".join(f"{int(o):08b}" for o in str(net.netmask).split("."))),
            (tr("d.type"), _kind(net, tr)),
        ]
    else:
        rows += [
            (tr("d.first_addr"), str(net.network_address)),
            (tr("d.last_addr"), str(net.broadcast_address)),
            (tr("d.addresses"), f"2^{128 - net.prefixlen}" if net.prefixlen < 64 else fmt(net.num_addresses)),
            (tr("d.compressed"), net.compressed),
            (tr("d.exploded"), net.exploded),
            (tr("d.type"), _kind(net, tr)),
        ]
    return rows


def _kind(net, tr) -> str:
    for attr in ("is_loopback", "is_link_local", "is_multicast", "is_private", "is_reserved", "is_global"):
        if getattr(net, attr, False):
            return tr("kind." + attr[3:])
    return "–"


class SubnetCalculator(ToolBase):
    def _fmt(self, number: int) -> str:
        sep = THOUSANDS.get(self.context.language.split("_")[0], ",")
        return f"{number:,}".replace(",", sep)

    def create_widget(self, parent=None) -> QWidget:
        tr = self.context.tr
        root = QWidget(parent)
        lay = QVBoxLayout(root)
        lay.setContentsMargins(16, 16, 16, 16)

        top = QHBoxLayout()
        self.input = QLineEdit(self.context.settings.get("default_network"))
        self.input.setPlaceholderText(tr("ui.input_placeholder"))
        self.input.setFont(QFont("Consolas", 11))
        self.input.textChanged.connect(self._calculate)
        top.addWidget(QLabel(tr("ui.network_label")))
        top.addWidget(self.input, 1)
        lay.addLayout(top)

        self.error = QLabel()
        self.error.setStyleSheet("color: #ef4444")
        lay.addWidget(self.error)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        details_box = QGroupBox(tr("ui.details"))
        self.details = QFormLayout(details_box)
        splitter.addWidget(details_box)

        split_box = QGroupBox(tr("ui.split"))
        sl = QVBoxLayout(split_box)
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("ui.new_prefix")))
        self.new_prefix = QSpinBox()
        self.new_prefix.valueChanged.connect(self._split)
        row.addWidget(self.new_prefix)
        self.split_info = QLabel()
        row.addWidget(self.split_info, 1)
        export = QPushButton(tr("ui.export"))
        export.clicked.connect(self._export)
        row.addWidget(export)
        sl.addLayout(row)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(
            ["#", tr("col.network"), tr("col.first"), tr("col.last"), tr("col.broadcast")])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().hide()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        sl.addWidget(self.table)
        splitter.addWidget(split_box)
        splitter.setSizes([380, 620])
        lay.addWidget(splitter, 1)

        self._net = None
        self._calculate()
        return root

    def _calculate(self) -> None:
        while self.details.rowCount():
            self.details.removeRow(0)
        try:
            net, ip = parse_network(self.input.text())
        except ValueError as exc:
            self.error.setText(self.context.tr("ui.invalid", error=exc))
            self._net = None
            self.table.setRowCount(0)
            return
        self.error.setText("")
        self._net = net
        for key, value in network_details(net, ip, self.context.tr, self._fmt):
            val = QLabel(value)
            val.setFont(QFont("Consolas", 10))
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            self.details.addRow(key + ":", val)
        max_len = 32 if net.version == 4 else 128
        self.new_prefix.blockSignals(True)
        self.new_prefix.setRange(net.prefixlen, max_len)
        if self.new_prefix.value() <= net.prefixlen:
            self.new_prefix.setValue(min(net.prefixlen + 2, max_len))
        self.new_prefix.blockSignals(False)
        self._split()

    def _subnets(self):
        if self._net is None:
            return []
        limit = int(self.context.settings.get("max_subnets", 1024))
        result = []
        for i, sub in enumerate(self._net.subnets(new_prefix=self.new_prefix.value())):
            if i >= limit:
                break
            result.append(sub)
        return result

    def _split(self) -> None:
        if self._net is None:
            return
        total = 2 ** (self.new_prefix.value() - self._net.prefixlen)
        subs = self._subnets()
        info = self.context.tr("ui.split_info", count=self._fmt(total))
        if len(subs) < total:
            info += self.context.tr("ui.split_info_limited", shown=self._fmt(len(subs)))
        self.split_info.setText(info)
        self.table.setRowCount(len(subs))
        for r, sub in enumerate(subs):
            if sub.version == 4 and sub.prefixlen < 31:
                first, last = sub.network_address + 1, sub.broadcast_address - 1
            else:
                first, last = sub.network_address, sub.broadcast_address
            values = [str(r + 1), str(sub), str(first), str(last),
                      str(sub.broadcast_address) if sub.version == 4 else "–"]
            for c, v in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(v))

    def _export(self) -> None:
        subs = self._subnets()
        if not subs:
            return
        start_dir = self.context.settings.get("export_dir") or str(Path.home())
        default = Path(start_dir) / f"subnets_{str(self._net).replace('/', '_').replace(':', '-')}.csv"
        path, _ = QFileDialog.getSaveFileName(self.table, self.context.tr("ui.export_title"), str(default), "CSV (*.csv)")
        if not path:
            return
        sep = self.context.settings.get("csv_separator", ";")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f, delimiter=sep)
            writer.writerow([self.table.horizontalHeaderItem(c).text() for c in range(self.table.columnCount())])
            for r in range(self.table.rowCount()):
                writer.writerow([self.table.item(r, c).text() for c in range(self.table.columnCount())])
        self.context.notify(self.context.tr("ui.exported", count=len(subs), path=path))

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "max_subnets" in changed_keys:
            self._split()
