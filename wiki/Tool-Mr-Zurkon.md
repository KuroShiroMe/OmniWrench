# Mr. Zurkon – Sprachassistent

> **Kurz:** Ein Sprachassistent wie Alexa, nur für OmniWrench: „Hey Zurkon“ sagen, Frage sprechen, die Antwort
> wird vorgelesen und steht im Chat daneben. Weckwort immer offline, Erkennung und Stimme auf Wunsch auch.

| | |
|---|---|
| **Tool-ID** | `ai.mr-zurkon` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Sprachassistent, Vosk, Piper, Whisper |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | Python-Pakete `numpy`, `soundcard` (bei der Installation); optional Vosk, Whisper lokal, Piper; ein verbundener Chat-Assistent |
| **Adminrechte** | nicht nötig |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/mr_zurkon`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/mr_zurkon) |

## Inhalt
- [Wofür](#wofür)
- [Installation und Voraussetzungen](#installation-und-voraussetzungen)
- [Erste Schritte](#erste-schritte)
- [Funktionen im Detail](#funktionen-im-detail)
  - [Die Anzeige](#die-anzeige)
  - [Wetter und Nachrichten](#wetter-und-nachrichten)
  - [Einstellungen im Tool](#einstellungen-im-tool)
  - [Welche Erkennung und Stimme passt?](#welche-erkennung-und-stimme-passt)
- [Einstellungen](#einstellungen)
- [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
- [Grenzen und bekannte Einschränkungen](#grenzen-und-bekannte-einschränkungen)
- [Fehlerbehebung](#fehlerbehebung)
- [Versionen](#versionen)
- [Siehe auch](#siehe-auch)

## Wofür
- Freihändig fragen, während man am Server oder im Rack arbeitet.
- Kurze Auskünfte mit den eingebauten Funktionen („Welche DHCP-Bereiche sind fast voll?“).
- Antworten vorlesen lassen statt lesen.
- Alltagsfragen ohne Konto: **Wetter** („Wie wird das Wetter morgen?“) und **Nachrichten** („Was gibt es Neues
  zu Windows?“) – mit großer animierter Anzeige.

## Installation und Voraussetzungen
Installation über den [Store](Store-und-Tools). Die Installation fragt, welche optionalen Teile gleich mit
eingerichtet werden (alle vorbelegt, einzeln abwählbar):

| Teil | Größe | Wofür |
|---|---|---|
| Weckwort offline (Vosk + kleines Sprachmodell der Programmsprache) | ca. 60 MB | „Hey Zurkon“ erkennen |
| Whisper lokal (faster-whisper + Modell *small*) | ca. 630 MB | Frage offline und genau erkennen |
| Piper (+ erste Stimme der Programmsprache) | ca. 80 MB | Natürlich klingende Stimme offline |

Pflicht sind nur `numpy` und `soundcard` (ca. 20 MB). Scheitert ein optionaler Teil (z. B. ohne Internet), bleibt
das Tool trotzdem installiert und bietet den Teil später an. Der Fortschritt steht als Balken im
Installationsfenster. Alle Pakete und Modelle liegen im gemeinsamen KI-Ordner und werden mit
[Kreeli](Tool-Kreeli) geteilt; nach einem Neustart wird nichts erneut abgefragt.

## Erste Schritte
1. Mr. Zurkon öffnen. Beim ersten Mal sind die **Einstellungen** aufgeklappt: Weckwort, Empfindlichkeit, Sprache,
   Erkennung, Stimme und **Heimatort** (für Wetterfragen ohne Ort) prüfen.
2. **Sprachassistent einschalten**. Die Einstellungen klappen zu, die Anzeige zeigt „Warte auf ‚Hey Zurkon‘“.
3. „Hey Zurkon“ sagen, dann die Frage. Die Antwort erscheint groß in der Anzeige, im Chat rechts und wird vorgelesen.
4. **Sprechen** stellt eine Frage ohne Weckwort, **Vorlesen stoppen** unterbricht.

## Funktionen im Detail

### Die Anzeige
Der größte Teil des Fensters ist die Anzeige; Verlauf und Status stehen klein darunter.

| Ansicht | Wann | Inhalt |
|---|---|---|
| Zustand | immer | Leuchtende Kugel in der Farbe des Zustands (wartet, hört zu, denkt nach, spricht), pulsiert mit der Mikrofonlautstärke; darunter die letzte Antwort. Beim Nachdenken läuft ein Zähler („Antwort wird erstellt … 12 s“) |
| Wetter | Frage nach dem Wetter | Ort, Temperatur, gefühlte Temperatur, Wind, Feuchte, Vorhersage-Karten für die nächsten Tage; Hintergrund und Animation passend zum Wetter (Sonne, Wolken, Regen, Schnee, Gewitter, Nacht) |
| Nachrichten | Frage nach Nachrichten | Schlagzeilen mit Quelle und Uhrzeit, rotes Laufband; Klick auf eine Meldung öffnet sie im Browser |

**✕** oben rechts kehrt zur Zustandsansicht zurück; die nächste Frage tut das auch.

### Wetter und Nachrichten
Beides funktioniert mit jedem Chat-Assistenten, der Funktionen aufrufen kann, und braucht **kein Konto**:
- **Wetter:** [Open-Meteo](https://open-meteo.com) (aktuelles Wetter, bis 7 Tage Vorhersage). Ohne Ortsangabe gilt
  der **Heimatort** aus den Einstellungen.
- **Nachrichten:** Google News (RSS) in der Programmsprache, auf Wunsch zu einem Thema.

Die Funktionen heißen `get_weather` und `get_news` und stehen auch in der Chatleiste und in Clank zur Verfügung
(Stufe „Beschreibung“, es gehen keine Programmdaten hinaus – nur Ort bzw. Suchbegriff).

### Einstellungen im Tool

| Einstellung | Bedeutung |
|---|---|
| Weckwort | Name nach „Hey“ (Standard „Zurkon“), weitere Schreibweisen möglich; offline mit Vosk erkannt. „Hey“, „Hei“, „Ey“ und „Hallo“ gelten alle |
| Empfindlichkeit | **Normal**, **Empfindlich** (Standard) oder **Sehr empfindlich** – reagiert dann auch auf den Namen allein, löst aber eher versehentlich aus |
| Sprache | Programmsprache oder eine andere; danach richten sich Weckwort-Modell, Erkennung und Stimmenliste |
| Spracherkennung | Anbieter, **Whisper lokal** oder „Offline (Vosk, ungenauer)“ |
| Antwort vorlesen mit | Systemstimme, **Piper** oder ein Anbieter mit Stimme (OpenAI, Google Gemini, ElevenLabs) |
| Stimme | Liste passend zur Sprache bzw. die Stimmen des Anbieters; **Probehören** spielt einen Beispielsatz |
| Folgefragen ohne Weckwort | 8 Sekunden nach der Antwort wieder zuhören |
| Vorlesen bis etwa | Längere Antworten werden gekürzt vorgelesen; Code wird nur erwähnt |
| Heimatort | Ort für Wetterfragen ohne Ortsangabe |

Das Weckwort wird **immer offline** erkannt; leise Sprache wird dafür automatisch verstärkt (bis 10-fach), und
kleine Erkennungsfehler („zur kon“, „zirkon“) zählen trotzdem. Erst danach geht der gesprochene Satz an die gewählte Erkennung.
Wiedergegeben wird über das in *Einstellungen › KI-Funktionen* gewählte Audiogerät, sonst über das
**aktuelle** Standardgerät des Systems (auch wenn es während des Betriebs gewechselt wird, z. B. auf ein Headset).

### Welche Erkennung und Stimme passt?

| Möglichkeit | Kosten | Qualität | Hinweise |
|---|---|---|---|
| Whisper lokal (faster-whisper) | kostenlos, offline | sehr gut (*small* empfohlen, *large-v3-turbo* am besten) | Braucht etwas Rechenzeit |
| Vosk | kostenlos, offline | einfach | Dasselbe kleine Modell wie das Weckwort |
| Groq (Whisper) | kostenlose Stufe | sehr gut, sehr schnell | |
| Google Gemini | kostenlose Stufe mit Minutenlimit | sehr gut | Erkennung und Vorlesen (30 Stimmen) |
| Mistral (Voxtral) | günstig | sehr gut | EU-Anbieter |
| OpenAI, ElevenLabs | kostenpflichtig | sehr gut | |
| Systemstimme | kostenlos, offline | je nach System | Unter Windows weitere Stimmen über *Einstellungen › Zeit und Sprache › Sprache* |
| Piper | kostenlos, offline | natürlich | Stimmen je Sprache (z. B. Thorsten, Kerstin, Eva), 20–110 MB je Stimme |

## Einstellungen
Keine Einstellungen im Rechtsklick-Menü; alles wird im Tool gesetzt und gemerkt. Einstellungen des
Sprachassistenten aus Clank 1.0.x werden übernommen.

## Sicherheit und Datenschutz
- **Verbindungen:** Wetter: Ortsname an open-meteo.com; Nachrichten: Suchbegriff an news.google.com. Gesprochene Fragen an die gewählte Erkennung (bei Whisper/Vosk nirgendwohin), Antworttext an die
  gewählte Stimme (bei Systemstimme/Piper nirgendwohin), Fragen verfremdet an den Chat-Assistenten. Downloads:
  PyPI, alphacephei.com (Vosk), Hugging Face (Whisper, Piper).
- **Gespeichert:** Das Gespräch als Chat in der KI-Datenablage. Audio wird nicht gespeichert.
- **Mikrofon:** Solange eingeschaltet, hört das Tool dauerhaft zu, wertet aber offline nur das Weckwort aus.

## Grenzen und bekannte Einschränkungen
- Weckwörter mit ungewöhnlicher Aussprache erkennt Vosk schlechter – weitere Schreibweisen eintragen.
- Die neuen „natürlichen“ Windows-Stimmen gibt Windows nur teilweise für andere Programme frei.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| Weckwort reagiert nicht | Empfindlichkeit auf **Sehr empfindlich** stellen, weitere Schreibweisen eintragen (das zuletzt Gehörte steht neben den Knöpfen) oder **Sprechen** benutzen |
| Antwort dauert lange | Der Zähler zeigt, ob die Erkennung oder der Assistent wartet. Nach 60 s bricht Mr. Zurkon ab und meldet das; dann einen anderen Assistenten oder Whisper lokal / Groq für die Erkennung wählen |
| Satzende wird nicht erkannt (laute Umgebung) | Der Grundpegel passt sich an; nach spätestens 15 s wird der Satz trotzdem abgeschickt |
| „Kein Wetter“ / Assistent kennt das Wetter nicht | Assistent ohne Funktionsaufrufe oder KI-Zugriff auf „Aus“ – Stufe mindestens „Beschreibung“ |
| „Offline-Sprache ist noch nicht eingerichtet“ | **Offline-Sprache einrichten** drücken |
| Kein Ton | Audiogerät in *Einstellungen › KI-Funktionen* prüfen |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Sprachassistent“ in Clank 1.0.x): Chat direkt im Tool, Vosk/Whisper/Piper bei der Installation wählbar, aktuelles Standard-Audiogerät, große Anzeige mit Wetter und Nachrichten, Empfindlichkeit, automatische Verstärkung, Abbruch nach 60 s |

## Siehe auch
- [Kreeli – Transkription](Tool-Kreeli)
- [KI lokal mit Ollama](KI-lokal-mit-Ollama)
- [Clank – KI-Chat](Tool-Clank)
