# Store und Tools

> **Kurz:** Der Store zeigt alle Tools aus den eingetragenen Repositories. Installieren, Aktualisieren,
> Reparieren und Deinstallieren geht per Knopf; Voraussetzungen wie RSAT richtet OmniWrench selbst ein.

**Gilt für:** Hauptprogramm ab Version 0.7.0 · Windows und Linux

## Inhalt
- [Der Store](#der-store)
- [Tool installieren](#tool-installieren)
- [Voraussetzungen](#voraussetzungen)
- [Updates](#updates)
- [Prüfen, reparieren, deinstallieren](#prüfen-reparieren-deinstallieren)
- [Tool aus Datei oder Ordner installieren](#tool-aus-datei-oder-ordner-installieren)
- [Repositories](#repositories)

## Der Store

*Ansicht › Store* oder `Strg+Umschalt+S` öffnet den Tab **Store**.

![Store mit Bereichen und Tool-Karten](images/hauptprogramm-store.png)

- **Links** die Bereiche als Baum, oben die Filter **Alle Tools**, **Updates (n)** und **Installiert**.
- **Rechts** eine Karte je Tool: Symbol, Name, Beschreibung, Version, Quelle (Repository), Voraussetzungen und
  Tags. Ein Klick auf ein Tag sucht nach allen Tools mit diesem Tag.
- **Suche** über Namen, Beschreibungen und Tags.
- **Aktualisieren** lädt die Kataloge neu.
- Unten steht, wie viele Tools aus wie vielen Repositories geladen wurden.

Je nach Zustand trägt eine Karte den Knopf **Installieren**, den Hinweis **Installiert (Version)** oder
**Update auf X.Y.Z**. Tools, die auf dem aktuellen Betriebssystem nicht laufen, zeigen
„Läuft nur unter …“ und keinen Installieren-Knopf.

## Tool installieren

1. Im Store **Installieren** klicken.
2. Hat das Tool Voraussetzungen, listet OmniWrench sie vorher auf („Für ‹Tool› wird zusätzlich installiert: …“).
3. Nach Bestätigung erscheint ein Fortschrittsfenster mit Protokoll. Windows-Funktionen werden in **einer**
   Administrator-Sitzung installiert, also mit einer einzigen UAC-Abfrage.
4. Das Tool steht danach auf Home und in der Seitenleiste.

Installierte Tools liegen im Benutzerprofil (siehe [Datenablage](Datenablage-und-Datenschutz)), nicht im
Programmordner. Jeder Windows-Benutzer hat also seine eigenen Tools.

Der Haken **„Dieses Fenster nach Abschluss schließen“** im Fortschrittsfenster wird gemerkt und gilt für alle
Installations- und Update-Fenster. Bei Fehlern bleibt das Fenster immer offen.

## Voraussetzungen

Tools melden in ihrem Paket, was sie brauchen. OmniWrench installiert es vor dem Tool:

| Art | Beispiel | Wie |
|---|---|---|
| Python-Paket | `dnspython`, `pykeepass` | per pip in den Tool-Ordner (`_lib`), keine Python-Installation nötig |
| Windows-Funktion (Capability) | RSAT: Active Directory, RSAT: DHCP | `Add-WindowsCapability`, mit UAC |
| Windows-Feature | `RSAT-DNS-Server` | Windows-Optionalfeatures, mit UAC |
| PowerShell-Modul | `ExchangeOnlineManagement` | `Install-Module -Scope CurrentUser` |
| winget-Paket | `WiresharkFoundation.Wireshark` | `winget install` |

Vorher fragt OmniWrench das Tool, ob etwas fehlt. Ist alles schon vorhanden, entfällt die UAC-Abfrage.
Läuft OmniWrench bereits als Administrator, gibt es ebenfalls keine Abfrage. Meldet Windows einen nötigen
Neustart, steht ein Hinweis im Protokoll; OmniWrench startet nie selbst neu.

**Firmennetz mit WSUS:** Schlägt die RSAT-Installation mit `0x800f0954` fehl, darf der Client optionale
Funktionen nicht direkt von Windows Update laden. Das Protokoll nennt die passende Gruppenrichtlinie
(„Einstellungen für die Installation optionaler Komponenten und die Reparatur von Komponenten angeben“).
OmniWrench ändert Richtlinien nie selbst.

## Updates

OmniWrench vergleicht beim Start die installierten Tools mit den Katalogen der Repositories.

- **Meldung beim Start:** Gibt es Updates, erscheint ein Fenster mit der Liste und den Knöpfen
  **Alle aktualisieren** und **Später**.
- **Einzeln:** Knopf **Update auf X.Y.Z** im Store, in der Detailleiste oder im Kontextmenü.
- **Alle auf einmal:** im Store (**Alle aktualisieren**) oder unter *Einstellungen › Updates*.
- **Automatisch:** *Einstellungen › Updates › Tools automatisch im Hintergrund aktualisieren* installiert Updates
  beim Start ohne Rückfrage. Übersprungen werden geöffnete Tools und Updates mit neuen Voraussetzungen; sie
  bleiben als Update sichtbar.

Ist ein Tool während des Updates geöffnet, fragt OmniWrench, ob es geschlossen werden darf. Einstellungen und
Daten eines Tools bleiben bei Updates erhalten. Schlägt ein Update fehl, wird die vorherige Version
wiederhergestellt.

Das Hauptprogramm selbst wird über GitHub Releases aktualisiert, siehe [Installation](Installation#updates).

## Prüfen, reparieren, deinstallieren

Alle drei über das Kontextmenü (Rechtsklick auf Kachel oder Seitenleiste):

- **Voraussetzungen prüfen:** zeigt, ob etwas fehlt, z. B. weil RSAT nach einem Windows-Upgrade verschwunden ist.
- **Reparieren:** führt die Installation erneut aus und installiert fehlende Voraussetzungen nach.
  Einstellungen bleiben erhalten.
- **Deinstallieren …:** entfernt das Tool. Der Haken **„Einstellungen, Daten und gespeicherte Zugangsdaten
  ebenfalls löschen“** entfernt zusätzlich alles, was das Tool gespeichert hat. Systemvoraussetzungen wie
  RSAT bleiben installiert.

## Tool aus Datei oder Ordner installieren

Für Tools, die (noch) in keinem Repository stehen, und für die Entwicklung:

- *Datei › Tool aus ZIP-Datei installieren …*: ein Tool-Paket (`.zip`) wählen.
- *Datei › Tool aus Ordner installieren …*: einen Ordner mit `tool.json` wählen.

Ist das Tool schon installiert, wird es ersetzt; seine Einstellungen bleiben erhalten. Pakete aus fremden
Quellen enthalten Programmcode, der mit den eigenen Rechten läuft. Nur Pakete aus vertrauenswürdigen Quellen
installieren.

## Repositories

Ein Repository ist eine Datei `index.json` (meist in einem GitHub-Repository), die Tools und Download-Pakete
auflistet. Verwaltet werden sie unter *Extras › Einstellungen › Repositories*:

| Spalte | Bedeutung |
|---|---|
| Aktiv | Repository im Store berücksichtigen |
| Name | Anzeigename (erscheint auf der Store-Karte als „Quelle“) |
| URL | `https://…/index.json` oder ein lokaler Pfad / Netzwerkpfad |

- Voreingestellt ist der **offizielle Store**:
  `https://raw.githubusercontent.com/KuroShiroMe/OmniWrench/main/store/index.json`
- Weitere Repositories (eigene, von Kollegen, von der Firma) mit **Hinzufügen** eintragen. Wie man ein eigenes
  Repository baut: [Eigenes Tool-Repository](Entwicklung-Eigenes-Repository).
- Kommt ein Tool in mehreren Repositories vor, gewinnt die höchste Version.
- **Private GitHub-Repositories** brauchen ein GitHub-Token (*Einstellungen › Updates › GitHub-Token*). Es wird
  verschlüsselt im Tresor gespeichert. Ein Token hebt außerdem das API-Limit von GitHub an.
- Ein Repository auf einer Dateifreigabe (`\\server\tools\store\index.json`) eignet sich für Firmen ohne
  GitHub-Zugang.

## Siehe auch
- [Einstellungen](Einstellungen#updates)
- [Repository in OmniWrench einbinden](Entwicklung-Repository-einbinden)
- [Fehlerbehebung](Fehlerbehebung)
