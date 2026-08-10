"""Runner 配置生成器 - 支持 GitLab Runner 和 GitHub Actions Runner"""


def generate_runner(config, output_dir):
    files = []

    # GitLab Runner 注册和配置脚本
    runner_setup = _build_runner_setup(config)
    files.append({"name": "setup-runner.sh", "content": runner_setup})

    # GitLab Runner 配置文件
    runner_config = _build_runner_config(config)
    files.append({"name": "config.toml", "content": runner_config})

    # GitHub Actions Runner 安装脚本
    github_runner_setup = _build_github_runner_setup(config)
    files.append({"name": "setup-github-runner.sh", "content": github_runner_setup})

    # 部署说明
    readme = _build_readme(config)
    files.append({"name": "README-Runner.md", "content": readme})

    # systemd 服务文件
    service = _build_systemd_service(config)
    files.append({"name": "gitlab-runner.service", "content": service})

    return files


def _build_runner_setup(c):
    """GitLab Runner 安装和注册脚本"""
    project = c.projectName
    return f"""#!/bin/bash
# ============================================
# GitLab Runner 安装与注册脚本
# 项目: {project}
# 生成: auto-cicd
# ============================================

set -e

echo "========================================="
echo "  GitLab Runner 自动安装脚本"
echo "========================================="

# ---------- 检测操作系统 ----------
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    OS=$(uname -s)
fi

echo ">>> 检测到操作系统: $OS"

# ---------- 安装 GitLab Runner ----------
echo ">>> 安装 GitLab Runner..."

case "$OS" in
    ubuntu|debian)
        curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
        sudo apt-get install -y gitlab-runner
        ;;
    centos|rhel|fedora|rocky|almalinux)
        curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh | sudo bash
        sudo yum install -y gitlab-runner
        ;;
    darwin)
        brew install gitlab-runner
        ;;
    *)
        echo "不支持的操作系统: $OS，请手动安装"
        echo "参考: https://docs.gitlab.com/runner/install/"
        exit 1
        ;;
esac

echo ">>> GitLab Runner 安装完成"
gitlab-runner --version

# ---------- 注册 Runner ----------
echo ""
echo "========================================="
echo "  注册 Runner"
echo "========================================="
echo ""
echo "请在 GitLab 中获取以下信息:"
echo "  1. 进入项目 → Settings → CI/CD → Runners"
echo "  2. 点击 'New project runner'"
echo "  3. 记录 Runner URL 和 Registration Token"
echo ""

read -p "GitLab URL (例如 https://gitlab.com): " GITLAB_URL
read -p "Registration Token: " REGISTRATION_TOKEN
read -p "Runner 描述 [默认: {project}-runner]: " DESCRIPTION
DESCRIPTION=${{DESCRIPTION:-{project}-runner}}
read -p "执行器类型 [docker/shell/ssh] (默认: shell): " EXECUTOR
EXECUTOR=${{EXECUTOR:-shell}}

echo ">>> 注册 Runner..."
sudo gitlab-runner register \\
    --non-interactive \\
    --url "$GITLAB_URL" \\
    --registration-token "$REGISTRATION_TOKEN" \\
    --description "$DESCRIPTION" \\
    --executor "$EXECUTOR" \\
    --tag-list "{project}" \\
    --run-untagged=true

echo ">>> Runner 注册成功！"

# ---------- 启动服务 ----------
echo ">>> 启动 GitLab Runner 服务..."
sudo gitlab-runner start
sudo gitlab-runner verify

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "管理命令:"
echo "  查看状态: sudo gitlab-runner status"
echo "  重启服务: sudo gitlab-runner restart"
echo "  查看日志: sudo journalctl -u gitlab-runner -f"
echo "  注销 Runner: sudo gitlab-runner unregister --all"
"""


def _build_runner_config(c):
    """GitLab Runner config.toml 模板"""
    project = c.projectName
    return f"""# GitLab Runner 配置文件
# 项目: {project}
# 路径: /etc/gitlab-runner/config.toml
# 生成: auto-cicd

concurrent = 1
check_interval = 0
shutdown_timeout = 15

[session_server]
  session_timeout = 1800

# Shell 执行器
[[runners]]
  name = "{project}-runner"
  url = "https://gitlab.com/"
  id = 0
  token = ""
  token_obtained_at = 0
  token_expires_at = 0
  executor = "shell"
  shell = "bash"
  [runners.custom_build_dir]
  [runners.cache]
    MaxUploadedArchiveSize = 0
    [runners.cache.s3]
    [runners.cache.gcs]
    [runners.cache.azure]

# Docker 执行器（可选，取消注释启用）
# [[runners]]
#   name = "{project}-docker-runner"
#   url = "https://gitlab.com/"
#   executor = "docker"
#   [runners.docker]
#     image = "alpine:latest"
#     privileged = false
#     disable_entrypoint_overwrite = false
#     oom_kill_disable = false
#     disable_cache = false
#     volumes = ["/cache"]
#     shm_size = 0
#     pull_policy = ["if-not-present"]
#   [runners.cache]
#     MaxUploadedArchiveSize = 0
"""


def _build_github_runner_setup(c):
    """GitHub Actions Runner 安装脚本"""
    project = c.projectName
    return f"""#!/bin/bash
# ============================================
# GitHub Actions Runner (Self-hosted) 安装脚本
# 项目: {project}
# 生成: auto-cicd
# ============================================

set -e

echo "========================================="
echo "  GitHub Actions Runner 安装脚本"
echo "========================================="

# ---------- 配置 ----------
RUNNER_DIR="/opt/github-runner/{project}"
RUNNER_USER="${{SUDO_USER:-$(whoami)}}"

# ---------- 获取 Token ----------
echo ""
echo "请在 GitHub 中获取 Runner Token:"
echo "  1. 进入仓库 → Settings → Actions → Runners"
echo "  2. 点击 'New self-hosted runner'"
echo "  3. 选择 Linux/macOS，记录 Token"
echo ""
read -p "GitHub Runner Token: " RUNNER_TOKEN
read -p "GitHub 仓库 URL (例如 https://github.com/owner/repo): " REPO_URL

# ---------- 创建目录 ----------
echo ">>> 创建 Runner 目录: $RUNNER_DIR"
sudo mkdir -p "$RUNNER_DIR"
sudo chown "$RUNNER_USER" "$RUNNER_DIR"

# ---------- 下载 Runner ----------
echo ">>> 下载 GitHub Actions Runner..."
RUNNER_VERSION="2.317.0"
ARCH=$(uname -m)
case "$ARCH" in
    x86_64) ARCH_LABEL="x64" ;;
    aarch64|arm64) ARCH_LABEL="arm64" ;;
    *) echo "不支持的架构: $ARCH"; exit 1 ;;
esac

cd "$RUNNER_DIR"
curl -o actions-runner.tar.gz \\
    -L "https://github.com/actions/runner/releases/download/v${{RUNNER_VERSION}}/actions-runner-linux-${{ARCH_LABEL}}-${{RUNNER_VERSION}}.tar.gz"

tar xzf actions-runner.tar.gz
rm actions-runner.tar.gz

# ---------- 安装依赖 ----------
echo ">>> 安装依赖..."
if [ -f /etc/os-release ]; then
    . /etc/os-release
    case "$ID" in
        ubuntu|debian)
            sudo apt-get install -y libicu-dev
            ;;
        centos|rhel|fedora)
            sudo yum install -y libicu
            ;;
    esac
fi

# ---------- 配置 Runner ----------
echo ">>> 配置 Runner..."
./config.sh --url "$REPO_URL" --token "$RUNNER_TOKEN" --name "{project}-runner" --unattended

# ---------- 安装为服务 ----------
echo ">>> 安装为系统服务..."
sudo ./svc.sh install "$RUNNER_USER"
sudo ./svc.sh start

echo ""
echo "========================================="
echo "  安装完成！"
echo "========================================="
echo ""
echo "管理命令:"
echo "  查看状态: cd $RUNNER_DIR && sudo ./svc.sh status"
echo "  重启服务: cd $RUNNER_DIR && sudo ./svc.sh restart"
echo "  查看日志: cd $RUNNER_DIR && tail -f _diag/*.log"
echo "  停止服务: cd $RUNNER_DIR && sudo ./svc.sh stop"
"""


def _build_systemd_service(c):
    """GitLab Runner systemd 服务文件"""
    project = c.projectName
    return f"""[Unit]
Description=GitLab Runner ({project})
Documentation=https://docs.gitlab.com/runner/
After=syslog.target network.target

[Service]
Type=simple
ExecStart=/usr/bin/gitlab-runner run --working-directory /home/gitlab-runner --config /etc/gitlab-runner/config.toml --service gitlab-runner --syslog
ExecReload=/bin/kill -HUP $MAINPID
ExecStop=/bin/kill -QUIT $MAINPID
Restart=always
RestartSec=10

User=gitlab-runner
Group=gitlab-runner

# 安全设置
ProtectSystem=full
ProtectHome=true
PrivateTmp=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""


def _build_readme(c):
    """Runner 部署说明"""
    project = c.projectName

    return f"""# {project} - Runner 部署说明

## 概述

本文档说明如何在服务器上部署 **Self-hosted Runner**，用于执行 CI/CD 流水线任务。
支持 GitLab Runner 和 GitHub Actions Runner 两种类型。

## 为什么需要 Self-hosted Runner？

| 场景 | 说明 |
|------|------|
| 内网部署 | 代码和构建过程不离开内网，满足安全合规要求 |
| 特殊环境 | 需要访问内网资源（数据库、私有仓库等） |
| 性能优化 | 使用高性能服务器构建，避免共享 Runner 排队 |
| 信创环境 | 在国产操作系统上运行流水线 |

## 方案一：GitLab Runner

### 安装

```bash
# 自动安装（推荐）
chmod +x setup-runner.sh
sudo ./setup-runner.sh

# 或手动安装
# Ubuntu/Debian
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | sudo bash
sudo apt-get install -y gitlab-runner

# CentOS/RHEL
curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh | sudo bash
sudo yum install -y gitlab-runner
```

### 注册

```bash
# 交互式注册
sudo gitlab-runner register

# 按提示输入:
#   GitLab URL: https://your-gitlab.com
#   Token: (从项目 Settings → CI/CD → Runners 获取)
#   Description: {project}-runner
#   Executor: shell (或 docker)
#   Tags: {project}
```

### 执行器类型

| 执行器 | 适用场景 | 隔离性 |
|--------|----------|--------|
| shell | 简单项目，直接使用宿主机环境 | 低 |
| docker | 需要环境隔离，每次构建使用新容器 | 高 |
| ssh | 远程构建到指定服务器 | 中 |
| kubernetes | K8s 集群弹性构建 | 高 |

### 管理

```bash
# 查看状态
sudo gitlab-runner status

# 查看运行中的任务
sudo gitlab-runner verify

# 查看日志
sudo journalctl -u gitlab-runner -f

# 重启
sudo gitlab-runner restart
```

## 方案二：GitHub Actions Runner

### 安装

```bash
# 自动安装（推荐）
chmod +x setup-github-runner.sh
sudo ./setup-github-runner.sh
```

### 手动安装

```bash
# 1. 创建目录
mkdir -p /opt/github-runner/{project} && cd /opt/github-runner/{project}

# 2. 下载（以 x64 为例）
curl -o actions-runner.tar.gz -L \\
    https://github.com/actions/runner/releases/download/v2.317.0/actions-runner-linux-x64-2.317.0.tar.gz
tar xzf actions-runner.tar.gz

# 3. 配置（Token 从仓库 Settings → Actions → Runners 获取）
./config.sh --url https://github.com/owner/repo --token YOUR_TOKEN

# 4. 安装为服务
sudo ./svc.sh install
sudo ./svc.sh start
```

## 在 .gitlab-ci.yml 中使用 Runner

```yaml
# 指定使用带 {project} 标签的 Runner
build_job:
  stage: build
  tags:
    - {project}
  script:
    - echo "在 Self-hosted Runner 上执行"
    - mvn clean package
```

## 在 GitHub Actions 中使用 Runner

```yaml
# .github/workflows/ci.yml
jobs:
  build:
    runs-on: self-hosted   # 使用 Self-hosted Runner
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: mvn clean package
```

## 安全建议

1. **网络隔离**: Runner 服务器应放在内网，仅开放必要端口
2. **最小权限**: Runner 服务使用专用低权限用户运行
3. **定期更新**: 保持 Runner 版本与 GitLab/GitHub 版本一致
4. **日志审计**: 开启 Runner 详细日志，定期审查
5. **Token 管理**: 定期轮换 Runner Registration Token

## 常见问题

### Q: Runner 离线怎么办？
```bash
sudo gitlab-runner verify    # 检查状态
sudo gitlab-runner restart   # 重启服务
```

### Q: 如何同时支持多个项目？
注册多个 Runner 或使用 `--run-untagged=true` 允许执行未标记任务。

### Q: Docker 执行器需要什么额外配置？
确保安装了 Docker，并将 gitlab-runner 用户加入 docker 组:
```bash
sudo usermod -aG docker gitlab-runner
sudo gitlab-runner restart
```
"""
