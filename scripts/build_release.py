"""Erzeugt das Release-Paket des Hauptprogramms: dist/OmniWrench-<version>.zip

Das ZIP enthält den kompletten Programmordner aus dem letzten Commit (git archive)
und wird als Asset an ein GitHub-Release mit Tag v<version> gehängt:

    python scripts/build_release.py
    gh release create v<version> dist/OmniWrench-<version>.zip --title "OmniWrench <version>" --notes "…"
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from omniwrench import APP_NAME, __version__  # noqa: E402


def main() -> None:
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True).stdout
    if dirty.strip():
        print("Warnung: nicht committete Änderungen sind NICHT im Paket enthalten.")
    out = ROOT / "dist" / f"{APP_NAME}-{__version__}.zip"
    out.parent.mkdir(exist_ok=True)
    subprocess.run(["git", "archive", "--format=zip", f"--prefix={APP_NAME}/", "-o", str(out), "HEAD"],
                   cwd=ROOT, check=True)
    print(f"{out.relative_to(ROOT)} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
