# Fehlerbehebung

> **Kurz:** Erste Anlaufstelle ist das Protokoll (*Hilfe › Log-Ordner öffnen*). Probleme mit Tools lassen sich
> oft mit *Voraussetzungen prüfen* und *Reparieren* lösen.

**Gilt für:** Hauptprogramm ab Version 0.7.0 · Windows und Linux

## Protokolle

*Hilfe › Log-Ordner öffnen* öffnet den Ordner `logs` im Datenverzeichnis
([Datenablage](Datenablage-und-Datenschutz)). Bei einem unerwarteten Fehler zeigt OmniWrench eine Meldung und
schreibt die Einzelheiten ins Protokoll. Für eine Fehlermeldung bitte die passende Stelle aus dem Protokoll
mitschicken (vorher auf Server- oder Benutzernamen prüfen).

## Häufige Probleme

### Start und Anmeldung

| Problem | Ursache / Lösung |
|---|---|
| SmartScreen warnt beim Start | Programm ist nicht signiert: *Weitere Informationen › Trotzdem ausführen* |
| Masterpasswort vergessen | [Passwort vergessen](Tresor-und-Anmeldung#passwort-vergessen) |
| Kein Zertifikat in der Auswahl | Nur RSA-Zertifikate mit privatem Schlüssel, die entschlüsseln dürfen; Smartcard eingesteckt? „Zertifikatliste neu laden“ |
| Hinweis „Windows Server wird nicht unterstützt“ | OmniWrench ist für Clients gedacht; auf Servern sind Funktionen eingeschränkt |
| Linux: Fenster erscheint nicht, Meldung zu `xcb` | Qt-Systembibliotheken installieren, siehe [Installation](Installation#linux-portable-version) |

### Store und Updates

| Problem | Ursache / Lösung |
|---|---|
| „Store-Fehler“ / Repository nicht erreichbar | Netzwerk oder Proxy prüfen; URL unter *Einstellungen › Repositories* prüfen |
| Zertifikatsfehler hinter Firmen-Proxy | OmniWrench nutzt den Windows-Zertifikatspeicher; das Stammzertifikat des Proxys muss dort liegen |
| GitHub meldet „rate limit“ | GitHub-Token unter *Einstellungen › Updates* eintragen |
| Tool zeigt „Läuft nur unter Windows“ | Das Tool nutzt Windows-Funktionen (z. B. RSAT) und ist unter Linux nicht verfügbar |
| Update eines Tools wird übersprungen | Tool ist geöffnet: schließen und erneut aktualisieren |

### Voraussetzungen (RSAT & Co.)

| Problem | Ursache / Lösung |
|---|---|
| UAC-Abfrage abgelehnt | Installation abgebrochen; erneut mit *Reparieren* |
| Fehler `0x800f0954` | WSUS-Client darf optionale Funktionen nicht von Windows Update laden: Gruppenrichtlinie „Einstellungen für die Installation optionaler Komponenten …“ aktivieren und „direkt von Windows Update herunterladen“ erlauben, oder RSAT über die eigene Softwareverteilung installieren |
| Neustart erforderlich | Hinweis im Protokoll; Windows neu starten, dann *Voraussetzungen prüfen* |
| Tool startet nicht mehr nach Windows-Upgrade | RSAT fehlt evtl.: *Voraussetzungen prüfen*, dann *Reparieren* |
| PowerShell-Modul fehlt | PowerShell Gallery erreichbar? Sonst Modul von Hand mit `Install-Module -Scope CurrentUser` installieren |

### Tools

| Problem | Ursache / Lösung |
|---|---|
| „‹Tool› konnte nicht gestartet werden“ | Details im Protokoll; *Reparieren* versuchen; bei Fehlern im Tool ein Issue anlegen |
| Zugangsdaten mit ❗ | Passwort nach dem Zurücksetzen neu eintragen (✎-Knopf) |
| Externer Passwortmanager fragt ständig nach Anmeldung | Haken „Anmeldedaten speichern“ im Anmeldefenster setzen |

Werkzeugspezifische Probleme stehen auf der Wiki-Seite des Tools unter „Fehlerbehebung“.

## Fehler melden

Fehler und Wünsche bitte als [Issue auf GitHub](https://github.com/KuroShiroMe/OmniWrench/issues) melden:
OmniWrench-Version (*Hilfe › Über …*), Betriebssystem, betroffenes Tool mit Version, Schritte zum Nachstellen
und der passende Ausschnitt aus dem Protokoll.

## Siehe auch
- [Installation](Installation#probleme-bei-der-installation)
- [Store und Tools](Store-und-Tools)
