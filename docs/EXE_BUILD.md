# OmniWrench als EXE bauen

OmniWrench wird mit [PyInstaller](https://pyinstaller.org) als **Programmordner** gebaut
(`dist\OmniWrench\OmniWrench.exe` + `_internal\`). Eine Einzel-EXE wird bewusst nicht erzeugt:
sie startet langsamer, wird häufiger von Virenscannern beanstandet und lässt sich vom
Selbst-Updater nicht ersetzen.

## Bauen

```powershell
.\.venv\Scripts\python -m pip install pyinstaller
.\.venv\Scripts\python scripts\build_exe.py           # dist\OmniWrench\OmniWrench.exe
.\.venv\Scripts\python scripts\build_exe.py --zip     # zusätzlich dist\OmniWrench-X.Y.Z-win64.zip
.\.venv\Scripts\python scripts\build_exe.py --console # mit Konsolenfenster (Fehlersuche)
.\.venv\Scripts\python scripts\build_exe.py --sign --zip # EXE vor dem Packen signieren
```

Signieren (Zertifikatsoptionen, lokal und in GitHub): siehe [EXE_SIGNIEREN.md](EXE_SIGNIEREN.md).

Der Ordner `dist\OmniWrench` kann so wie er ist kopiert oder verteilt werden (z. B. nach
`C:\Program Files\DarkMatter\OmniWrench`). Einstellungen, Tresor und installierte Tools liegen
weiterhin in `%APPDATA%` bzw. `%LOCALAPPDATA%\DarkMatter\OmniWrench` (oder `OMNIWRENCH_HOME`).

Ohne Windows-Rechner baut der GitHub-Workflow **EXE-Build** (`.github/workflows/build-exe.yml`)
die EXE: manuell über *Actions › EXE-Build › Run workflow*, automatisch bei jedem Tag `v*`.
Das ZIP liegt danach als Artefakt am Workflow-Lauf.

## Was in der EXE steckt

* Paket `omniwrench` vollständig, dazu `resources\` (App-Symbol, Lucide) und `locales\`.
* PySide6 (inkl. QtSvg, QtNetwork, QtPrintSupport, QtXml …), PySide6-QtAds, cryptography, truststore.
* Die komplette Python-Standardbibliothek (ohne tkinter, test, idlelib …): Tools werden erst zur
  Laufzeit geladen und dürfen jedes Standardmodul importieren.
* pip: Tool-Abhängigkeiten aus `tool.json → requirements.python` installiert die EXE über
  `OmniWrench.exe --pip install …` in den `_lib`-Ordner des Tools. Pakete ohne fertiges Wheel
  (nur Quellcode) lassen sich so nicht bauen.
* Neben der EXE: `docs\TOOL_ENTWICKLUNG.md` (Menü *Hilfe*) und `README.md`.
* Windows-Versionsinfo (Hersteller DarkMatter, Version aus `omniwrench/__init__.py`) und Programmsymbol
  aus `resources/app.svg`.

Der lokale Entwicklungs-Store (`store\`) wird nicht mitgeliefert; die EXE nutzt nur den offiziellen Store.

## Veröffentlichen

**Automatisch (empfohlen):** Version in `omniwrench/__init__.py` erhöhen, Release-Notizen in
`.github/release-notes/vX.Y.Z.md` ablegen (optional, sonst erzeugt GitHub sie), committen und den Tag pushen:

```powershell
git tag vX.Y.Z
git push origin vX.Y.Z
```

Der Workflow **EXE-Build** prüft, ob Tag und Programmversion zusammenpassen, baut beide Pakete und
legt das GitHub-Release mit Quellpaket und EXE-Paket an.

**Manuell:**

Version in `omniwrench/__init__.py` erhöhen, committen, dann beide Pakete bauen und **zuerst das
Quellpaket** hochladen (ältere Programmversionen nehmen das erste passende ZIP):

```powershell
.\.venv\Scripts\python scripts\build_release.py       # dist\OmniWrench-X.Y.Z.zip (Quellcode)
.\.venv\Scripts\python scripts\build_exe.py --zip     # dist\OmniWrench-X.Y.Z-win64.zip (EXE)
gh release create vX.Y.Z dist\OmniWrench-X.Y.Z.zip dist\OmniWrench-X.Y.Z-win64.zip --title "OmniWrench X.Y.Z" --notes "…"
```

Der Selbst-Updater wählt automatisch: die EXE lädt `…-win64.zip`, ein Start aus dem Quellcode `….zip`.

## NetProbe-Leitungstest-Mini-Tool (linkagent)

`scripts/build_exe.py` baut zusätzlich das eigenständige Leitungstest-Mini-Tool und legt
`linkagent.exe` in den Programmordner (neben `OmniWrench.exe`). Damit kann der Mini-Tool-Export in
NetProbe eine fertige `.exe` ausliefern, die auf der Gegenstelle **ohne Python** startet.

Einzeln bauen:

```powershell
.\.venv\Scripts\python scripts\build_linkagent.py     # dist\linkagent.exe (bzw. dist/linkagent unter Linux)
```

Quelle ist `tools/netprobe/linkagent.py` (nur Standardbibliothek, Server + Client + CLI). Beim
Tag-Release lädt der Workflow `linkagent.exe` auch als eigenständiges Asset hoch. Die Datei wird aktuell
nicht separat signiert.
