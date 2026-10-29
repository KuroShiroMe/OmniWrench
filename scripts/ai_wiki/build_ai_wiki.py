"""Erzeugt wiki/KI-Anbieter.md aus dem Anbieterkatalog und den Beschreibungen in descriptions.py.

    python scripts/ai_wiki/build_ai_wiki.py

Nach jeder Katalogänderung ausführen. Neue Anbieter brauchen einen Eintrag in descriptions.py (Was, Stärken),
sonst bricht das Skript ab.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from descriptions import D  # noqa: E402

R = str(Path(__file__).resolve().parents[2]) + "/"
cat = json.load(open(R + "omniwrench/resources/ai/providers.json"))
de = json.load(open(R + "omniwrench/locales/de.json"))
P = cat["providers"]
missing = [p["id"] for p in P if p["id"] not in D]
if missing:
    sys.exit(f"Beschreibung fehlt in descriptions.py: {', '.join(missing)}")
LAND = {"US": "USA", "DE": "Deutschland", "FR": "Frankreich", "GB": "Großbritannien", "CN": "China", "CA": "Kanada",
        "NL": "Niederlande", "IT": "Italien", "IL": "Israel", "KR": "Südkorea", "AU": "Australien", "SG": "Singapur",
        "ES": "Spanien", "LOCAL": "eigener Rechner/Server", "": "–"}
def anchor(t):
    t = t.lower()
    t = re.sub(r"[^\w\- ]", "", t)
    return t.replace(" ", "-")
def group(p):
    if p["status"] != "active": return "na"
    if p["id"].startswith("custom"): return "custom"
    if "local" in p["categories"] or p["country"] == "LOCAL": return "local"
    if p["api"] == "media_only": return "media"
    if "eu" in p["categories"] or p["country"] in ("DE", "FR", "NL", "IT"): return "eu"
    if "enterprise" in p["categories"]: return "enterprise"
    if "router" in p["categories"]: return "router"
    if p["country"] == "CN": return "cn"
    return "chat"
GROUPS = [("chat", "Große Chat-Anbieter", "Die bekannten Assistenten mit eigenen Modellen."),
          ("eu", "EU und Deutschland", "Verarbeitung in Europa, für strengere Datenschutzvorgaben."),
          ("enterprise", "Unternehmen und Cloud", "Modelle im eigenen Cloud-Konto oder mit Unternehmensvertrag."),
          ("router", "Sammelanbieter und schnelle Plattformen", "Ein Konto für viele Modelle, oft offene Modelle (Llama, Qwen, DeepSeek …) zu günstigen Preisen."),
          ("cn", "Anbieter aus China", "Günstig und leistungsfähig. Daten werden in China verarbeitet, vor der Nutzung Datenschutzvorgaben prüfen."),
          ("local", "Lokal auf dem eigenen Rechner oder Server", "Kostenlos, Daten verlassen das eigene Netz nicht. Braucht genug Arbeitsspeicher oder eine Grafikkarte. Die Modelle bestimmt der lokale Server."),
          ("media", "Bilder, Musik, Video und Sprache", "Genutzt in den KI-Tools ([Pixelizer](Tool-Pixelizer), [Groovitron](Tool-Groovitron), [Vidcomic](Tool-Vidcomic), [Kreeli](Tool-Kreeli))."),
          ("custom", "Benutzerdefiniert", "Für Firmen-Bots, Gateways und alles, was nicht in der Liste steht."),
          ("na", "Nicht oder nur indirekt verfügbar", "Stehen zur Information in der Liste. Rot markierte Einträge hat der Anbieter eingestellt.")]
def line(p):
    caps = ", ".join(de.get(f"ai.cap.{c}", c) for c in p["capabilities"]) or "–"
    auth = ", ".join(de.get(f"ai.auth.{a}", a) for a in p["auth"]) or "–"
    req = p.get("requires", {}).get("*")
    if not req:
        if not p["auth"]: req = ""
        elif "none" in p["auth"] or p["country"] == "LOCAL": req = "local"
        elif "enterprise" in p["categories"]: req = "cloud_contract"
        elif p["id"].startswith("custom"): req = ""
        else: req = "api_paid"
    parts = [f"**Hersteller:** {p.get('vendor') or '–'} ({LAND.get(p['country'], p['country'])})",
             f"**Anmeldung:** {auth}", f"**Kann:** {caps}"]
    if p.get("requires", {}).get("oauth_chatgpt"):
        parts.append("**Voraussetzung:** API-Schlüssel: Guthaben beim Anbieter · Mit ChatGPT anmelden: " + de["ai.req.chatgpt_plus"])
    elif req:
        parts.append("**Voraussetzung:** " + de[f"ai.req.{req}"])
    if p.get("models"):
        parts.append("**Empfohlene Modelle:** " + ", ".join(f"`{m}`" for m in p["models"][:4]))
    if p.get("nsfw"):
        parts.append("**🔞 NSFW-fähig** (je nach Modell, Schalter im Assistenten)")
    note = p.get("status_note") or p.get("note")
    if note and f"ai.note.{note}" in de:
        parts.append("**Hinweis:** " + de[f"ai.note.{note}"])
    links = []
    if p.get("key_url"): links.append(f"[Schlüssel/Konto]({p['key_url']})")
    if p["id"] == "ollama":
        parts.append("**In OmniWrench einrichten:** **🦙 Ollama einrichten …** im Verbindungsdialog installiert Ollama, "
                     "startet es und lädt Modelle, siehe [KI lokal mit Ollama](KI-lokal-mit-Ollama)")
    if p.get("docs_url"): links.append(f"[Dokumentation]({p['docs_url']})")
    if links: parts.append(" · ".join(links))
    return parts
out = []
w = out.append
w("# KI-Anbieter")
w("")
w("> **Kurz:** Alle KI-Anbieter, die OmniWrench kennt: was sie können, wofür sie sich eignen, was sie kosten und")
w("> welche Modelle es gibt. Die Liste kommt aus dem Anbieterkatalog und wird über den Store aktualisiert.")
w("> Einrichten: [KI-Assistenten](KI-Assistenten#assistenten-verbinden).")
w("")
w(f"**Gilt für:** Hauptprogramm ab Version 0.9.0 · **Stand des Katalogs:** {cat['updated'][:10]} · **{len(P)} Einträge**")
w("")
w("## Inhalt")
w("- [Welcher Anbieter passt?](#welcher-anbieter-passt)")
w("- [Kostenlos testen](#kostenlos-testen)")
w("- [Modelle auswählen](#modelle-auswählen)")
w("- [Inhalte für Erwachsene (NSFW)](#inhalte-für-erwachsene-nsfw)")
for g, title, _ in GROUPS:
    w(f"- [{title}](#{anchor(title)})")
w("- [Siehe auch](#siehe-auch)")
w("")
w("## Welcher Anbieter passt?")
w("")
w("| Wunsch | Empfehlung |")
w("|---|---|")
for a, b in [("Einfach loslegen, beste Allround-Qualität", "[ChatGPT / OpenAI](#chatgpt--openai), [Claude](#claude) oder [Gemini](#gemini)"),
             ("Kostenlos ausprobieren", "[Gemini](#gemini), [Groq](#groq), [OpenRouter](#openrouter) (Modelle mit `:free`), [GitHub Models](#github-models)"),
             ("Daten dürfen das Haus nicht verlassen", "[Ollama](#ollama), [LM Studio](#lm-studio), [Foundry Local](#foundry-local) oder ein eigener Server ([vLLM](#vllm))"),
             ("Verarbeitung in Deutschland/EU", "[Mistral](#mistral-le-chat), [IONOS](#ionos-ai-model-hub), [STACKIT](#stackit-ai-model-serving), [Aleph Alpha](#aleph-alpha-phariaai)"),
             ("Im Unternehmen mit Microsoft 365", "[Microsoft 365 Copilot](#microsoft-365-copilot) oder [Azure OpenAI](#azure-openai--ai-foundry)"),
             ("Viele Modelle mit einem Konto", "[OpenRouter](#openrouter), [Requesty](#requesty), [Vercel AI Gateway](#vercel-ai-gateway)"),
             ("Aktuelle Infos aus dem Web", "[Perplexity Sonar](#perplexity-sonar), [Gemini](#gemini), [Grok](#grok)"),
             ("Programmieren und Skripte", "[Claude](#claude), [ChatGPT / OpenAI](#chatgpt--openai), [Mistral](#mistral-le-chat) (Codestral)"),
             ("Sehr schnelle Antworten", "[Groq](#groq), [Cerebras](#cerebras), [SambaNova Cloud](#sambanova-cloud)")]:
    w(f"| {a} | {b} |")
w("")
w("## Kostenlos testen")
w("")
w("Diese Anbieter haben eine dauerhaft kostenlose Stufe mit Grenzen (Anfragen pro Minute und Tag). Stand: Herbst 2026,")
w("die Grenzen ändern sich häufig.")
w("")
w("| Anbieter | Kostenlos | Hinweis |")
w("|---|---|---|")
for r in [("[Gemini](#gemini)", "je nach Modell 5–15 Anfragen/Min., bis 1.500/Tag", "Eingaben werden außerhalb von EU/UK/EWR zum Training genutzt"),
          ("[Groq](#groq)", "ca. 30 Anfragen/Min., 1.000/Tag", "sehr schnell"),
          ("[OpenRouter](#openrouter)", "50 Anfragen/Tag mit `:free`-Modellen", "1.000/Tag nach einmaliger Aufladung von 10 $"),
          ("[Cerebras](#cerebras)", "ca. 1 Mio. Tokens/Tag", ""),
          ("[Mistral](#mistral-le-chat)", "Experiment-Stufe", "nur mit Zustimmung zum Training"),
          ("[GitHub Models](#github-models)", "ca. 15 Anfragen/Min., 150–1.000/Tag", "GitHub-Konto genügt"),
          ("[Cloudflare Workers AI](#cloudflare-workers-ai)", "tägliches Gratiskontingent", ""),
          ("[NVIDIA NIM](#nvidia-nim-buildnvidiacom)", "kostenlos für Entwickler", ""),
          ("[SambaNova Cloud](#sambanova-cloud)", "kostenlose Stufe", ""),
          ("[Hugging Face](#hugging-face-inference-providers), [Cohere](#cohere-command)", "kleine Kontingente", "Cohere nur nicht-kommerziell"),
          ("Lokal ([Ollama](#ollama), [LM Studio](#lm-studio) …)", "unbegrenzt", "eigene Hardware")]:
    w(f"| {r[0]} | {r[1]} | {r[2]} |")
w("")
w("> **Achtung:** Bei kostenlosen Stufen nutzen manche Anbieter die Eingaben zum Training. Keine Firmendaten, Kennwörter")
w("> oder personenbezogenen Daten eingeben. Die [Verfremdung](KI-Zugriff-und-Verfremdung) hilft, ersetzt das aber nicht.")
w("")
w("## Modelle auswählen")
w("")
w("Jeder Anbieter hat mehrere Modelle, die sich in Qualität, Geschwindigkeit und Preis unterscheiden. Das Modell wird")
w("oben in der Chatleiste gewählt (Knopf neben dem Assistenten, auch mitten im Chat) und gilt dann für diesen Assistenten.")
w("")
w("- OmniWrench fragt die Modellliste **direkt beim Anbieter** ab (spätestens alle 12 Stunden, oder mit")
w("  **Beim Anbieter abfragen**). Angezeigt werden nur Modelle, die es dort wirklich gibt.")
w("- **★** markiert das empfohlene Modell aus dem Katalog.")
w("- **Rot** mit ⚠: Das Modell meldet der Anbieter nicht (mehr). War es die Vorgabe aus dem Katalog, wechselt OmniWrench")
w("  von selbst auf das beste verfügbare Modell und sagt Bescheid. Selbst eingetragene Namen bleiben unverändert.")
w("- Liefert ein Anbieter keine Liste (z. B. manche Firmen-Endpunkte), steht „Verfügbarkeit unbekannt“. Ein Modellname")
w("  lässt sich dann ins Suchfeld tippen und mit **Modell „…“ verwenden** übernehmen.")
w("- **Auch andere Modelle zeigen** blendet Modelle ein, die nicht chatten (Bilder, Sprache, Einbettungen).")
w("")
w("Die Kurzbeschreibung der Modelle leitet OmniWrench aus dem Namen ab:")
w("")
w("| Merkmal | Bedeutung | Typische Namen |")
w("|---|---|---|")
names = {"top": "pro, opus, ultra, large, max", "balanced": "sonnet, medium, plus", "fast": "flash, turbo, fast",
         "light": "lite, mini, nano, haiku, small", "reasoning": "reasoner, thinking, o3, r1", "code": "code, coder, codestral",
         "vision": "vision, vl, pixtral", "free": "…:free (OpenRouter)", "preview": "preview, exp, beta"}
for t in ("top", "balanced", "fast", "light", "reasoning", "code", "vision", "free", "preview"):
    w(f"| **{de['ai.model.tag.' + t]}** | {de['ai.model.tip.' + t]} | {names[t]} |")
w("")
w("Faustregel: für den Alltag ein schnelles Modell (Flash, Mini, Sonnet), für schwierige Analysen das stärkste oder ein")
w("Nachdenkmodell.")
w("")
w("## Inhalte für Erwachsene (NSFW)")
w("")
w("Einige Anbieter können je nach Modell Inhalte für Erwachsene erzeugen. Sie sind in der Liste mit **🔞 NSFW** markiert.")
w("")
w("- Standardmäßig weist OmniWrench solche Assistenten an, **arbeitstauglich** zu bleiben.")
w("- In den Einstellungen des Assistenten gibt es den Schalter **NSFW-Inhalte erlauben (ab 18)**. Beim Einschalten")
w("  fragt OmniWrench nach, ob Volljährigkeit und Erlaubnis im Unternehmen gegeben sind. Die Verantwortung liegt beim")
w("  Benutzer.")
w("- Ist der Schalter an, zeigt die Chatleiste 🔞 vor dem Modellnamen.")
w("- Die Regeln des Anbieters gelten immer; OmniWrench hebt keine Filter des Anbieters auf.")
w("- Bei Anbietern ohne diese Fähigkeit gibt es den Schalter nicht.")
w("")
for g, title, intro in GROUPS:
    items = [p for p in P if group(p) == g]
    if not items:
        continue
    w(f"## {title}")
    w("")
    w(intro)
    w("")
    for p in items:
        what, strong = D[p["id"]]
        w(f"### {p['name']}")
        w("")
        w(what + (" **Eingestellt.**" if p["status"] == "removed" else ""))
        w("")
        w(f"**Stärken:** {strong}")
        w("")
        for part in line(p):
            w(f"- {part}")
        w("")
w("## Siehe auch")
w("")
w("- [KI-Assistenten](KI-Assistenten) – Assistenten verbinden, Chatleiste, Kosten")
w("- [KI-Zugriff und Verfremdung](KI-Zugriff-und-Verfremdung)")
w("- [KI-Tools](Tools) – Bilder, Musik, Video, Transkription, Sprachassistent")
w("- [KI lokal mit Ollama](KI-lokal-mit-Ollama)")
open(R + "wiki/KI-Anbieter.md", "w").write("\n".join(out) + "\n")
heads = [anchor(l[4:]) for l in out if l.startswith("### ")] + [anchor(l[3:]) for l in out if l.startswith("## ")]
bad = [a for a in re.findall(r"\]\(#([^)]+)\)", "\n".join(out)) if a not in heads]
if bad:
    sys.exit(f"Anker ohne Überschrift: {bad}")
print(f"wiki/KI-Anbieter.md: {len(P)} Anbieter")
