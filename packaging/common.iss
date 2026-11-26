#ifndef AppVersion
#define AppVersion "1.6.0"
#endif
[Setup]
AppId={{2FC7A234-486A-46EC-9E90-3A9F46AE3246}
AppName=试验记录智能归档工具
AppVersion={#AppVersion}
DefaultDirName={sd}\TrialRecords
DefaultGroupName=试验记录智能归档工具
PrivilegesRequired=lowest
OutputDir={#OutputDir}
#if OnlineMode
OutputBaseFilename=TrialRecords-Online-Setup-{#AppVersion}
#else
OutputBaseFilename=TrialRecords-Offline-Setup-{#AppVersion}
#endif
Compression=lzma2/fast
SolidCompression=yes
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
MinVersion=10.0.17763
CloseApplications=yes
[Files]
#if !OnlineMode
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
#endif
[Icons]
Name: "{group}\试验记录智能归档工具"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\desktop_app.py"""; WorkingDir: "{app}"
Name: "{autodesktop}\试验记录智能归档工具"; Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\desktop_app.py"""; WorkingDir: "{app}"
[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: """{app}\desktop_app.py"""; Description: "启动试验记录智能归档工具"; Flags: nowait postinstall skipifsilent
#if OnlineMode
[UninstallDelete]
Type: filesandordirs; Name: "{app}\runtime"
Type: filesandordirs; Name: "{app}\soft\paddleocr_models"
Type: files; Name: "{app}\desktop_app.py"
Type: files; Name: "{app}\outline_manager.py"
Type: files; Name: "{app}\outline_manager_backend.py"
Type: files; Name: "{app}\split_experiments.py"
Type: files; Name: "{app}\outline_catalog.py"
Type: files; Name: "{app}\vehicle_outlines.py"
Type: files; Name: "{app}\full_outline_pdf.py"
Type: files; Name: "{app}\demo_vehicle_data.py"
Type: files; Name: "{app}\Start.bat"
Type: files; Name: "{app}\启动软件.bat"
#endif
[Code]
#if OnlineMode
var DownloadPage: TDownloadWizardPage;
procedure InitializeWizard;
begin
  DownloadPage := CreateDownloadPage('Download application', 'Downloading runtime and OCR models...', nil);
end;
function PrepareToInstall(var NeedsRestart: Boolean): String;
var Code: Integer; Expanded, SourcePath, Args: String;
begin
  Result := '';
  try
    DownloadPage.Clear;
    DownloadPage.Add('{#PortableURL}', 'portable.zip', '{#PortableSHA256}');
    DownloadPage.Show;
    try DownloadPage.Download; finally DownloadPage.Hide; end;
    Expanded := ExpandConstant('{tmp}\expanded');
    ForceDirectories(Expanded);
    Args := '-xf "' + ExpandConstant('{tmp}\portable.zip') + '" -C "' + Expanded + '"';
    if not Exec(ExpandConstant('{sys}\tar.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then begin
      Result := 'Unable to extract the download. Please use the offline installer.'; Exit;
    end;
    if Code <> 0 then begin Result := 'Downloaded archive could not be extracted.'; Exit; end;
    SourcePath := Expanded + '\TrialRecords';
    if not FileExists(SourcePath + '\runtime\python.exe') then begin Result := 'Downloaded runtime is incomplete.'; Exit; end;
    if not ForceDirectories(WizardDirValue) then begin Result := 'Cannot create installation folder.'; Exit; end;
    Args := '"' + SourcePath + '\*" "' + WizardDirValue + '" /E /I /Y /Q';
    if not Exec(ExpandConstant('{sys}\xcopy.exe'), Args, '', SW_HIDE, ewWaitUntilTerminated, Code) then begin
      Result := 'Cannot copy application files.'; Exit;
    end;
    if Code <> 0 then Result := 'Cannot finish copying files. Close the application and retry.';
  except Result := GetExceptionMessage; end;
end;
#endif
function NextButtonClick(CurPageID: Integer): Boolean;
var I: Integer; P: String;
begin
  Result := True;
  if CurPageID = wpSelectDir then begin
    P := WizardDirValue;
    for I := 1 to Length(P) do
      if Ord(P[I]) > 127 then begin
        MsgBox('Please choose an English/ASCII path, for example C:\TrialRecords.', mbError, MB_OK);
        Result := False; Exit;
      end;
  end;
end;
