"""Baut das NetProbe-Leitungstest-Mini-Tool als eigenständige Datei (PyInstaller, Einzeldatei).

    python -m pip install pyinstaller
    python scripts\\build_linkagent.py          # dist\\linkagent.exe (Windows) bzw. dist/linkagent (Linux)

Das Ergebnis ist eine einzelne ausführbare Datei ohne Python-Installation: auf der Gegenstelle einfach
starten (`linkagent.exe` doppelklicken oder `linkagent.exe serve --port … --token …`). Quelle ist
tools/netprobe/linkagent.py (nur Standardbibliothek). build_exe.py legt die gebaute Datei zusätzlich neben
OmniWrench.exe, damit der Mini-Tool-Export sie direkt ausliefern kann.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "tools" / "netprobe" / "linkagent.py"
BUILD = ROOT / "build" / "linkagent"
DIST = ROOT / "dist"
NAME = "linkagent"

# Das Mini-Tool nutzt nur die Standardbibliothek; GUI-/Build-Module gehören nicht hinein.
EXCLUDES = ["tkinter", "PySide6", "PySide6QtAds", "pip", "setuptools", "numpy", "test", "unittest",
            "pydoc", "doctest", "lib2to3", "distutils", "xml", "email", "http.server"]


def version_file() -> Path | None:
    """Windows-Versionsinfo (Eigenschaften › Details), damit die EXE nicht völlig anonym ist."""
    if sys.platform != "win32":
        return None
    sys.path.insert(0, str(ROOT))
    from omniwrench import VENDOR, __version__

    parts = [int(p) if p.isdigit() else 0 for p in __version__.split("-")[0].split(".")][:4]
    parts += [0] * (4 - len(parts))
    v = tuple(parts)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1,
                    subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040704b0', [
      StringStruct('CompanyName', '{VENDOR}'),
      StringStruct('FileDescription', 'NetProbe Leitungstest (Gegenstelle)'),
      StringStruct('FileVersion', '{__version__}'),
      StringStruct('InternalName', 'linkagent'),
      StringStruct('OriginalFilename', 'linkagent.exe'),
      StringStruct('ProductName', 'OmniWrench NetProbe linkagent'),
      StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [0x0407, 1200])])
  ]
)
"""
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def build() -> Path:
    try:
        import PyInstaller.__main__ as pyinstaller
    except ImportError:
        sys.exit("PyInstaller fehlt: python -m pip install pyinstaller")
    args = [
        str(SRC),
        "--name", NAME,
        "--onefile", "--console",
        "--noconfirm", "--clean",
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "work"),
        "--specpath", str(BUILD),
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    vf = version_file()
    if vf:
        args += ["--version-file", str(vf)]
    pyinstaller.run(args)
    out = DIST / (NAME + (".exe" if sys.platform == "win32" else ""))
    return out


def main() -> None:
    out = build()
    if not out.is_file():
        sys.exit(f"Build fehlgeschlagen: {out} nicht gefunden")
    print(f"\n{out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
