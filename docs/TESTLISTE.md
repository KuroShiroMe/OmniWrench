# Testliste Windows (Stand main, 2026-10-22)

Alle offenen Windows-Tests aus Threads, Issues und `docs/ai/backlog.md` an einer Stelle, nach Bereich und Tool
geordnet. Alles hier ist bisher nur unter Linux, mit Attrappen (Fake-DLL, Fake-CLI) oder im CI-Starttest geprüft.
Erledigte Punkte abhaken; Fehler mit Screenshot oder Logdatei melden.

Tool-Versionen im Store: AD User Lookup 1.3.4, IconForge 1.1.5, MS DHCP Extended Management 1.4.2,
NetProbe 1.2.4, Subnetzrechner 1.2.5, OmniVault 1.1.5. App-Version 0.7.0.

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
- Logs: Unterordner `logs` im Testordner bzw. `%LOCALAPPDATA%\KuroShiro\OmniWrench\logs`.

## 1. Hauptprogramm

**Neuer Herstellername KuroShiro (vorher DarkMatter)**
- [ ] Erster Start aus `main`: `%APPDATA%\DarkMatter\OmniWrench` und `%LOCALAPPDATA%\DarkMatter\OmniWrench` sind nach
      `…\KuroShiro\OmniWrench` verschoben, der leere Ordner `DarkMatter` ist weg. Anmeldung mit dem bisherigen Tresor
      klappt, installierte Tools, Einstellungen und Layout sind da. Das Log nennt „Daten übernommen: …“.
- [ ] Store-Quelle heißt „KuroShiro Store“, Info-Dialog und Anmeldefenster zeigen „KuroShiro“.
- [ ] Nach dem nächsten Release: Update einer Installation aus `C:\Program Files\DarkMatter\OmniWrench` über
      *Nach Updates suchen*. Danach liegt das Programm in `C:\Program Files\KuroShiro\OmniWrench`, der alte Ordner
      ist weg, Startmenü-Eintrag und Deinstallation unter *Apps* zeigen auf den neuen Ort.

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
(oder Artefakt `OmniWrench-windows` aus GitHub › Actions › Build, oder die ZIP aus dem Release 0.7.0).
- [ ] Start ohne installiertes Python, Symbol und Versionsinfo.
- [ ] Anmeldung mit Smartcard.
- [ ] Tool-Installation inkl. pip (OmniVault/pykeepass über `OmniWrench.exe --pip`).
- [ ] Selbst-Update aus dem `-win64.zip`.
- [ ] UAC-Voraussetzungen (z. B. AD User Lookup mit RSAT).

## 4a. Installationsprogramm und Updates (0.7.0)

Dateien aus dem Release 0.7.0. Die CI installiert das Setup bereits still, startet und deinstalliert es;
offen sind der Assistent, die Verknüpfungen und das Update mit echter UAC-Abfrage.
- [ ] `OmniWrench-0.7.0-win64-setup.exe`: Assistent auf Deutsch, UAC-Abfrage, Ziel
      `C:\Program Files\KuroShiro\OmniWrench`, Startmenü-Eintrag, optional Desktop-Verknüpfung, Start am Ende.
- [ ] Nach der Installation: Einstellungen, Tresor und Tools der bisherigen portablen Version sind da
      (gleiche Daten in `%APPDATA%`/`%LOCALAPPDATA%`). Taskleisten-Symbol und Anheften passen.
- [ ] Setup erneut starten, während OmniWrench läuft: Meldung „wird noch ausgeführt“ mit Wiederholen/Abbrechen.
- [ ] Update der installierten Version (erst mit einem späteren Release möglich, z. B. 0.7.1): „Jetzt installieren“
      zeigt die UAC-Abfrage, das Setup läuft mit Fortschrittsfenster, OmniWrench startet danach von selbst und
      **ohne** Adminrechte.
- [ ] Portable Version in einem schreibgeschützten Ordner (z. B. von Hand nach `C:\Program Files\…` kopiert):
      Update fragt per UAC und startet danach neu. In einem normalen Ordner wie bisher ohne UAC.
- [ ] Deinstallation unter *Einstellungen › Apps*: Programmordner weg, Benutzerdaten bleiben.
- [ ] Optional: Ordner `portable-data` neben der portablen `OmniWrench.exe` anlegen -> Daten landen dort (leerer Tresor).
- [ ] Optional Linux (Ubuntu/Debian/Mint): `sudo apt install ./omniwrench_0.7.0_amd64.deb`, Start über das Menü,
      Tool-Store zeigt AD/DHCP mit „Läuft nur unter Windows“; portable `tar.gz` entpacken und starten.

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

**1.3.0: Adresspool und Abgleich mit dem Partner** (Fehler 0x4EA4 von rz-dhcp01, nur mit Fake-DLL getestet) – getestet (Stef 2026-10-23)
- [x] Failover-Scope, Pool **verkleinern** (z. B. Ende -10) und **vergrößern**: Speichern klappt ohne 0x4EA4,
      die DHCP-Konsole zeigt den neuen Bereich, Ausschlüsse und Leases sind unverändert.
- [x] Failover-Scope, Pool **verschieben** (neuer Start hinter altem Start und neues Ende hinter altem Ende):
      klappt in zwei Schritten (erst erweitern, dann kürzen).
- [x] Danach Replikation (automatisch oder „Replizieren“): Partner hat denselben Pool; Protokoll zeigt
      `add iprange` (bei Verschiebung zweimal).
- [x] Pool so ändern, dass ein Ausschluss außerhalb liegt: Rückfrage nennt den Ausschluss, er wird entfernt.
- [x] Fehlerfall (z. B. Richtlinie mit IP-Bereich im Scope und Pool verkleinern): verständliche Meldung, Pool und
      Ausschlüsse bleiben wie vorher.
- [x] Prüfung mit „Mit Partnern abgleichen“: Der zusätzliche Ausschluss auf rz-dhcp02 erscheint als „Ausschlüsse nur
      auf rz-dhcp02, nicht hier“ (Kategorie „Abgleich mit Partner“), ebenso im Scope-Tab mit „Jetzt replizieren“.
      Nach der Replikation ist der Befund im Scope-Tab weg, nach erneuter Prüfung auch in der Liste.
- [x] Keine Fehlalarme bei synchronen Scopes (Optionen, Reservierungen, Lease, Status); falls doch: Befundtext und
      beide Werte melden.
- [x] Serverbefunde zur Beziehung: Lastverteilung, MCLT, Authentifizierung und Scope-Liste werden bei gleichen
      Einstellungen nicht gemeldet; Klassen nur bei echten Unterschieden.
- [x] Neuer Scope und Duplikat: Pool-Felder, „Ganzes Netz“, beim Duplikat werden die Ausschlüsse der Quelle angelegt.

**1.3.0: Automatische Rücknahme bei Fehlern** (Transaktionen, nur mit Fake-Server getestet – bitte an einem Test-Scope) – getestet (Stef 2026-10-23)
- [x] Pool verkleinern, sodass ein Ausschluss wegfällt, und einen Fehler provozieren (z. B. Richtlinie mit IP-Bereich
      im Scope): Meldung „… Alle 1 bereits durchgeführten Änderungen wurden zurückgenommen“, der Ausschluss ist
      wieder da. Protokoll zeigt „Fehler bei „Scope … speichern“ – nehme 1 Änderungen zurück“ und „↶ …“.
- [x] Reservierungen einfügen mit „Überschreiben“, eine davon ungültig (z. B. IP schon als Reservierung in anderem
      Scope): keine Reservierung geändert, die überschriebenen sind unverändert da.
- [x] Mehrere Optionen entfernen, während der Server kurz nicht erreichbar ist (oder Nur-Lese-Konto): alle Optionen
      bleiben bzw. kommen zurück.
- [x] Neuer Scope mit Failover und Replikation, Partner absichtlich nicht erreichbar: Scope wird wieder entfernt,
      lokal und beim Partner bleibt nichts übrig.
- [x] Failover-Scope löschen, Fehler beim Löschen (z. B. Scope während des Löschens in der Konsole geöffnet/gesperrt):
      Scope ist wieder in der Beziehung und auf dem Partner vorhanden.
- [x] Während einer langen Aktion „Abbrechen“: Hinweis „Die Aktion wurde abgebrochen …“, Stand wie vorher.
- [x] Rücknahme nach gelöschter Failover-Beziehung: Beziehung ist wieder da; gemeinsamen Schlüssel prüfen bzw. neu
      setzen (lässt sich nicht wiederherstellen).

**1.4.0: Änderungen anderer erkennen** (nur mit Fake-Daten getestet – Testumgebung mit zwei Sitzungen bzw. DHCP-Konsole) – getestet (Stef 2026-10-23)
- [x] Scope im Tool öffnen, in der DHCP-Konsole eine Option ändern, im Tool eine andere Option speichern:
      Meldung „Auf dem Server geändert“ mit der Änderung aus der Konsole; nichts geschrieben.
- [x] Dieselbe Meldung nennt unter „Laut Ereignisprotokoll“ Uhrzeit, Konto und Text der Konsolen-Änderung.
      Falls stattdessen „Wer … nicht bekannt“: Protokollzeile „Ereignisprotokoll … nicht lesbar“ mit Fehler melden.
- [x] „Neu laden (Eingaben behalten)“: Konsolen-Änderung ist sichtbar, eigene Eingabe (z. B. Name) steht noch da;
      erneut speichern klappt ohne Meldung. „Trotzdem speichern“ schreibt; „Abbrechen“ ändert nichts.
- [x] Oben „Aktualisieren: jede Minute“ einstellen, in der Konsole Reservierung anlegen: spätestens nach einer
      Minute zeigt der Scope-Tab den Balken „Auf dem Server geändert und neu geladen“, Reservierung ist da, das
      Protokoll zeigt „Änderung am Server (…, Konto): …“. Die Oberfläche bleibt dabei bedienbar.
- [x] Wie oben, aber vorher im Tab den Namen ändern (nicht speichern): kein automatisches Neuladen, Balken mit
      „Neu laden“; danach Name noch geändert, Reservierung da.
- [x] Übersicht/Failover/Server-Optionen: Scope in der Konsole anlegen bzw. Server-Option ändern → nach der
      nächsten Runde sichtbar. Server-Option im Tool ändern, nachdem sie in der Konsole geändert wurde → Meldung.
- [x] Server kurz nicht erreichbar (Netz trennen): eine Protokollzeile „Automatische Aktualisierung fehlgeschlagen“,
      keine wiederholten Fehlerfenster.
- [x] Einstellung „Automatisch aktualisieren“ in den Tool-Einstellungen und Auswahl oben bleiben synchron.

**1.4.1: Seite „Ereignisprotokoll“** – getestet (Stef 2026-10-23)
- [x] Seite öffnen: lädt automatisch die letzten 24 Stunden. Konsolen-Änderungen (Option, Reservierung, Ausschluss,
      Scope, Failover) erscheinen mit Konto; Bereich/Aktion/Scope/Objekt passen zur Meldung (sonst Meldungstext
      und Ereignis-ID melden, damit die Lesehilfe nachgeschärft werden kann).
- [x] Ereignis anklicken: Details mit SID, Ereignisdaten und Hinweis; Doppelklick öffnet den Scope.
- [x] Zeitraum, Bereich und Suche filtern; Server auf den Partner umstellen und laden.
- [x] Konto ohne „Ereignisprotokollleser“: gelber Hinweis „fehlt das Leserecht“ mit Link; Link öffnet die Wiki-
      Anleitung. Nach Aufnahme in die Gruppe (ggf. ab-/anmelden) „Laden“ → Ereignisse da.
- [x] Firewall-Regel „Remote-Ereignisprotokollverwaltung“ aus: Hinweis „nicht erreichbar … Firewall“.
- [x] Wiki-Anleitung „Ereignisprotokoll einrichten“ einmal durchspielen (Befehle korrekt?).
- [x] Mit Auto-Refresh: neue Konsolen-Änderung erscheint ohne „Laden“ oben in der Liste.

**1.4.2: Ereignisprotokoll im Hintergrund**
- [ ] Zeitraum „30 Tage“ laden: Während „Lese Ereignisprotokoll …“ unten steht, lassen sich andere Seiten und Scopes
      bedienen (kein gesperrtes Fenster); danach erscheinen die Einträge.
- [ ] Während des Ladens abmelden: kein Fehler, nach erneuter Anmeldung ist die Liste leer bzw. lädt neu.

**1.5.0: IPv6 (DHCPv6)** – Server mit mindestens einem DHCPv6-Scope (gern Testserver)
- [ ] Umschalter **IPv6** oben links: Übersicht zeigt die v6-Scopes (Präfix, Status, Gültige Dauer); Server-Optionen und
      Definitionen zeigen die DHCPv6-Werte. Tool schließen und öffnen → Auswahl bleibt erhalten.
- [ ] v6-Scope öffnen: Werte wie in der DHCP-Konsole (Name, Preference, bevorzugte/gültige Dauer, Status, Rapid Commit,
      Unicast). Name, Beschreibung, beide Dauern ändern, speichern → in der Konsole sichtbar.
- [ ] Bevorzugte Dauer ≥ gültige Dauer eingeben → Fehler, Speichern gesperrt.
- [ ] Option 23 (DNS-Server) und 24 (Domänensuchliste) im Scope und als Server-Option setzen, ändern, entfernen.
- [ ] Reservierung anlegen (DUID und IAID von einem echten Client, z. B. `ipconfig /all` bzw. Lease), Name/Beschreibung
      ändern, entfernen. Hinweis im Protokoll, falls der Name nicht gesetzt werden konnte?
- [ ] Ausschluss hinzufügen und entfernen; Lease löschen.
- [ ] Neuer v6-Scope … (inaktiv anlegen), danach **Duplizieren …** mit anderem Präfix: Optionen und Ausschlüsse
      umgerechnet, Tab öffnet sich. Aktivieren/Deaktivieren und Löschen aus der Übersicht.
- [ ] Konflikt: v6-Scope im Tool ändern, vorher in der Konsole den Namen ändern → Meldung mit Unterschied.
- [ ] Optionen/Reservierungen eines v6-Scopes kopieren und in einen anderen v6-Scope einfügen; in einen IPv4-Scope
      einfügen → Ablehnung.
- [ ] Definitionen (Expertenmodus) unter IPv6: neue Definition anlegen und löschen.
- [ ] Prüfung: v6-Scopes erscheinen unter „Befunde je Scope“; Ereignisprotokoll zeigt v6-Änderungen der Konsole.
- [ ] **DNS-Abgleich** ankreuzen (mit „Leases einbeziehen“), prüfen: Reservierung mit falschem/fehlendem DNS-Eintrag
      und fehlendem PTR wird gemeldet; korrekte Einträge ohne Befund.

## 6. NetProbe (net.netprobe 1.2.3)

- [ ] Ping über IcmpSendEcho (Aufwärmen, 2 s Timeout): kein Paketverlust, wo CMD-Ping keinen hat.
- [ ] Gespeicherte Liste, aufklappbare Netzgruppen (x/y Hosts), erneut testen an Ort und Stelle, Kontextmenü
      (Wiederholen, Löschen, PDF-Export), Testvorlagen-Auswahl, Reiter Steckbrief/Konnektivität.
- [ ] DNS-Best-Practice-Befunde (CAA, MTA-STS, TLS-RPT) gegen echtes DNS.
- [ ] PDF-Export.
- [ ] Leitungstest zwischen zwei Rechnern (NetProbe ↔ NetProbe oder exportiertes `linkagent`): Bind auf 0.0.0.0,
      Firewall-Freigabe für den Port, echte Latenz- und Durchsatzwerte.

## 7. OmniVault-Konnektoren (OmniVault 1.1.4)

Nur testen, was verfügbar ist. Nach bestätigtem Test wird der Alpha-Hinweis des Konnektors entfernt.
- [ ] KeePass mit einer echten .kdbx-Datei (Issue #23).
- [ ] PowerShell SecretManagement live (Issue #23).
- [ ] Bitwarden: `bw login`/`unlock` mit Vaultwarden und bitwarden.com, winget-Pfad erkannt (Issue #19).
- [ ] 1Password: Dienstkonto, Desktop-App-Integration, verdeckte Werte ohne `--reveal`, winget-Pfad (Issue #20).
- [ ] HashiCorp Vault: Token, userpass, LDAP, AppRole (Issue #21).
- Netwrix (Issue #22) bleibt blockiert, solange keine Enterprise-Pro-Lizenz verfügbar ist.

## 8. IconForge (1.1.4)

- [ ] Schmale Kopfzeile bei kleiner Fensterbreite und 150–200 % Skalierung (Issue #17).

## 9. MS DNS Extended Management (net.ms-dns-extended 1.0.0)

Neu, nur unter Linux mit einem Test-Backend geprüft. Zugriff über WMI (root\MicrosoftDNS).
- [ ] Installation aus dem Store: pywin32 und dnspython landen im Tool-Ordner, Tool startet ohne Fehler.
- [ ] Anmeldung an einem DC mit angemeldetem Benutzer, mit Tresor-Zugangsdaten, mit anderen Anmeldedaten; an einem
      DNS-Server außerhalb der Domäne mit `SERVER\Benutzer`; am lokalen Computer (Hinweis „andere Anmeldedaten ignoriert“).
- [ ] Fehlermeldungen verständlich: falsches Kennwort, Konto ohne DnsAdmins, Server ohne DNS-Rolle, Firewall zu.
- [ ] Weitere DNS-Server werden nach der Anmeldung verbunden (zweiter DC), Vergleich zeigt Einstellungen und Zonen.
- [ ] Zone öffnen: Einträge, Allgemein (SOA, Updates, Alterung, Übertragung), Befunde, Aufräumen plausibel.
- [ ] Eintrag anlegen: A mit PTR, AAAA mit PTR (ip6.arpa-Zone vorhanden), CNAME, MX, TXT (langer DKIM-Text), SRV, NS;
      in der DNS-Konsole kontrollieren.
- [ ] Eintrag ändern (IP und Name) mit PTR: alter PTR weg, neuer da. TTL ändern, „Statisch machen“.
- [ ] „Dynamisch“ beim Anlegen: Zeitstempel gesetzt (AgeAllRecords); Hinweis: andere Einträge desselben Namens werden
      auch dynamisch.
- [ ] Löschen mit „PTR mitlöschen“.
- [ ] Zoneneinstellungen ändern (Updates, Alterung, Übertragung/Benachrichtigung mit Serverliste) und zurück.
- [ ] Neue Zone: primär AD, primär Datei, IPv4-Reverse aus Netz, IPv6-Reverse aus /48, sekundär, Stub, bedingte
      Weiterleitung; danach löschen (Wort „löschen“).
- [ ] Zonenaktionen: Anhalten/Fortsetzen, Neu laden, Von Master übertragen, Aus AD neu laden, In Datei schreiben.
- [ ] Server: Weiterleitungen ändern, Weiterleitungen testen, Aufräumintervall, Cache leeren, Jetzt aufräumen.
- [ ] Prüfung mit Namensserver-Abfrage; Befunde plausibel, Doppelklick-Korrekturen (PTR erstellen, Eintrag löschen).
- [ ] Aufräumen-Reiter: Ping v4/v6 zeigt „antwortet“/„keine Antwort“.
- [ ] DHCP-Abgleich mit echtem DHCP-Server (gleiche und andere Anmeldung).
- [ ] Ereignisprotokoll (DNSServer/Audit): Bereich/Aktion/Zone/Objekt sinnvoll bei deutschem Server.
- [ ] Änderung in der DNS-Konsole während die Zone offen ist: automatische Aktualisierung, „Am Server geändert“ beim
      Speichern mit „wer“.
- [ ] Fehler mitten im Ablauf (z. B. PTR-Zone ohne Schreibrecht): A-Eintrag wird zurückgenommen.

### 9a. Replikation (net.ms-dns-extended 1.1.0)
- [ ] Zwei DCs verbunden, AD-Zone öffnen: Zeile „Replikation (AD-integriert) … dc02: gleich“, Spalte „Repliziert“ ✓ 2/2.
- [ ] Eintrag auf DC01 anlegen: Spalte zeigt erst 1/2 (orange), Protokoll meldet nach einiger Zeit „angekommen“.
- [ ] „Replikation anstoßen“ als Domänen-Admin: Meldung „AD-Replikation … angestoßen, Abgleiche: n“ und „Zone neu aus
      AD gelesen“; danach ✓ 2/2.
- [ ] „Replikation anstoßen“ mit Konto nur in DnsAdmins (ohne Replikationsrecht): gelbe Meldung nennt das fehlende
      Recht „Replikation synchronisieren“, Konto und Partition; „Detailansicht“ zeigt Code 8453/5. UpdateFromDS lief.
- [ ] Zone in ForestDnsZones (_msdcs): Partition wird als ForestDnsZones erkannt.
- [ ] Dateibasierte Zone mit sekundärem Server (z. B. Server ohne Domäne): beide verbinden, Seriennummer und letzte
      Übertragung sichtbar; nach Änderung „Replikation anstoßen“ -> „Übertragung vom Master angefordert“, danach gleich.
- [ ] Sekundärer Server eingetragen, aber nicht verbunden: wird mit Seriennummer per SOA-Abfrage angezeigt.

## 10. Store und Startseite (0.8.0)

Neu, nur unter Linux (offscreen) geprüft.
- [ ] Store: Karten mit Symbol, Name, Screenshot, Kurzbeschreibung und einem Knopf; Bilder laden nach (erst
      „Lade Vorschau …“), Pfeile und Punkte blättern, nach Neustart sofort da (Zwischenspeicher).
- [ ] Klick auf eine Karte: Detailleiste rechts mit allen Angaben; Klick aufs Bild öffnet es groß (Pfeiltasten,
      Esc). ✕ schließt die Leiste. Installieren, Update und Öffnen aus Karte und Leiste.
- [ ] Startseite: Ansichten Vollansicht, Große Symbole, Kleine Symbole, Liste; Wahl bleibt nach Neustart.
      Liste nach Spalten sortieren, Update-Hinweis in der Spalte „Status“.
- [ ] Rechtsklick und Doppelklick in allen vier Ansichten; Suche und Bereichsfilter in allen Ansichten.
- [ ] Startseite ohne Netz: Screenshots installierter Tools werden trotzdem angezeigt.
- [ ] Kleines Fenster (ca. 1000 px) mit offener Detailleiste: Store blendet den Bereichsbaum aus, Karten bleiben
      lesbar. Skalierung 150–200 %, helles Farbschema.

## 11. Server-Favoriten (DHCP 1.6.1, DNS 1.2.1)

Neu, nur unter Linux mit Fake-Backends geprüft (scripts/fav_check/test_favorites.py). In beiden Tools gleich testen.
- [ ] Anmeldeseite: links die Liste „Favoriten“, ☆ rechts neben dem Serverfeld. Ordner anlegen (Ordner-Knopf),
      Unterordner per Rechtsklick, umbenennen, löschen (Inhalt wandert eine Ebene hoch).
- [ ] Maske ausfüllen mit „Andere Anmeldedaten“ + Kennwort, ☆: Dialog hat „Benutzer und Kennwort im Favoriten
      speichern“ vorausgewählt, Ordner wählen, OK. In `tool_settings\net.ms-dhcp-extended.json` bzw.
      `net.ms-dns-extended.json` steht unter "favorites" KEIN Kennwort.
- [ ] Zwei Favoriten verschiedener Kunden mit verschiedenen Konten/Kennwörtern: Klick füllt Benutzer + Kennwort,
      Doppelklick meldet direkt an (ohne weitere Auswahl).
- [ ] + in der Liste: Favorit von Hand anlegen, auch mit „Anmeldedaten aus dem Passwortmanager“ (🔑 wählt einen
      Eintrag, z. B. aus OmniVault/KeePass); beim Wählen steht der Eintrag unter „Gespeicherte Anmeldedaten“.
- [ ] „Nur Benutzer speichern“: beim Wählen ist das Kennwortfeld leer und hat den Fokus.
- [ ] Ziehen und Ablegen von Favoriten und Ordnern; Suche; Liste einklappen/aufklappen; Tool schließen und neu
      öffnen: Zustand, zugeklappte Ordner und zuletzt gewählter Favorit sind wieder da.
- [ ] ☆ bei gewähltem Favorit: überschreiben / als neuen speichern / bearbeiten. Server von Hand ändern: Stern grau.
- [ ] Favorit löschen: Kennwort ist aus dem Tresor weg (Duplizieren übernimmt es).
- [ ] Masterpasswort zurücksetzen (Testtresor!): Favorit mit Kennwort zeigt Hinweis, Kennwort neu eingeben.
- [ ] DHCP: Favorit mit Ansicht IPv6 → nach der Anmeldung steht die Ansicht auf IPv6.
- [ ] DNS: Favorit mit „Weitere Server“ (z. B. Server außerhalb der Domäne) und „DHCP-Server für den Abgleich“:
      weitere Server verbunden (Protokoll), Prüfung › „mit DHCP“ nennt den DHCP-Server. Nicht erreichbarer weiterer
      Server: nur Protokolleintrag, Anmeldung läuft durch.

## 12. KI-Assistenten und Clank – KI-Studio (0.9.0)

Neu, nur unter Linux mit Fake-Anbietern geprüft (scripts/test_ai.py, scripts/ai_check/*). Für echte Tests reicht
ein Anbieter mit API-Schlüssel oder „Mit ChatGPT anmelden“; Ollama lokal ist kostenlos.

### 12a. Verbindungen und Chatleiste
- [ ] Einstellungen › KI-Assistenten › Hinzufügen: Anbieterliste mit Kategorien, Suche, Filtern; Sora rot
      („Nicht mehr angeboten“).
- [ ] ChatGPT „Im Browser anmelden“: Browser öffnet, nach Anmeldung „Angemeldet als …“. Modelle laden, Verbindung
      testen. Ebenso ein API-Schlüssel (z. B. Claude) und einer per „Aus Passwortmanager …“.
- [ ] Entra ID / Microsoft 365 Copilot (falls Lizenz da): Anmeldung, Frage, Antwort (nur Text).
- [ ] Ollama lokal (Ohne Anmeldung, http://localhost:11434/v1): Modelle laden, Chat. Mit Firmen-Proxy: geht trotzdem.
- [ ] ★ Hauptassistent setzen, Reihenfolge ▲/▼; Verbindung entfernen: Chats bleiben.
- [ ] Chatleiste: Knopf „✦ Assistent“, Strg+Umschalt+A, ausklinken/andocken, Layout bleibt nach Neustart.
- [ ] Frage stellen, Antwort streamt; Anhalten; Assistent mitten im Chat wechseln; Bild und Textdatei anhängen.
- [ ] Projekt anlegen mit Anweisungen, Chat im Projekt; Verlauf: suchen, umbenennen, löschen, Ordner öffnen.
- [ ] „Was kann OmniWrench?“ / „Wie richte ich das DHCP-Tool ein?“: Antwort nutzt das Wiki (Funktions-Hinweis).
- [ ] „Öffne den Subnetzrechner“: Bestätigung erscheint, nach „Erlauben“ öffnet sich das Tool (Stufe 4 nötig).

### 12b. KI-Datenablage
- [ ] Standard: Chats unter Dokumente\OmniWrench\Chats als `.owai` (verschlüsselt). Verschlüsselung aus +
      Speichern: Dateien werden zu `.json` + `.md`; wieder an: zurück zu `.owai`.
- [ ] Ablage „Zentraler Speicherort“ wählen: Frage nach Verschieben, Daten landen im neuen Ordner.
- [ ] OneDrive-umgeleiteter Dokumente-Ordner: Ordner wird richtig erkannt.

- [ ] Voraussetzung im Dialog „Assistent hinzufügen“: ChatGPT mit „Mit ChatGPT anmelden“ zeigt „Plus oder Pro“,
      mit API-Schlüssel „API-Konto mit Guthaben“; Gemini „kostenlose Stufe“; Ollama „kostenlos, läuft lokal“.
- [ ] Mit ChatGPT anmelden (Plus): Anmeldung, Verbindung testen, Frage in der Chatleiste.
- [ ] Modellwahl Gemini: bestehende Verbindung mit `gemini-3.1-pro` öffnen. Chatleiste fragt die Modelle ab und
      meldet „Modell gemini-3.1-pro gibt es nicht mehr, jetzt wird … verwendet“; Frage funktioniert.
- [ ] Modellknopf in der Chatleiste (und in Clank): Liste mit ★, Kurzbeschreibung, Suche; Zeigen auf ein Modell
      zeigt die Erklärung; „Auch andere Modelle zeigen“; eigenen Namen eintippen und übernehmen; „Was bedeuten die
      Modelle?“ öffnet die Wiki-Seite KI-Anbieter. Modell wechseln mitten im Chat, nächste Antwort nennt das neue Modell.
- [ ] Nicht vorhandenes Modell eintragen: Fehlermeldung „Der Anbieter kennt das gewählte Modell nicht …“, Knopf rot mit ⚠.
- [ ] NSFW: Grok (oder Venice/Ollama) zeigt den Hinweis und den Schalter „NSFW-Inhalte erlauben (ab 18)“, Claude nicht.
      Einschalten fragt nach (Nein = bleibt aus). Eingeschaltet: 🔞 vor dem Modell in der Chatleiste.
- [ ] Neue Anbieter: GitHub Models mit GitHub-Token (models:read) verbinden, Modelle abfragen, Frage stellen.
      Cloudflare: Speichern mit `<ACCOUNT_ID>` in der Adresse wird abgelehnt. Filter Region „EU“ zeigt Mistral, IONOS, STACKIT usw.

### 12c. KI-Zugriff und Verfremdung
- [ ] Einstellungen › KI-Zugriff: Stufen, Verfremdung, Vorschau. Tool-Einstellungen: Reiter „KI-Zugriff“ mit
      „Wie im Hauptprogramm“. Ausnahme je Assistent setzen.
- [ ] DHCP Stufe 3: „Welche Scopes sind fast voll?“ – Antwort mit echten Werten in der Anzeige; im gespeicherten
      Chat (Verschlüsselung aus) stehen im `state.pseudo` die Platzhalter (NET1.x, HOST-1 …).
- [ ] DHCP Stufe 4: „Lege eine Reservierung für … an“ – Bestätigung mit Details, danach im Tool sichtbar, Partner
      repliziert. „Ablehnen“ ändert nichts.
- [ ] DNS Stufe 4: Eintrag anlegen und löschen lassen.
- [ ] Favorit mit KI-Zugriff 0 vs. 4 (Zeile „KI-Zugriff“ auf der Anmeldeseite): Assistent sieht den Server nicht /
      darf ändern. Abmelden setzt zurück.
- [ ] Rechtsklick in Leases/Einträgen/Befunden/NetProbe/AD-Ergebnissen › „Assistent fragen …“: Dialog zeigt die
      Zeilen, neuer Chat in der Chatleiste.

### 12d. Clank – KI-Studio
- [ ] Installation aus dem Store; Hinweis, falls Git oder ffmpeg fehlen. Screenshots im Store.
- [ ] Arbeitsbereich: Ordner und Git-Repository hinzufügen, Online-Repository (GitHub privat mit Token), lokal
      klonen. Stufe 3: Assistent liest Dateien; Stufe 4: Dateiänderung mit Diff bestätigen, Befehl (PowerShell)
      mit Erklärung bestätigen.
- [ ] Vorlagen: „Skript prüfen“ mit Platzhalter; eigene Vorlage anlegen.
- [ ] Bildschirmfoto: Bereich und ganzer Bildschirm (mehrere Monitore, 150 % Skalierung).
- [ ] Bilder: OpenAI/Gemini, Vorlagebild, Galerie-Kontextmenü.
- [ ] Musik/Video: ffmpeg-Download unter Windows, ein Stück und ein Video erzeugen, kürzen, als MP3/GIF,
      Musik unterlegen.
- [ ] Gruppenchat mit drei Teilnehmern, Einwurf, Bremse (z. B. 6 Beiträge), Zusammenfassung.
- [ ] Dokumente: schreiben lassen, Markierung überarbeiten, Export PDF/ODT öffnen.
- [ ] Planung: Zeitplan „alle 1 h“ + „Jetzt ausführen“; Ergebnis als Chat „⏰ …“; OmniWrench zu, später auf:
      verpasster Lauf wird nachgeholt.
- [ ] MCP-Client: z. B. `npx -y @modelcontextprotocol/server-filesystem C:\Temp` (stdio) verbinden, Werkzeuge
      ansehen, Assistent liest eine Datei (mit Bestätigung, solange „vertrauen“ aus).
- [ ] MCP-Server: einschalten, „Einrichtung kopieren“ für Claude Desktop (stdio) in dessen Konfiguration; Claude
      Desktop sieht OmniWrench-Funktionen; Änderung wird in OmniWrench bestätigt. EXE-Version: `OmniWrench.exe
      --mcp-stdio` startet ohne Fenster.
- [ ] Mitschrift: Pakete installieren, Einwilligung, Mikrofon + Systemton (Teams/Zoom-Testanruf), zwei Sprecher
      erkannt, umbenennen, Sprecherprofil speichern, nächste Mitschrift erkennt die Person; Zusammenfassung,
      Export. Im Ordner Transcripts nur Text, keine Audiodatei.
- [ ] Sprecherprofile: Opt-in anhaken und starten -> roter Hinweis „biometrische Daten (Art. 9 DSGVO)“, Start erst nach
      Bestätigungshaken; Abbrechen nimmt das Opt-in zurück. Versteckt: Opt-in 10x schnell umschalten (in 6 s) ->
      Haken „immer verwenden, ohne Hinweis“ erscheint; angehakt ist das Opt-in beim nächsten Mal vorbelegt und der
      Profilhinweis entfällt (Einwilligung zur Aufnahme bleibt). Haken wieder raus -> Hinweis kommt wieder.
- [ ] Sprachassistent: Weckwort einrichten (Vosk-Modell), „Hey Clank, wie spät ist es?“, Antwort mit Systemstimme;
      Folgefrage ohne Weckwort; „Sprechen“-Knopf; Stimme eines Anbieters (OpenAI) zum Vorlesen.
- [ ] Sprache auf Englisch/Französisch umstellen: Texte vollständig (KI-Texte in allen 23 Sprachen ergänzt,
      Dialekte nur leicht eingefärbt).

## Kein Test, nur Einstellung

- [ ] GitHub › Settings › Branches: CI-Prüfungen für `main` als Pflicht markieren (Issue #24).
- [ ] Projekteinstellungen in claude.ai: Repository `KuroShiroMe/OmniWrench` statt `Steffi-Tech/OmniWrench` eintragen.
