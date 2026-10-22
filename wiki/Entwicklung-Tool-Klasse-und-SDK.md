# Tool-Klasse und SDK

> **Kurz:** Das Einstiegsmodul enthält eine Klasse, die von `omniwrench.sdk.ToolBase` erbt und in
> `create_widget()` ihre Oberfläche baut. Über `self.context` erreicht sie Einstellungen, Übersetzungen,
> Tresor, Zugangsdaten, PowerShell und mehr.

**Gilt für:** OmniWrench ab Version 0.7.0

## Inhalt
- [Die Tool-Klasse](#die-tool-klasse)
- [ToolContext](#toolcontext)
- [Hintergrundarbeit](#hintergrundarbeit)
- [Zugangsdaten](#zugangsdaten)
- [Eigene Passwortmanager-Anbieter](#eigene-passwortmanager-anbieter)
- [Hooks](#hooks)
- [PowerShell](#powershell)
- [Sicherheit](#sicherheit)
- [Weitere Hilfsfunktionen](#weitere-hilfsfunktionen)

## Die Tool-Klasse

```python
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget
from omniwrench.sdk import ToolBase


class Tool(ToolBase):
    def create_widget(self, parent=None) -> QWidget:
        w = QWidget(parent)
        lay = QVBoxLayout(w)
        self.label = QLabel(f"Server: {self.context.settings.get('server')}")
        lay.addWidget(self.label)
        return w

    def on_settings_changed(self, changed_keys: set[str]) -> None:
        if "server" in changed_keys:
            self.label.setText(f"Server: {self.context.settings.get('server')}")

    def can_close(self) -> bool:     # False = Tab bleibt offen (z. B. ungespeicherte Änderungen)
        return True

    def shutdown(self) -> None:      # Threads beenden, Verbindungen schließen
        pass
```

- Pro geöffnetem Tab gibt es **eine eigene Instanz**. Was mehrere Tabs teilen sollen, gehört in Modulvariablen
  oder in den Datenordner.
- Klassenname und Modul legt `entry` in der `tool.json` fest (`"tool:Tool"`).
- Nach einem Sprachwechsel oder Update baut OmniWrench offene Tabs mit einer neuen Instanz neu auf.
- `ToolBase` ist **kein** `QObject`. Eigene Qt-Signale gehören in eine kleine Hilfsklasse
  (`class _Bridge(QObject): updated = Signal(object)`), die in `create_widget()` angelegt wird.

## ToolContext

| Mitglied | Beschreibung |
|---|---|
| `settings.get(key)` / `settings.set(key, value)` | Einstellungen laut `config.json`; Geheimnisse kommen automatisch aus dem Tresor |
| `get_credential(key)` | `(benutzer, passwort)` des gewählten Eintrags einer `credential`-Einstellung (blockiert, solange ein externer Manager antwortet) |
| `get_credential_async(key, on_done, on_error=None)` | dasselbe im Hintergrund; `on_done((benutzer, passwort) \| None)` läuft im GUI-Thread |
| `get_credentials(key)` | alle Einträge einer `credential`-Einstellung, ohne Passwörter |
| `secrets.get/set/delete(key)` | freier, verschlüsselter Speicher des Tools im Tresor |
| `secrets.is_lost(key)` | `True`, wenn der Wert beim Zurücksetzen des Masterpassworts verworfen wurde (dann z. B. ❗ anzeigen) |
| `tr(key, default=None, **werte)` | Übersetzung aus `locales/` |
| `language` | aktive Sprache des Tools, z. B. `de`, `en`, `de_bad` |
| `data_dir` | eigener Datenordner (`…/tool_data/<id>`), bleibt bei Updates erhalten |
| `tool_dir` | Installationsordner (mitgelieferte Dateien lesen, nicht hineinschreiben) |
| `run_powershell(skript, stdin=None, timeout=300, shell="powershell")` | PowerShell ausführen, siehe [PowerShell](#powershell) |
| `run_powershell_json(…)` | dasselbe, Ausgabe als JSON gelesen |
| `run_powershell_elevated(skript, on_output=None)` | mit Administratorrechten (UAC) |
| `register_credential_provider(provider)` | eigenen Passwortmanager bereitstellen |
| `notify(text)` | Meldung in der Statusleiste |
| `open_settings()` | Einstellungsdialog des Tools öffnen |
| `log` | Logger; schreibt ins OmniWrench-Protokoll |
| `manifest`, `tool_id` | Metadaten des Tools |

## Hintergrundarbeit

Alles, was länger als einen Augenblick dauert (Netzwerk, AD, PowerShell, Dateien), gehört in einen
Hintergrund-Thread, sonst friert die Oberfläche ein:

```python
from omniwrench.sdk import run_async

def _start(self):
    self.button.setEnabled(False)
    run_async(lambda: lade_daten(self.server), self._fertig, self._fehler)

def _fertig(self, ergebnis):        # läuft im GUI-Thread
    self.button.setEnabled(True)
    ...

def _fehler(self, meldung: str):    # läuft im GUI-Thread, meldung = Text der Ausnahme
    self.button.setEnabled(True)
    self.status.setText(self.context.tr("ui.error", "Error: {error}", error=meldung))
```

- Im Hintergrund-Thread **keine Widgets** anfassen.
- `run_async(fn, on_done, on_error, on_progress)`: Mit `on_progress` bekommt `fn` eine Funktion, über die es
  Zwischenstände an die Oberfläche schickt.
- Für dauerhafte Threads mit vielen Aktualisierungen (z. B. ein Scanner) eine `_Bridge(QObject)` mit Signalen
  verwenden (Beispiel: NetProbe).

## Zugangsdaten

OmniWrench hat einen eingebauten Passwortmanager; mit OmniVault kommen externe Manager dazu. Grundregeln:

- In Einstellungen stehen nur Verweise, nie Passwörter externer Manager.
- Abgerufen wird erst beim Gebrauch, einmal pro Sitzung, nur im Arbeitsspeicher.
- Braucht ein Manager eine neue Anmeldung, fragt OmniWrench selbst; das Tool sieht keine Fehlermeldung.
- Ein Feld kann mehrere Zugangsdaten enthalten.

**Als Einstellung:** `{"key": "login", "type": "credential", "label": "Credentials"}` in `config.json`. Im Code:

```python
user, password = self.context.get_credential("login")              # blockiert ggf. 1–3 s
self.context.get_credential_async("login", self._mit_zugang)       # empfohlen im GUI-Thread
```

**Direkt in der Oberfläche** (Auswahlliste, an dieselbe Einstellung gebunden):

```python
from omniwrench.sdk import CredentialField

self.login = CredentialField(settings=self.context.settings, key="login")
layout.addWidget(self.login)
...
self.login.resolve_async(self._start)     # self._start((benutzer, passwort) | None)
```

**Nur der Suchdialog:** `pick_credential(parent)` → `(benutzer, passwort)` oder `None`.

Beispiel: [ad_user_lookup/tool.py](https://github.com/KuroShiroMe/OmniWrench/blob/main/tools/ad_user_lookup/tool.py).

## Eigene Passwortmanager-Anbieter

Ein Tool kann weitere Quellen für die Zugangsdaten-Auswahl bereitstellen:

```json
"hooks": {"startup": "connectors:register_all"}
```

```python
from omniwrench.sdk import AuthenticationRequired, AuthField, Credential, CredentialProvider

class MyProvider(CredentialProvider):
    id, name = "my-provider", "Mein Manager"

    def search(self, query):            # -> [Credential(id, name, username)], ohne Passwort
        ...
    def get_secret(self, cred_id):      # -> Credential(..., password=...)
        ...                             # falsche Anmeldedaten: raise AuthenticationRequired(self)
    def auth_fields(self):              # wonach bei AuthenticationRequired gefragt wird
        return [AuthField("password", "Passwort", secret=True)]
    def set_auth(self, values, save):   # neue Anmeldedaten übernehmen; save=True -> dauerhaft speichern
        ...

def register_all(ctx):
    ctx.register_credential_provider(MyProvider())   # bei Update/Deinstallation automatisch entfernt
```

Vollständiges Beispiel: [omnivault/connectors.py](https://github.com/KuroShiroMe/OmniWrench/blob/main/tools/omnivault/connectors.py).

## Hooks

`"hooks": {"startup": "modul:funktion"}` ruft `funktion(ctx)` nach jeder Anmeldung und direkt nach der
Installation auf, auch ohne geöffneten Tab. Für Hintergrunddienste, Anbieter-Registrierung u. Ä.
Hooks müssen schnell zurückkehren; längere Arbeit mit `run_async` starten.

## PowerShell

```python
res = self.context.run_powershell(script, stdin=json.dumps(params))
if res.returncode != 0:
    raise RuntimeError(res.stderr)
```

- UTF-8, kein Fenster, Fehlerausgabe ohne CLIXML-Rauschen; `shell="pwsh"` nutzt PowerShell 7.
- `run_powershell_json` liest die Ausgabe als JSON (`ConvertTo-Json` im Skript).
- `run_powershell_elevated` startet eine Administrator-Sitzung (eine UAC-Abfrage; entfällt, wenn OmniWrench
  schon erhöht läuft). `returncode == 1223` heißt: UAC abgelehnt.
- `ps_quote(text)` setzt einen Wert sicher in einfache Anführungszeichen.
- Neue Tools möglichst in Python schreiben; PowerShell nur, wo es ohne nicht geht (z. B. Module ohne API).
  PowerShell gibt es unter Linux nicht.

## Sicherheit

- Passwörter **nie** in Skripttext, Kommandozeile oder Log einbauen. Parameter als JSON über `stdin` übergeben
  und im Skript mit `[Console]::In.ReadToEnd() | ConvertFrom-Json` lesen (wie die AD Benutzerabfrage).
- Benutzereingaben, die in Skripte gelangen, mit `ps_quote` oder als stdin-Parameter übergeben.
- Geheimnisse nur über `secrets` oder Einstellungen vom Typ `secret`/`credential` speichern.
- Schreibende Aktionen vorher bestätigen lassen; kritische (Löschen) mit Eingabe eines Bestätigungsworts.

## Weitere Hilfsfunktionen

| Funktion | Zweck |
|---|---|
| `sdk.device_pixel_ratio()` | Pixelverhältnis für selbst gezeichnete Bilder ([Layout](Entwicklung-Layout-und-Skalierung)) |
| `sdk.fit_to_screen(dialog, breite, höhe)` | Dialoggröße, die auf jeden Bildschirm passt |
| `sdk.APP_VERSION` | Version von OmniWrench |
| `sdk.LANGUAGE_KEY` | reservierter Einstellungsschlüssel der Sprachwahl |

## Siehe auch
- [Paketformat](Entwicklung-Paketformat)
- [Mehrsprachigkeit](Entwicklung-Mehrsprachigkeit)
- [Layout und Skalierung](Entwicklung-Layout-und-Skalierung)
