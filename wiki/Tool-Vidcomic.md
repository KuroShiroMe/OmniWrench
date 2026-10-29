# Vidcomic – Video

> **Kurz:** Erzeugt kurze Videoclips mit den verbundenen Anbietern, spielt sie ab und bearbeitet sie mit ffmpeg
> (kürzen, Musik unterlegen, GIF, Ton entfernen, Standbild).

| | |
|---|---|
| **Tool-ID** | `ai.vidcomic` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Video, Veo, Runway, Luma, Sora, ffmpeg |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | ein verbundener Assistent mit Videoerzeugung; ffmpeg (Windows: Download bei der Installation, Linux: Paketverwaltung) |
| **Adminrechte** | nicht nötig (unter Linux für `apt install ffmpeg`) |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/vidcomic`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/vidcomic) |

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
- Kurze Schulungs- und Erklärclips, Intros für Präsentationen.
- Animierte GIFs für Anleitungen.

## Installation und Voraussetzungen
Wie bei [Groovitron](Tool-Groovitron): Unter **Windows** bietet die Installation den ffmpeg-Download an
(vorbelegt, ca. 100 MB, gemeinsam mit Groovitron genutzt), unter **Linux** steht der Befehl für die
Paketverwaltung im Protokoll.

Anbieter mit Video: u. a. Google Gemini (Veo, Omni Flash), OpenAI (Sora), xAI, Runway, Luma, Seedance, MiniMax,
fal.ai, Replicate (siehe [KI-Anbieter](KI-Anbieter)).

## Erste Schritte
1. Vidcomic öffnen. Vorbelegt ist der Standard-Assistent für Video.
2. Beschreibung eingeben, optional Startbild, Länge und Auflösung.
3. **Erzeugen** drücken – je nach Anbieter dauert das einige Minuten. Der Clip erscheint in der Liste.

## Funktionen im Detail

### Erzeugen
Beschreibung, **Startbild …**, Länge, Auflösung. Die Auswahl von Anbieter und Modell wird gemerkt.

### Abspielen und Bearbeiten
Wiedergabe mit Ton über das gewählte Audiogerät (Standard: aktuelles Systemgerät). Bearbeiten mit ffmpeg (Ergebnis
immer als neue Datei): **Kürzen …**, **Musik unterlegen …** (z. B. ein Stück aus Groovitron), **Als GIF**,
**Ton entfernen**, **Standbild speichern**. Rechtsklick: öffnen, im Ordner zeigen, **An den Chat**, löschen.

## Einstellungen

| Einstellung | Standard | Bedeutung |
|---|---|---|
| ffmpeg-Programm | leer | Leer = automatisch (von OmniWrench geladene Kopie oder ffmpeg im PATH) |

## Sicherheit und Datenschutz
- **Verbindungen:** zum gewählten Anbieter (HTTPS); einmalig zu GitHub für den ffmpeg-Download (Windows).
- **Verfremdung:** Beschreibungen werden **nicht** verfremdet.
- **Gespeichert:** Clips unverschlüsselt im Ordner „Videos“ der KI-Datenablage.

## Grenzen und bekannte Einschränkungen
- Videos sind meist die teuerste Art (Abrechnung je Sekunde).
- Kling direkt und ComfyUI werden nicht unterstützt (über fal.ai/Replicate möglich).

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| „braucht ffmpeg“ | Windows: **ffmpeg herunterladen** im Tool; Linux: `sudo apt install ffmpeg`, dann **Erneut prüfen** |
| Erzeugen dauert sehr lange | Normal bei Video (mehrere Minuten); Tool offen lassen |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Video“ in Clank 1.0.x) |

## Siehe auch
- [Groovitron – Musik](Tool-Groovitron)
- [Clank – KI-Chat](Tool-Clank)
- [KI-Anbieter](KI-Anbieter)
