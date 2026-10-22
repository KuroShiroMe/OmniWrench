; Installationsprogramm für Windows (Inno Setup 6, https://jrsoftware.org/isinfo.php).
; Nicht direkt kompilieren, sondern über scripts/build_installer.py: das Skript übergibt Version,
; Programmordner (dist\OmniWrench aus scripts/build_exe.py), Symbol und Installationsmarker.
;
; Installiert nach C:\Program Files\DarkMatter\OmniWrench (UAC), legt Startmenü-Eintrag, optional
; Desktop-Verknüpfung und den Eintrag unter "Apps & Features" an. Benutzerdaten (Einstellungen,
; Tresor, Tools) liegen im Benutzerprofil und bleiben bei Updates und Deinstallation erhalten.
;
; Stille Installation (Softwareverteilung, Intune, SCCM):
;   OmniWrench-X.Y.Z-win64-setup.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART [/TASKS="desktopicon"]
; Stille Deinstallation:
;   "C:\Program Files\DarkMatter\OmniWrench\unins000.exe" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART
; Selbst-Update aus OmniWrench (core/app_updater.py): /SILENT /SUPPRESSMSGBOXES /NORESTART /SP- /restart=1

#ifndef AppVersion
  #error AppVersion fehlt - scripts/build_installer.py verwenden
#endif
#ifndef MarkerFile
  #error MarkerFile fehlt - scripts/build_installer.py verwenden
#endif
#ifndef NumericVersion
  #define NumericVersion AppVersion
#endif
#ifndef SourceDir
  #define SourceDir "..\..\dist\OmniWrench"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\dist"
#endif

#define AppName "OmniWrench"
#define AppPublisher "DarkMatter"
#define AppExe "OmniWrench.exe"
#define AppUrl "https://github.com/KuroShiroMe/OmniWrench"
; muss zu APP_MUTEX in omniwrench/__init__.py passen
#define AppMutexName "DarkMatter.OmniWrench"

[Setup]
; AppId nie ändern: daran erkennt Windows Updates einer bestehenden Installation
AppId={{6E7C1F4B-3D2A-4B8E-9A51-0C7D2E9F4A63}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppUrl}/issues
AppUpdatesURL={#AppUrl}/releases
VersionInfoVersion={#NumericVersion}
VersionInfoCompany={#AppPublisher}
VersionInfoProductName={#AppName}
DefaultDirName={autopf}\{#AppPublisher}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename={#AppName}-{#AppVersion}-win64-setup
#ifdef IconFile
SetupIconFile={#IconFile}
#endif
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
LicenseFile={#SourceDir}\LICENSE
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
; Laufendes OmniWrench erkennt der [Code]-Teil über den Mutex; der Restart Manager ist nur Rückfallebene
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=auto
LanguageDetectionMethod=uilanguage

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "de"; MessagesFile: "compiler:Languages\German.isl"
#if FileExists(CompilerPath + "Languages\French.isl")
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"
#endif
#if FileExists(CompilerPath + "Languages\Spanish.isl")
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Italian.isl")
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"
#endif
#if FileExists(CompilerPath + "Languages\Dutch.isl")
Name: "nl"; MessagesFile: "compiler:Languages\Dutch.isl"
#endif
#if FileExists(CompilerPath + "Languages\Polish.isl")
Name: "pl"; MessagesFile: "compiler:Languages\Polish.isl"
#endif
#if FileExists(CompilerPath + "Languages\BrazilianPortuguese.isl")
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
#endif
#if FileExists(CompilerPath + "Languages\Czech.isl")
Name: "cs"; MessagesFile: "compiler:Languages\Czech.isl"
#endif
#if FileExists(CompilerPath + "Languages\Swedish.isl")
Name: "sv"; MessagesFile: "compiler:Languages\Swedish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Turkish.isl")
Name: "tr"; MessagesFile: "compiler:Languages\Turkish.isl"
#endif
#if FileExists(CompilerPath + "Languages\Ukrainian.isl")
Name: "uk"; MessagesFile: "compiler:Languages\Ukrainian.isl"
#endif

[CustomMessages]
; ohne Sprachpräfix = Englisch für alle Sprachen, "de." überschreibt für Deutsch
AppRunning=OmniWrench is still running. Close OmniWrench and click "Retry", or "Cancel" to quit.
AppRunningSilent=OmniWrench did not close in time.
de.AppRunning=OmniWrench wird noch ausgeführt. OmniWrench schließen und „Wiederholen“ wählen oder „Abbrechen“, um das Setup zu beenden.
de.AppRunningSilent=OmniWrench wurde nicht rechtzeitig beendet.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Bei Updates alte Programmbibliotheken entfernen, damit keine veralteten Module liegen bleiben
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#MarkerFile}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; AppUserModelID: "{#AppName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
; Selbst-Update: nach stiller Installation wieder starten, als angemeldeter Benutzer (nicht als Admin)
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: RestartRequested

[Code]
function RestartRequested: Boolean;
begin
  Result := ExpandConstant('{param:restart|0}') = '1';
end;

// Wartet bis zu Sekunden, bis OmniWrench beendet ist (Selbst-Update: das Programm schließt sich gerade)
function WaitForApp(Seconds: Integer): Boolean;
var
  I: Integer;
begin
  I := 0;
  while CheckForMutexes('{#AppMutexName}') and (I < Seconds * 2) do
  begin
    Sleep(500);
    I := I + 1;
  end;
  Result := not CheckForMutexes('{#AppMutexName}');
end;

function AppClosed(Silent: Boolean): Boolean;
begin
  if Silent then
  begin
    Result := WaitForApp(60);
    if not Result then
      Log(CustomMessage('AppRunningSilent'));
    exit;
  end;
  Result := True;
  while CheckForMutexes('{#AppMutexName}') do
    if MsgBox(CustomMessage('AppRunning'), mbError, MB_RETRYCANCEL) <> IDRETRY then
    begin
      Result := False;
      exit;
    end;
end;

function InitializeSetup: Boolean;
begin
  Result := AppClosed(WizardSilent);
end;

function InitializeUninstall: Boolean;
begin
  Result := AppClosed(UninstallSilent);
end;
