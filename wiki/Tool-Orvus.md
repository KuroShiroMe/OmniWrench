# Orvus – Zeitpläne

> **Kurz:** Stellt einem Assistenten zu festen Zeiten eine Frage – einmalig, täglich, wöchentlich oder alle
> N Stunden. Jeder Lauf wird ein eigener Chat.

| | |
|---|---|
| **Tool-ID** | `ai.orvus` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Zeitpläne, Automatisierung |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | mindestens ein verbundener Assistent |
| **Adminrechte** | nicht nötig |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/orvus`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/orvus) |

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
- Regelmäßige Berichte: „Fasse jeden Montag die DHCP-Befunde zusammen“.
- Tägliche Prüfungen mit den eingebauten Funktionen (nur lesend).
- Erinnerungen mit Inhalt, z. B. „Erstelle am Monatsende die Checkliste für den Zertifikatswechsel“.

## Installation und Voraussetzungen
Installation über den [Store](Store-und-Tools), ohne zusätzliche Pakete. Zeitpläne aus Clank 1.0.x werden beim
ersten Öffnen übernommen.

## Erste Schritte
1. Orvus öffnen, **＋ Neuer Zeitplan** drücken.
2. Namen, Frage an den Assistenten, Assistent und Wiederholung wählen (vorbelegt ist der Standard-Assistent
   für Zeitpläne).
3. Speichern. Die Liste zeigt den nächsten Lauf; **Jetzt ausführen** testet den Zeitplan sofort.

## Funktionen im Detail

| Feld | Bedeutung |
|---|---|
| Wiederholung | Einmalig (Datum/Uhrzeit), täglich, wöchentlich (Wochentage), alle N Stunden |
| Projekt | Optional: der Lauf landet im Projekt und nutzt dessen Arbeitsbereich |
| Verpasste Läufe beim nächsten Öffnen nachholen | Läuft nach, wenn OmniWrench zur geplanten Zeit geschlossen war |
| Aktiv | Zeitplan vorübergehend abschalten, ohne ihn zu löschen |

Die Liste zeigt Zeitplan, nächsten und letzten Lauf und das Ergebnis. Ist ein Lauf fertig, meldet OmniWrench das
im Benachrichtigungsbereich. **Bearbeiten**, **Löschen**, **Jetzt ausführen**.

Jeder Lauf wird ein neuer Chat („⏰ Name · Datum“); **Ergebnis öffnen** zeigt ihn in [Clank](Tool-Clank) bzw.
der Chatleiste.

**Funktionen, die etwas ändern, werden bei geplanten Läufen nie ausgeführt.**

## Einstellungen
Keine eigenen Einstellungen. Der Standard-Assistent steht in *Einstellungen › KI-Funktionen*.

## Sicherheit und Datenschutz
- **Verbindungen:** zum gewählten Anbieter (HTTPS).
- **Änderungen:** nie – ändernde Funktionen sind in geplanten Läufen gesperrt.
- **Gespeichert:** Zeitpläne in den Tool-Einstellungen, Ergebnisse als Chats in der KI-Datenablage (verschlüsselt,
  falls eingestellt).

## Grenzen und bekannte Einschränkungen
- Zeitpläne laufen nur, solange OmniWrench mit geöffnetem Orvus läuft. Für Läufe ohne angemeldeten Benutzer ist
  Orvus nicht gedacht.
- Bei mehreren Orvus-Tabs führt nur einer die Zeitpläne aus.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| Lauf wurde nicht ausgeführt | Orvus war geschlossen – **Verpasste Läufe beim nächsten Öffnen nachholen** einschalten |
| Lauf meldet „Funktion gesperrt“ | Gewollt: ändernde Funktionen laufen nie geplant; Frage auf Lesen umformulieren |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Planung“ in Clank 1.0.x; Zeitpläne werden übernommen) |

## Siehe auch
- [Clank – KI-Chat](Tool-Clank)
- [KI-Zugriff und Verfremdung](KI-Zugriff-und-Verfremdung)
