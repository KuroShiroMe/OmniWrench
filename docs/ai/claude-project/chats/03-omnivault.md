# Chat: OmniVault

**Tool:** `sec.omnivault` – Ordner `tools/omnivault/` (früher „Password Manager Manager“)
Eingebauter Passwortmanager + Konnektoren zu externen Managern. Konnektor-Typen in `connector_types.json`
(Felder, `show_if`, Auswahlfelder, PowerShell-Skripte), Logik in `connectors.py`, Startup-Hook registriert die
Konnektoren beim Hauptprogramm.

**Status der Konnektoren:**
- KeePass (pykeepass): getestet mit Testdatenbank.
- Microsoft SecretManagement: nicht live getestet (Modul war nicht installiert).
- Netwrix Password Secure: Skripte nach der offiziellen API-Doku
  (https://help.passwordsafe.de/api/v9/html/e113b193-3482-8477-c479-6cf97ecbf796.htm) geschrieben:
  Login per API-Schlüssel oder Passwort-Ablauf (StartNewAuthentication/StartLogin/GetNextRequirement/Authenticate),
  Suche über GetContainerList + PsrListFilterGroupContent, Abruf über GetContainer + DecryptContainerItem.
  Noch nicht gegen ein echtes System getestet.

**Kern im Hauptprogramm:** `omniwrench/core/credentials.py`, `omniwrench/ui/credentials.py`

## Start-Prompt

```text
In diesem Chat geht es um das Tool "OmniVault" (tools/omnivault/) und den Passwortmanager-Kern von OmniWrench.
Lies CLAUDE.md, docs/ai/decisions.md (Abschnitt Password Manager Manager/OmniVault), docs/ai/architecture.md
(credentials) und tools/omnivault/connector_types.json. Fasse den Stand der drei Konnektoren zusammen.
Warte dann auf meine Aufgabe.
```
