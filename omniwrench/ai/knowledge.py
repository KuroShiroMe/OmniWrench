"""Wissen für den Assistenten: Wiki-Seiten (mitgeliefert) als Volltextindex (SQLite FTS5).

Der Index liegt in LOCAL_DIR/ai-index/knowledge.db und wird neu gebaut, wenn sich die Wiki-Dateien
ändern (Programm-Update). Seiten werden an Überschriften in Abschnitte zerlegt.
Ohne FTS5 (sehr alte SQLite-Version) wird einfach nach Wörtern gezählt.
"""

from __future__ import annotations

import hashlib
import logging
import re
import sqlite3
import sys
import threading
from pathlib import Path

from omniwrench import GITHUB_REPO
from omniwrench.core.paths import APP_DIR

from .storage import INDEX_DIR

log = logging.getLogger(__name__)
DB_FILE = INDEX_DIR / "knowledge.db"
WIKI_URL = f"https://github.com/{GITHUB_REPO}/wiki"
MAX_SECTION = 4000

_lock = threading.Lock()
_sections: list[dict] | None = None


def wiki_dir() -> Path | None:
    for base in (APP_DIR / "wiki", Path(getattr(sys, "_MEIPASS", "")) / "wiki"):
        if base.is_dir() and any(base.glob("*.md")):
            return base
    return None


def pages() -> list[Path]:
    d = wiki_dir()
    if d is None:
        return []
    return sorted(p for p in d.glob("*.md") if not p.name.startswith(("_", "Vorlage-")))


def _split(page: Path) -> list[dict]:
    text = page.read_text(encoding="utf-8", errors="replace")
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)                    # Bilder
    name = page.stem
    title = name.replace("-", " ")
    out, heading, buf = [], title, []

    def flush():
        body = "\n".join(buf).strip()
        if body:
            for i in range(0, len(body), MAX_SECTION):
                out.append({"page": name, "title": title, "heading": heading, "text": body[i:i + MAX_SECTION]})

    for line in text.splitlines():
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            if m.group(1) == "#":
                title = m.group(2).strip()
            flush()
            heading, buf = m.group(2).strip(), []
        else:
            buf.append(line)
    flush()
    return out


def _fingerprint(files: list[Path]) -> str:
    h = hashlib.sha256()
    for p in files:
        st = p.stat()
        h.update(f"{p.name}:{st.st_size}:{int(st.st_mtime)}".encode())
    return h.hexdigest()


def _connect() -> sqlite3.Connection:
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(str(DB_FILE), check_same_thread=False)


def ensure_index() -> bool:
    """Index aktuell halten. True, wenn FTS5 verfügbar ist."""
    global _sections
    files = pages()
    fp = _fingerprint(files)
    with _lock:
        if _sections is None:
            _sections = [s for p in files for s in _split(p)]
        try:
            con = _connect()
        except sqlite3.Error:
            return False
        try:
            con.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
            row = con.execute("SELECT value FROM meta WHERE key='fingerprint'").fetchone()
            if row and row[0] == fp:
                return True
            con.execute("DROP TABLE IF EXISTS docs")
            con.execute("CREATE VIRTUAL TABLE docs USING fts5(page, title, heading, text, "
                        "tokenize='unicode61 remove_diacritics 2')")
            con.executemany("INSERT INTO docs(page, title, heading, text) VALUES (?, ?, ?, ?)",
                            [(s["page"], s["title"], s["heading"], s["text"]) for s in _sections])
            con.execute("INSERT OR REPLACE INTO meta VALUES ('fingerprint', ?)", (fp,))
            con.commit()
            return True
        except sqlite3.Error as err:
            log.info("FTS5 nicht verfügbar (%s), einfache Suche", err)
            return False
        finally:
            con.close()


def _fts_query(query: str) -> str:
    words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 1]
    return " OR ".join(f'"{w}"*' for w in words[:12])


def search(query: str, limit: int = 6) -> list[dict]:
    """Passende Abschnitte: [{"page", "title", "heading", "text", "url"}]."""
    if ensure_index():
        q = _fts_query(query)
        if not q:
            return []
        con = _connect()
        try:
            rows = con.execute("SELECT page, title, heading, text FROM docs WHERE docs MATCH ? "
                               "ORDER BY bm25(docs, 2.0, 4.0, 3.0, 1.0) LIMIT ?", (q, limit)).fetchall()
        except sqlite3.Error:
            rows = []
        finally:
            con.close()
        hits = [{"page": r[0], "title": r[1], "heading": r[2], "text": r[3]} for r in rows]
    else:
        words = [w for w in re.findall(r"\w+", query.lower()) if len(w) > 2]
        scored = []
        for s in _sections or []:
            hay = f"{s['title']} {s['heading']} {s['text']}".lower()
            score = sum(hay.count(w) for w in words)
            if score:
                scored.append((score, s))
        scored.sort(key=lambda x: -x[0])
        hits = [dict(s) for _, s in scored[:limit]]
    for h in hits:
        h["url"] = f"{WIKI_URL}/{h['page']}"
    return hits


def read_page(name: str) -> dict | None:
    d = wiki_dir()
    if d is None:
        return None
    candidates = {p.stem.lower(): p for p in pages()}
    key = name.strip().replace(" ", "-").removesuffix(".md").lower()
    path = candidates.get(key) or next((p for k, p in candidates.items() if key in k), None)
    if path is None:
        return None
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", path.read_text(encoding="utf-8", errors="replace"))
    return {"page": path.stem, "url": f"{WIKI_URL}/{path.stem}", "text": text[:30_000]}


def page_list() -> list[str]:
    return [p.stem for p in pages()]
