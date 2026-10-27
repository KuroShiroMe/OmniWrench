# Tool-Entwicklung

> Für Tool-Entwickler gibt es die ausführliche Anleitung im Wiki:
> [Entwicklung](https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung). Diese Datei ist die interne technische
> Referenz; bei Änderungen am Paketformat oder SDK beide aktualisieren.

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
├── screenshots/   optional: PNGs für Store/Home + render.py (nicht im Paket, siehe Screenshots)
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
| `description` | | Kurzbeschreibung (Karte in Store/Home, Liste) |
| `long_description` | | Ausführliche Beschreibung (Detailleiste) |
| `author` | | |
| `category` | | Bereich als ID, z. B. `identity`, siehe [Kategorien](#kategorien) |
| `category_area` | | Nur für einen eigenen, neuen Bereich: Anzeigename (übersetzbar) |
| `icon` | | Symbol, siehe [Symbole](#symbole) |
| `icon_text` | | Eigenes Kürzel für das erzeugte Symbol (max. 4 Zeichen), z. B. `"EXO"` |
| `color` | | Hintergrundfarbe des erzeugten Symbols, z. B. `#0ea5e9` |
| `entry` | | `"<modul>:<Klasse>"`, Standard `tool:Tool` |
| `min_app_version` | | Mindestversion des Hauptprogramms |
| `platforms` | | Betriebssysteme, Standard `["windows"]`; `["windows", "linux"]`, wenn das Tool auch unter Linux läuft (siehe [Plattformen](#plattformen)) |
| `tags` | | Schlagwörter zur feineren Einordnung, siehe [Tags](#tags); sichtbar in Details und Store, durchsuchbar |
| `screenshots` | | `[{"file": "screenshots/x.png", "caption": "…"}]`, erstes = Hauptbild; siehe [Screenshots](#screenshots) |
| `single_instance` | | `true` = nur ein Tab gleichzeitig |
| `hooks` | | Einstiegspunkte ohne geöffneten Tab, z. B. `{"startup": "modul:funktion"}` (siehe [Eigene Passwortmanager-Anbieter](#eigene-passwortmanager-anbieter)) |
| `requirements` | | Voraussetzungen, siehe unten |

### Screenshots
Store und Home zeigen pro Tool-Karte einen durchblätterbaren Screenshot, die Detailleiste alle mit Unterschrift.
- PNG 1280×800, dunkel, englische UI, nur Beispieldaten; erstes Bild = Hauptansicht, dann je Funktion eins.
- Unterschrift übersetzt über `tool.screenshot.<dateiname ohne .png>` in den Tool-Locales.
- Erzeugt von `screenshots/render.py` (`def render(shot)`, API in `scripts/render_screenshots.py`):
  `python scripts/render_screenshots.py tools/<tool>` (ohne Argument alle; `--lang`, `--theme`).
- Nicht im ZIP: `build_store.py` kopiert sie nach `store/screenshots/<id>/` und schreibt url/sha256/size in
  index.json; neue Bilder brauchen keine Versionserhöhung. `check_store.py` prüft den Abgleich.

### Plattformen
OmniWrench läuft unter Windows und (seit 0.7.0) unter Linux. Ein Tool läuft nur auf den Systemen aus `platforms`:
Der Store zeigt andere Tools mit „Läuft nur unter …“ ohne Installieren-Knopf, die Installation wird abgelehnt.
`"linux"` nur eintragen, wenn das Tool dort wirklich funktioniert: keine PowerShell, kein `ctypes.windll`/`winreg`,
keine Windows-Voraussetzungen (`windows_capabilities`, `windows_features`, `powershell_modules`, `winget`).
Plattformabhängige Teile mit `sys.platform == "win32"` abfragen (Beispiel: NetProbe `icmp.py`). Der Starttest
(`scripts/smoke_test.py`, in der CI unter Windows und Linux) installiert und öffnet jedes Tool auf jedem System,
das es angibt.

### Kategorien
Es gibt nur eine Ebene: feste **Service-Bereiche** einer IT-Abteilung. Das Hauptprogramm übersetzt sie selbst
(`omniwrench/core/categories.py`, Schlüssel `category.area.<id>`). Die feinere Einordnung übernehmen die [Tags](#tags).

| Bereich | Anzeige (de) | Typische Inhalte |
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

Regeln:
- Vorhandene ID verwenden, z. B. `"category": "network"`. Ohne Angabe landet das Tool unter „Sonstiges“ (`other`).
- **Neuer Bereich:** eigene ID, z. B. `"category": "medical"`, Anzeigename über `category_area` / `"tool.category_area"`. Wird ein Bereich von mehreren Tools gebraucht, kommt er in die feste Liste des Hauptprogramms.
- Ein Tool steht in genau einem Bereich; Bezüge zu weiteren Bereichen über `tags`.
- `"tool.category"` in den Sprachdateien enthält den ausgeschriebenen Bereich (z. B. `"Netzwerk & Konnektivität"`). Das aktuelle Hauptprogramm nutzt ihn nur als Rückfall, ältere Versionen (bis 0.6.x) zeigen ihn an.
- Ältere Angaben mit Unterkategorie (`network/diagnostics`) und alte Freitext-Pfade (`Network/IP Tools`, `MS Server Tools/…`, `Security/…`, `Design/…`) werden automatisch auf den Bereich reduziert.

### Tags
`tags` ordnen ein Tool feiner ein (Technologie, Protokoll, Produkt, Aufgabe). Sie stehen in den Details auf der
Startseite und auf der Store-Karte; ein Klick auf ein Tag sucht nach allen Tools mit diesem Begriff.
- 4 bis 12 aussagekräftige Begriffe, sprachneutral: Produkt- und Protokollnamen (`Active Directory`, `DNS`,
  `KeePass`), sonst Englisch (`Port Scan`, `User Accounts`). Schreibweise wie sie angezeigt werden soll.
- Keine Synonyme oder Übersetzungen als Tags; deutsche Suchbegriffe findet die Suche über die übersetzte Beschreibung.
- Bezug zu einem weiteren Bereich als Tag, z. B. `Service Desk` bei der AD-Benutzerabfrage.

### Symbole

Das Symbol der Kachel wird in dieser Reihenfolge bestimmt:

1. **Eigene Bilddatei:** `"icon": "icon.png"` (png/svg/ico, quadratisch, mind. 128 px, im Tool-Ordner).
   `build_store.py` bettet sie in den Store-Katalog ein, damit sie auch im Store erscheint.
2. **Symbol aus der Bibliothek:** `"icon": "server"`. Eingebaut sind rund 2.100 Symbole von
   [Lucide](https://lucide.dev/icons) (ISC-Lizenz, frei auch für kommerzielle Nutzung).
   **Die Namen findest du im Tool IconForge** (Bibliothek „Lucide“): Der dort angezeigte Symbolname ist genau
   der Wert für `"icon"`. Alternativ: *Extras › Symbol-Bibliothek*.
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

* `python`: wird per pip in `<tool>/_lib` installiert und beim Laden in `sys.path` eingetragen.
  In der EXE-Version nur Pakete mit fertigem Wheel (kein Kompilieren); Standardbibliothek und die gängigen
  PySide6-Module sind eingebaut (Liste: `QT_MODULES` in `scripts/build_exe.py`).
* `windows_capabilities` / `windows_features`: werden gemeinsam in **einer** Administrator-Sitzung installiert (eine UAC-Abfrage).
  Unter Windows Server läuft das über `Install-WindowsFeature`, auf Clients über `Enable-WindowsOptionalFeature`.
  Der Fortschritt erscheint live im Installationsdialog; meldet Windows einen nötigen Neustart, steht ein Hinweis im
  Protokoll. Läuft OmniWrench bereits als Administrator, entfällt die UAC-Abfrage.
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
| `get_credential(key)` | `(benutzer, passwort)` einer `credential`-Einstellung (blockiert, solange ein externer Manager antwortet) |
| `get_credential_async(key, on_done)` | dasselbe im Hintergrund, `on_done((benutzer, passwort) \| None)` läuft im GUI-Thread |
| `secrets.get/set/delete(key)` | freier, verschlüsselter Speicher des Tools |
| `secrets.is_lost(key)` | `True`, wenn der Wert beim Zurücksetzen des Masterpassworts verworfen und noch nicht neu gesetzt wurde (dann z. B. ❗ anzeigen) |
| `tr(key, default=None, **platzhalter)` / `language` | Übersetzung aus `locales/` bzw. aktive Sprache |
| `data_dir` | eigener Datenordner (`%LOCALAPPDATA%\KuroShiro\OmniWrench\tool_data\<id>`) |
| `tool_dir` | Installationsordner (für mitgelieferte Dateien) |
| `run_powershell(script, stdin=…)` / `run_powershell_json(…)` | PowerShell ausführen (UTF-8, ohne Fenster) |
| `run_powershell_elevated(script, on_output=None)` | mit Adminrechten (UAC); `on_output(zeile)` erhält die Ausgabe live, `returncode` 1223 = UAC-Abfrage abgelehnt |
| `notify(msg)` | Meldung in der Statusleiste |
| `open_settings()` | Einstellungsdialog des Tools öffnen |
| `log` | Logger (`%LOCALAPPDATA%\KuroShiro\OmniWrench\logs`) |

### Zugangsdaten und Passwortmanager

OmniWrench hat einen eingebauten Passwortmanager (*Extras › Passwortmanager*). Mit dem Tool
**OmniVault** kommen externe Manager dazu (SecretManagement, KeePass, Netwrix, Bitwarden, 1Password, HashiCorp Vault …).
Die Auswahl „Aus Passwortmanager“ durchsucht dann alle Manager gleichzeitig.

Grundregeln:
* In Einstellungen werden **nur Verweise** gespeichert (`{"name", "username", "ref"}`), nie Passwörter externer Manager.
* Das Passwort wird erst beim Gebrauch abgerufen, **einmal pro Sitzung**, und nur im Speicher gehalten
  (beim Sperren gelöscht).
* Braucht ein Manager neue Anmeldedaten (z. B. geändertes Passwort), fragt OmniWrench selbst nach – ohne Fehlermeldung.
* Ein Feld kann **mehrere** Zugangsdaten enthalten; der Benutzer wählt per Auswahlliste.
* Externe Manager brauchen oft 1–3 s. Im GUI-Thread daher die `…_async`-Varianten nehmen, sonst friert
  die Oberfläche so lange ein. In eigenen Hintergrund-Threads (`run_async`) geht auch der direkte Abruf;
  eine nötige Anmelde-Rückfrage erscheint trotzdem korrekt im GUI-Thread.

So nutzt du das im Tool:

* **Einstellung vom Typ `credential`** – der Einstellungsdialog zeigt automatisch die Auswahlliste mit
  Buttons 🔑 (aus Manager), + (manuell), 🗑 (entfernen). Im Code:

  ```python
  user, password = self.context.get_credential("credential")   # gewählter Eintrag, Abruf erst hier
  self.context.get_credential_async("credential", self._start)  # dasselbe, ohne die Oberfläche zu blockieren
  entries = self.context.get_credentials("credential")          # alle Einträge (ohne Passwörter)
  ```

* **Auswahlliste direkt in der Tool-Oberfläche** (gebunden an dieselbe Einstellung, speichert selbst):

  ```python
  from omniwrench.sdk import CredentialField

  self.login = CredentialField(settings=self.context.settings, key="credential")
  layout.addWidget(self.login)
  ...
  creds = self.login.resolve()     # (user, password) oder None - erst jetzt wird abgerufen
  self.login.resolve_async(self._start)   # empfohlen: Abruf im Hintergrund, danach self._start(creds)
  ```

* **Nur der Suchdialog:** `pick_credential(parent)` → `(user, password)` oder `None`.

Beispiel: [ad_user_lookup/tool.py](../tools/ad_user_lookup/tool.py).

### Eigene Passwortmanager-Anbieter

Ein Tool kann weitere Quellen bereitstellen. Dazu implementiert es `CredentialProvider` und registriert ihn
in einem **Startup-Hook** (läuft nach dem Anmelden und nach der Installation, auch ohne geöffneten Tab):

```json
"hooks": {"startup": "connectors:register_all"}
```

```python
from omniwrench.sdk import AuthenticationRequired, AuthField, Credential, CredentialProvider

class MyProvider(CredentialProvider):
    id, name = "my-provider", "Mein Manager"
    def search(self, query):            # -> [Credential(id, name, username)]  (ohne Passwort)
        ...
    def get_secret(self, cred_id):      # -> Credential(..., password=...)
        ...                             # bei falschen Anmeldedaten: raise AuthenticationRequired(self)
    def auth_fields(self):              # wonach bei AuthenticationRequired gefragt wird
        return [AuthField("password", "Passwort", secret=True)]
    def set_auth(self, values, save):   # neue Anmeldedaten übernehmen, save=True -> dauerhaft speichern
        ...

def register_all(ctx):
    ctx.register_credential_provider(MyProvider())   # wird bei Deinstallation automatisch entfernt
```

Vollständiges Beispiel: [omnivault/connectors.py](../tools/omnivault/connectors.py)
mit den JSON-Definitionen in `connector_types.json`.

Lang laufende Aufgaben (AD-Abfragen, Netzwerk-Scans) gehören mit `run_async(fn, on_done, on_error)` in einen
Hintergrund-Thread. Die Callbacks laufen wieder im GUI-Thread.

**Sicherheit:** Passwörter nie in die Kommandozeile oder ins Skript einbauen. Übergib sie über `stdin`, wie es
[ad_user_lookup/tool.py](../tools/ad_user_lookup/tool.py) vormacht.

## Responsive Oberfläche und Skalierung

OmniWrench läuft von kleinen Fenstern (ca. 1000 px) bis zu maximierten 8k-Monitoren. Zusätzlich zur
Windows-Anzeigeskalierung kann unter *Einstellungen › Anzeige › Skalierung* vergrößert werden (75–300 %).

- Alle Größen im Code sind logische Pixel bzw. Punkt (pt) – sie wachsen mit der Skalierung automatisch mit.
  Keine Größen selbst umrechnen.
- Layouts statt fester Breiten verwenden; Mindestbreiten einer Zeile sollten zusammen unter ca. 700 px bleiben.
  Was breiter wird (viele Buttons, Seite-an-Seite-Bereiche), bei schmalem Fenster umbrechen oder untereinander
  anordnen (Beispiel: `_layout_filter` in [subnet_calculator/tool.py](../tools/subnet_calculator/tool.py)).
- Selbst gezeichnete Bilder (QPixmap/QImage) in `logische Größe × sdk.device_pixel_ratio()` rendern und
  `pixmap.setDevicePixelRatio(...)` setzen, sonst werden sie bei 200–300 % unscharf.
- Dialoge mit `sdk.fit_to_screen(dialog, breite, höhe)` statt `resize()` öffnen – so passen sie auch auf
  kleine Bildschirme mit hoher Skalierung.

## Mehrsprachigkeit

Jedes Tool bringt seine Sprachdateien in `locales/<code>.json` mit: flache JSON-Dateien mit Schlüssel → Text.
Platzhalter stehen in `{geschweiften Klammern}`.

```json
{
  "_meta": {"name": "German", "native": "Deutsch"},

  "tool.name": "Subnetzrechner",
  "tool.description": "IPv4/IPv6-Netze berechnen …",
  "tool.long_description": "…",
  "tool.category": "Netzwerk & Konnektivität",

  "settings.export_dir.label": "Export-Ordner",
  "settings.export_dir.description": "Standardordner für den CSV-Export.",
  "settings.csv_separator.option.;": "Semikolon",
  "settings.group.Export": "Export",

  "ui.exported": "{count} Subnetze exportiert nach {path}"
}
```

| Schlüssel | Wirkung |
|---|---|
| `tool.name`, `tool.description`, `tool.long_description`, `tool.category`, `tool.category_area` | Anzeige in Home, Seitenleiste und Store (`scripts/build_store.py` übernimmt sie in die index.json) |
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
Dialekte heißen `<basis>_<kürzel>` (z. B. `de_hes`). Die Sprachauswahl zeigt sie eingerückt unter ihrer
Hauptsprache; ein Tool ohne eigene Dialektdatei nutzt automatisch die Basissprache.

Mit `self.context.language` fragst du die aktive Sprache ab, z. B. für Zahlenformate.

Verfügbare Sprachcodes des Hauptprogramms: `en`, `de`, `fr`, `es`, `it`, `nl`, `pl`, `pt` (Brasilien), `cs`, `sv`,
`tr`, `uk` sowie die Dialekte `de_bad` (Badisch), `de_by` (Bayrisch), `de_hes` (Hessisch), `de_ksh` (Kölsch),
`de_nds` (Plattdeutsch), `de_sxu` (Sächsisch), `de_swg` (Schwäbisch), `de_gsw` (Schwiizerdütsch), `de_wien`
(Wienerisch), `en_sco` (Scots), `en_posh` (Posh English). Ein Tool muss nicht alle Sprachen mitbringen: fehlt eine,
greift die Fallback-Kette.

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
