// Fake der DHCPv6-Funktionen von dhcpsapi (zustandsbehaftet, gleiche Layouts wie Win64, wchar_t hier 4 Byte).
// Zusammen mit fake_dhcpsapi.c bauen:  gcc -shared -fPIC -o libfake.so fake_dhcpsapi.c fake_dhcpsapi6.c
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdint.h>
typedef uint32_t DWORD; typedef int BOOL; typedef uint8_t BYTE; typedef uint16_t WORD; typedef uint64_t U64; typedef wchar_t* LPWSTR;
typedef struct { DWORD lo, hi; } DATE_TIME;
typedef struct { DWORD DataLength; BYTE* Data; } BIN;
typedef struct { U64 hi, lo; } A6;
typedef struct { DWORD n; A6* e; } A6ARR;
typedef struct { A6 Addr; DWORD Prefix; WORD Pref; LPWSTR Name, Comment; DWORD State, ScopeId; } SUB6;
typedef struct { A6 Start, End; } RNG6;
typedef struct { A6 Ip; BIN* Duid; DWORD Iaid; } RES6;
typedef struct { int Type; union { RNG6* Range; RES6* Res; RNG6* Excl; } u; } EL6;
typedef struct { DWORD n; EL6* e; } EL6ARR;
typedef struct { A6 Ip; LPWSTR Nb, Host; } HOST6;
typedef struct { A6 Ip; BIN Duid; DWORD Type, Iaid; LPWSTR Name, Comment; DATE_TIME Valid, Pref; HOST6 Owner; } CL6;
typedef struct { DWORD n; CL6** c; } CL6ARR;
typedef struct { int Type; union { A6 ip; BIN duid; LPWSTR name; } u; } SEARCH6;
typedef struct { int Type; union { void* p; A6 subnet; struct { A6 ip, subnet; } res; } u; } SI6;
typedef struct { DWORD d1, d2; } DD;
typedef struct { int Type; union { BYTE b; WORD w; DWORD dw; DD dd; DWORD ip; LPWSTR s; BIN bin; } u; } OEL;
typedef struct { DWORD n; OEL* e; } ODATA;
typedef struct { DWORD Id; LPWSTR Name, Comment; ODATA Def; int OptionType; } OPT;
typedef struct { DWORD n; OPT* o; } OPTARR;
typedef struct { OPT Option; LPWSTR Vendor, Class; } VOPT;
typedef struct { DWORD Flags; OPTARR* NonVendor; DWORD NumVendor; VOPT* Vendor; } ALLOPT;
typedef struct { DWORD Id; ODATA Value; } OVAL;
typedef struct { DWORD n; OVAL* v; } OVARR;
typedef struct { LPWSTR Class, Vendor; BOOL IsVendor; OVARR* Arr; } AOVI;
typedef struct { DWORD Flags, n; AOVI* o; } AOV;
typedef struct { BOOL Unicast, Rapid; DWORD Pref, Valid, T1, T2, PrefIATA, ValidIATA; BOOL Audit; } CFG6;
typedef struct { A6 Subnet; U64 InUse, Free, Pend; } SMIB6;
typedef struct { DWORD a[10]; DATE_TIME t; DWORD Scopes; SMIB6* Info; } MIB6;
typedef struct { BOOL Status; DWORD Purge; } STATELESS;
typedef struct { DWORD Flags; BOOL Bound; A6 Prim, Sub; LPWSTR Desc; DWORD Idx, IfIdSize; BYTE* IfId; } BIND6;
typedef struct { DWORD n; BIND6* e; } BIND6ARR;

static void* M(size_t n) { return calloc(1, n); }
static wchar_t* W(const wchar_t* s) { wchar_t* p = M((wcslen(s ? s : L"") + 1) * sizeof(wchar_t)); wcscpy(p, s ? s : L""); return p; }
static int eq(A6 a, A6 b) { return a.hi == b.hi && a.lo == b.lo; }
static int le(A6 a, A6 b) { return a.hi < b.hi || (a.hi == b.hi && a.lo <= b.lo); }

// --- Zustand ------------------------------------------------------------------------------------------
#define MAXS 8
#define MAXE 16
typedef struct { int used; SUB6 s; CFG6 cfg; int nex; RNG6 ex[MAXE]; int nres; A6 rip[MAXE]; BYTE rduid[MAXE][32]; DWORD rdl[MAXE], riaid[MAXE];
                 int ncl; CL6 cl[MAXE]; } SCOPE6;
static SCOPE6 sc[MAXS];
typedef struct { int used; DWORD scope_kind; A6 sid; DWORD id; int vendor; int type; int n; wchar_t s[4][64]; DWORD dw[4]; } OV6;
static OV6 ov[64];
typedef struct { int used; DWORD id; int vendor; wchar_t name[64]; int type, multi; } DEF6;
static DEF6 defs[16];
int w6_calls = 0, w6_fail_at = 0;           // Schreibaufruf Nr. w6_fail_at scheitert (20000)
DWORD last_cfg_field = 0, cfg_calls = 0;
static int inited = 0;

static A6 A(U64 hi, U64 lo) { A6 a = {hi, lo}; return a; }
#define P1 0x20010db800010000ULL
#define P2 0x20010db800020000ULL
static void init(void) {
    if (inited) return;
    inited = 1;
    sc[0].used = 1; sc[0].s.Addr = A(P1, 0); sc[0].s.Prefix = 64; sc[0].s.Name = W(L"Büro v6"); sc[0].s.Comment = W(L"EG");
    sc[0].cfg.Pref = 8 * 86400; sc[0].cfg.Valid = 12 * 86400; sc[0].cfg.T1 = 4 * 86400; sc[0].cfg.T2 = 6 * 86400; sc[0].cfg.Rapid = 1;
    sc[0].nex = 1; sc[0].ex[0].Start = A(P1, 0x10); sc[0].ex[0].End = A(P1, 0x20);
    sc[0].nres = 1; sc[0].rip[0] = A(P1, 0x50); BYTE d[14] = {0, 1, 0, 1, 0x2c, 0x4f, 0x11, 0x22, 0, 0x15, 0x5d, 1, 2, 3};
    memcpy(sc[0].rduid[0], d, 14); sc[0].rdl[0] = 14; sc[0].riaid[0] = 0x0e00155d;
    sc[0].ncl = 2;
    for (int i = 0; i < 2; i++) {
        CL6* c = &sc[0].cl[i]; c->Ip = i ? A(P1, 0x1234) : A(P1, 0x50); c->Duid.DataLength = 14; c->Duid.Data = M(14);
        memcpy(c->Duid.Data, d, 14); c->Duid.Data[13] = (BYTE)(3 + i); c->Iaid = 0x0e00155d + i; c->Name = W(i ? L"pc02.firma.local" : L"drucker");
        c->Comment = W(i ? L"" : L"Reserviert"); c->Valid.hi = 0x7FFFFFFF; c->Valid.lo = 0xFFFFFFFF; c->Type = 0;
    }
    sc[1].used = 1; sc[1].s.Addr = A(P2, 0); sc[1].s.Prefix = 64; sc[1].s.Name = W(L"Lager v6"); sc[1].s.Comment = W(L""); sc[1].s.State = 1;
    sc[1].cfg.Pref = 8 * 86400; sc[1].cfg.Valid = 12 * 86400;
    ov[0].used = 1; ov[0].scope_kind = 3; ov[0].id = 23; ov[0].type = 8; ov[0].n = 1; wcscpy(ov[0].s[0], L"2001:db8::53");
    ov[1].used = 1; ov[1].scope_kind = 1; ov[1].sid = A(P1, 0); ov[1].id = 24; ov[1].type = 5; ov[1].n = 1; wcscpy(ov[1].s[0], L"firma.local");
    ov[2].used = 1; ov[2].scope_kind = 1; ov[2].sid = A(P1, 0); ov[2].id = 0x20001; ov[2].type = 2; ov[2].n = 1; ov[2].dw[0] = 1;  // intern
    defs[0] = (DEF6){1, 23, 0, L"DNS Recursive Name Server IPV6 Address List", 8, 1};
    defs[1] = (DEF6){1, 24, 0, L"Domain Search List", 5, 1};
    defs[2] = (DEF6){1, 0x20002, 0, L"intern", 2, 0};
}
static SCOPE6* find(A6 a) { init(); for (int i = 0; i < MAXS; i++) if (sc[i].used && eq(sc[i].s.Addr, a)) return &sc[i]; return NULL; }
static int wr(void) { w6_calls++; return w6_fail_at && w6_calls == w6_fail_at; }

// --- Scopes -------------------------------------------------------------------------------------------
DWORD DhcpEnumSubnetsV6(LPWSTR s, DWORD* resume, DWORD pref, A6ARR** out, DWORD* r, DWORD* t) {
    init();
    if (*resume) return 259;
    A6ARR* a = M(sizeof *a); a->e = M(sizeof(A6) * MAXS);
    for (int i = 0; i < MAXS; i++) if (sc[i].used) a->e[a->n++] = sc[i].s.Addr;
    *resume = 1; *out = a; *r = *t = a->n; return a->n ? 0 : 259;
}
DWORD DhcpGetSubnetInfoV6(LPWSTR s, A6 sid, SUB6** out) {
    SCOPE6* x = find(sid); if (!x) return 20005;
    SUB6* o = M(sizeof *o); *o = x->s; o->Name = W(x->s.Name); o->Comment = W(x->s.Comment); *out = o; return 0;
}
DWORD DhcpSetSubnetInfoV6(LPWSTR s, A6 sid, SUB6* i) {
    SCOPE6* x = find(sid); if (!x) return 20005; if (wr()) return 20000;
    x->s.Pref = i->Pref; x->s.Name = W(i->Name); x->s.Comment = W(i->Comment); x->s.State = i->State; return 0;
}
DWORD DhcpCreateSubnetV6(LPWSTR s, A6 sid, SUB6* i) {
    if (find(sid)) return 20006; if (wr()) return 20000;
    for (int k = 0; k < MAXS; k++) if (!sc[k].used) {
        memset(&sc[k], 0, sizeof sc[k]); sc[k].used = 1; sc[k].s = *i; sc[k].s.Name = W(i->Name); sc[k].s.Comment = W(i->Comment);
        sc[k].cfg.Pref = 8 * 86400; sc[k].cfg.Valid = 12 * 86400; return 0;
    }
    return 8;
}
DWORD DhcpDeleteSubnetV6(LPWSTR s, A6 sid, int force) {
    SCOPE6* x = find(sid); if (!x) return 20005; if (wr()) return 20000;
    x->used = 0;
    for (int i = 0; i < 64; i++) if (ov[i].used && ov[i].scope_kind == 1 && eq(ov[i].sid, sid)) ov[i].used = 0;
    return 0;
}
DWORD DhcpServerGetConfigV6(LPWSTR s, SI6* si, CFG6** out) {
    init();
    CFG6* c = M(sizeof *c);
    if (si->Type == 1) { SCOPE6* x = find(si->u.subnet); if (!x) return 20005; *c = x->cfg; }
    else { c->Pref = 8 * 86400; c->Valid = 12 * 86400; c->Audit = 1; }
    *out = c; return 0;
}
// MS-DHCPM: je Aufruf ein Feld; bevorzugt < gültig wird bei jedem Schritt geprüft, T1/T2 folgen der bevorzugten Dauer
DWORD DhcpServerSetConfigV6(LPWSTR s, SI6* si, DWORD field, CFG6* c) {
    if (si->Type != 1) return 87;
    SCOPE6* x = find(si->u.subnet); if (!x) return 20005;
    cfg_calls++; last_cfg_field = field;
    if (field & (field - 1)) return 87;
    if (wr()) return 20000;
    if (field == 1) x->cfg.Unicast = c->Unicast;
    else if (field == 2) x->cfg.Rapid = c->Rapid;
    else if (field == 4) { if (c->Pref >= x->cfg.Valid) return 87; x->cfg.Pref = c->Pref; x->cfg.T1 = c->Pref / 2; x->cfg.T2 = c->Pref / 5 * 4; }
    else if (field == 8) { if (x->cfg.Pref >= c->Valid) return 87; x->cfg.Valid = c->Valid; }
    else return 87;
    return 0;
}

// --- Elemente -----------------------------------------------------------------------------------------
DWORD DhcpEnumSubnetElementsV6(LPWSTR s, A6 sid, int type, DWORD* resume, DWORD pref, EL6ARR** out, DWORD* r, DWORD* t) {
    SCOPE6* x = find(sid); if (!x) return 20005;
    if (*resume) return 259;
    EL6ARR* a = M(sizeof *a); a->e = M(sizeof(EL6) * MAXE);
    if (type == 2) for (int i = 0; i < x->nex; i++) { RNG6* g = M(sizeof *g); *g = x->ex[i]; a->e[a->n].Type = 2; a->e[a->n++].u.Excl = g; }
    if (type == 1) for (int i = 0; i < x->nres; i++) {
        RES6* g = M(sizeof *g); g->Ip = x->rip[i]; g->Iaid = x->riaid[i]; g->Duid = M(sizeof(BIN)); g->Duid->DataLength = x->rdl[i];
        g->Duid->Data = M(32); memcpy(g->Duid->Data, x->rduid[i], x->rdl[i]); a->e[a->n].Type = 1; a->e[a->n++].u.Res = g;
    }
    *resume = 1; *out = a; *r = *t = a->n; return a->n ? 0 : 259;
}
DWORD DhcpAddSubnetElementV6(LPWSTR s, A6 sid, EL6* e) {
    SCOPE6* x = find(sid); if (!x) return 20005; if (wr()) return 20000;
    if (e->Type == 2) {
        for (int i = 0; i < x->nex; i++) if (eq(x->ex[i].Start, e->u.Excl->Start) && eq(x->ex[i].End, e->u.Excl->End)) return 20022;
        if (!le(e->u.Excl->Start, e->u.Excl->End)) return 87;
        x->ex[x->nex++] = *e->u.Excl; return 0;
    }
    if (e->Type == 1) {
        for (int i = 0; i < x->nres; i++) if (eq(x->rip[i], e->u.Res->Ip)) return 20022;
        int k = x->nres++; x->rip[k] = e->u.Res->Ip; x->riaid[k] = e->u.Res->Iaid; x->rdl[k] = e->u.Res->Duid->DataLength;
        memcpy(x->rduid[k], e->u.Res->Duid->Data, x->rdl[k] > 32 ? 32 : x->rdl[k]); return 0;
    }
    return 87;
}
DWORD DhcpRemoveSubnetElementV6(LPWSTR s, A6 sid, EL6* e, int force) {
    SCOPE6* x = find(sid); if (!x) return 20005; if (wr()) return 20000;
    if (e->Type == 2) for (int i = 0; i < x->nex; i++)
        if (eq(x->ex[i].Start, e->u.Excl->Start) && eq(x->ex[i].End, e->u.Excl->End)) { x->ex[i] = x->ex[--x->nex]; return 0; }
    if (e->Type == 1) for (int i = 0; i < x->nres; i++)
        if (eq(x->rip[i], e->u.Res->Ip)) {
            if (x->riaid[i] != e->u.Res->Iaid || x->rdl[i] != e->u.Res->Duid->DataLength) return 20007;
            int k = --x->nres; x->rip[i] = x->rip[k]; x->riaid[i] = x->riaid[k]; x->rdl[i] = x->rdl[k];
            memcpy(x->rduid[i], x->rduid[k], 32); return 0;
        }
    return 20007;
}

// --- Clients ------------------------------------------------------------------------------------------
DWORD DhcpEnumSubnetClientsV6(LPWSTR s, A6 sid, A6* resume, DWORD pref, CL6ARR** out, DWORD* r, DWORD* t) {
    SCOPE6* x = find(sid); if (!x) return 20005;
    if (resume->hi || resume->lo || !x->ncl) return 259;
    CL6ARR* a = M(sizeof *a); a->c = M(sizeof(CL6*) * MAXE);
    for (int i = 0; i < x->ncl; i++) { CL6* c = M(sizeof *c); *c = x->cl[i]; c->Name = W(x->cl[i].Name); c->Comment = W(x->cl[i].Comment); a->c[a->n++] = c; }
    resume->lo = 1; *out = a; *r = *t = a->n; return 0;
}
static CL6* client(A6 ip) {
    init();
    for (int k = 0; k < MAXS; k++) if (sc[k].used) for (int i = 0; i < sc[k].ncl; i++) if (eq(sc[k].cl[i].Ip, ip)) return &sc[k].cl[i];
    return NULL;
}
DWORD DhcpGetClientInfoV6(LPWSTR s, SEARCH6* q, CL6** out) {
    CL6* c = client(q->u.ip); if (!c) return 20013;
    CL6* o = M(sizeof *o); *o = *c; o->Name = W(c->Name); o->Comment = W(c->Comment); *out = o; return 0;
}
DWORD DhcpSetClientInfoV6(LPWSTR s, CL6* n) {
    CL6* c = client(n->Ip); if (!c) return 20013; if (wr()) return 20000;
    c->Name = W(n->Name); c->Comment = W(n->Comment); return 0;
}
DWORD DhcpDeleteClientInfoV6(LPWSTR s, SEARCH6* q) {
    init(); if (wr()) return 20000;
    for (int k = 0; k < MAXS; k++) if (sc[k].used) for (int i = 0; i < sc[k].ncl; i++)
        if (eq(sc[k].cl[i].Ip, q->u.ip)) { sc[k].cl[i] = sc[k].cl[--sc[k].ncl]; return 0; }
    return 20013;
}

// --- Optionen -----------------------------------------------------------------------------------------
static void opt6(OPT* o, DEF6* d) {
    o->Id = d->id; o->Name = W(d->name); o->Comment = W(L""); o->OptionType = d->multi; o->Def.n = 1; o->Def.e = M(sizeof(OEL));
    o->Def.e[0].Type = d->type; if (d->type == 5 || d->type == 8) o->Def.e[0].u.s = W(L"");
}
DWORD DhcpGetAllOptionsV6(LPWSTR s, DWORD f, ALLOPT** out) {
    init();
    ALLOPT* a = M(sizeof *a); a->NonVendor = M(sizeof(OPTARR)); a->NonVendor->o = M(sizeof(OPT) * 16);
    for (int i = 0; i < 16; i++) if (defs[i].used && !defs[i].vendor) opt6(&a->NonVendor->o[a->NonVendor->n++], &defs[i]);
    *out = a; return 0;
}
static DEF6* def6(DWORD id) { init(); for (int i = 0; i < 16; i++) if (defs[i].used && defs[i].id == id) return &defs[i]; return NULL; }
DWORD DhcpCreateOptionV6(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, OPT* o) {
    if (def6(id)) return 20009; if (wr()) return 20000;
    for (int i = 0; i < 16; i++) if (!defs[i].used) {
        defs[i].used = 1; defs[i].id = id; wcsncpy(defs[i].name, o->Name ? o->Name : L"", 63); defs[i].type = o->Def.n ? o->Def.e[0].Type : 5;
        defs[i].multi = o->OptionType; return 0;
    }
    return 8;
}
DWORD DhcpSetOptionInfoV6(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, OPT* o) {
    DEF6* d = def6(id); if (!d) return 20010; if (wr()) return 20000; wcsncpy(d->name, o->Name ? o->Name : L"", 63); return 0;
}
DWORD DhcpRemoveOptionV6(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v) {
    DEF6* d = def6(id); if (!d) return 20010; if (wr()) return 20000; d->used = 0; return 0;
}
static int same_scope(OV6* o, SI6* si) {
    if (si->Type == 1) return o->scope_kind == 1 && eq(o->sid, si->u.subnet);
    return o->scope_kind == 3 || o->scope_kind == 0;
}
DWORD DhcpGetAllOptionValuesV6(LPWSTR s, DWORD f, SI6* si, AOV** out) {
    init();
    if (si->Type == 1 && !find(si->u.subnet)) return 20005;
    AOV* a = M(sizeof *a); a->n = 1; a->o = M(sizeof(AOVI)); OVARR* arr = M(sizeof *arr); a->o[0].Arr = arr; arr->v = M(sizeof(OVAL) * 64);
    for (int i = 0; i < 64; i++) if (ov[i].used && same_scope(&ov[i], si)) {
        OVAL* v = &arr->v[arr->n++]; v->Id = ov[i].id; v->Value.n = ov[i].n; v->Value.e = M(sizeof(OEL) * 4);
        for (int k = 0; k < ov[i].n; k++) {
            v->Value.e[k].Type = ov[i].type;
            if (ov[i].type == 5 || ov[i].type == 8) v->Value.e[k].u.s = W(ov[i].s[k]); else v->Value.e[k].u.dw = ov[i].dw[k];
        }
    }
    *out = a; return 0;
}
static OV6* findov(DWORD id, SI6* si) { for (int i = 0; i < 64; i++) if (ov[i].used && ov[i].id == id && same_scope(&ov[i], si)) return &ov[i]; return NULL; }
DWORD DhcpSetOptionValueV6(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, SI6* si, ODATA* d) {
    init();
    if (si->Type == 1 && !find(si->u.subnet)) return 20005;
    if (!def6(id)) return 20010;
    if (wr()) return 20000;
    OV6* o = findov(id, si);
    if (!o) for (int i = 0; i < 64 && !o; i++) if (!ov[i].used) o = &ov[i];
    memset(o, 0, sizeof *o); o->used = 1; o->id = id; o->scope_kind = si->Type == 1 ? 1 : 3; if (si->Type == 1) o->sid = si->u.subnet;
    o->n = d->n > 4 ? 4 : d->n; o->type = d->n ? d->e[0].Type : 5;
    for (int k = 0; k < o->n; k++) { if (o->type == 5 || o->type == 8) wcsncpy(o->s[k], d->e[k].u.s, 63); else o->dw[k] = d->e[k].u.dw; }
    return 0;
}
DWORD DhcpRemoveOptionValueV6(LPWSTR s, DWORD f, DWORD id, LPWSTR c, LPWSTR v, SI6* si) {
    init(); OV6* o = findov(id, si); if (!o) return 20010; if (wr()) return 20000; o->used = 0; return 0;
}
DWORD DhcpEnumClassesV6(LPWSTR s, DWORD r0, DWORD* resume, DWORD pref, void** out, DWORD* r, DWORD* t) { return 259; }

// --- Server -------------------------------------------------------------------------------------------
DWORD DhcpGetMibInfoV6(LPWSTR s, MIB6** out) {
    init();
    MIB6* m = M(sizeof *m); m->Info = M(sizeof(SMIB6) * MAXS);
    for (int i = 0; i < MAXS; i++) if (sc[i].used) {
        SMIB6* x = &m->Info[m->Scopes++]; x->Subnet = sc[i].s.Addr; x->InUse = sc[i].ncl; x->Free = 0xFFFFFFFFFFFFULL; x->Pend = i == 0;
    }
    *out = m; return 0;
}
DWORD DhcpV6GetStatelessStoreParams(LPWSTR s, BOOL server, A6 sid, STATELESS** out) {
    STATELESS* p = M(sizeof *p); p->Status = 1; p->Purge = 0; *out = p; return 0;
}
DWORD DhcpGetServerBindingInfoV6(LPWSTR s, DWORD f, BIND6ARR** out) {
    BIND6ARR* a = M(sizeof *a); a->n = 1; a->e = M(sizeof(BIND6)); a->e[0].Bound = 1; a->e[0].Prim = A(P1, 1); a->e[0].Desc = W(L"Ethernet0");
    *out = a; return 0;
}
