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
1. Mr. Zurkon öffnen. Ist das Weckwort eingerichtet, steht „Offline-Erkennung bereit“.
2. **Sprachassistent einschalten**.
3. „Hey Zurkon“ sagen, dann die Frage. Die Antwort erscheint im Chat rechts und wird vorgelesen.
4. **Sprechen** stellt eine Frage ohne Weckwort, **Vorlesen stoppen** unterbricht.

## Funktionen im Detail

### Einstellungen im Tool

| Einstellung | Bedeutung |
|---|---|
| Weckwort | Name nach „Hey“ (Standard „Zurkon“), weitere Schreibweisen möglich; offline mit Vosk erkannt |
| Sprache | Programmsprache oder eine andere; danach richten sich Weckwort-Modell, Erkennung und Stimmenliste |
| Spracherkennung | Anbieter, **Whisper lokal** oder „Offline (Vosk, ungenauer)“ |
| Antwort vorlesen mit | Systemstimme, **Piper** oder ein Anbieter mit Stimme (OpenAI, Google Gemini, ElevenLabs) |
| Stimme | Liste passend zur Sprache bzw. die Stimmen des Anbieters; **Probehören** spielt einen Beispielsatz |
| Folgefragen ohne Weckwort | 8 Sekunden nach der Antwort wieder zuhören |
| Vorlesen bis etwa | Längere Antworten werden gekürzt vorgelesen; Code wird nur erwähnt |

Das Weckwort wird **immer offline** erkannt; erst danach geht der gesprochene Satz an die gewählte Erkennung.
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
- **Verbindungen:** gesprochene Fragen an die gewählte Erkennung (bei Whisper/Vosk nirgendwohin), Antworttext an die
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
| Weckwort reagiert nicht | Deutlich sprechen, weitere Schreibweisen eintragen (z. B. „hey zirkon“) oder **Sprechen** benutzen |
| „Offline-Sprache ist noch nicht eingerichtet“ | **Offline-Sprache einrichten** drücken |
| Kein Ton | Audiogerät in *Einstellungen › KI-Funktionen* prüfen |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Sprachassistent“ in Clank 1.0.x): Chat direkt im Tool, Vosk/Whisper/Piper bei der Installation wählbar, aktuelles Standard-Audiogerät |

## Siehe auch
- [Kreeli – Transkription](Tool-Kreeli)
- [KI lokal mit Ollama](KI-lokal-mit-Ollama)
- [Clank – KI-Chat](Tool-Clank)
