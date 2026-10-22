# Testliste Windows (Stand main, 2026-10-22)

Alle offenen Windows-Tests aus Threads, Issues und `docs/ai/backlog.md` an einer Stelle, nach Bereich und Tool
geordnet. Alles hier ist bisher nur unter Linux, mit Attrappen (Fake-DLL, Fake-CLI) oder im CI-Starttest geprüft.
Erledigte Punkte abhaken; Fehler mit Screenshot oder Logdatei melden.

Tool-Versionen im Store: AD User Lookup 1.3.3, IconForge 1.1.3, MS DHCP Extended Management 1.2.1,
NetProbe 1.2.2, Subnetzrechner 1.2.3, OmniVault 1.1.3. App-Version 0.6.0.

## 0. Vorbereitung

```powershell
git checkout main
git pull
.\.venv\Scripts\python -m pip install -U -r requirements.txt
.\.venv\Scripts\python main.py
```

- Für Abschnitt 2 (Tool-Updates) das **normale Profil** verwenden: Dort sind ältere Tool-Versionen installiert,
  also gibt es echte Updates.
- Für Abschnitt 3 (Passwort zurücksetzen) besser einen **Testordner** verwenden, damit der echte Tresor unberührt
  bleibt: `$env:OMNIWRENCH_HOME = "$env:TEMP\OmniWrench-Test"` (gilt nur für dieses PowerShell-Fenster).
- Logs: Unterordner `logs` im Testordner bzw. `%LOCALAPPDATA%\DarkMatter\OmniWrench\logs`.

## 1. Hauptprogramm

**Neuer GitHub-Name (PR #48)**
- [ ] Nach dem ersten Start: Einstellungen › Updates bzw. Store-Quellen zeigen `KuroShiroMe/OmniWrench`
      (gespeicherte `Steffi-Tech`-Adressen werden beim Laden automatisch umgeschrieben).
- [ ] „Nach Updates suchen“ für das Hauptprogramm läuft ohne Fehler, Store lädt den Index.

**Kategorien und Tags (PR #45)**
- [ ] Seitenleiste, Filter und Store zeigen nur noch die Hauptbereiche (keine Unterkategorien).
- [ ] Tags erscheinen in den Details auf der Startseite und auf der Store-Karte; Klick auf ein Tag sucht danach.

**Skalierung und Textbreiten (Issue #17)**
- [ ] Einstellungen › Anzeige: Skalierung ändern, Neustart annehmen; Programm startet neu (Quellcode und EXE).
- [ ] Sprachen pl und nl (und weitere neue Sprachen): keine abgeschnittenen Beschriftungen.

## 2. Tool-Updates (PR #46)

- [ ] Beim Start erscheint die Meldung mit allen Tool-Updates (Name, alte → neue Version), Knöpfe
      „Alle aktualisieren“ und „Später“. Bei „Später“ bleibt der Hinweis in der Statusleiste.
- [ ] „Alle aktualisieren (n)“ im Store und unter Einstellungen › Updates: alle Updates in einem Fenster; ein
      geöffnetes Tool wird nach Rückfrage geschlossen.
- [ ] Haken „Dieses Fenster nach Abschluss schließen“: wird sofort gemerkt, Fenster schließt nur bei Erfolg,
      lässt sich in den Optionen wieder abschalten.
- [ ] „Tools automatisch im Hintergrund aktualisieren“ einschalten, neu starten: Updates laufen ohne Fenster,
      Statusleiste meldet das Ergebnis. Besonders mit OmniVault prüfen (Tool mit Start-Hook). Geöffnete Tools und
      Updates mit neuen Voraussetzungen werden übersprungen und bleiben als Update sichtbar.

## 3. Tresor: Masterpasswort zurücksetzen (PR #47)

- [ ] Tresor mit Einträgen anlegen, ab- und wieder anmelden (dabei wird die DPAPI-Kopie ohne Passwörter angelegt).
- [ ] Anmeldung › „Passwort vergessen?“: neues Masterpasswort, Löschen per Haken bestätigen.
- [ ] Danach bleiben alle Einträge stehen und zeigen ❗: Passwortmanager, Auswahl, Zugangsfelder (✎ zum
      Nachtragen), geheime Tool-Einstellungen, GitHub-Token, OmniVault-Konnektorliste.
- [ ] Passwort nachtragen: ❗ verschwindet, Eintrag liefert wieder Zugangsdaten.
- [ ] Die alte Tresordatei liegt als Sicherung daneben.
- [ ] Optional: mit einem anderen Windows-Konto ist der Passwortmanager nach dem Zurücksetzen leer (gewollt).

## 4. EXE-Build (Issue #18)

`.\.venv\Scripts\python scripts\build_exe.py --zip`, dann `.\dist\OmniWrench\OmniWrench.exe`
(oder Artefakt `OmniWrench-win64` aus GitHub › Actions › EXE-Build).
- [ ] Start ohne installiertes Python, Symbol und Versionsinfo.
- [ ] Anmeldung mit Smartcard.
- [ ] Tool-Installation inkl. pip (OmniVault/pykeepass über `OmniWrench.exe --pip`).
- [ ] Selbst-Update aus dem `-win64.zip`.
- [ ] UAC-Voraussetzungen (z. B. AD User Lookup mit RSAT).

## 5. MS DHCP Extended Management (net.ms-dhcp-extended 1.2.1)

Vorher ein altes `net.scopekeeper` von Hand deinstallieren. Nur mit Fake-DLL getestet, Zugriff direkt über
dhcpsapi.dll.
- [ ] Anmeldung mit angemeldetem Benutzer, mit Tresor-Zugangsdaten und mit manuellen Anmeldedaten; „Aus AD laden“.
- [ ] Rechte-Erkennung: Konto nur in „DHCP-Benutzer“ ergibt „Nur Lesezugriff“ (Änderungsknöpfe ausgeblendet),
      Admin-Konto ergibt Vollzugriff. Auch für den Partner prüfen.
- [ ] Failover: Beziehungen aufklappen, beide Server mit Rolle, Anteil und Status; Scopes je Server inkl. Scopes
      außerhalb der Beziehung; Anlegen, Ändern, Scopes aufnehmen/entfernen, Löschen.
- [ ] Server-Optionen je Server (lokal und Partner): nur Optionen des gewählten Servers, Abgleichstatus,
      Übertragen je Option, Haken „Auf Partner übertragen“, Entfernen auf beiden Servern.
- [ ] Replikation von Scopes auf den Partner per netsh, auch wenn der Partner nur per RPC erreichbar ist.
- [ ] Scope-Tab: Bereiche, Optionen inkl. Binär- und Herstellerklassen, Reservierungen (Namen, MAC-Format), Leases,
      DNS-Einstellungen, Speichern; neuer Scope und Duplikat.
- [ ] Serverprüfung: Geschwindigkeit (ggf. Thread-Anzahl anpassen), Abbrechen, automatische Prüfung nach der
      Anmeldung, Spalte „Höchster Befund“.
- [ ] Definitionen: nur mit Expertenmodus sichtbar, Entsperren, Anlegen/Bearbeiten/Löschen.

## 6. NetProbe (net.netprobe 1.2.2)

- [ ] Ping über IcmpSendEcho (Aufwärmen, 2 s Timeout): kein Paketverlust, wo CMD-Ping keinen hat.
- [ ] Gespeicherte Liste, aufklappbare Netzgruppen (x/y Hosts), erneut testen an Ort und Stelle, Kontextmenü
      (Wiederholen, Löschen, PDF-Export), Testvorlagen-Auswahl, Reiter Steckbrief/Konnektivität.
- [ ] DNS-Best-Practice-Befunde (CAA, MTA-STS, TLS-RPT) gegen echtes DNS.
- [ ] PDF-Export.
- [ ] Leitungstest zwischen zwei Rechnern (NetProbe ↔ NetProbe oder exportiertes `linkagent`): Bind auf 0.0.0.0,
      Firewall-Freigabe für den Port, echte Latenz- und Durchsatzwerte.

## 7. OmniVault-Konnektoren (OmniVault 1.1.3)

Nur testen, was verfügbar ist. Nach bestätigtem Test wird der Alpha-Hinweis des Konnektors entfernt.
- [ ] KeePass mit einer echten .kdbx-Datei (Issue #23).
- [ ] PowerShell SecretManagement live (Issue #23).
- [ ] Bitwarden: `bw login`/`unlock` mit Vaultwarden und bitwarden.com, winget-Pfad erkannt (Issue #19).
- [ ] 1Password: Dienstkonto, Desktop-App-Integration, verdeckte Werte ohne `--reveal`, winget-Pfad (Issue #20).
- [ ] HashiCorp Vault: Token, userpass, LDAP, AppRole (Issue #21).
- Netwrix (Issue #22) bleibt blockiert, solange keine Enterprise-Pro-Lizenz verfügbar ist.

## 8. IconForge (1.1.3)

- [ ] Schmale Kopfzeile bei kleiner Fensterbreite und 150–200 % Skalierung (Issue #17).

## Kein Test, nur Einstellung

- [ ] GitHub › Settings › Branches: CI-Prüfungen für `main` als Pflicht markieren (Issue #24).
- [ ] Projekteinstellungen in claude.ai: Repository `KuroShiroMe/OmniWrench` statt `Steffi-Tech/OmniWrench` eintragen.
