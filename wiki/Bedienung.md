# Bedienung

> **Kurz:** Home zeigt die installierten Tools als Kacheln, die Seitenleiste sortiert sie nach Bereichen,
> jedes Tool läuft in einem eigenen, frei anordenbaren Tab.

**Gilt für:** Hauptprogramm ab Version 0.7.0 · Windows und Linux

## Inhalt
- [Aufbau des Hauptfensters](#aufbau-des-hauptfensters)
- [Home](#home)
- [Seitenleiste](#seitenleiste)
- [Tabs anordnen](#tabs-anordnen)
- [Kontextmenü eines Tools](#kontextmenü-eines-tools)
- [Menüs](#menüs)
- [Tastenkürzel](#tastenkürzel)
- [Bereiche (Kategorien) und Tags](#bereiche-kategorien-und-tags)

## Aufbau des Hauptfensters

![Hauptfenster mit Home, Seitenleiste und Detailleiste](images/hauptprogramm-home.png)

| Bereich | Funktion |
|---|---|
| Menüleiste | Datei, Ansicht, Extras, Hilfe |
| Seitenleiste (links) | alle installierten Tools, nach Bereichen gruppiert, mit Filterfeld |
| Tab-Leiste | Home (immer offen), Store und jedes geöffnete Tool |
| Detailleiste (rechts auf Home) | Informationen und Aktionen zum ausgewählten Tool |
| Statusleiste (unten) | kurze Meldungen, z. B. „Kopiert“ oder Ergebnisse von Tools |

## Home

Home ist immer geöffnet und lässt sich nicht schließen. Oben stehen die Anzahl installierter Tools und, falls
vorhanden, die Anzahl verfügbarer Updates.

- **Kacheln:** Symbol und Name je Tool, gruppiert nach Bereich. Lange Namen werden erst kleiner geschrieben,
  dann auf zwei Zeilen umgebrochen.
- **Ein Klick** wählt ein Tool aus und öffnet rechts die **Detailleiste**: Beschreibung, Version, Kategorie,
  Tags, Autor, Tool-ID, Voraussetzungen, Website (Link zur Wiki-Seite des Tools) und Knöpfe für Öffnen,
  Einstellungen, Aktualisieren, Programmordner öffnen und Deinstallieren.
- **Doppelklick** öffnet das Tool.
- **Rechtsklick** öffnet das [Kontextmenü](#kontextmenü-eines-tools).
- **Suche** (Feld oben): durchsucht Namen, Beschreibungen und Tags.
- **Filter:** zeigt nur einen Bereich an. Der aktive Filter wird angezeigt, **Filter entfernen** hebt ihn auf.
- **Tags** in der Detailleiste sind klickbar und suchen nach allen Tools mit demselben Tag.
- Hat ein Tool ein Update, trägt die Kachel den Hinweis „Update auf X.Y.Z“.

Unter Windows Server steht oben ein Hinweis, dass das System nicht unterstützt wird.

## Seitenleiste

- zeigt alle installierten Tools im Baum nach Bereichen
- `Strg+B` blendet sie ein und aus (*Ansicht › Seitenleiste*)
- Das Feld **Filtern …** sucht in Namen und Tags.
- **Doppelklick auf ein Tool** öffnet es, **Doppelklick auf einen Bereich** zeigt Home mit diesem Bereich als Filter.
- Rechtsklick auf ein Tool öffnet dasselbe Kontextmenü wie auf Home.

## Tabs anordnen

OmniWrench nutzt das Qt Advanced Docking System. Jeder Tab lässt sich mit der Maus ziehen:

- **nebeneinander oder übereinander:** Tab an den Rand eines anderen Bereichs ziehen, die blauen Markierungen
  zeigen, wo er landet
- **gestapelt:** auf die Mitte eines Bereichs ziehen
- **eigenes Fenster:** Tab aus dem Hauptfenster herausziehen (z. B. auf einen zweiten Monitor)
- Ein Tool lässt sich mehrfach öffnen (z. B. zwei NetProbe-Tabs), außer es ist als Einzelinstanz markiert
  (z. B. OmniVault).

Beim Beenden speichert OmniWrench, welche Tabs offen sind und wie sie angeordnet sind, und stellt beides beim
nächsten Start wieder her (abschaltbar unter *Einstellungen › Anzeige*). *Ansicht › Layout zurücksetzen* stellt
die Grundanordnung wieder her.

## Kontextmenü eines Tools

Rechtsklick auf eine Kachel oder einen Eintrag der Seitenleiste:

| Eintrag | Wirkung |
|---|---|
| Öffnen | öffnet das Tool in einem neuen Tab |
| Einstellungen … | Einstellungsdialog des Tools (siehe [Einstellungen](Einstellungen#einstellungen-eines-tools)) |
| Aktualisieren (auf X.Y.Z) | installiert die neuere Version aus dem Store |
| Voraussetzungen prüfen | prüft, ob alles Nötige (RSAT, Module …) vorhanden ist |
| Reparieren | führt die Installation erneut aus, inkl. fehlender Voraussetzungen |
| Programmordner öffnen | öffnet den Installationsordner des Tools |
| Deinstallieren … | entfernt das Tool, optional mit seinen Einstellungen und Daten |

Details: [Store und Tools](Store-und-Tools).

## Menüs

| Menü | Einträge |
|---|---|
| **Datei** | Tool aus ZIP-Datei installieren …, Tool aus Ordner installieren …, Sperren, Beenden |
| **Ansicht** | Seitenleiste, Home, Store, Layout zurücksetzen |
| **Extras** | Nach Updates suchen, Passwortmanager, Symbol-Bibliothek …, Einstellungen … |
| **Hilfe** | Tool-Entwicklung (Doku), Log-Ordner öffnen, Über … |

Die **Symbol-Bibliothek** zeigt die rund 2.100 eingebauten Lucide-Symbole; ein Klick kopiert den Namen
(nützlich für die [Tool-Entwicklung](Entwicklung-Paketformat#symbole)).

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+H` | Home anzeigen |
| `Strg+Umschalt+S` | Store anzeigen |
| `Strg+B` | Seitenleiste ein/aus |
| `Strg+Umschalt+P` | Passwortmanager |
| `Strg+,` | Einstellungen |
| `Strg+L` | Sperren |
| `Strg+Q` | Beenden |

## Bereiche (Kategorien) und Tags

Tools sind in feste **Service-Bereiche** einer IT-Abteilung einsortiert, jedes Tool in genau einen:

| Bereich | Typische Inhalte |
|---|---|
| Arbeitsplatz & Endgeräte | Windows-Client, Softwareverteilung, Drucker, Mobilgeräte |
| Identität & Zugriff | Active Directory, Entra ID, Gruppen und Berechtigungen |
| Netzwerk & Konnektivität | IP, DNS, DHCP, LAN/WLAN, VPN, Firewall, Diagnose |
| Server & Rechenzentrum | Virtualisierung, Speicher, Backup |
| Cloud & Microsoft 365 | Exchange, Teams, SharePoint, Azure |
| Informationssicherheit | Passwörter, Zertifikate, Verschlüsselung |
| Anwendungen & Datenbanken | SQL Server, IIS, Fachanwendungen |
| Betrieb & Überwachung | Ereignisprotokolle, Monitoring, Inventar |
| Service Desk & Support | Fernwartung, Benutzerhilfe |
| Automatisierung & Entwicklung | PowerShell, APIs, Konverter |
| Dokumentation & Design | Symbole, Diagramme, Vorlagen |
| Sonstiges | alles ohne Angabe |

Feiner ordnen **Tags** ein (z. B. `DHCP`, `Port Scan`, `KeePass`). Sie stehen in der Detailleiste und auf der
Store-Karte; ein Klick sucht nach allen Tools mit diesem Tag.

## Siehe auch
- [Store und Tools](Store-und-Tools)
- [Einstellungen](Einstellungen)
