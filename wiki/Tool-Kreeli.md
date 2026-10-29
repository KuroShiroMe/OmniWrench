# Kreeli – Transkription

> **Kurz:** Schreibt Besprechungen von Mikrofon und Systemton (Teams, Zoom, Webex …) live mit, erkennt die
> Sprecher und fasst am Ende zusammen – auf Wunsch ganz offline mit Whisper.

| | |
|---|---|
| **Tool-ID** | `ai.kreeli` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Transkription, Whisper, Meeting |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | Python-Pakete `numpy`, `soundcard` (bei der Installation); optional Whisper lokal; für die Zusammenfassung ein verbundener Assistent |
| **Adminrechte** | nicht nötig |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/kreeli`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/kreeli) |

## Inhalt
- [Wofür](#wofür)
- [Installation und Voraussetzungen](#installation-und-voraussetzungen)
- [Erste Schritte](#erste-schritte)
- [Funktionen im Detail](#funktionen-im-detail)
  - [Einwilligung](#einwilligung)
  - [Sprecher und Sprecherprofile](#sprecher-und-sprecherprofile)
  - [Welche Spracherkennung?](#welche-spracherkennung)
- [Einstellungen](#einstellungen)
- [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
- [Grenzen und bekannte Einschränkungen](#grenzen-und-bekannte-einschränkungen)
- [Fehlerbehebung](#fehlerbehebung)
- [Versionen](#versionen)
- [Siehe auch](#siehe-auch)

## Wofür
- Protokoll einer Besprechung oder eines Telefonats (mit Einwilligung aller) ohne Mitschreiben.
- Zusammenfassung mit Beschlüssen und Aufgaben direkt nach dem Termin.
- Transkription mehrsprachiger Runden (z. B. `de, en`).

## Installation und Voraussetzungen
Installation über den [Store](Store-und-Tools). Die Installation lädt `numpy` und `soundcard` (ca. 20 MB) in den
gemeinsamen KI-Paketordner und fragt, ob **Whisper lokal** gleich mit eingerichtet werden soll (vorbelegt, Paket
und Modell *small*, zusammen ca. 630 MB). Abgewählt lässt es sich später im Tool nachholen. Der Fortschritt steht
als Balken im Installationsfenster. Einmal geladene Pakete und Modelle teilen sich alle KI-Tools
(z. B. [Mr. Zurkon](Tool-Mr-Zurkon)); nach einem Neustart wird nichts erneut abgefragt.

Unter Linux braucht der Systemton (Loopback) PulseAudio oder PipeWire mit Pulse-Schnittstelle.

## Erste Schritte
1. Kreeli öffnen, Quellen (**Mikrofon**, **Systemton**), Spracherkennung, Sprachen und den eigenen Namen wählen.
2. **Aufnahme starten** – vor **jeder** Aufnahme fragt Kreeli die [Einwilligung](#einwilligung) ab. Ein roter
   Balken zeigt, solange aufgenommen wird. **Pause** unterbricht.
3. **Aufnahme beenden** – die Zusammenfassung entsteht automatisch (abschaltbar) oder über **Zusammenfassen**.
4. **In den Chat** schickt die Mitschrift an [Clank](Tool-Clank), **Exportieren …** speichert Markdown.

## Funktionen im Detail
Ansichten **Mitschrift**, **Zusammenfassung** und **Sprecher**; links die Liste früherer Mitschriften.

### Einwilligung
Gespräche dürfen nur mit Zustimmung aller Beteiligten aufgenommen werden (in Deutschland § 201 StGB, DSGVO). Der
Dialog verlangt die Bestätigung, dass alle informiert und einverstanden sind, und bietet einen **Hinweistext für
Teilnehmende** zum Kopieren an. Die Bestätigung wird mit Zeitpunkt in der Mitschrift vermerkt.

### Sprecher und Sprecherprofile
Ansicht **Sprecher**: **Umbenennen …**, **Zusammenlegen …** (wenn eine Person doppelt erkannt wurde),
**Als Sprecherprofil speichern …**. **Sprecherprofile** (Stimmmerkmale mit Namen, damit bekannte Stimmen
automatisch benannt werden) sind biometrische Daten (Art. 9 DSGVO): nur nach Erlaubnis im Einwilligungsdialog und
Zustimmung der Person. Beim Start mit Profilen erscheint ein eigener, deutlicher Hinweis. Profile sind **immer
verschlüsselt** und lassen sich verwalten und löschen. Die **Stimmen-Ähnlichkeit** legt fest, wie streng Stimmen
zugeordnet werden.

### Welche Spracherkennung?

| Möglichkeit | Kosten | Hinweise |
|---|---|---|
| Whisper lokal | kostenlos, offline | Sehr gut; ohne Sprechererkennung des Anbieters – Sprecher trennt Kreeli selbst |
| Groq (Whisper) | kostenlose Stufe | Sehr schnell |
| Google Gemini | kostenlose Stufe mit Minutenlimit | Erkennt Sprecher |
| Mistral (Voxtral) | günstig | EU-Anbieter |
| OpenAI, ElevenLabs, Deepgram, AssemblyAI | kostenpflichtig | Teils mit Sprechererkennung |

Vorbelegt sind die Standard-Assistenten für „Transkription: Erkennung“ und „Transkription: Zusammenfassung“
(*Einstellungen › KI-Funktionen*).

## Einstellungen
Keine Einstellungen im Rechtsklick-Menü; Quellen, Erkennung, Sprachen, eigener Name, „Mehrere Personen am
Mikrofon“, Stimmen-Ähnlichkeit und automatische Zusammenfassung werden im Tool gesetzt und gemerkt. Einstellungen
der Mitschrift aus Clank 1.0.x werden übernommen.

## Sicherheit und Datenschutz
- **Verbindungen:** Audio geht an die gewählte Spracherkennung (bei Whisper lokal nirgendwohin), der Text für die
  Zusammenfassung verfremdet an den gewählten Assistenten. Downloads: PyPI (Pakete), Hugging Face (Whisper-Modell).
- **Gespeichert:** nur der Text (verschlüsselt, falls eingestellt). Audio und Stimmmerkmale bleiben im
  Arbeitsspeicher; Sprecherprofile nur, wenn ausdrücklich angelegt, und dann immer verschlüsselt.

## Grenzen und bekannte Einschränkungen
- Die Sprechererkennung ohne Anbieter-Diarisierung arbeitet mit einfachen Stimmmerkmalen; bei ähnlichen Stimmen
  hilft **Zusammenlegen …** oder ein Sprecherprofil.
- Whisper lokal braucht Rechenzeit; auf schwachen Rechnern das Modell *base* wählen.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| Quelle kann nicht aufgenommen werden | Gerät belegt oder fehlt; unter Linux PulseAudio/PipeWire prüfen; unter Windows Mikrofonzugriff in den Datenschutzeinstellungen erlauben |
| „Offline-Sprache ist noch nicht eingerichtet“ | **Offline-Sprache einrichten** drücken (lädt faster-whisper und das Modell) |
| Paketinstallation scheitert mit „Zugriff verweigert“ | Ab OmniWrench 0.9.0 behoben (bereits geladene Pakete werden nicht mehr ersetzt). Sonst OmniWrench neu starten und erneut versuchen |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Mitschrift“ in Clank 1.0.x); Whisper bei der Installation wählbar, gemeinsamer Paketordner |

## Siehe auch
- [Mr. Zurkon – Sprachassistent](Tool-Mr-Zurkon)
- [KI lokal mit Ollama](KI-lokal-mit-Ollama)
- [Datenablage und Datenschutz](Datenablage-und-Datenschutz)
