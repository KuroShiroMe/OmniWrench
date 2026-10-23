"""Direkter Zugriff auf Microsoft-DHCP-Server über die DHCP Server Management API (dhcpsapi.dll, RPC).

Das ist derselbe Weg, den die DHCP-Konsole nutzt: kein PowerShell, kein WinRM. Die Funktionen liefern die
Daten in derselben Form wie die DhcpServer-Cmdlets (Feldnamen wie ScopeId, StartRange, LeaseDuration in
Sekunden …), damit service.py unverändert normalisieren kann (siehe CMDLETS am Ende).

Abweichende Anmeldedaten gelten wie bei "runas /netonly" nur für den Netzwerkzugriff: LogonUser mit
LOGON32_LOGON_NEW_CREDENTIALS, die Identität wird pro Aufruf im aufrufenden Thread angenommen. Damit sind
parallele Aufrufe aus mehreren Threads möglich (ctypes gibt das GIL während des RPC-Aufrufs frei).

IP-Adressen sind in der API DWORDs in Host-Reihenfolge (10.0.0.1 = 0x0A000001).
"""

from __future__ import annotations

import ctypes
import datetime as _dt
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import POINTER, Structure, Union, byref, c_int, c_ubyte, c_uint16, c_uint32, c_void_p, c_wchar_p

DWORD = c_uint32
ULONG = c_uint32
BOOL = c_int
BYTE = c_ubyte
WORD = c_uint16
LPWSTR = c_wchar_p

ERROR_MORE_DATA = 234
ERROR_NO_MORE_ITEMS = 259
ERROR_DHCP_SUBNET_NOT_PRESENT = 20005
ERROR_DHCP_JET_ERROR = 20013
MAX_PREF = 0xFFFFFFFF
FLAG_VENDOR = 0x03                     # DHCP_FLAGS_OPTION_IS_VENDOR
UNLIMITED = 4294967295

# DHCP_SUBNET_ELEMENT_TYPE
EL_RANGES, EL_RESERVED, EL_EXCLUDED, EL_RANGES_DHCP_ONLY = 0, 2, 3, 5
# DHCP_OPTION_SCOPE_TYPE
SCOPE_DEFAULT, SCOPE_GLOBAL, SCOPE_SUBNET = 0, 1, 2
# DHCP_FORCE_FLAG
FULL_FORCE, NO_FORCE = 0, 1
OPTION_TYPES = ["Byte", "Word", "DWord", "DWordDword", "IPv4Address", "String", "BinaryData", "EncapsulatedData",
                "IPv6Address"]
CLIENT_TYPES = {1: "Dhcp", 2: "Bootp", 3: "Both"}
FO_STATES = ["NoState", "Init", "Startup", "Normal", "CommunicationInterrupted", "PartnerDown", "PotentialConflict",
             "ConflictDone", "ResolutionInterrupted", "Recover", "RecoverWait", "RecoverDone", "Paused", "Shutdown"]
# Option 81 (DNS-Einstellungen) als Bitmaske
DNS_ENABLED, DNS_DOWNLEVEL, DNS_CLEANUP, DNS_BOTH_ALWAYS, DNS_DHCID, DNS_NO_PTR = 0x01, 0x02, 0x04, 0x10, 0x20, 0x40
DNS_DEFAULT = DNS_ENABLED | DNS_CLEANUP


# --- Strukturen (dhcpsapi.h) -----------------------------------------------------------------------

class DATE_TIME(Structure):
    _fields_ = [("dwLowDateTime", DWORD), ("dwHighDateTime", DWORD)]


class DHCP_BINARY_DATA(Structure):
    _fields_ = [("DataLength", DWORD), ("Data", POINTER(BYTE))]


class DHCP_HOST_INFO(Structure):
    _fields_ = [("IpAddress", DWORD), ("NetBiosName", LPWSTR), ("HostName", LPWSTR)]


class DHCP_IP_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DWORD))]


class DHCP_SUBNET_INFO(Structure):
    _fields_ = [("SubnetAddress", DWORD), ("SubnetMask", DWORD), ("SubnetName", LPWSTR), ("SubnetComment", LPWSTR),
                ("PrimaryHost", DHCP_HOST_INFO), ("SubnetState", c_int)]


class DHCP_IP_RANGE(Structure):
    _fields_ = [("StartAddress", DWORD), ("EndAddress", DWORD)]


class DHCP_BOOTP_IP_RANGE(Structure):
    _fields_ = [("StartAddress", DWORD), ("EndAddress", DWORD), ("BootpAllocated", ULONG), ("MaxBootpAllowed", ULONG)]


class DHCP_IP_RESERVATION_V4(Structure):
    _fields_ = [("ReservedIpAddress", DWORD), ("ReservedForClient", POINTER(DHCP_BINARY_DATA)),
                ("bAllowedClientTypes", BYTE)]


class DHCP_IP_CLUSTER(Structure):
    _fields_ = [("ClusterAddress", DWORD), ("ClusterMask", DWORD)]


class _ElementUnion(Union):
    _fields_ = [("IpRange", POINTER(DHCP_BOOTP_IP_RANGE)), ("SecondaryHost", POINTER(DHCP_HOST_INFO)),
                ("ReservedIp", POINTER(DHCP_IP_RESERVATION_V4)), ("ExcludeIpRange", POINTER(DHCP_IP_RANGE)),
                ("IpUsedCluster", POINTER(DHCP_IP_CLUSTER))]


class DHCP_SUBNET_ELEMENT_DATA_V5(Structure):
    _fields_ = [("ElementType", c_int), ("Element", _ElementUnion)]


class DHCP_SUBNET_ELEMENT_INFO_ARRAY_V5(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DHCP_SUBNET_ELEMENT_DATA_V5))]


class DHCP_CLIENT_INFO_V4(Structure):
    _fields_ = [("ClientIpAddress", DWORD), ("SubnetMask", DWORD), ("ClientHardwareAddress", DHCP_BINARY_DATA),
                ("ClientName", LPWSTR), ("ClientComment", LPWSTR), ("ClientLeaseExpires", DATE_TIME),
                ("OwnerHost", DHCP_HOST_INFO), ("bClientType", BYTE)]


class DHCP_CLIENT_INFO_V5(Structure):
    _fields_ = [("ClientIpAddress", DWORD), ("SubnetMask", DWORD), ("ClientHardwareAddress", DHCP_BINARY_DATA),
                ("ClientName", LPWSTR), ("ClientComment", LPWSTR), ("ClientLeaseExpires", DATE_TIME),
                ("OwnerHost", DHCP_HOST_INFO), ("bClientType", BYTE), ("AddressState", BYTE)]


class DHCP_CLIENT_INFO_ARRAY_V5(Structure):
    _fields_ = [("NumElements", DWORD), ("Clients", POINTER(POINTER(DHCP_CLIENT_INFO_V5)))]


class _SearchUnion(Union):
    _fields_ = [("ClientIpAddress", DWORD), ("ClientHardwareAddress", DHCP_BINARY_DATA), ("ClientName", LPWSTR)]


class DHCP_SEARCH_INFO(Structure):
    _fields_ = [("SearchType", c_int), ("SearchInfo", _SearchUnion)]


class DWORD_DWORD(Structure):
    _fields_ = [("DWord1", DWORD), ("DWord2", DWORD)]


class _OptionUnion(Union):
    _fields_ = [("ByteOption", BYTE), ("WordOption", WORD), ("DWordOption", DWORD), ("DWordDWordOption", DWORD_DWORD),
                ("IpAddressOption", DWORD), ("StringDataOption", LPWSTR), ("BinaryDataOption", DHCP_BINARY_DATA),
                ("EncapsulatedDataOption", DHCP_BINARY_DATA), ("Ipv6AddressDataOption", LPWSTR)]


class DHCP_OPTION_DATA_ELEMENT(Structure):
    _fields_ = [("OptionType", c_int), ("Element", _OptionUnion)]


class DHCP_OPTION_DATA(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DHCP_OPTION_DATA_ELEMENT))]


class DHCP_OPTION(Structure):
    _fields_ = [("OptionID", DWORD), ("OptionName", LPWSTR), ("OptionComment", LPWSTR),
                ("DefaultValue", DHCP_OPTION_DATA), ("OptionType", c_int)]


class DHCP_OPTION_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Options", POINTER(DHCP_OPTION))]


class DHCP_VENDOR_OPTION(Structure):
    _fields_ = [("Option", DHCP_OPTION), ("VendorName", LPWSTR), ("ClassName", LPWSTR)]


class DHCP_ALL_OPTIONS(Structure):
    _fields_ = [("Flags", DWORD), ("NonVendorOptions", POINTER(DHCP_OPTION_ARRAY)), ("NumVendorOptions", DWORD),
                ("VendorOptions", POINTER(DHCP_VENDOR_OPTION))]


class DHCP_OPTION_VALUE(Structure):
    _fields_ = [("OptionID", DWORD), ("Value", DHCP_OPTION_DATA)]


class DHCP_OPTION_VALUE_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Values", POINTER(DHCP_OPTION_VALUE))]


class DHCP_ALL_OPTION_VALUES_ITEM(Structure):
    _fields_ = [("ClassName", LPWSTR), ("VendorName", LPWSTR), ("IsVendor", BOOL),
                ("OptionsArray", POINTER(DHCP_OPTION_VALUE_ARRAY))]


class DHCP_ALL_OPTION_VALUES(Structure):
    _fields_ = [("Flags", DWORD), ("NumElements", DWORD), ("Options", POINTER(DHCP_ALL_OPTION_VALUES_ITEM))]


class DHCP_RESERVED_SCOPE(Structure):
    _fields_ = [("ReservedIpAddress", DWORD), ("ReservedIpSubnetAddress", DWORD)]


class _ScopeUnion(Union):
    _fields_ = [("DefaultScopeInfo", c_void_p), ("SubnetScopeInfo", DWORD), ("ReservedScopeInfo", DHCP_RESERVED_SCOPE),
                ("MScopeInfo", LPWSTR)]


class DHCP_OPTION_SCOPE_INFO(Structure):
    _fields_ = [("ScopeType", c_int), ("ScopeInfo", _ScopeUnion)]


class DHCP_CLASS_INFO(Structure):
    _fields_ = [("ClassName", LPWSTR), ("ClassComment", LPWSTR), ("ClassDataLength", DWORD), ("IsVendor", BOOL),
                ("Flags", DWORD), ("ClassData", POINTER(BYTE))]


class DHCP_CLASS_INFO_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Classes", POINTER(DHCP_CLASS_INFO))]


class SCOPE_MIB_INFO(Structure):
    _fields_ = [("Subnet", DWORD), ("NumAddressesInuse", DWORD), ("NumAddressesFree", DWORD),
                ("NumPendingOffers", DWORD)]


class DHCP_MIB_INFO(Structure):
    _fields_ = [("Discovers", DWORD), ("Offers", DWORD), ("Requests", DWORD), ("Acks", DWORD), ("Naks", DWORD),
                ("Declines", DWORD), ("Releases", DWORD), ("ServerStartTime", DATE_TIME), ("Scopes", DWORD),
                ("ScopeInfo", POINTER(SCOPE_MIB_INFO))]


class DHCP_SUPER_SCOPE_TABLE_ENTRY(Structure):
    _fields_ = [("SubnetAddress", DWORD), ("SuperScopeNumber", DWORD), ("NextInSuperScope", DWORD),
                ("SuperScopeName", LPWSTR)]


class DHCP_SUPER_SCOPE_TABLE(Structure):
    _fields_ = [("cEntries", DWORD), ("pEntries", POINTER(DHCP_SUPER_SCOPE_TABLE_ENTRY))]


class DHCP_SERVER_CONFIG_INFO_V4(Structure):
    _fields_ = [("APIProtocolSupport", DWORD), ("DatabaseName", LPWSTR), ("DatabasePath", LPWSTR),
                ("BackupPath", LPWSTR), ("BackupInterval", DWORD), ("DatabaseLoggingFlag", DWORD),
                ("RestoreFlag", DWORD), ("DatabaseCleanupInterval", DWORD), ("DebugFlag", DWORD),
                ("dwPingRetries", DWORD), ("cbBootTableString", DWORD), ("wszBootTableString", LPWSTR),
                ("fAuditLog", BOOL)]


class DHCP_ATTRIB(Structure):
    _fields_ = [("DhcpAttribId", ULONG), ("DhcpAttribType", ULONG), ("Value", ULONG)]


class DHCP_BIND_ELEMENT(Structure):
    _fields_ = [("Flags", ULONG), ("fBoundToDHCPServer", BOOL), ("AdapterPrimaryAddress", DWORD),
                ("AdapterSubnetAddress", DWORD), ("IfDescription", LPWSTR), ("IfIdSize", ULONG), ("IfId", POINTER(BYTE))]


class DHCP_BIND_ELEMENT_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DHCP_BIND_ELEMENT))]


class DHCP_POLICY(Structure):
    _fields_ = [("PolicyName", LPWSTR), ("IsGlobalPolicy", BOOL), ("Subnet", DWORD), ("ProcessingOrder", DWORD),
                ("Conditions", c_void_p), ("Expressions", c_void_p), ("Ranges", c_void_p), ("Description", LPWSTR),
                ("Enabled", BOOL)]


class DHCP_POLICY_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("Elements", POINTER(DHCP_POLICY))]


class DHCP_FILTER_GLOBAL_INFO(Structure):
    _fields_ = [("EnforceAllowList", BOOL), ("EnforceDenyList", BOOL)]


class DHCP_ADDR_PATTERN(Structure):
    _fields_ = [("MatchHWType", BOOL), ("HWType", BYTE), ("IsWildcard", BOOL), ("Length", BYTE),
                ("Pattern", BYTE * 255)]


class DHCP_FILTER_RECORD(Structure):
    _fields_ = [("AddrPatt", DHCP_ADDR_PATTERN), ("Comment", LPWSTR)]


class DHCP_FILTER_ENUM_INFO(Structure):
    _fields_ = [("NumElements", DWORD), ("pEnumRecords", POINTER(DHCP_FILTER_RECORD))]


class DHCP_FAILOVER_RELATIONSHIP(Structure):
    _fields_ = [("PrimaryServer", DWORD), ("SecondaryServer", DWORD), ("Mode", c_int), ("ServerType", c_int),
                ("State", c_int), ("PrevState", c_int), ("Mclt", DWORD), ("SafePeriod", DWORD),
                ("RelationshipName", LPWSTR), ("PrimaryServerName", LPWSTR), ("SecondaryServerName", LPWSTR),
                ("pScopes", POINTER(DHCP_IP_ARRAY)), ("Percentage", BYTE), ("SharedSecret", LPWSTR)]


class DHCP_FAILOVER_RELATIONSHIP_ARRAY(Structure):
    _fields_ = [("NumElements", DWORD), ("pRelationships", POINTER(DHCP_FAILOVER_RELATIONSHIP))]


class DHCPDS_SERVER(Structure):
    _fields_ = [("Version", DWORD), ("ServerName", LPWSTR), ("ServerAddress", DWORD), ("Flags", DWORD),
                ("State", DWORD), ("DsLocation", LPWSTR), ("DsLocType", DWORD)]


class DHCPDS_SERVERS(Structure):
    _fields_ = [("Flags", DWORD), ("NumElements", DWORD), ("Servers", POINTER(DHCPDS_SERVER))]


# --- Funktionen ------------------------------------------------------------------------------------

def _p(t):
    return POINTER(t)


_PROTOS = {
    "DhcpGetVersion": (LPWSTR, _p(DWORD), _p(DWORD)),
    "DhcpEnumSubnets": (LPWSTR, _p(DWORD), DWORD, _p(_p(DHCP_IP_ARRAY)), _p(DWORD), _p(DWORD)),
    "DhcpGetSubnetInfo": (LPWSTR, DWORD, _p(_p(DHCP_SUBNET_INFO))),
    "DhcpSetSubnetInfo": (LPWSTR, DWORD, _p(DHCP_SUBNET_INFO)),
    "DhcpCreateSubnet": (LPWSTR, DWORD, _p(DHCP_SUBNET_INFO)),
    "DhcpDeleteSubnet": (LPWSTR, DWORD, c_int),
    "DhcpEnumSubnetElementsV5": (LPWSTR, DWORD, c_int, _p(DWORD), DWORD, _p(_p(DHCP_SUBNET_ELEMENT_INFO_ARRAY_V5)),
                                 _p(DWORD), _p(DWORD)),
    "DhcpAddSubnetElementV5": (LPWSTR, DWORD, _p(DHCP_SUBNET_ELEMENT_DATA_V5)),
    "DhcpRemoveSubnetElementV5": (LPWSTR, DWORD, _p(DHCP_SUBNET_ELEMENT_DATA_V5), c_int),
    "DhcpEnumSubnetClientsV5": (LPWSTR, DWORD, _p(DWORD), DWORD, _p(_p(DHCP_CLIENT_INFO_ARRAY_V5)), _p(DWORD),
                                _p(DWORD)),
    "DhcpGetClientInfoV4": (LPWSTR, _p(DHCP_SEARCH_INFO), _p(_p(DHCP_CLIENT_INFO_V4))),
    "DhcpSetClientInfoV4": (LPWSTR, _p(DHCP_CLIENT_INFO_V4)),
    "DhcpDeleteClientInfo": (LPWSTR, _p(DHCP_SEARCH_INFO)),
    "DhcpGetAllOptions": (LPWSTR, DWORD, _p(_p(DHCP_ALL_OPTIONS))),
    "DhcpGetOptionInfoV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(_p(DHCP_OPTION))),
    "DhcpCreateOptionV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(DHCP_OPTION)),
    "DhcpSetOptionInfoV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(DHCP_OPTION)),
    "DhcpRemoveOptionV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR),
    "DhcpGetAllOptionValues": (LPWSTR, DWORD, _p(DHCP_OPTION_SCOPE_INFO), _p(_p(DHCP_ALL_OPTION_VALUES))),
    "DhcpGetOptionValueV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(DHCP_OPTION_SCOPE_INFO),
                             _p(_p(DHCP_OPTION_VALUE))),
    "DhcpSetOptionValueV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(DHCP_OPTION_SCOPE_INFO), _p(DHCP_OPTION_DATA)),
    "DhcpRemoveOptionValueV5": (LPWSTR, DWORD, DWORD, LPWSTR, LPWSTR, _p(DHCP_OPTION_SCOPE_INFO)),
    "DhcpEnumClasses": (LPWSTR, DWORD, _p(DWORD), DWORD, _p(_p(DHCP_CLASS_INFO_ARRAY)), _p(DWORD), _p(DWORD)),
    "DhcpGetMibInfo": (LPWSTR, _p(_p(DHCP_MIB_INFO))),
    "DhcpGetSuperScopeInfoV4": (LPWSTR, _p(_p(DHCP_SUPER_SCOPE_TABLE))),
    "DhcpServerGetConfigV4": (LPWSTR, _p(_p(DHCP_SERVER_CONFIG_INFO_V4))),
    "DhcpServerSetConfigV4": (LPWSTR, DWORD, _p(DHCP_SERVER_CONFIG_INFO_V4)),
    "DhcpServerQueryAttribute": (LPWSTR, ULONG, ULONG, _p(_p(DHCP_ATTRIB))),
    "DhcpServerQueryDnsRegCredentials": (LPWSTR, ULONG, LPWSTR, ULONG, LPWSTR),
    "DhcpGetServerBindingInfo": (LPWSTR, ULONG, _p(_p(DHCP_BIND_ELEMENT_ARRAY))),
    "DhcpV4EnumPolicies": (LPWSTR, _p(DWORD), DWORD, BOOL, DWORD, _p(_p(DHCP_POLICY_ARRAY)), _p(DWORD), _p(DWORD)),
    "DhcpGetFilterV4": (LPWSTR, _p(DHCP_FILTER_GLOBAL_INFO)),
    "DhcpEnumFilterV4": (LPWSTR, _p(DHCP_ADDR_PATTERN), DWORD, c_int, _p(_p(DHCP_FILTER_ENUM_INFO)), _p(DWORD),
                         _p(DWORD)),
    "DhcpV4FailoverEnumRelationship": (LPWSTR, _p(DWORD), DWORD, _p(_p(DHCP_FAILOVER_RELATIONSHIP_ARRAY)), _p(DWORD),
                                       _p(DWORD)),
    "DhcpV4FailoverCreateRelationship": (LPWSTR, _p(DHCP_FAILOVER_RELATIONSHIP)),
    "DhcpV4FailoverSetRelationship": (LPWSTR, DWORD, _p(DHCP_FAILOVER_RELATIONSHIP)),
    "DhcpV4FailoverDeleteRelationship": (LPWSTR, LPWSTR),
    "DhcpV4FailoverAddScopeToRelationship": (LPWSTR, _p(DHCP_FAILOVER_RELATIONSHIP)),
    "DhcpV4FailoverDeleteScopeFromRelationship": (LPWSTR, _p(DHCP_FAILOVER_RELATIONSHIP)),
    "DhcpEnumServers": (DWORD, c_void_p, _p(_p(DHCPDS_SERVERS)), c_void_p, c_void_p),
}

_lib = None
_lib_lock = threading.Lock()


def available() -> bool:
    try:
        _dll()
        return True
    except OSError:
        return False


def _dll():
    global _lib
    with _lib_lock:
        if _lib is None:
            if os.name != "nt":
                raise OSError("dhcpsapi.dll gibt es nur unter Windows")
            _lib = setup(ctypes.WinDLL("dhcpsapi.dll"))
        return _lib


def setup(lib):
    """Signaturen setzen (auch für Testbibliotheken mit denselben Funktionen)."""
    for name, args in _PROTOS.items():
        try:
            f = getattr(lib, name)
        except AttributeError:
            continue
        f.argtypes = list(args)
        f.restype = DWORD
    lib.DhcpRpcFreeMemory.argtypes = [c_void_p]
    lib.DhcpRpcFreeMemory.restype = None
    return lib


def _free(ptr) -> None:
    if ptr:
        _dll().DhcpRpcFreeMemory(ctypes.cast(ptr, c_void_p))


def error_text(code: int) -> str:
    """Systemtext zu einem Fehlercode (DHCP-Codes 20000+ stehen in dhcpsapi.dll)."""
    if os.name != "nt":
        return f"Fehler {code}"
    k32 = ctypes.windll.kernel32
    buf = ctypes.create_unicode_buffer(1024)
    flags = 0x1000 | 0x200        # FROM_SYSTEM | IGNORE_INSERTS
    src = None
    if code >= 20000:
        try:
            src = _dll()._handle
            flags |= 0x800        # FROM_HMODULE
        except OSError:
            pass
    n = k32.FormatMessageW(flags, c_void_p(src) if src else None, code, 0, buf, len(buf), None)
    return buf.value[:n].strip() if n else f"Fehler {code}"


class RpcError(Exception):
    def __init__(self, op: str, server: str, code: int):
        self.op, self.server, self.code = op, server, int(code)
        super().__init__(f"@RPC:{op}:{server}:{self.code}:{error_text(self.code)}")


# --- Hilfen ----------------------------------------------------------------------------------------

def ip2n(ip: str) -> int:
    a, b, c, d = (int(x) for x in str(ip).strip().split("."))
    return (a << 24) | (b << 16) | (c << 8) | d


def n2ip(n: int) -> str:
    n = int(n) & 0xFFFFFFFF
    return f"{n >> 24 & 255}.{n >> 16 & 255}.{n >> 8 & 255}.{n & 255}"


def _bytes(bd: DHCP_BINARY_DATA) -> bytes:
    if not bd.Data or not bd.DataLength:
        return b""
    return bytes(bd.Data[:bd.DataLength])


def _hexid(data: bytes, subnet: int | None = None) -> str:
    """Client-ID wie die Cmdlets ("00-15-5d-01-02-03"). Reservierungen tragen teils Subnetz + Typ 1 davor."""
    if subnet is not None and len(data) > 6 and data[4:5] == b"\x01" and int.from_bytes(data[:4], "little") == subnet:
        data = data[5:]
    return "-".join(f"{b:02x}" for b in data)


def _cid_bytes(cid: str) -> bytes:
    h = "".join(ch for ch in str(cid) if ch.lower() in "0123456789abcdef")
    if not h or len(h) % 2:
        raise ValueError(cid)
    return bytes.fromhex(h)


def _filetime(dt: DATE_TIME) -> str:
    ft = (int(dt.dwHighDateTime) << 32) | int(dt.dwLowDateTime)
    if ft == 0 or dt.dwHighDateTime >= 0x7FFFFFFF:
        return ""
    try:
        t = _dt.datetime(1601, 1, 1, tzinfo=_dt.timezone.utc) + _dt.timedelta(microseconds=ft // 10)
        return t.astimezone().strftime("%Y-%m-%dT%H:%M:%S")
    except (OverflowError, ValueError, OSError):
        return ""


def _secs(v) -> int | None:
    if v is None:
        return None
    if isinstance(v, dict) and "__ts" in v:
        v = v["__ts"]
    return min(int(v), UNLIMITED)


def _list(v) -> list:
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else [v]


def _truthy(v) -> bool:
    return bool(v) and str(v).lower() not in ("false", "0")


def _scope_info(sid: str | None) -> DHCP_OPTION_SCOPE_INFO:
    si = DHCP_OPTION_SCOPE_INFO()
    if sid:
        si.ScopeType = SCOPE_SUBNET
        si.ScopeInfo.SubnetScopeInfo = ip2n(sid)
    else:
        si.ScopeType = SCOPE_GLOBAL
    return si


def _format_element(e: DHCP_OPTION_DATA_ELEMENT) -> tuple[str, str]:
    t = int(e.OptionType)
    u = e.Element
    if t == 0:
        v = str(u.ByteOption)
    elif t == 1:
        v = str(u.WordOption)
    elif t == 2:
        v = str(u.DWordOption)
    elif t == 3:
        v = str((int(u.DWordDWordOption.DWord1) << 32) | int(u.DWordDWordOption.DWord2))
    elif t == 4:
        v = n2ip(u.IpAddressOption)
    elif t == 5:
        v = u.StringDataOption or ""
    elif t in (6, 7):
        b = _bytes(u.BinaryDataOption if t == 6 else u.EncapsulatedDataOption)
        v = "0x" + b.hex().upper() if b else ""
    elif t == 8:
        v = u.Ipv6AddressDataOption or ""
    else:
        v = ""
    return (OPTION_TYPES[t] if 0 <= t < len(OPTION_TYPES) else "BinaryData"), v


def _format_data(d: DHCP_OPTION_DATA) -> tuple[str | None, list[str]]:
    vals, typ = [], None
    for i in range(int(d.NumElements or 0)):
        t, v = _format_element(d.Elements[i])
        typ = typ or t
        vals.append(v)
    return typ, vals


def _to_number(v) -> int:
    s = str(v).strip()
    return int(s, 16) if s.lower().startswith("0x") else int(s)


def _to_bin(v) -> bytes:
    s = str(v).strip()
    if s.lower().startswith("0x"):
        s = s[2:]
    s = "".join(ch for ch in s if ch not in " :-,")
    if len(s) % 2:
        s = "0" + s
    return bytes.fromhex(s)


def _build_data(type_name: str, values: list, keep: list) -> DHCP_OPTION_DATA:
    t = OPTION_TYPES.index(type_name) if type_name in OPTION_TYPES else 5
    vals = [v for v in _list(values)]
    arr = (DHCP_OPTION_DATA_ELEMENT * max(1, len(vals)))()
    keep.append(arr)
    for i, v in enumerate(vals):
        e = arr[i]
        e.OptionType = t
        if t == 0:
            e.Element.ByteOption = _to_number(v) & 0xFF
        elif t == 1:
            e.Element.WordOption = _to_number(v) & 0xFFFF
        elif t == 2:
            e.Element.DWordOption = _to_number(v) & 0xFFFFFFFF
        elif t == 3:
            n = _to_number(v)
            e.Element.DWordDWordOption.DWord1 = (n >> 32) & 0xFFFFFFFF
            e.Element.DWordDWordOption.DWord2 = n & 0xFFFFFFFF
        elif t == 4:
            e.Element.IpAddressOption = ip2n(v)
        elif t in (5, 8):
            buf = ctypes.create_unicode_buffer(str(v))
            keep.append(buf)
            ptr = ctypes.cast(buf, c_wchar_p)
            if t == 5:
                e.Element.StringDataOption = ptr
            else:
                e.Element.Ipv6AddressDataOption = ptr
        else:
            b = _to_bin(v)
            buf = (BYTE * max(1, len(b))).from_buffer_copy(b or b"\0")
            keep.append(buf)
            bd = e.Element.BinaryDataOption if t == 6 else e.Element.EncapsulatedDataOption
            bd.DataLength = len(b)
            bd.Data = ctypes.cast(buf, POINTER(BYTE))
    d = DHCP_OPTION_DATA()
    d.NumElements = len(vals)
    d.Elements = ctypes.cast(arr, POINTER(DHCP_OPTION_DATA_ELEMENT))
    return d


def _empty_value(type_name: str) -> str:
    return {"IPv4Address": "0.0.0.0", "String": "", "BinaryData": "", "EncapsulatedData": "",
            "IPv6Address": "::"}.get(type_name, "0")


# --- Anmeldung pro Thread (runas /netonly) ---------------------------------------------------------

class Identity:
    """Netzwerk-Anmeldedaten für RPC-Aufrufe. Ohne Benutzer gilt die aktuelle Windows-Anmeldung."""

    def __init__(self, user: str = "", password: str = ""):
        self.user, self.domain = _split_user(user)
        self._password = password or ""
        self._token = None
        self._lock = threading.Lock()

    @property
    def empty(self) -> bool:
        return not self.user

    def parts(self) -> tuple[str | None, str | None, str | None]:
        if not self.user:
            return None, None, None
        return self.user, self.domain, self._password

    def token(self):
        with self._lock:
            if self._token is None:
                adv = ctypes.WinDLL("advapi32", use_last_error=True)
                tok = ctypes.c_void_p()
                ok = adv.LogonUserW(c_wchar_p(self.user), c_wchar_p(self.domain), c_wchar_p(self._password),
                                    9, 3, byref(tok))    # LOGON32_LOGON_NEW_CREDENTIALS, LOGON32_PROVIDER_WINNT50
                if not ok:
                    err = ctypes.get_last_error()
                    raise RuntimeError(f"@RPC:logon::{err}:{ctypes.FormatError(err).strip()}")
                self._token = tok
            return self._token

    def close(self) -> None:
        with self._lock:
            if self._token:
                ctypes.windll.kernel32.CloseHandle(self._token)
                self._token = None


def _split_user(user: str) -> tuple[str, str | None]:
    u = (user or "").strip()
    if not u:
        return "", None
    if "\\" in u:
        d, n = u.split("\\", 1)
        return n, d or None
    if "@" in u:
        return u, None
    return u, os.environ.get("USERDOMAIN") or None


class _Impersonate:
    def __init__(self, ident: Identity | None):
        self.ident = ident if ident and not ident.empty else None

    def __enter__(self):
        if self.ident:
            adv = ctypes.WinDLL("advapi32", use_last_error=True)
            if not adv.ImpersonateLoggedOnUser(self.ident.token()):
                err = ctypes.get_last_error()
                raise RuntimeError(f"@RPC:logon::{err}:{ctypes.FormatError(err).strip()}")
        return self

    def __exit__(self, *exc):
        if self.ident:
            ctypes.WinDLL("advapi32").RevertToSelf()
        return False


# --- Zugriff auf einen Server ----------------------------------------------------------------------

class DhcpApi:
    """Alle Aufrufe gegen einen Server; liefert Daten in Cmdlet-Form."""

    def __init__(self, server: str, ident: Identity | None = None, threads: int = 8):
        self.server = server
        self.ident = ident
        self.threads = max(1, int(threads))
        self._defs = None
        self._defs_lock = threading.Lock()

    # --- Grundaufruf --------------------------------------------------------------------------------
    def rpc(self, op: str, name: str, *args, ok=(0,)) -> int:
        f = getattr(_dll(), name, None)
        if f is None:
            raise RuntimeError(f"@ERR:no_api:{name}")
        with _Impersonate(self.ident):
            rc = int(f(self.server, *args))
        if rc not in ok:
            raise RpcError(op, self.server, rc)
        return rc

    def parallel(self, fn, items):
        items = list(items)
        if len(items) <= 1 or self.threads <= 1:
            return [fn(x) for x in items]
        with ThreadPoolExecutor(max_workers=min(self.threads, len(items))) as ex:
            return list(ex.map(fn, items))

    # --- Server -------------------------------------------------------------------------------------
    def version(self) -> dict:
        ma, mi = DWORD(0), DWORD(0)
        self.rpc("connect", "DhcpGetVersion", byref(ma), byref(mi))
        return {"MajorVersion": int(ma.value), "MinorVersion": int(mi.value)}

    def access(self) -> str:
        """Schreibrecht prüfen, ohne etwas zu ändern: DhcpServerSetConfigV4 mit FieldsToSet = 0.
        Der Server prüft vor allem anderen die Berechtigung (DHCP-Administratoren bzw. lokale Administratoren);
        Mitglieder von „DHCP-Benutzer“ bekommen ERROR_ACCESS_DENIED (5). Ergebnis: admin | read | unknown."""
        f = getattr(_dll(), "DhcpServerSetConfigV4", None)
        if f is None:
            return "unknown"
        cfg = DHCP_SERVER_CONFIG_INFO_V4()
        with _Impersonate(self.ident):
            rc = int(f(self.server, 0, byref(cfg)))
        return "admin" if rc == 0 else "read" if rc == 5 else "unknown"

    def config(self) -> dict | None:
        p = POINTER(DHCP_SERVER_CONFIG_INFO_V4)()
        self.rpc("read", "DhcpServerGetConfigV4", byref(p))
        if not p:
            return None
        c = p.contents
        info = {"db": c.DatabaseName or "", "path": c.DatabasePath or "", "backup": c.BackupPath or "",
                "interval": int(c.BackupInterval), "logging": bool(c.DatabaseLoggingFlag),
                "ping": int(c.dwPingRetries), "audit": bool(c.fAuditLog)}
        _free(p)
        return info

    def attribute(self, attr: int) -> int | None:
        p = POINTER(DHCP_ATTRIB)()
        try:
            self.rpc("read", "DhcpServerQueryAttribute", 0, attr, byref(p))
        except RpcError:
            return None
        v = int(p.contents.Value) if p else None
        _free(p)
        return v

    def server_setting(self) -> list[dict]:
        cfg = self.config() or {}
        rogue, bootp, dsdc = self.attribute(0x01), self.attribute(0x02), self.attribute(0x03)
        return [{"IsDomainJoined": bool(dsdc), "IsAuthorized": rogue == 0 if rogue is not None else False,
                 "NapEnabled": False, "ConflictDetectionAttempts": cfg.get("ping", 0), "DynamicBootp": bool(bootp)}]

    def audit_log(self) -> list[dict]:
        return [{"Enable": bool((self.config() or {}).get("audit"))}]

    def database(self) -> list[dict]:
        c = self.config() or {}
        path = c.get("path", "")
        f = os.path.join(path, c.get("db", "")) if path else c.get("db", "")
        return [{"FileName": f.replace("/", "\\"), "BackupPath": c.get("backup", ""),
                 "BackupInterval": c.get("interval", 0), "LoggingEnabled": c.get("logging", False)}]

    def dns_credential(self) -> list[dict]:
        u, d = ctypes.create_unicode_buffer(1024), ctypes.create_unicode_buffer(1024)
        self.rpc("read", "DhcpServerQueryDnsRegCredentials", 1024, u, 1024, d)
        return [{"UserName": u.value, "DomainName": d.value}]

    def bindings(self) -> list[dict]:
        p = POINTER(DHCP_BIND_ELEMENT_ARRAY)()
        self.rpc("read", "DhcpGetServerBindingInfo", 0, byref(p))
        out = []
        if p:
            a = p.contents
            for i in range(a.NumElements):
                b = a.Elements[i]
                out.append({"BindingState": bool(b.fBoundToDHCPServer), "InterfaceAlias": b.IfDescription or "",
                            "IPAddress": n2ip(b.AdapterPrimaryAddress), "SubnetMask": n2ip(b.AdapterSubnetAddress)})
            _free(p)
        return out

    def policies(self) -> list[dict]:
        out = []

        def read(buf):
            a = buf.contents
            for i in range(a.NumElements):
                x = a.Elements[i]
                out.append({"Name": x.PolicyName or "", "Enabled": bool(x.Enabled), "Description": x.Description or ""})
        self._enum_resume("read", "DhcpV4EnumPolicies", (), (1, 0), read)     # fGlobalPolicy = TRUE
        return out

    def filter_list(self) -> list[dict]:
        g = DHCP_FILTER_GLOBAL_INFO()
        self.rpc("read", "DhcpGetFilterV4", byref(g))
        return [{"Allow": bool(g.EnforceAllowList), "Deny": bool(g.EnforceDenyList)}]

    def filters(self, list_name: str) -> list[dict]:
        kind = 1 if str(list_name).lower() == "allow" else 0
        resume = DHCP_ADDR_PATTERN()
        out = []
        for _ in range(1000):
            buf = POINTER(DHCP_FILTER_ENUM_INFO)()
            nread, total = DWORD(0), DWORD(0)
            rc = self.rpc("read", "DhcpEnumFilterV4", byref(resume), MAX_PREF, kind, byref(buf), byref(nread),
                          byref(total), ok=(0, ERROR_MORE_DATA, ERROR_NO_MORE_ITEMS))
            if rc == ERROR_NO_MORE_ITEMS:
                break
            if buf:
                a = buf.contents
                for i in range(a.NumElements):
                    r = a.pEnumRecords[i]
                    mac = bytes(r.AddrPatt.Pattern[:r.AddrPatt.Length])
                    out.append({"List": "Allow" if kind else "Deny", "MacAddress": "-".join(f"{b:02x}" for b in mac),
                                "Description": r.Comment or ""})
                _free(buf)
            if rc == 0:
                break
        return out

    # --- Scopes -------------------------------------------------------------------------------------
    def subnets(self) -> list[int]:
        out: list[int] = []

        def read(buf):
            a = buf.contents
            out.extend(int(a.Elements[i]) for i in range(a.NumElements))
        self._enum_resume("read", "DhcpEnumSubnets", (), (), read)
        return out

    def _enum_resume(self, op, name, before, after, read):
        """name(server, *before, &resume, PreferredMaximum, *after, &buf, &read, &total)."""
        f = getattr(_dll(), name, None)
        if f is None:
            raise RuntimeError(f"@ERR:no_api:{name}")
        buf_type = f.argtypes[len(before) + 3 + len(after)]._type_      # POINTER(Array-Struktur)
        resume = DWORD(0)
        for _ in range(100000):
            buf = buf_type()
            nread, total = DWORD(0), DWORD(0)
            with _Impersonate(self.ident):
                rc = int(f(self.server, *before, byref(resume), MAX_PREF, *after, byref(buf), byref(nread), byref(total)))
            if rc == ERROR_NO_MORE_ITEMS:
                break
            if rc not in (0, ERROR_MORE_DATA):
                raise RpcError(op, self.server, rc)
            if buf:
                try:
                    read(buf)
                finally:
                    _free(buf)
            if rc == 0:
                break

    def subnet_info(self, sid: int) -> dict | None:
        p = POINTER(DHCP_SUBNET_INFO)()
        try:
            self.rpc("read", "DhcpGetSubnetInfo", sid, byref(p))
        except RpcError as e:
            if e.code == ERROR_DHCP_SUBNET_NOT_PRESENT:
                return None
            raise
        if not p:
            return None
        s = p.contents
        out = {"mask": int(s.SubnetMask), "name": s.SubnetName or "", "comment": s.SubnetComment or "",
               "state": int(s.SubnetState)}
        _free(p)
        return out

    def elements(self, sid: int, kind: int) -> list[dict]:
        out: list[dict] = []

        def read(buf):
            a = buf.contents
            for i in range(a.NumElements):
                e = a.Elements[i]
                t = int(e.ElementType)
                if kind == EL_RESERVED:
                    r = e.Element.ReservedIp
                    if r:
                        r = r.contents
                        uid = _bytes(r.ReservedForClient.contents) if r.ReservedForClient else b""
                        out.append({"type": t, "ip": int(r.ReservedIpAddress), "uid": uid,
                                    "ctype": int(r.bAllowedClientTypes)})
                elif kind == EL_EXCLUDED:
                    r = e.Element.ExcludeIpRange
                    if r:
                        out.append({"type": t, "start": int(r.contents.StartAddress), "end": int(r.contents.EndAddress)})
                else:
                    r = e.Element.IpRange
                    if r:
                        out.append({"type": t, "start": int(r.contents.StartAddress), "end": int(r.contents.EndAddress)})
        try:
            self._enum_resume("read", "DhcpEnumSubnetElementsV5", (sid, kind), (), read)
        except RpcError as e:
            if e.code == ERROR_DHCP_SUBNET_NOT_PRESENT:
                return []
            raise
        return out

    def clients(self, sid: int) -> list[dict]:
        out: list[dict] = []

        def read(buf):
            a = buf.contents
            for i in range(a.NumElements):
                p = a.Clients[i]
                if not p:
                    continue
                c = p.contents
                out.append({"ip": int(c.ClientIpAddress), "mask": int(c.SubnetMask), "uid": _bytes(c.ClientHardwareAddress),
                            "name": c.ClientName or "", "comment": c.ClientComment or "",
                            "expires": _filetime(c.ClientLeaseExpires), "ctype": int(c.bClientType),
                            "state": int(c.AddressState)})
        try:
            self._enum_resume("read", "DhcpEnumSubnetClientsV5", (sid,), (), read)
        except RpcError as e:
            if e.code == ERROR_DHCP_SUBNET_NOT_PRESENT:
                return []
            raise
        return out

    def option_value(self, opt_id: int, sid: str | None, vendor: str = "", user: str = "") -> list[str] | None:
        si = _scope_info(sid)
        p = POINTER(DHCP_OPTION_VALUE)()
        try:
            self.rpc("read", "DhcpGetOptionValueV5", FLAG_VENDOR if vendor else 0, int(opt_id), user or None,
                     vendor or None, byref(si), byref(p))
        except RpcError:
            return None
        if not p:
            return None
        vals = _format_data(p.contents.Value)[1]
        _free(p)
        return vals

    def _superscopes(self) -> dict[int, str]:
        p = POINTER(DHCP_SUPER_SCOPE_TABLE)()
        try:
            self.rpc("read", "DhcpGetSuperScopeInfoV4", byref(p))
        except RpcError:
            return {}
        out = {}
        if p:
            t = p.contents
            for i in range(t.cEntries):
                e = t.pEntries[i]
                if e.SuperScopeName:
                    out[int(e.SubnetAddress)] = e.SuperScopeName
            _free(p)
        return out

    def _scope(self, sid: int, sup: dict[int, str]) -> dict | None:
        info = self.subnet_info(sid)
        if info is None:
            return None
        rng = self.elements(sid, EL_RANGES)
        lease = self.option_value(51, n2ip(sid))
        try:
            secs = int(lease[0]) if lease else None
        except ValueError:
            secs = None
        return {"ScopeId": n2ip(sid), "SubnetMask": n2ip(info["mask"]), "Name": info["name"],
                "Description": info["comment"], "State": "Active" if info["state"] in (0, 2) else "InActive",
                "StartRange": n2ip(rng[0]["start"]) if rng else "", "EndRange": n2ip(rng[0]["end"]) if rng else "",
                "LeaseDuration": secs, "SuperscopeName": sup.get(sid, ""), "Type": "Dhcp"}

    def scopes(self, sid: str | None = None) -> list[dict]:
        sup = self._superscopes()
        ids = [ip2n(sid)] if sid else self.subnets()
        return [s for s in self.parallel(lambda x: self._scope(x, sup), ids) if s]

    def _ids(self, sid: str | None) -> list[int]:
        return [ip2n(sid)] if sid else self.subnets()

    def exclusions(self, sid: str | None = None) -> list[dict]:
        ids = self._ids(sid)
        out = []
        for x, rows in zip(ids, self.parallel(lambda s: self.elements(s, EL_EXCLUDED), ids)):
            out += [{"ScopeId": n2ip(x), "StartRange": n2ip(r["start"]), "EndRange": n2ip(r["end"])} for r in rows]
        return out

    def statistics(self, sid: str | None = None) -> list[dict]:
        p = POINTER(DHCP_MIB_INFO)()
        self.rpc("read", "DhcpGetMibInfo", byref(p))
        mib = {}
        if p:
            m = p.contents
            for i in range(m.Scopes):
                s = m.ScopeInfo[i]
                mib[int(s.Subnet)] = (int(s.NumAddressesInuse), int(s.NumAddressesFree), int(s.NumPendingOffers))
            _free(p)
        ids = [ip2n(sid)] if sid else list(mib)
        reserved = dict(zip(ids, self.parallel(lambda s: len(self.elements(s, EL_RESERVED)), ids)))
        out = []
        for x in ids:
            used, free, pend = mib.get(x, (0, 0, 0))
            tot = used + free
            out.append({"ScopeId": n2ip(x), "InUse": used, "Free": free, "Pending": pend, "Reserved": reserved.get(x, 0),
                        "PercentageInUse": round(used * 100.0 / tot, 2) if tot else 0.0})
        return out

    def reservations(self, sid: str | None = None) -> list[dict]:
        def one(x):
            res = self.elements(x, EL_RESERVED)
            if not res:
                return []
            names = {c["ip"]: c for c in self.clients(x)}
            rows = []
            for r in res:
                c = names.get(r["ip"], {})
                rows.append({"ScopeId": n2ip(x), "IPAddress": n2ip(r["ip"]), "ClientId": _hexid(r["uid"], x),
                             "Name": c.get("name", ""), "Description": c.get("comment", ""),
                             "Type": CLIENT_TYPES.get(r["ctype"] & 3, "Both")})
            return rows
        return [r for rows in self.parallel(one, self._ids(sid)) for r in rows]

    def leases(self, sid: str | None = None) -> list[dict]:
        states = {0: "Offered", 1: "Active", 2: "Declined", 3: "Expired"}

        def one(x):
            res = {r["ip"] for r in self.elements(x, EL_RESERVED)}
            rows = []
            for c in self.clients(x):
                st = c["state"] & 0x03
                if c["ip"] in res:
                    state = "ActiveReservation" if st == 1 and c["expires"] else "InactiveReservation"
                else:
                    state = states.get(st, "Active")
                rows.append({"ScopeId": n2ip(x), "IPAddress": n2ip(c["ip"]), "ClientId": _hexid(c["uid"], x),
                             "HostName": c["name"], "Description": c["comment"], "AddressState": state,
                             "LeaseExpiryTime": c["expires"], "ClientType": CLIENT_TYPES.get(c["ctype"] & 3, "Dhcp")})
            return rows
        return [r for rows in self.parallel(one, self._ids(sid)) for r in rows]

    def dns_setting(self, sid: str | None = None) -> list[dict]:
        v = self.option_value(81, sid) if sid else None
        if v is None:
            v = self.option_value(81, None)
        try:
            f = _to_number(v[0]) if v else DNS_DEFAULT
        except ValueError:
            f = DNS_DEFAULT
        dyn = "Never" if not f & DNS_ENABLED else "Always" if f & DNS_BOTH_ALWAYS else "OnClientRequest"
        return [{"DynamicUpdates": dyn, "DeleteDnsRROnLeaseExpiry": bool(f & DNS_CLEANUP),
                 "UpdateDnsRRForOlderClients": bool(f & DNS_DOWNLEVEL), "DisableDnsPtrRRUpdate": bool(f & DNS_NO_PTR),
                 "NameProtection": bool(f & DNS_DHCID)}]

    def superscope_rows(self) -> list[dict]:
        groups: dict[str, list[str]] = {}
        for sid, name in self._superscopes().items():
            groups.setdefault(name, []).append(n2ip(sid))
        return [{"SuperscopeName": k, "ScopeId": v} for k, v in groups.items()]

    # --- Optionen -----------------------------------------------------------------------------------
    def definitions(self, fresh: bool = False) -> list[dict]:
        with self._defs_lock:
            if self._defs is not None and not fresh:
                return list(self._defs)
        p = POINTER(DHCP_ALL_OPTIONS)()
        self.rpc("read", "DhcpGetAllOptions", 0, byref(p))
        out = []

        def row(o: DHCP_OPTION, vendor: str, cls: str):
            typ, vals = _format_data(o.DefaultValue)
            out.append({"OptionId": int(o.OptionID), "Name": o.OptionName or "", "Description": o.OptionComment or "",
                        "Type": typ or "String", "MultiValued": int(o.OptionType) == 1, "VendorClass": vendor or "",
                        "UserClass": cls or "", "DefaultValue": vals})
        if p:
            a = p.contents
            if a.NonVendorOptions:
                arr = a.NonVendorOptions.contents
                for i in range(arr.NumElements):
                    row(arr.Options[i], "", "")
            for i in range(a.NumVendorOptions):
                v = a.VendorOptions[i]
                row(v.Option, v.VendorName or "", v.ClassName or "")
            _free(p)
        with self._defs_lock:
            self._defs = out
        return list(out)

    def _def(self, opt_id: int, vendor: str = "") -> dict | None:
        for fresh in (False, True):
            for d in self.definitions(fresh):
                if d["OptionId"] == int(opt_id) and (d["VendorClass"] or "") == (vendor or ""):
                    return d
        return None

    def option_values(self, sid: str | None = None) -> list[dict]:
        si = _scope_info(sid)
        p = POINTER(DHCP_ALL_OPTION_VALUES)()
        self.rpc("read", "DhcpGetAllOptionValues", 0, byref(si), byref(p))
        names = {(d["VendorClass"], d["OptionId"]): d["Name"] for d in self.definitions()}
        out = []
        if p:
            a = p.contents
            for i in range(a.NumElements):
                it = a.Options[i]
                if not it.OptionsArray:
                    continue
                vendor = (it.VendorName or "") if it.IsVendor else ""
                user = it.ClassName or ""
                arr = it.OptionsArray.contents
                for k in range(arr.NumElements):
                    v = arr.Values[k]
                    typ, vals = _format_data(v.Value)
                    oid = int(v.OptionID)
                    out.append({"OptionId": oid, "Name": names.get((vendor, oid), ""), "Value": vals, "Type": typ or "",
                                "VendorClass": vendor, "UserClass": user})
            _free(p)
        return out

    def classes(self) -> list[dict]:
        out = []

        def read(buf):
            a = buf.contents
            for i in range(a.NumElements):
                c = a.Classes[i]
                data = bytes(c.ClassData[:c.ClassDataLength]) if c.ClassData and c.ClassDataLength else b""
                out.append({"Name": c.ClassName or "", "Description": c.ClassComment or "",
                            "Type": "Vendor" if c.IsVendor else "User", "Data": data.decode("ascii", errors="replace")})
        self._enum_resume("read", "DhcpEnumClasses", (0,), (), read)
        return out

    # --- Failover -----------------------------------------------------------------------------------
    def fo_enum(self) -> list[dict]:
        out = []

        def read(buf):
            a = buf.contents
            for i in range(a.NumElements):
                out.append(_fo_read(a.pRelationships[i]))
        self._enum_resume("enum", "DhcpV4FailoverEnumRelationship", (), (), read)
        return out

    def failover(self) -> list[dict]:
        return [fo_cmdlet_row(r) for r in self.fo_enum()]

    def fo_call(self, op: str, rel: dict | None = None, name: str | None = None, flags: int = 0):
        if op == "enum":
            return {"items": self.fo_enum()}
        if op == "delete":
            self.rpc("delete", "DhcpV4FailoverDeleteRelationship", name)
            return True
        keep: list = []
        s = _fo_build(rel or {}, keep)
        fn = {"create": "DhcpV4FailoverCreateRelationship", "add_scopes": "DhcpV4FailoverAddScopeToRelationship",
              "remove_scopes": "DhcpV4FailoverDeleteScopeFromRelationship"}.get(op)
        if op == "set":
            self.rpc("set", "DhcpV4FailoverSetRelationship", int(flags), byref(s))
        elif fn:
            self.rpc(op, fn, byref(s))
        else:
            raise RuntimeError(f"@ERR:bad_op:{op}")
        return True

    # --- Ändern -------------------------------------------------------------------------------------
    def set_scope(self, p: dict) -> None:
        sid = ip2n(p["ScopeId"])
        if any(k in p for k in ("Name", "Description", "State")):
            info = DHCP_SUBNET_INFO()
            cur = POINTER(DHCP_SUBNET_INFO)()
            self.rpc("read", "DhcpGetSubnetInfo", sid, byref(cur))
            c = cur.contents
            info.SubnetAddress, info.SubnetMask = c.SubnetAddress, c.SubnetMask
            info.SubnetName = p["Name"] if "Name" in p and p["Name"] is not None else (c.SubnetName or "")
            info.SubnetComment = p["Description"] if "Description" in p and p["Description"] is not None else (c.SubnetComment or "")
            info.PrimaryHost.IpAddress = c.PrimaryHost.IpAddress
            state = int(c.SubnetState)
            if p.get("State"):
                state = 0 if str(p["State"]).lower() == "active" else 1
            info.SubnetState = state
            _free(cur)
            self.rpc("write", "DhcpSetSubnetInfo", sid, byref(info))
        if p.get("LeaseDuration") is not None:
            self.set_option(51, [str(_secs(p["LeaseDuration"]))], p["ScopeId"], type_name="DWord")
        if p.get("StartRange") and p.get("EndRange"):
            self.set_range(sid, ip2n(p["StartRange"]), ip2n(p["EndRange"]))

    def _range_el(self, t: int, start: int, end: int, keep: list) -> DHCP_SUBNET_ELEMENT_DATA_V5:
        r = DHCP_BOOTP_IP_RANGE(start, end, 0, 0)
        keep.append(r)
        e = DHCP_SUBNET_ELEMENT_DATA_V5()
        e.ElementType = t
        e.Element.IpRange = ctypes.pointer(r)
        return e

    def set_range(self, sid: int, start: int, end: int) -> None:
        """Ändert den Verteilbereich. Ein vorhandener Bereich wird per DhcpAddSubnetElementV5 direkt angepasst
        (MS-DHCPM 3.2.4.38: neuer Bereich muss den alten enthalten oder darin liegen). Entfernen geht bei
        Failover-Scopes nicht (ERROR_DHCP_FO_RANGE_PART_OF_REL), daher bei Verschiebung über die Vereinigung."""
        old = self.elements(sid, EL_RANGES)
        keep: list = []
        for r in old:
            if (r["start"], r["end"]) == (start, end):
                return
        t = old[0]["type"] if old and old[0]["type"] not in (EL_RANGES,) else EL_RANGES_DHCP_ONLY
        if len(old) == 1:
            o = old[0]
            steps = [(start, end)]
            if not (o["start"] <= start and end <= o["end"]) and not (start <= o["start"] and o["end"] <= end):
                steps.insert(0, (min(start, o["start"]), max(end, o["end"])))     # erst erweitern, dann verkleinern
            for i, (a, b) in enumerate(steps):
                try:
                    self.rpc("write", "DhcpAddSubnetElementV5", sid, byref(self._range_el(t, a, b, keep)))
                except RpcError:
                    if i:          # Vereinigung steht schon - alten Bereich wiederherstellen
                        try:
                            self.rpc("write", "DhcpAddSubnetElementV5", sid,
                                     byref(self._range_el(t, o["start"], o["end"], keep)))
                        except RpcError:
                            pass
                    raise
            return
        for r in old:
            e = self._range_el(r["type"], r["start"], r["end"], keep)
            try:
                self.rpc("write", "DhcpRemoveSubnetElementV5", sid, byref(e), NO_FORCE)
            except RpcError:
                self.rpc("write", "DhcpRemoveSubnetElementV5", sid, byref(e), FULL_FORCE)
        e = self._range_el(t, start, end, keep)
        try:
            self.rpc("write", "DhcpAddSubnetElementV5", sid, byref(e))
        except RpcError:
            for r in old:      # alten Bereich wiederherstellen
                try:
                    self.rpc("write", "DhcpAddSubnetElementV5", sid, byref(self._range_el(r["type"], r["start"], r["end"], keep)))
                except RpcError:
                    pass
            raise

    def add_scope(self, p: dict) -> None:
        mask = ip2n(p["SubnetMask"])
        start, end = ip2n(p["StartRange"]), ip2n(p["EndRange"])
        sid = start & mask
        info = DHCP_SUBNET_INFO()
        info.SubnetAddress, info.SubnetMask = sid, mask
        info.SubnetName = p.get("Name") or ""
        info.SubnetComment = p.get("Description") or ""
        info.SubnetState = 0 if str(p.get("State") or "Active").lower() == "active" else 1
        self.rpc("write", "DhcpCreateSubnet", sid, byref(info))
        keep: list = []
        try:
            self.rpc("write", "DhcpAddSubnetElementV5", sid, byref(self._range_el(EL_RANGES_DHCP_ONLY, start, end, keep)))
            if p.get("LeaseDuration") is not None:
                self.set_option(51, [str(_secs(p["LeaseDuration"]))], n2ip(sid), type_name="DWord")
        except Exception:
            try:
                self.rpc("write", "DhcpDeleteSubnet", sid, FULL_FORCE)
            except RpcError:
                pass
            raise

    def remove_scope(self, sid: str) -> None:
        self.rpc("write", "DhcpDeleteSubnet", ip2n(sid), FULL_FORCE)

    def _excl_el(self, start: int, end: int, keep: list) -> DHCP_SUBNET_ELEMENT_DATA_V5:
        r = DHCP_IP_RANGE(start, end)
        keep.append(r)
        e = DHCP_SUBNET_ELEMENT_DATA_V5()
        e.ElementType = EL_EXCLUDED
        e.Element.ExcludeIpRange = ctypes.pointer(r)
        return e

    def add_exclusion(self, sid: str, start: str, end: str) -> None:
        keep: list = []
        self.rpc("write", "DhcpAddSubnetElementV5", ip2n(sid), byref(self._excl_el(ip2n(start), ip2n(end), keep)))

    def remove_exclusion(self, sid: str, start: str, end: str) -> None:
        keep: list = []
        self.rpc("write", "DhcpRemoveSubnetElementV5", ip2n(sid), byref(self._excl_el(ip2n(start), ip2n(end), keep)),
                 FULL_FORCE)

    def set_option(self, opt_id: int, values: list, sid: str | None = None, vendor: str = "", user: str = "",
                   type_name: str | None = None) -> None:
        if type_name is None:
            d = self._def(opt_id, vendor)
            type_name = d["Type"] if d else "String"
        keep: list = []
        data = _build_data(type_name, values, keep)
        si = _scope_info(sid)
        self.rpc("write", "DhcpSetOptionValueV5", FLAG_VENDOR if vendor else 0, int(opt_id), user or None,
                 vendor or None, byref(si), byref(data))

    def remove_option(self, opt_id: int, sid: str | None = None, vendor: str = "", user: str = "") -> None:
        si = _scope_info(sid)
        self.rpc("write", "DhcpRemoveOptionValueV5", FLAG_VENDOR if vendor else 0, int(opt_id), user or None,
                 vendor or None, byref(si))

    def _reservation_el(self, ip: int, uid: bytes, ctype: int, keep: list) -> DHCP_SUBNET_ELEMENT_DATA_V5:
        buf = (BYTE * max(1, len(uid))).from_buffer_copy(uid or b"\0")
        bd = DHCP_BINARY_DATA(len(uid), ctypes.cast(buf, POINTER(BYTE)))
        r = DHCP_IP_RESERVATION_V4(ip, ctypes.pointer(bd), ctype)
        keep += [buf, bd, r]
        e = DHCP_SUBNET_ELEMENT_DATA_V5()
        e.ElementType = EL_RESERVED
        e.Element.ReservedIp = ctypes.pointer(r)
        return e

    def _set_client_text(self, ip: int, name: str | None, desc: str | None) -> None:
        if name is None and desc is None:
            return
        si = DHCP_SEARCH_INFO()
        si.SearchType = 0
        si.SearchInfo.ClientIpAddress = ip
        p = POINTER(DHCP_CLIENT_INFO_V4)()
        self.rpc("read", "DhcpGetClientInfoV4", byref(si), byref(p))
        c = p.contents
        n = DHCP_CLIENT_INFO_V4()
        n.ClientIpAddress, n.SubnetMask = c.ClientIpAddress, c.SubnetMask
        uid = _bytes(c.ClientHardwareAddress)
        buf = (BYTE * max(1, len(uid))).from_buffer_copy(uid or b"\0")
        n.ClientHardwareAddress = DHCP_BINARY_DATA(len(uid), ctypes.cast(buf, POINTER(BYTE)))
        n.ClientName = name if name is not None else (c.ClientName or "")
        n.ClientComment = desc if desc is not None else (c.ClientComment or "")
        n.ClientLeaseExpires = DATE_TIME(c.ClientLeaseExpires.dwLowDateTime, c.ClientLeaseExpires.dwHighDateTime)
        n.OwnerHost.IpAddress = c.OwnerHost.IpAddress
        n.bClientType = c.bClientType
        _free(p)
        self.rpc("write", "DhcpSetClientInfoV4", byref(n))

    @staticmethod
    def _ctype(name) -> int:
        return {"dhcp": 1, "bootp": 2, "both": 3}.get(str(name or "Dhcp").lower(), 1)

    def add_reservation(self, p: dict) -> None:
        sid, rip = ip2n(p["ScopeId"]), ip2n(p["IPAddress"])
        keep: list = []
        self.rpc("write", "DhcpAddSubnetElementV5", sid,
                 byref(self._reservation_el(rip, _cid_bytes(p["ClientId"]), self._ctype(p.get("Type")), keep)))
        self._set_client_text(rip, p.get("Name") or "", p.get("Description") or "")

    def _find_reservation(self, rip: int, sid: int | None = None) -> tuple[int, dict]:
        ids = [sid] if sid is not None else self.subnets()
        for s in ids:
            for r in self.elements(s, EL_RESERVED):
                if r["ip"] == rip:
                    return s, r
        raise RuntimeError(f"@ERR:res_missing:{n2ip(rip)}")

    def set_reservation(self, p: dict) -> None:
        rip = ip2n(p["IPAddress"])
        sid, cur = self._find_reservation(rip)
        uid = _cid_bytes(p["ClientId"]) if p.get("ClientId") else cur["uid"]
        ctype = self._ctype(p.get("Type")) if p.get("Type") else cur["ctype"]
        same_uid = _hexid(uid, sid) == _hexid(cur["uid"], sid)
        if not same_uid or ctype != cur["ctype"]:
            keep: list = []
            self.rpc("write", "DhcpRemoveSubnetElementV5", sid, byref(self._reservation_el(rip, cur["uid"], cur["ctype"], keep)),
                     FULL_FORCE)
            try:
                self.rpc("write", "DhcpAddSubnetElementV5", sid, byref(self._reservation_el(rip, uid, ctype, keep)))
            except RpcError:
                self.rpc("write", "DhcpAddSubnetElementV5", sid,
                         byref(self._reservation_el(rip, cur["uid"], cur["ctype"], keep)))
                raise
        self._set_client_text(rip, p.get("Name"), p.get("Description"))

    def remove_reservation(self, sid: str, rip: str) -> None:
        s, cur = self._find_reservation(ip2n(rip), ip2n(sid) if sid else None)
        keep: list = []
        self.rpc("write", "DhcpRemoveSubnetElementV5", s, byref(self._reservation_el(cur["ip"], cur["uid"], cur["ctype"], keep)),
                 FULL_FORCE)

    def remove_lease(self, rip: str) -> None:
        si = DHCP_SEARCH_INFO()
        si.SearchType = 0
        si.SearchInfo.ClientIpAddress = ip2n(rip)
        self.rpc("write", "DhcpDeleteClientInfo", byref(si))

    def set_dns(self, p: dict) -> None:
        dyn = str(p.get("DynamicUpdates") or "OnClientRequest").lower()
        f = 0 if dyn == "never" else DNS_ENABLED | (DNS_BOTH_ALWAYS if dyn == "always" else 0)
        if _truthy(p.get("DeleteDnsRROnLeaseExpiry")):
            f |= DNS_CLEANUP
        if _truthy(p.get("UpdateDnsRRForOlderClients")):
            f |= DNS_DOWNLEVEL
        if _truthy(p.get("DisableDnsPtrRRUpdate")):
            f |= DNS_NO_PTR
        if _truthy(p.get("NameProtection")):
            f |= DNS_DHCID
        self.set_option(81, [str(f)], p.get("ScopeId"), type_name="DWord")

    def _option_struct(self, d: dict, keep: list) -> DHCP_OPTION:
        o = DHCP_OPTION()
        o.OptionID = int(d["OptionId"])
        o.OptionName = d.get("Name") or ""
        o.OptionComment = d.get("Description") or ""
        dv = [x for x in _list(d.get("DefaultValue")) if str(x) != ""] or [_empty_value(d["Type"])]
        if d["Type"] in ("BinaryData", "EncapsulatedData") and dv == [""]:
            dv = []
        o.DefaultValue = _build_data(d["Type"], dv, keep)
        o.OptionType = 1 if _truthy(d.get("MultiValued")) else 0
        return o

    def add_definition(self, p: dict) -> None:
        keep: list = []
        vendor = p.get("VendorClass") or ""
        o = self._option_struct({"OptionId": p["OptionId"], "Name": p.get("Name"), "Description": p.get("Description"),
                                 "Type": p.get("Type") or "String", "MultiValued": p.get("MultiValued"),
                                 "DefaultValue": p.get("DefaultValue")}, keep)
        self.rpc("write", "DhcpCreateOptionV5", FLAG_VENDOR if vendor else 0, int(p["OptionId"]), None, vendor or None,
                 byref(o))
        self.definitions(True)

    def set_definition(self, p: dict) -> None:
        vendor = p.get("VendorClass") or ""
        cur = self._def(p["OptionId"], vendor)
        if not cur:
            raise RpcError("write", self.server, 20010)     # ERROR_DHCP_OPTION_NOT_PRESENT
        d = dict(cur)
        for k in ("Name", "Description", "DefaultValue"):
            if p.get(k) is not None:
                d[k] = p[k]
        keep: list = []
        o = self._option_struct(d, keep)
        self.rpc("write", "DhcpSetOptionInfoV5", FLAG_VENDOR if vendor else 0, int(p["OptionId"]), None, vendor or None,
                 byref(o))
        self.definitions(True)

    def remove_definition(self, p: dict) -> None:
        vendor = p.get("VendorClass") or ""
        self.rpc("write", "DhcpRemoveOptionV5", FLAG_VENDOR if vendor else 0, int(p["OptionId"]), None, vendor or None)
        self.definitions(True)


def fo_cmdlet_row(r: dict) -> dict:
    """Rohdaten einer Failover-Beziehung (Sicht des abgefragten Servers) wie Get-DhcpServerv4Failover."""
    primary = r["server_type"] == 0
    partner = (r["secondary_name"] or r["secondary_ip"]) if primary else (r["primary_name"] or r["primary_ip"])
    pct = int(r["percentage"])
    hs = r["mode"] == 1
    sp = int(r["safe_period"])
    st = int(r["state"])
    return {"Name": r["name"], "PartnerServer": partner, "Mode": "HotStandby" if hs else "LoadBalance",
            "ServerRole": ("Active" if primary else "Standby") if hs else "",
            "LoadBalancePercent": None if hs else (pct if primary else 100 - pct),
            "ReservePercent": pct if hs else None, "MaxClientLeadTime": int(r["mclt"]),
            "AutoStateTransition": sp not in (0, UNLIMITED), "StateSwitchInterval": 0 if sp == UNLIMITED else sp,
            "State": FO_STATES[st] if 0 <= st < len(FO_STATES) else str(st), "ScopeId": r["scopes"],
            "EnableAuth": bool(r["secret"])}


def _fo_read(s: DHCP_FAILOVER_RELATIONSHIP) -> dict:
    scopes = []
    if s.pScopes:
        a = s.pScopes.contents
        scopes = [n2ip(a.Elements[i]) for i in range(a.NumElements)]
    return {"name": s.RelationshipName or "", "primary_ip": n2ip(s.PrimaryServer), "secondary_ip": n2ip(s.SecondaryServer),
            "primary_name": s.PrimaryServerName or "", "secondary_name": s.SecondaryServerName or "", "mode": int(s.Mode),
            "server_type": int(s.ServerType), "state": int(s.State), "prev_state": int(s.PrevState), "mclt": int(s.Mclt),
            "safe_period": int(s.SafePeriod), "percentage": int(s.Percentage), "secret": bool(s.SharedSecret),
            "scopes": scopes}


def _fo_build(a: dict, keep: list) -> DHCP_FAILOVER_RELATIONSHIP:
    s = DHCP_FAILOVER_RELATIONSHIP()
    s.RelationshipName = a.get("name") or None
    if a.get("primary_ip"):
        s.PrimaryServer = ip2n(a["primary_ip"])
    if a.get("secondary_ip"):
        s.SecondaryServer = ip2n(a["secondary_ip"])
    s.PrimaryServerName = a.get("primary_name") or None
    s.SecondaryServerName = a.get("secondary_name") or None
    for k, f in (("mode", "Mode"), ("server_type", "ServerType"), ("mclt", "Mclt"), ("safe_period", "SafePeriod"),
                 ("percentage", "Percentage")):
        if a.get(k) is not None:
            setattr(s, f, int(a[k]))
    if a.get("secret"):
        s.SharedSecret = str(a["secret"])
    scopes = [ip2n(x) for x in _list(a.get("scopes")) if x]
    if scopes:
        el = (DWORD * len(scopes))(*scopes)
        arr = DHCP_IP_ARRAY(len(scopes), ctypes.cast(el, POINTER(DWORD)))
        keep += [el, arr]
        s.pScopes = ctypes.pointer(arr)
    keep.append(s)
    return s


def dhcp_in_dc() -> list[dict]:
    """Im AD autorisierte DHCP-Server."""
    lib = _dll()
    p = POINTER(DHCPDS_SERVERS)()
    rc = int(lib.DhcpEnumServers(0, None, byref(p), None, None))
    if rc != 0:
        raise RpcError("ad", "", rc)
    out = []
    if p:
        a = p.contents
        for i in range(a.NumElements):
            s = a.Servers[i]
            out.append({"name": s.ServerName or "", "ip": n2ip(s.ServerAddress)})
        _free(p)
    return out


# Cmdlet-Name -> Funktion(api, parameter); Ergebnis immer eine Liste von Dicts in Cmdlet-Form
CMDLETS = {
    "Get-DhcpServerVersion": lambda a, p: [a.version()],
    "Get-DhcpServerSetting": lambda a, p: a.server_setting(),
    "Get-DhcpServerAuditLog": lambda a, p: a.audit_log(),
    "Get-DhcpServerDatabase": lambda a, p: a.database(),
    "Get-DhcpServerDnsCredential": lambda a, p: a.dns_credential(),
    "Get-DhcpServerv4Binding": lambda a, p: a.bindings(),
    "Get-DhcpServerv4Policy": lambda a, p: a.policies(),
    "Get-DhcpServerv4FilterList": lambda a, p: a.filter_list(),
    "Get-DhcpServerv4Filter": lambda a, p: a.filters(p.get("List") or "Allow"),
    "Get-DhcpServerv4Superscope": lambda a, p: a.superscope_rows(),
    "Get-DhcpServerv4Scope": lambda a, p: a.scopes(p.get("ScopeId")),
    "Get-DhcpServerv4ScopeStatistics": lambda a, p: a.statistics(p.get("ScopeId")),
    "Get-DhcpServerv4ExclusionRange": lambda a, p: a.exclusions(p.get("ScopeId")),
    "Get-DhcpServerv4Reservation": lambda a, p: a.reservations(p.get("ScopeId")),
    "Get-DhcpServerv4Lease": lambda a, p: a.leases(p.get("ScopeId")),
    "Get-DhcpServerv4DnsSetting": lambda a, p: a.dns_setting(p.get("ScopeId")),
    "Get-DhcpServerv4OptionDefinition": lambda a, p: a.definitions(True),
    "Get-DhcpServerv4OptionValue": lambda a, p: a.option_values(p.get("ScopeId")),
    "Get-DhcpServerv4Class": lambda a, p: a.classes(),
    "Get-DhcpServerv4Failover": lambda a, p: a.failover(),
    "Set-DhcpServerv4Scope": lambda a, p: a.set_scope(p),
    "Add-DhcpServerv4Scope": lambda a, p: a.add_scope(p),
    "Remove-DhcpServerv4Scope": lambda a, p: a.remove_scope(p["ScopeId"]),
    "Add-DhcpServerv4ExclusionRange": lambda a, p: a.add_exclusion(p["ScopeId"], p["StartRange"], p["EndRange"]),
    "Remove-DhcpServerv4ExclusionRange": lambda a, p: a.remove_exclusion(p["ScopeId"], p["StartRange"], p["EndRange"]),
    "Set-DhcpServerv4OptionValue": lambda a, p: a.set_option(p["OptionId"], _list(p.get("Value")), p.get("ScopeId"),
                                                             p.get("VendorClass") or "", p.get("UserClass") or ""),
    "Remove-DhcpServerv4OptionValue": lambda a, p: a.remove_option(p["OptionId"], p.get("ScopeId"),
                                                                   p.get("VendorClass") or "", p.get("UserClass") or ""),
    "Add-DhcpServerv4Reservation": lambda a, p: a.add_reservation(p),
    "Set-DhcpServerv4Reservation": lambda a, p: a.set_reservation(p),
    "Remove-DhcpServerv4Reservation": lambda a, p: a.remove_reservation(p.get("ScopeId"), p["IPAddress"]),
    "Remove-DhcpServerv4Lease": lambda a, p: a.remove_lease(p["IPAddress"]),
    "Set-DhcpServerv4DnsSetting": lambda a, p: a.set_dns(p),
    "Add-DhcpServerv4OptionDefinition": lambda a, p: a.add_definition(p),
    "Set-DhcpServerv4OptionDefinition": lambda a, p: a.set_definition(p),
    "Remove-DhcpServerv4OptionDefinition": lambda a, p: a.remove_definition(p),
}
