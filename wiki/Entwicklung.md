# Entwicklung

> **Kurz:** Ein OmniWrench-Tool ist ein Ordner mit `tool.json`, `config.json`, `install.py` und einem
> Python-Modul mit der Oberfläche (PySide6). Tools werden über ein eigenes GitHub-Repository verteilt; die
> [Vorlage](Entwicklung-Vorlagen-Repository) richtet so ein Repository mit einem Klick ein.

**Gilt für:** OmniWrench ab Version 0.7.0

## Der schnellste Weg

1. Auf [OmniWrench-Tool-Template](https://github.com/KuroShiroMe/OmniWrench-Tool-Template)
   **Use this template › Create a new repository** wählen.
2. Warten, bis der Workflow „Vorlage einrichten“ fertig ist (Tab *Actions*): Das Repository enthält dann ein
   lauffähiges Beispiel-Tool und einen fertigen Store.
3. In OmniWrench das Repository eintragen (*Einstellungen › Repositories*) und das Tool aus dem Store installieren.
4. Tool anpassen, Version erhöhen, pushen: Der Store baut sich selbst neu.

Ausführlich: [Schnellstart](Entwicklung-Schnellstart).

## Inhalt des Entwicklerbereichs

| Seite | Inhalt |
|---|---|
| [Schnellstart](Entwicklung-Schnellstart) | vom leeren Repository zum installierten Tool in 15 Minuten |
| [Paketformat](Entwicklung-Paketformat) | Aufbau eines Tools: `tool.json`, `config.json`, `install.py`, Kategorien, Tags, Symbole, Voraussetzungen, Plattformen |
| [Tool-Klasse und SDK](Entwicklung-Tool-Klasse-und-SDK) | `ToolBase`, `ToolContext`, Einstellungen, Hintergrundarbeit, PowerShell, Zugangsdaten, eigene Passwortmanager-Anbieter |
| [Mehrsprachigkeit](Entwicklung-Mehrsprachigkeit) | Sprachdateien eines Tools, Schlüssel, Fallback, Prüfung |
| [Layout und Skalierung](Entwicklung-Layout-und-Skalierung) | Oberflächen, die von 1000 px bis 8K und von 75 bis 300 % Skalierung funktionieren |
| [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository) | Aufbau, Store bauen, Versionen, Veröffentlichen, private Repositories, Firmennetz |
| [Vorlagen-Repository](Entwicklung-Vorlagen-Repository) | die GitHub-Vorlage: was sie enthält und wie die Automatik funktioniert |
| [Repository einbinden](Entwicklung-Repository-einbinden) | eigenes Repository in OmniWrench eintragen und verteilen |
| [Testen und veröffentlichen](Entwicklung-Testen-und-Veroeffentlichen) | lokal testen, Checkliste vor jeder Version |
| [Wiki-Seiten schreiben](Entwicklung-Wiki-Seiten) | Regeln und Aufbau der Doku-Seiten, Vorlagen |

## Was ein Tool kann

- eine beliebige PySide6-Oberfläche in einem eigenen, andockbaren Tab
- Einstellungen, für die OmniWrench den Dialog selbst erzeugt (inkl. verschlüsselter Passwörter und
  Zugangsdaten aus dem Passwortmanager)
- Voraussetzungen, die OmniWrench vor der Installation einrichtet (Python-Pakete, RSAT, Windows-Features,
  PowerShell-Module, winget-Pakete)
- eigene Sprachdateien mit automatischer Sprachwahl
- verschlüsselter Speicher für eigene Geheimnisse, eigener Datenordner, Logger
- Hintergrundarbeit, ohne die Oberfläche zu blockieren
- Hooks, die nach der Anmeldung laufen, z. B. für eigene Passwortmanager-Anbieter

## Grundregeln

- Ein Tool importiert nur aus `omniwrench.sdk`, PySide6, der Standardbibliothek und seinen eigenen
  Python-Paketen (`requirements.python`). Andere Module von OmniWrench sind keine stabile Schnittstelle.
- Jede Version eines Tools bekommt eine höhere `version`; nur so erkennen Clients Updates.
- Texte der Oberfläche kommen aus den Sprachdateien, neutral formuliert („Server eingeben“, nicht „Gib … ein“).
- Passwörter nie in Kommandozeilen, Logs oder normale Einstellungen schreiben.
- Lange Aufgaben laufen im Hintergrund (`run_async`).
- Jedes Tool hat eine vollständige Doku-Seite nach der [Vorlage](Vorlage-Tool-Seite).

## Hilfe

Fragen und Probleme bei der Tool-Entwicklung als
[Issue](https://github.com/KuroShiroMe/OmniWrench/issues) stellen. Die mitgelieferten Tools im Ordner
[`tools/`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools) sind vollständige Beispiele:
der [Subnetzrechner](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/subnet_calculator) (ohne
Voraussetzungen) und die [AD Benutzerabfrage](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/ad_user_lookup)
(mit RSAT, PowerShell und Zugangsdaten).
