"""Update-Prüfung für das Hauptprogramm über GitHub Releases.

Erwartet im konfigurierten Repository ("owner/repo") Releases mit Tag "vX.Y.Z". Welche Datei
geladen wird, hängt von der Installationsart ab (paths.INSTALL_KIND):

    setup     OmniWrench-X.Y.Z-win64-setup.exe     Windows-Installationsprogramm (scripts/build_installer.py)
    deb       omniwrench_X.Y.Z_amd64.deb            Linux-Paket (scripts/build_installer.py)
    portable  OmniWrench-X.Y.Z-win64.zip            portable Version Windows (scripts/build_exe.py --zip)
              OmniWrench-X.Y.Z-linux-x86_64.tar.gz  portable Version Linux
    source    OmniWrench-X.Y.Z.zip                  Quellcode (scripts/build_release.py)

Installierte Versionen liegen im Programmordner, den nur Administratoren ändern dürfen. Sie werden
deshalb über das jeweilige Installationsprogramm aktualisiert (Windows: UAC-Abfrage, Linux: pkexec).
Portable Versionen und der Quellcode werden nach dem Beenden über den bestehenden Ordner entpackt;
ist der Ordner schreibgeschützt (z. B. von Hand nach C:\\Program Files kopiert), läuft nur dieser
Kopierschritt mit Administratorrechten (siehe apply_update).
"""

from __future__ import annotations

import base64
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from omniwrench import __version__

from . import elevation, net
from .i18n import tr
from .paths import APP_DIR, INSTALL_KIND, app_dir_writable
from .versioning import is_newer

DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000


class UpdateError(Exception):
    """Update kann nicht automatisch eingespielt werden (Meldung ist übersetzt)."""


@dataclass
class AppRelease:
    version: str
    name: str
    notes: str
    html_url: str
    asset_url: str
    asset_name: str = ""


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
        asset = _pick_asset(rel.get("assets", []))
        return AppRelease(
            version=version,
            name=rel.get("name") or rel.get("tag_name", ""),
            notes=rel.get("body") or "",
            html_url=rel.get("html_url", ""),
            asset_url=asset["browser_download_url"] if asset else "",
            asset_name=asset["name"] if asset else "",
        )
    return None


def _linux_arch() -> tuple[str, str]:
    """(Debian-Architektur, Kernel-Architektur), z. B. ("amd64", "x86_64")."""
    machine = platform.machine().lower() or "x86_64"
    deb = {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}.get(machine, machine)
    return deb, machine


def asset_suffix(kind: str = INSTALL_KIND) -> str:
    """Namensende des passenden Release-Pakets für diese Installation."""
    if kind == "source":
        return ".zip"
    if sys.platform == "win32":
        return "-win64-setup.exe" if kind == "setup" else "-win64.zip"
    deb, machine = _linux_arch()
    return f"_{deb}.deb" if kind == "deb" else f"-linux-{machine}.tar.gz"


def _pick_asset(assets: list[dict], kind: str = INSTALL_KIND) -> dict | None:
    suffix = asset_suffix(kind)
    for a in assets:
        name = a["name"].lower()
        if not name.startswith("omniwrench") or not name.endswith(suffix):
            continue
        if kind == "source" and name.endswith("-win64.zip"):
            continue  # Quellpaket ist das ZIP ohne Plattform-Endung
        return a
    return None


def download_update(release: AppRelease) -> Path:
    name = release.asset_name or Path(release.asset_url).name or "update.zip"
    target = Path(tempfile.mkdtemp(prefix="omniwrench_update_")) / name
    return net.download(release.asset_url, target)


def apply_update(package: Path) -> None:
    """Startet das Einspielen des Updates. Das Hauptprogramm muss sich direkt danach beenden.

    Löst elevation.ElevationCancelled aus, wenn die UAC-Abfrage abgelehnt wurde, und UpdateError,
    wenn das Update nicht automatisch eingespielt werden kann.
    """
    name = package.name.lower()
    if name.endswith(".exe"):
        _run_windows_setup(package)
    elif name.endswith(".deb"):
        _run_deb_install(package)
    elif sys.platform == "win32":
        _replace_files_windows(package)
    else:
        _replace_files_posix(package)


# ------------------------------------------------------------------ installierte Versionen
def _run_windows_setup(setup: Path) -> None:
    """Installationsprogramm still starten (eigene UAC-Abfrage). Es wartet, bis OmniWrench beendet ist,
    und startet es danach wieder als angemeldeter Benutzer (Parameter /restart=1, siehe OmniWrench.iss)."""
    params = "/SILENT /SUPPRESSMSGBOXES /NORESTART /SP- /restart=1"
    if elevation.is_admin():
        subprocess.Popen([str(setup), *params.split()], close_fds=True)
    else:
        elevation.start_elevated(str(setup), params, hidden=False)


def _run_deb_install(deb: Path) -> None:
    """Linux-Paket nach Programmende mit pkexec (grafische Passwortabfrage) installieren und neu starten."""
    if not shutil.which("pkexec"):
        raise UpdateError(tr("updates.err_no_pkexec", file=str(deb)))
    tool = "apt-get install -y --allow-downgrades" if shutil.which("apt-get") else "dpkg -i"
    script = deb.parent / "apply_update.sh"
    script.write_text(
        "#!/bin/sh\n"
        f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done\n"
        f"pkexec {tool} {shlex.quote(str(deb))} > {shlex.quote(str(deb.parent / 'install.log'))} 2>&1\n"
        f"exec {_restart_command_posix()}\n",
        encoding="utf-8",
    )
    _start_detached_posix(script)


# ------------------------------------------------------------------ portable Version / Quellcode
def _restart_command_posix() -> str:
    if getattr(sys, "frozen", False):
        return shlex.quote(sys.executable)
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(APP_DIR / 'main.py'))}"


def _start_detached_posix(script: Path) -> None:
    script.chmod(0o755)
    subprocess.Popen(["/bin/sh", str(script)], start_new_session=True, close_fds=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _replace_files_posix(package: Path) -> None:
    if not app_dir_writable():
        raise UpdateError(tr("updates.err_readonly", path=str(APP_DIR)))
    work = package.parent / "extract"
    if package.name.lower().endswith(".zip"):
        # zipfile statt unzip (nicht überall installiert); der Interpreter ist beim Quellcode-Start vorhanden
        extract = (f"{shlex.quote(sys.executable)} -c \"import sys, zipfile; "
                   f"zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])\" "
                   f"{shlex.quote(str(package))} {shlex.quote(str(work))}")
    else:
        extract = f"tar -xzf {shlex.quote(str(package))} -C {shlex.quote(str(work))}"
    script = package.parent / "apply_update.sh"
    script.write_text(
        "#!/bin/sh\n"
        "set -e\n"
        f"while kill -0 {os.getpid()} 2>/dev/null; do sleep 0.5; done\n"
        f"mkdir -p {shlex.quote(str(work))}\n"
        f"{extract}\n"
        f"root={shlex.quote(str(work))}\n"
        'set -- "$root"/*\n'
        'if [ "$#" -eq 1 ] && [ -d "$1" ]; then root="$1"; fi\n'
        f'cp -a "$root"/. {shlex.quote(str(APP_DIR))}/\n'
        f"exec {_restart_command_posix()}\n",
        encoding="utf-8",
    )
    _start_detached_posix(script)


def _ps_quote(value) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def _encoded(script: str) -> str:
    return base64.b64encode(script.encode("utf-16-le")).decode("ascii")


def _start_hidden_ps(script: str) -> None:
    # -EncodedCommand statt -File: unterliegt nicht der Ausführungsrichtlinie (AllSigned per GPO)
    subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden",
         "-EncodedCommand", _encoded(script)],
        creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW,
        close_fds=True,
    )


def _replace_files_windows(package: Path) -> None:
    """Paket nach Programmende über APP_DIR entpacken und neu starten.

    Darf der Benutzer den Programmordner nicht ändern, kopiert ein erhöhter Hilfsprozess (UAC) die
    Dateien; neu gestartet wird trotzdem ohne Adminrechte durch einen zweiten, normalen Hilfsprozess,
    der auf die Fertig-Datei des erhöhten Prozesses wartet.
    """
    if getattr(sys, "frozen", False):
        restart = f"Start-Process -FilePath {_ps_quote(sys.executable)}"
    else:
        restart = (f"Start-Process -FilePath {_ps_quote(sys.executable)} "
                   f"-ArgumentList {_ps_quote(chr(34) + str(APP_DIR / 'main.py') + chr(34))} "
                   f"-WorkingDirectory {_ps_quote(APP_DIR)}")
    work = package.parent
    done = work / "update.done"
    copy = (
        "$ErrorActionPreference = 'Stop'\n"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        "Start-Sleep -Milliseconds 500\n"
        "try {\n"
        f"  $tmp = Join-Path {_ps_quote(work)} 'extract'\n"
        f"  Expand-Archive -Path {_ps_quote(package)} -DestinationPath $tmp -Force\n"
        "  $root = $tmp; $items = @(Get-ChildItem $tmp)\n"
        "  if ($items.Count -eq 1 -and $items[0].PSIsContainer) { $root = $items[0].FullName }\n"
        f"  Copy-Item -Path (Join-Path $root '*') -Destination {_ps_quote(APP_DIR)} -Recurse -Force\n"
        f"  Set-Content -Path {_ps_quote(done)} -Value 'ok'\n"
        "} catch {\n"
        f"  Set-Content -Path {_ps_quote(done)} -Value $_.Exception.Message\n"
        "}\n"
    )
    restarter = (
        f"$deadline = (Get-Date).AddMinutes(15)\n"
        f"while (-not (Test-Path {_ps_quote(done)}) -and (Get-Date) -lt $deadline) {{ Start-Sleep -Milliseconds 500 }}\n"
        f"Wait-Process -Id {os.getpid()} -ErrorAction SilentlyContinue\n"
        f"{restart}\n"
    )
    if app_dir_writable():
        _start_hidden_ps(copy + restarter)
        return
    elevation.start_elevated("powershell.exe",
                             f"-NoProfile -NonInteractive -WindowStyle Hidden -EncodedCommand {_encoded(copy)}")
    _start_hidden_ps(restarter)
