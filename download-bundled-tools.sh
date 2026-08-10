#!/bin/bash
# CI/CD 流水线自动搭建平台 - 离线安装包下载脚本
# 下载各架构的 Jenkins、Runner、JDK、Docker 离线安装包
# 使用方法: ./download-bundled-tools.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLS_DIR="$SCRIPT_DIR/bundled-tools"

echo "=========================================="
echo "  CI/CD 离线安装包下载工具"
echo "=========================================="

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 创建目录结构
create_dirs() {
    echo -e "${YELLOW}创建目录结构...${NC}"
    mkdir -p "$TOOLS_DIR"/{jenkins,runner/{amd64,arm64,arm},jdk/{x86_64,aarch64},docker/{amd64,arm64}}
    echo -e "${GREEN}✓ 目录结构创建完成${NC}"
}

# 下载 Jenkins WAR 包（跨架构通用）
download_jenkins() {
    echo -e "${YELLOW}下载 Jenkins WAR 包（通用，跨架构）...${NC}"
    
    local jenkins_url="https://get.jenkins.io/war-stable/latest/jenkins.war"
    local jenkins_file="$TOOLS_DIR/jenkins/jenkins.war"
    
    if [ -f "$jenkins_file" ]; then
        echo "Jenkins WAR 包已存在，跳过"
        return
    fi
    
    echo "下载: $jenkins_url"
    curl -fsSL -o "$jenkins_file" "$jenkins_url" || {
        echo -e "${YELLOW}官方源下载失败，尝试清华镜像...${NC}"
        curl -fsSL -o "$jenkins_file" "https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war" || {
            echo -e "${RED}✗ Jenkins 下载失败${NC}"
            return 1
        }
    }
    
    echo -e "${GREEN}✓ Jenkins WAR 包下载完成: $(du -h "$jenkins_file" | cut -f1)${NC}"
}

# 下载 GitLab Runner（多架构）
download_runner() {
    echo -e "${YELLOW}下载 GitLab Runner（多架构）...${NC}"
    
    local base_url="https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries"
    
    # amd64
    local runner_amd64="$TOOLS_DIR/runner/amd64/gitlab-runner"
    if [ ! -f "$runner_amd64" ]; then
        echo "下载: gitlab-runner-linux-amd64"
        curl -fsSL -o "$runner_amd64" "$base_url/gitlab-runner-linux-amd64" || {
            echo -e "${RED}✗ Runner amd64 下载失败${NC}"
        }
        chmod +x "$runner_amd64" 2>/dev/null || true
    else
        echo "Runner amd64 已存在，跳过"
    fi
    
    # arm64
    local runner_arm64="$TOOLS_DIR/runner/arm64/gitlab-runner"
    if [ ! -f "$runner_arm64" ]; then
        echo "下载: gitlab-runner-linux-arm64"
        curl -fsSL -o "$runner_arm64" "$base_url/gitlab-runner-linux-arm64" || {
            echo -e "${RED}✗ Runner arm64 下载失败${NC}"
        }
        chmod +x "$runner_arm64" 2>/dev/null || true
    else
        echo "Runner arm64 已存在，跳过"
    fi
    
    # arm (32-bit)
    local runner_arm="$TOOLS_DIR/runner/arm/gitlab-runner"
    if [ ! -f "$runner_arm" ]; then
        echo "下载: gitlab-runner-linux-arm"
        curl -fsSL -o "$runner_arm" "$base_url/gitlab-runner-linux-arm" || {
            echo -e "${RED}✗ Runner arm 下载失败${NC}"
        }
        chmod +x "$runner_arm" 2>/dev/null || true
    else
        echo "Runner arm 已存在，跳过"
    fi
    
    echo -e "${GREEN}✓ GitLab Runner 下载完成${NC}"
}

# 下载 OpenJDK（多架构、多版本）
download_jdk() {
    echo -e "${YELLOW}下载 OpenJDK（多架构、多版本）...${NC}"
    
    # === JDK 17 ===
    # x86_64
    local jdk_x64="$TOOLS_DIR/jdk/x86_64/openjdk.tar.gz"
    if [ ! -f "$jdk_x64" ]; then
        echo "下载: OpenJDK 17 (x86_64)"
        curl -fsSL -o "$jdk_x64" "https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-x64_bin.tar.gz" || {
            echo -e "${YELLOW}官方源失败，尝试清华镜像...${NC}"
            curl -fsSL -o "$jdk_x64" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/x64/linux/OpenJDK17U-jdk_x64_linux_hotspot_17.0.2_8.tar.gz" || {
                echo -e "${RED}✗ JDK 17 x86_64 下载失败${NC}"
            }
        }
    else
        echo "JDK 17 x86_64 已存在，跳过"
    fi
    
    # aarch64
    local jdk_arm64="$TOOLS_DIR/jdk/aarch64/openjdk.tar.gz"
    if [ ! -f "$jdk_arm64" ]; then
        echo "下载: OpenJDK 17 (aarch64)"
        curl -fsSL -o "$jdk_arm64" "https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-aarch64_bin.tar.gz" || {
            echo -e "${YELLOW}官方源失败，尝试清华镜像...${NC}"
            curl -fsSL -o "$jdk_arm64" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/aarch64/linux/OpenJDK17U-jdk_aarch64_linux_hotspot_17.0.2_8.tar.gz" || {
                echo -e "${RED}✗ JDK 17 aarch64 下载失败${NC}"
            }
        }
    else
        echo "JDK 17 aarch64 已存在，跳过"
    fi
    
    # === JDK 8 ===
    # x86_64
    local jdk8_x64="$TOOLS_DIR/jdk/x86_64/openjdk8.tar.gz"
    if [ ! -f "$jdk8_x64" ]; then
        echo "下载: OpenJDK 8 (x86_64)"
        curl -fsSL -o "$jdk8_x64" "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u422-b05/OpenJDK8U-jdk_x64_linux_hotspot_8u422b05.tar.gz" || {
            echo -e "${YELLOW}官方源失败，尝试清华镜像...${NC}"
            curl -fsSL -o "$jdk8_x64" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/x64/linux/OpenJDK8U-jdk_x64_linux_hotspot_8u422b05.tar.gz" || {
                echo -e "${RED}✗ JDK 8 x86_64 下载失败${NC}"
            }
        }
    else
        echo "JDK 8 x86_64 已存在，跳过"
    fi
    
    # aarch64
    local jdk8_arm64="$TOOLS_DIR/jdk/aarch64/openjdk8.tar.gz"
    if [ ! -f "$jdk8_arm64" ]; then
        echo "下载: OpenJDK 8 (aarch64)"
        curl -fsSL -o "$jdk8_arm64" "https://github.com/adoptium/temurin8-binaries/releases/download/jdk8u422-b05/OpenJDK8U-jdk_aarch64_linux_hotspot_8u422b05.tar.gz" || {
            echo -e "${YELLOW}官方源失败，尝试清华镜像...${NC}"
            curl -fsSL -o "$jdk8_arm64" "https://mirrors.tuna.tsinghua.edu.cn/Adoptium/8/jdk/aarch64/linux/OpenJDK8U-jdk_aarch64_linux_hotspot_8u422b05.tar.gz" || {
                echo -e "${RED}✗ JDK 8 aarch64 下载失败${NC}"
            }
        }
    else
        echo "JDK 8 aarch64 已存在，跳过"
    fi
    
    echo -e "${GREEN}✓ OpenJDK 8 和 17 下载完成${NC}"
}

# 下载 Docker 离线包（多架构）
download_docker() {
    echo -e "${YELLOW}下载 Docker 静态二进制包（多架构）...${NC}"
    
    # 使用 Docker 官方静态二进制包
    local docker_version="24.0.7"
    
    # amd64
    local docker_amd64="$TOOLS_DIR/docker/amd64/docker.tgz"
    if [ ! -f "$docker_amd64" ]; then
        echo "下载: Docker $docker_version (x86_64)"
        curl -fsSL -o "$docker_amd64" "https://download.docker.com/linux/static/stable/x86_64/docker-${docker_version}.tgz" || {
            echo -e "${YELLOW}官方源失败，尝试阿里云镜像...${NC}"
            curl -fsSL -o "$docker_amd64" "https://mirrors.aliyun.com/docker-ce/linux/static/stable/x86_64/docker-${docker_version}.tgz" || {
                echo -e "${RED}✗ Docker amd64 下载失败${NC}"
            }
        }
    else
        echo "Docker amd64 已存在，跳过"
    fi
    
    # arm64
    local docker_arm64="$TOOLS_DIR/docker/arm64/docker.tgz"
    if [ ! -f "$docker_arm64" ]; then
        echo "下载: Docker $docker_version (aarch64)"
        curl -fsSL -o "$docker_arm64" "https://download.docker.com/linux/static/stable/aarch64/docker-${docker_version}.tgz" || {
            echo -e "${YELLOW}官方源失败，尝试阿里云镜像...${NC}"
            curl -fsSL -o "$docker_arm64" "https://mirrors.aliyun.com/docker-ce/linux/static/stable/aarch64/docker-${docker_version}.tgz" || {
                echo -e "${RED}✗ Docker arm64 下载失败${NC}"
            }
        }
    else
        echo "Docker arm64 已存在，跳过"
    fi
    
    echo -e "${GREEN}✓ Docker 下载完成${NC}"
}

# 显示下载结果
show_result() {
    echo ""
    echo "=========================================="
    echo -e "${GREEN}  离线包下载完成！${NC}"
    echo "=========================================="
    echo ""
    echo "目录结构:"
    echo "  bundled-tools/"
    echo "  ├── jenkins/"
    echo "  │   └── jenkins.war          $(du -h "$TOOLS_DIR/jenkins/jenkins.war" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  ├── runner/"
    echo "  │   ├── amd64/gitlab-runner  $(du -h "$TOOLS_DIR/runner/amd64/gitlab-runner" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  │   ├── arm64/gitlab-runner  $(du -h "$TOOLS_DIR/runner/arm64/gitlab-runner" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  │   └── arm/gitlab-runner    $(du -h "$TOOLS_DIR/runner/arm/gitlab-runner" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  ├── jdk/"
    echo "  │   ├── x86_64/openjdk.tar.gz  $(du -h "$TOOLS_DIR/jdk/x86_64/openjdk.tar.gz" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  │   └── aarch64/openjdk.tar.gz $(du -h "$TOOLS_DIR/jdk/aarch64/openjdk.tar.gz" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "  └── docker/"
    echo "      ├── amd64/docker.tgz     $(du -h "$TOOLS_DIR/docker/amd64/docker.tgz" 2>/dev/null | cut -f1 || echo '未下载')"
    echo "      └── arm64/docker.tgz     $(du -h "$TOOLS_DIR/docker/arm64/docker.tgz" 2>/dev/null | cut -f1 || echo '未下载')"
    echo ""
    echo "总大小: $(du -sh "$TOOLS_DIR" 2>/dev/null | cut -f1 || echo '未知')"
    echo ""
}

# 主流程
main() {
    create_dirs
    
    case "$1" in
        --jenkins)
            download_jenkins
            ;;
        --runner)
            download_runner
            ;;
        --jdk)
            download_jdk
            ;;
        --docker)
            download_docker
            ;;
        --all|"")
            download_jenkins
            download_runner
            download_jdk
            download_docker
            show_result
            ;;
        *)
            echo "用法: $0 [--jenkins|--runner|--jdk|--docker|--all]"
            exit 1
            ;;
    esac
}

main "$@"
