# OmniWrench

*Das Universalwerkzeug für Administratoren, von **DarkMatter**.*

Modulare Toolsammlung für Administratoren. Tools werden wie aus einem App-Store aus GitHub-Repositories
installiert, einschließlich ihrer Voraussetzungen (RSAT, PowerShell-Module, winget-Pakete, Python-Pakete).

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
* **Mehrsprachig**: Deutsch, Englisch, Französisch, Spanisch sowie Badisch, Bayrisch, Scots und Posh English.
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

| Pfad | Inhalt |
|---|---|
| `%APPDATA%\DarkMatter\OmniWrench\` | `settings.json`, `vault.json` (verschlüsselt), `tool_settings\`, `layout.json` |
| `%LOCALAPPDATA%\DarkMatter\OmniWrench\` | `tools\` (installierte Tools), `tool_data\`, `logs\` |

Mit der Umgebungsvariable `OMNIWRENCH_HOME` liegt alles in einem Ordner (portabler Betrieb, Tests).

## Veröffentlichen

Repository: [github.com/Steffi-Tech/OmniWrench](https://github.com/Steffi-Tech/OmniWrench). Das Programm ist
standardmäßig darauf eingestellt (`GITHUB_REPO` in `omniwrench/__init__.py`).

* **Tools aktualisieren:** `version` in der `tool.json` erhöhen, `python scripts/build_store.py` ausführen,
  `store/` committen und pushen. Der offizielle Store
  (`https://raw.githubusercontent.com/Steffi-Tech/OmniWrench/main/store/index.json`) zeigt das Update sofort an.
* **Hauptprogramm veröffentlichen:** Version in `omniwrench/__init__.py` erhöhen, committen, dann:

  ```powershell
  python scripts/build_release.py          # erzeugt dist\OmniWrench-X.Y.Z.zip aus dem letzten Commit
  gh release create vX.Y.Z dist\OmniWrench-X.Y.Z.zip --title "OmniWrench X.Y.Z" --notes "…"
  ```

  Installierte Programme finden das Release über *Extras › Nach Updates suchen* bzw. beim Start.
* **EXE bauen:** `python scripts/build_exe.py --zip` erzeugt `dist\OmniWrench\OmniWrench.exe` und
  `dist\OmniWrench-X.Y.Z-win64.zip` (Anleitung: [docs/EXE_BUILD.md](docs/EXE_BUILD.md)).
* **Private Repositories** brauchen ein GitHub-Token (*Einstellungen › Updates*). Es wird im Tresor gespeichert.

## Lizenz

OmniWrench steht unter der [MIT-Lizenz](LICENSE). Mitgelieferte Bibliotheken behalten ihre eigenen Lizenzen
(u. a. Lucide: ISC, PySide6/Qt: LGPL).

## Code signing policy

Die Windows-Programmdateien (`OmniWrench.exe` im Paket `OmniWrench-X.Y.Z-win64.zip`) werden automatisch aus
diesem Repository mit GitHub Actions gebaut und signiert.

Free code signing provided by [SignPath.io](https://about.signpath.io), certificate by
[SignPath Foundation](https://signpath.org).

| Rolle | Mitglieder |
|---|---|
| Autoren (Committer) und Prüfer (Reviewer) | [Steffi-Tech](https://github.com/Steffi-Tech) |
| Freigabe jeder Signierung (Approver) | [Steffi-Tech](https://github.com/Steffi-Tech) |

### Datenschutz

This program will not transfer any information to other networked systems unless
specifically requested by the user or the person installing or operating it. Abgerufen werden nur der
Tool-Store und die Release-Liste von GitHub (`raw.githubusercontent.com`, `api.github.com`); die Prüfung beim
Start lässt sich unter *Einstellungen › Updates* abschalten. Verbindungen zu Active Directory,
Passwort-Managern oder anderen Systemen stellen nur die Tools her, die der Benutzer installiert und
einrichtet.
