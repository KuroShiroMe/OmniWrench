"""dhcpapi.py gegen die offiziellen Win32-Metadaten (windows-sys 0.52, Dhcp/mod.rs) prüfen: Felder, Größen, Signaturen."""
import ctypes, re, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from tools.ms_dhcp_extended import dhcpapi as A
src = open(sys.argv[1]).read()
aliases = dict(re.findall(r"pub type (\w+) = (\w+);", src))
defs = {}
for kind, name, body in re.findall(r"pub (struct|union) (\w+) \{(.*?)\n\}", src, re.S):
    fields = re.findall(r"pub (\w+): ([^,\n]+),", body)
    defs[name] = (kind, fields)
PRIM = {"u8": 1, "i8": 1, "u16": 2, "i16": 2, "u32": 4, "i32": 4, "u64": 8, "i64": 8, "f32": 4, "f64": 8, "BOOL": 4, "BOOLEAN": 1}
def norm(t):
    t = t.strip().split("::")[-1].strip()
    return t
def layout(t):
    t = t.strip()
    if t.startswith("*") or "PWSTR" in t or "PCWSTR" in t or "PSTR" in t or "c_void" in t and t.startswith("*"):
        return 8, 8
    m = re.match(r"\[(.+);\s*(\d+)\]", t)
    if m:
        s, a = layout(m.group(1)); return s * int(m.group(2)), a
    n = norm(t)
    if n in PRIM: return PRIM[n], PRIM[n]
    if n in aliases: return layout(aliases[n])
    if n in defs:
        kind, fields = defs[n]
        off = 0; al = 1; mx = 0
        for _, ft in fields:
            s, a = layout(ft); al = max(al, a)
            if kind == "union": mx = max(mx, s)
            else:
                off = (off + a - 1) // a * a + s
        size = mx if kind == "union" else off
        return (size + al - 1) // al * al, al
    raise KeyError(t)
bad = 0
for name in dir(A):
    cls = getattr(A, name)
    if not (isinstance(cls, type) and issubclass(cls, (ctypes.Structure, ctypes.Union))) or name.startswith("_"):
        continue
    if name not in defs:
        print("?? nicht in Metadaten:", name); continue
    kind, fields = defs[name]
    mine = [f[0] for f in cls._fields_]
    theirs = [f[0] for f in fields]
    rs, _ = layout(name)
    ok = rs == ctypes.sizeof(cls) and len(mine) == len(theirs)
    detail = []
    for (fn, ft), (pn, pt) in zip(fields, cls._fields_):
        s, _ = layout(ft)
        if s != ctypes.sizeof(pt) or fn.lower() != pn.lower():
            ok = False; detail.append(f"{fn}:{ft}({s}) vs {pn}({ctypes.sizeof(pt)})")
    # Offsets
    if ok:
        pass
    print(("OK  " if ok else "BAD ") + f"{name}: rust {rs} / py {ctypes.sizeof(cls)}", "; ".join(detail) if detail else "",
          "" if len(mine) == len(theirs) else f"fields {theirs} vs {mine}")
    bad += not ok
# Signaturen
sigs = {}
for name, args in re.findall(r"fn (Dhcp\w+)\((.*?)\) -> u32\);", src):
    parts = [p.split(":", 1)[1].strip() for p in re.split(r",\s*(?=\w+ :)", args) if ":" in p]
    sigs[name] = parts
for name, args in A._PROTOS.items():
    if name not in sigs:
        print("?? Funktion fehlt:", name); bad += 1; continue
    theirs = sigs[name]
    ok = len(theirs) == len(args)
    det = []
    for i, (t, p) in enumerate(zip(theirs, args)):
        s, _ = layout(t)
        ps = ctypes.sizeof(p)
        if s != ps:
            ok = False; det.append(f"#{i} {t} vs {p.__name__}")
        if t.startswith("*mut *mut") or t.startswith("*mut"):
            inner = re.sub(r"^\*mut\s*", "", t)
            pi = getattr(p, "_type_", None)
            if inner.startswith("*mut") and pi is not None:
                pi2 = getattr(pi, "_type_", None)
                tn = norm(re.sub(r"^\*mut\s*", "", inner))
                if pi2 is not None and hasattr(pi2, "__name__") and tn != pi2.__name__ and tn in defs:
                    ok = False; det.append(f"#{i} {tn} vs {pi2.__name__}")
            elif pi is not None and hasattr(pi, "__name__") and norm(inner) in defs and norm(inner) != pi.__name__:
                ok = False; det.append(f"#{i} {norm(inner)} vs {pi.__name__}")
    print(("OK  " if ok else "BAD ") + name, "; ".join(det), "" if len(theirs) == len(args) else f"n {len(theirs)} vs {len(args)}")
    bad += not ok
print("FEHLER", bad)
