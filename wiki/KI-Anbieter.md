# KI-Anbieter

> **Kurz:** Alle KI-Anbieter, die OmniWrench kennt: was sie können, wofür sie sich eignen, was sie kosten und
> welche Modelle es gibt. Die Liste kommt aus dem Anbieterkatalog und wird über den Store aktualisiert.
> Einrichten: [KI-Assistenten](KI-Assistenten#assistenten-verbinden).

**Gilt für:** Hauptprogramm ab Version 0.9.0 · **Stand des Katalogs:** 2026-10-29 · **112 Einträge**

## Inhalt
- [Welcher Anbieter passt?](#welcher-anbieter-passt)
- [Kostenlos testen](#kostenlos-testen)
- [Modelle auswählen](#modelle-auswählen)
- [Inhalte für Erwachsene (NSFW)](#inhalte-für-erwachsene-nsfw)
- [Große Chat-Anbieter](#große-chat-anbieter)
- [EU und Deutschland](#eu-und-deutschland)
- [Unternehmen und Cloud](#unternehmen-und-cloud)
- [Sammelanbieter und schnelle Plattformen](#sammelanbieter-und-schnelle-plattformen)
- [Anbieter aus China](#anbieter-aus-china)
- [Lokal auf dem eigenen Rechner oder Server](#lokal-auf-dem-eigenen-rechner-oder-server)
- [Bilder, Musik, Video und Sprache](#bilder-musik-video-und-sprache)
- [Benutzerdefiniert](#benutzerdefiniert)
- [Nicht oder nur indirekt verfügbar](#nicht-oder-nur-indirekt-verfügbar)
- [Siehe auch](#siehe-auch)

## Welcher Anbieter passt?

| Wunsch | Empfehlung |
|---|---|
| Einfach loslegen, beste Allround-Qualität | [ChatGPT / OpenAI](#chatgpt--openai), [Claude](#claude) oder [Gemini](#gemini) |
| Kostenlos ausprobieren | [Gemini](#gemini), [Groq](#groq), [OpenRouter](#openrouter) (Modelle mit `:free`), [GitHub Models](#github-models) |
| Daten dürfen das Haus nicht verlassen | [Ollama](#ollama), [LM Studio](#lm-studio), [Foundry Local](#foundry-local) oder ein eigener Server ([vLLM](#vllm)) |
| Verarbeitung in Deutschland/EU | [Mistral](#mistral-le-chat), [IONOS](#ionos-ai-model-hub), [STACKIT](#stackit-ai-model-serving), [Aleph Alpha](#aleph-alpha-phariaai) |
| Im Unternehmen mit Microsoft 365 | [Microsoft 365 Copilot](#microsoft-365-copilot) oder [Azure OpenAI](#azure-openai--ai-foundry) |
| Viele Modelle mit einem Konto | [OpenRouter](#openrouter), [Requesty](#requesty), [Vercel AI Gateway](#vercel-ai-gateway) |
| Aktuelle Infos aus dem Web | [Perplexity Sonar](#perplexity-sonar), [Gemini](#gemini), [Grok](#grok) |
| Programmieren und Skripte | [Claude](#claude), [ChatGPT / OpenAI](#chatgpt--openai), [Mistral](#mistral-le-chat) (Codestral) |
| Sehr schnelle Antworten | [Groq](#groq), [Cerebras](#cerebras), [SambaNova Cloud](#sambanova-cloud) |

## Kostenlos testen

Diese Anbieter haben eine dauerhaft kostenlose Stufe mit Grenzen (Anfragen pro Minute und Tag). Stand: Herbst 2026,
die Grenzen ändern sich häufig.

| Anbieter | Kostenlos | Hinweis |
|---|---|---|
| [Gemini](#gemini) | je nach Modell 5–15 Anfragen/Min., bis 1.500/Tag | Eingaben werden außerhalb von EU/UK/EWR zum Training genutzt |
| [Groq](#groq) | ca. 30 Anfragen/Min., 1.000/Tag | sehr schnell |
| [OpenRouter](#openrouter) | 50 Anfragen/Tag mit `:free`-Modellen | 1.000/Tag nach einmaliger Aufladung von 10 $ |
| [Cerebras](#cerebras) | ca. 1 Mio. Tokens/Tag |  |
| [Mistral](#mistral-le-chat) | Experiment-Stufe | nur mit Zustimmung zum Training |
| [GitHub Models](#github-models) | ca. 15 Anfragen/Min., 150–1.000/Tag | GitHub-Konto genügt |
| [Cloudflare Workers AI](#cloudflare-workers-ai) | tägliches Gratiskontingent |  |
| [NVIDIA NIM](#nvidia-nim-buildnvidiacom) | kostenlos für Entwickler |  |
| [SambaNova Cloud](#sambanova-cloud) | kostenlose Stufe |  |
| [Hugging Face](#hugging-face-inference-providers), [Cohere](#cohere-command) | kleine Kontingente | Cohere nur nicht-kommerziell |
| Lokal ([Ollama](#ollama), [LM Studio](#lm-studio) …) | unbegrenzt | eigene Hardware |

> **Achtung:** Bei kostenlosen Stufen nutzen manche Anbieter die Eingaben zum Training. Keine Firmendaten, Kennwörter
> oder personenbezogenen Daten eingeben. Die [Verfremdung](KI-Zugriff-und-Verfremdung) hilft, ersetzt das aber nicht.

## Modelle auswählen

Jeder Anbieter hat mehrere Modelle, die sich in Qualität, Geschwindigkeit und Preis unterscheiden. Das Modell wird
oben in der Chatleiste gewählt (Knopf neben dem Assistenten, auch mitten im Chat) und gilt dann für diesen Assistenten.

- OmniWrench fragt die Modellliste **direkt beim Anbieter** ab (spätestens alle 12 Stunden, oder mit
  **Beim Anbieter abfragen**). Angezeigt werden nur Modelle, die es dort wirklich gibt.
- **★** markiert das empfohlene Modell aus dem Katalog.
- **Rot** mit ⚠: Das Modell meldet der Anbieter nicht (mehr). War es die Vorgabe aus dem Katalog, wechselt OmniWrench
  von selbst auf das beste verfügbare Modell und sagt Bescheid. Selbst eingetragene Namen bleiben unverändert.
- Liefert ein Anbieter keine Liste (z. B. manche Firmen-Endpunkte), steht „Verfügbarkeit unbekannt“. Ein Modellname
  lässt sich dann ins Suchfeld tippen und mit **Modell „…“ verwenden** übernehmen.
- **Auch andere Modelle zeigen** blendet Modelle ein, die nicht chatten (Bilder, Sprache, Einbettungen).

Die Kurzbeschreibung der Modelle leitet OmniWrench aus dem Namen ab:

| Merkmal | Bedeutung | Typische Namen |
|---|---|---|
| **Stärkstes Modell** | Beste Antworten bei schwierigen Fragen, dafür langsamer und teurer. | pro, opus, ultra, large, max |
| **Ausgewogen** | Gute Antworten bei mittleren Kosten. Eine sinnvolle Grundeinstellung. | sonnet, medium, plus |
| **Schnell** | Antwortet schnell und kostet wenig. Reicht für die meisten Alltagsfragen. | flash, turbo, fast |
| **Leicht und günstig** | Kleinste und günstigste Variante, für einfache Aufgaben und große Textmengen. | lite, mini, nano, haiku, small |
| **Denkt länger nach** | Arbeitet eine Aufgabe Schritt für Schritt durch, bevor es antwortet. Gut für Analysen und Fehlersuche, dauert länger. | reasoner, thinking, o3, r1 |
| **Für Code** | Auf Programmcode und Skripte spezialisiert. | code, coder, codestral |
| **Versteht Bilder** | Kann auch angehängte Bilder und Bildschirmfotos lesen. | vision, vl, pixtral |
| **Kostenlos** | Bei diesem Anbieter kostenlos, meist mit engen Grenzen. | …:free (OpenRouter) |
| **Vorschau** | Testversion: kann sich ändern oder kurzfristig wegfallen. | preview, exp, beta |

Faustregel: für den Alltag ein schnelles Modell (Flash, Mini, Sonnet), für schwierige Analysen das stärkste oder ein
Nachdenkmodell.

## Inhalte für Erwachsene (NSFW)

Einige Anbieter können je nach Modell Inhalte für Erwachsene erzeugen. Sie sind in der Liste mit **🔞 NSFW** markiert.

- Standardmäßig weist OmniWrench solche Assistenten an, **arbeitstauglich** zu bleiben.
- In den Einstellungen des Assistenten gibt es den Schalter **NSFW-Inhalte erlauben (ab 18)**. Beim Einschalten
  fragt OmniWrench nach, ob Volljährigkeit und Erlaubnis im Unternehmen gegeben sind. Die Verantwortung liegt beim
  Benutzer.
- Ist der Schalter an, zeigt die Chatleiste 🔞 vor dem Modellnamen.
- Die Regeln des Anbieters gelten immer; OmniWrench hebt keine Filter des Anbieters auf.
- Bei Anbietern ohne diese Fähigkeit gibt es den Schalter nicht.

## Große Chat-Anbieter

Die bekannten Assistenten mit eigenen Modellen.

### ChatGPT / OpenAI

Die GPT-Modelle hinter ChatGPT. Anmeldung mit dem ChatGPT-Abo oder per API-Schlüssel.

**Stärken:** Sehr gute Allrounder, starke Programmfunktionen und Bildverständnis, Bilderzeugung, Websuche. Größtes Ökosystem.

- **Hersteller:** OpenAI (USA)
- **Anmeldung:** Mit ChatGPT anmelden, API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild, Websuche, Sprache
- **Voraussetzung:** API-Schlüssel: Guthaben beim Anbieter · Mit ChatGPT anmelden: ChatGPT Plus oder Pro. Mit Free geht es nicht, Go nennt OpenAI derzeit nicht. Die Nutzung zählt auf das Kontingent des Abos.
- **Empfohlene Modelle:** `gpt-6.1-sol`, `gpt-6-astra`, `gpt-6.1-terra`, `gpt-6-luna`
- [Schlüssel/Konto](https://platform.openai.com/api-keys) · [Dokumentation](https://platform.openai.com/docs)

### Claude

Die Claude-Modelle von Anthropic (Fable, Opus, Sonnet, Haiku).

**Stärken:** Sehr stark bei Code, langen Texten, Analysen und sorgfältigem Befolgen von Anweisungen. Großes Kontextfenster.

- **Hersteller:** Anthropic (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Websuche
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-5-5`
- **Hinweis:** Claude-Abos (Pro/Max) dürfen nicht in anderen Programmen genutzt werden. Bitte einen API-Schlüssel aus der Claude Console verwenden.
- [Schlüssel/Konto](https://console.anthropic.com/settings/keys) · [Dokumentation](https://docs.claude.com)

### Gemini

Googles Gemini-Modelle über Google AI Studio.

**Stärken:** Kostenlose Stufe, sehr großes Kontextfenster, schnelle Flash-Modelle, dazu Bilder, Musik (Lyria) und Video. Websuche über Google.

- **Hersteller:** Google (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild, Musik, Video, Websuche, Sprache
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- **Empfohlene Modelle:** `gemini-3.8-flash`, `gemini-4-argon`, `gemini-3.1-pro-preview`, `gemini-3.6-flash`
- [Schlüssel/Konto](https://aistudio.google.com/apikey) · [Dokumentation](https://ai.google.dev/gemini-api/docs)

### Grok

Die Grok-Modelle von xAI.

**Stärken:** Aktuelles Wissen, lockerer Ton, schnelle Code-Modelle, Bild- und Videoerzeugung. Weniger streng gefiltert, daher NSFW-fähig.

- **Hersteller:** xAI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild, Video
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `grok-4.7`, `grok-4.20`, `grok-code-fast`
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://console.x.ai) · [Dokumentation](https://docs.x.ai)

### Perplexity Sonar

Suchmaschine mit KI-Antworten (Sonar-Modelle).

**Stärken:** Antworten mit aktuellen Quellen aus dem Web, gut für Recherche und Fragen zu neuen Versionen oder Sicherheitslücken.

- **Hersteller:** Perplexity (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Websuche
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `sonar-pro`, `sonar`, `sonar-reasoning-pro`
- [Schlüssel/Konto](https://www.perplexity.ai/settings/api) · [Dokumentation](https://docs.perplexity.ai)

### Cohere Command

Kanadischer Anbieter mit Fokus auf Unternehmen (Command-Modelle).

**Stärken:** Gute Suche in eigenen Dokumenten (RAG), mehrsprachig, kostenloser Testschlüssel für nicht-kommerzielle Nutzung.

- **Hersteller:** Cohere (Kanada)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- **Empfohlene Modelle:** `command-a-03-2025`, `command-r-plus`
- [Schlüssel/Konto](https://dashboard.cohere.com/api-keys) · [Dokumentation](https://docs.cohere.com)

### Venice AI

Venice AI: privatsphäreorientierter Anbieter mit offenen Modellen.

**Stärken:** Speichert keine Chats, wenig Filter, NSFW-fähig.

- **Hersteller:** Venice (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://venice.ai/settings/api) · [Dokumentation](https://docs.venice.ai)

### AI21 (Jamba)

AI21 Labs (Israel) mit den Jamba-Modellen.

**Stärken:** Sehr lange Kontexte, effizient bei großen Dokumenten.

- **Hersteller:** AI21 Labs (Israel)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `jamba-large`, `jamba-mini`
- [Schlüssel/Konto](https://studio.ai21.com/account/api-key) · [Dokumentation](https://docs.ai21.com)

### Reka

Reka: multimodale Modelle.

**Stärken:** Verstehen Text, Bilder, Audio und Video.

- **Hersteller:** Reka AI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://platform.reka.ai/apikeys) · [Dokumentation](https://docs.reka.ai)

### Upstage Solar

Upstage (Korea) mit den Solar-Modellen.

**Stärken:** Kompakt und günstig, starke Dokumentenverarbeitung.

- **Hersteller:** Upstage (Südkorea)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `solar-pro2`, `solar-mini`
- [Schlüssel/Konto](https://console.upstage.ai/api-keys) · [Dokumentation](https://console.upstage.ai/docs)

### Inception (Mercury)

Inception Labs mit den Mercury-Diffusionsmodellen.

**Stärken:** Ungewöhnlich schnelle Textausgabe, gut für Code-Vervollständigung.

- **Hersteller:** Inception Labs (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `mercury`, `mercury-coder`
- [Schlüssel/Konto](https://platform.inceptionlabs.ai) · [Dokumentation](https://docs.inceptionlabs.ai)

## EU und Deutschland

Verarbeitung in Europa, für strengere Datenschutzvorgaben.

### Mistral (Le Chat)

Französischer Anbieter mit eigenen offenen und kommerziellen Modellen.

**Stärken:** Verarbeitung in der EU, gute Mehrsprachigkeit, Codestral für Code, kostenlose Experimentierstufe.

- **Hersteller:** Mistral AI (Frankreich)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Sprache
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- **Empfohlene Modelle:** `mistral-large-latest`, `mistral-medium-latest`, `mistral-small-latest`, `codestral-latest`
- [Schlüssel/Konto](https://console.mistral.ai/api-keys) · [Dokumentation](https://docs.mistral.ai)

### IONOS AI Model Hub

IONOS AI Model Hub mit offenen Modellen in deutschen Rechenzentren.

**Stärken:** Hosting in Deutschland, DSGVO-freundlich, Abrechnung über IONOS.

- **Hersteller:** IONOS (Deutschland)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://dcd.ionos.com) · [Dokumentation](https://docs.ionos.com/cloud/ai/ai-model-hub)

### STACKIT AI Model Serving

STACKIT (Schwarz Gruppe) mit offenen Modellen in deutschen Rechenzentren.

**Stärken:** Souveräne deutsche Cloud, geeignet für strenge Datenschutzvorgaben.

- **Hersteller:** STACKIT (Deutschland)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://portal.stackit.cloud) · [Dokumentation](https://docs.stackit.cloud/products/data-and-ai/ai-model-serving/)

### T-Systems AI Foundation Services

T-Systems AI Foundation Services (Telekom).

**Stärken:** Deutsche Cloud mit Unternehmensvertrag, Zugang zu mehreren Modellfamilien.

- **Hersteller:** T-Systems (Deutschland)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://www.t-systems.com) · [Dokumentation](https://docs.llmhub.t-systems.net)

### mittwald AI Hosting

mittwald AI Hosting für Kunden des Hosters mittwald.

**Stärken:** Hosting in Deutschland, einfache Einrichtung für bestehende Kunden.

- **Hersteller:** mittwald (Deutschland)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://studio.mittwald.de) · [Dokumentation](https://developer.mittwald.de)

### Scaleway Generative APIs

Scaleway Generative APIs (Frankreich).

**Stärken:** EU-Hosting, günstige offene Modelle, Abrechnung nach Verbrauch.

- **Hersteller:** Scaleway (Frankreich)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://console.scaleway.com) · [Dokumentation](https://www.scaleway.com/en/docs/generative-apis/)

### OVHcloud AI Endpoints

OVHcloud AI Endpoints (Frankreich).

**Stärken:** EU-Hosting, offene Modelle, einfache Preise.

- **Hersteller:** OVHcloud (Frankreich)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://www.ovh.com/manager) · [Dokumentation](https://help.ovhcloud.com)

### Aleph Alpha PhariaAI

Aleph Alpha PhariaAI aus Heidelberg.

**Stärken:** Für Behörden und regulierte Branchen, nachvollziehbare Antworten, Betrieb in Deutschland oder vor Ort.

- **Hersteller:** Aleph Alpha (Deutschland)
- **Anmeldung:** API-Schlüssel, Eigenes OAuth
- **Kann:** Chat
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Dokumentation](https://docs.aleph-alpha.com)

### Nebius Token Factory

Nebius Token Factory (Niederlande/Finnland): offene Modelle.

**Stärken:** Rechenzentren in Europa, günstig, Startguthaben.

- **Hersteller:** Nebius (Niederlande)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://tokenfactory.nebius.com) · [Dokumentation](https://docs.tokenfactory.nebius.com)

### Regolo.ai

Regolo.ai von Seeweb (Italien).

**Stärken:** Hosting in Italien (EU), mit Ökostrom betrieben.

- **Hersteller:** Seeweb (Italien)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://dashboard.regolo.ai) · [Dokumentation](https://docs.regolo.ai)

## Unternehmen und Cloud

Modelle im eigenen Cloud-Konto oder mit Unternehmensvertrag.

### Microsoft 365 Copilot

Microsoft 365 Copilot im Unternehmen, angebunden über Microsoft Graph.

**Stärken:** Kennt die eigenen Microsoft-365-Daten (Mails, Dateien, Teams) im Rahmen der Berechtigungen. Nur Text, keine Programmfunktionen.

- **Hersteller:** Microsoft (USA)
- **Anmeldung:** Microsoft-Konto (Entra ID)
- **Kann:** Chat
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- **Hinweis:** Benötigt eine Microsoft-365-Copilot-Lizenz. Vorschau-Schnittstelle: nur Text, keine Programmfunktionen. Erfahrungen gern ins Wiki.
- [Dokumentation](https://learn.microsoft.com/microsoft-365/copilot/extensibility/api/ai-services/chat/overview)

### Azure OpenAI / AI Foundry

OpenAI-Modelle im eigenen Azure-Abonnement (Azure AI Foundry).

**Stärken:** Daten bleiben im gewählten Azure-Rechenzentrum, Abrechnung über den Microsoft-Vertrag, Unternehmens-Compliance.

- **Hersteller:** Microsoft (USA)
- **Anmeldung:** API-Schlüssel, Eigenes OAuth
- **Kann:** Chat, Funktionen, Bildeingabe, Bild
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- **Empfohlene Modelle:** `gpt-6.1-sol`, `gpt-6-astra`, `gpt-5.5`, `gpt-5.5-mini`
- [Schlüssel/Konto](https://portal.azure.com) · [Dokumentation](https://learn.microsoft.com/azure/ai-foundry/openai/)

### Amazon Bedrock

Amazon Bedrock: Modelle vieler Hersteller (Claude, Llama, Mistral, Nova) im AWS-Konto.

**Stärken:** Eine AWS-Abrechnung für viele Modelle, Region frei wählbar (Standard Frankfurt).

- **Hersteller:** Amazon (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://console.aws.amazon.com/bedrock) · [Dokumentation](https://docs.aws.amazon.com/bedrock/)

### Google Vertex AI

Google Vertex AI: Gemini und Partnermodelle im Google-Cloud-Projekt.

**Stärken:** Unternehmensverträge, Region wählbar, gleiche Modelle wie AI Studio mit Cloud-Verwaltung.

- **Hersteller:** Google (USA)
- **Anmeldung:** API-Schlüssel, Eigenes OAuth
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- **Empfohlene Modelle:** `google/gemini-3.8-flash`, `google/gemini-3.1-pro-preview`
- [Schlüssel/Konto](https://console.cloud.google.com/vertex-ai) · [Dokumentation](https://cloud.google.com/vertex-ai/docs)

### IBM watsonx

IBM watsonx.ai mit Granite- und Partnermodellen.

**Stärken:** Für Unternehmen mit IBM-Umgebung, Governance-Funktionen.

- **Hersteller:** IBM (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://cloud.ibm.com/iam/apikeys) · [Dokumentation](https://www.ibm.com/docs/en/watsonx)

### Databricks Model Serving

Databricks Model Serving: Modelle im eigenen Databricks-Arbeitsbereich.

**Stärken:** Daten bleiben in der eigenen Datenplattform, Unternehmens-Governance.

- **Hersteller:** Databricks (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://docs.databricks.com/en/dev-tools/auth/pat.html) · [Dokumentation](https://docs.databricks.com/en/machine-learning/model-serving/)

### Snowflake Cortex

Snowflake Cortex: Modelle direkt im Snowflake-Konto.

**Stärken:** Daten bleiben in Snowflake, Abrechnung über den bestehenden Vertrag.

- **Hersteller:** Snowflake (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Cloud-Konto beim Anbieter (z. B. Azure-, AWS- oder Google-Cloud-Abonnement) mit freigeschaltetem Modell.
- [Schlüssel/Konto](https://docs.snowflake.com/en/user-guide/programmatic-access-tokens) · [Dokumentation](https://docs.snowflake.com/en/user-guide/snowflake-cortex/open_ai_sdk)

## Sammelanbieter und schnelle Plattformen

Ein Konto für viele Modelle, oft offene Modelle (Llama, Qwen, DeepSeek …) zu günstigen Preisen.

### OpenRouter

Sammelanbieter: ein Schlüssel für Hunderte Modelle fast aller Hersteller.

**Stärken:** Modelle frei wechseln, viele kostenlose Modelle (:free), Anmeldung per Browser möglich, eine Abrechnung.

- **Hersteller:** OpenRouter (USA)
- **Anmeldung:** Mit OpenRouter anmelden, API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild, Websuche
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- **Empfohlene Modelle:** `anthropic/claude-sonnet-5.5`, `openai/gpt-5.5`, `google/gemini-3.8-flash`, `x-ai/grok-4.7`
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://openrouter.ai/settings/keys) · [Dokumentation](https://openrouter.ai/docs)

### Together AI

Together AI: offene Modelle (Llama, Qwen, DeepSeek …) in der Cloud.

**Stärken:** Große Auswahl offener Modelle, schnell und günstig, auch Bilder.

- **Hersteller:** Together AI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://api.together.ai/settings/api-keys) · [Dokumentation](https://docs.together.ai)

### Fireworks AI

Fireworks AI: schnelle Plattform für offene Modelle.

**Stärken:** Sehr kurze Antwortzeiten, Startguthaben zum Testen.

- **Hersteller:** Fireworks (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://fireworks.ai/account/api-keys) · [Dokumentation](https://docs.fireworks.ai)

### DeepInfra

DeepInfra: offene Modelle zum günstigen Verbrauchspreis.

**Stärken:** Sehr günstig, große Auswahl.

- **Hersteller:** DeepInfra (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://deepinfra.com/dash/api_keys) · [Dokumentation](https://deepinfra.com/docs)

### Groq

Groq: offene Modelle auf eigenen Spezialchips.

**Stärken:** Extrem schnelle Antworten, kostenlose Stufe, auch Spracherkennung (Whisper).

- **Hersteller:** Groq (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Sprache
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://console.groq.com/keys) · [Dokumentation](https://console.groq.com/docs)

### Cerebras

Cerebras: offene Modelle auf Wafer-Scale-Chips.

**Stärken:** Sehr schnell, großzügige kostenlose Stufe.

- **Hersteller:** Cerebras (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://cloud.cerebras.ai) · [Dokumentation](https://inference-docs.cerebras.ai)

### Hugging Face Inference Providers

Hugging Face Inference Providers: Modelle vom Hugging Face Hub über verschiedene Rechenanbieter.

**Stärken:** Riesige Modellauswahl, kleines kostenloses Kontingent.

- **Hersteller:** Hugging Face (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://huggingface.co/settings/tokens) · [Dokumentation](https://huggingface.co/docs/inference-providers)

### Vercel AI Gateway

Vercel AI Gateway: Sammelanbieter für viele Hersteller.

**Stärken:** Ein Schlüssel für viele Modelle, Ausfallsicherheit über mehrere Anbieter.

- **Hersteller:** Vercel (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://vercel.com/dashboard) · [Dokumentation](https://vercel.com/docs/ai-gateway)

### GitHub Models

GitHub Models: Modelle vieler Hersteller (OpenAI, Meta, Mistral, DeepSeek …) mit dem GitHub-Konto.

**Stärken:** Kostenlos zum Testen mit einem GitHub-Token (Recht „models:read“), ideal zum Ausprobieren.

- **Hersteller:** GitHub (Microsoft) (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- **Empfohlene Modelle:** `openai/gpt-5.5-mini`, `openai/gpt-5.5`, `meta/llama-4-maverick-17b-128e-instruct-fp8`
- [Schlüssel/Konto](https://github.com/settings/personal-access-tokens) · [Dokumentation](https://docs.github.com/en/github-models)

### Cloudflare Workers AI

Cloudflare Workers AI: offene Modelle im weltweiten Cloudflare-Netz.

**Stärken:** Tägliches Gratiskontingent, schnelle Antworten. Adresse braucht die eigene Konto-ID.

- **Hersteller:** Cloudflare (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://dash.cloudflare.com/profile/api-tokens) · [Dokumentation](https://developers.cloudflare.com/workers-ai/)

### NVIDIA NIM (build.nvidia.com)

NVIDIA NIM über build.nvidia.com: optimierte offene Modelle.

**Stärken:** Kostenlos für Entwickler zum Testen, sehr viele Modelle (Llama, Nemotron, DeepSeek, Qwen).

- **Hersteller:** NVIDIA (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://build.nvidia.com) · [Dokumentation](https://docs.api.nvidia.com)

### SambaNova Cloud

SambaNova Cloud: offene Modelle auf eigenen Chips.

**Stärken:** Sehr schnell, kostenlose Stufe.

- **Hersteller:** SambaNova (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter. Es gibt eine kostenlose Stufe mit Begrenzungen, darüber wird nach Verbrauch abgerechnet.
- [Schlüssel/Konto](https://cloud.sambanova.ai/apis) · [Dokumentation](https://docs.sambanova.ai)

### Novita AI

Novita AI: günstige offene Modelle.

**Stärken:** Niedrige Preise, viele Modelle, auch weniger gefilterte.

- **Hersteller:** Novita AI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://novita.ai/settings/key-management) · [Dokumentation](https://novita.ai/docs)

### Hyperbolic

Hyperbolic: offene Modelle und GPU-Miete.

**Stärken:** Günstige Preise, auch Basismodelle ohne Feinabstimmung.

- **Hersteller:** Hyperbolic (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://app.hyperbolic.xyz/settings) · [Dokumentation](https://docs.hyperbolic.xyz)

### Featherless AI

Featherless: Flatrate für Tausende offene Modelle vom Hugging Face Hub.

**Stärken:** Fester Monatspreis statt Verbrauch, viele Spezial- und Rollenspielmodelle.

- **Hersteller:** Featherless (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://featherless.ai/account/api-keys) · [Dokumentation](https://featherless.ai/docs)

### Chutes

Chutes: dezentrale Plattform für offene Modelle.

**Stärken:** Sehr günstig, viele aktuelle offene Modelle.

- **Hersteller:** Chutes (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://chutes.ai/app/api) · [Dokumentation](https://chutes.ai/docs)

### Requesty

Requesty: Sammelanbieter mit Kostenkontrolle.

**Stärken:** Ein Schlüssel für viele Modelle, Ausgabengrenzen, automatische Ausweichmodelle.

- **Hersteller:** Requesty (Großbritannien)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://app.requesty.ai/api-keys) · [Dokumentation](https://docs.requesty.ai)

### Nscale

Nscale (Großbritannien): offene Modelle in europäischen Rechenzentren.

**Stärken:** Europäisches Hosting, günstige Preise.

- **Hersteller:** Nscale (Großbritannien)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://console.nscale.com) · [Dokumentation](https://docs.nscale.com)

### SiliconFlow

SiliconFlow: Plattform für offene, vor allem chinesische Modelle.

**Stärken:** Sehr günstig, große Auswahl (Qwen, DeepSeek, GLM, Kimi).

- **Hersteller:** SiliconFlow (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://cloud.siliconflow.com/account/ak) · [Dokumentation](https://docs.siliconflow.com)

## Anbieter aus China

Günstig und leistungsfähig. Daten werden in China verarbeitet, vor der Nutzung Datenschutzvorgaben prüfen.

### DeepSeek

Chinesischer Anbieter der DeepSeek-Modelle.

**Stärken:** Sehr günstig, starkes Nachdenkmodell (Reasoner) für Mathematik und Code.

- **Hersteller:** DeepSeek (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `deepseek-chat`, `deepseek-reasoner`
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://platform.deepseek.com/api_keys) · [Dokumentation](https://api-docs.deepseek.com)

### Qwen (Alibaba Cloud)

Die Qwen-Modelle von Alibaba Cloud.

**Stärken:** Gute Allrounder, starke Code-Varianten, Bildverständnis und Bilderzeugung, günstige Preise.

- **Hersteller:** Alibaba (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `qwen-max`, `qwen-plus`, `qwen-turbo`
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://modelstudio.console.alibabacloud.com) · [Dokumentation](https://www.alibabacloud.com/help/en/model-studio)

### Kimi (Moonshot)

Kimi-Modelle von Moonshot AI.

**Stärken:** Lange Kontexte, gute Agenten- und Code-Fähigkeiten.

- **Hersteller:** Moonshot AI (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `kimi-k2`, `kimi-latest`
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://platform.moonshot.ai) · [Dokumentation](https://platform.moonshot.ai/docs)

### GLM (Z.ai)

GLM-Modelle von Zhipu AI (Z.ai).

**Stärken:** Günstig, gute Code- und Agentenleistung, Flash-Varianten mit kostenlosen Kontingenten.

- **Hersteller:** Zhipu AI (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `glm-5.3`, `glm-5.3-flash`
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://z.ai/manage-apikey/apikey-list) · [Dokumentation](https://docs.z.ai)

### MiniMax

MiniMax: Sprachmodelle sowie Hailuo-Video, Musik und Sprachausgabe.

**Stärken:** Ein Konto für Chat, Bilder, Musik, Video und Stimmen; gute Videoqualität.

- **Hersteller:** MiniMax (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bild, Musik, Video, Sprache
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Empfohlene Modelle:** `MiniMax-M2`
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://www.minimax.io/platform) · [Dokumentation](https://www.minimax.io/platform/document)

### Doubao (BytePlus ModelArk)

Doubao von ByteDance über BytePlus ModelArk.

**Stärken:** Günstig, gute Allrounder, Bildverständnis.

- **Hersteller:** ByteDance (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://console.byteplus.com/ark) · [Dokumentation](https://docs.byteplus.com/en/docs/ModelArk)

### ERNIE (Baidu Qianfan)

ERNIE von Baidu über Qianfan.

**Stärken:** Stark im Chinesischen, günstige Preise.

- **Hersteller:** Baidu (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://console.bce.baidu.com/qianfan) · [Dokumentation](https://cloud.baidu.com/doc/qianfan)

### Hunyuan (Tencent)

Hunyuan von Tencent.

**Stärken:** Gute Allrounder, stark im Chinesischen.

- **Hersteller:** Tencent (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://console.cloud.tencent.com/hunyuan) · [Dokumentation](https://cloud.tencent.com/document/product/1729)

### StepFun

StepFun mit den Step-Modellen.

**Stärken:** Gute multimodale Modelle mit Bildverständnis.

- **Hersteller:** StepFun (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://platform.stepfun.com) · [Dokumentation](https://platform.stepfun.com/docs)

## Lokal auf dem eigenen Rechner oder Server

Kostenlos, Daten verlassen das eigene Netz nicht. Braucht genug Arbeitsspeicher oder eine Grafikkarte. Die Modelle bestimmt der lokale Server.

### Ollama

Ollama: lokale Modelle auf dem eigenen Rechner.

**Stärken:** Kostenlos, Daten verlassen den Rechner nicht, einfache Installation, große Modellbibliothek.

- **Hersteller:** Ollama (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://ollama.com)

### LM Studio

LM Studio: Desktop-Programm für lokale Modelle mit eingebautem Server.

**Stärken:** Bequeme Oberfläche zum Herunterladen und Testen, kostenlos, offline.

- **Hersteller:** LM Studio (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://lmstudio.ai/docs)

### llama.cpp-Server

llama.cpp-Server: die Grundlage vieler lokaler Programme.

**Stärken:** Sehr ressourcenschonend, läuft auch ohne Grafikkarte.

- **Hersteller:** ggml (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://github.com/ggml-org/llama.cpp)

### vLLM

vLLM: Hochleistungs-Server für eigene Modelle (Rechenzentrum, GPU-Server).

**Stärken:** Sehr hoher Durchsatz für viele Benutzer, gut für Firmen-Server.

- **Hersteller:** vLLM (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung, API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.vllm.ai)

### LocalAI

LocalAI: lokaler Ersatz für die OpenAI-Schnittstelle, auch mit Bildern.

**Stärken:** Chat, Bilder und Sprache lokal mit einem Dienst.

- **Hersteller:** LocalAI (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung, API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe, Bild
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://localai.io)

### Jan

Jan: Open-Source-Desktop-Programm für lokale Modelle.

**Stärken:** Kostenlos, offline, einfache Oberfläche.

- **Hersteller:** Jan (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://jan.ai/docs)

### GPT4All

GPT4All von Nomic: lokale Modelle auf normalen PCs.

**Stärken:** Läuft auf schwacher Hardware, auch mit eigenen Dokumenten.

- **Hersteller:** Nomic (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.gpt4all.io)

### KoboldCpp

KoboldCpp: lokaler Server, beliebt für kreatives Schreiben.

**Stärken:** Ein Programm ohne Installation, ungefiltert je nach Modell.

- **Hersteller:** KoboldCpp (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://github.com/LostRuins/koboldcpp)

### ComfyUI

ComfyUI: lokale Bild- und Videoerzeugung mit Knoten-Workflows.

**Stärken:** Volle Kontrolle über Stable Diffusion, FLUX und Videomodelle, kostenlos.

- **Hersteller:** Comfy (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Bild, Video
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.comfy.org)

### LiteLLM Proxy (eigenes Gateway)

LiteLLM Proxy: eigenes Gateway, das viele Anbieter hinter einer Adresse bündelt.

**Stärken:** Zentrale Schlüssel, Budgets und Protokolle für das ganze Team, ideal für Firmen.

- **Hersteller:** BerriAI (eigener Rechner/Server)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- [Dokumentation](https://docs.litellm.ai/docs/simple_proxy)

### Foundry Local

Microsoft Foundry Local: lokale Modelle unter Windows, optimiert für NPU, GPU und CPU.

**Stärken:** Von Microsoft, nutzt Copilot+-PC-Chips, kostenlos und offline. Der Port kann wechseln.

- **Hersteller:** Microsoft (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://learn.microsoft.com/azure/ai-foundry/foundry-local/)

### Docker Model Runner

Docker Model Runner: lokale Modelle über Docker Desktop.

**Stärken:** Für Teams, die ohnehin Docker nutzen; Modelle wie Container verwalten.

- **Hersteller:** Docker (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.docker.com/ai/model-runner/)

### Text Generation WebUI (oobabooga)

Text Generation WebUI (oobabooga): umfangreiche lokale Oberfläche.

**Stärken:** Sehr viele Einstellmöglichkeiten und Modellformate.

- **Hersteller:** oobabooga (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://github.com/oobabooga/text-generation-webui)

### llamafile

llamafile von Mozilla: ein Modell als einzelne ausführbare Datei.

**Stärken:** Keine Installation, einfach starten.

- **Hersteller:** Mozilla (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://github.com/Mozilla-Ocho/llamafile)

### AnythingLLM

AnythingLLM: lokaler Arbeitsbereich mit eigenen Dokumenten.

**Stärken:** Fragen zu eigenen Dateien (RAG) über die Arbeitsbereiche von AnythingLLM.

- **Hersteller:** Mintplex Labs (eigener Rechner/Server)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.anythingllm.com)

### Open WebUI

Open WebUI: Weboberfläche für Ollama und andere Server, oft zentral im Unternehmen.

**Stärken:** Ein Firmen-Server mit Benutzerverwaltung lässt sich direkt anbinden.

- **Hersteller:** Open WebUI (eigener Rechner/Server)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.openwebui.com)

### Lemonade Server (AMD)

Lemonade Server von AMD.

**Stärken:** Nutzt Ryzen-AI-NPUs und AMD-Grafikkarten.

- **Hersteller:** AMD (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://lemonade-server.ai)

### Xinference

Xinference: Server für viele lokale Modelltypen.

**Stärken:** Chat, Einbettungen, Bilder und Sprache aus einer Hand, für Server.

- **Hersteller:** Xorbits (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://inference.readthedocs.io)

### SGLang

SGLang: Hochleistungs-Server für eigene Modelle.

**Stärken:** Sehr schnell bei vielen gleichzeitigen Anfragen.

- **Hersteller:** LMSYS (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.sglang.ai)

### TabbyAPI (ExLlama)

TabbyAPI: Server für ExLlama-Modelle.

**Stärken:** Sehr schnell auf NVIDIA-Grafikkarten mit wenig Speicher.

- **Hersteller:** theroyallab (eigener Rechner/Server)
- **Anmeldung:** API-Schlüssel
- **Kann:** Chat, Funktionen
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://github.com/theroyallab/tabbyAPI)

### Msty

Msty: Desktop-Programm für lokale und Cloud-Modelle.

**Stärken:** Einfache Oberfläche, lokaler Server für andere Programme.

- **Hersteller:** Msty (eigener Rechner/Server)
- **Anmeldung:** Ohne Anmeldung
- **Kann:** Chat
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Dokumentation](https://docs.msty.app)

## Bilder, Musik, Video und Sprache

Genutzt in [Clank – KI-Studio](Tool-Clank-KI-Studio) (Bilder, Medien, Mitschrift).

### fal.ai

fal.ai: Plattform für Bild-, Musik- und Videomodelle.

**Stärken:** Sehr viele Medienmodelle (FLUX, Kling, Veo, Hailuo, Pika …) über ein Konto.

- **Hersteller:** fal (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild, Musik, Video
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://fal.ai/dashboard/keys) · [Dokumentation](https://docs.fal.ai)

### Replicate

Replicate: Tausende Community- und Herstellermodelle per Schnittstelle.

**Stärken:** Riesige Auswahl für Bilder, Musik und Video, auch Nischenmodelle.

- **Hersteller:** Replicate (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild, Musik, Video
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)
- [Schlüssel/Konto](https://replicate.com/account/api-tokens) · [Dokumentation](https://replicate.com/docs)

### FLUX (Black Forest Labs)

Black Forest Labs (Freiburg) mit den FLUX-Bildmodellen.

**Stärken:** Sehr gute Bildqualität und Textdarstellung, Anbieter aus Deutschland.

- **Hersteller:** Black Forest Labs (Deutschland)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://dashboard.bfl.ai) · [Dokumentation](https://docs.bfl.ai)

### Recraft

Recraft: Bilder, Illustrationen und Vektorgrafiken.

**Stärken:** Einheitliche Stile, Vektorgrafiken (SVG), Logos und Symbole.

- **Hersteller:** Recraft (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://www.recraft.ai/profile/api) · [Dokumentation](https://www.recraft.ai/docs)

### Stability AI

Stability AI: Stable Diffusion und Stable Audio.

**Stärken:** Bilder und kurze Musikstücke, viele Stilvarianten.

- **Hersteller:** Stability AI (Großbritannien)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild, Musik
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://platform.stability.ai/account/keys) · [Dokumentation](https://platform.stability.ai/docs)

### Ideogram

Ideogram: Bildmodelle mit Fokus auf Schrift im Bild.

**Stärken:** Sehr gute Textdarstellung in Bildern (Plakate, Logos).

- **Hersteller:** Ideogram (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://ideogram.ai/manage-api) · [Dokumentation](https://developer.ideogram.ai)

### ElevenLabs

ElevenLabs: Stimmen, Sprachausgabe und Musik.

**Stärken:** Sehr natürliche Stimmen in vielen Sprachen, Musik mit Gesang.

- **Hersteller:** ElevenLabs (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Musik, Sprache
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://elevenlabs.io/app/settings/api-keys) · [Dokumentation](https://elevenlabs.io/docs)

### Mureka

Mureka (Kunlun Tech): Musik mit Gesang.

**Stärken:** Ganze Lieder aus Text und Stilangabe.

- **Hersteller:** Kunlun Tech (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Musik
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://platform.mureka.ai) · [Dokumentation](https://platform.mureka.ai/docs)

### Runway

Runway: Videoerzeugung (Gen-4.5) und Zugang zu Veo.

**Stärken:** Filmische Videos, Bild-zu-Video, gute Steuerung.

- **Hersteller:** Runway (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Video, Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://dev.runwayml.com) · [Dokumentation](https://docs.dev.runwayml.com)

### Luma Dream Machine

Luma Dream Machine (Ray): Video und Bilder.

**Stärken:** Flüssige Bewegungen, schnelle Erzeugung.

- **Hersteller:** Luma AI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Video, Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://lumalabs.ai/dream-machine/api/keys) · [Dokumentation](https://docs.lumalabs.ai)

### Kling

Kling von Kuaishou: Videoerzeugung.

**Stärken:** Realistische Bewegungen und Personen, lange Clips.

- **Hersteller:** Kuaishou (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Video
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://app.klingai.com/global/dev) · [Dokumentation](https://app.klingai.com/global/dev/document-api)

### Seedance (ByteDance)

Seedance von ByteDance: Video und Bilder.

**Stärken:** Gute Qualität zu günstigem Preis, mehrere Einstellungen pro Clip.

- **Hersteller:** ByteDance (China)
- **Anmeldung:** API-Schlüssel
- **Kann:** Video, Bild
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- **Hinweis:** Daten werden in China verarbeitet. Vor der Nutzung Datenschutzvorgaben prüfen.
- [Schlüssel/Konto](https://console.byteplus.com) · [Dokumentation](https://docs.byteplus.com/en/docs/ModelArk)

### Deepgram

Deepgram: Spracherkennung (Transkription).

**Stärken:** Schnell und genau, Sprechererkennung, für Mitschriften.

- **Hersteller:** Deepgram (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Sprache
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://console.deepgram.com) · [Dokumentation](https://developers.deepgram.com)

### AssemblyAI

AssemblyAI: Spracherkennung mit Zusatzfunktionen.

**Stärken:** Sprechererkennung, Zusammenfassungen, viele Sprachen.

- **Hersteller:** AssemblyAI (USA)
- **Anmeldung:** API-Schlüssel
- **Kann:** Sprache
- **Voraussetzung:** API-Konto beim Anbieter mit Guthaben oder Zahlungsmittel, abgerechnet nach Verbrauch. Chat-Abos wie ChatGPT Plus oder Claude Pro gelten dafür nicht.
- [Schlüssel/Konto](https://www.assemblyai.com/app/api-keys) · [Dokumentation](https://www.assemblyai.com/docs)

## Benutzerdefiniert

Für Firmen-Bots, Gateways und alles, was nicht in der Liste steht.

### Benutzerdefiniert (OpenAI-kompatibel)

Eigener Endpunkt im OpenAI-Format, z. B. ein Firmen-Bot oder Gateway.

**Stärken:** Bindet jeden kompatiblen Dienst an, Adresse und Modell frei einstellbar.

- **Hersteller:** – (–)
- **Anmeldung:** API-Schlüssel, Ohne Anmeldung, Eigenes OAuth
- **Kann:** Chat, Funktionen, Bildeingabe
- **Voraussetzung:** Kostenlos. Läuft auf dem eigenen Rechner oder Server und braucht dafür genug Arbeitsspeicher bzw. eine Grafikkarte.
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)

### Benutzerdefiniert (Anthropic-Format)

Eigener Endpunkt im Anthropic-Format.

**Stärken:** Für Gateways oder Proxys, die das Claude-Format sprechen.

- **Hersteller:** – (–)
- **Anmeldung:** API-Schlüssel, Eigenes OAuth
- **Kann:** Chat, Funktionen, Bildeingabe
- **🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)

## Nicht oder nur indirekt verfügbar

Stehen zur Information in der Liste. Rot markierte Einträge hat der Anbieter eingestellt.

### Midjourney

Midjourney: bekannter Bildgenerator.

**Stärken:** Sehr ästhetische Bilder, aber ohne öffentliche Schnittstelle.

- **Hersteller:** Midjourney (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://www.midjourney.com)

### Adobe Firefly

Adobe Firefly: Bildmodelle von Adobe.

**Stärken:** Lizenzrechtlich abgesichert, nur mit Unternehmensvertrag per Schnittstelle.

- **Hersteller:** Adobe (USA)
- **Anmeldung:** –
- **Kann:** Bild
- **Hinweis:** Setzt meist einen Vertrag mit dem Anbieter voraus.
- [Dokumentation](https://developer.adobe.com/firefly-services/docs/)

### Suno

Suno: Musikgenerator.

**Stärken:** Ganze Lieder mit Gesang, aber ohne offizielle Schnittstelle.

- **Hersteller:** Suno (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://suno.com)

### Udio

Udio: Musikgenerator.

**Stärken:** Hochwertige Musik, aber ohne offizielle Schnittstelle.

- **Hersteller:** Udio (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://www.udio.com)

### Sora

Sora von OpenAI: Videoerzeugung. **Eingestellt.**

**Stärken:** Vom Anbieter eingestellt, bleibt nur zur Information in der Liste.

- **Hersteller:** OpenAI (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Der Anbieter hat diesen Dienst am 24.09.2026 eingestellt.
- [Dokumentation](https://openai.com/sora)

### Microsoft Copilot (privat)

Microsoft Copilot für Privatpersonen.

**Stärken:** Keine Schnittstelle für andere Programme. Für Firmen gibt es Microsoft 365 Copilot.

- **Hersteller:** Microsoft (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://copilot.microsoft.com)

### Leonardo.Ai

Leonardo.Ai (Canva): Bilder und Videos.

**Stärken:** Viele Stile und Feinabstimmungen. Noch nicht direkt angebunden.

- **Hersteller:** Canva (Australien)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Noch nicht direkt angebunden. Wünsche für eine Anbindung gern als GitHub-Issue.
- [Dokumentation](https://docs.leonardo.ai)

### Krea

Krea: Bilder und Videos in Echtzeit.

**Stärken:** Schnelle Vorschau beim Tippen. Über fal.ai oder Replicate nutzbar.

- **Hersteller:** Krea (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Keine direkte Anbindung. Die Modelle dieses Anbieters lassen sich über fal.ai oder Replicate nutzen.
- [Dokumentation](https://docs.krea.ai)

### Pika

Pika: kurze Videos mit Effekten.

**Stärken:** Kreative Effekte. Über fal.ai nutzbar.

- **Hersteller:** Pika Labs (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Keine direkte Anbindung. Die Modelle dieses Anbieters lassen sich über fal.ai oder Replicate nutzen.
- [Dokumentation](https://pika.art)

### PixVerse

PixVerse: Videoerzeugung.

**Stärken:** Schnell und günstig. Über fal.ai oder Replicate nutzbar.

- **Hersteller:** PixVerse (Singapur)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Keine direkte Anbindung. Die Modelle dieses Anbieters lassen sich über fal.ai oder Replicate nutzen.
- [Dokumentation](https://docs.platform.pixverse.ai)

### Vidu

Vidu von ShengShu: Videoerzeugung.

**Stärken:** Gute Bewegungen und Figurenkonsistenz. Über fal.ai oder Replicate nutzbar.

- **Hersteller:** ShengShu (China)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Keine direkte Anbindung. Die Modelle dieses Anbieters lassen sich über fal.ai oder Replicate nutzen.
- [Dokumentation](https://platform.vidu.com)

### Hailuo (MiniMax Video)

Hailuo: Videomodelle von MiniMax.

**Stärken:** Sehr gute Videoqualität. Über den Eintrag MiniMax nutzbar.

- **Hersteller:** MiniMax (China)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Hailuo-Videos gibt es über den Eintrag MiniMax.
- [Dokumentation](https://www.minimax.io)

### Freepik AI

Freepik AI: Bilder und Videos mit vielen Modellen.

**Stärken:** Große Auswahl in einem Konto. Noch nicht direkt angebunden.

- **Hersteller:** Freepik (Spanien)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Noch nicht direkt angebunden. Wünsche für eine Anbindung gern als GitHub-Issue.
- [Dokumentation](https://docs.freepik.com)

### Speechmatics

Speechmatics (Großbritannien): Spracherkennung.

**Stärken:** Sehr genau bei Akzenten und Dialekten. Noch nicht direkt angebunden.

- **Hersteller:** Speechmatics (Großbritannien)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Noch nicht direkt angebunden. Wünsche für eine Anbindung gern als GitHub-Issue.
- [Dokumentation](https://docs.speechmatics.com)

### Cartesia

Cartesia: sehr schnelle Sprachausgabe.

**Stärken:** Stimmen mit kaum Verzögerung. Noch nicht direkt angebunden.

- **Hersteller:** Cartesia (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Noch nicht direkt angebunden. Wünsche für eine Anbindung gern als GitHub-Issue.
- [Dokumentation](https://docs.cartesia.ai)

### Azure AI Speech

Azure AI Speech: Spracherkennung und Sprachausgabe von Microsoft.

**Stärken:** Viele Sprachen und Stimmen, Unternehmensvertrag. Noch nicht direkt angebunden.

- **Hersteller:** Microsoft (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Noch nicht direkt angebunden. Wünsche für eine Anbindung gern als GitHub-Issue.
- [Dokumentation](https://learn.microsoft.com/azure/ai-services/speech-service/)

### Pi (Inflection)

Pi von Inflection AI: persönlicher Gesprächsassistent.

**Stärken:** Keine öffentliche Schnittstelle für andere Programme.

- **Hersteller:** Inflection AI (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://inflection.ai)

### Meta AI

Meta AI: Assistent in WhatsApp, Instagram und Facebook.

**Stärken:** Keine öffentliche Schnittstelle. Die Llama-Modelle gibt es über viele andere Anbieter und lokal.

- **Hersteller:** Meta (USA)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Dieser Dienst bietet keine öffentliche Schnittstelle für andere Programme.
- [Dokumentation](https://www.meta.ai)

### Le Chat Pro (Mistral-Abo)

Le Chat Pro: das Chat-Abo von Mistral.

**Stärken:** Gilt nicht für andere Programme. Bitte den Eintrag Mistral mit API-Schlüssel verwenden.

- **Hersteller:** Mistral AI (Frankreich)
- **Anmeldung:** –
- **Kann:** –
- **Hinweis:** Das Chat-Abo gilt nicht in anderen Programmen. Bitte den Eintrag Mistral mit API-Schlüssel verwenden.
- [Dokumentation](https://mistral.ai)

## Siehe auch

- [KI-Assistenten](KI-Assistenten) – Assistenten verbinden, Chatleiste, Kosten
- [KI-Zugriff und Verfremdung](KI-Zugriff-und-Verfremdung)
- [Clank – KI-Studio](Tool-Clank-KI-Studio) – Bilder, Musik, Video, Mitschrift
