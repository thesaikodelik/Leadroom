#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif

#define AppName "Leadroom"
#define AppPublisher "Leadroom contributors"
#define AppUrl "https://github.com/thesaikodelik/Leadroom"
#define AppProjectUrl "https://github.com/thesaikodelik/Leadroom"
#define AppExeName "Leadroom.exe"

[Setup]
AppId={{05D64A66-2D13-4E1E-8A20-981D2C802A04}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppUrl}
AppSupportURL={#AppProjectUrl}/issues
AppUpdatesURL={#AppProjectUrl}/releases
DefaultDirName={localappdata}\Programs\Leadroom
DefaultGroupName=Leadroom
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
CloseApplicationsFilter=Leadroom.exe
AllowCancelDuringInstall=yes
OutputDir=..\dist
OutputBaseFilename=Leadroom-Setup
; The setup icon is the app icon with a download badge, so the installer is easy to
; tell apart from the installed Leadroom.exe.
SetupIconFile=..\assets\leadroom-setup.ico
WizardImageFile=images\wizard-large-100.bmp,images\wizard-large-125.bmp,images\wizard-large-150.bmp,images\wizard-large-200.bmp
WizardSmallImageFile=images\wizard-small-100.bmp,images\wizard-small-125.bmp,images\wizard-small-150.bmp,images\wizard-small-200.bmp
UninstallDisplayIcon={app}\Leadroom.exe
LicenseFile=..\LICENSE
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardSizePercent=110
DisableWelcomePage=no
ShowLanguageDialog=no
SetupLogging=yes
VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription=Leadroom Windows Installer
VersionInfoProductName={#AppName}
VersionInfoProductVersion={#AppVersion}

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
; These small helpers are extracted before file installation so prerequisite
; downloads can be cancelled before Setup commits any application files.
Source: "..\scripts\install-bootstrap.ps1"; Flags: dontcopy noencryption
Source: "..\scripts\setup-local-data.ps1"; Flags: dontcopy noencryption
Source: "..\scripts\import-osm.ps1"; Flags: dontcopy noencryption
Source: "..\scripts\setup-local-updates.ps1"; Flags: dontcopy noencryption
Source: "..\infra\osm\leadroom.lua"; Flags: dontcopy noencryption
Source: "..\infra\osm\post-import.sql"; Flags: dontcopy noencryption
Source: "..\infra\osm\leadroom-osm-update.sh"; Flags: dontcopy noencryption
Source: "..\infra\osm\leadroom-osm-update.service"; Flags: dontcopy noencryption
Source: "..\infra\osm\leadroom-osm-update.timer"; Flags: dontcopy noencryption
Source: "..\dist\Leadroom.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\leadroom-icon.ico"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\THIRD_PARTY_NOTICES.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\build\THIRD_PARTY_LICENSES.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\licenses\GPL-3.0.txt"; DestDir: "{app}\licenses"; Flags: ignoreversion
Source: "..\docs\DEPENDENCY_LICENSES.md"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\scripts\install-bootstrap.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\clean-install-state.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\setup-local-data.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\import-osm.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\setup-local-updates.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\infra\osm\*"; DestDir: "{app}\infra\osm"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Leadroom"; Filename: "{app}\Leadroom.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\leadroom-icon.ico"
Name: "{autodesktop}\Leadroom"; Filename: "{app}\Leadroom.exe"; WorkingDir: "{app}"; IconFilename: "{app}\assets\leadroom-icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\Leadroom.exe"; Description: "Launch Leadroom"; Flags: nowait postinstall skipifsilent
; The in-app updater runs Setup quietly with /RELAUNCH=1 after quitting; this opens the new
; version once the files are in place. Other quiet installs (scripts, tests) are not affected.
Filename: "{app}\Leadroom.exe"; Flags: nowait; Check: RelaunchRequested

[Code]
type
  TWindowsMessage = record
    WindowHandle: LongWord;
    MessageId: LongWord;
    WParam: LongWord;
    LParam: Longint;
    MessageTime: LongWord;
    PointX: Longint;
    PointY: Longint;
  end;

function PeekMessage(var Msg: TWindowsMessage; Wnd: LongWord;
  FilterMin, FilterMax, RemoveFlag: LongWord): Boolean;
  external 'PeekMessageW@user32.dll stdcall';
function TranslateMessage(var Msg: TWindowsMessage): Boolean;
  external 'TranslateMessage@user32.dll stdcall';
function DispatchMessage(var Msg: TWindowsMessage): Longint;
  external 'DispatchMessageW@user32.dll stdcall';
function OpenProcess(DesiredAccess: LongWord; InheritHandle: Boolean;
  ProcessId: LongWord): LongWord;
  external 'OpenProcess@kernel32.dll stdcall';
function GetExitCodeProcess(ProcessHandle: LongWord;
  var ExitCode: LongWord): Boolean;
  external 'GetExitCodeProcess@kernel32.dll stdcall';
function CloseHandle(Handle: LongWord): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';
function CreateFileW(FileName: String; DesiredAccess, ShareMode, SecurityAttributes,
  CreationDisposition, FlagsAndAttributes, TemplateFile: LongWord): LongWord;
  external 'CreateFileW@kernel32.dll stdcall';

var
  InstallFinished: Boolean;
  ModePage: TInputOptionWizardPage;
  StoragePage: TInputDirWizardPage;
  DependencyPage: TInputOptionWizardPage;
  BootstrapProgress: TOutputProgressWizardPage;
  BootstrapStatusPath: String;
  BootstrapCompletionPath: String;
  BootstrapCancelPath: String;
  BootstrapProcessPath: String;
  BootstrapRunning: Boolean;
  BootstrapCancelRequested: Boolean;
  BootstrapCancelButton: TNewButton;

procedure BootstrapCancelClick(Sender: TObject); forward;

procedure PumpPendingMessages;
var
  Msg: TWindowsMessage;
begin
  while PeekMessage(Msg, 0, 0, 0, 1) do begin
    TranslateMessage(Msg);
    DispatchMessage(Msg);
  end;
end;

function ParamValue(const Name, Default: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|' + Default + '}');
end;

function ParamEnabled(const Name: String; Default: Boolean): Boolean;
var
  Value: String;
begin
  if Default then Value := '1' else Value := '0';
  Value := Lowercase(ParamValue(Name, Value));
  Result := (Value = '1') or (Value = 'true') or (Value = 'yes');
end;

function RelaunchRequested: Boolean;
begin
  Result := ParamEnabled('RELAUNCH', False);
end;

const
  UninstallKeyRoot = 'Software\Microsoft\Windows\CurrentVersion\Uninstall';

{ Earlier Leadroom builds were registered under a different AppId, so Windows treats them
  as a separate program and an install of this one would sit beside them. Any other
  Inno Setup entry whose name starts with "Leadroom" is removed quietly before the new
  files are copied. Workspace data, models and the map index live outside the program
  folder, and a quiet uninstall keeps them (its keep-data question defaults to Yes). }
procedure RemoveEarlierInstallsUnder(RootKey: Integer; const RootName: String);
var
  Names: TArrayOfString;
  I, ResultCode, Waited: Integer;
  OwnKey, Key, DisplayName, Uninstaller: String;
  Started: Boolean;
begin
  if not RegGetSubkeyNames(RootKey, UninstallKeyRoot, Names) then Exit;
  OwnKey := ExpandConstant('{#SetupSetting("AppId")}') + '_is1';
  for I := 0 to GetArrayLength(Names) - 1 do begin
    if CompareText(Names[I], OwnKey) = 0 then Continue;
    if CompareText(Copy(Names[I], Length(Names[I]) - 3, 4), '_is1') <> 0 then Continue;
    Key := UninstallKeyRoot + '\' + Names[I];
    if not RegQueryStringValue(RootKey, Key, 'DisplayName', DisplayName) then Continue;
    if CompareText(Copy(DisplayName, 1, 8), 'Leadroom') <> 0 then Continue;
    if not RegQueryStringValue(RootKey, Key, 'UninstallString', Uninstaller) then Continue;
    Uninstaller := RemoveQuotes(Uninstaller);
    if not FileExists(Uninstaller) then begin
      Log('Skipping an earlier Leadroom entry without its uninstaller: ' + RootName + '\' + Names[I]);
      Continue;
    end;
    Log('Removing an earlier Leadroom installation: ' + DisplayName + ' (' + RootName + '\' + Names[I] + ')');
    if RootKey = HKEY_CURRENT_USER then
      Started := Exec(Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
        SW_HIDE, ewWaitUntilTerminated, ResultCode)
    else
      { A machine-wide install needs administrator rights to remove; Windows asks. }
      Started := ShellExec('', Uninstaller, '/VERYSILENT /SUPPRESSMSGBOXES /NORESTART', '',
        SW_SHOWNORMAL, ewWaitUntilTerminated, ResultCode);
    if not Started then begin
      Log('The earlier uninstaller could not be started: ' + SysErrorMessage(ResultCode));
      Continue;
    end;
    { The uninstaller finishes in a copy of itself; wait for its entry to disappear. }
    Waited := 0;
    while RegKeyExists(RootKey, Key) and (Waited < 600) do begin
      PumpPendingMessages;
      Sleep(100);
      Waited := Waited + 1;
    end;
    if RegKeyExists(RootKey, Key) then
      Log('The earlier installation is still registered after its uninstaller ran.')
    else
      Log('The earlier installation was removed.');
  end;
end;

procedure RemoveEarlierInstalls;
begin
  RemoveEarlierInstallsUnder(HKEY_CURRENT_USER, 'HKCU');
  if IsWin64 then begin
    RemoveEarlierInstallsUnder(HKLM64, 'HKLM64');
    RemoveEarlierInstallsUnder(HKLM32, 'HKLM32');
  end else
    RemoveEarlierInstallsUnder(HKEY_LOCAL_MACHINE, 'HKLM');
end;

function IsAbsoluteWindowsPath(const Value: String): Boolean;
begin
  Result := ((Length(Value) >= 3) and (Value[2] = ':') and ((Value[3] = '\') or (Value[3] = '/'))) or
    (Copy(Value, 1, 2) = '\\');
end;

function PowerShellQuote(const Value: String): String;
begin
  Result := Value;
  StringChangeEx(Result, '"', '""', True);
  Result := '"' + Result + '"';
end;

function IsProcessRunning(ProcessId: Integer): Boolean;
var
  ProcessHandle, ExitCode: LongWord;
begin
  Result := False;
  ProcessHandle := OpenProcess($1000, False, ProcessId);
  if ProcessHandle = 0 then Exit;
  try
    if GetExitCodeProcess(ProcessHandle, ExitCode) then
      Result := ExitCode = 259;
  finally
    CloseHandle(ProcessHandle);
  end;
end;

function OllamaAlreadyInstalled: Boolean;
begin
  Result := FileExists(ExpandConstant('{localappdata}\Programs\Ollama\ollama.exe')) or
    FileExists(ExpandConstant('{commonpf64}\Ollama\ollama.exe'));
end;

procedure ApplyDependencySelection;
var
  ModelAvailable: Boolean;
begin
  { The model can only be downloaded when Ollama exists or will be installed. }
  ModelAvailable := OllamaAlreadyInstalled or DependencyPage.Values[1];
  DependencyPage.CheckListBox.ItemEnabled[2] := ModelAvailable;
  if not ModelAvailable then DependencyPage.Values[2] := False;
end;

procedure DependencyClickCheck(Sender: TObject);
begin
  ApplyDependencySelection;
end;

procedure ApplyModeSelection;
var
  FullLocal: Boolean;
begin
  FullLocal := ModePage.SelectedValueIndex = 1;
  DependencyPage.CheckListBox.ItemEnabled[3] := FullLocal;
  if not FullLocal then DependencyPage.Values[3] := False;
  if FullLocal then
    DependencyPage.SubCaptionLabel.Caption :=
      'Full Local can download roughly 2 GB and use 25-40 GB after import. It requires WSL2, Ubuntu, PostgreSQL, and PostGIS.'
  else
    DependencyPage.SubCaptionLabel.Caption :=
      'Recommended components are downloaded only with your approval. Existing installations are reused.';
end;

procedure InitializeWizard;
var
  DefaultData, DefaultDownloads, RequestedMode: String;
begin
  DefaultData := ExpandConstant('{localappdata}\Leadroom');
  DefaultDownloads := ExpandConstant('{localappdata}\Leadroom\downloads');
  RequestedMode := Lowercase(ParamValue('INSTALLMODE', 'standard'));

  ModePage := CreateInputOptionPage(wpSelectDir,
    'Choose the Leadroom experience',
    'Start lightweight or prepare the full local discovery stack.',
    'Standard is recommended. Full Local is intended for powerful Windows computers with plenty of disk space.',
    True, False);
  ModePage.Add('Standard - web discovery and local AI enrichment');
  ModePage.Add('Full Local - add private OpenStreetMap discovery');
  ModePage.SelectedValueIndex := 0;
  if RequestedMode = 'full' then ModePage.SelectedValueIndex := 1;

  StoragePage := CreateInputDirPage(ModePage.ID,
    'Choose where Leadroom stores data',
    'Keep the application small and place workspace data or large downloads on any drive.',
    'The first folder holds the SQLite workspace. The second holds models, browser files, cache, and optional map data.',
    False, 'New Folder');
  StoragePage.Add('Workspace data:');
  StoragePage.Add('Large downloads:');
  StoragePage.Values[0] := ParamValue('DATAROOT', DefaultData);
  StoragePage.Values[1] := ParamValue('DOWNLOADSROOT', DefaultDownloads);

  DependencyPage := CreateInputOptionPage(StoragePage.ID,
    'Prepare this computer',
    'Choose the components Leadroom may download.',
    'Recommended components are downloaded only with your approval. Existing installations are reused.',
    False, False);
  DependencyPage.Add('Install Microsoft Edge WebView2 Runtime if missing');
  DependencyPage.Add('Install Ollama if missing');
  DependencyPage.Add('Download the recommended llama3.2:3b model');
  DependencyPage.Add('Download and prepare the Full Local OpenStreetMap stack');
  DependencyPage.Values[0] := ParamEnabled('INSTALL_WEBVIEW', True);
  DependencyPage.Values[1] := ParamEnabled('INSTALL_OLLAMA', True);
  DependencyPage.Values[2] := ParamEnabled('DOWNLOAD_MODEL', True);
  DependencyPage.Values[3] := ParamEnabled('SETUP_LOCAL_DATA', False);
  DependencyPage.CheckListBox.OnClickCheck := @DependencyClickCheck;
  ApplyModeSelection;
  ApplyDependencySelection;

  BootstrapProgress := CreateOutputProgressPage(
    'Preparing Leadroom',
    'Progress for each selected component appears below.');

  BootstrapCancelButton := TNewButton.Create(WizardForm);
  BootstrapCancelButton.Parent := WizardForm;
  BootstrapCancelButton.Caption := 'Cancel setup';
  BootstrapCancelButton.Cancel := True;
  BootstrapCancelButton.Left := WizardForm.CancelButton.Left;
  BootstrapCancelButton.Top := WizardForm.CancelButton.Top;
  BootstrapCancelButton.Width := WizardForm.CancelButton.Width;
  BootstrapCancelButton.Height := WizardForm.CancelButton.Height;
  BootstrapCancelButton.Anchors := [akRight, akBottom];
  BootstrapCancelButton.OnClick := @BootstrapCancelClick;
  BootstrapCancelButton.Visible := False;
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = ModePage.ID then ApplyModeSelection;
  if CurPageID = StoragePage.ID then begin
    if not IsAbsoluteWindowsPath(StoragePage.Values[0]) then begin
      MsgBox('Choose an absolute workspace folder, such as D:\LeadroomData\workspace.', mbError, MB_OK);
      Result := False;
    end else if not IsAbsoluteWindowsPath(StoragePage.Values[1]) then begin
      MsgBox('Choose an absolute downloads folder, such as D:\LeadroomData\downloads.', mbError, MB_OK);
      Result := False;
    end;
  end;
end;

function BootstrapArguments: String;
var
  Mode: String;
begin
  if ModePage.SelectedValueIndex = 1 then Mode := 'FullLocal' else Mode := 'Standard';
  Result := '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
    PowerShellQuote(ExpandConstant('{tmp}\install-bootstrap.ps1')) +
    ' -Mode ' + Mode +
    ' -InstallRoot ' + PowerShellQuote(ExpandConstant('{app}')) +
    ' -HelperRoot ' + PowerShellQuote(ExpandConstant('{tmp}')) +
    ' -ResourceRoot ' + PowerShellQuote(ExpandConstant('{tmp}')) +
    ' -DataRoot ' + PowerShellQuote(StoragePage.Values[0]) +
    ' -DownloadsRoot ' + PowerShellQuote(StoragePage.Values[1]) +
    ' -Model ' + PowerShellQuote(ParamValue('MODEL', 'llama3.2:3b')) +
    ' -StatusPath ' + PowerShellQuote(BootstrapStatusPath) +
    ' -CompletionPath ' + PowerShellQuote(BootstrapCompletionPath) +
    ' -CancelPath ' + PowerShellQuote(BootstrapCancelPath) +
    ' -ProcessPath ' + PowerShellQuote(BootstrapProcessPath);
  if DependencyPage.Values[0] then Result := Result + ' -InstallWebView';
  if DependencyPage.Values[1] then Result := Result + ' -InstallOllama';
  if DependencyPage.Values[2] then Result := Result + ' -DownloadModel';
  if DependencyPage.Values[3] then Result := Result + ' -SetupLocalData';
  if ParamEnabled('FORCE_STORAGE', False) then Result := Result + ' -ForceStorage';
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if not BootstrapRunning then begin
    if BootstrapCancelRequested then Confirm := False;
    Exit;
  end;
  if SaveStringToFile(BootstrapCancelPath, 'cancel', False) then begin
    BootstrapCancelRequested := True;
    BootstrapProgress.SetText('Cancelling setup',
      'Stopping the current operation safely');
    WizardForm.CancelButton.Enabled := False;
  end;
  Confirm := False;
end;

procedure BootstrapCancelClick(Sender: TObject);
begin
  if not BootstrapRunning then Exit;
  if not SaveStringToFile(BootstrapCancelPath, 'cancel', False) then begin
    MsgBox('Setup could not signal the current download to stop.', mbError, MB_OK);
    Exit;
  end;
  BootstrapCancelRequested := True;
  BootstrapCancelButton.Enabled := False;
  BootstrapProgress.SetText('Cancelling setup',
    'Stopping the current operation safely');
end;

procedure RefreshBootstrapProgress;
var
  Lines: TArrayOfString;
  Percent: Integer;
begin
  if not LoadStringsFromFile(BootstrapStatusPath, Lines) then Exit;
  if GetArrayLength(Lines) < 3 then Exit;
  Percent := StrToIntDef(Trim(Lines[0]), 0);
  if Percent < 0 then Percent := 0;
  if Percent > 100 then Percent := 100;
  BootstrapProgress.SetText(Trim(Lines[1]), Trim(Lines[2]));
  BootstrapProgress.SetProgress(Percent, 100);
  WizardForm.Refresh;
end;

{ True while a process holds Leadroom.exe open: a running program cannot be opened
  for writing with no sharing. }
function AppExeInUse: Boolean;
var
  Path: String;
  Handle: LongWord;
begin
  Result := False;
  Path := ExpandConstant('{app}\{#AppExeName}');
  if not FileExists(Path) then Exit;
  Handle := CreateFileW(Path, $40000000, 0, 0, 3, $80, 0);
  if Handle = $FFFFFFFF then
    Result := True
  else
    CloseHandle(Handle);
end;

{ The in-app updater starts Setup and then quits; a one-file app takes a few seconds
  to let go of its files. A quiet Setup cannot close a window-less process itself and
  would abort, so wait for it here (up to 90 seconds). }
function WaitForAppToClose: Boolean;
var
  Tries: Integer;
begin
  Tries := 0;
  while AppExeInUse and (Tries < 900) do begin
    PumpPendingMessages;
    Sleep(100);
    Tries := Tries + 1;
  end;
  Result := not AppExeInUse;
  if Tries > 0 then
    Log(Format('Waited %d ms for Leadroom.exe to close; closed: %d', [Tries * 100, Ord(Result)]));
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then InstallFinished := True;
end;

{ An update that did not complete must not leave the user without Leadroom: open the
  version that is still installed, which reports the failure from its pending note. }
procedure DeinitializeSetup;
var
  ResultCode: Integer;
  Path: String;
begin
  if InstallFinished or not RelaunchRequested then Exit;
  try
    Path := ExpandConstant('{app}\{#AppExeName}');
  except
    Exit;
  end;
  if FileExists(Path) then begin
    Log('The update did not complete; reopening the installed Leadroom.');
    Exec(Path, '', ExtractFileDir(Path), SW_SHOWNORMAL, ewNoWait, ResultCode);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  CompletionLines: TArrayOfString;
  ProcessLines: TArrayOfString;
  FailureDetail: String;
  BootstrapProcessId, ProcessWaitCycles, LivenessCycles: Integer;
begin
  Result := '';
  ExtractTemporaryFiles('{tmp}\install-bootstrap.ps1');
  ExtractTemporaryFiles('{tmp}\setup-local-data.ps1');
  ExtractTemporaryFiles('{tmp}\import-osm.ps1');
  ExtractTemporaryFiles('{tmp}\setup-local-updates.ps1');
  ExtractTemporaryFiles('{tmp}\leadroom.lua');
  ExtractTemporaryFiles('{tmp}\post-import.sql');
  ExtractTemporaryFiles('{tmp}\leadroom-osm-update.sh');
  ExtractTemporaryFiles('{tmp}\leadroom-osm-update.service');
  ExtractTemporaryFiles('{tmp}\leadroom-osm-update.timer');
  BootstrapStatusPath := ExpandConstant('{tmp}\leadroom-bootstrap.status');
  BootstrapCompletionPath := ExpandConstant('{tmp}\leadroom-bootstrap.complete');
  BootstrapCancelPath := ExpandConstant('{tmp}\leadroom-bootstrap.cancel');
  BootstrapProcessPath := ExpandConstant('{tmp}\leadroom-bootstrap.process');
  DeleteFile(BootstrapStatusPath);
  DeleteFile(BootstrapCompletionPath);
  DeleteFile(BootstrapCancelPath);
  DeleteFile(BootstrapProcessPath);
  BootstrapCancelRequested := False;
  BootstrapProgress.SetText('Checking this computer',
    'Preparing the selected components');
  BootstrapProgress.SetProgress(0, 100);
  BootstrapRunning := True;
  BootstrapProgress.Show;
  BootstrapCancelButton.Enabled := True;
  BootstrapCancelButton.Visible := True;
  try
    if not Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      BootstrapArguments, '', SW_HIDE, ewNoWait, ResultCode) then
      RaiseException('Windows could not start the Leadroom setup helper.');
    BootstrapProcessId := 0;
    ProcessWaitCycles := 0;
    while (BootstrapProcessId = 0) and
      (not FileExists(BootstrapCompletionPath)) do begin
      PumpPendingMessages;
      RefreshBootstrapProgress;
      if LoadStringsFromFile(BootstrapProcessPath, ProcessLines) and
        (GetArrayLength(ProcessLines) >= 1) then
        BootstrapProcessId := StrToIntDef(Trim(ProcessLines[0]), 0);
      ProcessWaitCycles := ProcessWaitCycles + 1;
      { Allow up to two minutes: the first PowerShell start on a fresh Windows
        installation (profile setup, antivirus scanning) can exceed ten seconds. }
      if ProcessWaitCycles >= 2400 then begin
        SaveStringToFile(BootstrapCancelPath, 'cancel', False);
        BootstrapCancelRequested := True;
        Result := 'The Leadroom setup helper did not start correctly.' + #13#10 + #13#10 +
          'Review ' + ExpandConstant('{localappdata}\Leadroom\logs\install.log') +
          ' and run setup again.';
        Exit;
      end;
      Sleep(50);
    end;
    LivenessCycles := 0;
    while not FileExists(BootstrapCompletionPath) do begin
      PumpPendingMessages;
      RefreshBootstrapProgress;
      LivenessCycles := LivenessCycles + 1;
      if (LivenessCycles >= 10) and
        (not IsProcessRunning(BootstrapProcessId)) then begin
        Result := 'The Leadroom setup helper stopped unexpectedly.' + #13#10 + #13#10 +
          'Review ' + ExpandConstant('{localappdata}\Leadroom\logs\install.log') +
          ' and run setup again.';
        Exit;
      end;
      if LivenessCycles >= 10 then LivenessCycles := 0;
      Sleep(50);
    end;
    RefreshBootstrapProgress;
    if not LoadStringsFromFile(BootstrapCompletionPath, CompletionLines) then
      RaiseException('Leadroom setup did not report a completion status.');
    if (GetArrayLength(CompletionLines) >= 1) and (Trim(CompletionLines[0]) = '2') then begin
      BootstrapRunning := False;
      BootstrapCancelButton.Visible := False;
      WizardForm.CancelButton.Enabled := True;
      WizardForm.CancelButton.OnClick(WizardForm.CancelButton);
      Result := 'Setup was cancelled.';
      Exit;
    end;
    if (GetArrayLength(CompletionLines) < 1) or (Trim(CompletionLines[0]) <> '0') then begin
      FailureDetail := 'Leadroom prerequisites could not be prepared.';
      if (GetArrayLength(CompletionLines) >= 2) and
        (Trim(CompletionLines[1]) <> '') then
        FailureDetail := Trim(CompletionLines[1]);
      Result := FailureDetail + #13#10 + #13#10 + 'Review ' +
        ExpandConstant('{localappdata}\Leadroom\logs\install.log') + ' and run setup again.';
      Exit;
    end;
    { Only now, with the prerequisites in place: a failure above leaves the earlier
      version installed and working. }
    BootstrapProgress.SetText('Removing the earlier version',
      'Your workspace, models and map data are kept');
    RemoveEarlierInstalls;
    if (WizardSilent or RelaunchRequested) and not WaitForAppToClose then begin
      Result := 'Leadroom is still running, so it could not be updated.' + #13#10 + #13#10 +
        'Close Leadroom and run setup again.';
      Exit;
    end;
  finally
    BootstrapRunning := False;
    BootstrapCancelButton.Visible := False;
    DeleteFile(BootstrapStatusPath);
    DeleteFile(BootstrapCompletionPath);
    DeleteFile(BootstrapProcessPath);
    if not BootstrapCancelRequested then DeleteFile(BootstrapCancelPath);
    BootstrapProgress.Hide;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ResultCode: Integer;
begin
  if CurUninstallStep <> usUninstall then Exit;
  if SuppressibleMsgBox(
    'Keep your Leadroom workspace, downloaded models, cache, and local map data?' + #13#10 + #13#10 +
    'Choose Yes to preserve them for a future install. Choose No for a clean removal.',
    mbConfirmation, MB_YESNO, IDYES) = IDNO then
    Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
      '-NoLogo -NoProfile -ExecutionPolicy Bypass -File ' +
      PowerShellQuote(ExpandConstant('{app}\scripts\clean-install-state.ps1')) +
      ' -IncludeWorkspaceData -IncludeDownloads -Confirm',
      '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
