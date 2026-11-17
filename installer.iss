#define MyAppName "База проектов"
#define MyAppExeName "BasaProject.exe"
#define MyAppVersion "1.9.0"

[Setup]
; ФИКСИРОВАННЫЙ GUID — не менять между версиями, иначе будет две копии вместо обновления
AppId={{7C4E1D92-5B3A-4F6E-9A21-BASA0PROJECT1}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=elistratov
DefaultDirName={localappdata}\Programs\BasaProject
DefaultGroupName={#MyAppName}
PrivilegesRequired=lowest
OutputBaseFilename=BasaProjectSetup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#MyAppExeName}
DisableProgramGroupPage=yes

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; Flags: unchecked

[Files]
; только программные файлы; данные пользователя установщик не трогает
Source: "dist\BasaProject\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить {#MyAppName}"; Flags: nowait postinstall skipifsilent

; ============================================================
;  ДАННЫЕ НЕ УДАЛЯЮТСЯ ПРИ ДЕИНСТАЛЯЦИИ.
;  %APPDATA%\BasaProject и %LOCALAPPDATA%\BasaProject остаются.
;  Секцию [UninstallDelete] для них добавлять ЗАПРЕЩЕНО.
; ============================================================
