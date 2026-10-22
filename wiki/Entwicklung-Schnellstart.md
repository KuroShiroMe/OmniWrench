# Schnellstart: das erste eigene Tool

> **Kurz:** Repository aus der Vorlage erzeugen, in OmniWrench eintragen, Beispiel-Tool installieren, ändern,
> Version erhöhen, pushen. Fertig.

**Gilt für:** OmniWrench ab Version 0.7.0 · Voraussetzung: GitHub-Konto, Git, Python 3.14 (für lokale Tests)

## 1. Repository erzeugen

1. [OmniWrench-Tool-Template](https://github.com/KuroShiroMe/OmniWrench-Tool-Template) öffnen.
2. **Use this template › Create a new repository**, Namen wählen (z. B. `dns-tools`), öffentlich oder privat.
3. Im neuen Repository den Tab **Actions** öffnen und warten, bis „Vorlage einrichten“ grün ist (etwa eine Minute).

Danach enthält das Repository:
- `tools/dns_tools/`: ein lauffähiges Beispiel-Tool (ID `<besitzer>.dns-tools`), das Hostnamen auflöst
- `docs/Tool-dns-tools.md`: die Doku-Seite des Tools nach der Vorlage
- `store/index.json` und `store/packages/…zip`: der fertige Store
- eine README mit der Store-URL

Falls der Workflow nicht startet: unter *Actions* „Vorlage einrichten“ wählen und **Run workflow**.
Schlägt er mit „Permission denied“ fehl: *Settings › Actions › General › Workflow permissions* auf
**Read and write permissions** stellen und erneut ausführen.

## 2. In OmniWrench eintragen

1. *Extras › Einstellungen › Repositories › Hinzufügen*
2. Name: z. B. „DNS-Tools“, URL:
   ```
   https://raw.githubusercontent.com/<besitzer>/dns-tools/main/store/index.json
   ```
3. Speichern, Store öffnen (`Strg+Umschalt+S`): Das Tool erscheint unter „Sonstiges“ mit der Quelle „DNS-Tools“.
4. **Installieren** und per Doppelklick öffnen.

Private Repositories brauchen ein [GitHub-Token](Entwicklung-Repository-einbinden#private-repositories).

## 3. Lokal entwickeln

```bash
git clone https://github.com/<besitzer>/dns-tools
git clone https://github.com/KuroShiroMe/OmniWrench      # daneben, für Prüfungen und zum Testen
cd OmniWrench && python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\...
```

Den Code des Tools in `dns-tools/tools/dns_tools/tool.py` ändern. Zum Ausprobieren in OmniWrench
*Datei › Tool aus Ordner installieren …* und den Ordner `tools/dns_tools` wählen. Nach jeder Änderung denselben
Befehl erneut ausführen; Einstellungen bleiben erhalten.

## 4. Veröffentlichen

1. In `tools/dns_tools/tool.json` die `version` erhöhen (z. B. `0.1.0` → `0.2.0`).
2. Lokal prüfen: `python scripts/store.py check`
3. Committen und auf `main` pushen.

Der Workflow **Store** prüft die Pakete, baut den Store und committet ihn. OmniWrench meldet das Update beim
nächsten Start. Ohne erhöhte Version schlägt der Workflow fehl, denn installierte Clients würden die Änderung
sonst nie bekommen.

## 5. Weitere Tools

```bash
python scripts/new_tool.py --id <besitzer>.zweites-tool --name "Zweites Tool" --category network
```

legt `tools/zweites_tool/` und `docs/Tool-Zweites-Tool.md` an. Ein Repository darf beliebig viele Tools enthalten.

## Wie geht es weiter?
- [Paketformat](Entwicklung-Paketformat): alle Felder von `tool.json` und `config.json`
- [Tool-Klasse und SDK](Entwicklung-Tool-Klasse-und-SDK): was ein Tool alles nutzen kann
- [Wiki-Seiten schreiben](Entwicklung-Wiki-Seiten): die Doku-Seite ausfüllen
