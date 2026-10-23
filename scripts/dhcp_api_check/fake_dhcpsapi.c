// Fake dhcpsapi für Linux-Tests von dhcpapi.py (gleiche Strukturlayouts wie Win64, wchar_t hier 4 Byte)
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdint.h>
typedef uint32_t DWORD; typedef int BOOL; typedef uint8_t BYTE; typedef uint16_t WORD; typedef wchar_t* LPWSTR;
typedef struct { DWORD lo, hi; } DATE_TIME;
typedef struct { DWORD DataLength; BYTE* Data; } BIN;
typedef struct { DWORD IpAddress; LPWSTR NetBiosName; LPWSTR HostName; } HOST;
typedef struct { DWORD NumElements; DWORD* Elements; } IPARR;
typedef struct { DWORD SubnetAddress, SubnetMask; LPWSTR SubnetName, SubnetComment; HOST PrimaryHost; int SubnetState; } SUBNET;
typedef struct { DWORD Start, End; } RANGE;
typedef struct { DWORD Start, End, Ba, Mb; } BRANGE;
typedef struct { DWORD Ip; BIN* Uid; BYTE Types; } RESV;
typedef struct { int Type; union { BRANGE* IpRange; RESV* ReservedIp; RANGE* Excl; void* p; } u; } ELEM;
typedef struct { DWORD NumElements; ELEM* Elements; } ELARR;
typedef struct { DWORD Ip, Mask; BIN Hw; LPWSTR Name, Comment; DATE_TIME Exp; HOST Owner; BYTE Type; BYTE State; } CL5;
typedef struct { DWORD Ip, Mask; BIN Hw; LPWSTR Name, Comment; DATE_TIME Exp; HOST Owner; BYTE Type; } CL4;
typedef struct { DWORD NumElements; CL5** Clients; } CLARR;
typedef struct { DWORD d1, d2; } DD;
typedef struct { int Type; union { BYTE b; WORD w; DWORD dw; DD dd; DWORD ip; LPWSTR s; BIN bin; } u; } OEL;
typedef struct { DWORD NumElements; OEL* Elements; } ODATA;
typedef struct { DWORD Id; LPWSTR Name, Comment; ODATA Def; int OptionType; } OPT;
typedef struct { DWORD NumElements; OPT* Options; } OPTARR;
typedef struct { OPT Option; LPWSTR Vendor, Class; } VOPT;
typedef struct { DWORD Flags; OPTARR* NonVendor; DWORD NumVendor; VOPT* Vendor; } ALLOPT;
typedef struct { DWORD Id; ODATA Value; } OVAL;
typedef struct { DWORD NumElements; OVAL* Values; } OVARR;
typedef struct { LPWSTR Class, Vendor; BOOL IsVendor; OVARR* Arr; } AOVI;
typedef struct { DWORD Flags, NumElements; AOVI* Options; } AOV;
typedef struct { int Type; union { void* p; DWORD subnet; DD res; } u; } SCOPEINFO;
typedef struct { DWORD Subnet, InUse, Free, Pend; } SMIB;
typedef struct { DWORD a[7]; DATE_TIME t; DWORD Scopes; SMIB* Info; } MIB;
typedef struct { DWORD Subnet, Num, Next; LPWSTR Name; } SSE;
typedef struct { DWORD n; SSE* e; } SST;
typedef struct { DWORD P, S; int Mode, Type, State, Prev; DWORD Mclt, Safe; LPWSTR Name, PName, SName; IPARR* Scopes; BYTE Pct; LPWSTR Secret; } FOREL;
typedef struct { DWORD n; FOREL* r; } FOARR;

static void* M(size_t n) { void* p = calloc(1, n); return p; }
static wchar_t* W(const wchar_t* s) { wchar_t* p = M((wcslen(s) + 1) * sizeof(wchar_t)); wcscpy(p, s); return p; }
#define IP(a,b,c,d) (((DWORD)(a)<<24)|((DWORD)(b)<<16)|((DWORD)(c)<<8)|(DWORD)(d))
#define S1 IP(10,1,0,0)
#define S2 IP(10,2,0,0)

void DhcpRpcFreeMemory(void* p) { (void)p; }
DWORD DhcpGetVersion(LPWSTR s, DWORD* ma, DWORD* mi) { if (wcscmp(s, L"bad") == 0) return 1722; *ma = 10; *mi = 0; return 0; }
DWORD DhcpEnumSubnets(LPWSTR s, DWORD* resume, DWORD pref, IPARR** out, DWORD* r, DWORD* t) {
    IPARR* a = M(sizeof *a); a->NumElements = 1; a->Elements = M(4); *t = 2; *r = 1;
    if (*resume == 0) { a->Elements[0] = S1; *resume = 1; *out = a; return 234; }
    if (*resume == 1) { a->Elements[0] = S2; *resume = 2; *out = a; return 0; }
    return 259;
}
DWORD DhcpGetSubnetInfo(LPWSTR s, DWORD sid, SUBNET** out) {
    if (sid != S1 && sid != S2) return 20005;
    SUBNET* x = M(sizeof *x); x->SubnetAddress = sid; x->SubnetMask = IP(255,255,255,0);
    x->SubnetName = W(sid == S1 ? L"Büro" : L"Lager"); x->SubnetComment = W(L"Kommentar"); x->SubnetState = sid == S1 ? 0 : 1;
    *out = x; return 0;
}
// Verteilbereich je Scope; S1 ist ein Failover-Scope (Bereich darf nicht gelöscht werden, nur angepasst)
DWORD rng_s[2] = {S1 + 10, S2 + 10}, rng_e[2] = {S1 + 200, S2 + 200}; int range_adds = 0, range_fail_at = 0;
DWORD last_set_state = 99; wchar_t last_set_name[64];
DWORD DhcpSetSubnetInfo(LPWSTR s, DWORD sid, SUBNET* i) { last_set_state = i->SubnetState; wcsncpy(last_set_name, i->SubnetName, 63); return 0; }
DWORD DhcpEnumSubnetElementsV5(LPWSTR s, DWORD sid, int type, DWORD* resume, DWORD pref, ELARR** out, DWORD* r, DWORD* t) {
    if (*resume) return 259;
    if (sid != S1 && sid != S2) return 20005;
    ELARR* a = M(sizeof *a); a->Elements = M(sizeof(ELEM) * 2); *resume = 1;
    if (type == 0) { BRANGE* b = M(sizeof *b); b->Start = rng_s[sid == S2]; b->End = rng_e[sid == S2]; a->Elements[0].Type = 5; a->Elements[0].u.IpRange = b; a->NumElements = 1; }
    else if (type == 3 && sid == S1) { RANGE* x = M(sizeof *x); x->Start = sid + 50; x->End = sid + 60; a->Elements[0].Type = 3; a->Elements[0].u.Excl = x; a->NumElements = 1; }
    else if (type == 2 && sid == S1) {
        RESV* x = M(sizeof *x); x->Ip = sid + 20; x->Types = 3; x->Uid = M(sizeof(BIN));
        // Reservierung im Format Subnetz (little endian) + 01 + MAC
        BYTE raw[11] = {0x00, 0x00, 0x01, 0x0a, 1, 0x00, 0x11, 0x22, 0x33, 0x44, 0x55};
        x->Uid->DataLength = 11; x->Uid->Data = M(11); memcpy(x->Uid->Data, raw, 11);
        a->Elements[0].Type = 2; a->Elements[0].u.ReservedIp = x; a->NumElements = 1;
    } else { *out = a; return 259; }
    *r = *t = a->NumElements; *out = a; return 0;
}
int added_type = -1; DWORD added_a = 0, added_b = 0; int removed = 0;
DWORD DhcpAddSubnetElementV5(LPWSTR s, DWORD sid, ELEM* e) {
    added_type = e->Type;
    if (e->Type == 2) { added_a = e->u.ReservedIp->Ip; added_b = e->u.ReservedIp->Uid->DataLength; }
    else if (e->Type == 3) { added_a = e->u.Excl->Start; added_b = e->u.Excl->End; }
    else {
        // MS-DHCPM 3.2.4.38: vorhandener Bereich wird angepasst, neuer muss alten enthalten oder darin liegen
        DWORD a = e->u.IpRange->Start, b = e->u.IpRange->End; int i = sid == S2;
        added_a = a; added_b = b; range_adds++;
        if (range_fail_at && range_adds == range_fail_at) return 20112;
        if (b < a) return 20023;
        if (rng_s[i] && !((a <= rng_s[i] && rng_e[i] <= b) || (rng_s[i] <= a && b <= rng_e[i]))) return 20023;
        rng_s[i] = a; rng_e[i] = b;
    }
    return 0;
}
DWORD DhcpRemoveSubnetElementV5(LPWSTR s, DWORD sid, ELEM* e, int f) {
    if ((e->Type == 0 || e->Type == 5) && sid == S1) return 20132;     // ERROR_DHCP_FO_RANGE_PART_OF_REL
    if (e->Type == 0 || e->Type == 5) rng_s[sid == S2] = rng_e[sid == S2] = 0;
    removed++; return 0;
}
DWORD DhcpEnumSubnetClientsV5(LPWSTR s, DWORD sid, DWORD* resume, DWORD pref, CLARR** out, DWORD* r, DWORD* t) {
    if (*resume || sid != S1) return 259;
    CLARR* a = M(sizeof *a); a->NumElements = 2; a->Clients = M(sizeof(CL5*) * 2);
    for (int i = 0; i < 2; i++) {
        CL5* c = M(sizeof *c); a->Clients[i] = c; c->Mask = IP(255,255,255,0);
        c->Hw.DataLength = 6; c->Hw.Data = M(6); BYTE mac[6] = {0, 0x11, 0x22, 0x33, 0x44, (BYTE)(0x55 + i)}; memcpy(c->Hw.Data, mac, 6);
        c->Ip = i ? sid + 100 : sid + 20; c->Name = W(i ? L"pc01.firma.local" : L"drucker"); c->Comment = W(i ? L"" : L"EG");
        c->Exp.hi = i ? 0x01DC4000 : 0x7FFFFFFF; c->Exp.lo = 0xFFFFFFFF; c->Type = i ? 1 : 3 | 4; c->State = 1;
    }
    *resume = 1; *out = a; *r = *t = 2; return 0;
}
static OEL ipel(DWORD ip) { OEL e; memset(&e, 0, sizeof e); e.Type = 4; e.u.ip = ip; return e; }
static void opt(OPT* o, DWORD id, const wchar_t* name, int type, int multi) {
    o->Id = id; o->Name = W(name); o->Comment = W(L"c"); o->OptionType = multi; o->Def.NumElements = 1; o->Def.Elements = M(sizeof(OEL));
    o->Def.Elements[0].Type = type; if (type == 5) o->Def.Elements[0].u.s = W(L"");
}
DWORD DhcpGetAllOptions(LPWSTR s, DWORD f, ALLOPT** out) {
    ALLOPT* a = M(sizeof *a); a->NonVendor = M(sizeof(OPTARR)); a->NonVendor->NumElements = 5; a->NonVendor->Options = M(sizeof(OPT) * 5);
    OPT* o = a->NonVendor->Options;
    opt(&o[0], 3, L"Router", 4, 1); opt(&o[1], 6, L"DNS Servers", 4, 1); opt(&o[2], 15, L"DNS Domain Name", 5, 0);
    opt(&o[3], 51, L"Lease", 2, 0); opt(&o[4], 43, L"Vendor Specific", 6, 0);
    a->NumVendor = 1; a->Vendor = M(sizeof(VOPT)); opt(&a->Vendor[0].Option, 1, L"Microsoft Disable Netbios Option", 2, 0);
    a->Vendor[0].Vendor = W(L"Microsoft Windows 2000 Options"); a->Vendor[0].Class = NULL;
    *out = a; return 0;
}
static ODATA data1(OEL e) { ODATA d; d.NumElements = 1; d.Elements = M(sizeof(OEL)); d.Elements[0] = e; return d; }
DWORD DhcpGetAllOptionValues(LPWSTR s, DWORD f, SCOPEINFO* si, AOV** out) {
    AOV* a = M(sizeof *a); a->NumElements = 2; a->Options = M(sizeof(AOVI) * 2);
    OVARR* arr = M(sizeof *arr); a->Options[0].Arr = arr;
    OVARR* varr = M(sizeof *varr); a->Options[1].Arr = varr; a->Options[1].IsVendor = 1; a->Options[1].Vendor = W(L"Microsoft Windows 2000 Options");
    varr->NumElements = 1; varr->Values = M(sizeof(OVAL)); varr->Values[0].Id = 1; OEL v; memset(&v, 0, sizeof v); v.Type = 2; v.u.dw = 2; varr->Values[0].Value = data1(v);
    if (si->Type == 1) {
        arr->NumElements = 1; arr->Values = M(sizeof(OVAL)); arr->Values[0].Id = 6;
        ODATA d; d.NumElements = 2; d.Elements = M(sizeof(OEL) * 2); d.Elements[0] = ipel(IP(10,0,0,5)); d.Elements[1] = ipel(IP(10,0,0,6));
        arr->Values[0].Value = d;
    } else {
        arr->NumElements = 4; arr->Values = M(sizeof(OVAL) * 4);
        arr->Values[0].Id = 3; arr->Values[0].Value = data1(ipel(si->u.subnet + 1));
        OEL e; memset(&e, 0, sizeof e); e.Type = 2; e.u.dw = 691200; arr->Values[1].Id = 51; arr->Values[1].Value = data1(e);
        OEL st; memset(&st, 0, sizeof st); st.Type = 5; st.u.s = W(L"firma.local"); arr->Values[2].Id = 15; arr->Values[2].Value = data1(st);
        OEL b; memset(&b, 0, sizeof b); b.Type = 6; b.u.bin.DataLength = 2; b.u.bin.Data = M(2); b.u.bin.Data[0] = 1; b.u.bin.Data[1] = 0xAB;
        arr->Values[3].Id = 43; arr->Values[3].Value = data1(b);
    }
    *out = a; return 0;
}
DWORD DhcpGetOptionValueV5(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, SCOPEINFO* si, OVAL** out) {
    if (id == 51 && si->Type == 2) { OVAL* o = M(sizeof *o); OEL e; memset(&e, 0, sizeof e); e.Type = 2; e.u.dw = 691200; o->Id = 51; o->Value = data1(e); *out = o; return 0; }
    if (id == 81 && si->Type == 1) { OVAL* o = M(sizeof *o); OEL e; memset(&e, 0, sizeof e); e.Type = 2; e.u.dw = 0x01 | 0x04 | 0x20; o->Id = 81; o->Value = data1(e); *out = o; return 0; }
    return 20010;
}
int set_type = -1, set_n = -1; DWORD set_id = 0, set_v0 = 0, set_v1 = 0, set_scope = 0, set_flags = 9; wchar_t set_str[64]; wchar_t set_vendor[64]; int set_blen = -1; BYTE set_b0 = 0;
DWORD DhcpSetOptionValueV5(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, SCOPEINFO* si, ODATA* d) {
    set_flags = f; set_id = id; set_n = d->NumElements; set_type = d->Elements[0].Type; set_scope = si->Type == 2 ? si->u.subnet : 0;
    set_vendor[0] = 0; if (v) wcsncpy(set_vendor, v, 63);
    if (set_type == 4) { set_v0 = d->Elements[0].u.ip; if (set_n > 1) set_v1 = d->Elements[1].u.ip; }
    else if (set_type == 5) wcsncpy(set_str, d->Elements[0].u.s, 63);
    else if (set_type == 6) { set_blen = d->Elements[0].u.bin.DataLength; set_b0 = d->Elements[0].u.bin.Data[1]; }
    else if (set_type == 3) { set_v0 = d->Elements[0].u.dd.d1; set_v1 = d->Elements[0].u.dd.d2; }
    else set_v0 = d->Elements[0].u.dw;
    return 0;
}
DWORD DhcpGetMibInfo(LPWSTR s, MIB** out) {
    MIB* m = M(sizeof *m); m->Scopes = 2; m->Info = M(sizeof(SMIB) * 2);
    m->Info[0].Subnet = S1; m->Info[0].InUse = 30; m->Info[0].Free = 150; m->Info[1].Subnet = S2; m->Info[1].Free = 191;
    *out = m; return 0;
}
DWORD DhcpGetSuperScopeInfoV4(LPWSTR s, SST** out) {
    SST* t = M(sizeof *t); t->n = 2; t->e = M(sizeof(SSE) * 2); t->e[0].Subnet = S1; t->e[0].Name = W(L"Haus"); t->e[1].Subnet = S2; *out = t; return 0;
}
DWORD DhcpV4FailoverEnumRelationship(LPWSTR s, DWORD* resume, DWORD pref, FOARR** out, DWORD* r, DWORD* t) {
    if (*resume) return 259;
    FOARR* a = M(sizeof *a); a->n = 1; a->r = M(sizeof(FOREL)); FOREL* x = a->r;
    x->P = IP(10,0,0,10); x->S = IP(10,0,0,11); x->Mode = 0; x->Type = 1; x->State = 3; x->Mclt = 3600; x->Safe = 0xFFFFFFFF;
    x->Name = W(L"dhcp01-dhcp02"); x->PName = W(L"dhcp02.firma.local"); x->SName = W(L"dhcp01.firma.local"); x->Pct = 70;
    x->Scopes = M(sizeof(IPARR)); x->Scopes->NumElements = 1; x->Scopes->Elements = M(4); x->Scopes->Elements[0] = S1;
    *resume = 1; *out = a; *r = *t = 1; return 0;
}
DWORD fo_set_pct = 0, fo_set_flags = 0, fo_scopes = 0; wchar_t fo_name[64];
DWORD DhcpV4FailoverSetRelationship(LPWSTR s, DWORD flags, FOREL* r) { fo_set_flags = flags; fo_set_pct = r->Pct; wcsncpy(fo_name, r->Name, 63); return 0; }
DWORD DhcpV4FailoverAddScopeToRelationship(LPWSTR s, FOREL* r) { fo_scopes = r->Scopes ? r->Scopes->Elements[r->Scopes->NumElements - 1] : 0; return 20120; }
typedef struct { int Type; union { DWORD ip; BIN hw; LPWSTR name; } u; } SEARCH;
wchar_t ci_name[64], ci_comment[64]; DWORD ci_ip = 0, ci_hwlen = 0;
DWORD DhcpGetClientInfoV4(LPWSTR s, SEARCH* q, CL4** out) {
    CL4* c = M(sizeof *c); c->Ip = q->u.ip; c->Mask = IP(255,255,255,0); c->Hw.DataLength = 6; c->Hw.Data = M(6);
    c->Name = W(L"alt"); c->Comment = W(L"altkommentar"); c->Type = 3; *out = c; return 0;
}
DWORD DhcpSetClientInfoV4(LPWSTR s, CL4* c) { ci_ip = c->Ip; ci_hwlen = c->Hw.DataLength; wcsncpy(ci_name, c->Name, 63); wcsncpy(ci_comment, c->Comment, 63); return 0; }
// Rechteprüfung: "ro" = nur DHCP-Benutzer (Zugriff verweigert), sonst Administrator; FieldsToSet muss 0 sein
DWORD cfg_fields = 99;
DWORD DhcpServerSetConfigV4(LPWSTR s, DWORD fields, void* c) { cfg_fields = fields; return wcscmp(s, L"ro") == 0 ? 5 : 0; }
