# OmniWrench als Programm und Installationsprogramm bauen

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

Der Ordner `dist\OmniWrench` ist die **portable Version** (`--zip` packt ihn als
`OmniWrench-X.Y.Z-win64.zip`). Einstellungen, Tresor und installierte Tools liegen im Benutzerprofil
(`%APPDATA%` bzw. `%LOCALAPPDATA%\DarkMatter\OmniWrench`), außer neben der EXE liegt ein Ordner
`portable-data` oder `OMNIWRENCH_HOME` ist gesetzt.

Unter Linux baut dasselbe Skript `dist/OmniWrench/OmniWrench`; `--zip` erzeugt dort
`OmniWrench-X.Y.Z-linux-x86_64.tar.gz` (tar.gz, damit die Ausführungsrechte erhalten bleiben).
Zum Bauen und Starten braucht Linux die Qt-Systembibliotheken
(`libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0 …`, Liste in `scripts/build_installer.py`).

## Installationsprogramme

```powershell
.\.venv\Scripts\python scripts\build_exe.py --zip     # zuerst Programmordner + portable Version
.\.venv\Scripts\python scripts\build_installer.py     # dist\OmniWrench-X.Y.Z-win64-setup.exe
```

* **Windows: Inno Setup 6** (`installer/windows/OmniWrench.iss`, Installation: `winget install JRSoftware.InnoSetup`).
  Gewählt statt MSI/WiX oder MSIX: ein einzelnes Setup-Programm mit Assistent und Sprachauswahl, stille
  Installation für Softwareverteilung (`/VERYSILENT`), Updates über dieselbe `AppId`, frei und ohne
  Zertifikatszwang (MSIX ließe sich unsigniert gar nicht installieren). Installiert per UAC nach
  `C:\Program Files\DarkMatter\OmniWrench`, Startmenü, optionale Desktop-Verknüpfung, Deinstallation unter
  *Apps*. Ein laufendes OmniWrench erkennt das Setup am Mutex `DarkMatter.OmniWrench` (`APP_MUTEX`).
  Benutzerdaten bleiben bei der Deinstallation erhalten.
* **Linux: Debian-Paket** (`python scripts/build_installer.py` unter Linux -> `dist/omniwrench_X.Y.Z_amd64.deb`,
  braucht `dpkg-deb`). Programm nach `/opt/omniwrench`, Befehl `/usr/bin/omniwrench`, Startmenü-Eintrag
  (`installer/linux/omniwrench.desktop`) und Symbol; die Qt-Systembibliotheken stehen als Abhängigkeiten im
  Paket und installiert `apt`. Gebaut wird auf Ubuntu 22.04 (glibc 2.35), damit das Paket auch auf älteren
  Systemen läuft.

Beide legen `omniwrench-install.json` neben das Programm. Daran erkennt OmniWrench die Installationsart
(`paths.INSTALL_KIND`) und lädt beim Selbst-Update das Installationsprogramm statt der portablen Version:
Windows startet das Setup still mit UAC-Abfrage, Linux installiert das neue Paket über `pkexec`.

## Was in der EXE steckt

* Paket `omniwrench` vollständig, dazu `resources\` (App-Symbol, Lucide) und `locales\`.
* PySide6 (inkl. QtSvg, QtNetwork, QtPrintSupport, QtXml …), PySide6-QtAds, cryptography, truststore.
* Die komplette Python-Standardbibliothek (ohne tkinter, test, idlelib …): Tools werden erst zur
  Laufzeit geladen und dürfen jedes Standardmodul importieren.
* pip: Tool-Abhängigkeiten aus `tool.json → requirements.python` installiert die EXE über
  `OmniWrench.exe --pip install …` in den `_lib`-Ordner des Tools. Pakete ohne fertiges Wheel
  (nur Quellcode) lassen sich so nicht bauen.
* Neben der EXE: `README.md` und `LICENSE`. Hilfe und Entwicklerdoku öffnet das Menü *Hilfe* im GitHub-Wiki.
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

Der Workflow **Build** prüft, ob Tag und Programmversion zusammenpassen, baut alle Pakete und legt das
GitHub-Release an: Quellpaket, Windows-Setup und -ZIP, Linux-Paket und -tar.gz sowie `linkagent.exe`.

**Manuell:** Version erhöhen, committen, Pakete wie oben bauen (Windows und Linux) und **zuerst das
Quellpaket** hochladen (Programmversionen bis 0.5.x nehmen das erste passende ZIP):

```powershell
.\.venv\Scripts\python scripts\build_release.py       # dist\OmniWrench-X.Y.Z.zip (Quellcode)
gh release create vX.Y.Z dist\OmniWrench-X.Y.Z.zip --title "OmniWrench X.Y.Z" --notes "…"
gh release upload vX.Y.Z dist\OmniWrench-X.Y.Z-win64-setup.exe dist\OmniWrench-X.Y.Z-win64.zip <Linux-Pakete>
```

Der Selbst-Updater wählt die Datei nach Installationsart (`core/app_updater.py`, `asset_suffix`): Setup,
Debian-Paket, portable Version (`-win64.zip` / `-linux-x86_64.tar.gz`) oder Quellpaket. Die Dateinamen
deshalb nicht ändern.

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
