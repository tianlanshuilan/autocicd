#!/bin/bash
#
# Linux 安装包打包脚本
# 支持: .deb (Debian/Ubuntu), .AppImage (通用)
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_NAME="AutoCICD"
VERSION="1.0.0"
ARCH=$(dpkg --print-architecture 2>/dev/null || echo "amd64")

echo "=========================================="
echo "  Linux 安装包打包"
echo "=========================================="

# 检查可执行文件
EXEC_PATH="$PROJECT_ROOT/dist/$APP_NAME"
if [ ! -f "$EXEC_PATH" ]; then
    echo "错误: $EXEC_PATH 不存在"
    echo "请先运行: pyinstaller auto-cicd-desktop.spec"
    exit 1
fi

# ============================================
# 创建 .deb 包
# ============================================
create_deb() {
    echo "创建 .deb 安装包..."
    
    DEB_DIR="$PROJECT_ROOT/dist/deb-build"
    rm -rf "$DEB_DIR"
    
    # 创建目录结构
    mkdir -p "$DEB_DIR/opt/autocicd"
    mkdir -p "$DEB_DIR/usr/bin"
    mkdir -p "$DEB_DIR/usr/share/applications"
    mkdir -p "$DEB_DIR/usr/share/icons/hicolor/256x256/apps"
    mkdir -p "$DEB_DIR/DEBIAN"
    
    # 复制可执行文件
    cp "$EXEC_PATH" "$DEB_DIR/opt/autocicd/autocicd"
    chmod +x "$DEB_DIR/opt/autocicd/autocicd"
    
    # 创建启动脚本
    cat > "$DEB_DIR/usr/bin/autocicd" << 'LAUNCHER'
#!/bin/bash
/opt/autocicd/autocicd "$@"
LAUNCHER
    chmod +x "$DEB_DIR/usr/bin/autocicd"
    
    # 复制图标
    cp "$PROJECT_ROOT/desktop/icons/icon.png" \
       "$DEB_DIR/usr/share/icons/hicolor/256x256/apps/autocicd.png"
    
    # 创建桌面入口文件
    cat > "$DEB_DIR/usr/share/applications/autocicd.desktop" << DESKTOP
[Desktop Entry]
Name=CI/CD 流水线自动搭建平台
Name[zh_CN]=CI/CD 流水线自动搭建平台
Comment=自动搭建 CI/CD 流水线
Exec=/usr/bin/autocicd
Icon=autocicd
Terminal=false
Type=Application
Categories=Development;BuildTool;
DESKTOP
    
    # 创建 control 文件
    cat > "$DEB_DIR/DEBIAN/control" << CONTROL
Package: autocicd
Version: $VERSION
Architecture: $ARCH
Maintainer: AutoCICD <support@autocicd.com>
Description: CI/CD 流水线自动搭建平台
 自动搭建 Jenkins、GitLab Runner 等 CI/CD 工具
 支持多平台、多架构、国产操作系统
CONTROL
    
    # 构建 .deb
    DEB_PATH="$PROJECT_ROOT/dist/autocicd_${VERSION}_${ARCH}.deb"
    dpkg-deb --build "$DEB_DIR" "$DEB_PATH"
    
    # 清理
    rm -rf "$DEB_DIR"
    
    echo "  .deb 安装包: $DEB_PATH"
}

# ============================================
# 创建 .AppImage (简化版)
# ============================================
create_appimage() {
    echo "创建 AppImage..."
    
    APPIMAGE_DIR="$PROJECT_ROOT/dist/appimage-build"
    rm -rf "$APPIMAGE_DIR"
    
    # 创建目录结构
    mkdir -p "$APPIMAGE_DIR/usr/bin"
    mkdir -p "$APPIMAGE_DIR/usr/share/applications"
    mkdir -p "$APPIMAGE_DIR/usr/share/icons/hicolor/256x256/apps"
    
    # 复制可执行文件
    cp "$EXEC_PATH" "$APPIMAGE_DIR/usr/bin/autocicd"
    chmod +x "$APPIMAGE_DIR/usr/bin/autocicd"
    
    # 复制图标
    cp "$PROJECT_ROOT/desktop/icons/icon.png" \
       "$APPIMAGE_DIR/usr/share/icons/hicolor/256x256/apps/autocicd.png"
    
    # 创建桌面入口文件
    cat > "$APPIMAGE_DIR/usr/share/applications/autocicd.desktop" << DESKTOP
[Desktop Entry]
Name=CI/CD 流水线自动搭建平台
Comment=自动搭建 CI/CD 流水线
Exec=autocicd
Icon=autocicd
Terminal=false
Type=Application
Categories=Development;BuildTool;
DESKTOP
    
    # 创建 AppRun
    cat > "$APPIMAGE_DIR/AppRun" << 'APPRUN'
#!/bin/bash
HERE="$(dirname "$(readlink -f "$0")")"
exec "$HERE/usr/bin/autocicd" "$@"
APPRUN
    chmod +x "$APPIMAGE_DIR/AppRun"
    
    # 如果有 appimagetool，打包为 .AppImage
    if command -v appimagetool &>/dev/null; then
        APPIMAGE_PATH="$PROJECT_ROOT/dist/AutoCICD-${ARCH}.AppImage"
        appimagetool "$APPIMAGE_DIR" "$APPIMAGE_PATH"
        echo "  AppImage: $APPIMAGE_PATH"
    else
        echo "  AppImage 目录已准备: $APPIMAGE_DIR"
        echo "  安装 appimagetool 后可打包为 .AppImage 文件"
    fi
    
    # 清理（如果已生成 AppImage）
    if command -v appimagetool &>/dev/null; then
        rm -rf "$APPIMAGE_DIR"
    fi
}

# 执行
create_deb
create_appimage

echo ""
echo "=========================================="
echo "  Linux 安装包创建完成！"
echo "=========================================="
echo ""
echo "安装方式："
echo "  Debian/Ubuntu: sudo dpkg -i dist/autocicd_${VERSION}_${ARCH}.deb"
echo "  AppImage:      chmod +x dist/AutoCICD-${ARCH}.AppImage && ./dist/AutoCICD-${ARCH}.AppImage"
