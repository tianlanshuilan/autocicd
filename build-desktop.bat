@echo off
chcp 65001 >nul
REM CI/CD 流水线自动搭建平台 - 桌面应用构建脚本 (Windows)
REM 使用方法: build-desktop.bat

echo ==========================================
echo   CI/CD 流水线自动搭建平台 - 桌面应用构建
echo ==========================================

REM 检查依赖
echo 检查依赖...

where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 未找到 Python
    echo 请安装 Python 3.8+ 并添加到 PATH
    pause
    exit /b 1
)

where node >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 未找到 Node.js
    pause
    exit /b 1
)

echo [OK] 依赖检查通过

REM 安装依赖
echo 安装依赖...
pip install -r requirements.txt
pip install pyinstaller pywebview
if %ERRORLEVEL% NEQ 0 (
    echo 错误: Python 依赖安装失败
    pause
    exit /b 1
)
echo [OK] Python 依赖安装完成

REM 安装前端依赖
echo 安装前端依赖...
cd frontend
call npm install
cd ..
echo [OK] 前端依赖安装完成

REM 构建前端
echo 构建前端...
cd frontend
call npm run build
cd ..
if not exist "frontend\dist" (
    echo 错误: 前端构建失败
    pause
    exit /b 1
)
echo [OK] 前端构建完成

REM 打包桌面应用
echo 打包桌面应用...

REM 清理旧的构建
if exist build rmdir /s /q build
if exist "dist\AutoCICD" rmdir /s /q "dist\AutoCICD"
if exist "dist\AutoCICD.exe" del /f "dist\AutoCICD.exe"

REM 运行 PyInstaller
pyinstaller auto-cicd-desktop.spec --clean --noconfirm
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 桌面应用打包失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   桌面应用构建成功！
echo ==========================================
echo.
echo 可执行文件位置:
echo   dist\AutoCICD.exe
echo.
echo 运行方式:
echo   双击 dist\AutoCICD.exe
echo.
echo 创建安装包 (需要 NSIS):
echo   makensis desktop\installer\windows\installer.nsi
echo.

pause
