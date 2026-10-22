"""Baut OmniWrench als Programmordner für Windows bzw. Linux (PyInstaller, Ordner-Variante):

    .\\.venv\\Scripts\\python -m pip install pyinstaller
    .\\.venv\\Scripts\\python scripts\\build_exe.py            # dist\\OmniWrench\\OmniWrench.exe
    .\\.venv\\Scripts\\python scripts\\build_exe.py --zip      # zusätzlich dist\\OmniWrench-<version>-win64.zip
    python scripts/build_exe.py --zip                       # Linux: dist/OmniWrench-<version>-linux-x86_64.tar.gz
    .\\.venv\\Scripts\\python scripts\\build_exe.py --sign --zip   # EXE vor dem Packen signieren (sign_exe.py)

Ergebnis ist ein Programmordner (keine Einzel-EXE): startet schneller, wird nicht so
oft von Virenscannern beanstandet und lässt sich vom Selbst-Updater überschreiben.

Tools werden zur Laufzeit aus %LOCALAPPDATA% geladen und importieren Module, die das
Hauptprogramm selbst nicht nutzt. Deshalb kommen das komplette Paket omniwrench, die
gesamte Standardbibliothek, die von Tools genutzten Qt-Module und pip mit in die EXE.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench import APP_NAME, VENDOR, __version__  # noqa: E402

BUILD = ROOT / "build" / "exe"
DIST = ROOT / "dist"
SEP = os.pathsep  # Trenner für --add-data (Windows ";", sonst ":")

# Qt-Module, die Tools (auch künftige aus dem Store) nutzen dürfen, ohne dass das
# Hauptprogramm sie selbst importiert
QT_MODULES = ["QtCore", "QtGui", "QtWidgets", "QtSvg", "QtSvgWidgets", "QtNetwork", "QtPrintSupport",
              "QtConcurrent", "QtXml"]

# Teile der Standardbibliothek, die ein Admin-Tool nie braucht
STDLIB_EXCLUDE = {"tkinter", "turtle", "turtledemo", "idlelib", "test", "lib2to3", "ensurepip", "venv",
                  "pydoc_data", "distutils", "antigravity", "this", "__hello__", "__phello__"}


def stdlib_modules() -> list[str]:
    """Alle auf dieser Plattform vorhandenen Module der Standardbibliothek (ohne STDLIB_EXCLUDE)."""
    names = []
    for name in sorted(sys.stdlib_module_names):
        if name in STDLIB_EXCLUDE:
            continue
        try:
            if importlib.util.find_spec(name) is None:
                continue
        except (ImportError, ValueError):
            continue
        names.append(name)
    return names


def make_icon() -> Path | None:
    """Rendert resources/app.svg in eine mehrstufige .ico (nur für das EXE-Symbol)."""
    import struct

    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    _app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - muss leben, solange gerendert wird
    renderer = QSvgRenderer(str(ROOT / "omniwrench" / "resources" / "app.svg"))
    if not renderer.isValid():
        return None
    # Qt schreibt ICO nur mit einer Größe -> mehrere PNGs selbst zu einer ICO zusammensetzen
    images = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        img = QImage(QSize(size, size), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()
        data = QByteArray()
        buf = QBuffer(data)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        images.append((size, bytes(data)))
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, png in images:
        s = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", s, s, 0, 0, 1, 32, len(png), offset + len(blobs))
        blobs += png
    ico = BUILD / "OmniWrench.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    ico.write_bytes(header + entries + blobs)
    return ico


def make_version_file() -> Path:
    """Windows-Versionsinfo (Eigenschaften › Details der EXE)."""
    parts = [int(p) if p.isdigit() else 0 for p in __version__.split("-")[0].split(".")][:4]
    parts += [0] * (4 - len(parts))
    v = tuple(parts)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', '{VENDOR}'),
      StringStruct('FileDescription', '{APP_NAME}'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', '{APP_NAME}'),
      StringStruct('OriginalFilename', '{APP_NAME}.exe'),
      StringStruct('ProductName', '{APP_NAME}'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def pyinstaller_args(console: bool) -> list[str]:
    args = [
        str(ROOT / "main.py"),
        "--name", APP_NAME,
        "--noconfirm", "--clean",
        "--onedir",
        "--console" if console else "--windowed",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
        "--paths", str(ROOT),
        # Programmdaten (Pfade wie im Quellordner, paths.py/i18n.py finden sie über __file__)
        "--add-data", f"{ROOT / 'omniwrench' / 'resources'}{SEP}omniwrench/resources",
        "--add-data", f"{ROOT / 'omniwrench' / 'locales'}{SEP}omniwrench/locales",
        # Komplettes Paket: Tools importieren auch Module, die main.py nicht lädt
        "--collect-submodules", "omniwrench",
        # pip für Tool-Abhängigkeiten (OmniWrench.exe --pip …, siehe main.py)
        "--collect-submodules", "pip",
        "--collect-data", "pip",
        "--collect-submodules", "cryptography",
        "--hidden-import", "truststore",
        "--hidden-import", "PySide6QtAds",
        "--exclude-module", "tkinter",
    ]
    for mod in QT_MODULES:
        args += ["--hidden-import", f"PySide6.{mod}"]
    for mod in stdlib_modules():
        args += ["--hidden-import", mod]
    if sys.platform == "win32":
        args += ["--version-file", str(make_version_file())]
    ico = make_icon()
    if ico:
        args += ["--icon", str(ico)]
    return args


def copy_extras(app_dir: Path) -> None:
    """Dateien neben der EXE, die das Programm über APP_DIR öffnet."""
    docs = app_dir / "docs"
    docs.mkdir(exist_ok=True)
    shutil.copy2(ROOT / "docs" / "TOOL_ENTWICKLUNG.md", docs / "TOOL_ENTWICKLUNG.md")
    shutil.copy2(ROOT / "README.md", app_dir / "README.md")
    shutil.copy2(ROOT / "LICENSE", app_dir / "LICENSE")


def build_linkagent(app_dir: Path) -> None:
    """Baut das NetProbe-Leitungstest-Mini-Tool als Einzeldatei und legt es neben die EXE.

    So kann der Mini-Tool-Export (tools/netprobe) eine fertige linkagent.exe ausliefern, die auf der
    Gegenstelle ohne Python-Installation startet. Eigener Prozess, damit sich die beiden PyInstaller-Läufe
    (OmniWrench onedir + linkagent onefile) nicht in die Quere kommen.
    """
    import subprocess

    name = "linkagent.exe" if sys.platform == "win32" else "linkagent"
    out = DIST / name
    subprocess.run([sys.executable, str(ROOT / "scripts" / "build_linkagent.py")], check=True)
    if not out.is_file():
        sys.exit(f"linkagent-Build fehlgeschlagen: {out} nicht gefunden")
    shutil.copy2(out, app_dir / name)
    print(f"Mini-Tool beigelegt: {app_dir / name}")


def make_zip(app_dir: Path) -> Path:
    """Portable Version: Windows ZIP (…-win64.zip), Linux tar.gz (…-linux-x86_64.tar.gz, behält die
    Ausführungsrechte). Dateinamen müssen zu app_updater.asset_suffix passen."""
    if sys.platform == "win32":
        out = DIST / f"{APP_NAME}-{__version__}-win64.zip"
        out.unlink(missing_ok=True)
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file in sorted(app_dir.rglob("*")):
                if file.is_file():
                    zf.write(file, Path(APP_NAME) / file.relative_to(app_dir))
        return out
    import platform
    import tarfile

    out = DIST / f"{APP_NAME}-{__version__}-linux-{platform.machine().lower() or 'x86_64'}.tar.gz"
    out.unlink(missing_ok=True)
    with tarfile.open(out, "w:gz", compresslevel=6) as tf:
        tf.add(app_dir, arcname=APP_NAME, filter=_anonymous)
    return out


def _anonymous(info):
    """Archiv ohne Benutzer/Gruppe des Build-Rechners."""
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    return info


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--zip", action="store_true", help="Programmordner zusätzlich als portable Version packen (Windows ZIP, Linux tar.gz)")
    parser.add_argument("--console", action="store_true", help="mit Konsolenfenster bauen (Fehlersuche)")
    parser.add_argument("--sign", action="store_true",
                        help="EXE signieren, falls ein Zertifikat angegeben ist (scripts/sign_exe.py)")
    parser.add_argument("--no-build", action="store_true",
                        help="nicht neu bauen, nur vorhandenen Programmordner signieren/packen (CI)")
    opts = parser.parse_args()

    app_dir = DIST / APP_NAME
    exe = app_dir / (APP_NAME + (".exe" if sys.platform == "win32" else ""))
    if opts.no_build:
        if not exe.is_file():
            sys.exit(f"{exe.relative_to(ROOT)} fehlt - zuerst ohne --no-build bauen")
    else:
        try:
            import PyInstaller.__main__ as pyinstaller
        except ImportError:
            sys.exit("PyInstaller fehlt: python -m pip install pyinstaller")
        pyinstaller.run(pyinstaller_args(opts.console))
        copy_extras(app_dir)
        build_linkagent(app_dir)
    if opts.sign:
        import sign_exe

        agent = app_dir / ("linkagent.exe" if sys.platform == "win32" else "linkagent")
        sign_targets = [exe] + ([agent] if agent.is_file() else [])
        if sign_exe.configured():
            try:
                sign_exe.sign_files(sign_targets)
            except sign_exe.SignError as exc:
                sys.exit(str(exc))
            print("Signiert: " + ", ".join(str(f.relative_to(ROOT)) for f in sign_targets))
        else:
            print("Kein Zertifikat angegeben (SIGN_CERT_SHA1/SIGN_PFX_*), EXE bleibt unsigniert.")
    size = sum(f.stat().st_size for f in app_dir.rglob("*") if f.is_file()) // (1024 * 1024)
    print(f"\n{exe.relative_to(ROOT)} ({size} MB Programmordner)")
    if opts.zip:
        out = make_zip(app_dir)
        print(f"{out.relative_to(ROOT)} ({out.stat().st_size // (1024 * 1024)} MB)")


if __name__ == "__main__":
    main()
