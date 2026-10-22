# Sprachen

> **Kurz:** OmniWrench spricht 12 Sprachen und 11 Dialekte. Umgestellt wird unter
> *Einstellungen › Allgemein › Sprache*, für einzelne Tools zusätzlich in deren Einstellungen.

**Gilt für:** Hauptprogramm ab Version 0.6.0 · Windows und Linux

## Verfügbare Sprachen

| Sprache | Code | | Dialekt | Code |
|---|---|---|---|---|
| Deutsch | `de` | | Badisch | `de_bad` |
| English | `en` | | Bairisch | `de_by` |
| Français | `fr` | | Hessisch | `de_hes` |
| Español | `es` | | Kölsch | `de_ksh` |
| Italiano | `it` | | Plattdüütsch | `de_nds` |
| Nederlands | `nl` | | Sächsisch | `de_sxu` |
| Polski | `pl` | | Schwäbisch | `de_swg` |
| Português (Brasil) | `pt` | | Schwiizerdütsch | `de_gsw` |
| Čeština | `cs` | | Wienerisch | `de_wien` |
| Svenska | `sv` | | Scots | `en_sco` |
| Türkçe | `tr` | | Posh English | `en_posh` |
| Українська | `uk` | | | |

Die Übersetzungen außer Deutsch und Englisch sind maschinell erstellt und noch nicht von Muttersprachlern
geprüft. Verbesserungen sind willkommen (siehe [Mehrsprachigkeit für Entwickler](Entwicklung-Mehrsprachigkeit)).

## Programmsprache

*Einstellungen › Allgemein › Sprache*. Ohne Einstellung nimmt OmniWrench die Anzeigesprache des Systems,
sonst Englisch. Die Auswahl zeigt Dialekte eingerückt unter ihrer Hauptsprache. Die Oberfläche wird sofort neu
aufgebaut, eine neue Anmeldung ist nicht nötig.

## Sprache der Tools

Tools bringen eigene Sprachdateien mit, oft nur Deutsch und Englisch. Die Sprache eines Tools ergibt sich so:

1. In den Tool-Einstellungen steht oben **Sprache**: *Automatisch* oder eine feste Sprache des Tools.
2. *Automatisch* nimmt die Programmsprache, wenn das Tool sie hat. Bei Dialekten zuerst die Hauptsprache
   (Badisch → Deutsch).
3. Gibt es keine passende Datei, ist das Tool **Englisch**.

Fehlt einem Tool nur ein einzelner Text, wird er aus der nächsten Sprache ergänzt (Dialekt → Hauptsprache →
Englisch). So erscheint nie ein leeres Feld.

## Siehe auch
- [Einstellungen](Einstellungen)
- [Mehrsprachigkeit für Entwickler](Entwicklung-Mehrsprachigkeit)
