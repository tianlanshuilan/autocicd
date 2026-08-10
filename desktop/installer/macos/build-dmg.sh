#!/bin/bash
#
# macOS DMG 安装包打包脚本
# 使用方法: ./build-dmg.sh
#
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
APP_NAME="AutoCICD"
APP_BUNDLE="$PROJECT_ROOT/dist/$APP_NAME.app"
DMG_PATH="$PROJECT_ROOT/dist/${APP_NAME}-Installer.dmg"
DMG_TEMP="$PROJECT_ROOT/dist/dmg_temp"
VOLUME_NAME="CI/CD 流水线自动搭建平台"

echo "=========================================="
echo "  macOS DMG 安装包打包"
echo "=========================================="

# 检查 .app 是否存在
if [ ! -d "$APP_BUNDLE" ]; then
    echo "错误: $APP_BUNDLE 不存在"
    echo "请先运行: pyinstaller auto-cicd-desktop.spec"
    exit 1
fi

# 清理旧的 DMG
rm -f "$DMG_PATH"
rm -rf "$DMG_TEMP"

# 创建临时目录
mkdir -p "$DMG_TEMP"

# 复制 .app 到临时目录
echo "复制应用..."
cp -R "$APP_BUNDLE" "$DMG_TEMP/"

# 创建 Applications 快捷方式
ln -s /Applications "$DMG_TEMP/Applications"

# 创建 DMG
echo "创建 DMG 镜像..."
hdiutil create \
    -volname "$VOLUME_NAME" \
    -srcfolder "$DMG_TEMP" \
    -ov \
    -format UDZO \
    "$DMG_PATH"

# 清理临时目录
rm -rf "$DMG_TEMP"

echo ""
echo "=========================================="
echo "  DMG 安装包创建完成！"
echo "  路径: $DMG_PATH"
echo "=========================================="
echo ""
echo "使用方法："
echo "  1. 双击 DMG 文件挂载"
echo "  2. 将 AutoCICD.app 拖入 Applications 文件夹"
echo "  3. 从 Launchpad 或 Applications 启动"
