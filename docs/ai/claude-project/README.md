# Claude-Projekt „OmniWrench (DarkMatter)“ einrichten

Die AI-Dokumentation bleibt im Repository (Quelle der Wahrheit). Das claude.ai-Projekt bindet sie nur ein.

## 1. Projekt anlegen

claude.ai › **Projects** › **Create project**

- **Name:** `OmniWrench (DarkMatter)`
- **Description:** `Modulare Windows-Admin-Toolbox (Python/PySide6) – Hauptprogramm und Tools`

## 2. Projektanweisungen (Custom instructions)

Folgenden Text in *Set project instructions* einfügen:

```text
Projekt: OmniWrench von DarkMatter – modulare Windows-Admin-Toolbox (Python 3.14, PySide6, QtAds).
Repository: github.com/KuroShiroMe/OmniWrench (öffentlich). Antworte auf Deutsch.

Die Projektdateien sind das Projektgedächtnis:
- CLAUDE.md: Einstieg, Konventionen, Befehle
- docs/ai/decisions.md: verbindliche Entscheidungen und Wünsche des Nutzers
- docs/ai/architecture.md: Aufbau des Codes
- docs/ai/history.md: Verlauf der bisherigen Arbeit
- docs/ai/backlog.md: offene Punkte
- docs/ai/gotchas.md: Stolperfallen der Umgebung
- docs/TOOL_ENTWICKLUNG.md: Anleitung für Tool-Entwickler

Regeln:
- Vor Vorschlägen decisions.md beachten; nichts davon stillschweigend ändern.
- Oberflächentexte neutral formulieren (kein Duzen, kein Chat-Ton), alle Texte über Sprachdateien (8 Sprachen).
- Code-Änderungen erfolgen in Claude Code im Repository; danach docs/ai/ aktualisieren.
```

## 3. Projektwissen aus GitHub einbinden

Im Projekt › **Project knowledge** › **+ Add content** › **GitHub** › Repository `KuroShiroMe/OmniWrench` wählen und
diese Dateien/Ordner auswählen:

- `CLAUDE.md`
- `docs/ai/` (alle Dateien inkl. `claude-project/`)
- `docs/TOOL_ENTWICKLUNG.md`
- `README.md`

Die Dateien bleiben auf GitHub; über *Sync* holt das Projekt den aktuellen Stand.

## 4. Chats anlegen

Für jeden Bereich einen eigenen Chat im Projekt starten und den jeweiligen Start-Prompt als erste Nachricht senden:

| Chat | Start-Prompt |
|---|---|
| Hauptprogramm | [chats/00-hauptprogramm.md](chats/00-hauptprogramm.md) |
| Subnetzrechner | [chats/01-subnetzrechner.md](chats/01-subnetzrechner.md) |
| AD Benutzerabfrage | [chats/02-ad-benutzerabfrage.md](chats/02-ad-benutzerabfrage.md) |
| OmniVault | [chats/03-omnivault.md](chats/03-omnivault.md) |
| IconForge | [chats/04-iconforge.md](chats/04-iconforge.md) |

Für Code-Arbeit gilt dasselbe in Claude Code: neue Sitzung im Repository öffnen und den Start-Prompt verwenden –
`CLAUDE.md` wird dort automatisch geladen.
