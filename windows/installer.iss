; Vox installer (Inno Setup 6). Built by .github/workflows/build.yml.
; Per-user install, no admin rights needed.
#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

[Setup]
AppId={{6F3C2A1E-8B7D-4E2A-9C5B-5A1D0E7F4B21}
AppName=Vox
AppVersion={#MyAppVersion}
AppPublisher=Vox
DefaultDirName={localappdata}\Programs\Vox
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=VoxSetup
SetupIconFile=vox.ico
UninstallDisplayIcon={app}\Vox.exe
UninstallDisplayName=Vox
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "autostart"; Description: "Start Vox when I sign in to Windows"
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "dist\Vox\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\Vox"; Filename: "{app}\Vox.exe"
Name: "{userdesktop}\Vox"; Filename: "{app}\Vox.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Vox"; ValueData: """{app}\Vox.exe"""; Tasks: autostart; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Vox.exe"; Description: "Start Vox"; Flags: nowait postinstall

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/f /im Vox.exe"; Flags: runhidden; RunOnceId: "KillVox"

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Code: Integer;
begin
  if CurStep = ssInstall then
    Exec(ExpandConstant('{sys}\taskkill.exe'), '/f /im Vox.exe', '', SW_HIDE, ewWaitUntilTerminated, Code);
end;
