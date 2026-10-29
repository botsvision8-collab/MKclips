#define AppName "MKClips"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{B359A0B8-9B85-4E1C-873E-6C4CF2C1743B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MKClips
DefaultDirName={localappdata}\Programs\MKClips
DefaultGroupName=MKClips
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=MKClips-Setup-win64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\MKClips.exe

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[Files]
Source: "..\..\dist\MKClips\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MKClips"; Filename: "{app}\MKClips.exe"
Name: "{autodesktop}\MKClips"; Filename: "{app}\MKClips.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MKClips.exe"; Description: "Iniciar MKClips"; Flags: postinstall nowait skipifsilent
