# Infobot – Dokumente

> **Kurz:** Markdown-Editor mit Vorschau, in dem ein Assistent Anleitungen, Berichte, Konzepte und E-Mails
> schreibt und überarbeitet; Export als HTML, PDF oder ODT.

| | |
|---|---|
| **Tool-ID** | `ai.infobot` |
| **Stand der Seite** | Version 1.0.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Dokumente, PDF, ODT, HTML |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | mindestens ein verbundener Assistent |
| **Adminrechte** | nicht nötig |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/infobot`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/infobot) |

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
- Runbooks und Anleitungen für Anwender schreiben lassen.
- Berichte, Protokolle und Konzepte aus Stichpunkten ausformulieren.
- E-Mails an Anwender (z. B. Wartungsankündigung) entwerfen.

## Installation und Voraussetzungen
Installation über den [Store](Store-und-Tools), ohne zusätzliche Pakete.

## Erste Schritte
1. Infobot öffnen. Vorbelegt ist der Standard-Assistent für Dokumente.
2. **Schreiben lassen …** – Art wählen (Anleitung/Runbook, Bericht, Konzept, Protokoll, E-Mail, freier Text) und
   beschreiben, worum es geht.
3. Text prüfen, bei Bedarf **Überarbeiten …**, dann **Speichern** oder **Exportieren**.

## Funktionen im Detail

| Knopf | Wirkung |
|---|---|
| **Schreiben lassen …** | Neuer Text nach Art und Beschreibung; auf Wunsch mit dem bisherigen Text als Entwurf |
| **Überarbeiten …** | Gilt für die Markierung, sonst den ganzen Text (z. B. „kürzer und mit nummerierten Schritten“) |
| **Speichern** | Markdown-Datei im Ordner „Documents“ der KI-Datenablage |
| **Exportieren** | HTML, PDF oder ODT |
| **An den Chat anhängen** | Schickt den Text in [Clank](Tool-Clank) bzw. die Chatleiste |

Links steht der Markdown-Text, rechts die Vorschau.

## Einstellungen
Keine eigenen Einstellungen. Die Verfremdung folgt dem Reiter **KI-Zugriff** in den Einstellungen des Tools.

## Sicherheit und Datenschutz
- **Verbindungen:** zum gewählten Anbieter (HTTPS).
- **Verfremdung:** Der Text wird verfremdet gesendet und die Antwort zurückübersetzt.
- **Gespeichert:** Dokumente **unverschlüsselt** im Ordner „Documents“, damit andere Programme sie bearbeiten können.

## Grenzen und bekannte Einschränkungen
- Kein Mehrbenutzer-Bearbeiten; Dokumente sind lokale Dateien.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| Export als PDF sieht anders aus als die Vorschau | Der PDF-Export nutzt die Druckfunktion von Qt; für exaktes Layout als ODT exportieren und im Office nachbearbeiten |

## Versionen

| Version | Änderungen |
|---|---|
| 1.0.0 | Erste Version als eigenes Tool (vorher Reiter „Dokumente“ in Clank 1.0.x) |

## Siehe auch
- [Clank – KI-Chat](Tool-Clank)
- [KI-Zugriff und Verfremdung](KI-Zugriff-und-Verfremdung)
