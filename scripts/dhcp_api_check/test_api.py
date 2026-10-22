import ctypes, json, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[2]))
from tools.ms_dhcp_extended import dhcpapi as A
from tools.ms_dhcp_extended.backend import ApiBackend, HostError
from tools.ms_dhcp_extended import service as S
lib = ctypes.CDLL(sys.argv[1] if len(sys.argv) > 1 else "./libfake.so")
A._lib = A.setup(lib)
b = ApiBackend()
svc = S.DhcpService(b, lambda k, d=None, **kw: f"{k}{kw}")
steps = []
print("connect", b.call("connect", {"server": "dhcp01", "primary": True}, steps.append), steps)
try:
    b.call("connect", {"server": "bad", "primary": False}, steps.append)
except HostError as e:
    print("bad ->", e, "| text:", svc.host_text(str(e)))
svc.server = "dhcp01"
def show(name, **p):
    r = b.call("cim", {"name": name, "server": "dhcp01", "params": p})["items"]
    print(name, p, "->", json.dumps(r, ensure_ascii=False, default=str)[:400])
    return r
sc = show("Get-DhcpServerv4Scope")
print("n_scope", [S.n_scope(x) for x in sc])
print("missing", show("Get-DhcpServerv4Scope", ScopeId="10.9.0.0"))
print("n_excl", [S.n_excl(x) for x in show("Get-DhcpServerv4ExclusionRange")])
print("n_res", [S.n_res(x) for x in show("Get-DhcpServerv4Reservation", ScopeId="10.1.0.0")])
print("n_lease", [S.n_lease(x) for x in show("Get-DhcpServerv4Lease", ScopeId="10.1.0.0")])
print("n_stats", [S.n_stats(x) for x in show("Get-DhcpServerv4ScopeStatistics")])
print("n_def", [S.n_def(x) for x in show("Get-DhcpServerv4OptionDefinition", All=True)])
print("n_opt srv", [S.n_opt(x) for x in show("Get-DhcpServerv4OptionValue", All=True)])
print("n_opt scope", [S.n_opt(x) for x in show("Get-DhcpServerv4OptionValue", All=True, ScopeId="10.1.0.0")])
print("n_dns", [S.n_dns(x) for x in show("Get-DhcpServerv4DnsSetting", ScopeId="10.1.0.0")])
print("n_fo", [S.n_fo(x) for x in show("Get-DhcpServerv4Failover")])
show("Get-DhcpServerv4Superscope")
print("fo enum", b.call("fo_api", {"server": "dhcp02", "op": "enum"}))
# Schreiben
b.call("cim", {"name": "Set-DhcpServerv4OptionValue", "server": "dhcp01", "params": {"ScopeId": "10.1.0.0", "OptionId": 6, "Value": ["10.0.0.7", "10.0.0.8"]}})
print("set ip", lib.set_id if False else ctypes.c_uint32.in_dll(lib, "set_id").value, ctypes.c_int.in_dll(lib, "set_type").value, ctypes.c_int.in_dll(lib, "set_n").value, A.n2ip(ctypes.c_uint32.in_dll(lib, "set_v0").value), A.n2ip(ctypes.c_uint32.in_dll(lib, "set_v1").value), A.n2ip(ctypes.c_uint32.in_dll(lib, "set_scope").value))
b.call("cim", {"name": "Set-DhcpServerv4OptionValue", "server": "dhcp01", "params": {"OptionId": 15, "Value": ["beispiel.de"]}})
print("set str", ctypes.c_int.in_dll(lib, "set_type").value, ctypes.c_uint32.in_dll(lib, "set_scope").value, ctypes.c_wchar_p(ctypes.addressof(ctypes.c_wchar.in_dll(lib, "set_str"))).value)
b.call("cim", {"name": "Set-DhcpServerv4OptionValue", "server": "dhcp01", "params": {"ScopeId": "10.1.0.0", "OptionId": 43, "Value": ["0x01CD"]}})
print("set bin", ctypes.c_int.in_dll(lib, "set_type").value, ctypes.c_int.in_dll(lib, "set_blen").value, hex(ctypes.c_ubyte.in_dll(lib, "set_b0").value))
b.call("cim", {"name": "Set-DhcpServerv4OptionValue", "server": "dhcp01", "params": {"OptionId": 1, "Value": ["1"], "VendorClass": "Microsoft Windows 2000 Options"}})
print("set vendor", ctypes.c_uint32.in_dll(lib, "set_flags").value, ctypes.c_int.in_dll(lib, "set_type").value, ctypes.c_wchar_p(ctypes.addressof(ctypes.c_wchar.in_dll(lib, "set_vendor"))).value)
svc.scope_set("10.1.0.0", Name="Neu", State="InActive", LeaseDuration=86400)
print("set scope", ctypes.c_uint32.in_dll(lib, "last_set_state").value, ctypes.c_wchar_p(ctypes.addressof(ctypes.c_wchar.in_dll(lib, "last_set_name"))).value, "lease ->", ctypes.c_uint32.in_dll(lib, "set_id").value, ctypes.c_uint32.in_dll(lib, "set_v0").value)
svc.scope_set("10.1.0.0", StartRange="10.1.0.5", EndRange="10.1.0.250")
print("range", ctypes.c_int.in_dll(lib, "added_type").value, A.n2ip(ctypes.c_uint32.in_dll(lib, "added_a").value), A.n2ip(ctypes.c_uint32.in_dll(lib, "added_b").value), "removed", ctypes.c_int.in_dll(lib, "removed").value)
svc.res_add("10.1.0.0", {"ip": "10.1.0.30", "cid": "00-aa-bb-cc-dd-ee", "name": "x", "desc": "", "type": "Dhcp"}) if False else None
svc.excl_add("10.1.0.0", "10.1.0.70", "10.1.0.80")
print("excl", ctypes.c_int.in_dll(lib, "added_type").value, A.n2ip(ctypes.c_uint32.in_dll(lib, "added_a").value), A.n2ip(ctypes.c_uint32.in_dll(lib, "added_b").value))
svc.dns_set("10.1.0.0", {"dyn": "Always", "delete_on_expiry": True, "older": False, "disable_ptr": True, "name_protection": False})
print("dns", ctypes.c_uint32.in_dll(lib, "set_id").value, hex(ctypes.c_uint32.in_dll(lib, "set_v0").value))
b.call("fo_api", {"server": "dhcp01", "op": "set", "rel": {"name": "dhcp01-dhcp02", "percentage": 40}, "flags": 8})
print("fo set", ctypes.c_uint32.in_dll(lib, "fo_set_flags").value, ctypes.c_uint32.in_dll(lib, "fo_set_pct").value, ctypes.c_wchar_p(ctypes.addressof(ctypes.c_wchar.in_dll(lib, "fo_name"))).value)
try:
    b.call("fo_api", {"server": "dhcp01", "op": "add_scopes", "rel": {"name": "x", "scopes": ["10.1.0.0", "10.2.0.0"]}})
except HostError as e:
    print("fo add ->", svc.host_text(str(e)), A.n2ip(ctypes.c_uint32.in_dll(lib, "fo_scopes").value))
# cim_many parallel
got = []
res = svc.cim_many([("Get-DhcpServerv4Scope", None, {}), ("Get-DhcpServerv4Lease", None, {"ScopeId": "10.1.0.0"}), ("Get-DhcpServerv4Nope", None, {})], 4, lambda k, v: got.append(k))
print("cim_many", len(res), len(got), [type(v).__name__ for v in res.values()])
try:
    svc.cim_many([("Remove-DhcpServerv4Scope", None, {})])
except S.UserError as e:
    print("blocked", e)
ws = lambda n: ctypes.c_wchar_p(ctypes.addressof(ctypes.c_wchar.in_dll(lib, n))).value
u = lambda n: ctypes.c_uint32.in_dll(lib, n).value
svc.res_add("10.1.0.0", {"ip": "10.1.0.30", "cid": "00-aa-bb-cc-dd-ee", "name": "neu", "desc": "d", "type": "Dhcp"})
print("add", ctypes.c_int.in_dll(lib, "added_type").value, A.n2ip(u("added_a")), u("added_b"), "client", A.n2ip(u("ci_ip")), ws("ci_name"), ws("ci_comment"), u("ci_hwlen"))
r0 = ctypes.c_int.in_dll(lib, "removed").value
svc.res_set({"ip": "10.1.0.20", "cid": "00-11-22-33-44-55", "name": "drucker2", "desc": "", "type": "Both"})
print("set same cid: removed", ctypes.c_int.in_dll(lib, "removed").value - r0, ws("ci_name"), repr(ws("ci_comment")))
svc.res_set({"ip": "10.1.0.20", "cid": "00-11-22-33-44-99", "name": "drucker3", "desc": "x", "type": "Dhcp"})
print("set new cid: removed", ctypes.c_int.in_dll(lib, "removed").value - r0, "added", A.n2ip(u("added_a")), u("added_b"))
svc.res_remove("10.1.0.0", "10.1.0.20"); print("remove ok", ctypes.c_int.in_dll(lib, "removed").value - r0)
try:
    svc.res_remove("10.1.0.0", "10.1.0.99")
except S.UserError as e:
    print("missing ->", e)
# Rechte: Schreibprobe ohne Änderung (FieldsToSet = 0)
print("access", b.call("access", {"server": "dhcp01"}), b.call("access", {"server": "ro"}), "fields", u("cfg_fields"))
