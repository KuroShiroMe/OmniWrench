# Chat: AD Benutzerabfrage

**Tool:** `ms.ad-user-lookup` – Ordner `tools/ad_user_lookup/`
Sucht AD-Benutzer über das PowerShell-Modul ActiveDirectory (RSAT als Voraussetzung, `check()` überspringt die
Installation, wenn RSAT vorhanden ist). Zugangsdaten-Auswahl (mehrere Einträge, Abruf erst bei der Suche)
direkt in der Oberfläche.

**Wichtige Dateien:** `tool.json` (requirements.windows_capabilities), `install.py`, `tool.py` (SEARCH_SCRIPT,
CredentialField), `locales/*.json`

## Start-Prompt

```text
In diesem Chat geht es um das Tool "AD Benutzerabfrage" (tools/ad_user_lookup/) von OmniWrench.
Lies CLAUDE.md, docs/ai/decisions.md (Tool-Paketformat, Password Manager) und docs/TOOL_ENTWICKLUNG.md
(Abschnitt Zugangsdaten). Beschreibe kurz Aufbau und Datenfluss (Suche, Zugangsdaten, PowerShell).
Warte dann auf meine Aufgabe.
```
