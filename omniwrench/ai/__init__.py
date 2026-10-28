"""KI-Assistenten: Verbindungen zu Chatbots, lokale Ablage, Chat-Ablauf mit Funktionsaufrufen.

Aufbau:
    providers    Anbieterkatalog (resources/ai/providers.json, aktualisierbar über den Store)
    connections  eingerichtete Verbindungen (Einstellungen) und ihre Geheimnisse (Tresor)
    oauth        Anmeldung per Browser (Loopback + PKCE): ChatGPT, OpenRouter, Entra, eigenes OAuth
    adapters     Protokolle der Anbieter (OpenAI Chat/Responses, Anthropic, Microsoft Graph)
    storage      lokale Ablage in lesbaren Formaten, Chats optional verschlüsselt
    chat         ein Chatverlauf mit Systemanweisung, Detailgrad und Funktionsaufrufen
    functions    Funktionen, die der Assistent aufrufen darf (Programm, Wiki, Tools)
"""
