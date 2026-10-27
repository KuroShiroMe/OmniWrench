# Vorlagen-Repository

> **Kurz:** [OmniWrench-Tool-Template](https://github.com/KuroShiroMe/OmniWrench-Tool-Template) ist ein
> GitHub-Vorlagen-Repository. **Use this template** erzeugt ein eigenes Tool-Repository, das sich per Workflow
> selbst einrichtet: Namen und Links, ein lauffähiges Beispiel-Tool, Doku-Seite und fertiger Store.

**Gilt für:** OmniWrench ab Version 0.7.0

## Inhalt
- [Repository erzeugen](#repository-erzeugen)
- [Was die Einrichtung macht](#was-die-einrichtung-macht)
- [Inhalt der Vorlage](#inhalt-der-vorlage)
- [Workflow „Store“](#workflow-store)
- [Skripte](#skripte)
- [Häufige Fragen](#häufige-fragen)

## Repository erzeugen

1. [OmniWrench-Tool-Template](https://github.com/KuroShiroMe/OmniWrench-Tool-Template) öffnen.
2. **Use this template › Create a new repository**.
3. Besitzer und Namen wählen, z. B. `contoso/omniwrench-tools`; öffentlich oder privat.
4. **Create repository**. Im Tab **Actions** läuft „Vorlage einrichten“ (etwa eine Minute).

Danach ist das Repository fertig. Die Store-URL steht in der README.

## Was die Einrichtung macht

Der Workflow „Vorlage einrichten“ läuft einmal beim ersten Push:

1. ersetzt die Platzhalter in README, LICENSE und Doku durch Besitzer, Repository-Name und Jahr
2. legt das erste Tool an: Ordner `tools/<repo>/`, ID `<besitzer>.<repo>`, Name = Repository-Name,
   `homepage` zeigt auf die Doku-Seite
3. legt `docs/Tool-<Name>.md` aus der Vorlage für Tool-Seiten an
4. baut den Store (`store/index.json`, `store/packages/…zip`), Name „‹repo› Store“
5. löscht die Markierung `.github/template-setup.json` und committet alles

Startet der Workflow nicht, unter *Actions* „Vorlage einrichten“ wählen und **Run workflow** drücken. Meldet er
„Permission denied“, unter *Settings › Actions › General › Workflow permissions* **Read and write permissions**
einstellen und erneut ausführen.

## Inhalt der Vorlage

```
.github/
  template-setup.json      Markierung für die Einrichtung (danach gelöscht)
  workflows/setup.yml      „Vorlage einrichten“
  workflows/store.yml      „Store“: prüfen und bauen
template/
  tool/                    Gerüst für neue Tools (Platzhalter __TOOL_ID__, __TOOL_NAME__ …)
  Tool-Seite.md            Gerüst für die Doku-Seite
scripts/
  store.py                 Store prüfen und bauen
  new_tool.py              neues Tool anlegen
  screenshots.py           Screenshots für Store und Home rendern
  setup_repo.py            Einrichtung (vom Workflow genutzt)
tools/                     die Tools
docs/                      die Doku-Seiten
README.md, LICENSE (MIT), .gitignore, .gitattributes
```

Das Beispiel-Tool löst einen Hostnamen auf und zeigt die Adressen. Es enthält alle Bausteine eines echten Tools:
`tool.json` mit Bereich, Tags, Symbol und Plattformen, `config.json` mit zwei Einstellungen, `install.py`,
Sprachdateien `en.json`/`de.json`, Arbeit im Hintergrund mit `run_async`, eine Meldung in der Statusleiste und
einen Screenshot samt `screenshots/render.py` (siehe [Screenshots](Entwicklung-Paketformat#screenshots)).

## Workflow „Store“

| Auslöser | Was passiert |
|---|---|
| Pull Request | Python kompilieren, Sprachdateien prüfen, Pakete prüfen (inkl. Versionsprüfung) |
| Push auf `main` (Änderungen in `tools/`) | dasselbe, dann Store bauen und als „Store neu gebaut“ committen |
| manuell (*Run workflow*) | wie Push |

Für die Prüfungen checkt der Workflow den aktuellen OmniWrench-Quellcode aus (`.omniwrench/`). Schlägt er fehl,
steht der Grund im Protokoll, z. B. „geändert, aber Version 1.0.0 nicht erhöht“.

## Skripte

Lokal brauchen die Skripte den OmniWrench-Quellcode, z. B. als Nachbarordner
(`git clone https://github.com/KuroShiroMe/OmniWrench ../OmniWrench`), oder die Umgebungsvariable
`OMNIWRENCH_SRC`.

```bash
python scripts/new_tool.py --id contoso.gpo-report --name "GPO Report" --category identity
python scripts/screenshots.py            # braucht PySide6 + PySide6-QtAds (requirements.txt von OmniWrench)
python scripts/store.py check
python scripts/store.py build
```

| Skript | Parameter |
|---|---|
| `new_tool.py` | `--id` (Pflicht), `--name` (Pflicht), `--category` (Standard `other`), `--folder`, `--author` |
| `screenshots.py` | Tool-Ordner (Standard: alle mit `screenshots/render.py`), `--lang` (Standard `en`), `--theme` (`dark`/`light`), `--omniwrench PFAD` |
| `store.py` | `check` oder `build`, `--name` (Anzeigename des Stores), `--omniwrench PFAD` |

## Häufige Fragen

**Kann ich das Repository auch ohne Vorlage aufbauen?**
Ja, siehe [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository). Die Vorlage spart nur Arbeit.

**Bekomme ich Verbesserungen der Vorlage automatisch?**
Nein, ein aus einer Vorlage erzeugtes Repository ist unabhängig. Neue Versionen von `scripts/store.py`,
`scripts/screenshots.py` und `.github/workflows/store.yml` lassen sich aus der Vorlage herüberkopieren.

**Muss das Repository öffentlich sein?**
Nein. Private Repositories funktionieren, jeder Client braucht dann ein GitHub-Token
([Repository einbinden](Entwicklung-Repository-einbinden#private-repositories)).

## Siehe auch
- [Schnellstart](Entwicklung-Schnellstart)
- [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository)
