# Datenablage und Datenschutz

> **Kurz:** Programmdateien und Benutzerdaten sind getrennt. Alle Daten liegen pro Benutzer im Profil.
> Ins Netz geht OmniWrench nur für Store und Updates, Tools nur zu den Systemen, die man ihnen nennt.

**Gilt für:** Hauptprogramm ab Version 0.8.0 (Ordnernamen `KuroShiro`; bis 0.7.x `DarkMatter`)

## Wo liegen die Daten?

| System | Ordner | Inhalt |
|---|---|---|
| Windows | `%APPDATA%\KuroShiro\OmniWrench\` | `settings.json`, `vault.json` (verschlüsselt), `tool_settings\`, `layout.json` |
| Windows | `%LOCALAPPDATA%\KuroShiro\OmniWrench\` | `tools\` (installierte Tools), `tool_data\`, `logs\` |
| Linux | `~/.config/KuroShiro/OmniWrench/` | Einstellungen, Tresor, Tool-Einstellungen, Layout |
| Linux | `~/.local/share/KuroShiro/OmniWrench/` | installierte Tools, Tool-Daten, Logs |

- Unter Linux gelten `XDG_CONFIG_HOME` und `XDG_DATA_HOME`, falls gesetzt.
- Daten aus älteren Versionen (Ordner `DarkMatter`, unter Linux früher `~/AppData/…`) werden beim ersten Start
  automatisch übernommen.
- Der **Programmordner** (z. B. `C:\Program Files\KuroShiro\OmniWrench`, `/opt/omniwrench`) wird nur bei
  Installation und Update geändert.

### Was steht wo?

| Datei / Ordner | Inhalt |
|---|---|
| `settings.json` | Programmeinstellungen (Sprache, Repositories, Updates …), keine Geheimnisse |
| `vault.json` | Tresor: Passwortmanager, Geheimnisse und Zugangsdaten aller Tools, verschlüsselt |
| `tool_settings\<tool-id>.json` | normale Einstellungen der Tools (Server, Pfade …), keine Geheimnisse |
| `layout.json` | Fenstergröße, geöffnete Tabs, Anordnung |
| `tools\<tool-id>\` | installierte Tools inkl. ihrer Python-Pakete (`_lib`) |
| `tool_data\<tool-id>\` | Daten der Tools, z. B. heruntergeladene Symbol-Bibliotheken (IconForge), Herstellerliste (NetProbe) |
| `logs\` | Protokolle (*Hilfe › Log-Ordner öffnen*) |

## Alles in einem Ordner (portabel)

- **Portable Version mit Daten** (z. B. USB-Stick): neben dem Programm einen Ordner `portable-data` anlegen.
  OmniWrench speichert dann alles dort statt im Profil.
- **Umgebungsvariable** `OMNIWRENCH_HOME=<Ordner>`: alle Daten in diesem Ordner (für Tests und Sonderfälle).

## Sichern und umziehen

Zum Sichern genügen die beiden Datenordner (bzw. `portable-data`). Installierte Tools lassen sich auch einfach
neu aus dem Store installieren; wichtig sind vor allem `vault.json`, `settings.json` und `tool_settings`.

## Datenschutz

OmniWrench überträgt keine Informationen an andere Systeme, solange der Benutzer oder die Person, die es
installiert und betreibt, das nicht ausdrücklich veranlasst.

Abgerufen werden nur:
- der **Tool-Store**: die eingetragenen `index.json`-Dateien (offiziell von `raw.githubusercontent.com`)
- die **Release-Liste** des Hauptprogramms von `api.github.com`

Die Prüfung beim Start lässt sich unter *Einstellungen › Updates* abschalten. Tool-Pakete werden nur auf
Anforderung geladen oder, wenn ausdrücklich eingeschaltet, beim Start automatisch aktualisiert (Standard: aus).
Es gibt keine Telemetrie und kein Konto.

Verbindungen zu Active Directory, DHCP-Servern, Passwortmanagern oder anderen Systemen stellen nur die Tools her,
die der Benutzer installiert und einrichtet. Was ein Tool im Netz tut, steht auf seiner Wiki-Seite unter
„Sicherheit und Datenschutz“.

## Siehe auch
- [Tresor und Anmeldung](Tresor-und-Anmeldung)
- [Installation › Deinstallation](Installation#deinstallation)
