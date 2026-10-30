"""KI-Assistent: Funktionen von IconForge für den Assistenten des Hauptprogramms (ab OmniWrench 0.9.0)."""

from __future__ import annotations

MAX_HITS = 60


class IconForgeAI:
    def __init__(self, tool):
        self.tool = tool
        add = getattr(tool.context, "ai_function", None)
        if add is None:     # älteres Hauptprogramm ohne KI
            return
        from omniwrench.sdk import AI_OVERVIEW, AI_READ
        add("iconforge_packs", "IconForge: installed icon packs with licence and number of icons.", self.packs,
            level=AI_OVERVIEW)
        add("iconforge_search", "IconForge: search icons of the installed packs by name, tag or category "
            "(English words work best). Returns pack, variant and name.", self.search, level=AI_READ,
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
        add("iconforge_show", "IconForge: select an icon in the tool so the user can preview and export it.",
            self.show, level=AI_READ,
            parameters={"type": "object", "properties": {
                "pack": {"type": "string"}, "variant": {"type": "string"}, "name": {"type": "string"}},
                "required": ["pack", "name"]})

    def packs(self, args, call):
        def read():
            st = self.tool.store
            out = []
            for pid, spec in st.defs.items():
                if not st.is_available(pid):
                    continue
                idx = st.index(pid)
                out.append({"pack": pid, "name": spec.get("name", pid), "version": idx.get("version", ""),
                            "license": st.license_key(pid), "icons": len(st.items(pid)),
                            "variants": list(idx.get("variants", {}))})
            return out
        return call.in_gui(read)

    def search(self, args, call):
        words = [w for w in str(args.get("query") or "").lower().split() if w]

        def read():
            st = self.tool.store
            hits, seen = [], set()
            for pid in st.defs:
                if not st.is_available(pid):
                    continue
                for ref in st.items(pid):
                    if (ref.pack, ref.name) in seen:
                        continue
                    info = st.info(ref)
                    hay = " ".join([ref.name] + list(info.get("tags", [])) + list(info.get("categories", []))).lower()
                    if all(w in hay for w in words):
                        seen.add((ref.pack, ref.name))
                        hits.append({"pack": ref.pack, "variant": ref.variant, "name": ref.name,
                                     "brand": st.is_brand(ref)})
                        if len(hits) >= MAX_HITS:
                            return {"items": hits, "truncated": True}
            return {"items": hits, "truncated": False}
        return call.in_gui(read)

    def show(self, args, call):
        def go():
            t = self.tool
            pack, name = str(args.get("pack") or ""), str(args.get("name") or "")
            if t.pack.findData(pack) < 0:
                return {"error": f"Pack {pack} is not installed."}
            t.pack.setCurrentIndex(t.pack.findData(pack))
            if args.get("variant") and t.variant.findData(args["variant"]) >= 0:
                t.variant.setCurrentIndex(t.variant.findData(args["variant"]))
            t.search.setText(name)
            model = t.proxy
            for row in range(model.rowCount()):
                idx = model.index(row, 0)
                ref = idx.data(t.model.REF)
                if ref is not None and ref.name == name:
                    t.view.setCurrentIndex(idx)
                    t.view.scrollTo(idx)
                    return {"ok": True, "shown": f"{pack}/{ref.variant}/{name}"}
            return {"error": f"Icon {name} not found in {pack}."}
        return call.in_gui(go)
