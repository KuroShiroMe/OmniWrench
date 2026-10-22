# Mehrsprachigkeit

> **Kurz:** Jedes Tool bringt seine Texte in `locales/<sprache>.json` mit (mindestens `en.json`). Im Code wird
> jeder sichtbare Text mit `self.context.tr("schlüssel", "Englischer Standard")` geholt.

**Gilt für:** OmniWrench ab Version 0.6.0

## Sprachdateien

Flache JSON-Dateien mit Schlüssel → Text. Platzhalter stehen in `{geschweiften Klammern}`.

```json
{
  "_meta": {"name": "German", "native": "Deutsch"},

  "tool.name": "Subnetzrechner",
  "tool.description": "IPv4/IPv6-Netze berechnen …",
  "tool.long_description": "…",

  "settings.export_dir.label": "Export-Ordner",
  "settings.export_dir.description": "Standardordner für den CSV-Export.",
  "settings.csv_separator.option.;": "Semikolon",
  "settings.group.Export": "Export",

  "ui.exported": "{count} Subnetze exportiert nach {path}"
}
```

| Schlüssel | Wirkung |
|---|---|
| `tool.name`, `tool.description`, `tool.long_description` | Anzeige in Home, Seitenleiste und Store (der Store-Bau übernimmt sie in den Katalog) |
| `tool.category_area` | Anzeigename eines eigenen Bereichs |
| `tool.category` | ausgeschriebener Bereich, nur für OmniWrench bis 0.6.x nötig |
| `settings.<key>.label` / `.description` / `.placeholder` | Texte im Einstellungsdialog |
| `settings.<key>.option.<wert>` | Anzeigetext einer `choice`-Option |
| `settings.group.<gruppe>` | Reiter-Titel einer Einstellungsgruppe |
| alles andere | frei wählbar, z. B. `ui.*`, `err.*`, `install.*` |

## Im Code

```python
tr = self.context.tr
QPushButton(tr("ui.start", "Start"))
self.status.setText(tr("ui.found", "{count} result(s)", count=len(items)))
```

- Der zweite Parameter ist der Standardtext, falls der Schlüssel in keiner Datei steht.
- Platzhalter **nicht** `key` oder `default` nennen (kollidiert mit den Parametern von `tr`).
- `self.context.language` liefert die aktive Sprache, z. B. für Zahlen- und Datumsformate.
- In `install.py`: `ctx.tr(…)` genauso.

## Welche Sprache ein Tool verwendet

1. In den Tool-Einstellungen wählt der Benutzer **Automatisch** oder eine Sprache des Tools.
2. *Automatisch* nimmt die Programmsprache, wenn das Tool sie hat; bei Dialekten zuerst die Hauptsprache
   (`de_bad` → `de`). Sonst Englisch.
3. Fehlt ein einzelner Schlüssel: Dialekt → Hauptsprache → `en.json` → Standardtext im Code bzw. Text aus
   `config.json`.

Ein Tool muss nicht alle Sprachen mitbringen. Sprachcodes von OmniWrench: `en`, `de`, `fr`, `es`, `it`, `nl`,
`pl`, `pt` (Brasilien), `cs`, `sv`, `tr`, `uk` und die Dialekte `de_bad`, `de_by`, `de_hes`, `de_ksh`,
`de_nds`, `de_sxu`, `de_swg`, `de_gsw`, `de_wien`, `en_sco`, `en_posh`.

## Stil

- Neutral und knapp wie normale Software: „Server eingeben“, „Verbindung fehlgeschlagen: {error}“.
  Kein Duzen, kein Plauderton. Dialekt-Dateien dürfen locker sein.
- Fachbegriffe so, wie Admins sie kennen (Scope, Lease, Failover).

## Prüfen

```bash
python <OmniWrench>/scripts/check_locales.py tools/mein_tool
```

Vergleicht alle Sprachdateien mit `en.json` und `config.json`: fehlende und überzählige Schlüssel, falsche
Platzhalter. Der Store-Workflow der [Vorlage](Entwicklung-Vorlagen-Repository) führt die Prüfung automatisch aus.

## Siehe auch
- [Sprachen (für Anwender)](Sprachen)
- [Paketformat](Entwicklung-Paketformat)
