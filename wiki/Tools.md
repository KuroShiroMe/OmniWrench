# Tools

> **Kurz:** Alle Tools aus dem offiziellen Store mit Plattformen und Voraussetzungen. Jedes Tool hat eine eigene
> Seite mit allen Funktionen. Installiert wird über den [Store](Store-und-Tools).

| Tool | Bereich | Zweck | Windows | Linux | Voraussetzungen |
|---|---|---|---|---|---|
| [Subnetzrechner](Tool-Subnetzrechner) | Netzwerk & Konnektivität | IPv4/IPv6-Netze berechnen und aufteilen | ✔ | ✔ | keine |
| [AD Benutzerabfrage](Tool-AD-Benutzerabfrage) | Identität & Zugriff | Benutzer im Active Directory suchen | ✔ | – | RSAT: Active Directory |
| [OmniVault](Tool-OmniVault) | Informationssicherheit | externe Passwortmanager anbinden | ✔ | ✔ ¹ | `pykeepass` |
| [IconForge](Tool-IconForge) | Dokumentation & Design | freie Symbole suchen und exportieren | ✔ | ✔ | keine |
| [NetProbe](Tool-NetProbe) | Netzwerk & Konnektivität | Netzwerk-Tests, Portscan, DNS, Leitungstest | ✔ | ✔ | `dnspython` |
| [MS DHCP Extended Management](Tool-MS-DHCP-Extended-Management) | Netzwerk & Konnektivität | Microsoft-DHCP-Server verwalten und prüfen | ✔ | – | RSAT: DHCP |
| [MS DNS Extended Management](Tool-MS-DNS-Extended-Management) | Netzwerk & Konnektivität | Microsoft-DNS-Server verwalten und prüfen (IPv4/IPv6, PTR, Aufräumen) | ✔ | – | `pywin32`, `dnspython` |
| [Clank – KI-Chat](Tool-Clank) | KI-Tools | KI-Chat mit Projekten, Vorlagen, Arbeitsbereich (Ordner, Git, GitHub/GitLab/Azure DevOps), Bildschirmfoto | ✔ | ✔ | verbundener KI-Assistent; optional Git |
| [Pixelizer – Bilder](Tool-Pixelizer) | KI-Tools | Bilder erzeugen, mit Vorlagebild und Galerie | ✔ | ✔ | Anbieter mit Bilderzeugung |
| [Groovitron – Musik](Tool-Groovitron) | KI-Tools | Musik erzeugen, abspielen, mit ffmpeg bearbeiten | ✔ | ✔ | Anbieter mit Musik; ffmpeg ² |
| [Vidcomic – Video](Tool-Vidcomic) | KI-Tools | Videoclips erzeugen, abspielen, mit ffmpeg bearbeiten | ✔ | ✔ | Anbieter mit Video; ffmpeg ² |
| [Q-Force – Gruppenchat](Tool-Q-Force) | KI-Tools | Mehrere Assistenten besprechen ein Thema | ✔ | ✔ | verbundener KI-Assistent |
| [Infobot – Dokumente](Tool-Infobot) | KI-Tools | Dokumente schreiben lassen, Export HTML/PDF/ODT | ✔ | ✔ | verbundener KI-Assistent |
| [Orvus – Zeitpläne](Tool-Orvus) | KI-Tools | Fragen zu festen Zeiten an einen Assistenten | ✔ | ✔ | verbundener KI-Assistent |
| [Kreeli – Transkription](Tool-Kreeli) | KI-Tools | Besprechungen live transkribieren, Sprecher erkennen, zusammenfassen | ✔ | ✔ | `numpy`, `soundcard`; optional Whisper ³ |
| [Mr. Zurkon – Sprachassistent](Tool-Mr-Zurkon) | KI-Tools | Weckwort, Spracherkennung, Antworten vorlesen | ✔ | ✔ | `numpy`, `soundcard`; optional Vosk, Whisper, Piper ³ |
| [Gadgetron – MCP](Tool-Gadgetron) | KI-Tools | MCP-Server anbinden, OmniWrench als MCP-Server anbieten | ✔ | ✔ | keine |

¹ ohne die Konnektoren Microsoft SecretManagement und Netwrix Password Secure
² Windows: Download bei der Installation (abwählbar); Linux: Paketverwaltung
³ werden bei der Installation geladen; optionale Teile sind vorbelegt und abwählbar (siehe [KI lokal mit Ollama](KI-lokal-mit-Ollama#sprache-offline))

Voraussetzungen installiert OmniWrench selbst (siehe [Store und Tools › Voraussetzungen](Store-und-Tools#voraussetzungen)).

## Aufbau der Tool-Seiten
Alle Tool-Seiten folgen derselben [Vorlage](Vorlage-Tool-Seite): Steckbrief, Wofür, Installation und
Voraussetzungen, Erste Schritte, Funktionen im Detail, Einstellungen, Sicherheit und Datenschutz, Grenzen,
Fehlerbehebung, Versionen.

## Tools aus anderen Quellen
Tools aus weiteren Repositories (z. B. firmeneigene Tools) stehen nicht hier, sondern in der Dokumentation ihres
Repositorys. Wie man sie einbindet: [Store und Tools › Repositories](Store-und-Tools#repositories).

## Eigene Tools
Wie neue Tools entstehen: [Entwicklerbereich](Entwicklung).
