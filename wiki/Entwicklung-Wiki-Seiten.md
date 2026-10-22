# Wiki-Seiten schreiben

> **Kurz:** Jedes Tool hat eine vollständige Doku-Seite nach der [Vorlage: Tool-Seite](Vorlage-Tool-Seite);
> Seiten zum Hauptprogramm folgen der [Vorlage: Bereichsseite](Vorlage-Bereichsseite). Die Quellen liegen im
> Repository unter `wiki/` und werden automatisch ins GitHub-Wiki übertragen.

## Regeln

1. **Jedes Tool bekommt eine vollständige Seite**, spätestens mit dem Pull Request, der das Tool einführt.
   Jede neue Funktion, Einstellung oder geänderte Bedienung wird im selben Pull Request auf der Seite nachgetragen.
2. **Fester Aufbau.** Tool-Seiten haben genau die Abschnitte der Vorlage in derselben Reihenfolge. Was nicht
   zutrifft, bleibt mit einem Satz stehen („Keine Voraussetzungen.“).
3. **Vollständig.** Jede Funktion, jeder Knopf mit Wirkung, jede Einstellung mit Standardwert, jede Verbindung
   nach außen, jede bekannte Grenze.
4. **Für Anwender geschrieben:** Was sieht man, was kann man tun, was passiert dabei. Interna (Klassen, Module)
   gehören nicht auf Anwenderseiten, sondern in den Entwicklerbereich.
5. **Begriffe wie in der Oberfläche**, in derselben Schreibweise; Menüpfade als *Menü › Eintrag*, Knöpfe **fett**.
6. **Neutraler Ton**, kein Duzen, kurze Sätze. Deutsch.
7. **Stand angeben:** Tool-Seiten nennen die Version („Stand der Seite“), Bereichsseiten „Gilt für: ab Version …“.
8. **Verlinken statt wiederholen:** Allgemeines (Tresor, Passwortmanager, Store) verlinken.

## Dateien und Namen

| Was | Datei in `wiki/` | Seitenname im Wiki |
|---|---|---|
| Startseite | `Home.md` | Home |
| Seitenleiste / Fußzeile | `_Sidebar.md`, `_Footer.md` | – |
| Bereich des Hauptprogramms | `Einstellungen.md` | Einstellungen |
| Tool | `Tool-<Anzeigename mit Bindestrichen>.md` | Tool-NetProbe |
| Entwicklerbereich | `Entwicklung-<Thema>.md` | Entwicklung-Paketformat |
| Vorlagen | `Vorlage-<Art>.md` | Vorlage-Tool-Seite |
| Bilder | `images/<seite>-<inhalt>.png` | – |

- Dateinamen ohne Umlaute und Leerzeichen (`Veroeffentlichen`), damit Links überall funktionieren.
- Links zwischen Seiten: `[Text](Seitenname)` bzw. `[Text](Seitenname#abschnitt)`.
- Bilder: `![Beschreibung](images/datei.png)`, PNG, Breite höchstens 1600 px, dunkles Farbschema, keine echten
  Server- oder Benutzernamen.
- Neue Seiten in `_Sidebar.md` und auf der passenden Übersicht (`Home.md`, `Tools.md`, `Entwicklung.md`) eintragen.
- `homepage` in der `tool.json` zeigt auf die Tool-Seite: `https://github.com/KuroShiroMe/OmniWrench/wiki/Tool-<Name>`.

## Abgleich ins Wiki

Der Workflow **Wiki** (`.github/workflows/wiki.yml`) überträgt bei jedem Push auf `main`, der `wiki/` ändert,
den Ordnerinhalt ins GitHub-Wiki (`OmniWrench.wiki.git`). Das Wiki ist damit ein Spiegel:

- Änderungen nur im Repository per Pull Request, nicht im Wiki-Editor (würden überschrieben).
- Gelöschte Dateien verschwinden auch im Wiki.
- Lokale Vorschau: Markdown-Vorschau des Editors; Links ohne `.md` funktionieren dort nicht, im Wiki schon.

## Tools im offiziellen Repository

Für Tools in `KuroShiroMe/OmniWrench` gilt zusätzlich:

- Seitenname exakt `Tool-<Anzeigename, Leerzeichen als Bindestrich>`; `homepage` in der `tool.json` zeigt darauf.
- Die Landing Page [kuroshiro.me](https://kuroshiro.me) (Ordner `site/`) listet die Tools nach Bereichen und
  verlinkt auf diese Wiki-Seiten. Ein Pull Request mit neuem Tool oder neuer Hauptfunktion prüft, ob die
  Landing Page ergänzt werden muss.
- Neue Seite in `Tools.md` (richtiger Bereich), `_Sidebar.md` und `Home.md` eintragen.

## Tools aus anderen Repositories

Tools aus eigenen Repositories dokumentieren sich in ihrem Repository unter `docs/Tool-<Name>.md`, im selben
Aufbau (die [Vorlage](Entwicklung-Vorlagen-Repository) legt die Seite an). `homepage` in der `tool.json` zeigt
dann auf diese Datei.

## Siehe auch
- [Vorlage: Tool-Seite](Vorlage-Tool-Seite)
- [Vorlage: Bereichsseite](Vorlage-Bereichsseite)
