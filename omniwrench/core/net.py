"""Minimaler HTTP-/Datei-Zugriff (https://, file:// und lokale Pfade)."""

from __future__ import annotations

import shutil
import ssl
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable

from omniwrench import APP_ID, __version__

USER_AGENT = f"{APP_ID}/{__version__}"


def _ssl_context() -> ssl.SSLContext:
    """Zertifikatsprüfung über den Windows-Zertifikatspeicher (wie Browser).

    Wichtig in Firmennetzen mit TLS-Inspection: Deren Stammzertifikate sind per GPO im
    Windows-Speicher hinterlegt, erfüllen aber oft nicht die strengere X.509-Prüfung,
    die Python ab 3.13 standardmäßig erzwingt.
    """
    try:
        import truststore
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        ctx = ssl.create_default_context()
        ctx.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)
        return ctx


_SSL = _ssl_context()

# Optional gesetzt vom Hauptprogramm (aus dem Tresor): GitHub-Token für private Repos / höheres Rate-Limit
github_token: str | None = None


def is_remote(url: str) -> bool:
    return urllib.parse.urlparse(url).scheme in ("http", "https")


def local_path(url: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        return Path(urllib.request.url2pathname(parsed.path))
    return Path(url)


def resolve(base: str, ref: str) -> str:
    """Löst einen (evtl. relativen) Verweis relativ zu einer Basis-URL/-Datei auf."""
    if is_remote(ref) or ref.startswith("file:") or Path(ref).is_absolute():
        return ref
    if is_remote(base):
        return urllib.parse.urljoin(base, ref)
    return str(local_path(base).parent / ref)


def _request(url: str, accept: str | None = None) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    if accept:
        headers["Accept"] = accept
    host = urllib.parse.urlparse(url).hostname or ""
    if github_token and (host.endswith("github.com") or host.endswith("githubusercontent.com")):
        headers["Authorization"] = f"Bearer {github_token}"
    return urllib.request.Request(url, headers=headers)


def get_bytes(url: str, accept: str | None = None, timeout: float = 30) -> bytes:
    if not is_remote(url):
        return local_path(url).read_bytes()
    with urllib.request.urlopen(_request(url, accept), timeout=timeout, context=_SSL) as resp:
        return resp.read()


def download(url: str, target: Path, progress: Callable[[int, int], None] | None = None,
             accept: str | None = None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if not is_remote(url):
        shutil.copyfile(local_path(url), target)
        return target
    with urllib.request.urlopen(_request(url, accept), timeout=60, context=_SSL) as resp, open(target, "wb") as f:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while chunk := resp.read(256 * 1024):
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    return target
