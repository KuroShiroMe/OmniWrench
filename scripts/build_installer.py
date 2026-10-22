"""Baut das Installationsprogramm aus dem fertigen Programmordner dist/OmniWrench (scripts/build_exe.py):

    python scripts/build_exe.py --zip           # Programmordner + portable Version
    python scripts/build_installer.py           # Windows: dist\\OmniWrench-X.Y.Z-win64-setup.exe (Inno Setup 6)
                                                # Linux:   dist/omniwrench_X.Y.Z_amd64.deb

Windows: braucht Inno Setup 6 (ISCC.exe im PATH, in der Umgebungsvariable ISCC oder im Standardordner;
         Installation z. B. "winget install JRSoftware.InnoSetup"). Skript: installer/windows/OmniWrench.iss.
Linux:   braucht dpkg-deb (Debian/Ubuntu). Programm nach /opt/omniwrench, Starter /usr/bin/omniwrench,
         Startmenü-Eintrag und Symbol; Abhängigkeiten (Qt-Systembibliotheken) installiert apt.

Beide Installationsprogramme legen omniwrench-install.json neben das Programm. Daran erkennt
OmniWrench, dass es installiert ist, und aktualisiert sich über das Installationsprogramm statt
die Dateien im (schreibgeschützten) Programmordner selbst zu ersetzen (core/app_updater.py).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench import APP_NAME, VENDOR, __version__  # noqa: E402

DIST = ROOT / "dist"
APP_DIR = DIST / APP_NAME
BUILD = ROOT / "build" / "installer"
MARKER = "omniwrench-install.json"

# Systembibliotheken für Qt (xcb), die PyInstaller nicht mitliefert. glibc: PySide6-Wheels brauchen 2.34,
# gebaut wird auf Ubuntu 22.04 (2.35) -> läuft auf Ubuntu 22.04+, Debian 12+, Linux Mint 21+.
DEB_DEPENDS = [
    "libc6 (>= 2.35)", "libegl1", "libgl1", "libfontconfig1", "libfreetype6", "libdbus-1-3",
    "libglib2.0-0t64 | libglib2.0-0", "libxkbcommon0", "libxkbcommon-x11-0", "libx11-xcb1",
    "libxcb-cursor0", "libxcb-icccm4", "libxcb-image0", "libxcb-keysyms1", "libxcb-randr0",
    "libxcb-render-util0", "libxcb-shape0", "libxcb-xinerama0", "libxcb-xkb1",
]
DEB_RECOMMENDS = ["iputils-ping", "fonts-dejavu-core"]


def numeric_version() -> str:
    parts = [p if p.isdigit() else "0" for p in __version__.split("-")[0].split("+")[0].split(".")][:4]
    return ".".join(parts + ["0"] * (4 - len(parts)))


def write_marker(directory: Path, kind: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / MARKER
    path.write_text(json.dumps({"kind": kind, "version": __version__}, indent=2) + "\n", encoding="utf-8")
    return path


# ------------------------------------------------------------------ Windows (Inno Setup)
def find_iscc() -> Path:
    candidates = [os.environ.get("ISCC", ""), shutil.which("iscc") or "", shutil.which("ISCC") or ""]
    for env in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        base = os.environ.get(env)
        if base:
            sub = "Programs/Inno Setup 6" if env == "LOCALAPPDATA" else "Inno Setup 6"
            candidates.append(str(Path(base) / sub / "ISCC.exe"))
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    sys.exit("Inno Setup 6 (ISCC.exe) nicht gefunden: winget install JRSoftware.InnoSetup "
             "oder Pfad in der Umgebungsvariable ISCC angeben")


def build_windows() -> Path:
    exe = APP_DIR / f"{APP_NAME}.exe"
    if not exe.is_file():
        sys.exit(f"{exe.relative_to(ROOT)} fehlt - zuerst scripts/build_exe.py ausführen")
    marker = write_marker(BUILD / "windows", "setup")
    args = [str(find_iscc()), "/Qp",
            f"/DAppVersion={__version__}", f"/DNumericVersion={numeric_version()}",
            f"/DSourceDir={APP_DIR}", f"/DOutputDir={DIST}", f"/DMarkerFile={marker}"]
    ico = ROOT / "build" / "exe" / "OmniWrench.ico"  # von build_exe.py erzeugt
    if ico.is_file():
        args.append(f"/DIconFile={ico}")
    args.append(str(ROOT / "installer" / "windows" / "OmniWrench.iss"))
    subprocess.run(args, check=True)
    out = DIST / f"{APP_NAME}-{__version__}-win64-setup.exe"
    if not out.is_file():
        sys.exit(f"{out.relative_to(ROOT)} wurde nicht erzeugt")
    return out


# ------------------------------------------------------------------ Linux (.deb)
def deb_arch() -> str:
    machine = platform.machine().lower()
    return {"x86_64": "amd64", "aarch64": "arm64", "armv7l": "armhf"}.get(machine, machine)


def render_png(size: int, target: Path) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - muss leben, solange gerendert wird
    renderer = QSvgRenderer(str(ROOT / "omniwrench" / "resources" / "app.svg"))
    img = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    painter = QPainter(img)
    renderer.render(painter)
    painter.end()
    target.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(target), "PNG")


def build_deb() -> Path:
    exe = APP_DIR / APP_NAME
    if not exe.is_file():
        sys.exit(f"{exe.relative_to(ROOT)} fehlt - zuerst scripts/build_exe.py ausführen")
    if not shutil.which("dpkg-deb"):
        sys.exit("dpkg-deb fehlt (Debian/Ubuntu: apt install dpkg)")
    pkg = "omniwrench"
    version = __version__.replace("-", "~")  # 1.0.0-beta1 -> 1.0.0~beta1 (vor 1.0.0 einsortiert)
    arch = deb_arch()
    root = BUILD / "deb" / "root"
    shutil.rmtree(root, ignore_errors=True)
    opt = root / "opt" / pkg
    shutil.copytree(APP_DIR, opt, symlinks=True)
    write_marker(opt, "deb")

    usr = root / "usr"
    (usr / "bin").mkdir(parents=True)
    (usr / "bin" / pkg).symlink_to(f"/opt/{pkg}/{APP_NAME}")
    apps = usr / "share" / "applications"
    apps.mkdir(parents=True)
    shutil.copy2(ROOT / "installer" / "linux" / "omniwrench.desktop", apps / "omniwrench.desktop")
    icons = usr / "share" / "icons" / "hicolor"
    (icons / "scalable" / "apps").mkdir(parents=True)
    shutil.copy2(ROOT / "omniwrench" / "resources" / "app.svg", icons / "scalable" / "apps" / "omniwrench.svg")
    for size in (48, 128, 256):
        render_png(size, icons / f"{size}x{size}" / "apps" / "omniwrench.png")
    doc = usr / "share" / "doc" / pkg
    doc.mkdir(parents=True)
    shutil.copy2(ROOT / "LICENSE", doc / "copyright")

    for path in root.rglob("*"):  # Rechte unabhängig von der umask des Build-Rechners
        if path.is_symlink():
            continue
        if path.is_dir() or os.access(path, os.X_OK):
            path.chmod(0o755)
        else:
            path.chmod(0o644)

    size_kb = sum(f.stat().st_size for f in root.rglob("*") if f.is_file() and not f.is_symlink()) // 1024
    control = root / "DEBIAN" / "control"
    control.parent.mkdir()
    control.write_text(
        f"Package: {pkg}\n"
        f"Version: {version}\n"
        f"Architecture: {arch}\n"
        f"Maintainer: {VENDOR} <https://github.com/KuroShiroMe/OmniWrench/issues>\n"
        f"Installed-Size: {size_kb}\n"
        f"Depends: {', '.join(DEB_DEPENDS)}\n"
        f"Recommends: {', '.join(DEB_RECOMMENDS)}\n"
        "Section: admin\n"
        "Priority: optional\n"
        "Homepage: https://github.com/KuroShiroMe/OmniWrench\n"
        f"Description: {APP_NAME} - modular toolbox for administrators\n"
        " Modular admin toolbox by KuroShiro. Tools are installed from a store\n"
        " (GitHub repository) and open in dockable tabs. Settings, the encrypted\n"
        " vault and installed tools are stored per user in ~/.config and\n"
        " ~/.local/share (KuroShiro/OmniWrench).\n",
        encoding="utf-8",
    )
    out = DIST / f"{pkg}_{version}_{arch}.deb"
    out.unlink(missing_ok=True)
    subprocess.run(["dpkg-deb", "--root-owner-group", "-Zxz", "--build", str(root), str(out)], check=True)
    return out


def main() -> None:
    out = build_windows() if sys.platform == "win32" else build_deb()
    print(f"\n{out.relative_to(ROOT)} ({out.stat().st_size // (1024 * 1024)} MB)")


if __name__ == "__main__":
    main()
