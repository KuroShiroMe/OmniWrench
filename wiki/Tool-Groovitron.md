# Groovitron – Musik

> **Kurz:** Erzeugt Musikstücke mit den verbundenen Anbietern, spielt sie ab und bearbeitet sie mit ffmpeg
> (kürzen, als MP3).

| | |
|---|---|
| **Tool-ID** | `ai.groovitron` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Musik, Lyria, ElevenLabs, ffmpeg |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | ein verbundener Assistent mit Musikerzeugung; ffmpeg (Windows: Download bei der Installation, Linux: Paketverwaltung) |
| **Adminrechte** | nicht nötig (unter Linux für `apt install ffmpeg`) |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/groovitron`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/groovitron) |

## Inhalt
- [Wofür](#wofür)
- [Installation und Voraussetzungen](#installation-und-voraussetzungen)
- [Erste Schritte](#erste-schritte)
- [Funktionen im Detail](#funktionen-im-detail)
- [Einstellungen](#einstellungen)
- [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
- [Grenzen und bekannte Einschränkungen](#grenzen-und-bekannte-einschränkungen)
- [Fehlerbehebung](#fehlerbehebung)
- [Versionen](#versionen)
- [Siehe auch](#siehe-auch)

## Wofür
- Wartemusik für die Telefonanlage, Hintergrundmusik für Schulungsvideos und Präsentationen.
- Kurze Jingles für Ankündigungen.

## Installation und Voraussetzungen
Installation über den [Store](Store-und-Tools). Unter **Windows** fragt die Installation, ob ffmpeg geladen werden
soll (vorbelegt, ca. 100 MB, BtbN-Build von GitHub, mit Fortschrittsbalken). ffmpeg landet im gemeinsamen
KI-Ordner und wird auch von [Vidcomic](Tool-Vidcomic) genutzt. Abgewählt lässt es sich später im Tool laden.
Unter **Linux** zeigt die Installation den Befehl für die Paketverwaltung (`sudo apt install ffmpeg`).

Anbieter mit Musik: u. a. Google Gemini (Lyria), ElevenLabs, MiniMax, Stability, Mureka, fal.ai, Replicate (siehe
[KI-Anbieter](KI-Anbieter)). **Kostenlos und lokal:** ComfyUI mit ACE-Step (Gesang, eigener Liedtext), siehe
[KI lokal](KI-lokal-mit-Ollama#bilder-musik-und-video-mit-comfyui).

## Erste Schritte
1. Groovitron öffnen. Vorbelegt ist der Standard-Assistent für Musik.
2. Beschreibung eingeben (Stil, Stimmung, Instrumente), optional Liedtext und Länge.
3. **Erzeugen** drücken. Das Stück erscheint in der Liste und lässt sich abspielen.

## Funktionen im Detail

### Erzeugen
Beschreibung, Liedtext, **Nur instrumental**, Länge. Die Auswahl von Anbieter und Modell wird gemerkt.

### Abspielen und Bearbeiten
Wiedergabe über das in *Einstellungen › KI-Funktionen* gewählte Audiogerät; ist dort nichts gewählt,
über das aktuelle Standardgerät des Systems. Bearbeiten mit ffmpeg (Ergebnis immer als neue Datei): **Kürzen …**,
**Als MP3**. Rechtsklick: öffnen, im Ordner zeigen, **An den Chat**, löschen.

## Einstellungen

| Einstellung | Standard | Bedeutung |
|---|---|---|
| ffmpeg-Programm | leer | Leer = automatisch (von OmniWrench geladene Kopie oder ffmpeg im PATH) |

## Sicherheit und Datenschutz
- **Verbindungen:** zum gewählten Anbieter (HTTPS); einmalig zu GitHub für den ffmpeg-Download (Windows).
- **Verfremdung:** Beschreibungen werden **nicht** verfremdet.
- **Gespeichert:** Stücke unverschlüsselt im Ordner „Music“ der KI-Datenablage.

## Grenzen und bekannte Einschränkungen
- Länge und Liedtext hängen vom Anbieter ab.
- Ohne ffmpeg gehen Erzeugen und Abspielen, aber nicht das Bearbeiten.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| „braucht ffmpeg“ | Windows: **ffmpeg herunterladen** im Tool; Linux: `sudo apt install ffmpeg`, dann **Erneut prüfen** |
| Kein Ton | Audiogerät in *Einstellungen › KI-Funktionen* prüfen (Standard = Systemgerät) |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Musik“ in Clank 1.0.x); ffmpeg-Download bei der Installation mit Fortschritt |

## Siehe auch
- [Vidcomic – Video](Tool-Vidcomic)
- [Clank – KI-Chat](Tool-Clank)
- [KI-Anbieter](KI-Anbieter)
