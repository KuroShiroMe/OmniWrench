"""Eingabe in Ziele zerlegen: IP, DNS-Name, Netz (CIDR), Bereich (a-b) oder Liste."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass

HOSTNAME = re.compile(r"^(?=.{1,253}$)(?!-)[A-Za-z0-9_-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9_-]{1,63}(?<!-))*\.?$")
# Bereich: eine IPv4-Adresse, Bindestrich, dann entweder eine volle IPv4 oder nur das letzte Oktett.
IPV4_RANGE = re.compile(r"^(\d{1,3}(?:\.\d{1,3}){3})-(\d{1,3}(?:\.\d{1,3}){3}|\d{1,3})$")


class TargetError(ValueError):
    pass


@dataclass
class Target:
    address: str            # IP-Adresse oder (noch nicht aufgelöster) Name
    name: str = ""          # eingegebener DNS-Name
    from_network: bool = False
    group: str = ""         # ursprüngliche Netz-/Bereichsangabe (z. B. "192.168.1.0/24"), sonst leer

    @property
    def label(self) -> str:
        return self.name or self.address


def _hosts(net: ipaddress._BaseNetwork):
    if net.version == 4 and net.prefixlen < 31:
        return net.hosts()
    return iter(net)


def parse(text: str, limit: int) -> list[Target]:
    """Zerlegt die Eingabe; mehrere Angaben durch Komma, Semikolon oder Leerzeichen getrennt."""
    items = [p for p in re.split(r"[,;\s]+", text.strip()) if p]
    if not items:
        raise TargetError("empty")
    result: list[Target] = []
    seen: set[str] = set()

    def add(t: Target) -> None:
        if t.address in seen:
            return
        if len(result) >= limit:
            raise TargetError(f"limit:{limit}")
        seen.add(t.address)
        result.append(t)

    for item in items:
        if "/" in item:
            try:
                net = ipaddress.ip_network(item, strict=False)
            except ValueError as exc:
                raise TargetError(f"invalid:{item}") from exc
            if net.num_addresses > limit + 2:
                raise TargetError(f"limit:{limit}")
            single = net.num_addresses == 1
            group = "" if single else item
            for ip in _hosts(net):
                add(Target(str(ip), from_network=not single, group=group))
        elif (m := IPV4_RANGE.match(item)):
            first, last = m.group(1), m.group(2)
            try:
                start = ipaddress.ip_address(first)
                end = ipaddress.ip_address(last) if "." in last else \
                    ipaddress.ip_address(".".join(first.split(".")[:3] + [last]))
            except ValueError as exc:
                raise TargetError(f"invalid:{item}") from exc
            if end < start or int(end) - int(start) >= limit:
                raise TargetError(f"limit:{limit}")
            for n in range(int(start), int(end) + 1):
                add(Target(str(ipaddress.ip_address(n)), from_network=True, group=item))
        else:
            try:
                add(Target(str(ipaddress.ip_address(item.strip("[]")))))
            except ValueError:
                # Sieht aus wie eine (fehlerhafte) IPv4, ist aber keine gültige -> echter Fehler statt "Name"
                if not HOSTNAME.match(item) or re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", item):
                    raise TargetError(f"invalid:{item}") from None
                name = item.rstrip(".").lower()
                add(Target(name, name=name))
    return result


def classify(ip: str) -> str:
    """Grobe Einordnung einer Adresse (Schlüssel für die Übersetzung)."""
    addr = ipaddress.ip_address(ip)
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return "cgnat"
    for attr in ("is_loopback", "is_link_local", "is_multicast", "is_private", "is_reserved", "is_unspecified"):
        if getattr(addr, attr):
            return attr[3:]
    return "public"
