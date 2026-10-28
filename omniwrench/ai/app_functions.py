"""Funktionen des Hauptprogramms für den Assistenten: Programm, Tools, Store, Wiki."""

from __future__ import annotations

import platform
from typing import Any

from omniwrench import APP_NAME, GITHUB_REPO, VENDOR, __version__
from omniwrench.core.i18n import current_language, tr

from . import knowledge
from .functions import (
    LEVEL_CHANGE, LEVEL_DESCRIBE, LEVEL_OVERVIEW, CallContext, Function, register, unregister_source,
)

WIKI_URL = f"https://github.com/{GITHUB_REPO}/wiki"


def _obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or []}


def _tool_info(window, tool_id: str, tool) -> dict:
    m = tool.manifest
    return {"id": tool_id, "name": m.display_name, "version": m.version,
            "description": m.localized("description"), "category": " › ".join(m.category_path),
            "platforms": m.platforms, "wiki": m.homepage or "",
            "open": any(o.tool_id == tool_id for o in window.open_tools.values()),
            "broken": bool(getattr(tool, "error", None))}


def register_app_functions(window) -> None:
    unregister_source("app")

    def program_info(args: dict, ctx: CallContext) -> Any:
        return {"program": APP_NAME, "vendor": VENDOR, "version": __version__,
                "os": f"{platform.system()} {platform.release()}", "language": current_language(),
                "wiki": WIKI_URL, "installed_tools": len(window.manager.tools),
                "hint": "Tools are installed from the Store (View > Store). Each tool has a wiki page."}

    def list_installed(args: dict, ctx: CallContext) -> Any:
        return ctx.in_gui(lambda: [_tool_info(window, tid, t) for tid, t in sorted(window.manager.tools.items())])

    def list_store(args: dict, ctx: CallContext) -> Any:
        def collect():
            cat = window.catalog
            if cat is None:
                return {"note": "The store catalog is not loaded yet. Ask the user to open the Store once."}
            out = []
            for tid, entry in sorted(cat.entries.items()):
                m = entry.manifest
                inst = window.manager.get(tid)
                out.append({"id": tid, "name": m.display_name, "version": m.version,
                            "description": m.localized("description"), "category": " › ".join(m.category_path),
                            "platforms": m.platforms, "installed": inst is not None,
                            "update_available": tid in window.tool_updates, "wiki": m.homepage or ""})
            return out
        return ctx.in_gui(collect)

    def search_docs(args: dict, ctx: CallContext) -> Any:
        hits = knowledge.search(str(args.get("query", "")), int(args.get("limit") or 6))
        return hits or {"note": "No matching documentation found."}

    def read_page(args: dict, ctx: CallContext) -> Any:
        page = knowledge.read_page(str(args.get("page", "")))
        return page or {"note": "Page not found.", "pages": knowledge.page_list()}

    def open_tabs(args: dict, ctx: CallContext) -> Any:
        return ctx.in_gui(lambda: [{"tab": name, "tool_id": o.tool_id} for name, o in window.open_tools.items()])

    def open_tool(args: dict, ctx: CallContext) -> Any:
        tid = str(args.get("tool_id", ""))
        if window.manager.get(tid) is None:
            return {"error": f"Tool {tid} is not installed."}
        ctx.in_gui(lambda: window.open_tool(tid))
        return {"opened": tid}

    def install_tool(args: dict, ctx: CallContext) -> Any:
        tid = str(args.get("tool_id", ""))

        def run():
            cat = window.catalog
            entry = cat.entries.get(tid) if cat else None
            if entry is None:
                return {"error": f"Tool {tid} is not in the store catalog."}
            window.install_entry(entry)
            return {"started": tid, "note": "The installation window is shown to the user."}
        return ctx.in_gui(run)

    for fn in (
        Function("program_info", "Version, operating system, language and wiki of OmniWrench.", program_info,
                 level=LEVEL_DESCRIBE),
        Function("list_installed_tools", "Installed OmniWrench tools with description, version, wiki page and "
                 "whether a tab is open.", list_installed, level=LEVEL_DESCRIBE),
        Function("list_store_tools", "All tools offered in the OmniWrench Store (installed or not, updates). Use it "
                 "to recommend a tool that is not installed yet.", list_store, level=LEVEL_DESCRIBE),
        Function("search_documentation", "Full-text search in the OmniWrench wiki (German). Returns matching "
                 "sections with page name and link.", search_docs,
                 _obj({"query": {"type": "string", "description": "Search words (German works best)"},
                       "limit": {"type": "integer", "description": "Max. results (default 6)"}}, ["query"]),
                 level=LEVEL_DESCRIBE),
        Function("read_documentation_page", "Read a complete wiki page, e.g. 'Tool-IconForge'.", read_page,
                 _obj({"page": {"type": "string", "description": "Page name"}}, ["page"]), level=LEVEL_DESCRIBE),
        Function("list_open_tabs", "Tool tabs currently open in OmniWrench.", open_tabs, level=LEVEL_OVERVIEW),
        Function("open_tool", "Open an installed tool in a new tab.", open_tool,
                 _obj({"tool_id": {"type": "string"}}, ["tool_id"]), level=LEVEL_CHANGE, confirm=True,
                 summary=lambda a: tr("ai.fn.open_tool", tool=a.get("tool_id", ""))),
        Function("install_tool", "Start installing a tool from the store (the user sees the install window).",
                 install_tool, _obj({"tool_id": {"type": "string"}}, ["tool_id"]), level=LEVEL_CHANGE,
                 confirm=True, summary=lambda a: tr("ai.fn.install_tool", tool=a.get("tool_id", ""))),
    ):
        register(fn)
