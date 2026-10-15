# Admin Tools

Modulare Toolsammlung für Administratoren. Tools werden wie aus einem App-Store aus GitHub-Repositories
installiert, einschließlich ihrer Voraussetzungen (RSAT, PowerShell-Module, winget-Pakete, Python-Pakete).

## Funktionen

* **Home-Tab** (immer geöffnet): installierte Tools als Kacheln, nach Kategorien gruppiert, mit Suche
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
  Die Sprachdateien liegen in `admintools/locales/` und in `<tool>/locales/`. Jedes Tool übernimmt automatisch die
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
admintools/
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
docs/TOOL_ENTWICKLUNG.md    Anleitung für neue Tools
```

## Datenablage

| Pfad | Inhalt |
|---|---|
| `%APPDATA%\AdminTools\` | `settings.json`, `vault.json` (verschlüsselt), `tool_settings\`, `layout.json` |
| `%LOCALAPPDATA%\AdminTools\` | `tools\` (installierte Tools), `tool_data\`, `logs\` |

Mit der Umgebungsvariable `ADMINTOOLS_HOME` liegt alles in einem Ordner (portabler Betrieb, Tests).

## GitHub einrichten

* **Tools:** `python scripts/build_store.py` ausführen und `store/` pushen. Die Repository-URL
  `https://raw.githubusercontent.com/<owner>/<repo>/main/store/index.json` unter *Extras › Einstellungen › Repositories* eintragen.
* **Hauptprogramm:** Release mit Tag `vX.Y.Z` und einem ZIP-Asset `AdminTools-X.Y.Z.zip` (kompletter Programmordner)
  anlegen. `owner/repo` unter *Einstellungen › Updates* eintragen. Die Version steht in `admintools/__init__.py`.
* Für private Repositories ein GitHub-Token hinterlegen. Es wird im Tresor gespeichert.
