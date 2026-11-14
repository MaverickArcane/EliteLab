#ifndef StagingDir
  #error StagingDir must point to the extracted EliteLab bundle
#endif
#ifndef AppVersion
  #error AppVersion must be provided
#endif
#ifndef AppIdValue
  #define AppIdValue "MaverickArcane.EliteLab"
#endif
#ifndef AppGroupName
  #define AppGroupName "EliteLab"
#endif

[Setup]
AppId={#AppIdValue}
AppName=EliteLab
AppVersion={#AppVersion}
#ifdef NativeVersion
VersionInfoVersion={#NativeVersion}
#endif
AppPublisher=MaverickArcane
DefaultDirName={localappdata}\Programs\EliteLab
DefaultGroupName={#AppGroupName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
DisableProgramGroupPage=yes
CloseApplications=no
RestartApplications=no
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
UninstallDisplayName=EliteLab

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "{#StagingDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "{#StagingDir}\.windows-bundle"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\EliteLab"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch EliteLab.vbs"""; WorkingDir: "{app}"
Name: "{autodesktop}\EliteLab"; Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch EliteLab.vbs"""; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{sys}\wscript.exe"; Parameters: """{app}\Launch EliteLab.vbs"""; WorkingDir: "{app}"; Description: "Launch EliteLab"; Flags: nowait postinstall skipifsilent

[INI]
Filename: "{app}\desktop-browser.ini"; Section: "Desktop"; Key: "Browser"; String: "{code:SelectedBrowser}"; Flags: uninsdeleteentry uninsdeletesectionifempty
Filename: "{app}\desktop-browser.ini"; Section: "Desktop"; Key: "Profile"; String: "{code:SelectedProfile}"; Flags: uninsdeleteentry uninsdeletesectionifempty

[Code]
var GuardHandle: THandle;
    GuardHeld: Boolean;
    BrowserPage, ProfilePage: TInputOptionWizardPage;
    BrowserIds: TArrayOfString;
    RequestedBrowser, RequestedProfile: String;

function BrowserPath(Id: String): String;
var Relative, Candidate: String; I: Integer;
begin
  Result := '';
  if Id = 'chrome' then Relative := 'Google\Chrome\Application\chrome.exe'
  else if Id = 'edge' then Relative := 'Microsoft\Edge\Application\msedge.exe'
  else if Id = 'brave' then Relative := 'BraveSoftware\Brave-Browser\Application\brave.exe'
  else if Id = 'chromium' then Relative := 'Chromium\Application\chrome.exe'
  else exit;
  for I := 0 to 2 do begin
    if I = 0 then Candidate := ExpandConstant('{commonpf64}')
    else if I = 1 then Candidate := ExpandConstant('{commonpf32}')
    else Candidate := ExpandConstant('{localappdata}');
    Candidate := AddBackslash(Candidate) + Relative;
    if FileExists(Candidate) then begin Result := Candidate; exit; end;
  end;
end;

function DefaultBrowser: String;
var ProgId: String;
begin
  Result := '';
  if RegQueryStringValue(HKCU, 'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice', 'ProgId', ProgId) then begin
    ProgId := Lowercase(ProgId);
    if Pos('chromehtml', ProgId) = 1 then Result := 'chrome'
    else if Pos('msedgehtm', ProgId) = 1 then Result := 'edge'
    else if Pos('bravehtml', ProgId) = 1 then Result := 'brave'
    else if Pos('chromiumhtm', ProgId) = 1 then Result := 'chromium';
  end;
end;

procedure AddBrowser(Id, LabelText: String);
var N: Integer;
begin
  if BrowserPath(Id) = '' then exit;
  N := GetArrayLength(BrowserIds);
  SetArrayLength(BrowserIds, N + 1);
  BrowserIds[N] := Id;
  if Id = DefaultBrowser then LabelText := LabelText + ' (Windows default)';
  BrowserPage.Add(LabelText);
end;

function SelectedBrowser(Param: String): String;
var I: Integer;
begin
  Result := '';
  I := BrowserPage.SelectedValueIndex;
  if (I >= 0) and (I < GetArrayLength(BrowserIds)) then Result := BrowserIds[I];
end;

function SelectedProfile(Param: String): String;
begin
  if ProfilePage.SelectedValueIndex = 1 then Result := 'persistent' else Result := 'guest';
end;

procedure InitializeWizard;
var Preferred: String; I: Integer;
begin
  BrowserPage := CreateInputOptionPage(wpSelectDir, 'App window browser',
    'Choose the browser that runs the EliteLab app window.',
    'EliteLab opens as its own window, without tabs or an address bar. Only installed browsers supported by this launcher are listed. Rerun setup to change this choice.', True, False);
  AddBrowser('chrome', 'Google Chrome');
  AddBrowser('edge', 'Microsoft Edge');
  AddBrowser('brave', 'Brave');
  AddBrowser('chromium', 'Chromium');
  RequestedBrowser := Lowercase(ExpandConstant('{param:APPBROWSER|}'));
  Preferred := RequestedBrowser;
  if Preferred = '' then Preferred := GetPreviousData('AppBrowser', DefaultBrowser);
  if GetArrayLength(BrowserIds) > 0 then BrowserPage.SelectedValueIndex := 0;
  for I := 0 to GetArrayLength(BrowserIds) - 1 do
    if BrowserIds[I] = Preferred then BrowserPage.SelectedValueIndex := I;
  ProfilePage := CreateInputOptionPage(BrowserPage.ID, 'App browser profile',
    'Choose how the app window keeps browser information.',
    'Guest mode keeps browser accounts separate. Browser-only layout and filter preferences reset when all guest windows close; EliteLab saved data and plans remain. A persistent profile remembers window preferences but can use the browser''s account and import features.', True, False);
  ProfilePage.Add('Guest profile (recommended)');
  ProfilePage.Add('Persistent EliteLab profile');
  RequestedProfile := Lowercase(ExpandConstant('{param:BROWSERPROFILE|}'));
  Preferred := RequestedProfile;
  if Preferred = '' then Preferred := GetPreviousData('BrowserProfile', 'guest');
  if Preferred = 'persistent' then ProfilePage.SelectedValueIndex := 1
  else ProfilePage.SelectedValueIndex := 0;
end;

procedure RegisterPreviousData(PreviousDataKey: Integer);
begin
  SetPreviousData(PreviousDataKey, 'AppBrowser', SelectedBrowser(''));
  SetPreviousData(PreviousDataKey, 'BrowserProfile', SelectedProfile(''));
end;

function NativeCreateFile(Name: String; Access, Share: Cardinal; Security: THandle;
  Disposition, Flags: Cardinal; Template: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function NativeLockFile(Handle: THandle; OffsetLow, OffsetHigh, LengthLow, LengthHigh: Cardinal): Boolean;
  external 'LockFile@kernel32.dll stdcall';
function NativeUnlockFile(Handle: THandle; OffsetLow, OffsetHigh, LengthLow, LengthHigh: Cardinal): Boolean;
  external 'UnlockFile@kernel32.dll stdcall';
function NativeCloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function AcquireGuard: Boolean;
var Dir, FileName, ProfileDir: String;
begin
  Result := False;
  Dir := GetEnv('ELITELAB_INSTANCE_DIR');
  if Dir = '' then begin
    { Match Python's Windows Path.home() lookup; userprofile is not an Inno constant. }
    ProfileDir := GetEnv('USERPROFILE');
    if (ProfileDir = '') and (GetEnv('HOMEPATH') <> '') then
      ProfileDir := GetEnv('HOMEDRIVE') + GetEnv('HOMEPATH');
    if ProfileDir = '' then begin
      SuppressibleMsgBox('Cannot locate the Windows user profile. Set USERPROFILE or an absolute ELITELAB_INSTANCE_DIR and try again.', mbError, MB_OK, IDOK);
      exit;
    end;
    Dir := AddBackslash(ProfileDir) + '.elitelab';
  end;
  if not (((Length(Dir) >= 3) and (Copy(Dir, 2, 2) = ':\')) or (Copy(Dir, 1, 2) = '\\')) then begin
    SuppressibleMsgBox('The EliteLab instance directory must be an absolute path during installation.', mbError, MB_OK, IDOK);
    exit;
  end;
  if not ForceDirectories(Dir) then begin
    SuppressibleMsgBox('Cannot access the EliteLab instance directory. Close EliteLab and check the directory permissions.', mbError, MB_OK, IDOK);
    exit;
  end;
  FileName := AddBackslash(Dir) + 'instance.lock';
  GuardHandle := NativeCreateFile(FileName, $C0000000, $7, 0, 4, $80, 0);
  if GuardHandle = THandle(-1) then begin
    SuppressibleMsgBox('Cannot open the EliteLab instance guard. Close EliteLab and check its permissions.', mbError, MB_OK, IDOK);
    exit;
  end;
  if not NativeLockFile(GuardHandle, 0, 0, 1, 0) then begin
    NativeCloseHandle(GuardHandle);
    SuppressibleMsgBox('EliteLab is running. Quit it before installing or uninstalling.', mbError, MB_OK, IDOK);
    exit;
  end;
  GuardHeld := True;
  Result := True;
end;

procedure ReleaseGuard;
begin
  if GuardHeld then begin
    NativeUnlockFile(GuardHandle, 0, 0, 1, 0);
    NativeCloseHandle(GuardHandle);
    GuardHeld := False;
  end;
end;

function InitializeSetup: Boolean;
begin
  Result := AcquireGuard;
end;

function DirectoryHasEntries(Dir: String): Boolean;
var Entry: TFindRec;
begin
  Result := False;
  if FindFirst(AddBackslash(Dir) + '*', Entry) then begin
    try
      repeat
        if (Entry.Name <> '.') and (Entry.Name <> '..') then begin
          Result := True;
          exit;
        end;
      until not FindNext(Entry);
    finally
      FindClose(Entry);
    end;
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var Destination: String;
begin
  Result := '';
  if (SelectedBrowser('') = '') or (BrowserPath(SelectedBrowser('')) = '') then begin
    Result := 'Install Chrome, Edge, Brave or Chromium, then run EliteLab setup again.';
    exit;
  end;
  if (RequestedBrowser <> '') and (RequestedBrowser <> SelectedBrowser('')) then begin
    Result := 'APPBROWSER must name an installed chrome, edge, brave or chromium browser.';
    exit;
  end;
  if (RequestedProfile <> '') and (RequestedProfile <> 'guest') and (RequestedProfile <> 'persistent') then begin
    Result := 'BROWSERPROFILE must be guest or persistent.';
    exit;
  end;
  Destination := ExpandConstant('{app}');
  if DirExists(Destination) and not FileExists(AddBackslash(Destination) + '.windows-bundle') and DirectoryHasEntries(Destination) then
    Result := 'Choose an empty folder or an existing EliteLab bundle folder. Setup will not overwrite an unrelated folder.';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then ReleaseGuard;
end;

procedure DeinitializeSetup;
begin
  ReleaseGuard;
end;

function InitializeUninstall: Boolean;
begin
  Result := AcquireGuard;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var ExitCode: Integer; Python: String;
begin
  if CurUninstallStep = usUninstall then begin
    Python := ExpandConstant('{app}\runtime\pythonw.exe');
    if not FileExists(Python) or not Exec(Python, '-m elitelab.autostart --remove-owned --value-name {#AppIdValue}',
          ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, ExitCode) or (ExitCode <> 0) then begin
      SuppressibleMsgBox('The bundled launcher is missing or its sign-in entry could not be checked. Reinstall EliteLab over this folder and try uninstalling again.', mbError, MB_OK, IDOK);
      Abort;
    end;
  end;
end;

procedure DeinitializeUninstall;
begin
  ReleaseGuard;
end;

