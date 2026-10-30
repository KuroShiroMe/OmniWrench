"""KI-Assistent: Funktionen von NetProbe für den Assistenten des Hauptprogramms (ab OmniWrench 0.9.0).

Ergebnisse und Befunde werden aus dem GUI-Thread gelesen. Neue Tests sendet NetProbe ins Netz;
deshalb gelten sie wie Änderungen (Stufe 4, das Hauptprogramm fragt vorher nach).
"""

from __future__ import annotations

import json

from . import findings as fx
from .engine import TEMPLATE_IDS
from .targets import TargetError, parse

MAX_ROWS = 500
MAX_AI_HOSTS = 256


class NetProbeAI:
    def __init__(self, tool):
        self.tool = tool
        add = getattr(tool.context, "ai_function", None)
        if add is None:     # älteres Hauptprogramm ohne KI
            return
        from omniwrench.sdk import AI_CHANGE, AI_OVERVIEW, AI_READ
        add("netprobe_results", "NetProbe (network diagnostics): list of tested targets with state, IP and number "
            "of findings per severity.", self.results, level=AI_OVERVIEW)
        add("netprobe_result", "NetProbe: findings (translated) and raw test data of one tested target "
            "(address or name as shown in netprobe_results).", self.result, level=AI_READ,
            parameters={"type": "object", "properties": {
                "target": {"type": "string"},
                "raw": {"type": "boolean", "description": "Include raw test data (default true)"}},
                "required": ["target"]})
        tr = tool.context.tr
        add("netprobe_start", "NetProbe: start tests for targets (host names, IPs, ranges or networks like "
            "192.168.1.0/28; at most 256 hosts). Sends traffic into the network, so the user confirms first. "
            "Results arrive asynchronously; read them with netprobe_results/netprobe_result.",
            self.start, level=AI_CHANGE,
            parameters={"type": "object", "properties": {
                "targets": {"type": "string"},
                "profile": {"type": "string", "enum": [t for t in TEMPLATE_IDS if t != "custom"]}},
                "required": ["targets"]},
            summary=lambda a: tr("ai.fn.start", targets=a.get("targets", ""),
                                 profile=tr("template." + (a.get("profile") or "standard"))))

    def _finding(self, f: fx.Finding) -> dict:
        tr = self.tool.context.tr
        params = {k: (", ".join(map(str, v)) if isinstance(v, (list, tuple)) else v) for k, v in f.params.items()}
        return {"level": f.level, "category": f.category, "port": f.port,
                "title": tr(f"fx.{f.id}.title", **params), "detail": tr(f"fx.{f.id}.detail", **params)}

    def results(self, args, call):
        def read():
            out = []
            for addr, res in self.tool.res_for_addr.items():
                counts: dict[str, int] = {}
                for f in res.findings:
                    counts[f.level] = counts.get(f.level, 0) + 1
                out.append({"target": res.label, "address": addr, "ip": res.ip, "group": res.target.group,
                            "state": res.status, "findings": counts})
            return {"total": len(out), "items": out[:MAX_ROWS], "running": bool(self.tool.engines)}
        return call.in_gui(read)

    def result(self, args, call):
        want = str(args.get("target") or "").strip().lower()

        def read():
            for addr, res in self.tool.res_for_addr.items():
                if want in (addr.lower(), res.label.lower(), (res.ip or "").lower()):
                    out = {"target": res.label, "address": addr, "ip": res.ip, "state": res.status,
                           "findings": [self._finding(f) for f in res.findings],
                           "errors": res.errors}
                    if args.get("raw", True) is not False:
                        out["raw"] = json.loads(json.dumps(res.raw, default=str))
                    return out
            return {"error": f"No result for {want}. Use netprobe_results for the list."}
        return call.in_gui(read)

    def start(self, args, call):
        text = str(args.get("targets") or "").strip()
        try:
            targets = parse(text, MAX_AI_HOSTS)
        except TargetError as e:
            return {"error": str(e)}
        profile = args.get("profile") or ""

        def go():
            t = self.tool
            if profile in TEMPLATE_IDS:
                t.template.setCurrentIndex(max(0, t.template.findData(profile)))
            t.input.setText(text)
            t._run_targets(targets)
            return {"started": len(targets), "profile": t.template.currentData(),
                    "hint": "Tests run in the background; ask for netprobe_results later."}
        return call.in_gui(go)
