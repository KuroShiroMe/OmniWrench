"""Update-Prüfung für das Hauptprogramm über GitHub Releases.

Erwartet im konfigurierten Repository ("owner/repo") Releases mit Tag "vX.Y.Z"
und einem ZIP-Asset, dessen Name mit "AdminTools" beginnt. Das ZIP enthält den
kompletten Programmordner und wird nach dem Beenden über den bestehenden
Ordner entpackt (siehe apply_update).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from admintools import __version__

from . import net
from .paths import APP_DIR
from .versioning import is_newer

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200


@dataclass
class AppRelease:
    version: str
    name: str
    notes: str
    html_url: str
    asset_url: str


def check_for_update(repo: str, include_prereleases: bool = False) -> AppRelease | None:
    if not repo or "/" not in repo:
        return None
    api = f"https://api.github.com/repos/{repo.strip()}/releases"
    releases = json.loads(net.get_bytes(api, accept="application/vnd.github+json"))
    for rel in releases:
        if rel.get("draft") or (rel.get("prerelease") and not include_prereleases):
            continue
        version = rel.get("tag_name", "").lstrip("vV")
        if not is_newer(version, __version__):
            return None  # Releases sind neueste zuerst sortiert
        asset = next(
            (a for a in rel.get("assets", [])
             if a["name"].lower().endswith(".zip") and a["name"].lower().startswith("admintools")),
            None,
        )
        return AppRelease(
            version=version,
            name=rel.get("name") or rel.get("tag_name", ""),
            notes=rel.get("body") or "",
            html_url=rel.get("html_url", ""),
            asset_url=asset["browser_download_url"] if asset else "",
        )
    return None


def download_update(release: AppRelease) -> Path:
    target = Path(tempfile.mkdtemp(prefix="admintools_update_")) / "update.zip"
    return net.download(release.asset_url, target)


def apply_update(zip_path: Path) -> None:
    """Startet ein Hilfsskript, das nach Programmende das ZIP entpackt und neu startet.

    Das Hauptprogramm muss sich direkt danach beenden.
    """
    if getattr(sys, "frozen", False):
        restart = f"Start-Process -FilePath '{sys.executable}'"
    else:
        restart = (f"Start-Process -FilePath '{sys.executable}' -ArgumentList '\"{APP_DIR / 'main.py'}\"' "
                   f"-WorkingDirectory '{APP_DIR}'")
    script = zip_path.parent / "apply_update.ps1"
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Milliseconds 500\n"
        f"$tmp = Join-Path '{zip_path.parent}' 'extract'\n"
        f"Expand-Archive -Path '{zip_path}' -DestinationPath $tmp -Force\n"
        "$root = $tmp; $items = @(Get-ChildItem $tmp)\n"
        "if ($items.Count -eq 1 -and $items[0].PSIsContainer) { $root = $items[0].FullName }\n"
        f"Copy-Item -Path (Join-Path $root '*') -Destination '{APP_DIR}' -Recurse -Force\n"
        f"{restart}\n",
        encoding="utf-8-sig",
    )
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", str(script)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
