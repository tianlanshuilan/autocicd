; NSIS 安装脚本 - CI/CD 流水线自动搭建平台 (Windows)
; 使用方法: makensis installer.nsi
;
; 需要先安装 NSIS: https://nsis.sourceforge.io/

!include "MUI2.nsh"

; 基本信息
Name "CI/CD 流水线自动搭建平台"
OutFile "..\..\..\dist\AutoCICD-Setup.exe"
InstallDir "$PROGRAMFILES\AutoCICD"
InstallDirRegKey HKLM "Software\AutoCICD" "InstallDir"
RequestExecutionLevel admin

; 版本信息
VIProductVersion "1.0.0.0"
VIAddVersionKey "ProductName" "CI/CD 流水线自动搭建平台"
VIAddVersionKey "CompanyName" "AutoCICD"
VIAddVersionKey "FileVersion" "1.0.0"
VIAddVersionKey "LegalCopyright" "Copyright 2024"
VIAddVersionKey "FileDescription" "CI/CD 流水线自动搭建平台安装程序"

; MUI 配置
!define MUI_ABORTWARNING
!define MUI_ICON "..\icons\icon.ico"
!define MUI_UNICON "..\icons\icon.ico"

; 页面
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE "..\..\LICENSE"
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; 语言
!insertmacro MUI_LANGUAGE "SimpChinese"

; 安装区段
Section "安装" SecInstall
    SetOutPath "$INSTDIR"
    
    ; 复制所有文件
    File /r "..\..\..\dist\AutoCICD\*.*"
    
    ; 创建卸载程序
    WriteUninstaller "$INSTDIR\uninstall.exe"
    
    ; 创建开始菜单快捷方式
    CreateDirectory "$SMPROGRAMS\AutoCICD"
    CreateShortcut "$SMPROGRAMS\AutoCICD\CI-CD 流水线自动搭建平台.lnk" "$INSTDIR\AutoCICD.exe" "" "$INSTDIR\AutoCICD.exe" 0
    CreateShortcut "$SMPROGRAMS\AutoCICD\卸载.lnk" "$INSTDIR\uninstall.exe"
    
    ; 创建桌面快捷方式
    CreateShortcut "$DESKTOP\CI-CD 流水线自动搭建平台.lnk" "$INSTDIR\AutoCICD.exe" "" "$INSTDIR\AutoCICD.exe" 0
    
    ; 写入注册表
    WriteRegStr HKLM "Software\AutoCICD" "InstallDir" "$INSTDIR"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD" "DisplayName" "CI/CD 流水线自动搭建平台"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD" "UninstallString" "$INSTDIR\uninstall.exe"
    WriteRegStr HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD" "DisplayIcon" "$INSTDIR\AutoCICD.exe"
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD" "NoModify" 1
    WriteRegDWORD HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD" "NoRepair" 1
SectionEnd

; 卸载区段
Section "Uninstall"
    ; 删除安装目录
    RMDir /r "$INSTDIR"
    
    ; 删除开始菜单快捷方式
    RMDir /r "$SMPROGRAMS\AutoCICD"
    
    ; 删除桌面快捷方式
    Delete "$DESKTOP\CI-CD 流水线自动搭建平台.lnk"
    
    ; 删除注册表
    DeleteRegKey HKLM "Software\AutoCICD"
    DeleteRegKey HKLM "Software\Microsoft\Windows\CurrentVersion\Uninstall\AutoCICD"
SectionEnd
