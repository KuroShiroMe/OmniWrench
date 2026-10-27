"""Screenshots der Tools für Store und Home rendern.

    python scripts/screenshots.py                     # alle Tools mit screenshots/render.py
    python scripts/screenshots.py tools/mein_tool     # nur dieses Tool
    python scripts/screenshots.py --lang de           # Oberflächensprache der Bilder (Standard: en)

Ruft scripts/render_screenshots.py aus dem OmniWrench-Quellcode auf (gesucht wie in store.py:
--omniwrench PFAD, OMNIWRENCH_SRC, ./.omniwrench, ../OmniWrench). Braucht PySide6 und PySide6-QtAds
(pip install -r <OmniWrench>/requirements.txt). Danach: python scripts/store.py build
Anleitung: https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung-Paketformat#screenshots
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from store import ROOT, TOOLS, find_omniwrench

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--omniwrench", help="Pfad zum OmniWrench-Quellcode")
    args, rest = ap.parse_known_args()
    script = find_omniwrench(args.omniwrench) / "scripts" / "render_screenshots.py"
    tools = [a for a in rest if not a.startswith("-")]
    if not tools:  # ohne Angabe: alle Tools dieses Repositorys mit render.py
        rest += [str(p) for p in sorted(TOOLS.glob("*/screenshots/render.py"))
                 if not p.parts[-3].startswith((".", "_"))]
        rest = [str(Path(a).parents[1]) if a.endswith("render.py") else a for a in rest]
    sys.exit(subprocess.call([sys.executable, str(script), *rest], cwd=ROOT))
