# __REPO__

<!-- template:start -->
> **Dies ist die Vorlage für eigene OmniWrench-Tool-Repositories.** Oben **Use this template › Create a new
> repository** wählen. Der Workflow „Vorlage einrichten“ passt danach Namen und Links an, legt das erste Tool
> an und baut den Store (Tab *Actions*, dauert etwa eine Minute). Anleitung:
> [Vorlagen-Repository im OmniWrench-Wiki](https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung-Vorlagen-Repository).
<!-- template:end -->

Tool-Repository für [OmniWrench](https://github.com/KuroShiroMe/OmniWrench), das Universalwerkzeug für
Administratoren. Erstellt aus der
[OmniWrench-Tool-Vorlage](https://github.com/KuroShiroMe/OmniWrench-Tool-Template).

## In OmniWrench einbinden

In OmniWrench unter *Extras › Einstellungen › Repositories* **Hinzufügen** und diese URL eintragen:

```
https://raw.githubusercontent.com/__OWNER__/__REPO__/main/store/index.json
```

Danach stehen die Tools im **Store**. Private Repositories brauchen zusätzlich ein GitHub-Token
(*Einstellungen › Updates › GitHub-Token*).

## Tools

| Tool | Beschreibung | Anleitung |
|---|---|---|
| ‹Name› | ‹Kurzbeschreibung› | [docs/‹Seite›.md](docs/) |

## Aufbau

```
tools/<tool>/          ein Ordner je Tool (tool.json, config.json, install.py, tool.py, locales/, screenshots/)
docs/Tool-<Name>.md    Anleitung je Tool (Aufbau wie im OmniWrench-Wiki)
store/                 wird automatisch gebaut: index.json, packages/*.zip, screenshots/ (nicht von Hand ändern)
template/              Vorlage für neue Tools (scripts/new_tool.py)
scripts/store.py       Store prüfen und bauen
scripts/new_tool.py    neues Tool anlegen
scripts/screenshots.py Screenshots für Store und Home rendern
.github/workflows/     Store-Workflow (Prüfung bei Pull Requests, Bau bei Push auf main)
```

## Entwickeln

```bash
git clone https://github.com/KuroShiroMe/OmniWrench ../OmniWrench      # einmalig, für Tests und Prüfungen
python scripts/new_tool.py --id __OWNER__.mein-tool --name "Mein Tool" --category network
```

1. Tool unter `tools/<ordner>/` programmieren, Anleitung in `docs/` schreiben.
2. Testen: in OmniWrench *Datei › Tool aus Ordner installieren …* und den Tool-Ordner wählen.
3. Screenshots: `screenshots/render.py` mit Beispieldaten anpassen, Bilder in `tool.json` unter `screenshots`
   eintragen (erstes = Hauptbild) und `python scripts/screenshots.py` ausführen.
4. `version` in `tool.json` erhöhen, committen und auf `main` pushen. Der Workflow **Store** prüft alles und
   baut den Store. Installierte Clients melden das Update beim nächsten Start.

Lokal prüfen: `python scripts/store.py check` (bauen: `python scripts/store.py build`).

Vollständige Anleitung: [Entwicklerbereich im OmniWrench-Wiki](https://github.com/KuroShiroMe/OmniWrench/wiki/Entwicklung).

## Lizenz

[MIT](LICENSE)
