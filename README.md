# OmniWrench

*Das Universalwerkzeug für Administratoren, von **DarkMatter**.*

Modulare Toolsammlung für Administratoren. Tools werden wie aus einem App-Store aus GitHub-Repositories
installiert, einschließlich ihrer Voraussetzungen (RSAT, PowerShell-Module, winget-Pakete, Python-Pakete).
Läuft unter Windows 10/11 (Clients) und Linux (Debian/Ubuntu und andere Distributionen mit glibc 2.35 oder neuer).

## Installation

Alle Dateien gibt es unter [Releases](https://github.com/KuroShiroMe/OmniWrench/releases/latest).
Python muss nicht installiert sein, alles Nötige ist enthalten.

| System | Installationsprogramm (empfohlen) | Portable Version (ohne Installation) |
|---|---|---|
| Windows 10/11 (64 Bit) | `OmniWrench-X.Y.Z-win64-setup.exe` | `OmniWrench-X.Y.Z-win64.zip` |
| Linux (x86_64) | `omniwrench_X.Y.Z_amd64.deb` (Debian, Ubuntu, Mint …) | `OmniWrench-X.Y.Z-linux-x86_64.tar.gz` |

### Windows
* **Installationsprogramm:** `OmniWrench-X.Y.Z-win64-setup.exe` ausführen und die Abfrage der Benutzerkontensteuerung
  bestätigen. OmniWrench wird nach `C:\Program Files\DarkMatter\OmniWrench` installiert, mit Eintrag im Startmenü,
  optionaler Desktop-Verknüpfung und Deinstallation über *Einstellungen › Apps*.
  Stille Installation für Softwareverteilung (Intune, SCCM …):
  `OmniWrench-X.Y.Z-win64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART` (Desktop-Verknüpfung zusätzlich mit
  `/TASKS="desktopicon"`), stille Deinstallation:
  `"C:\Program Files\DarkMatter\OmniWrench\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART`.
* **Portable Version:** ZIP entpacken (z. B. nach `C:\Tools`) und `OmniWrench\OmniWrench.exe` starten.
* Die Programmdateien sind noch nicht signiert. Windows SmartScreen kann deshalb beim ersten Start warnen
  („Weitere Informationen › Trotzdem ausführen“).

### Linux
* **Installationspaket:** `sudo apt install ./omniwrench_X.Y.Z_amd64.deb` installiert OmniWrench nach `/opt/omniwrench`
  mit allen benötigten Systembibliotheken, dem Befehl `omniwrench` und einem Eintrag im Anwendungsmenü.
  Entfernen: `sudo apt remove omniwrench`.
* **Portable Version:** `tar -xzf OmniWrench-X.Y.Z-linux-x86_64.tar.gz` und `OmniWrench/OmniWrench` starten.
  Benötigt die Qt-Systembibliotheken (Debian/Ubuntu: `sudo apt install libegl1 libxkbcommon-x11-0 libxcb-cursor0`).
* Unter Linux laufen nur Tools, die Linux unterstützen (Subnetzrechner, IconForge, NetProbe, OmniVault);
  der Store kennzeichnet die übrigen mit „Läuft nur unter Windows“. Die Anmeldung per Zertifikat/Smartcard
  gibt es nur unter Windows, unter Linux dient das Masterpasswort.

### Updates
OmniWrench meldet neue Versionen beim Start bzw. unter *Extras › Nach Updates suchen* und lädt automatisch das
passende Paket: Eine installierte Version aktualisiert sich über das Installationsprogramm (Windows mit
UAC-Abfrage, Linux mit Passwortabfrage über `pkexec`), die portable Version ersetzt ihre Dateien selbst.
Einstellungen, Tresor und installierte Tools bleiben bei Updates und bei der Deinstallation erhalten.

## Funktionen

* **Home-Tab** (immer geöffnet): installierte Tools als Kacheln (Symbol + Name), nach Kategorien gruppiert,
  mit Suche und Kategorie-Filter. Ein Klick zeigt eine Detail-Leiste, ein Doppelklick öffnet das Tool.
  Ein Doppelklick auf eine Kategorie in der Seitenleiste setzt den Filter.
* **Symbol-Bibliothek**: rund 2.100 Symbole von [Lucide](https://lucide.dev) (ISC-Lizenz) für Tool-Kacheln,
  alternativ eigene Bilddatei oder Kürzel
* **Passwortmanager**: Zugangsdaten verschlüsselt im Tresor; überall, wo Tools Anmeldedaten brauchen,
  per Schlüssel-Button übernehmbar. Mehrere Zugangsdaten je Feld (Auswahlliste); gespeichert werden nur Verweise,
  Passwörter werden erst beim Gebrauch abgerufen und nur für die Sitzung im Speicher gehalten.

## Mitgelieferte Tools (Store)

| Tool | Zweck |
|---|---|
| Subnetzrechner | IPv4/IPv6 berechnen, Subnetze aufteilen, CSV-Export |
| AD Benutzerabfrage | AD-Benutzer suchen (RSAT), mit Zugangsdaten-Auswahl |
| OmniVault | Eingebauter Passwortmanager + Konnektoren: Microsoft SecretManagement, KeePass (.kdbx), Netwrix Password Secure (SDK `PsrApi.dll` nötig), Bitwarden/Vaultwarden (Bitwarden-CLI), 1Password (1Password-CLI), HashiCorp Vault/OpenBao (KV) – die letzten vier als Alpha |
| IconForge | Über 100.000 Symbole aus 26 freien Bibliotheken (Lucide eingebaut, weitere werden bei Bedarf geladen), Lizenz-Checkliste je Symbol, Export als SVG/PNG/ICO/PDF/JPG oder direkt in Visio einfügen |
* **Store-Tab**: Tools aus einem oder mehreren Repositories, Kategoriebaum, Installieren und Aktualisieren
* **Tool-Tabs**: Jedes Tool öffnet sich in einem eigenen Tab. Tabs lassen sich per Drag & Drop nebeneinander
  oder übereinander anordnen und als eigenes Fenster ausklinken (Qt Advanced Docking System).
  Das Layout wird beim Beenden gespeichert.
* **Seitenleiste** mit allen installierten Tools im Kategoriebaum (`Strg+B` blendet sie ein und aus)
* **Kontextmenü** (Rechtsklick auf Kachel oder Eintrag in der Seitenleiste): Öffnen, Einstellungen, Aktualisieren,
  Voraussetzungen prüfen, Reparieren, Deinstallieren
* **Tool-Einstellungen** werden aus der `config.json` des Tools automatisch als Dialog erzeugt
  (Pfade, Zugangsdaten, Zertifikate …)
* **Tresor**: Masterpasswort (Argon2id + AES-256-GCM) und/oder Benutzerzertifikat bzw. Smartcard (RSA-OAEP).
  Alle Passwörter der Tools werden darin verschlüsselt gespeichert. Sperren mit `Strg+L`, optional automatisch.
* **Updates**: Das Hauptprogramm prüft GitHub Releases, die Tools werden per Versionsvergleich mit dem Store-Katalog
  aktualisiert.
* **Mehrsprachig**: Deutsch, Englisch, Französisch, Spanisch, Italienisch, Niederländisch, Polnisch, Portugiesisch (Brasilien),
  Tschechisch, Schwedisch, Türkisch, Ukrainisch sowie die Dialekte Badisch, Bayrisch, Hessisch, Kölsch, Plattdeutsch,
  Sächsisch, Schwäbisch, Schwiizerdütsch, Wienerisch, Scots und Posh English.
  Die Sprachdateien liegen in `omniwrench/locales/` und in `<tool>/locales/`. Jedes Tool übernimmt automatisch die
  Programmsprache, falls es sie mitbringt, sonst Englisch. In den Tool-Einstellungen lässt sich die Sprache pro Tool
  festlegen. Eine neue Sprache ergänzt man, indem man `en.json` kopiert, übersetzt und `_meta` anpasst;
  `python scripts/check_locales.py` zeigt fehlende Texte.

## Start (Entwicklung)

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python main.py
```

Beim ersten Start wird der Tresor eingerichtet. Danach lassen sich im Store die beiden Beispiel-Tools aus dem
lokalen Entwicklungs-Store (`store/`) installieren.

## Projektstruktur

```
main.py                     Startpunkt
omniwrench/
  sdk.py                    Öffentliche API für Tools (ToolBase, ToolContext, InstallContext)
  core/                     Logik ohne Oberfläche
    vault.py                Verschlüsselter Tresor (Passwort-/Zertifikat-Anmeldung)
    certificates.py         Windows-Zertifikatspeicher, Smartcard
    tool_manager.py         Tools laden, installieren, deinstallieren
    prerequisites.py        RSAT, Features, PS-Module, winget, pip
    repository.py           Store-Katalog (index.json)
    app_updater.py          Update des Hauptprogramms über GitHub Releases
    manifest.py             Paketformat (tool.json / config.json)
    i18n.py                 Mehrsprachigkeit (Sprachdateien, Fallback-Ketten)
  locales/                  Sprachdateien des Hauptprogramms (<code>.json)
  ui/                       PySide6-Oberfläche
tools/                      Quellcode der Tools (je ein Ordner)
store/                      Generierter Store (index.json + ZIP-Pakete)
scripts/build_store.py      Baut store/ aus tools/
scripts/check_locales.py    Prüft Sprachdateien auf fehlende Texte
scripts/update_icons.py     Aktualisiert die Symbol-Bibliothek (Lucide)
docs/TOOL_ENTWICKLUNG.md    Anleitung für neue Tools
```

## Datenablage

Programmdateien und Benutzerdaten sind getrennt. Der Programmordner wird nur bei Installation und Update
geändert; alle Daten liegen pro Benutzer im Benutzerverzeichnis:

| System | Pfad | Inhalt |
|---|---|---|
| Windows | `%APPDATA%\DarkMatter\OmniWrench\` | `settings.json`, `vault.json` (verschlüsselt), `tool_settings\`, `layout.json` |
| Windows | `%LOCALAPPDATA%\DarkMatter\OmniWrench\` | `tools\` (installierte Tools), `tool_data\`, `logs\` |
| Linux | `~/.config/DarkMatter/OmniWrench/` | Einstellungen, Tresor, Tool-Einstellungen, Layout |
| Linux | `~/.local/share/DarkMatter/OmniWrench/` | installierte Tools, Tool-Daten, Logs |

Unter Linux gelten `XDG_CONFIG_HOME`/`XDG_DATA_HOME`. Daten aus älteren Versionen (unter Linux bisher
`~/AppData/…`) werden beim ersten Start automatisch übernommen; unter Windows bleiben die Orte unverändert.

Alles in einem Ordner statt im Benutzerverzeichnis:
* **Portable Version mit Daten** (z. B. USB-Stick): neben dem Programm einen Ordner `portable-data` anlegen.
* **Umgebungsvariable** `OMNIWRENCH_HOME` (Tests, Sonderfälle).

## Veröffentlichen

Repository: [github.com/KuroShiroMe/OmniWrench](https://github.com/KuroShiroMe/OmniWrench). Das Programm ist
standardmäßig darauf eingestellt (`GITHUB_REPO` in `omniwrench/__init__.py`).

* **Tools aktualisieren:** `version` in der `tool.json` erhöhen, `python scripts/build_store.py` ausführen,
  `store/` committen und pushen. Der offizielle Store
  (`https://raw.githubusercontent.com/KuroShiroMe/OmniWrench/main/store/index.json`) zeigt das Update sofort an.
* **Hauptprogramm veröffentlichen:** Version in `omniwrench/__init__.py` erhöhen, optional Release-Notizen in
  `.github/release-notes/vX.Y.Z.md` ablegen, committen und den Tag pushen:

  ```powershell
  git tag vX.Y.Z
  git push origin vX.Y.Z
  ```

  Der Workflow **Build** (`.github/workflows/build.yml`) baut und testet alle Pakete (Windows-Installationsprogramm
  und ZIP, Linux-Paket und tar.gz, Quellcode) und legt das GitHub-Release an. Installierte Programme finden es über
  *Extras › Nach Updates suchen* bzw. beim Start.
* **Pakete lokal bauen:** `python scripts/build_exe.py --zip` (Programmordner + portable Version), danach
  `python scripts/build_installer.py` (Windows: Inno Setup 6 nötig, Linux: `dpkg-deb`). Anleitung:
  [docs/EXE_BUILD.md](docs/EXE_BUILD.md).
* **Private Repositories** brauchen ein GitHub-Token (*Einstellungen › Updates*). Es wird im Tresor gespeichert.

## Lizenz

OmniWrench steht unter der [MIT-Lizenz](LICENSE). Mitgelieferte Bibliotheken behalten ihre eigenen Lizenzen
(u. a. Lucide: ISC, PySide6/Qt: LGPL).

## Signierung

Die Programmdateien werden derzeit **nicht signiert**. Ein Antrag bei der SignPath Foundation wurde abgelehnt;
die Vorbereitung für eine spätere Signierung (eigenes Zertifikat, Azure, SignPath) liegt in
[docs/EXE_SIGNIEREN.md](docs/EXE_SIGNIEREN.md). Alle Pakete werden automatisch aus diesem Repository mit
GitHub Actions gebaut.

## Datenschutz

This program will not transfer any information to other networked systems unless
specifically requested by the user or the person installing or operating it. Abgerufen werden nur der
Tool-Store und die Release-Liste von GitHub (`raw.githubusercontent.com`, `api.github.com`); die Prüfung beim
Start lässt sich unter *Einstellungen › Updates* abschalten. Tool-Pakete werden nur auf Anforderung
heruntergeladen oder, wenn dort ausdrücklich eingeschaltet, beim Start automatisch aktualisiert (Standard: aus). Verbindungen zu Active Directory,
Passwort-Managern oder anderen Systemen stellen nur die Tools her, die der Benutzer installiert und
einrichtet.
