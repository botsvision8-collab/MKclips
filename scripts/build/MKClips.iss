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
Source: "MicrosoftEdgeWebView2Setup.exe"; Flags: dontcopy
Source: "install_ffmpeg.ps1"; Flags: dontcopy
Source: "..\..\third_party\licenses\GPL-3.0.txt"; Flags: dontcopy
Source: "..\..\dist\MKClips\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\MKClips"; Filename: "{app}\MKClips.exe"
Name: "{autodesktop}\MKClips"; Filename: "{app}\MKClips.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MKClips.exe"; Description: "Iniciar MKClips"; Flags: postinstall nowait skipifsilent

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  TempDir, BinDir, PowerShell, Params: String;
begin
  Result := '';
  NeedsRestart := False;
  ExtractTemporaryFile('MicrosoftEdgeWebView2Setup.exe');
  ExtractTemporaryFile('install_ffmpeg.ps1');
  ExtractTemporaryFile('GPL-3.0.txt');

  TempDir := ExpandConstant('{tmp}\MKClipsPrerequisites');
  BinDir := TempDir + '\bin';
  if not ForceDirectories(BinDir) then begin
    Result := 'No se pudo preparar la carpeta temporal para los componentes.';
    exit;
  end;

  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2Setup.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    Result := 'No se pudo iniciar el instalador de WebView2. Comprueba que Windows permite instalar el runtime.';
    exit;
  end;
  if (ResultCode <> 0) and (ResultCode <> 3010) and (ResultCode <> 1641) then begin
    Result := 'No se pudo instalar WebView2 Runtime. Comprueba tu conexion a Internet y vuelve a intentarlo.';
    exit;
  end;

  WizardForm.StatusLabel.Caption := 'Descargando FFmpeg 9.0.2 (aprox. 109 MB)...';
  WizardForm.Update;
  PowerShell := ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe');
  Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{tmp}\install_ffmpeg.ps1') + '" -InstallDir "' + BinDir + '"';
  if not Exec(PowerShell, Params, ExpandConstant('{tmp}'), SW_HIDE, ewWaitUntilTerminated, ResultCode) then begin
    Result := 'No se pudo iniciar la descarga de FFmpeg. Comprueba que Windows PowerShell esta disponible.';
    exit;
  end;
  if ResultCode <> 0 then begin
    Result := 'No se pudo descargar FFmpeg. Comprueba tu conexion a Internet y vuelve a intentarlo.';
    exit;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  TempDir, BinDir: String;
begin
  if CurStep = ssPostInstall then begin
    TempDir := ExpandConstant('{tmp}\MKClipsPrerequisites\bin');
    BinDir := ExpandConstant('{app}\bin');
    if not ForceDirectories(BinDir) then
      RaiseException('No se pudo crear la carpeta de FFmpeg.');
    if not FileCopy(TempDir + '\ffmpeg.exe', BinDir + '\ffmpeg.exe', False) then
      RaiseException('No se pudo instalar ffmpeg.exe.');
    if not FileCopy(TempDir + '\ffprobe.exe', BinDir + '\ffprobe.exe', False) then
      RaiseException('No se pudo instalar ffprobe.exe.');
    if not FileCopy(TempDir + '\FFmpeg-THIRD-PARTY.txt', BinDir + '\FFmpeg-THIRD-PARTY.txt', False) then
      RaiseException('No se pudo instalar el aviso de licencia de FFmpeg.');
    if not FileCopy(ExpandConstant('{tmp}\GPL-3.0.txt'), BinDir + '\GPL-3.0.txt', False) then
      RaiseException('No se pudo instalar la licencia de FFmpeg.');
    if FileExists(TempDir + '\FFmpeg-BUILD-README.txt') then
      FileCopy(TempDir + '\FFmpeg-BUILD-README.txt', BinDir + '\FFmpeg-BUILD-README.txt', False);
  end;
end;

[UninstallDelete]
Type: filesandordirs; Name: "{app}\bin"
