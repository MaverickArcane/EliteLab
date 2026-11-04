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

[Code]
var GuardHandle: THandle;
    GuardHeld: Boolean;

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
var Dir, FileName: String;
begin
  Result := False;
  Dir := GetEnv('ELITELAB_INSTANCE_DIR');
  if Dir = '' then Dir := ExpandConstant('{userprofile}\.elitelab');
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

