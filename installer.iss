; Inno Setup Script for Hardware_Monitor
#define MyAppName "Hardware Monitor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Perform-Stats"
#define InstallDir "C:\\Hardware_Monitor"
#define SourceDir "c:\\Dev\\Perform-Stats\\dist"

[Setup]
AppId={{C0C3D3F5-0D1A-4D1A-9F1B-9B1F9A9C0F01}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#InstallDir}
DisableDirPage=yes
DisableProgramGroupPage=yes
UninstallDisplayIcon={#InstallDir}\\PerformStatsSensorService\\PerformStatsSensorService.exe
OutputDir={#SourceDir}
OutputBaseFilename=Hardware_Monitor_Setup
Compression=lzma
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\\French.isl"

[Files]
; Application published bits
Source: "{#SourceDir}\\PerformStatsSensorService\\*"; DestDir: "{#InstallDir}\\PerformStatsSensorService"; Flags: recursesubdirs createallsubdirs ignoreversion
; OpenHardwareMonitor resources
Source: "{#SourceDir}\\OpenHardwareMonitor\\*"; DestDir: "{#InstallDir}\\OpenHardwareMonitor"; Flags: recursesubdirs createallsubdirs ignoreversion
; Helper scripts (optional)
Source: "{#SourceDir}\\installer_service.ps1"; DestDir: "{#InstallDir}"; Flags: ignoreversion
Source: "{#SourceDir}\\desinstaller_service.ps1"; DestDir: "{#InstallDir}"; Flags: ignoreversion

[Run]
; Install and start Windows Service immediately after copying files
Filename: "sc.exe"; Parameters: "create Hardware_Monitor binPath= '""{#InstallDir}\\PerformStatsSensorService\\PerformStatsSensorService.exe""' start= auto DisplayName= '""Hardware Monitor""'"; Flags: runhidden; StatusMsg: "Création du service Windows..."
Filename: "sc.exe"; Parameters: "description Hardware_Monitor ""Expose les métriques via HTTP en local sur http://127.0.0.1:9755/metrics"""; Flags: runhidden
Filename: "sc.exe"; Parameters: "start Hardware_Monitor"; Flags: runhidden; StatusMsg: "Démarrage du service..."

[UninstallRun]
; Stop and delete the service during uninstall
Filename: "sc.exe"; Parameters: "stop Hardware_Monitor"; Flags: runhidden
Filename: "sc.exe"; Parameters: "delete Hardware_Monitor"; Flags: runhidden

[Icons]
Name: "{autoprograms}\\{#MyAppName}"; Filename: "{#InstallDir}\\PerformStatsSensorService\\PerformStatsSensorService.exe"; WorkingDir: "{#InstallDir}\\PerformStatsSensorService"
Name: "{autoprograms}\\Désinstaller {#MyAppName}"; Filename: "{uninstallexe}"