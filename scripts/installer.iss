; FIDUX - Inno Setup Installer
; Download Inno Setup: https://jrsoftware.org/isdl.php

#ifndef MyAppVersion
  #define MyAppVersion "2.3.0"
#endif

#define MyAppName "FIDUX"
#define MyAppPublisher "FIDUX"
#define MyAppExeName "FIDUX.exe"

[Setup]
AppId={{9F3B2D7E-5C81-4A6B-9E2D-6A81C4F0B3D5}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=..\dist\installer
OutputBaseFilename=FIDUX_Setup_{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\{#MyAppExeName}
PrivilegesRequired=admin
AppMutex=CAM350ReviewMutex
CloseApplications=yes
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\FIDUX.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\config\config.json"; DestDir: "{app}\config"; Flags: ignoreversion onlyifdoesntexist

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: postinstall nowait skipifsilent

[UninstallRun]
Filename: "{cmd}"; Parameters: "/c del ""{app}\config\config.json"" /q"; Flags: runhidden
