; PulseGuard installer.
;
; Admin rights (see PulseGuard-project-plan.md §12): installs per-user, no UAC
; elevation, matching the app's own unprivileged default (some protected
; processes will just be skipped in the process list rather than requiring
; the whole app to run elevated).
;
; Autostart (§12): opt-in via an unchecked installer checkbox, not on by
; default -- a monitoring tool auto-launching at boot is the kind of thing
; that should be an explicit choice.

#define MyAppName "PulseGuard"
#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppPublisher "Trukitro"
#define MyAppExeName "PulseGuard.exe"
#define MyAppURL "https://github.com/Trukitro/PulseGuard"

[Setup]
AppId={{B6C1A6F0-6F2A-4B0E-9C7B-6E9F6E7B6F30}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=PulseGuardSetup
SetupIconFile=..\assets\icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
Name: "autostart"; Description: "Start PulseGuard automatically when Windows starts"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
Source: "..\backend\dist\PulseGuard\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
; Fetched by the release workflow (.github/workflows/release.yml) from Microsoft's
; official evergreen WebView2 bootstrapper before this script is compiled -- not
; committed to the repo. Setup still works if it's absent (see Check: below).
Source: "redist\MicrosoftEdgeWebView2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist

[Icons]
; IconFilename points at the exe itself (which PyInstaller already embeds icon.ico
; into) rather than the assets/ copy -- that copy actually lands at
; {app}\_internal\assets\icon.ico under PyInstaller's onedir layout, and chasing that
; internal path is one PyInstaller version bump away from silently breaking again.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; IconFilename: "{app}\{#MyAppExeName}"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "PulseGuard"; ValueData: """{app}\{#MyAppExeName}"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{tmp}\MicrosoftEdgeWebView2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing Microsoft WebView2 Runtime..."; Check: WebView2RuntimeMissing and FileExists(ExpandConstant('{tmp}\MicrosoftEdgeWebView2Setup.exe'))
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
function WebView2RuntimeMissing(): Boolean;
var
  Version: String;
begin
  { Same runtime GUID Microsoft documents for detecting an existing WebView2
    Evergreen install; checked under both the WOW6432Node and native paths
    since installers can register under either depending on OS/runtime bitness. }
  Result := not (
    RegQueryStringValue(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
    or RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
  );
end;
