# Vorlage: Tool-Seite

Diese Seite ist die Kopiervorlage für die Wiki-Seite eines Tools. Jedes Tool bekommt eine eigene Seite
`Tool-<Name>.md` mit genau diesen Abschnitten in dieser Reihenfolge. Abschnitte, die für ein Tool nicht
zutreffen, bleiben mit einem Satz stehen (z. B. „Keine Voraussetzungen.“), damit alle Seiten gleich aufgebaut sind.
Regeln dazu: [Wiki-Seiten schreiben](Entwicklung-Wiki-Seiten).

Den Block unten kopieren, Platzhalter `‹…›` ersetzen, Hinweise in `<!-- … -->` löschen.

````markdown
# ‹Anzeigename des Tools›

> **Kurz:** ‹Ein bis zwei Sätze: was das Tool tut und für wen.›

| | |
|---|---|
| **Tool-ID** | `‹bereich.tool-id›` |
| **Stand der Seite** | Version ‹X.Y.Z› |
| **Bereich** | ‹Bereich, z. B. Netzwerk & Konnektivität› |
| **Tags** | ‹Tag 1›, ‹Tag 2›, … |
| **Plattformen** | ‹Windows / Windows, Linux› |
| **Voraussetzungen** | ‹z. B. RSAT: DHCP-Server-Tools (wird automatisch installiert) / keine› |
| **Adminrechte** | ‹nur für die Installation der Voraussetzungen / nicht nötig / …› |
| **Mindestversion OmniWrench** | ‹0.6.0› |
| **Quellcode** | [`tools/‹ordner›`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/‹ordner›) |

![‹Hauptansicht des Tools›](images/‹tool›-uebersicht.png)

## Inhalt
<!-- Sprungmarken auf alle Abschnitte ab "Wofür" -->

## Wofür
<!-- Typische Aufgaben als Liste, aus Sicht des Admins: "Prüfen, ob ...", "Schnell herausfinden, ..." -->
- ‹Einsatzzweck 1›
- ‹Einsatzzweck 2›

## Installation und Voraussetzungen
<!-- Was der Store mitinstalliert, ob UAC nötig ist, Besonderheiten unter Linux, zusätzliche Software. -->

## Erste Schritte
<!-- Nummerierte Schritte vom Öffnen bis zum ersten Ergebnis. -->
1. ‹Schritt›
2. ‹Schritt›

## Funktionen im Detail
<!-- Ein Unterabschnitt (###) je Funktion, Seite oder Reiter des Tools, in der Reihenfolge der Oberfläche.
     Je Unterabschnitt: was man sieht, was man tun kann (Knöpfe/Menüs fett), was dabei im Hintergrund passiert,
     Grenzen. Tabellen für Spalten, Felder und Optionen. Screenshot, wo es hilft. -->

### ‹Funktion 1›

### ‹Funktion 2›

## Einstellungen
<!-- Rechtsklick › Einstellungen. Alle Felder aus config.json, mit Standardwert. Die Sprache nicht aufführen. -->

| Einstellung | Standard | Bedeutung |
|---|---|---|
| ‹Feld› | ‹Wert› | ‹Erklärung› |

## Sicherheit und Datenschutz
<!-- Welche Verbindungen das Tool aufbaut (wohin, welches Protokoll), welche Rechte es braucht,
     was es speichert (Einstellungen, Tresor, tool_data), ob es etwas verändert oder nur liest. -->

## Grenzen und bekannte Einschränkungen

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| ‹Meldung oder Verhalten› | ‹Lösung› |

## Versionen
<!-- Neueste zuerst, eine Zeile je Version mit den wichtigsten Änderungen. -->
| Version | Änderungen |
|---|---|
| ‹X.Y.Z› | ‹Änderungen› |

## Siehe auch
- ‹verwandte Seiten›
````
