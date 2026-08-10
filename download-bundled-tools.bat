@echo off
chcp 65001 >nul
REM CI/CD 流水线自动搭建平台 - 离线安装包下载脚本 (Windows)
REM 使用方法: download-bundled-tools.bat

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set TOOLS_DIR=%SCRIPT_DIR%bundled-tools

echo ==========================================
echo   CI/CD 离线安装包下载工具 (Windows)
echo ==========================================

REM 创建目录结构
echo 创建目录结构...
if not exist "%TOOLS_DIR%\jenkins" mkdir "%TOOLS_DIR%\jenkins"
if not exist "%TOOLS_DIR%\runner\amd64" mkdir "%TOOLS_DIR%\runner\amd64"
if not exist "%TOOLS_DIR%\runner\arm64" mkdir "%TOOLS_DIR%\runner\arm64"
if not exist "%TOOLS_DIR%\runner\arm" mkdir "%TOOLS_DIR%\runner\arm"
if not exist "%TOOLS_DIR%\jdk\x86_64" mkdir "%TOOLS_DIR%\jdk\x86_64"
if not exist "%TOOLS_DIR%\jdk\aarch64" mkdir "%TOOLS_DIR%\jdk\aarch64"
if not exist "%TOOLS_DIR%\docker\amd64" mkdir "%TOOLS_DIR%\docker\amd64"
if not exist "%TOOLS_DIR%\docker\arm64" mkdir "%TOOLS_DIR%\docker\arm64"
echo [OK] 目录结构创建完成

REM 下载 Jenkins WAR 包
echo 下载 Jenkins WAR 包...
if not exist "%TOOLS_DIR%\jenkins\jenkins.war" (
    curl -fsSL -o "%TOOLS_DIR%\jenkins\jenkins.war" "https://get.jenkins.io/war-stable/latest/jenkins.war"
    if !ERRORLEVEL! NEQ 0 (
        echo 官方源失败，尝试清华镜像...
        curl -fsSL -o "%TOOLS_DIR%\jenkins\jenkins.war" "https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war"
    )
    echo [OK] Jenkins WAR 包下载完成
) else (
    echo Jenkins WAR 包已存在，跳过
)

REM 下载 GitLab Runner (amd64)
echo 下载 GitLab Runner (amd64)...
if not exist "%TOOLS_DIR%\runner\amd64\gitlab-runner.exe" (
    curl -fsSL -o "%TOOLS_DIR%\runner\amd64\gitlab-runner" "https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-amd64"
    echo [OK] Runner amd64 下载完成
) else (
    echo Runner amd64 已存在，跳过
)

REM 下载 GitLab Runner (arm64)
echo 下载 GitLab Runner (arm64)...
if not exist "%TOOLS_DIR%\runner\arm64\gitlab-runner" (
    curl -fsSL -o "%TOOLS_DIR%\runner\arm64\gitlab-runner" "https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-arm64"
    echo [OK] Runner arm64 下载完成
) else (
    echo Runner arm64 已存在，跳过
)

REM 下载 OpenJDK (x86_64)
echo 下载 OpenJDK 17 (x86_64)...
if not exist "%TOOLS_DIR%\jdk\x86_64\openjdk.tar.gz" (
    curl -fsSL -o "%TOOLS_DIR%\jdk\x86_64\openjdk.tar.gz" "https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-x64_bin.tar.gz"
    if !ERRORLEVEL! NEQ 0 (
        echo 官方源失败，尝试清华镜像...
        curl -fsSL -o "%TOOLS_DIR%\jdk\x86_64\openjdk.tar.gz" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.2_8.tar.gz"
    )
    echo [OK] JDK x86_64 下载完成
) else (
    echo JDK x86_64 已存在，跳过
)

REM 下载 OpenJDK (aarch64)
echo 下载 OpenJDK 17 (aarch64)...
if not exist "%TOOLS_DIR%\jdk\aarch64\openjdk.tar.gz" (
    curl -fsSL -o "%TOOLS_DIR%\jdk\aarch64\openjdk.tar.gz" "https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-aarch64_bin.tar.gz"
    if !ERRORLEVEL! NEQ 0 (
        echo 官方源失败，尝试清华镜像...
        curl -fsSL -o "%TOOLS_DIR%\jdk\aarch64\openjdk.tar.gz" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/aarch64/linux/OpenJDK17U-jdk_aarch64_linux_hotspot_17.0.2_8.tar.gz"
    )
    echo [OK] JDK aarch64 下载完成
) else (
    echo JDK aarch64 已存在，跳过
)

REM 下载 Docker (amd64)
echo 下载 Docker (amd64)...
if not exist "%TOOLS_DIR%\docker\amd64\docker.tgz" (
    curl -fsSL -o "%TOOLS_DIR%\docker\amd64\docker.tgz" "https://download.docker.com/linux/static/stable/x86_64/docker-24.0.7.tgz"
    if !ERRORLEVEL! NEQ 0 (
        echo 官方源失败，尝试阿里云镜像...
        curl -fsSL -o "%TOOLS_DIR%\docker\amd64\docker.tgz" "https://mirrors.aliyun.com/docker-ce/linux/static/stable/x86_64/docker-24.0.7.tgz"
    )
    echo [OK] Docker amd64 下载完成
) else (
    echo Docker amd64 已存在，跳过
)

REM 下载 Docker (arm64)
echo 下载 Docker (arm64)...
if not exist "%TOOLS_DIR%\docker\arm64\docker.tgz" (
    curl -fsSL -o "%TOOLS_DIR%\docker\arm64\docker.tgz" "https://download.docker.com/linux/static/stable/aarch64/docker-24.0.7.tgz"
    if !ERRORLEVEL! NEQ 0 (
        echo 官方源失败，尝试阿里云镜像...
        curl -fsSL -o "%TOOLS_DIR%\docker\arm64\docker.tgz" "https://mirrors.aliyun.com/docker-ce/linux/static/stable/aarch64/docker-24.0.7.tgz"
    )
    echo [OK] Docker arm64 下载完成
) else (
    echo Docker arm64 已存在，跳过
)

echo.
echo ==========================================
echo   离线包下载完成！
echo ==========================================
echo.
echo 目录: %TOOLS_DIR%
echo.

pause
