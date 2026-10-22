# Testen und veröffentlichen

> **Kurz:** Tool über *Datei › Tool aus Ordner installieren …* testen, Checkliste abarbeiten, Version erhöhen,
> pushen. Der Store-Workflow prüft und baut den Rest.

**Gilt für:** OmniWrench ab Version 0.7.0

## Lokal testen

1. OmniWrench starten (installiert oder aus dem Quellcode: `python main.py`).
2. *Datei › Tool aus Ordner installieren …* und den Tool-Ordner wählen (der mit `tool.json`).
3. Tool öffnen und ausprobieren. Nach Änderungen denselben Befehl erneut ausführen: Das Tool wird ersetzt,
   Einstellungen und Daten bleiben.
4. Fehler stehen im Protokoll (*Hilfe › Log-Ordner öffnen*). `self.context.log.info(...)` schreibt dorthin.

Mit einer leeren Testumgebung arbeiten, ohne die eigenen Daten zu berühren:

```powershell
$env:OMNIWRENCH_HOME = "C:\Temp\ow-test"; python main.py     # Linux: OMNIWRENCH_HOME=/tmp/ow-test python main.py
```

## Prüfungen

```bash
python -m compileall -q tools
python <OmniWrench>/scripts/check_locales.py tools/mein_tool
python scripts/store.py check
```

Die Vorlage führt alle drei bei jedem Pull Request automatisch aus.

## Checkliste vor jeder Version

- [ ] `version` in `tool.json` erhöht, bei neuen Programmfunktionen `min_app_version` angepasst
- [ ] `platforms` stimmt (Linux nur, wenn wirklich getestet)
- [ ] Voraussetzungen vollständig, `check()` meldet Fehlendes korrekt
- [ ] alle sichtbaren Texte über `tr()`, mindestens `en.json` vollständig, `check_locales` ohne Fehler
- [ ] lange Aufgaben im Hintergrund, Oberfläche friert nicht ein
- [ ] kleines Fenster (ca. 1000 px), großes Fenster, Skalierung 200 %, helles und dunkles Farbschema
- [ ] keine Passwörter in Kommandozeile, Log oder normalen Einstellungen
- [ ] schreibende Aktionen werden bestätigt
- [ ] Doku-Seite nach der [Vorlage](Vorlage-Tool-Seite) aktualisiert (Funktionen, Einstellungen, Versionen)
- [ ] `homepage` in `tool.json` zeigt auf die Doku-Seite

## Veröffentlichen

1. Committen und auf `main` pushen (oder per Pull Request mergen).
2. Der Workflow **Store** baut die Pakete und committet den Store.
3. Clients sehen das Update beim nächsten Start bzw. nach **Aktualisieren** im Store.

## Siehe auch
- [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository)
- [Wiki-Seiten schreiben](Entwicklung-Wiki-Seiten)
