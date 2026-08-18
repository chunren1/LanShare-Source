; ---------------------------------------------------------------------
; LanShare 安装器脚本（Inno Setup 6）
; 用途：把 dist/LanShare.exe 打包成标准 Windows 安装程序 LanShare-Setup.exe
; 特性：
;   - 免管理员权限安装到 %LOCALAPPDATA%\Programs\LanShare（不弹 UAC）
;   - 桌面 + 开始菜单快捷方式
;   - 控制面板可卸载
;   - 安装完成后可选立即启动
; 编译：双击「打包安装包.bat」即可（自动装 Inno Setup + 编译）
; ---------------------------------------------------------------------

#define MyAppName "LanShare 局域网文件共享"
#define MyAppVersion "1.0.0"
#define MyAppExeName "LanShare.exe"

[Setup]
; 应用标识（固定 GUID，卸载/升级时识别用）
AppId={{8F2A3B1C-4D5E-4F60-9A71-B82C93D4E5F6}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=LanShare
; 免管理员安装到用户目录：不弹 UAC、不要求管理员权限，对小白最友好
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\LanShare
DefaultGroupName=LanShare
DisableProgramGroupPage=yes
; 输出
OutputDir=installer
OutputBaseFilename=LanShare-Setup
; 压缩
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 安装包自身图标（向导窗口 + 产物图标）
SetupIconFile=icons\lanshare.ico
; 卸载显示图标
UninstallDisplayIcon={app}\{#MyAppExeName}
; 允许 64 位系统
ArchitecturesInstallIn64BitMode=x64compatible
; 语言（中文 + 英文）
ShowLanguageDialog=no

[Languages]
Name: "chinesesimplified"; MessagesFile: "ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "icons\lanshare.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\lanshare.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\lanshare.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
