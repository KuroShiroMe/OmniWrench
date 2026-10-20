# ScopeKeeper - PowerShell-Host (Windows PowerShell 5.1)
#
# Läuft als dauerhafter Hintergrundprozess und spricht mit ScopeKeeper über stdin/stdout (eine JSON-Zeile je
# Nachricht). Anfrage: {"id":1,"cmd":"cim","args":{...}}  Antwort: "@@OWR " + {"id":1,"ok":true,"data":...}
# Fortschritt: "@@OWP " + {"id":1,...}. Kennwörter kommen nur über stdin, nie über die Befehlszeile.
#
# Der Failover-Partner wird bei Bedarf per RPC direkt von diesem Rechner angesprochen (wie die DHCP-Konsole):
# Failover-API aus dhcpsapi.dll und netsh dhcp. Kein WinRM zum Partner, kein CredSSP, kein Double Hop.
# Abweichende Anmeldedaten gelten dabei wie bei "runas /netonly" nur für Netzwerkzugriffe.
#
# Erwartet vom Startskript: $OwIn (StreamReader) und $OwOut (StreamWriter, AutoFlush).

Set-StrictMode -Off
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$global:ConfirmPreference = 'None'
# Arrays sonst in PowerShell 5.1 als {"value":[...],"Count":n} serialisiert
Remove-TypeData System.Array -ErrorAction SilentlyContinue

$script:Sessions = @{}   # Server -> CimSession
$script:Creds = @{}      # Server -> PSCredential ('*' = Anmeldung am Primärserver)
$script:CurrentId = 0

$script:DsmRpcSource = @'
using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.Principal;
using System.Text;

public static class DsmRpc
{
    [StructLayout(LayoutKind.Sequential)]
    struct FO_REL
    {
        public uint PrimaryServer;
        public uint SecondaryServer;
        public int Mode;
        public int ServerType;
        public int State;
        public int PrevState;
        public uint Mclt;
        public uint SafePeriod;
        public IntPtr RelationshipName;
        public IntPtr PrimaryServerName;
        public IntPtr SecondaryServerName;
        public IntPtr pScopes;
        public byte Percentage;
        public IntPtr SharedSecret;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct IP_ARRAY { public uint NumElements; public IntPtr Elements; }

    [StructLayout(LayoutKind.Sequential)]
    struct FO_REL_ARRAY { public uint NumElements; public IntPtr pRelationships; }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct STARTUPINFO
    {
        public int cb; public string lpReserved; public string lpDesktop; public string lpTitle;
        public int dwX; public int dwY; public int dwXSize; public int dwYSize; public int dwXCountChars; public int dwYCountChars;
        public int dwFillAttribute; public int dwFlags; public short wShowWindow; public short cbReserved2;
        public IntPtr lpReserved2; public IntPtr hStdInput; public IntPtr hStdOutput; public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct PROCESS_INFORMATION { public IntPtr hProcess; public IntPtr hThread; public int dwProcessId; public int dwThreadId; }

    public class Relationship
    {
        public string Name;
        public uint PrimaryServer;
        public uint SecondaryServer;
        public string PrimaryServerName;
        public string SecondaryServerName;
        public int Mode;
        public int ServerType;
        public int State;
        public int PrevState;
        public uint Mclt;
        public uint SafePeriod;
        public byte Percentage;
        public string SharedSecret;
        public uint[] Scopes = new uint[0];
    }

    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverCreateRelationship(string ServerIpAddress, IntPtr pRelationship);
    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverSetRelationship(string ServerIpAddress, uint Flags, IntPtr pRelationship);
    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverDeleteRelationship(string ServerIpAddress, string pRelationshipName);
    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverEnumRelationship(string ServerIpAddress, ref uint ResumeHandle, uint PreferredMaximum, out IntPtr pRelationship, out uint RelationshipRead, out uint RelationshipTotal);
    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverAddScopeToRelationship(string ServerIpAddress, IntPtr pRelationship);
    [DllImport("dhcpsapi.dll", CharSet = CharSet.Unicode)] static extern uint DhcpV4FailoverDeleteScopeFromRelationship(string ServerIpAddress, IntPtr pRelationship);
    [DllImport("dhcpsapi.dll")] static extern void DhcpRpcFreeMemory(IntPtr BufferPointer);

    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool LogonUser(string user, string domain, string password, int logonType, int provider, out IntPtr token);
    [DllImport("advapi32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessWithLogonW(string user, string domain, string password, int logonFlags, string app, StringBuilder cmdLine,
        int creationFlags, IntPtr env, string curDir, ref STARTUPINFO si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern bool CreateProcessW(string app, StringBuilder cmdLine, IntPtr pa, IntPtr ta, bool inherit, int flags, IntPtr env, string curDir,
        ref STARTUPINFO si, out PROCESS_INFORMATION pi);
    [DllImport("kernel32.dll", SetLastError = true)] static extern uint WaitForSingleObject(IntPtr h, uint ms);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool GetExitCodeProcess(IntPtr h, out uint code);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool TerminateProcess(IntPtr h, uint code);
    [DllImport("kernel32.dll", SetLastError = true)] static extern bool CloseHandle(IntPtr h);
    [DllImport("kernel32.dll")] public static extern uint GetOEMCP();

    delegate uint RpcCall();

    // RPC-Aufruf, bei abweichenden Anmeldedaten mit "NewCredentials"-Identität (wie runas /netonly)
    static uint Run(string user, string domain, string password, RpcCall call)
    {
        if (String.IsNullOrEmpty(user)) return call();
        IntPtr tok;
        if (!LogonUser(user, domain, password, 9, 3, out tok))
        {
            int err = Marshal.GetLastWin32Error();
            throw new Exception(String.Format("@RPC:logon::{0}:{1}", err, new Win32Exception(err).Message));
        }
        try
        {
            using (WindowsImpersonationContext ctx = WindowsIdentity.Impersonate(tok)) { return call(); }
        }
        finally { CloseHandle(tok); }
    }

    // Fehler strukturiert melden, ScopeKeeper übersetzt den Text: @RPC:<vorgang>:<server>:<code>:<systemtext>
    static Exception Fail(string what, string server, uint rc)
    {
        return new Exception(String.Format("@RPC:{0}:{1}:{2}:{3}", what, server, rc, new Win32Exception((int)rc).Message));
    }

    static IntPtr Str(string v, List<IntPtr> allocs)
    {
        if (v == null) return IntPtr.Zero;
        IntPtr p = Marshal.StringToHGlobalUni(v);
        allocs.Add(p);
        return p;
    }

    static IntPtr Build(Relationship r, List<IntPtr> allocs)
    {
        FO_REL s = new FO_REL();
        s.PrimaryServer = r.PrimaryServer;
        s.SecondaryServer = r.SecondaryServer;
        s.Mode = r.Mode;
        s.ServerType = r.ServerType;
        s.State = r.State;
        s.PrevState = r.PrevState;
        s.Mclt = r.Mclt;
        s.SafePeriod = r.SafePeriod;
        s.RelationshipName = Str(r.Name, allocs);
        s.PrimaryServerName = Str(r.PrimaryServerName, allocs);
        s.SecondaryServerName = Str(r.SecondaryServerName, allocs);
        s.Percentage = r.Percentage;
        s.SharedSecret = Str(r.SharedSecret, allocs);
        if (r.Scopes != null && r.Scopes.Length > 0)
        {
            IntPtr el = Marshal.AllocHGlobal(4 * r.Scopes.Length);
            allocs.Add(el);
            for (int i = 0; i < r.Scopes.Length; i++) Marshal.WriteInt32(el, i * 4, unchecked((int)r.Scopes[i]));
            IP_ARRAY a = new IP_ARRAY();
            a.NumElements = (uint)r.Scopes.Length;
            a.Elements = el;
            IntPtr pa = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(IP_ARRAY)));
            allocs.Add(pa);
            Marshal.StructureToPtr(a, pa, false);
            s.pScopes = pa;
        }
        IntPtr p = Marshal.AllocHGlobal(Marshal.SizeOf(typeof(FO_REL)));
        allocs.Add(p);
        Marshal.StructureToPtr(s, p, false);
        return p;
    }

    static void Free(List<IntPtr> allocs) { foreach (IntPtr p in allocs) Marshal.FreeHGlobal(p); }

    static string ReadStr(IntPtr p) { return p == IntPtr.Zero ? null : Marshal.PtrToStringUni(p); }

    static Relationship Read(IntPtr p)
    {
        FO_REL s = (FO_REL)Marshal.PtrToStructure(p, typeof(FO_REL));
        Relationship r = new Relationship();
        r.PrimaryServer = s.PrimaryServer;
        r.SecondaryServer = s.SecondaryServer;
        r.Mode = s.Mode;
        r.ServerType = s.ServerType;
        r.State = s.State;
        r.PrevState = s.PrevState;
        r.Mclt = s.Mclt;
        r.SafePeriod = s.SafePeriod;
        r.Name = ReadStr(s.RelationshipName);
        r.PrimaryServerName = ReadStr(s.PrimaryServerName);
        r.SecondaryServerName = ReadStr(s.SecondaryServerName);
        r.Percentage = s.Percentage;
        r.SharedSecret = ReadStr(s.SharedSecret);
        if (s.pScopes != IntPtr.Zero)
        {
            IP_ARRAY a = (IP_ARRAY)Marshal.PtrToStructure(s.pScopes, typeof(IP_ARRAY));
            r.Scopes = new uint[a.NumElements];
            for (int i = 0; i < a.NumElements; i++) r.Scopes[i] = unchecked((uint)Marshal.ReadInt32(a.Elements, i * 4));
        }
        return r;
    }

    public static Relationship[] EnumRelationships(string server, string user, string domain, string password)
    {
        List<Relationship> list = new List<Relationship>();
        uint resume = 0;
        for (int round = 0; round < 100; round++)
        {
            IntPtr buf = IntPtr.Zero;
            uint read = 0, total = 0;
            uint rc = Run(user, domain, password, delegate { return DhcpV4FailoverEnumRelationship(server, ref resume, 0xFFFFFFFF, out buf, out read, out total); });
            if (rc == 259) break;
            if (rc != 0 && rc != 234) throw Fail("enum", server, rc);
            if (buf != IntPtr.Zero)
            {
                FO_REL_ARRAY arr = (FO_REL_ARRAY)Marshal.PtrToStructure(buf, typeof(FO_REL_ARRAY));
                int size = Marshal.SizeOf(typeof(FO_REL));
                for (int i = 0; i < arr.NumElements; i++) list.Add(Read(new IntPtr(arr.pRelationships.ToInt64() + (long)i * size)));
                DhcpRpcFreeMemory(buf);
            }
            if (rc == 0) break;
        }
        return list.ToArray();
    }

    static void WithStruct(string what, string server, Relationship r, string user, string domain, string password, Func<IntPtr, uint> call)
    {
        List<IntPtr> allocs = new List<IntPtr>();
        try
        {
            IntPtr p = Build(r, allocs);
            uint rc = Run(user, domain, password, delegate { return call(p); });
            if (rc != 0) throw Fail(what, server, rc);
        }
        finally { Free(allocs); }
    }

    public static void CreateRelationship(string server, Relationship r, string user, string domain, string password)
    {
        WithStruct("create", server, r, user, domain, password, delegate(IntPtr p) { return DhcpV4FailoverCreateRelationship(server, p); });
    }

    public static void SetRelationship(string server, uint flags, Relationship r, string user, string domain, string password)
    {
        WithStruct("set", server, r, user, domain, password, delegate(IntPtr p) { return DhcpV4FailoverSetRelationship(server, flags, p); });
    }

    public static void AddScopes(string server, Relationship r, string user, string domain, string password)
    {
        WithStruct("add_scopes", server, r, user, domain, password, delegate(IntPtr p) { return DhcpV4FailoverAddScopeToRelationship(server, p); });
    }

    public static void RemoveScopes(string server, Relationship r, string user, string domain, string password)
    {
        WithStruct("remove_scopes", server, r, user, domain, password, delegate(IntPtr p) { return DhcpV4FailoverDeleteScopeFromRelationship(server, p); });
    }

    public static void DeleteRelationship(string server, string name, string user, string domain, string password)
    {
        uint rc = Run(user, domain, password, delegate { return DhcpV4FailoverDeleteRelationship(server, name); });
        if (rc != 0) throw Fail("delete", server, rc);
    }

    // Startet einen Befehl unsichtbar; mit Anmeldedaten wie "runas /netonly" (lokal eigenes Konto, im Netz das angegebene)
    public static IntPtr StartHidden(string cmdLine, string user, string domain, string password)
    {
        STARTUPINFO si = new STARTUPINFO();
        si.cb = Marshal.SizeOf(typeof(STARTUPINFO));
        si.dwFlags = 1;          // STARTF_USESHOWWINDOW
        si.wShowWindow = 0;      // SW_HIDE
        PROCESS_INFORMATION pi;
        string sys = Environment.GetFolderPath(Environment.SpecialFolder.System);
        bool ok;
        if (String.IsNullOrEmpty(user))
            ok = CreateProcessW(null, new StringBuilder(cmdLine), IntPtr.Zero, IntPtr.Zero, false, 0x08000000, IntPtr.Zero, sys, ref si, out pi);
        else
            ok = CreateProcessWithLogonW(user, domain, password, 2, null, new StringBuilder(cmdLine), 0x10, IntPtr.Zero, sys, ref si, out pi);
        if (!ok)
        {
            int err = Marshal.GetLastWin32Error();
            throw new Exception(String.Format("@RPC:{0}::{1}:{2}", String.IsNullOrEmpty(user) ? "start" : "start_logon", err, new Win32Exception(err).Message));
        }
        CloseHandle(pi.hThread);
        return pi.hProcess;
    }

    // -1 = läuft noch, sonst Exit-Code
    public static long WaitExit(IntPtr h, int ms)
    {
        uint w = WaitForSingleObject(h, (uint)ms);
        if (w == 0x102) return -1;
        uint code;
        if (!GetExitCodeProcess(h, out code)) return 0xFFFFFFFF;
        return code;
    }

    public static void Kill(IntPtr h) { TerminateProcess(h, 1); }
    public static void CloseH(IntPtr h) { if (h != IntPtr.Zero) CloseHandle(h); }
}
'@

# ---------------------------------------------------------------------------------------------------
# Protokoll
# ---------------------------------------------------------------------------------------------------
function Send-Line {
    param([string]$Prefix, $Object)
    $OwOut.WriteLine($Prefix + (ConvertTo-Json -InputObject $Object -Compress -Depth 10))
}

function Send-Progress {
    param([hashtable]$Data)
    $Data.id = $script:CurrentId
    Send-Line '@@OWP ' $Data
}

# Ausgaben von Cmdlets in einfache Werte umwandeln (Hashtables, Listen, Zahlen, Texte)
function ConvertTo-Plain {
    param($V, [int]$Depth = 0)
    if ($null -eq $V) { return $null }
    if ($V -is [string] -or $V -is [bool]) { return $V }
    if ($V -is [char] -or $V -is [guid]) { return [string]$V }
    if ($V -is [byte] -or $V -is [int16] -or $V -is [uint16] -or $V -is [int] -or $V -is [uint32] -or $V -is [long] -or
        $V -is [uint64] -or $V -is [double] -or $V -is [single] -or $V -is [decimal] -or $V -is [sbyte]) { return $V }
    if ($V -is [TimeSpan]) {
        if ($V.TotalSeconds -ge 4294967295) { return [int64]4294967295 }
        return [int64][Math]::Round($V.TotalSeconds)
    }
    if ($V -is [DateTime]) { return $V.ToString('yyyy-MM-ddTHH:mm:ss') }
    if ($V -is [enum]) { return $V.ToString() }
    if ($V -is [System.Net.IPAddress]) { return $V.IPAddressToString }
    if ($V -is [System.Collections.IDictionary]) {
        $h = @{}
        foreach ($k in $V.Keys) { $h[[string]$k] = ConvertTo-Plain $V[$k] ($Depth + 1) }
        return $h
    }
    if ($V -is [System.Collections.IEnumerable]) {
        $list = New-Object System.Collections.ArrayList
        foreach ($x in $V) { [void]$list.Add((ConvertTo-Plain $x ($Depth + 1))) }
        return , $list.ToArray()
    }
    if ($Depth -ge 4) { return [string]$V }
    $h = @{}
    foreach ($p in $V.PSObject.Properties) {
        if ($p.Name -in 'CimClass', 'CimInstanceProperties', 'CimSystemProperties', 'PSComputerName', 'PSShowComputerName') { continue }
        if ($p.MemberType -notmatch 'Property') { continue }
        try { $h[$p.Name] = ConvertTo-Plain $p.Value ($Depth + 1) } catch { }
    }
    $h
}

function ConvertTo-Hashtable {
    param($Obj)
    $h = @{}
    if ($null -eq $Obj) { return $h }
    foreach ($p in $Obj.PSObject.Properties) { $h[$p.Name] = ConvertFrom-Arg $p.Value }
    $h
}

# Argumente aus JSON: {"__ts": Sekunden} -> TimeSpan, Listen -> string[] bzw. object[]
function ConvertFrom-Arg {
    param($V)
    if ($null -eq $V) { return $null }
    if ($V -is [System.Management.Automation.PSCustomObject]) {
        $names = @($V.PSObject.Properties | ForEach-Object { $_.Name })
        if ($names -contains '__ts') {
            $s = [double]$V.__ts
            if ($s -ge 4294967295) { return [TimeSpan]::MaxValue }
            return [TimeSpan]::FromSeconds($s)
        }
        return (ConvertTo-Hashtable $V)
    }
    if ($V -is [System.Array]) {
        if (@($V | Where-Object { $_ -isnot [string] }).Count -eq 0) { return [string[]]$V }
        return , @($V | ForEach-Object { ConvertFrom-Arg $_ })
    }
    $V
}

function Get-InnerMessage {
    param($Err)
    $e = $Err.Exception
    while ($e.InnerException) { $e = $e.InnerException }
    $m = [string]$e.Message
    if (-not $m) { $m = [string]$Err }
    $m.Trim()
}

function New-Cred {
    param([string]$User, [string]$Password)
    if (-not $User) { return $null }
    $sec = New-Object System.Security.SecureString
    foreach ($ch in ([string]$Password).ToCharArray()) { $sec.AppendChar($ch) }
    $sec.MakeReadOnly()
    New-Object System.Management.Automation.PSCredential($User, $sec)
}

function Get-Session {
    param([string]$Server)
    $s = $script:Sessions[$Server]
    if (-not $s) { throw "@ERR:not_connected:$Server" }
    $s
}

# ---------------------------------------------------------------------------------------------------
# Verbindung (WSMan, Fallback DCOM)
# ---------------------------------------------------------------------------------------------------
function Connect-Target {
    param([string]$ComputerName, $Credential)
    $base = @{ ComputerName = $ComputerName; ErrorAction = 'Stop'; OperationTimeoutSec = 60 }
    if ($Credential) { $base.Credential = $Credential }
    $errs = @()
    foreach ($proto in 'Wsman', 'Dcom') {
        $session = $null
        try {
            $opt = New-CimSessionOption -Protocol $proto
            $session = New-CimSession @base -SessionOption $opt
            $null = Get-DhcpServerVersion -CimSession $session -ErrorAction Stop
            return $session
        } catch {
            $errs += "$($proto.ToUpper()): $(Get-InnerMessage $_)"
            if ($session) { Remove-CimSession -CimSession $session -ErrorAction SilentlyContinue }
        }
    }
    throw ($errs -join "`n`n")
}

# ---------------------------------------------------------------------------------------------------
# RPC: Failover-API und netsh dhcp
# ---------------------------------------------------------------------------------------------------
function Initialize-DhcpRpc {
    if ('DsmRpc' -as [type]) { return }
    Add-Type -TypeDefinition $script:DsmRpcSource -Language CSharp -ErrorAction Stop
}

# @(Benutzer, Domäne, Kennwort) - alles $null = aktuelle Windows-Anmeldung
function Get-RpcCredParts {
    param([string]$Server)
    $c = if ($Server -and $script:Creds.ContainsKey($Server)) { $script:Creds[$Server] } else { $script:Creds['*'] }
    if (-not $c) { return @($null, $null, $null) }
    $n = $c.GetNetworkCredential()
    $u = [string]$n.UserName; $d = [string]$n.Domain
    if (-not $d -and $u -notmatch '@') { $d = $env:USERDOMAIN }
    @($u, $(if ($d) { $d } else { $null }), $n.Password)
}

function Get-OemEncoding {
    Initialize-DhcpRpc
    try { [System.Text.Encoding]::GetEncoding([int][DsmRpc]::GetOEMCP()) } catch { [System.Text.Encoding]::GetEncoding(850) }
}

function ConvertTo-IPNumber { param([string]$Ip) $b = ([System.Net.IPAddress]::Parse($Ip.Trim())).GetAddressBytes(); [uint32](([uint32]$b[0] -shl 24) -bor ([uint32]$b[1] -shl 16) -bor ([uint32]$b[2] -shl 8) -bor [uint32]$b[3]) }
function ConvertFrom-IPNumber { param([uint32]$N) '{0}.{1}.{2}.{3}' -f (($N -shr 24) -band 255), (($N -shr 16) -band 255), (($N -shr 8) -band 255), ($N -band 255) }

function ConvertTo-FoStruct {
    param($A)
    Initialize-DhcpRpc
    $r = New-Object 'DsmRpc+Relationship'
    if ($null -eq $A) { return $r }
    $r.Name = [string]$A.name
    if ($A.primary_ip) { $r.PrimaryServer = ConvertTo-IPNumber $A.primary_ip }
    if ($A.secondary_ip) { $r.SecondaryServer = ConvertTo-IPNumber $A.secondary_ip }
    if ($A.primary_name) { $r.PrimaryServerName = [string]$A.primary_name }
    if ($A.secondary_name) { $r.SecondaryServerName = [string]$A.secondary_name }
    if ($null -ne $A.mode) { $r.Mode = [int]$A.mode }
    if ($null -ne $A.server_type) { $r.ServerType = [int]$A.server_type }
    if ($null -ne $A.mclt) { $r.Mclt = [uint32]$A.mclt }
    if ($null -ne $A.safe_period) { $r.SafePeriod = [uint32]$A.safe_period }
    if ($null -ne $A.percentage) { $r.Percentage = [byte]$A.percentage }
    if ($A.secret) { $r.SharedSecret = [string]$A.secret }
    $r.Scopes = [uint32[]]@(@($A.scopes) | Where-Object { $_ } | ForEach-Object { ConvertTo-IPNumber ([string]$_) })
    $r
}

function ConvertFrom-FoStruct {
    param($R)
    @{
        name = $R.Name; primary_ip = (ConvertFrom-IPNumber $R.PrimaryServer); secondary_ip = (ConvertFrom-IPNumber $R.SecondaryServer)
        primary_name = $R.PrimaryServerName; secondary_name = $R.SecondaryServerName; mode = $R.Mode; server_type = $R.ServerType
        state = $R.State; prev_state = $R.PrevState; mclt = $R.Mclt; safe_period = $R.SafePeriod; percentage = [int]$R.Percentage
        secret = [bool]$R.SharedSecret; scopes = @($R.Scopes | ForEach-Object { ConvertFrom-IPNumber $_ })
    }
}

function Convert-NetshBytes {
    param([byte[]]$Bytes)
    if (-not $Bytes -or $Bytes.Length -eq 0) { return '' }
    try { (New-Object System.Text.UTF8Encoding($false, $true)).GetString($Bytes) }
    catch { (Get-OemEncoding).GetString($Bytes) }
}

# Liest die (noch wachsende) Ausgabedatei bis zum letzten vollständigen Zeilenende
function Read-NetshOutput {
    param([string]$Path, [switch]$Complete)
    if (-not (Test-Path -LiteralPath $Path)) { return '' }
    $fs = $null
    try {
        $fs = [System.IO.File]::Open($Path, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::ReadWrite)
        $ms = New-Object System.IO.MemoryStream
        $fs.CopyTo($ms)
        $b = $ms.ToArray()
    } catch { return '' } finally { if ($fs) { $fs.Dispose() } }
    if (-not $Complete) {
        $n = [Array]::LastIndexOf($b, [byte]10)
        if ($n -lt 0) { return '' }
        if ($n -lt $b.Length - 1) { $b = $b[0..$n] }
    }
    Convert-NetshBytes $b
}

function Get-NetshSegment {
    param([string]$Text, [int]$Index, [string]$Cmd)
    $m = [regex]::Match($Text, "##BEGIN$Index##\r?\n(?<o>[\s\S]*?)##RC$Index=(?<c>-?\d+)")
    if (-not $m.Success) { return $null }
    @{ cmd = $Cmd; code = [int]$m.Groups['c'].Value; out = @($m.Groups['o'].Value -split "\r?\n" | Where-Object { $_.Trim() }) }
}

# netsh-dhcp-Befehle gegen einen Server: ein unsichtbarer Prozess, ein netsh-Aufruf pro Zeile.
# Jeder fertige Befehl wird sofort als Fortschritt gemeldet.
function Invoke-NetshBatch {
    param([string]$Server, [string[]]$Lines, [int]$TimeoutSec = 0)
    if (-not $Lines -or $Lines.Count -eq 0) { return , @() }
    Initialize-DhcpRpc
    if ($TimeoutSec -le 0) { $TimeoutSec = 120 + 3 * $Lines.Count }
    $enc = Get-OemEncoding
    $id = [guid]::NewGuid().ToString('N')
    $tmp = [System.IO.Path]::GetTempPath()
    $bat = Join-Path $tmp "owsk_$id.cmd"
    $out = Join-Path $tmp "owsk_$id.txt"
    $netsh = "$env:SystemRoot\System32\netsh.exe"
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine('@echo off')
    for ($i = 0; $i -lt $Lines.Count; $i++) {
        [void]$sb.AppendLine(('echo ##BEGIN{0}##>>"{1}"' -f $i, $out))
        [void]$sb.AppendLine(('"{0}" dhcp server \\{1} {2} >>"{3}" 2>&1' -f $netsh, $Server, ($Lines[$i] -replace '%', '%%'), $out))
        [void]$sb.AppendLine(('echo ##RC{0}=%errorlevel%##>>"{1}"' -f $i, $out))
    }
    [System.IO.File]::WriteAllText($bat, $sb.ToString(), $enc)
    $next = 0
    $results = New-Object System.Collections.ArrayList
    try {
        $c = Get-RpcCredParts $Server
        $cmd = '"{0}" /d /c "{1}"' -f "$env:SystemRoot\System32\cmd.exe", $bat
        $h = [DsmRpc]::StartHidden($cmd, $c[0], $c[1], $c[2])
        try {
            $sw = [System.Diagnostics.Stopwatch]::StartNew()
            while ([DsmRpc]::WaitExit($h, 300) -eq -1) {
                if ($sw.Elapsed.TotalSeconds -gt $TimeoutSec) { [DsmRpc]::Kill($h); throw "@ERR:netsh_timeout:$Server|$TimeoutSec" }
                $live = Read-NetshOutput $out
                while ($next -lt $Lines.Count) {
                    $seg = Get-NetshSegment $live $next $Lines[$next]
                    if (-not $seg) { break }
                    [void]$results.Add($seg)
                    Send-Progress @{ i = $next; n = $Lines.Count; result = $seg }
                    $next++
                }
            }
        } finally { [DsmRpc]::CloseH($h) }
        $txt = Read-NetshOutput $out -Complete
    } finally {
        Remove-Item -LiteralPath $bat, $out -Force -ErrorAction SilentlyContinue
    }
    for ($k = $next; $k -lt $Lines.Count; $k++) {
        $seg = Get-NetshSegment $txt $k $Lines[$k]
        if (-not $seg) { $seg = @{ cmd = $Lines[$k]; code = -1; out = @() } }
        [void]$results.Add($seg)
        Send-Progress @{ i = $k; n = $Lines.Count; result = $seg }
    }
    , $results.ToArray()
}

# ---------------------------------------------------------------------------------------------------
# Befehle
# ---------------------------------------------------------------------------------------------------
$script:Handlers = @{
    hello = {
        param($A)
        @{ ps = $PSVersionTable.PSVersion.ToString(); edition = [string]$PSVersionTable.PSEdition
           dhcp = [bool](Get-Module -ListAvailable -Name DhcpServer); user = "$env:USERDOMAIN\$env:USERNAME"; computer = $env:COMPUTERNAME }
    }
    connect = {
        param($A)
        Import-Module DhcpServer -ErrorAction Stop
        $server = [string]$A.server
        if ($A.reuse) {
            # Partner: gespeicherte Anmeldedaten dieses Servers bzw. die des Primärservers
            $cred = if ($script:Creds.ContainsKey($server)) { $script:Creds[$server] } else { $script:Creds['*'] }
        } else {
            $cred = New-Cred ([string]$A.user) ([string]$A.password)
            # Partner: Anmeldedaten vorab merken - sie gelten auch für den RPC-Weg, falls WinRM scheitert
            if (-not $A.primary) { if ($cred) { $script:Creds[$server] = $cred } else { $script:Creds.Remove($server) } }
        }
        $s = Connect-Target -ComputerName $server -Credential $cred
        if ($script:Sessions[$server]) { Remove-CimSession -CimSession $script:Sessions[$server] -ErrorAction SilentlyContinue }
        $script:Sessions[$server] = $s
        if ($A.primary) { $script:Creds['*'] = $cred }
        @{ protocol = [string]$s.Protocol }
    }
    set_cred = {
        param($A)
        $server = [string]$A.server
        $cred = New-Cred ([string]$A.user) ([string]$A.password)
        if ($cred) { $script:Creds[$server] = $cred } else { $script:Creds.Remove($server) }
        $true
    }
    disconnect = {
        param($A)
        $names = if ($A -and $A.server) { @([string]$A.server) } else { @($script:Sessions.Keys) }
        foreach ($n in $names) {
            if ($script:Sessions[$n]) { Remove-CimSession -CimSession $script:Sessions[$n] -ErrorAction SilentlyContinue }
            $script:Sessions.Remove($n)
        }
        if (-not ($A -and $A.server)) { $script:Creds = @{} }
        $true
    }
    cim = {
        param($A)
        $name = [string]$A.name
        if ($name -notmatch '^(Get|Set|Add|Remove|Invoke)-DhcpServer\w*$') { throw "@ERR:bad_cmdlet:$name" }
        $p = ConvertTo-Hashtable $A.params
        $s = Get-Session ([string]$A.server)
        $res = @(& $name -CimSession $s @p -ErrorAction Stop)
        $items = New-Object System.Collections.ArrayList
        foreach ($r in $res) { if ($null -ne $r) { [void]$items.Add((ConvertTo-Plain $r)) } }
        @{ items = $items.ToArray() }
    }
    dhcp_in_dc = {
        param($A)
        Import-Module DhcpServer -ErrorAction Stop
        $items = New-Object System.Collections.ArrayList
        foreach ($r in @(Get-DhcpServerInDC -ErrorAction Stop)) { [void]$items.Add(@{ name = [string]$r.DnsName; ip = [string]$r.IPAddress }) }
        @{ items = $items.ToArray() }
    }
    resolve = {
        param($A)
        $n = [string]$A.name
        $ipObj = $null
        if ([System.Net.IPAddress]::TryParse($n.Trim(), [ref]$ipObj) -and $ipObj.AddressFamily -eq 'InterNetwork') { return $n.Trim() }
        $a = @([System.Net.Dns]::GetHostAddresses($n) | Where-Object { $_.AddressFamily -eq 'InterNetwork' })
        if (-not $a.Count) { throw "@ERR:resolve:$n" }
        $a[0].IPAddressToString
    }
    fo_api = {
        param($A)
        Initialize-DhcpRpc
        $server = [string]$A.server
        $c = Get-RpcCredParts $server
        switch ([string]$A.op) {
            'enum' {
                $list = New-Object System.Collections.ArrayList
                foreach ($r in @([DsmRpc]::EnumRelationships($server, $c[0], $c[1], $c[2]))) { [void]$list.Add((ConvertFrom-FoStruct $r)) }
                return @{ items = $list.ToArray() }
            }
            'create' { [DsmRpc]::CreateRelationship($server, (ConvertTo-FoStruct $A.rel), $c[0], $c[1], $c[2]) }
            'set' { [DsmRpc]::SetRelationship($server, [uint32]$A.flags, (ConvertTo-FoStruct $A.rel), $c[0], $c[1], $c[2]) }
            'delete' { [DsmRpc]::DeleteRelationship($server, [string]$A.name, $c[0], $c[1], $c[2]) }
            'add_scopes' { [DsmRpc]::AddScopes($server, (ConvertTo-FoStruct $A.rel), $c[0], $c[1], $c[2]) }
            'remove_scopes' { [DsmRpc]::RemoveScopes($server, (ConvertTo-FoStruct $A.rel), $c[0], $c[1], $c[2]) }
            default { throw "@ERR:bad_op:$($A.op)" }
        }
        $true
    }
    netsh = {
        param($A)
        @{ items = (Invoke-NetshBatch ([string]$A.server) ([string[]]@($A.lines)) ([int]$A.timeout)) }
    }
}

# ---------------------------------------------------------------------------------------------------
# Hauptschleife
# ---------------------------------------------------------------------------------------------------
Send-Line '@@OWR ' @{ id = 0; ok = $true; data = @{ ready = $true } }
while ($true) {
    $line = $OwIn.ReadLine()
    if ($null -eq $line) { break }
    if (-not $line.Trim()) { continue }
    $req = $null
    try { $req = ConvertFrom-Json -InputObject $line } catch { continue }
    $script:CurrentId = [int]$req.id
    if ([string]$req.cmd -eq 'exit') { break }
    try {
        $h = $script:Handlers[[string]$req.cmd]
        if (-not $h) { throw "@ERR:bad_cmd:$($req.cmd)" }
        $data = & $h $req.args
        Send-Line '@@OWR ' @{ id = $script:CurrentId; ok = $true; data = $data }
    } catch {
        Send-Line '@@OWR ' @{ id = $script:CurrentId; ok = $false; error = (Get-InnerMessage $_) }
    }
}
foreach ($s in @($script:Sessions.Values)) { Remove-CimSession -CimSession $s -ErrorAction SilentlyContinue }
