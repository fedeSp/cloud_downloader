; =============================================================================
;  Cloud Downloader — Inno Setup 6 script
;  Genera: dist\installer\CloudDownloader_Setup.exe
;
;  Uso: ISCC.exe installer.iss
;  (o ejecutá build_windows.ps1 que lo invoca automáticamente si está instalado)
; =============================================================================

#define AppName      "Cloud Downloader"
#define AppVersion   "1.0"
#define AppPublisher "Cloud Downloader"
#define AppURL       "https://github.com"
#define AppExeName   "CloudDownloader.exe"

[Setup]
AppId={{4F9E3B2A-7C1D-4E8F-A0B3-2D5C6E9F1234}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
; El instalador va a dist\installer\
OutputDir=dist\installer
OutputBaseFilename=CloudDownloader_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Requiere admin para instalar en Program Files
PrivilegesRequired=admin
; Imagen lateral del wizard (opcional — descomenta y agregá el archivo)
; WizardImageFile=assets\installer_banner.bmp
; WizardSmallImageFile=assets\installer_icon.bmp

[Languages]
; El instalador se mostrará en español si el sistema lo tiene, sino inglés
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
spanish.WelcomeLabel1=Bienvenido al instalador de [name]
spanish.WelcomeLabel2=Este asistente instalará [name/ver] en tu computadora.%n%nCerrá todas las demás aplicaciones antes de continuar.
spanish.FinishedLabel=La instalación de [name] finalizó correctamente.%n%nAl abrirla por primera vez, se pedirá que conectes tu cuenta de Google Drive. Solo hace falta hacerlo una vez.

[Tasks]
Name: "desktopicon"; \
    Description: "Crear acceso directo en el Escritorio"; \
    GroupDescription: "Opciones adicionales:"; \
    Flags: unchecked

[Files]
; El .exe generado por PyInstaller (ya incluye rclone y Python embebidos)
Source: "dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Acceso directo en el menú inicio
Name: "{group}\{#AppName}";                       Filename: "{app}\{#AppExeName}"
Name: "{group}\Desinstalar {#AppName}";            Filename: "{uninstallexe}"
; Acceso directo en el escritorio (solo si el usuario lo eligió)
Name: "{autodesktop}\{#AppName}";                  Filename: "{app}\{#AppExeName}"; \
    Tasks: desktopicon

[Run]
; Ofrecer lanzar la app al finalizar el instalador
Filename: "{app}\{#AppExeName}"; \
    Description: "Abrir {#AppName} ahora"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Limpiar la carpeta de configuración de rclone solo si el usuario lo desea
; (descomenta si querés incluir esto — es destructivo, borra las credenciales)
; Type: filesandordirs; Name: "{userappdata}\rclone"
