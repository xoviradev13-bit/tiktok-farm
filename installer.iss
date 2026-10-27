; Inno Setup Script for TikTok Auto Farm & AI Video Engine
; Modern, clean, and antivirus-safe installer specification

#define MyAppName "TikTok Auto Farm & AI Video Engine"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "TikTok Farm Systems"
#define MyAppExeName "TikTokFarm.exe"
#define MyAppAssocName MyAppName + " File"
#define MyAppAssocExt ".ttfarm"
#define MyAppAssocKey StringChange(MyAppAssocName, " ", "") + MyAppAssocExt

[Setup]
; Unique AppId so updates properly detect previous versions
AppId={{D864F25A-A91B-4C91-9F2B-B129D55C7E83}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\TikTok Auto Farm
DefaultGroupName={#MyAppName}
AllowNoIcons=yes
OutputDir=dist_installer
OutputBaseFilename=TikTokAutoFarm_Setup_v1.0.0
SetupIconFile=logo\app-logo.ico
Compression=lzma2/normal
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
UninstallDisplayIcon={app}\{#MyAppExeName}
VersionInfoVersion=1.0.0.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoTextVersion=1.0.0.0
VersionInfoCopyright=Copyright (C) 2026 {#MyAppPublisher}
DisableProgramGroupPage=auto
CloseApplications=yes
CloseApplicationsFilter=*{#MyAppExeName}*
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\TikTokFarm\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "logo\*"; DestDir: "{app}\logo"; Flags: ignoreversion recursesubdirs createallsubdirs


[Dirs]
; Tạo thư mục dữ liệu trong %APPDATA% (không bị xóa khi gỡ cài đặt)
Name: "{userappdata}\TikTok Auto Farm"
Name: "{userappdata}\TikTok Auto Farm\downloads"
Name: "{userappdata}\TikTok Auto Farm\rendered"
Name: "{userappdata}\TikTok Auto Farm\logs"
Name: "{userappdata}\TikTok Auto Farm\music"

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo\app-logo.ico"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\logo\app-logo.ico"; Tasks: desktopicon

[UninstallDelete]
; Xóa sạch các file phát sinh khi chạy (như .env, cache) và thư mục cài đặt khi gỡ bỏ
Type: filesandordirs; Name: "{app}"

[UninstallRun]
; Tắt ứng dụng chạy ngầm trên khay hệ thống (system tray) trước khi gỡ cài đặt
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM {#MyAppExeName} /T >nul 2>&1"; Flags: runhidden

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent


