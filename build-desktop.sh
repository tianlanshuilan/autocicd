#!/bin/bash
# CI/CD 流水线自动搭建平台 - 桌面应用构建脚本 (Linux/macOS)
# 使用方法: ./build-desktop.sh

set -e

echo "=========================================="
echo "  CI/CD 流水线自动搭建平台 - 桌面应用构建"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 检查依赖
check_deps() {
    echo -e "${YELLOW}检查依赖...${NC}"
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: 未找到 Python 3${NC}"
        exit 1
    fi
    
    if ! command -v node &> /dev/null; then
        echo -e "${RED}错误: 未找到 Node.js${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ 依赖检查通过${NC}"
}

# 安装依赖
install_deps() {
    echo -e "${YELLOW}安装依赖...${NC}"
    
    # Python 依赖
    pip3 install -r requirements.txt
    pip3 install pyinstaller pywebview
    
    # 前端依赖
    cd frontend
    npm install
    cd ..
    
    echo -e "${GREEN}✓ 依赖安装完成${NC}"
}

# 构建前端
build_frontend() {
    echo -e "${YELLOW}构建前端...${NC}"
    cd frontend
    npm run build
    cd ..
    
    if [ ! -d "frontend/dist" ]; then
        echo -e "${RED}错误: 前端构建失败${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ 前端构建完成${NC}"
}

# 生成图标
generate_icons() {
    echo -e "${YELLOW}生成应用图标...${NC}"
    python3 -c "
from PIL import Image
import os

src = 'frontend/public/favicon.png'
icon_dir = 'desktop/icons'
os.makedirs(icon_dir, exist_ok=True)

if not os.path.exists(src):
    print('WARNING: favicon.png 不存在，跳过图标生成')
    exit(0)

img = Image.open(src).convert('RGBA')

# 生成各尺寸 PNG
for s in [16, 24, 32, 48, 64, 128, 256, 512]:
    img.resize((s, s), Image.LANCZOS).save(os.path.join(icon_dir, f'icon-{s}.png'))

# 主图标
img.resize((256, 256), Image.LANCZOS).save(os.path.join(icon_dir, 'icon.png'))

# Windows .ico
img.save(os.path.join(icon_dir, 'icon.ico'), format='ICO',
         sizes=[(16,16), (32,32), (48,48), (64,64), (128,128), (256,256)])

# macOS .icns
iconset = os.path.join(icon_dir, 'icon.iconset')
os.makedirs(iconset, exist_ok=True)
icns_map = {
    'icon_16x16.png': 16, 'icon_16x16@2x.png': 32,
    'icon_32x32.png': 32, 'icon_32x32@2x.png': 64,
    'icon_128x128.png': 128, 'icon_128x128@2x.png': 256,
    'icon_256x256.png': 256, 'icon_256x256@2x.png': 512,
    'icon_512x512.png': 512, 'icon_512x512@2x.png': 1024,
}
for name, size in icns_map.items():
    img.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, name))
os.system(f'iconutil -c icns {iconset} -o {os.path.join(icon_dir, \"icon.icns\")} 2>/dev/null')
import shutil
shutil.rmtree(iconset, ignore_errors=True)
print('图标生成完成')
" 2>/dev/null || echo -e "${YELLOW}图标生成跳过（需要 Pillow）${NC}"
}

# 打包桌面应用
build_desktop() {
    echo -e "${YELLOW}打包桌面应用...${NC}"
    
    # 清理旧的构建
    rm -rf build dist/AutoCICD dist/AutoCICD.app
    
    # 运行 PyInstaller
    pyinstaller auto-cicd-desktop.spec --clean --noconfirm
    
    echo -e "${GREEN}✓ 桌面应用打包完成${NC}"
}

# 创建安装包
build_installer() {
    local os_name=$(uname -s)
    
    echo -e "${YELLOW}创建安装包...${NC}"
    
    if [ "$os_name" = "Darwin" ]; then
        # macOS DMG
        chmod +x desktop/installer/macos/build-dmg.sh
        ./desktop/installer/macos/build-dmg.sh
    elif [ "$os_name" = "Linux" ]; then
        # Linux deb/AppImage
        chmod +x desktop/installer/linux/build-package.sh
        ./desktop/installer/linux/build-package.sh
    fi
}

# 显示结果
show_result() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  桌面应用构建成功！${NC}"
    echo "=========================================="
    echo ""
    
    local os_name=$(uname -s)
    if [ "$os_name" = "Darwin" ]; then
        echo "应用位置:"
        echo "  dist/AutoCICD/AutoCICD.app"
        echo ""
        echo "DMG 安装包:"
        echo "  dist/AutoCICD-Installer.dmg"
        echo ""
        echo "运行方式:"
        echo "  open dist/AutoCICD/AutoCICD.app"
    elif [ "$os_name" = "Linux" ]; then
        echo "可执行文件:"
        echo "  dist/AutoCICD"
        echo ""
        echo "安装包:"
        echo "  dist/autocicd_1.0.0_*.deb"
        echo ""
        echo "运行方式:"
        echo "  ./dist/AutoCICD"
    fi
    echo ""
}

# 主流程
main() {
    check_deps
    install_deps
    build_frontend
    generate_icons
    build_desktop
    build_installer
    show_result
}

# 支持参数
case "$1" in
    --frontend-only)
        build_frontend
        ;;
    --desktop-only)
        build_desktop
        show_result
        ;;
    --installer-only)
        build_installer
        ;;
    --skip-deps)
        build_frontend
        generate_icons
        build_desktop
        build_installer
        show_result
        ;;
    *)
        main
        ;;
esac
