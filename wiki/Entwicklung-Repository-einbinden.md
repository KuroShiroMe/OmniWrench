# Repository in OmniWrench einbinden

> **Kurz:** *Extras › Einstellungen › Repositories › Hinzufügen*, Name und URL der `index.json` eintragen.
> Danach erscheinen die Tools im Store; Updates kommen automatisch.

**Gilt für:** OmniWrench ab Version 0.7.0

## Einbinden

1. *Extras › Einstellungen* (`Strg+,`) › Reiter **Repositories**.
2. **Hinzufügen**: Haken **Aktiv**, **Name** (erscheint im Store als „Quelle“), **URL**:
   - GitHub: `https://raw.githubusercontent.com/<besitzer>/<repo>/main/store/index.json`
   - Freigabe: `\\server\freigabe\omniwrench-store\index.json`
   - Webserver: `https://intranet.contoso.local/omniwrench/index.json`
3. Speichern und den Store öffnen. Fehlermeldungen eines Repositorys stehen oben im Store.

Ein Repository lässt sich mit dem Haken **Aktiv** vorübergehend abschalten, ohne es zu löschen.

## Private Repositories

1. Auf GitHub ein Token erzeugen: *Settings › Developer settings › Personal access tokens › Fine-grained tokens*,
   Zugriff nur auf das Repository, Berechtigung **Contents: Read-only**.
2. In OmniWrench unter *Einstellungen › Updates › GitHub-Token* eintragen. Es liegt verschlüsselt im Tresor.

Das Token gilt für alle GitHub-Abrufe von OmniWrench und hebt zugleich das API-Limit an.

## Für viele Rechner verteilen

Repositories und Einstellungen liegen pro Benutzer in `settings.json` (siehe
[Datenablage](Datenablage-und-Datenschutz)). Für eine Firmenverteilung:

- **Dateifreigabe oder Intranet-Server** als Store nutzen, dann ist kein GitHub-Zugang nötig.
- Den Eintrag einmal anlegen und die Zeile aus `settings.json` (Schlüssel `repositories`) per Skript oder
  Softwareverteilung in die Profile übernehmen. Beispiel für den Eintrag:
  ```json
  "repositories": [
    {"name": "OmniWrench", "url": "https://raw.githubusercontent.com/KuroShiroMe/OmniWrench/main/store/index.json", "enabled": true},
    {"name": "Contoso", "url": "\\\\fs01\\it\\omniwrench-store\\index.json", "enabled": true}
  ]
  ```
- Der offizielle Store kann deaktiviert werden, wenn nur freigegebene Tools erlaubt sein sollen.

## Einzelne Tools ohne Repository

Für Tests oder einmalige Weitergabe: *Datei › Tool aus ZIP-Datei installieren …* oder
*Datei › Tool aus Ordner installieren …*. So installierte Tools bekommen Updates, sobald sie in einem
eingetragenen Repository mit höherer Version auftauchen.

## Siehe auch
- [Store und Tools › Repositories](Store-und-Tools#repositories)
- [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository)
