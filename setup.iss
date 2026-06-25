; Inno Setup Script for Irtifa
; This script creates a professional installer and uninstaller.

[Setup]
; App Information
AppName=İrtifa Balon Operasyon
AppVersion=1.1.2
AppPublisher=BewoAI
AppPublisherURL=https://bewoai.com
AppSupportURL=https://bewoai.com
AppUpdatesURL=https://bewoai.com

; Installation Directory (User's Program Files)
DefaultDirName={autopf}\Irtifa
DefaultGroupName=İrtifa Balon Operasyon

; Output Settings
OutputDir=.\setup_build
OutputBaseFilename=Irtifa_Setup
SetupIconFile=assets\setup_icon.ico
WizardImageFile=assets\setup_large.bmp
WizardSmallImageFile=assets\setup_small.bmp

; Compression Settings
Compression=lzma2/ultra64
SolidCompression=yes

; Look and Feel
WizardStyle=modern

[Languages]
Name: "turkish"; MessagesFile: "compiler:Languages\Turkish.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; The main executable built by PyInstaller
Source: "dist\Irtifa.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu Shortcut
Name: "{group}\İrtifa Balon Operasyon"; Filename: "{app}\Irtifa.exe"
; Start Menu Uninstall Shortcut
Name: "{group}\Programı Kaldır"; Filename: "{uninstallexe}"
; Desktop Shortcut (if user checked the box)
Name: "{autodesktop}\İrtifa Balon Operasyon"; Filename: "{app}\Irtifa.exe"; Tasks: desktopicon

[Run]
; Option to run the app immediately after installation
Filename: "{app}\Irtifa.exe"; Description: "{cm:LaunchProgram,İrtifa Balon Operasyon}"; Flags: nowait postinstall skipifsilent
