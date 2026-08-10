#!/bin/bash
# CI/CD 流水线自动搭建平台 - 构建脚本 (Linux/macOS)
# 使用方法: ./build.sh

set -e

echo "=========================================="
echo "  CI/CD 流水线自动搭建平台 - 构建工具"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
    
    if ! command -v npm &> /dev/null; then
        echo -e "${RED}错误: 未找到 npm${NC}"
        exit 1
    fi
    
    echo -e "${GREEN}✓ 依赖检查通过${NC}"
}

# 安装 Python 依赖
install_python_deps() {
    echo -e "${YELLOW}安装 Python 依赖...${NC}"
    pip3 install -r requirements.txt
    pip3 install pyinstaller
    echo -e "${GREEN}✓ Python 依赖安装完成${NC}"
}

# 安装前端依赖
install_frontend_deps() {
    echo -e "${YELLOW}安装前端依赖...${NC}"
    cd frontend
    npm install
    cd ..
    echo -e "${GREEN}✓ 前端依赖安装完成${NC}"
}

# 构建前端
build_frontend() {
    echo -e "${YELLOW}构建前端...${NC}"
    cd frontend
    npm run build
    cd ..
    
    if [ ! -d "frontend/dist" ]; then
        echo -e "${RED}错误: 前端构建失败，未找到 frontend/dist 目录${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ 前端构建完成${NC}"
}

# 打包应用
build_app() {
    echo -e "${YELLOW}打包应用...${NC}"
    
    # 清理旧的构建
    rm -rf build dist
    rm -f auto-cicd.spec.bak
    
    # 检查离线安装包
    if [ ! -d "bundled-tools/jenkins" ] || [ ! -f "bundled-tools/jenkins/jenkins.war" ]; then
        echo -e "${YELLOW}离线安装包未下载，正在下载...${NC}"
        if [ -f "./download-bundled-tools.sh" ]; then
            chmod +x ./download-bundled-tools.sh
            ./download-bundled-tools.sh --all
        else
            echo -e "${YELLOW}警告: 离线安装包不可用，仅支持在线安装${NC}"
        fi
    else
        echo -e "${GREEN}✓ 离线安装包已就绪${NC}"
    fi
    
    # 运行 PyInstaller
    pyinstaller auto-cicd.spec --clean --noconfirm
    
    echo -e "${GREEN}✓ 应用打包完成${NC}"
}

# 输出结果
show_result() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  构建成功！${NC}"
    echo "=========================================="
    echo ""
    echo "可执行文件位置:"
    echo "  dist/auto-cicd"
    echo ""
    echo "运行方式:"
    echo "  ./dist/auto-cicd"
    echo ""
    echo "或指定端口:"
    echo "  PORT=9000 ./dist/auto-cicd"
    echo ""
}

# 主流程
main() {
    check_deps
    install_python_deps
    install_frontend_deps
    build_frontend
    build_app
    show_result
}

# 支持参数
case "$1" in
    --frontend-only)
        build_frontend
        ;;
    --app-only)
        build_app
        show_result
        ;;
    --skip-deps)
        build_frontend
        build_app
        show_result
        ;;
    *)
        main
        ;;
esac
