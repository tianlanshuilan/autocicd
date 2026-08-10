@echo off
chcp 65001 >nul
REM CI/CD 流水线自动搭建平台 - 构建脚本 (Windows)
REM 使用方法: build.bat

echo ==========================================
echo   CI/CD 流水线自动搭建平台 - 构建工具
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
    echo 请安装 Node.js 并添加到 PATH
    pause
    exit /b 1
)

where npm >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 未找到 npm
    pause
    exit /b 1
)

echo [OK] 依赖检查通过

REM 安装 Python 依赖
echo 安装 Python 依赖...
pip install -r requirements.txt
pip install pyinstaller
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
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 前端依赖安装失败
    pause
    exit /b 1
)
echo [OK] 前端依赖安装完成

REM 构建前端
echo 构建前端...
cd frontend
call npm run build
cd ..
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 前端构建失败
    pause
    exit /b 1
)

if not exist "frontend\dist" (
    echo 错误: 前端构建失败，未找到 frontend\dist 目录
    pause
    exit /b 1
)
echo [OK] 前端构建完成

REM 打包应用
echo 打包应用...

REM 清理旧的构建
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

REM 运行 PyInstaller
pyinstaller auto-cicd.spec --clean --noconfirm
if %ERRORLEVEL% NEQ 0 (
    echo 错误: 应用打包失败
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   构建成功！
echo ==========================================
echo.
echo 可执行文件位置:
echo   dist\auto-cicd.exe
echo.
echo 运行方式:
echo   dist\auto-cicd.exe
echo.
echo 或指定端口:
echo   set PORT=9000
echo   dist\auto-cicd.exe
echo.

pause
