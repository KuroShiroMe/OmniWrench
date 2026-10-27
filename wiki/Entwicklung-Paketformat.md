# Paketformat

> **Kurz:** Ein Tool ist ein Ordner mit `tool.json` (Metadaten), `config.json` (Einstellungen), `install.py`
> (Installationsroutine), einem Einstiegsmodul (`tool.py`) und Sprachdateien in `locales/`.

**Gilt für:** OmniWrench ab Version 0.7.0 (Screenshots ab 0.8.0)

## Inhalt
- [Aufbau](#aufbau)
- [tool.json](#tooljson)
- [Plattformen](#plattformen)
- [Kategorien (Bereiche)](#kategorien-bereiche)
- [Tags](#tags)
- [Symbole](#symbole)
- [Screenshots](#screenshots)
- [Voraussetzungen (requirements)](#voraussetzungen-requirements)
- [config.json](#configjson)
- [install.py](#installpy)
- [Versionen](#versionen)

## Aufbau

```
mein_tool/
├── tool.json      Metadaten (Pflicht)
├── config.json    Einstellungen: Schema und Standardwerte (Pflicht, darf leer sein: {"settings": []})
├── install.py     Installationsroutine (Pflicht, alle Funktionen optional)
├── tool.py        Einstiegsmodul mit der Tool-Klasse (Name frei, siehe "entry")
├── locales/       Sprachdateien (mindestens en.json, empfohlen de.json)
│   ├── en.json
│   └── de.json
├── icon.png       optional
├── screenshots/   optional: Bilder für Store und Home (+ render.py, das sie erzeugt)
└── …              weitere Module, Daten, Skripte
```

Beim Packen ausgelassen werden `__pycache__`, `_lib` (dort landen die installierten Python-Pakete), `.git`,
`screenshots` (werden getrennt veröffentlicht, siehe [Screenshots](#screenshots)) sowie `*.pyc`/`*.pyo`. Ordner, deren Name mit `.` oder `_` beginnt, gelten nicht als Tool.

Texte in `tool.json` und `config.json` auf Englisch schreiben: Sie sind die letzte Rückfallstufe, wenn eine
Übersetzung fehlt. Die eigentlichen Anzeigetexte kommen aus den [Sprachdateien](Entwicklung-Mehrsprachigkeit).

## tool.json

```json
{
  "id": "contoso.dns-cleanup",
  "name": "DNS Cleanup",
  "version": "1.0.0",
  "description": "Find and remove stale DNS records.",
  "long_description": "Lists stale A and PTR records per zone ...",
  "author": "Contoso IT",
  "homepage": "https://github.com/contoso/omniwrench-tools/blob/main/docs/Tool-DNS-Cleanup.md",
  "category": "network",
  "tags": ["DNS", "Active Directory", "Cleanup", "RSAT"],
  "screenshots": [
    {"file": "screenshots/overview.png", "caption": "Stale records of all zones"},
    {"file": "screenshots/cleanup.png", "caption": "Preview before deleting"}
  ],
  "icon": "trash-2",
  "color": "#0ea5e9",
  "entry": "tool:DnsCleanup",
  "min_app_version": "0.7.0",
  "platforms": ["windows"],
  "single_instance": false,
  "requirements": {"windows_capabilities": ["Rsat.Dns.Tools~~~~0.0.1.0"]}
}
```

| Feld | Pflicht | Beschreibung |
|---|---|---|
| `id` | ✔ | eindeutige ID, nur `a-z0-9._-`; Muster `<herausgeber>.<tool>`, z. B. `contoso.dns-cleanup`. Nie mehr ändern: Einstellungen, Tresor-Einträge und Updates hängen daran. |
| `name` | ✔ | Anzeigename (englisch; übersetzt über `tool.name`) |
| `version` | ✔ | `MAJOR.MINOR.PATCH`; steuert die Update-Erkennung |
| `description` | | Kurzbeschreibung (Karte in Store und Home, Liste, Tooltip) |
| `long_description` | | ausführliche Beschreibung (Detailleiste) |
| `author` | | Autor oder Herausgeber |
| `homepage` | | Link zur Doku-Seite; erscheint als „Website“ in der Detailleiste |
| `category` | | Bereich als ID, siehe [Kategorien](#kategorien-bereiche) |
| `category_area` | | nur bei eigenem Bereich: Anzeigename (übersetzbar) |
| `tags` | | Schlagwörter, siehe [Tags](#tags) |
| `screenshots` | | Bilder für Store und Home, siehe [Screenshots](#screenshots) |
| `icon` | | Symbol, siehe [Symbole](#symbole) |
| `icon_text` | | eigenes Kürzel für das erzeugte Symbol (max. 4 Zeichen), z. B. `"EXO"` |
| `color` | | Hintergrundfarbe des Symbols, z. B. `#0ea5e9` |
| `entry` | | `"<modul>:<Klasse>"`, Standard `tool:Tool` |
| `min_app_version` | | Mindestversion von OmniWrench; ältere Versionen lehnen die Installation ab |
| `platforms` | | Standard `["windows"]`; siehe [Plattformen](#plattformen) |
| `single_instance` | | `true` = nur ein Tab gleichzeitig |
| `hooks` | | Einstiegspunkte ohne geöffneten Tab, z. B. `{"startup": "modul:funktion"}` ([SDK](Entwicklung-Tool-Klasse-und-SDK#hooks)) |
| `requirements` | | Voraussetzungen, siehe [unten](#voraussetzungen-requirements) |

Unbekannte Felder werden ignoriert. `icon_data`, `download_url`, `sha256`, `size` und `translations` erzeugt
der Store-Bau; nicht selbst eintragen.

## Plattformen

OmniWrench läuft unter Windows und Linux. Ein Tool läuft nur auf den Systemen in `platforms`: Der Store zeigt
andere mit „Läuft nur unter …“ ohne Installieren-Knopf.

`"linux"` nur eintragen, wenn das Tool dort wirklich funktioniert: keine PowerShell, kein
`ctypes.windll`/`winreg`, keine Windows-Voraussetzungen (`windows_capabilities`, `windows_features`,
`powershell_modules`, `winget`). Plattformabhängige Teile mit `sys.platform == "win32"` abfragen (Beispiel:
`icmp.py` von NetProbe). macOS ist nicht vorgesehen.

## Kategorien (Bereiche)

Es gibt eine Ebene: feste Service-Bereiche, die OmniWrench selbst übersetzt.

| ID | Anzeige (de) | Typische Inhalte |
|---|---|---|
| `workplace` | Arbeitsplatz & Endgeräte | Windows-Client, Softwareverteilung, Drucker, Mobilgeräte, Peripherie |
| `identity` | Identität & Zugriff | Active Directory, Entra ID, Gruppen & Berechtigungen, MFA |
| `network` | Netzwerk & Konnektivität | IP, DNS, DHCP, LAN/WLAN, VPN, Firewall, Diagnose |
| `infrastructure` | Server & Rechenzentrum | Virtualisierung, Speicher, Backup, Serverbetrieb |
| `cloud` | Cloud & Microsoft 365 | Exchange, Teams, SharePoint/OneDrive, Azure, Lizenzen |
| `security` | Informationssicherheit | Passwörter, Zertifikate/PKI, Verschlüsselung, Schwachstellen |
| `applications` | Anwendungen & Datenbanken | SQL Server, IIS, Fachanwendungen |
| `operations` | Betrieb & Überwachung | Ereignisprotokolle, Monitoring, Inventar, Leistung |
| `servicedesk` | Service Desk & Support | Fernwartung, Benutzerhilfe, Ticket-Hilfsmittel |
| `automation` | Automatisierung & Entwicklung | PowerShell, APIs, Konverter |
| `documentation` | Dokumentation & Design | Icons, Diagramme, Vorlagen |

- Ohne Angabe landet das Tool unter „Sonstiges“ (`other`).
- **Eigener Bereich:** eigene ID (z. B. `"category": "medical"`) und Anzeigename über `category_area` bzw. den
  Sprachschlüssel `tool.category_area`.
- Ein Tool steht in genau einem Bereich; Bezüge zu weiteren Bereichen über Tags.
- Ältere Angaben mit Unterkategorie (`network/diagnostics`) werden auf den Bereich gekürzt.

## Tags

Tags ordnen ein Tool feiner ein (Technologie, Protokoll, Produkt, Aufgabe). Sie stehen in der Detailleiste und
auf der Store-Karte; ein Klick sucht nach allen Tools mit diesem Tag.

- 4 bis 12 aussagekräftige Begriffe
- sprachneutral: Produkt- und Protokollnamen (`Active Directory`, `DNS`, `KeePass`), sonst Englisch
  (`Port Scan`, `User Accounts`), in der Schreibweise, wie sie angezeigt werden sollen
- keine Synonyme oder Übersetzungen; deutsche Suchbegriffe findet die Suche über die übersetzte Beschreibung
- Bezug zu einem weiteren Bereich als Tag, z. B. `Service Desk`

## Symbole

Das Symbol der Kachel wird in dieser Reihenfolge bestimmt:

1. **Eigene Bilddatei:** `"icon": "icon.png"` (png/svg/ico, quadratisch, mind. 128 px, im Tool-Ordner).
   Der Store-Bau bettet sie in den Katalog ein, damit sie auch im Store erscheint.
2. **Symbol aus der Bibliothek:** `"icon": "server"`. Eingebaut sind rund 2.100 Symbole von
   [Lucide](https://lucide.dev/icons) (ISC-Lizenz). Die Namen zeigt das Tool [IconForge](Tool-IconForge)
   (Bibliothek Lucide) oder *Extras › Symbol-Bibliothek* (Klick kopiert den Namen). Dargestellt weiß auf `color`.
3. **Eigenes Kürzel:** `"icon_text": "EXO"`.
4. **Nichts angegeben:** Anfangsbuchstaben des Namens („DNS Cleanup“ → „DC“).

## Screenshots

Store und Home zeigen auf jeder Tool-Karte einen Screenshot, durch den man blättern kann; die Detailleiste zeigt
alle Bilder mit Bildunterschrift.

- **Reihenfolge:** Der erste Eintrag ist der **Hauptscreenshot** (Hauptansicht des Tools), danach folgt je
  wichtiger Funktion ein weiteres Bild.
- **Format:** PNG, 1280 × 800 Pixel (16:10), dunkles Farbschema, englische Oberfläche, nur Beispieldaten
  (keine echten Server-, Benutzer- oder Firmennamen).
- **`caption`:** Bildunterschrift auf Englisch; übersetzt über den Sprachschlüssel `tool.screenshot.<Dateiname
  ohne .png>`, z. B. `"tool.screenshot.overview": "Veraltete Einträge aller Zonen"` in `locales/de.json`.
- Die Bilder gehören **nicht** ins Tool-Paket. Das Store-Skript legt sie getrennt ab (`store/screenshots/<id>/`)
  und trägt sie mit Adresse, Größe und SHA-256 in die `index.json` ein. Neue Bilder brauchen deshalb keine neue
  Tool-Version. OmniWrench lädt sie erst, wenn sie sichtbar werden, und legt sie bei der Installation mit ins
  Tool (für Home ohne Netz).

### Screenshots erzeugen

Die Bilder werden nicht von Hand aufgenommen, sondern gerendert: `screenshots/render.py` baut die Oberfläche mit
Beispieldaten auf und speichert jedes Bild.

```python
# screenshots/render.py
def render(shot):
    shot.module("backend").Backend = FakeBackend   # Netz/Server durch Beispieldaten ersetzen
    tool, widget = shot.create()                    # Tool-Instanz mit Oberfläche in 1280 × 800
    tool.search.setText("corp.example")
    tool.start()
    shot.wait_until(lambda: tool.done, 30, "Suche")
    shot.save("overview")                           # -> screenshots/overview.png
    tool.tabs.setCurrentIndex(1)
    shot.save("cleanup")
```

| `shot.` | Wirkung |
|---|---|
| `create(width, height)` | neue Tool-Instanz samt Oberfläche (Standard 1280 × 800) → `(tool, widget)` |
| `module("name")` | Modul aus dem eigenen Paket, z. B. um ein Backend zu ersetzen |
| `settings` | Einstellungen des Tools (vor `create()` setzen) |
| `wait(s)`, `wait_until(bedingung, timeout, text)` | Ereignisse verarbeiten, auf Hintergrundarbeit warten |
| `save("name")` | Oberfläche als `screenshots/name.png` speichern |
| `save_dialog("name", dialog)` | Dialog mittig über der abgedunkelten Oberfläche speichern |
| `source` | Tool-Ordner im Repository |

```
python scripts/render_screenshots.py tools/mein_tool        # ein Tool (ohne Angabe: alle)
python scripts/render_screenshots.py --lang de --theme light  # andere Sprache/Farbschema
```

Das Skript läuft ohne Bildschirm (Qt offscreen) in einem leeren Temp-Profil und meldet, wenn `tool.json` und die
gespeicherten Bilder nicht zusammenpassen. Windows-Tools lassen sich so auch unter Linux rendern, solange
`render.py` Netz- und Systemzugriffe durch Beispieldaten ersetzt.

## Voraussetzungen (requirements)

OmniWrench installiert die Voraussetzungen **vor** `install()`.

```json
"requirements": {
  "python": ["ldap3>=2.9"],
  "windows_capabilities": ["Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0"],
  "windows_features": ["RSAT-DNS-Server"],
  "powershell_modules": ["ExchangeOnlineManagement"],
  "winget": ["WiresharkFoundation.Wireshark"]
}
```

| Schlüssel | Installation |
|---|---|
| `python` | per pip in `<tool>/_lib`, beim Laden in `sys.path`. In der installierten Programmversion nur Pakete mit fertigem Wheel (kein Kompilieren). Standardbibliothek und die gängigen PySide6-Module sind eingebaut. Wird immer installiert. |
| `windows_capabilities` | `Add-WindowsCapability` (z. B. RSAT) |
| `windows_features` | auf Clients `Enable-WindowsOptionalFeature`, auf Servern `Install-WindowsFeature` |
| `powershell_modules` | `Install-Module -Scope CurrentUser` |
| `winget` | `winget install --id … -e --silent` |

Windows-Funktionen und -Features werden gemeinsam in **einer** Administrator-Sitzung installiert (eine
UAC-Abfrage), mit Fortschritt im Installationsfenster. Hat `install.py` eine Funktion `check()` und liefert
sie eine leere Liste, gelten Funktionen, Features, Module und winget-Pakete als vorhanden und werden
übersprungen (keine UAC-Abfrage).

Häufige RSAT-Namen (`Get-WindowsCapability -Online -Name Rsat*`), jeweils mit Suffix `~~~~0.0.1.0`:
`Rsat.ActiveDirectory.DS-LDS.Tools`, `Rsat.Dns.Tools`, `Rsat.DHCP.Tools`, `Rsat.GroupPolicy.Management.Tools`,
`Rsat.ServerManager.Tools`, `Rsat.CertificateServices.Tools`.

## config.json

Aus dem Schema erzeugt OmniWrench den Einstellungsdialog (Rechtsklick › *Einstellungen …*).

```json
{
  "settings": [
    {"key": "server", "type": "string", "label": "Server", "default": "", "group": "Connection",
     "placeholder": "dc01.contoso.local", "required": true},
    {"key": "login", "type": "credential", "label": "Credentials", "group": "Connection"},
    {"key": "client_cert", "type": "certificate", "label": "Client certificate"},
    {"key": "mode", "type": "choice", "label": "Mode", "default": "fast",
     "options": [{"value": "fast", "label": "Fast"}, {"value": "full", "label": "Full"}]},
    {"key": "timeout", "type": "int", "label": "Timeout (s)", "default": 30, "min": 1, "max": 600}
  ]
}
```

| Typ | Wert | Gespeichert |
|---|---|---|
| `string`, `text` | Text (einzeilig / mehrzeilig) | Einstellungsdatei |
| `int`, `float` | Zahl (`min`, `max`) | Einstellungsdatei |
| `bool` | Ja/Nein | Einstellungsdatei |
| `choice` | ein Wert aus `options` (`["a","b"]` oder `[{"value":…, "label":…}]`) | Einstellungsdatei |
| `path_file`, `path_dir` | Pfad mit Durchsuchen-Knopf | Einstellungsdatei |
| `certificate` | Fingerabdruck aus dem persönlichen Zertifikatspeicher | Einstellungsdatei |
| `secret` | Passwort, Token, API-Schlüssel | **Tresor, verschlüsselt** |
| `credential` | Zugangsdaten mit Auswahl aus dem Passwortmanager, mehrere Einträge möglich | **Tresor, verschlüsselt** |

Weitere Felder je Einstellung: `label`, `description`, `group` (eigener Reiter im Dialog), `placeholder`,
`required`, `default`. Der Schlüssel `_language` ist reserviert (Sprachwahl des Tools).

## install.py

Alle Funktionen sind optional. `ctx` ist ein `InstallContext`.

```python
def check(ctx):                 # -> Liste fehlender Voraussetzungen ([] = alles da)
    return []

def install(ctx):               # Erstinstallation und „Reparieren“
    ctx.report(ctx.tr("install.ready", "Installed."))

def update(ctx, old_version):   # statt install() bei Updates, z. B. Einstellungen migrieren
    ...

def uninstall(ctx):             # vor dem Löschen des Tool-Ordners
    ...
```

`InstallContext` bietet: `report(text)` (Zeile im Installationsfenster), `tr(key, default, **werte)`,
`pip_install(*pakete)`, `run_powershell(skript)`, `run_powershell_elevated(skript)`, `settings`, `secrets`,
`tool_dir`, `data_dir`, `log`.

`check()` läuft, bevor `_lib` im Suchpfad liegt. Wer dort eigene Python-Pakete braucht, trägt
`ctx.tool_dir / "_lib"` selbst in `sys.path` ein.

## Versionen

- `MAJOR.MINOR.PATCH`: Fehlerbehebung → PATCH, neue Funktion → MINOR, inkompatible Änderung → MAJOR.
- Jede veröffentlichte Änderung braucht eine höhere Version, sonst sehen Clients sie nicht. Der Store-Workflow
  der [Vorlage](Entwicklung-Vorlagen-Repository) erzwingt das.
- Neue Funktionen des Hauptprogramms nutzen → `min_app_version` anheben.

## Siehe auch
- [Tool-Klasse und SDK](Entwicklung-Tool-Klasse-und-SDK)
- [Mehrsprachigkeit](Entwicklung-Mehrsprachigkeit)
