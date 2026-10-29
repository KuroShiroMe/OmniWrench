# Clank – KI-Chat

> **Kurz:** Der große Chat für die [KI-Assistenten](KI-Assistenten): Chats mit Projekten, Vorlagen und einem
> Arbeitsbereich aus Ordnern und Repositories, dazu Bildschirmfotos. Bilder, Musik, Video, Gruppenchat,
> Dokumente, Zeitpläne, Transkription, Sprachassistent und MCP sind seit 0.9.0 eigene [KI-Tools](#die-ki-tools).

| | |
|---|---|
| **Tool-ID** | `ai.clank` |
| **Stand der Seite** | Version 1.1.0 |
| **Bereich** | KI-Tools |
| **Tags** | KI, Chat, ChatGPT, Claude, Copilot, Gemini, Ollama, Git, GitHub, GitLab, Azure DevOps, Projekte |
| **Plattformen** | Windows, Linux |
| **Voraussetzungen** | mindestens ein verbundener Assistent; optional Git |
| **Adminrechte** | nicht nötig |
| **Mindestversion OmniWrench** | 0.9.0 |
| **Quellcode** | [`tools/clank`](https://github.com/KuroShiroMe/OmniWrench/tree/main/tools/clank) |

![Chat in Clank](images/clank-chat.png)

## Inhalt
- [Wofür](#wofür)
- [Installation und Voraussetzungen](#installation-und-voraussetzungen)
- [Erste Schritte](#erste-schritte)
- [Funktionen im Detail](#funktionen-im-detail)
  - [Chat, Projekte und Arbeitsbereich](#chat-projekte-und-arbeitsbereich)
  - [Vorlagen](#vorlagen)
  - [Bildschirmfoto](#bildschirmfoto)
  - [Die KI-Tools](#die-ki-tools)
- [Einstellungen](#einstellungen)
- [Sicherheit und Datenschutz](#sicherheit-und-datenschutz)
- [Grenzen und bekannte Einschränkungen](#grenzen-und-bekannte-einschränkungen)
- [Fehlerbehebung](#fehlerbehebung)
- [Versionen](#versionen)
- [Siehe auch](#siehe-auch)

## Wofür
- Mit einem Assistenten an Skripten und Konfigurationen arbeiten: Ordner oder Git-Repository freigeben, Dateien
  lesen und durchsuchen lassen, Änderungen als Diff vorschlagen lassen und nach Bestätigung speichern.
- Wiederkehrende Fragen mit Vorlagen stellen („Skript prüfen“, „Fehlermeldung erklären“, „Runbook schreiben“).
- Fehlermeldungen per Bildschirmfoto zeigen und erklären lassen.
- Ergebnisse der anderen KI-Tools (Bilder, Dokumente, Zeitplan-Läufe, Transkriptionen) weiterbesprechen.

## Installation und Voraussetzungen
Clank wird über den [Store](Store-und-Tools) installiert und braucht keine zusätzlichen Pakete. Assistenten werden
im Hauptprogramm verbunden (*Einstellungen › KI-Assistenten*, siehe [KI-Assistenten](KI-Assistenten)) und gelten
in Clank, in der Chatleiste und in allen KI-Tools gleichermaßen. Ein kostenloser, lokaler Assistent lässt sich mit
[Ollama](KI-lokal-mit-Ollama) direkt aus OmniWrench einrichten.

Für lokale Git-Repositories und das Klonen wird Git gebraucht ([git-scm.com](https://git-scm.com) bzw.
Paketverwaltung). Ordner und Online-Repositories gehen ohne Git.

**Update von Clank 1.0.x:** Die Einstellungen der früheren Reiter (Mitschrift, Sprachassistent, Planung, MCP,
Gruppenchat) übernehmen die neuen KI-Tools beim ersten Öffnen automatisch. Die Tools selbst werden einzeln im Store
installiert.

## Erste Schritte
1. Im Hauptprogramm mindestens einen Assistenten verbinden (*Einstellungen › KI-Assistenten*).
2. Clank öffnen. Links steht die Liste der Chats, in der Mitte der Chat.
3. Frage eingeben und mit **Enter** senden.
4. Damit der Assistent Dateien sehen darf: Seitenleiste **Arbeitsbereich** › **Hinzufügen** › Ordner oder
   Repository, dann im KI-Zugriff von Clank mindestens Stufe 3 (Lesen) einstellen – der Hinweisbalken im
   Arbeitsbereich führt direkt dorthin.

## Funktionen im Detail

### Chat, Projekte und Arbeitsbereich

| Teil | Inhalt |
|---|---|
| Seitenleiste **Chats** | Chats nach Projekt gruppiert, Suche, **＋ Chat**, **＋ Projekt**; Rechtsklick: öffnen, umbenennen, Ordner öffnen, löschen, Projekt bearbeiten/löschen |
| Seitenleiste **Arbeitsbereich** | Freigegebene Ordner und Repositories des aktuellen Projekts (oder ohne Projekt) |
| Seitenleiste **Vorlagen** | siehe [Vorlagen](#vorlagen) |
| Mitte | Der Chat – wie die [Chatleiste](KI-Assistenten#die-chatleiste), mit denselben Chats und Projekten |
| Rechts | Dateiansicht mit Hervorhebung, **Änderungen zeigen (Git)**, **An den Chat anhängen** |

**Arbeitsbereich hinzufügen** (**Hinzufügen**):
- **Ordner oder Git-Repository …** – lokaler Ordner; erkennt Git automatisch. Rechtsklick › **Nur lesen** sperrt
  Änderungen.
- **Online-Repository (GitHub, GitLab, Azure DevOps) …** – Adresse, optional Zugriffstoken (nur für private
  Repositories, im Tresor) und Zweig. Online-Repositories sind nur lesbar; **Lokal klonen** legt eine lokale Kopie
  an (das Token wird dabei nur als Header übergeben, nie in `.git/config` gespeichert).

**Was der Assistent im Arbeitsbereich darf** (Stufe im KI-Zugriff von Clank):

| Funktion | Stufe |
|---|---|
| Arbeitsbereich beschreiben (Namen, Art, Zweig) | 2 – Übersicht |
| Dateien auflisten, lesen, durchsuchen; Git-Status, Verlauf, Diff | 3 – Lesen |
| Datei ändern (Bestätigung zeigt das Diff) | 4 – Ändern mit Bestätigung |
| Befehl ausführen (Bestätigung zeigt Befehl und Erklärung; Shell und Zeitlimit siehe [Einstellungen](#einstellungen)) | 4 – Ändern mit Bestätigung |

Pfade außerhalb der freigegebenen Ordner werden abgelehnt.

### Vorlagen
Seitenleiste **Vorlagen**: mitgelieferte (📌) und eigene (✎) Vorlagen für wiederkehrende Fragen. Doppelklick
setzt die Vorlage in das Eingabefeld. Platzhalter in doppelten geschweiften Klammern (`{{Skript}}`,
`{{Servername}}`) werden beim Verwenden abgefragt. Mitgeliefert: Skript erklären, Skript prüfen, PowerShell-Skript
schreiben, Protokoll analysieren, Fehlermeldung erklären, E-Mail an Anwender, Änderungseintrag, Runbook.
Mitgelieferte Vorlagen lassen sich als eigene kopieren und anpassen.

### Bildschirmfoto
Knopf **Bildschirmfoto** oben rechts: **Bereich auswählen …** (mit der Maus aufziehen, Esc bricht ab) oder
**Ganzer Bildschirm**. Das Fenster von OmniWrench wird dafür kurz ausgeblendet; das Bild landet im Bilder-Ordner
und hängt am Chat. Unter Wayland liefern manche Desktops ein leeres Bild – dann das Werkzeug des Desktops
nutzen und das Bild über 📎 anhängen.

### Die KI-Tools
Alle KI-Tools stehen im Bereich **KI-Tools** und nutzen dieselben Assistenten, dieselbe
[KI-Datenablage](KI-Assistenten#ki-datenablage) und die Standard-Assistenten aus *Einstellungen ›
KI-Funktionen*. Ergebnisse lassen sich mit **An den Chat** in Clank (oder die Chatleiste) schicken.

| Tool | Zweck |
|---|---|
| [Pixelizer – Bilder](Tool-Pixelizer) | Bilder erzeugen, mit Vorlagebild und Galerie |
| [Groovitron – Musik](Tool-Groovitron) | Musik erzeugen, abspielen, mit ffmpeg bearbeiten |
| [Vidcomic – Video](Tool-Vidcomic) | Videoclips erzeugen, abspielen, mit ffmpeg bearbeiten |
| [Q-Force – Gruppenchat](Tool-Q-Force) | Mehrere Assistenten besprechen ein Thema |
| [Infobot – Dokumente](Tool-Infobot) | Dokumente schreiben lassen, als HTML/PDF/ODT exportieren |
| [Orvus – Zeitpläne](Tool-Orvus) | Fragen zu festen Zeiten stellen |
| [Kreeli – Transkription](Tool-Kreeli) | Besprechungen live transkribieren, Sprecher erkennen, zusammenfassen |
| [Mr. Zurkon – Sprachassistent](Tool-Mr-Zurkon) | Weckwort, Spracherkennung, Antworten vorlesen |
| [Gadgetron – MCP](Tool-Gadgetron) | MCP-Server anbinden, OmniWrench als MCP-Server anbieten |

## Einstellungen
Rechtsklick auf Clank › *Einstellungen*:

| Einstellung | Standard | Bedeutung |
|---|---|---|
| Shell für Befehle | Automatisch | PowerShell unter Windows, bash unter Linux; oder fest PowerShell, cmd, bash |
| Zeitlimit je Befehl | 120 s | Befehle des Assistenten werden danach abgebrochen (10–900 s) |
| Ordner für geklonte Repositories | leer | Leer = `OmniWrench-Repos` im Benutzerordner |

Der Reiter **KI-Zugriff** in den Einstellungen legt Stufe und Verfremdung für Clank fest (siehe
[KI-Zugriff](KI-Zugriff-und-Verfremdung)). Welcher Assistent standardmäßig chattet, steht in *Einstellungen ›
KI-Funktionen*.

## Sicherheit und Datenschutz
- **Verbindungen:** zu den verbundenen KI-Anbietern (HTTPS) und zu GitHub/GitLab/Azure DevOps für
  Online-Repositories.
- **Verfremdung:** Chats werden nach dem KI-Zugriff von Clank verfremdet gesendet.
- **Änderungen:** Dateien schreiben und Befehle ausführen nur nach Bestätigung.
- **Gespeichert:** Chats und Projekte in der KI-Datenablage (verschlüsselt, falls eingestellt); Token für
  Repositories im Tresor; Einstellungen ohne Geheimnisse in den Tool-Einstellungen.

## Grenzen und bekannte Einschränkungen
- Microsoft 365 Copilot kann keine Programmfunktionen aufrufen (nur Text).
- Bildschirmfotos unter Wayland können leer sein.
- Online-Repositories sind nur lesbar.

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| „Clank braucht OmniWrench 0.9.0 oder neuer“ | OmniWrench aktualisieren |
| Assistent sieht den Arbeitsbereich nicht | KI-Zugriff von Clank auf Stufe 3 oder 4 stellen |
| Kein Assistent zur Auswahl | In *Einstellungen › KI-Assistenten* verbinden, kostenlos z. B. mit [Ollama](KI-lokal-mit-Ollama) |
| Reiter Bilder, Mitschrift usw. fehlen nach dem Update | Seit 1.1.0 eigene KI-Tools – im Store installieren (siehe [Die KI-Tools](#die-ki-tools)) |

## Versionen

| Version | Änderungen |
|---|---|
| 1.1.0 | Aufgeteilt: Bilder, Musik, Video, Gruppenchat, Dokumente, Zeitpläne, Transkription, Sprachassistent und MCP sind eigene KI-Tools; Clank ist der KI-Chat. Standard-Assistenten und Audio-Ausgabe jetzt in *Einstellungen › KI-Funktionen* |
| 1.0.2 | Reiter **KI-Übersicht**; Sprachassistent mit Whisper lokal, Piper, Systemstimmen; Spracherkennung mit Gemini, Groq, Mistral; Gruppenchat wartet bei Minutenlimits |
| 1.0.1 | Mitschrift: deutlicher Hinweis (Art. 9 DSGVO) vor dem Verwenden von Sprecherprofilen |
| 1.0.0 | Erste Version (damals „KI-Studio“ mit allen Funktionen in Reitern) |

## Siehe auch
- [KI-Assistenten](KI-Assistenten)
- [KI lokal mit Ollama](KI-lokal-mit-Ollama)
- [KI-Zugriff und Verfremdung](KI-Zugriff-und-Verfremdung)
- [Datenablage und Datenschutz](Datenablage-und-Datenschutz)
