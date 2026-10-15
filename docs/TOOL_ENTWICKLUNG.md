# Tool-Entwicklung

Ein Tool ist ein Ordner mit festem Aufbau. Fertige Beispiele:
[tools/subnet_calculator](../tools/subnet_calculator) (ohne Voraussetzungen) und
[tools/ad_user_lookup](../tools/ad_user_lookup) (mit RSAT-Voraussetzung und Anmeldedaten).

```
mein_tool/
├── tool.json      Metadaten (Pflicht)
├── config.json    Einstellungen: Schema und Standardwerte (Pflicht, darf leer sein: {"settings": []})
├── install.py     Installationsroutine (Pflicht, Funktionen optional)
├── tool.py        Einstiegsmodul mit der Tool-Klasse (Name frei wählbar, siehe "entry")
├── locales/       Sprachdateien (empfohlen, mindestens en.json)
│   ├── en.json
│   └── de.json
├── icon.png       optional
└── ...            beliebige weitere Module/Dateien
```

Texte in `tool.json` und `config.json` schreibst du am besten auf Englisch. Sie sind die letzte Rückfallstufe,
falls eine Übersetzung fehlt.

## tool.json – Metadaten

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `id` | ✔ | Eindeutige ID, `a-z0-9._-`, z. B. `net.subnet-calculator` |
| `name` | ✔ | Anzeigename |
| `version` | ✔ | `MAJOR.MINOR.PATCH`, steuert die Update-Erkennung |
| `description` | | Kurzbeschreibung (Kachel) |
| `long_description` | | Ausführliche Beschreibung (Store, Tooltip) |
| `author` | | |
| `category` | | Kategoriepfad mit `/`, z. B. `MS Server Tools/Active Directory` |
| `icon` | | Symbol, siehe [Symbole](#symbole) |
| `icon_text` | | Eigenes Kürzel für das erzeugte Symbol (max. 4 Zeichen), z. B. `"EXO"` |
| `color` | | Hintergrundfarbe des erzeugten Symbols, z. B. `#0ea5e9` |
| `entry` | | `"<modul>:<Klasse>"`, Standard `tool:Tool` |
| `min_app_version` | | Mindestversion des Hauptprogramms |
| `platforms` | | Standard `["windows"]` |
| `tags` | | Suchbegriffe |
| `single_instance` | | `true` = nur ein Tab gleichzeitig |
| `requirements` | | Voraussetzungen, siehe unten |

### Symbole

Das Symbol der Kachel wird in dieser Reihenfolge bestimmt:

1. **Eigene Bilddatei:** `"icon": "icon.png"` (png/svg/ico, quadratisch, mind. 128 px, im Tool-Ordner).
   `build_store.py` bettet sie in den Store-Katalog ein, damit sie auch im Store erscheint.
2. **Symbol aus der Bibliothek:** `"icon": "server"`. Eingebaut sind rund 2.100 Symbole von
   [Lucide](https://lucide.dev/icons) (ISC-Lizenz, frei auch für kommerzielle Nutzung).
   Übersicht im Programm unter *Extras › Symbol-Bibliothek*; ein Klick kopiert den Namen.
   Das Symbol wird weiß auf der Farbe `color` dargestellt.
3. **Eigenes Kürzel:** `"icon_text": "EXO"` erzeugt ein Symbol mit diesem Text.
4. **Nichts angegeben:** Anfangsbuchstaben des Namens (z. B. „DNS Cleanup“ → „DC“).

```json
"icon": "network",
"color": "#0ea5e9"
```

Lange Namen passt die Kachel automatisch an: Erst wird die Schrift etwas verkleinert, dann an Leerzeichen
oder nach Bindestrichen in zwei Zeilen umgebrochen.

### requirements

Die Voraussetzungen installiert das Hauptprogramm **vor** `install()`. Hat die `install.py` eine Funktion `check()`,
wird sie vorher aufgerufen: Liefert sie eine leere Liste, gelten Windows-Funktionen, PowerShell-Module und
winget-Pakete als vorhanden und werden übersprungen. Es erscheint dann keine UAC-Abfrage. Python-Pakete werden
immer installiert.

```json
"requirements": {
  "python": ["ldap3>=2.9"],
  "windows_capabilities": ["Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0"],
  "windows_features": ["RSAT-DNS-Server"],
  "powershell_modules": ["ExchangeOnlineManagement"],
  "winget": ["WiresharkFoundation.Wireshark"]
}
```

* `python`: wird per pip in `<tool>/_lib` installiert und beim Laden in `sys.path` eingetragen
* `windows_capabilities` / `windows_features`: werden gemeinsam in **einer** Administrator-Sitzung installiert (eine UAC-Abfrage).
  Unter Windows Server läuft das über `Install-WindowsFeature`, auf Clients über `Enable-WindowsOptionalFeature`.
* `powershell_modules`: `Install-Module -Scope CurrentUser`
* `winget`: `winget install --id … -e --silent`

Häufige RSAT-Namen (`Get-WindowsCapability -Online -Name Rsat*`):
`Rsat.ActiveDirectory.DS-LDS.Tools`, `Rsat.Dns.Tools`, `Rsat.DHCP.Tools`, `Rsat.GroupPolicy.Management.Tools`,
`Rsat.ServerManager.Tools`, `Rsat.CertificateServices.Tools` (jeweils mit Suffix `~~~~0.0.1.0`).

## config.json – Einstellungen

Aus dem Schema erzeugt das Hauptprogramm automatisch den Einstellungsdialog
(Rechtsklick auf das Tool › *Einstellungen …*).

```json
{
  "settings": [
    {"key": "server", "type": "string", "label": "Server", "default": "", "group": "Verbindung"},
    {"key": "login", "type": "credential", "label": "Anmeldedaten", "group": "Verbindung"},
    {"key": "client_cert", "type": "certificate", "label": "Client-Zertifikat"},
    {"key": "config_dir", "type": "path_dir", "label": "Konfigurationsordner"}
  ]
}
```

| Typ | Wert | Gespeichert |
|---|---|---|
| `string`, `text` | str | JSON |
| `int`, `float` | Zahl (`min`, `max`) | JSON |
| `bool` | bool | JSON |
| `choice` | ein Wert aus `options` (`["a","b"]` oder `[{"value":…, "label":…}]`) | JSON |
| `path_file`, `path_dir` | Pfad (mit Durchsuchen-Button) | JSON |
| `certificate` | Fingerabdruck aus `Cert:\CurrentUser\My` | JSON |
| `secret` | str (Passwort, Token, API-Key) | **Tresor, verschlüsselt** |
| `credential` | `{"username": …, "password": …}`, mit Button „Aus Passwortmanager“ | **Tresor, verschlüsselt** |

Weitere Felder: `label`, `description`, `group` (eigener Tab im Dialog), `placeholder`, `required`.

## install.py – Installationsroutine

Alle Funktionen sind optional. `ctx` ist ein `InstallContext`.

```python
def check(ctx):            # -> Liste fehlender Voraussetzungen ([] = OK)
    ...
def install(ctx):          # Erstinstallation / "Reparieren"
    ctx.report("Lege Standardkonfiguration an …")
def update(ctx, old_version):   # statt install() bei Updates
    ...
def uninstall(ctx):        # vor dem Löschen des Tool-Ordners
    ...
```

`InstallContext` bietet: `report(msg)`, `tr(key, …)`, `pip_install(*pakete)`, `run_powershell(script)`,
`run_powershell_elevated(script)`, `settings`, `secrets`, `tool_dir`, `data_dir`, `log`.

## Die Tool-Klasse

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from omniwrench.sdk import ToolBase, run_async


class Tool(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        w = QWidget(parent)
        lay = QVBoxLayout(w)
        server = self.context.settings.get("server")
        self.label = QLabel(f"Server: {server}")
        lay.addWidget(self.label)
        return w

    def on_settings_changed(self, changed_keys):
        if "server" in changed_keys:
            self.label.setText(f"Server: {self.context.settings.get('server')}")

    def can_close(self):       # False = Tab bleibt offen
        return True

    def shutdown(self):        # Threads beenden, Verbindungen schließen
        pass
```

Pro geöffnetem Tab gibt es eine eigene Instanz. `self.context` (`ToolContext`) bietet:

| | |
|---|---|
| `settings.get(key)` / `settings.set(key, value)` | Einstellungen laut config.json (Secrets automatisch aus dem Tresor) |
| `get_credential(key)` | `(benutzer, passwort)` einer `credential`-Einstellung |
| `secrets.get/set/delete(key)` | freier, verschlüsselter Speicher des Tools |
| `tr(key, default=None, **platzhalter)` / `language` | Übersetzung aus `locales/` bzw. aktive Sprache |
| `data_dir` | eigener Datenordner (`%LOCALAPPDATA%\DarkMatter\OmniWrench\tool_data\<id>`) |
| `tool_dir` | Installationsordner (für mitgelieferte Dateien) |
| `run_powershell(script, stdin=…)` / `run_powershell_json(…)` | PowerShell ausführen (UTF-8, ohne Fenster) |
| `run_powershell_elevated(script)` | mit Adminrechten (UAC) |
| `notify(msg)` | Meldung in der Statusleiste |
| `open_settings()` | Einstellungsdialog des Tools öffnen |
| `log` | Logger (`%LOCALAPPDATA%\DarkMatter\OmniWrench\logs`) |

### Zugangsdaten und Passwortmanager

OmniWrench hat einen eingebauten Passwortmanager (*Extras › Passwortmanager*). Tools greifen so darauf zu:

* **Einstellung vom Typ `credential`:** Der Einstellungsdialog zeigt automatisch Benutzer, Passwort und einen
  Schlüssel-Button. Wird ein Eintrag übernommen, bleibt er **verknüpft**: Ändert sich das Passwort im Manager,
  liefert `self.context.get_credential("key")` automatisch das neue.
* **Eigene Anmeldemaske im Tool:** fertiges Feld mit Schlüssel-Button.

  ```python
  from omniwrench.sdk import CredentialField, pick_credential

  self.login = CredentialField()                 # Benutzer + Passwort + 🔑
  layout.addWidget(self.login)
  user = self.login.value()["username"]

  creds = pick_credential(parent_widget)         # nur der Auswahldialog -> (user, pw) oder None
  ```

Lang laufende Aufgaben (AD-Abfragen, Netzwerk-Scans) gehören mit `run_async(fn, on_done, on_error)` in einen
Hintergrund-Thread. Die Callbacks laufen wieder im GUI-Thread.

**Sicherheit:** Passwörter nie in die Kommandozeile oder ins Skript einbauen. Übergib sie über `stdin`, wie es
[ad_user_lookup/tool.py](../tools/ad_user_lookup/tool.py) vormacht.

## Mehrsprachigkeit

Jedes Tool bringt seine Sprachdateien in `locales/<code>.json` mit: flache JSON-Dateien mit Schlüssel → Text.
Platzhalter stehen in `{geschweiften Klammern}`.

```json
{
  "_meta": {"name": "German", "native": "Deutsch"},

  "tool.name": "Subnetzrechner",
  "tool.description": "IPv4/IPv6-Netze berechnen …",
  "tool.long_description": "…",
  "tool.category": "Netzwerk/IP-Tools",

  "settings.export_dir.label": "Export-Ordner",
  "settings.export_dir.description": "Standardordner für den CSV-Export.",
  "settings.csv_separator.option.;": "Semikolon",
  "settings.group.Export": "Export",

  "ui.exported": "{count} Subnetze exportiert nach {path}"
}
```

| Schlüssel | Wirkung |
|---|---|
| `tool.name`, `tool.description`, `tool.long_description`, `tool.category` | Anzeige in Home, Seitenleiste und Store (`scripts/build_store.py` übernimmt sie in die index.json) |
| `settings.<key>.label` / `.description` / `.placeholder` | Texte im Einstellungsdialog (Ersatz für die Texte aus config.json) |
| `settings.<key>.option.<wert>` | Anzeigetext einer `choice`-Option |
| `settings.group.<gruppe>` | Tab-Titel einer Einstellungsgruppe |
| alles andere | frei, im Code über `self.context.tr("schlüssel", name=…)` |

**Welche Sprache ein Tool verwendet:**

1. Im Einstellungsdialog des Tools gibt es oben das Feld **Sprache**: entweder *Automatisch* oder eine der Sprachen,
   die das Tool mitbringt. Damit lässt sich ein Tool z. B. auf Englisch stellen, wenn seine deutsche Übersetzung
   noch lückenhaft ist.
2. *Automatisch* übernimmt die Sprache des Hauptprogramms, wenn das Tool eine Datei dafür hat. Bei Dialekten wird
   zuerst die Basissprache probiert (Badisch → Deutsch). Gibt es keine passende Datei, wird **Englisch** verwendet.
3. Fehlt ein einzelner Schlüssel, greift die Fallback-Kette, z. B. `de_bad.json` → `de.json` → `en.json` → der
   Standardtext im Code (`tr("key", "Default")`) bzw. der Text aus config.json.

Nach einem Sprachwechsel baut das Hauptprogramm offene Tabs des Tools automatisch mit einer neuen Instanz neu auf.
Mit `self.context.language` fragst du die aktive Sprache ab, z. B. für Zahlenformate.

Verfügbare Sprachcodes des Hauptprogramms: `en`, `de`, `fr`, `es`, `de_bad` (Badisch), `de_by` (Bayrisch),
`en_sco` (Scots), `en_posh` (Posh English).

Prüfen, welche Übersetzungen noch fehlen:

```powershell
python scripts/check_locales.py tools/mein_tool
```

## Testen und Veröffentlichen

1. **Lokal testen:** *Datei › Tool aus Ordner installieren …* und den Tool-Ordner wählen.
   Nach Änderungen dasselbe erneut ausführen: Das Tool wird ersetzt, die Einstellungen bleiben erhalten.
2. **Store bauen:** `python scripts/build_store.py` packt alle Ordner unter `tools/` nach
   `store/packages/*.zip` und schreibt `store/index.json` mit SHA-256-Prüfsummen.
3. **Veröffentlichen:** `store/` ins GitHub-Repository pushen. Im Programm unter *Extras › Einstellungen › Repositories*
   `https://raw.githubusercontent.com/<owner>/<repo>/main/store/index.json` eintragen.
4. **Update:** `version` in tool.json erhöhen, Store neu bauen und pushen. Installierte Clients zeigen dann
   „Update verfügbar“ an.
