"""Prüft die KI-Bausteine ohne Oberfläche und ohne Internet (für CI und lokal).

    python scripts/test_ai.py

Ein lokaler Testserver spricht die drei Protokolle (OpenAI Chat Completions, OpenAI Responses,
Anthropic Messages) und ruft beim ersten Mal eine Funktion auf. Geprüft werden außerdem
Verfremdung, Zugriffsstufen mit Vererbung, verschlüsselte Ablage und die Wiki-Suche.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_home = tempfile.TemporaryDirectory(prefix="omniwrench_ai_")
os.environ["OMNIWRENCH_HOME"] = _home.name
sys.path.insert(0, str(ROOT))

from omniwrench.core import credentials, paths  # noqa: E402
from omniwrench.core.settings import AppSettings  # noqa: E402
from omniwrench.core.vault import Vault  # noqa: E402

failures: list[str] = []
received: list[dict] = []


def check(cond: bool, what: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + what)
    if not cond:
        failures.append(what)


class Fake(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _sse(self, events):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for ev, data in events:
            if ev:
                self.wfile.write(f"event: {ev}\n".encode())
            self.wfile.write(f"data: {data if isinstance(data, str) else json.dumps(data)}\n\n".encode())
        self.close_connection = True

    def do_GET(self):  # noqa: N802
        body = json.dumps({"data": [{"id": "m1"}, {"id": "m2"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.path.endswith("/oauth/token"):
            from urllib.parse import parse_qs
            received.append({"token_form": {k: v[0] for k, v in parse_qs(raw.decode()).items()}})
            tok = json.dumps({"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(tok)))
            self.end_headers()
            self.wfile.write(tok)
            return
        body = json.loads(raw or b"{}")
        received.append(body)
        if (self.headers.get("Authorization") or self.headers.get("x-api-key")) not in ("Bearer sk-test", "sk-test"):
            err = b'{"error":{"message":"bad key","code":"invalid_api_key"}}'
            self.send_response(401)
            self.send_header("Content-Length", str(len(err)))
            self.end_headers()
            self.wfile.write(err)
            return
        s = json.dumps(body)
        done = '"tool"' in s or "function_call_output" in s or "tool_result" in s
        call = bool(body.get("tools")) and not done
        if self.path.endswith("/chat/completions"):
            ev = ([("", {"choices": [{"delta": {"tool_calls": [{"index": 0, "id": "c1", "function": {
                "name": "probe", "arguments": '{"x": 1}'}}]}}]})] if call else
                  [("", {"choices": [{"delta": {"content": "Antwort zu NET1"}}]}),
                   ("", {"choices": [{"delta": {"content": ".57"}}]})])
            ev += [("", {"choices": [], "usage": {"prompt_tokens": 3, "completion_tokens": 2}}), ("", "[DONE]")]
        elif self.path.endswith("/responses"):
            ev = ([("", {"type": "response.output_item.done", "item": {
                "type": "function_call", "call_id": "c1", "name": "probe", "arguments": "{}"}})] if call else
                  [("", {"type": "response.output_text.delta", "delta": "Antwort Responses"})])
            ev.append(("", {"type": "response.completed", "response": {"usage": {"input_tokens": 1}}}))
        else:
            ev = [("", {"type": "message_start", "message": {"usage": {"input_tokens": 1}}})]
            if call:
                ev += [("", {"type": "content_block_start", "index": 0,
                             "content_block": {"type": "tool_use", "id": "t1", "name": "probe"}}),
                       ("", {"type": "content_block_delta", "index": 0,
                             "delta": {"type": "input_json_delta", "partial_json": "{}"}})]
            else:
                ev.append(("", {"type": "content_block_delta", "index": 0,
                                "delta": {"type": "text_delta", "text": "Antwort Claude"}}))
            ev.append(("", {"type": "message_stop"}))
        self._sse(ev)


def main() -> int:
    paths.ensure_dirs()
    vault = Vault(paths.VAULT_FILE)
    vault.create(password="test-passwort-123")
    credentials.init(vault)
    settings = AppSettings()
    from omniwrench.ai import access, adapters, chat, functions, knowledge, providers, storage
    from omniwrench.ai.connections import Connection, ConnectionStore
    from omniwrench.ai.pseudo import Pseudonymizer

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_port}/v1"

    print("Anbieterkatalog")
    check(len(providers.all_providers()) > 50, "Katalog geladen")
    check(all(p.api in providers.CHAT_APIS + ("media_only", "none") for p in providers.all_providers()),
          "nur bekannte Protokolle")
    check(providers.get("sora") is not None and providers.get("sora").removed, "eingestellter Anbieter markiert")

    print("Adapter und Chat-Ablauf")
    store = ConnectionStore(settings, vault)
    functions.register(functions.Function("probe", "test", lambda a, c: {"hostname": "SRV01", "ip": "10.1.2.3"},
                                          source="app"))
    for provider in ("custom", "openai", "anthropic"):
        conn = Connection(id=store.new_id(), name=provider, provider=provider, base_url=url, model="m")
        store.save(conn)
        store.update_secrets(conn.id, api_key="sk-test")
        check(adapters.for_connection(store, conn).test() == "2", f"{provider}: Modelle laden")
        thread = chat.new_thread(conn)
        thread["messages"].append({"role": "user", "content": "Host 10.1.2.57 prüfen"})
        p = Pseudonymizer({}, access.pseudo_kinds(settings))
        received.clear()
        chat.run(store, conn, thread, "sys", chat.RunHooks(
            level_for=lambda s: 1, encode=p.encode, decode=p.decode,
            encode_result=lambda src, v: functions.format_result(p.encode_value(v))), threading.Event())
        roles = [m["role"] for m in thread["messages"]]
        check(roles == ["user", "assistant", "tool", "assistant"], f"{provider}: Funktionsaufruf und Antwort")
        sent = json.dumps(received, ensure_ascii=False)
        check("10.1.2" not in sent and "SRV01" not in sent, f"{provider}: nur Platzhalter gesendet")
        if provider == "custom":
            check(thread["messages"][-1]["content"] == "Antwort zu 10.1.2.57", "Antwort zurückübersetzt")
    bad = Connection(id="bad", name="bad", provider="custom", base_url=url, model="m")
    store.save(bad)
    store.update_secrets("bad", api_key="falsch")
    try:
        chat.run(store, bad, {"messages": [{"role": "user", "content": "x"}]}, "", chat.RunHooks(), threading.Event())
        check(False, "falscher Schlüssel meldet Fehler")
    except Exception as err:  # noqa: BLE001
        check(getattr(err, "kind", "") == "auth", "falscher Schlüssel -> Anmeldefehler")
    sora = Connection(id="sora", name="s", provider="sora")
    try:
        adapters.for_connection(store, sora)
        check(False, "eingestellter Anbieter meldet Hinweis")
    except Exception as err:  # noqa: BLE001
        check(getattr(err, "kind", "") == "removed", "eingestellter Anbieter -> Hinweis")

    print("Verfremdung")
    p = Pseudonymizer({}, {})
    text = ("dc01.corp.contoso.local 10.1.2.57/255.255.255.0 MAC 00-15-5D-0A-12-34 CONTOSO\\m.muster "
            "m.muster@contoso.com 2001:db8::5 127.0.0.1 github.com tool.json 1.2.3")
    enc = p.encode(text)
    check(all(x not in enc for x in ("dc01", "10.1.2", "00-15", "m.muster", "contoso", "2001:db8")),
          "echte Werte ersetzt")
    check(all(x in enc for x in ("255.255.255.0", "127.0.0.1", "github.com", "tool.json", "1.2.3")),
          "Masken, Loopback, öffentliche Domänen, Dateien bleiben")
    check(p.decode(enc) == text, "Rückübersetzung exakt")
    check(p.encode("DC01 antwortet nicht").startswith("HOST-"), "bekannter Name auch im Freitext")
    check(Pseudonymizer({}, {}, enabled=False).encode(text) == text, "abgeschaltet = unverändert")

    print("Zugriffsstufen")
    check(access.level(settings, "app") == 1, "Standardstufe 1")
    check(access.level(settings, "net.x") == 1, "Tool erbt vom Hauptprogramm")
    access.set_tool_config(settings, "net.x", {"level": 3, "pseudo": False, "exceptions": {"c9": 0}})
    check(access.level(settings, "net.x") == 3 and access.level(settings, "net.x", "c9") == 0,
          "eigene Stufe und Ausnahme je Assistent")
    access.set_runtime("net.x", 2)
    check(access.level(settings, "net.x") == 2, "Stufe aus Favorit zur Laufzeit")
    access.set_runtime("net.x")
    check(not access.pseudo_enabled(settings, "net.x") and access.pseudo_enabled(settings, "app"),
          "Verfremdung je Tool")
    check(len(functions.available(lambda s: 0)) == 0, "Stufe 0 = keine Funktionen")

    print("Ablage")
    settings.set(storage.MODE_KEY, "central")
    settings.set(storage.ROOT_KEY, str(Path(_home.name) / "ai"))
    st = storage.Storage(settings, vault)
    t = {"id": st.new_id(), "title": "Test", "messages": [{"role": "user", "content": "geheim"}]}
    st.save_thread(t, chat.thread_markdown(t))
    files = sorted(f.name for f in st.thread_dir(t["id"]).iterdir())
    check(files == ["thread.owai"], "standardmäßig verschlüsselt")
    check(b"geheim" not in (st.thread_dir(t["id"]) / "thread.owai").read_bytes(), "Inhalt nicht lesbar")
    check(st.load_thread(t["id"])["messages"][0]["content"] == "geheim", "Entschlüsseln")
    st.convert_all(False)
    files = sorted(f.name for f in st.thread_dir(t["id"]).iterdir())
    check(files == ["thread.json", "thread.md"], "unverschlüsselt als JSON + Markdown")

    print("Wiki-Suche")
    hits = knowledge.search("DHCP Reservierung")
    check(bool(hits) and hits[0]["page"].startswith("Tool-"), "Treffer im Wiki")
    check(bool(knowledge.read_page("Tool-IconForge")), "Wiki-Seite lesen")

    print("Sign in with ChatGPT")
    from urllib.parse import parse_qs, urlencode, urlsplit
    from urllib.request import urlopen
    from omniwrench.ai import oauth
    oauth.CHATGPT_TOKEN = url.rsplit("/v1", 1)[0] + "/api/accounts/oauth/token"
    settings.set(oauth.HOST_ID_KEY, "0b5c2f0e-1111-4222-8333-444455556666")     # Vorabstand ohne Präfix
    seen: list[dict] = []

    def browser(issued: str):
        def open_url(u: str) -> None:
            q = {k: v[0] for k, v in parse_qs(urlsplit(u).query).items()}
            seen.append(q)
            back = {"code": "c-1", "state": q["state"]}
            if issued:
                back["client_id"] = issued
            threading.Thread(target=lambda: urlopen(q["redirect_uri"] + "?" + urlencode(back), timeout=10).read(),
                             daemon=True).start()
        return open_url
    gpt = Connection(id=store.new_id(), name="ChatGPT", provider="chatgpt", auth=providers.AUTH_CHATGPT)
    store.save(gpt)
    try:
        oauth.login_chatgpt(store, gpt, open_url=browser(""))
        check(False, "Registrierung ohne Client-ID abgelehnt")
    except Exception as e:  # noqa: BLE001
        check(getattr(e, "code", "") == "no_client", "Registrierung ohne Client-ID abgelehnt")
    received.clear()
    oauth.login_chatgpt(store, gpt, open_url=browser("oaiapp_test"))
    q = seen[-1]
    check(q["ext_agent_host_id"] == "urn:uuid:0b5c2f0e-1111-4222-8333-444455556666", "Host-ID als urn:uuid (migriert)")
    check(q["client_id"] == "dynamic_agent_client" and q["agent_name_hint"] == "OmniWrench", "Erstregistrierung")
    check(urlsplit(q["redirect_uri"]).hostname == "127.0.0.1" and q["redirect_uri"].endswith("/auth/callback"),
          "Rücksprung 127.0.0.1/auth/callback")
    check(q["scope"] == oauth.CHATGPT_SCOPES and q["resource"] == "https://api.openai.com/v1"
          and q["code_challenge_method"] == "S256", "Bereiche, Ressource, PKCE")
    form = received[-1]["token_form"]
    check(form["client_id"] == "oaiapp_test" and form["redirect_uri"] == q["redirect_uri"]
          and form.get("code_verifier"), "Token-Tausch mit ausgestellter Client-ID")
    check(store.secrets(gpt.id).get("client_id") == "oaiapp_test", "Client-ID gespeichert")
    oauth.login_chatgpt(store, gpt, open_url=browser(""))
    check(seen[-1]["client_id"] == "oaiapp_test" and "agent_name_hint" not in seen[-1]
          and seen[-1]["ext_agent_host_id"] == q["ext_agent_host_id"], "erneute Anmeldung mit derselben Host-ID")

    server.shutdown()
    if failures:
        print(f"\n{len(failures)} Prüfung(en) fehlgeschlagen", file=sys.stderr)
        return 1
    print("\nAlle KI-Prüfungen OK")
    return 0


if __name__ == "__main__":
    code = main()
    try:
        _home.cleanup()
    except OSError:
        pass
    sys.exit(code)
