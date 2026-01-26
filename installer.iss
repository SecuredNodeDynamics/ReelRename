#define MyAppName "ReelRename"
#define MyAppVersion "1.1.2"
#define MyAppPublisher "ReelRename"
#define MyAppExeName "reelrename.exe"

[Setup]
AppId={{9738EC93-6E6E-4E6A-8BBF-57936C03EFF4}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=release
OutputBaseFilename=ReelRename-Setup-{#MyAppVersion}
Compression=lzma
SolidCompression=yes
WizardStyle=modern

; Use your ICO for installer + uninstaller icon
SetupIconFile=reelrename_app\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop icon"; GroupDescription: "Additional icons:"
Name: "startmenuicon"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Additional icons:"

[Files]
; Install everything from the PyInstaller onedir output
Source: "dist\reelrename\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
