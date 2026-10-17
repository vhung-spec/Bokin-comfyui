; Bokin Upscaler - Windows installer (Inno Setup 6).
; Build:  iscc /DAppVersion=0.2.0 installer\windows\bokin.iss   ->  dist\BokinUpscaler-Setup.exe
;
; The .exe carries the Bokin source. After copying it, Setup runs setup.ps1,
; which downloads ComfyUI, PyTorch and the chosen models into the same folder.

#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{6F1C9E52-4B7A-4E0B-9C1E-B0C1A5E2D7F3}
AppName=Bokin Upscaler
AppVersion={#AppVersion}
AppVerName=Bokin Upscaler {#AppVersion}
AppPublisher=Bokin
DefaultDirName={localappdata}\BokinUpscaler
DirExistsWarning=no
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=BokinUpscaler-Setup
SetupIconFile=..\assets\bokin.ico
UninstallDisplayIcon={app}\bokin.ico
UninstallDisplayName=Bokin Upscaler
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Messages]
WelcomeLabel2=Bộ cài sẽ cài Bokin Upscaler (phóng to ảnh kiểu Shakker) vào máy: ComfyUI, PyTorch, bộ node Bokin và model AI.%n%nCần Internet và khoảng 5-25 GB ổ đĩa trống tùy bộ model. Không cần quyền quản trị.%n%nNên dùng máy có GPU NVIDIA.

[Tasks]
Name: "sdxl"; Description: "SDXL + ControlNet Tile (~9 GB) - khuyên dùng, GPU NVIDIA 8 GB+"; GroupDescription: "Bộ model tải về:"; Flags: exclusive
Name: "sd15"; Description: "SD 1.5 + ControlNet Tile (~3 GB) - GPU 4 GB+"; GroupDescription: "Bộ model tải về:"; Flags: exclusive unchecked
Name: "fast"; Description: "Chỉ upscale nhanh (~150 MB) - máy yếu / không có GPU"; GroupDescription: "Bộ model tải về:"; Flags: exclusive unchecked
Name: "flux"; Description: "Flux.1 dev fp8 (~17 GB) - chi tiết nhất, GPU 12 GB+"; GroupDescription: "Bộ model tải về:"; Flags: exclusive unchecked
Name: "desktopicon"; Description: "Tạo shortcut trên Desktop"; GroupDescription: "Shortcut:"

[InstallDelete]
Type: filesandordirs; Name: "{app}\src"

[Files]
Source: "..\..\*"; DestDir: "{app}\src"; Excludes: ".git,.github,dist,tests,__pycache__,*.pyc,.pytest_cache,.ruff_cache"; Flags: recursesubdirs createallsubdirs ignoreversion
Source: "..\assets\bokin.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "Bokin Upscaler.bat"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Bokin Upscaler"; Filename: "{app}\Bokin Upscaler.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bokin.ico"
Name: "{userdesktop}\Bokin Upscaler"; Filename: "{app}\Bokin Upscaler.bat"; WorkingDir: "{app}"; IconFilename: "{app}\bokin.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Bokin Upscaler.bat"; Description: "Mở Bokin Upscaler"; Flags: postinstall nowait skipifsilent shellexec; Check: SetupSucceeded

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function ModelPreset(Param: String): String;
begin
  if WizardIsTaskSelected('sd15') then
    Result := 'sd15'
  else if WizardIsTaskSelected('fast') then
    Result := 'fast'
  else if WizardIsTaskSelected('flux') then
    Result := 'flux'
  else
    Result := 'sdxl';
end;

function PauseFlag(Param: String): String;
begin
  if WizardSilent then
    Result := ''
  else
    Result := '-PauseOnError';
end;

var
  SetupFailed: Boolean;

{ Download ComfyUI, PyTorch and the models with setup.ps1 and check that it worked. }
procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Params: String;
begin
  if CurStep = ssPostInstall then
  begin
    Params := '-NoProfile -ExecutionPolicy Bypass -File "' + ExpandConstant('{app}\src\installer\windows\setup.ps1') +
      '" -InstallDir "' + ExpandConstant('{app}') + '" -Models ' + ModelPreset('') + ' -NoShortcut -Yes ' + PauseFlag('');
    WizardForm.StatusLabel.Caption := 'Đang tải ComfyUI, PyTorch và model (10-40 phút, xem cửa sổ PowerShell)...';
    WizardForm.FilenameLabel.Caption := '';
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'), Params, ExpandConstant('{app}'),
                SW_SHOW, ewWaitUntilTerminated, ResultCode) or (ResultCode <> 0) then
    begin
      SetupFailed := True;
      SuppressibleMsgBox('Cài đặt chưa hoàn tất: bước tải ComfyUI / PyTorch / model bị lỗi (mã ' + IntToStr(ResultCode) + ').' + #13#10#13#10 +
        'Xem thông báo lỗi trong cửa sổ PowerShell và file install-log.txt trong thư mục cài, rồi chạy lại Setup ' +
        '(những phần đã tải xong sẽ được giữ lại).', mbError, MB_OK, IDOK);
    end;
  end;
end;

function SetupSucceeded: Boolean;
begin
  Result := not SetupFailed;
end;
