#ifndef AppVersion
#define AppVersion "0.1.0"
#endif

#define AppId "{{D8165062-360B-4483-8A94-4080CAAD414C}"
#define PublisherName "OGSpiderX"
#define RepoURL "https://github.com/ogspiderx/luma"
#define BuildRoot "..\..\dist\Luma"

[Setup]
AppId={#AppId}
AppName=Luma
AppVersion={#AppVersion}
AppVerName=Luma {#AppVersion}
AppPublisher={#PublisherName}
AppPublisherURL={#RepoURL}
AppSupportURL={#RepoURL}/issues
AppUpdatesURL={#RepoURL}/releases
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\Luma
DefaultGroupName=Luma
DisableProgramGroupPage=yes
LicenseFile=..\..\TERMS.md
InfoBeforeFile=..\..\PRIVACY.md
OutputDir=..\..\dist\installer
OutputBaseFilename=Luma-Setup-{#AppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Luma.exe
UninstallDisplayName=Luma
#ifexist "luma.ico"
SetupIconFile=luma.ico
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenu"; Description: "Create a Start Menu shortcut"; \
    GroupDescription: "Shortcuts:"; Flags: checked
Name: "pinstart"; Description: "Pin Luma to Start"; \
    GroupDescription: "Shortcuts:"; Flags: checked

[Files]
Source: "{#BuildRoot}\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion
Source: "installed.marker"; DestDir: "{app}"; DestName: ".installed_app"; \
    Flags: ignoreversion
#ifexist "luma.ico"
Source: "luma.ico"; DestDir: "{app}"; Flags: ignoreversion
#endif

[Icons]
Name: "{group}\Luma"; Filename: "{app}\Luma.exe"; \
    IconFilename: "{app}\Luma.exe"; Tasks: startmenu
Name: "{group}\Uninstall Luma"; Filename: "{uninstallexe}"; \
    Tasks: startmenu

[Run]
Filename: "{sys}\WindowsPowerShell\v1.0\powershell.exe"; \
    Parameters: "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -Command ""try {{ $s = New-Object -ComObject Shell.Application; $f = $s.Namespace('{group}'); $i = $f.ParseName('Luma.lnk'); $i.InvokeVerb('pintohome') } catch {{}; exit 0"""; \
    Tasks: pinstart; Flags: runhidden; \
    StatusMsg: "Pinning Luma to Start..."

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
