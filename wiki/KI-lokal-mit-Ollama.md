# KI lokal mit Ollama

> **Kurz:** So läuft KI in OmniWrench ganz auf dem eigenen Rechner – kostenlos, ohne Konto, ohne dass Daten das
> Haus verlassen. Ollama für den Chat lässt sich direkt aus OmniWrench installieren und mit Modellen bestücken;
> Sprache (Whisper, Piper, Vosk) und ffmpeg richten die KI-Tools bei ihrer Installation selbst ein.

## Inhalt
- [Überblick: was lokal geht](#überblick-was-lokal-geht)
- [Ollama einrichten](#ollama-einrichten)
- [Welches Modell?](#welches-modell)
- [Ollama auf einem anderen Rechner](#ollama-auf-einem-anderen-rechner)
- [Sprache offline](#sprache-offline)
- [ffmpeg](#ffmpeg)
- [Andere lokale Programme](#andere-lokale-programme)
- [Fehlerbehebung](#fehlerbehebung)

## Überblick: was lokal geht

| Funktion | Lokal mit | Einrichtung |
|---|---|---|
| Chat, Funktionen, Dokumente, Zeitpläne, Gruppenchat | [Ollama](https://ollama.com) | In OmniWrench: Assistent „Ollama“ › **🦙 Ollama einrichten …** |
| Spracherkennung (Transkription, Sprachassistent) | Whisper lokal (faster-whisper) | Bei der Installation von [Kreeli](Tool-Kreeli) bzw. [Mr. Zurkon](Tool-Mr-Zurkon) |
| Weckwort | Vosk | Bei der Installation von Mr. Zurkon |
| Vorlesen | Piper oder die Systemstimme | Bei der Installation von Mr. Zurkon |
| Musik/Video bearbeiten | ffmpeg | Bei der Installation von [Groovitron](Tool-Groovitron) / [Vidcomic](Tool-Vidcomic) |
| Bilder, Musik, Video erzeugen | – | Nur über Anbieter; lokale Bildprogramme siehe [unten](#andere-lokale-programme) |

## Ollama einrichten
1. *Extras › Einstellungen › KI-Assistenten* › **Hinzufügen** › Anbieter **Ollama**.
2. Im Dialog **🦙 Ollama einrichten (Installation, Modelle) …** drücken. Das Fenster zeigt, ob Ollama läuft.
3. **Windows:** **Ollama installieren** – OmniWrench nimmt winget, sonst das offizielle Setup von ollama.com
   (ca. 1 GB, für den angemeldeten Benutzer, ohne Administratorrechte). Der Fortschritt steht als Balken im Fenster.
   **Linux:** Das Fenster zeigt den offiziellen Installationsbefehl; **Befehl kopieren**, im Terminal ausführen
   (braucht sudo), dann das Fenster erneut öffnen.
4. Läuft Ollama nicht, **Ollama starten**.
5. Unter **Modelle** ein empfohlenes Modell wählen (oder einen Namen aus [ollama.com/library](https://ollama.com/library)
   eintragen) und **Modell laden** drücken. Der Download zeigt Prozent und Größe. Ein abgebrochener Download setzt
   beim nächsten **Modell laden** fort.
6. Fenster schließen – die Modellliste der Verbindung ist schon aktualisiert. Modell wählen, speichern.
7. Optional in *Einstellungen › KI-Funktionen* Ollama als Standard für einzelne Funktionen festlegen.

**Löschen** entfernt ein Modell wieder von der Festplatte.

## Welches Modell?
Faustregel: Das Modell sollte mit etwas Luft in den Grafikspeicher (oder Arbeitsspeicher) passen. Kleine Modelle
antworten schnell, große können Funktionen und lange Texte besser.

| Modell | Größe | Für |
|---|---|---|
| `llama3.2:3b` | 2 GB | schnell, wenig Speicher – Notebooks ohne Grafikkarte |
| `qwen3:8b` | 5,2 GB | gute Allround-Wahl mit Funktionen (Tool-Aufrufe) |
| `gemma3:12b` | 8,1 GB | versteht Bilder (Bildschirmfotos, Fehlermeldungen) |
| `gpt-oss:20b` | 14 GB | stark, braucht 16 GB |
| `mistral-small3.2` | 15 GB | stark, aus der EU |

Das sind die fünf Empfehlungen (★). Die Auswahl im Einrichtungsfenster enthält rund 40 Modelle, nach Größe sortiert
und nach Zweck beschriftet:

| Zweck | Beispiele |
|---|---|
| winzig (unter 2 GB) | `qwen3:0.6b`, `gemma3:1b`, `llama3.2:1b`, `qwen3:1.7b` |
| klein | `qwen3:4b`, `phi4-mini`, `granite3.3:2b` |
| Allround | `llama3.1:8b`, `granite3.3:8b`, `mistral-nemo`, `phi4`, `qwen3:14b`, `olmo2:13b` |
| viele Sprachen / Übersetzen | `aya-expanse:8b` |
| versteht Bilder | `gemma3:4b`, `granite3.2-vision`, `minicpm-v`, `qwen2.5vl:7b`, `llama3.2-vision`, `gemma3:27b` |
| denkt Schritt für Schritt | `deepseek-r1:8b`/`14b`/`32b`, `magistral` (EU) |
| Programmieren | `qwen2.5-coder:7b`/`14b`, `deepseek-coder-v2:16b`, `devstral` (EU), `qwen3-coder:30b` |
| stark (16–24 GB) | `qwen3:30b`, `qwen3:32b` |
| Profi-Hardware (48 GB+) | `llama3.3`, `gpt-oss:120b`, `qwen3:235b` |

✔ markiert bereits geladene Modelle, ⚠ Modelle, die größer als der Arbeitsspeicher des PCs sind. Jeder andere Name
aus dem Katalog lässt sich eintippen; der Link **Alle Modelle auf ollama.com …** öffnet den Katalog.

Für die eingebauten Funktionen (DHCP, DNS, Arbeitsbereich, Wetter …) ein Modell mit Funktionsaufrufen wählen
(z. B. `qwen3`, `gpt-oss`, `mistral-small3.2`).

## Ollama auf einem anderen Rechner
Läuft Ollama auf einem Server im Netz, in der Verbindung die Adresse eintragen (z. B.
`http://ki-server:11434/v1`). Das Einrichtungsfenster zeigt dann Status und Modelle dieses Servers und kann dort
Modelle laden und löschen; Installieren und Starten gehen nur auf dem eigenen Rechner. Auf dem Server muss Ollama
im Netz lauschen (`OLLAMA_HOST=0.0.0.0`) – nur in vertrauenswürdigen Netzen, Ollama hat keine Anmeldung.

## Sprache offline
[Kreeli](Tool-Kreeli) und [Mr. Zurkon](Tool-Mr-Zurkon) fragen bei der Installation, welche Offline-Teile sie
gleich mit einrichten sollen (vorbelegt, abwählbar): Whisper lokal (ca. 630 MB), Vosk fürs Weckwort (ca. 60 MB),
Piper-Stimmen (ca. 80 MB). Alles landet im gemeinsamen KI-Ordner (`ai` im lokalen Datenordner von OmniWrench) und
wird von allen KI-Tools geteilt. Weitere Whisper-Modelle und Piper-Stimmen lassen sich später im Tool laden.

## ffmpeg
Unter Windows lädt die Installation von Groovitron bzw. Vidcomic auf Wunsch einen ffmpeg-Build (BtbN, GitHub,
ca. 100 MB) in den gemeinsamen KI-Ordner. Unter Linux kommt ffmpeg aus der Paketverwaltung
(`sudo apt install ffmpeg`).

## Andere lokale Programme
Diese Programme richtet OmniWrench nicht selbst ein, sie lassen sich aber als Assistent verbinden (*Hinzufügen* ›
Anbieter, Adresse eintragen):

| Programm | Wofür | Hinweis |
|---|---|---|
| [LM Studio](https://lmstudio.ai) | Chat mit Oberfläche zum Modellwählen | Lokalen Server in LM Studio starten (Port 1234) |
| [LocalAI](https://localai.io) | OpenAI-kompatibler Server für Chat, Bilder, Sprache | Docker: `docker run -p 8080:8080 localai/localai`; als „OpenAI-kompatibel“ verbinden |
| [ComfyUI](https://www.comfy.org) | Bilderzeugung lokal | Wird für Bilder/Video noch nicht direkt unterstützt |
| llama.cpp, vLLM | Server für eigene Hardware | Siehe [KI-Anbieter](KI-Anbieter) |

## Fehlerbehebung

| Problem | Ursache / Lösung |
|---|---|
| „Ollama ist installiert, läuft aber nicht“ | **Ollama starten** oder das Ollama-Symbol im Infobereich prüfen |
| Installation unter Windows scheitert | winget fehlt oder ist gesperrt – OmniWrench nimmt dann das Setup; sonst [ollama.com/download](https://ollama.com/download) manuell |
| Modell lädt sehr langsam / bricht ab | Download erneut starten, Ollama setzt fort |
| Antworten sehr langsam | Modell zu groß für den Speicher – kleineres Modell wählen |
| Assistent ruft keine Funktionen auf | Modell ohne Funktionsaufrufe – z. B. `qwen3:8b` nehmen |

## Siehe auch
- [KI-Assistenten](KI-Assistenten)
- [KI-Anbieter › Ollama](KI-Anbieter#ollama)
- [Clank – KI-Chat](Tool-Clank)
