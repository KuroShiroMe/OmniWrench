"""Verfremdung: echte Werte werden vor dem Senden durch Platzhalter ersetzt und in Antworten
lokal zurückübersetzt. Die Zuordnung gehört zum Chat (thread["state"]["pseudo"]), damit derselbe
Wert im ganzen Verlauf denselben Platzhalter behält.

Platzhalter: IP-1, NET1.57 (Netz bleibt erkennbar), IP6-1, MAC-1, HOST-1, DOMAIN-1, USER-1, EMAIL-1.
Ausgenommen sind Werte ohne Aussagekraft über die Umgebung (127.0.0.1, 0.0.0.0, Netzmasken,
bekannte öffentliche Domänen, Dateinamen).
"""

from __future__ import annotations

import ipaddress
import re
from typing import Any

IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?![\w.]*\d)")
IPV6 = re.compile(r"(?<![\w:.])[0-9A-Fa-f]{0,4}(?::[0-9A-Fa-f]{0,4}){2,7}(?![\w:])")
MAC = re.compile(r"(?<![\w:-])(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}(?![\w:-])")
EMAIL = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
FQDN = re.compile(r"(?<![\w@./\\-])(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z][A-Za-z0-9-]{1,23}(?![\w-])")
DOWNLEVEL = re.compile(r"(?<![\w\\])([A-Za-z][\w-]{0,14})\\([\w.$-]{1,64})(?![\w\\])")
PLACEHOLDER = re.compile(r"\b(?:IP6?|MAC|HOST|DOMAIN|USER|EMAIL)-\d+\b|\bNET\d+\.\d+\b")

FILE_SUFFIXES = {"json", "py", "md", "txt", "exe", "dll", "msi", "ps1", "psm1", "psd1", "log", "xml", "csv", "zip",
                 "png", "jpg", "jpeg", "gif", "svg", "ico", "ini", "cfg", "conf", "yaml", "yml", "html", "htm", "js",
                 "css", "bat", "cmd", "reg", "sql", "vsdx", "vssx", "pdf", "docx", "xlsx", "pptx", "toml", "lock",
                 "sh", "deb", "tar", "gz", "mp3", "mp4", "wav", "webp", "db", "owai", "pfx", "cer", "crt", "key"}
PUBLIC_DOMAINS = ("microsoft.com", "windows.com", "office.com", "azure.com", "live.com", "github.com", "github.io",
                  "githubusercontent.com", "google.com", "gstatic.com", "openai.com", "chatgpt.com", "anthropic.com",
                  "claude.ai", "claude.com", "kuroshiro.me", "python.org", "pypi.org", "mozilla.org", "apple.com",
                  "cloudflare.com", "wikipedia.org", "example.com", "example.org", "example.net", "localhost",
                  "openrouter.ai", "x.ai", "mistral.ai", "ollama.com", "w3.org", "ietf.org", "letsencrypt.org")
HOST_KEYS = ("host", "computer", "server", "fqdn", "machine", "dns_name", "dnsname", "netbios", "client_name",
             "clientname", "hostname")
USER_KEYS = ("user", "owner", "login", "account", "sam", "upn")
PSEUDO_SKIP_KEYS = ("tool", "function", "type", "kind", "status", "state", "version", "option")


class Pseudonymizer:
    def __init__(self, state: dict | None = None, kinds: dict | None = None, enabled: bool = True):
        self.state = state if state is not None else {}
        self.map: dict[str, str] = self.state.setdefault("map", {})       # echt -> Platzhalter
        self.counters: dict[str, int] = self.state.setdefault("n", {})
        self.rev: dict[str, str] = self.state.setdefault("rev", {})       # Platzhalter -> Original
        self.kinds = kinds or {}
        self.enabled = enabled

    def on(self, kind: str) -> bool:
        return self.enabled and self.kinds.get(kind, True)

    # ------------------------------------------------------------ Zuordnung
    def _token(self, kind: str, real: str) -> str:
        key = real.lower()
        if key in self.map:
            return self.map[key]
        self.counters[kind] = self.counters.get(kind, 0) + 1
        token = f"{kind}-{self.counters[kind]}"
        self.map[key] = token
        self.rev.setdefault(token, real)
        return token

    def _ipv4(self, text: str) -> str:
        try:
            ip = ipaddress.IPv4Address(text)
        except ValueError:
            return text
        if ip.is_loopback or ip.is_unspecified or text.startswith("255.") or text.endswith(".255.255") \
                or str(ip) in ("255.255.255.255",) or _is_mask(text):
            return text
        if self.kinds.get("keep_network", True):
            net = ".".join(text.split(".")[:3])
            key = net + ".*"
            if key not in self.map:
                self.counters["NET"] = self.counters.get("NET", 0) + 1
                self.map[key] = f"NET{self.counters['NET']}"
            token = f"{self.map[key]}.{text.split('.')[3]}"
            self.map.setdefault(text, token)
            return token
        return self._token("IP", text)

    def _ipv6(self, text: str) -> str:
        try:
            ip = ipaddress.IPv6Address(text)
        except ValueError:
            return text
        if ip.is_loopback or ip.is_unspecified:
            return text
        return self._token("IP6", str(ip))

    def _fqdn(self, text: str) -> str:
        if PLACEHOLDER.search(text):
            return text
        low = text.lower().rstrip(".")
        suffix = low.rsplit(".", 1)[-1]
        if suffix in FILE_SUFFIXES or suffix.isdigit():
            return text
        if any(low == d or low.endswith("." + d) for d in PUBLIC_DOMAINS):
            return text
        if low in self.map:
            return self.map[low]
        labels = low.split(".")
        if len(labels) >= 3 and self.on("host"):
            host, domain = labels[0], ".".join(labels[1:])
            dom = self._token("DOMAIN", domain) if self.on("domain") else domain
            token = f"{self._token('HOST', host)}.{dom}"
            self.map[low] = token
            self.rev.setdefault(token, text)
            return token
        return self._token("DOMAIN", text) if self.on("domain") else text

    # ------------------------------------------------------------ Text
    def encode(self, text: str) -> str:
        if not self.enabled or not text:
            return text
        # Bereits bekannte Werte (z. B. Hostnamen aus Funktionsergebnissen) auch im Freitext ersetzen
        for real, token in sorted(self.map.items(), key=lambda kv: -len(kv[0])):
            if real.endswith(".*") or len(real) < 3:
                continue
            text = re.sub(rf"(?<![\w.-]){re.escape(real)}(?![\w-]|\.\w)", token, text, flags=re.IGNORECASE)
        if self.on("email"):
            text = EMAIL.sub(lambda m: self._token("EMAIL", m.group(0)), text)
        if self.on("mac"):
            text = MAC.sub(lambda m: self._token("MAC", m.group(0)), text)
        if self.on("ip"):
            text = IPV4.sub(lambda m: self._ipv4(m.group(0)), text)
            text = IPV6.sub(lambda m: self._ipv6(m.group(0)), text)
        if self.on("host") or self.on("domain"):
            text = FQDN.sub(lambda m: self._fqdn(m.group(0)), text)
        if self.on("user"):
            text = DOWNLEVEL.sub(lambda m: self._downlevel(m), text)
        return text

    def _downlevel(self, m: re.Match) -> str:
        dom, user = m.group(1), m.group(2)
        if PLACEHOLDER.fullmatch(dom) or PLACEHOLDER.fullmatch(user) or dom.upper() in ("NT AUTHORITY", "BUILTIN", "NT"):
            return m.group(0)
        d = self._token("DOMAIN", dom) if self.on("domain") else dom
        return f"{d}\\{self._token('USER', user)}"

    def decode(self, text: str) -> str:
        if not text or not self.map:
            return text
        reverse = dict(self.rev)
        for real, token in self.map.items():
            if real.endswith(".*"):
                reverse[token] = real[:-2]       # NET1 -> 10.0.0
            else:
                reverse.setdefault(token, real)
        pattern = re.compile("|".join(re.escape(t) for t in sorted(reverse, key=len, reverse=True)))
        return pattern.sub(lambda m: reverse[m.group(0)], text)

    # ------------------------------------------------------------ Strukturen
    def encode_value(self, value: Any, key: str = "") -> Any:
        """Funktionsergebnisse: Schlüssel wie host/server/user markieren Werte, die kein Muster haben."""
        if not self.enabled:
            return value
        if isinstance(value, dict):
            return {k: self.encode_value(v, str(k)) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.encode_value(v, key) for v in value]
        if isinstance(value, str):
            k = key.lower()
            plain = value.strip()
            if plain and not PLACEHOLDER.search(plain) and not any(s in k for s in PSEUDO_SKIP_KEYS):
                if self.on("host") and any(h in k for h in HOST_KEYS) and _looks_like_name(plain):
                    if "." in plain:
                        return self._fqdn(plain)
                    return self._token("HOST", plain)
                if self.on("user") and any(u in k for u in USER_KEYS) and _looks_like_name(plain) \
                        and "\\" not in plain and "@" not in plain:
                    return self._token("USER", plain)
            return self.encode(value)
        return value


def _is_mask(text: str) -> bool:
    try:
        bits = "".join(f"{int(p):08b}" for p in text.split("."))
    except ValueError:
        return False
    return "01" not in bits and bits.startswith("1")


def _looks_like_name(text: str) -> bool:
    return 1 < len(text) <= 255 and " " not in text and not text.isdigit()
