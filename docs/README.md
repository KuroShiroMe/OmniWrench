# docs/ – interne Entwicklerunterlagen

Dieser Ordner ist für die Entwicklung von OmniWrench selbst gedacht (Stef und Claude).
**Anleitungen für Anwender und für Tool-Entwickler stehen im Wiki:**

| Thema | Wiki |
|---|---|
| Programm, Installation, Bedienung, Einstellungen, Tresor | [Wiki-Startseite](https://github.com/KuroShiroMe/OmniWrench/wiki) |
| Alle Tools im Detail | [Tools](https://github.com/KuroShiroMe/OmniWrench/wiki/Tools) |
| Eigene Tools entwickeln, eigenes Repository, Repository einbinden | [Entwicklung](https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung) |

Die Quellen der Wiki-Seiten liegen in [`wiki/`](../wiki) und werden per Workflow **Wiki**
(`.github/workflows/wiki.yml`) ins GitHub-Wiki übertragen. Seiten nur dort ändern, nicht im Wiki-Editor.
Regeln und Vorlagen: [`wiki/Entwicklung-Wiki-Seiten.md`](../wiki/Entwicklung-Wiki-Seiten.md),
[`wiki/Vorlage-Tool-Seite.md`](../wiki/Vorlage-Tool-Seite.md).

## Inhalt

| Datei | Wofür |
|---|---|
| [`ai/`](ai) | Projektgedächtnis: Entscheidungen, Architektur, Verlauf, Backlog, Stolperfallen |
| [`TESTLISTE.md`](TESTLISTE.md) | offene Tests unter Windows |
| [`TOOL_ENTWICKLUNG.md`](TOOL_ENTWICKLUNG.md) | technische Referenz zum Paketformat und SDK (Grundlage der Wiki-Seiten „Entwicklung-…“) |
| [`EXE_BUILD.md`](EXE_BUILD.md) | EXE und Installationspakete bauen |
| [`EXE_SIGNIEREN.md`](EXE_SIGNIEREN.md) | Signieren der EXE (zurückgestellt) |

Die Vorlage für fremde Tool-Repositories liegt in [`templates/tool-repo/`](../templates/tool-repo)
(siehe [`templates/README.md`](../templates/README.md)).
