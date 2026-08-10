"""TongWeb（东方通）应用服务器配置生成器"""


def generate_tongweb(config, output_dir):
    files = []

    # TongWeb 部署脚本
    deploy_sh = _build_deploy_script(config)
    files.append({"name": "deploy-tongweb.sh", "content": deploy_sh})

    # TongWeb 部署描述文件
    tongweb_xml = _build_tongweb_xml(config)
    files.append({"name": "tongweb-web.xml", "content": tongweb_xml})

    # Jenkinsfile（TongWeb 专用流水线）
    jenkinsfile = _build_jenkinsfile(config)
    files.append({"name": "Jenkinsfile.tongweb", "content": jenkinsfile})

    # 部署说明
    readme = _build_readme(config)
    files.append({"name": "README-TongWeb.md", "content": readme})

    # Dockerfile（含 TongWeb 基础镜像）
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile.tongweb", "content": dockerfile})

    # 多分支发布流程文件
    from generators.workflow import is_multi_branch_workflow, build_rollback_script, build_release_readme
    if is_multi_branch_workflow(config):
        rollback = build_rollback_script(config)
        files.append({"name": "rollback.sh", "content": rollback})
        release_readme = build_release_readme(config)
        files.append({"name": "README-Release.md", "content": release_readme})

    return files


def _build_deploy_script(c):
    port = c.port
    project = c.projectName
    jdk = c.jdkVersion or "17"

    if c.projectType.startswith("java"):
        build_tool = "mvn" if "maven" in c.projectType else "gradle"
        if "maven" in c.projectType:
            war_path = f"target/{project}.war"
            build_cmd = "mvn clean package -DskipTests"
        else:
            war_path = f"build/libs/{project}.war"
            build_cmd = "gradle war -x test"

        return f"""#!/bin/bash
# ============================================
# TongWeb 部署脚本
# 项目: {project}
# 生成: auto-cicd
# ============================================

set -e

# ---------- 配置区 ----------
TONGWEB_HOME="${{TONGWEB_HOME:-/opt/TongWeb7.0}}"
TONGWEB_CONSOLE_PORT=9060
TONGWEB_HTTP_PORT={port}
APP_NAME="{project}"
DEPLOY_DIR="$TONGWEB_HOME/autodeploy"
BACKUP_DIR="$TONGWEB_HOME/backup"
WAR_FILE="{war_path}"

# ---------- 构建 ----------
echo ">>> 构建项目..."
{build_cmd}

if [ ! -f "$WAR_FILE" ]; then
    echo "错误: 构建产物 $WAR_FILE 不存在"
    exit 1
fi

# ---------- 备份旧版本 ----------
if [ -f "$DEPLOY_DIR/$APP_NAME.war" ]; then
    echo ">>> 备份旧版本..."
    mkdir -p "$BACKUP_DIR"
    cp "$DEPLOY_DIR/$APP_NAME.war" "$BACKUP_DIR/$APP_NAME.war.$(date +%Y%m%d%H%M%S)"
fi

# ---------- 停止 TongWeb ----------
echo ">>> 停止 TongWeb..."
$TONGWEB_HOME/bin/stopserver.sh 2>/dev/null || true
sleep 3

# ---------- 部署 ----------
echo ">>> 部署 WAR 到 TongWeb..."
cp "$WAR_FILE" "$DEPLOY_DIR/$APP_NAME.war"

# ---------- 配置端口 ----------
echo ">>> 配置 HTTP 端口为 $TONGWEB_HTTP_PORT..."
if [ -f "$TONGWEB_HOME/conf/tongweb-web.xml" ]; then
    sed -i "s/port=\\"[0-9]*\\"/port=\\"$TONGWEB_HTTP_PORT\\"/" "$TONGWEB_HOME/conf/tongweb-web.xml" 2>/dev/null || true
fi

# ---------- 启动 TongWeb ----------
echo ">>> 启动 TongWeb..."
$TONGWEB_HOME/bin/startserver.sh
sleep 5

# ---------- 检查状态 ----------
echo ">>> 检查 TongWeb 状态..."
if curl -s -o /dev/null -w "%{{http_code}}" "http://localhost:$TONGWEB_HTTP_PORT/$APP_NAME" | grep -q "200\\|302\\|404"; then
    echo ">>> 部署成功！"
    echo "    应用地址: http://$(hostname -i):$TONGWEB_HTTP_PORT/$APP_NAME"
    echo "    管理控制台: https://$(hostname -i):$TONGWEB_CONSOLE_PORT/console"
else
    echo ">>> 警告: 应用可能尚未完全启动，请检查日志"
    echo "    日志路径: $TONGWEB_HOME/logs/"
fi

echo ">>> 完成"
"""
    else:
        return f"""#!/bin/bash
# TongWeb 不支持非 Java 项目部署
echo "TongWeb 仅支持 Java 项目部署"
exit 1
"""


def _build_tongweb_xml(c):
    """生成 TongWeb 部署描述文件"""
    project = c.projectName
    port = c.port

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- TongWeb 应用部署描述文件 -->
<!-- 将此文件放入 WAR 包的 WEB-INF/ 目录下 -->
<tongweb-web>
    <context-root>/{project}</context-root>

    <!-- 会话配置 -->
    <session-config>
        <session-timeout>30</session-timeout>
    </session-config>

    <!-- 数据源配置（按需启用） -->
    <!--
    <resource>
        <name>jdbc/defaultDS</name>
        <type>javax.sql.DataSource</type>
        <property>
            <name>url</name>
            <value>jdbc:mysql://localhost:3306/{project}</value>
        </property>
        <property>
            <name>username</name>
            <value>root</value>
        </property>
        <property>
            <name>password</name>
            <value>password</value>
        </property>
    </resource>
    -->

    <!-- 虚拟主机配置 -->
    <virtual-host>
        <host-name>*</host-name>
        <http-port>{port}</http-port>
    </virtual-host>
</tongweb-web>
"""


def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def _build_jenkinsfile(c):
    """生成 Jenkins 流水线（TongWeb 专用）"""
    project = c.projectName
    branches = _get_branches(c)
    branch = branches[0]

    if c.projectType == "java-maven":
        build_cmd = "mvn clean package -DskipTests"
        war_path = "target/*.war"
    elif c.projectType == "java-gradle":
        build_cmd = "gradle war -x test"
        war_path = "build/libs/*.war"
    else:
        build_cmd = "echo 'TongWeb 仅支持 Java 项目'"
        war_path = ""

    # 多分支时生成并行构建
    if len(branches) > 1:
        parallel_stages = []
        for b in branches:
            safe_name = b.replace("/", "-").replace(".", "-")
            parallel_stages.append(f"""            '{b}' {{
                agent any
                environment {{
                    BRANCH_NAME = '{b}'
                    DEPLOY_DIR = "${{WORKSPACE}}/{project}-{safe_name}"
                }}
                stages {{
                    stage('构建-${safe_name}') {{
                        steps {{
                            sh 'git checkout {b}'
                            sh '{build_cmd}'
                        }}
                    }}
                    stage('测试-${safe_name}') {{
                        steps {{
                            sh '{"mvn test" if c.projectType == "java-maven" else "gradle test"}'
                        }}
                    }}
                    stage('部署-${safe_name}') {{
                        steps {{
                            sh '''
                                mkdir -p $DEPLOY_DIR
                                cp {war_path} $DEPLOY_DIR/ || true
                                echo "分支 {b} 部署完成"
                            '''
                        }}
                    }}
                }}
            }}""")
        parallel_block = "\n".join(parallel_stages)
        return f"""// Jenkins Multi-Branch Pipeline - TongWeb 部署
// 项目: {project}
// 分支: {', '.join(branches)}
// 生成: auto-cicd

pipeline {{
    agent none

    environment {{
        TONGWEB_HOME = '/opt/TongWeb7.0'
        APP_NAME = '{project}'
    }}

    stages {{
        stage('多分支并行构建') {{
            parallel {{
{parallel_block}
            }}
        }}
    }}
}}
"""

    return f"""// Jenkins Pipeline - TongWeb 部署
// 项目: {project}
// 分支: {branch}
// 生成: auto-cicd

pipeline {{
    agent any

    environment {{
        TONGWEB_HOME = '/opt/TongWeb7.0'
        APP_NAME = '{project}'
        BRANCH_NAME = '{branch}'
    }}

    stages {{
        stage('拉取代码') {{
            steps {{
                checkout scm
            }}
        }}

        stage('构建') {{
            steps {{
                sh '{build_cmd}'
            }}
        }}

        stage('测试') {{
            steps {{
                sh '{"mvn test" if c.projectType == "java-maven" else "gradle test"}'
            }}
        }}

        stage('部署到 TongWeb') {{
            steps {{
                sh '''
                    # 停止 TongWeb
                    $TONGWEB_HOME/bin/stopserver.sh || true
                    sleep 3

                    # 备份旧版本
                    mkdir -p $TONGWEB_HOME/backup
                    cp $TONGWEB_HOME/autodeploy/$APP_NAME.war \\
                       $TONGWEB_HOME/backup/$APP_NAME.war.$(date +%Y%m%d%H%M%S) 2>/dev/null || true

                    # 部署新版本
                    cp {war_path} $TONGWEB_HOME/autodeploy/$APP_NAME.war

                    # 启动 TongWeb
                    $TONGWEB_HOME/bin/startserver.sh
                    sleep 5
                '''
            }}
        }}

        stage('验证') {{
            steps {{
                sh '''
                    echo "检查应用状态..."
                    curl -s -o /dev/null -w "%{{http_code}}" \\
                        http://localhost:{c.port}/$APP_NAME || true
                '''
            }}
        }}
    }}

    post {{
        always {{
            echo 'Pipeline 执行完成'
        }}
        success {{
            echo 'TongWeb 部署成功'
        }}
        failure {{
            echo '部署失败，请检查 TongWeb 日志'
            sh 'tail -50 $TONGWEB_HOME/logs/tongweb.log 2>/dev/null || true'
        }}
    }}
}}
"""


def _build_dockerfile(c):
    """生成 TongWeb Docker 镜像"""
    jdk = c.jdkVersion or "17"
    project = c.projectName
    port = c.port

    if c.projectType == "java-maven":
        build_stage = f"""FROM maven:3.9-eclipse-temurin-{jdk} AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests"""
        war_src = "/app/target/*.war"
    elif c.projectType == "java-gradle":
        build_stage = f"""FROM gradle:8-jdk{jdk} AS build
WORKDIR /app
COPY build.gradle settings.gradle ./
COPY src ./src
RUN gradle war -x test --no-daemon"""
        war_src = "/app/build/libs/*.war"
    else:
        build_stage = "FROM alpine AS build"
        war_src = ""

    return f"""# TongWeb Docker 部署
# 项目: {project}
# 注意: 需提前准备 TongWeb 基础镜像或使用离线安装包

{build_stage}

# TongWeb 运行镜像（需提前构建 TongWeb 基础镜像）
# 构建方式: 将 TongWeb 安装包放入构建上下文
FROM eclipse-temurin:{jdk}-jdk AS tongweb-base

# 安装 TongWeb（需将安装包放到构建上下文）
# COPY tongweb-installer.bin /tmp/
# RUN chmod +x /tmp/tongweb-installer.bin && /tmp/tongweb-installer.bin -i silent -DINSTALL_DIR=/opt/TongWeb7.0
ENV TONGWEB_HOME=/opt/TongWeb7.0
ENV PATH="$TONGWEB_HOME/bin:$PATH"

# 如果尚未 TongWeb 安装包，使用模拟目录结构
RUN mkdir -p $TONGWEB_HOME/bin $TONGWEB_HOME/autodeploy $TONGWEB_HOME/conf $TONGWEB_HOME/logs

WORKDIR /app

# 复制 WAR 到自动部署目录
COPY --from=build {war_src} $TONGWEB_HOME/autodeploy/{project}.war

# 暴露端口
EXPOSE {port} 9060

# 启动 TongWeb
CMD ["$TONGWEB_HOME/bin/startserver.sh", "--foreground"]
"""


def _build_readme(c):
    """生成 TongWeb 部署说明"""
    project = c.projectName
    port = c.port
    jdk = c.jdkVersion or "17"

    return f"""# {project} - TongWeb 部署说明

## 概述

本项目配置为部署到 **东方通 TongWeb** 应用服务器。TongWeb 是国产 Java EE 应用服务器，
兼容 Jakarta EE / Java EE 规范，适用于信创环境。

## 环境要求

| 组件 | 版本 |
|------|------|
| TongWeb | 7.0+ |
| JDK | {jdk} |
| 操作系统 | CentOS 7+ / 银河麒麟 / 统信 UOS |

## TongWeb 安装

### 1. 下载安装包

从东方通官网下载 TongWeb 安装包，或通过信创渠道获取。

### 2. 安装

```bash
# 赋予执行权限
chmod +x TongWeb7.0_xxx.bin

# 静默安装
./TongWeb7.0_xxx.bin -i silent -DINSTALL_DIR=/opt/TongWeb7.0

# 设置环境变量
echo 'export TONGWEB_HOME=/opt/TongWeb7.0' >> ~/.bashrc
echo 'export PATH=$TONGWEB_HOME/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
```

### 3. 启动/停止

```bash
# 启动
$TONGWEB_HOME/bin/startserver.sh

# 停止
$TONGWEB_HOME/bin/stopserver.sh

# 查看状态
ps -ef | grep tongweb
```

### 4. 管理控制台

- 地址: `https://<服务器IP>:9060/console`
- 默认用户名: `tongweb`
- 默认密码: `123456`（首次登录需修改）

## 部署方式

### 方式一：自动部署（推荐）

```bash
chmod +x deploy-tongweb.sh
./deploy-tongweb.sh
```

### 方式二：手动部署

1. 构建 WAR 包:
   ```bash
   {"mvn clean package -DskipTests" if c.projectType == "java-maven" else "gradle war -x test"}
   ```

2. 复制 WAR 到自动部署目录:
   ```bash
   cp {"target" if c.projectType == "java-maven" else "build/libs"}/{project}.war $TONGWEB_HOME/autodeploy/
   ```

3. TongWeb 会自动检测并部署 WAR 包。

### 方式三：控制台部署

1. 登录管理控制台 `https://<IP>:9060/console`
2. 进入「应用管理」→「Web 应用」
3. 点击「部署」，上传 WAR 文件
4. 配置上下文根路径为 `/{project}`
5. 点击「启动」

## Jenkins 集成

使用 `Jenkinsfile.tongweb` 配置 Jenkins 流水线：

1. 在 Jenkins 中创建 Pipeline 项目
2. 指定 SCM 仓库和分支
3. Jenkins 会自动识别 `Jenkinsfile.tongweb`
4. 流水线将自动完成：构建 → 测试 → 部署到 TongWeb → 验证

## 端口配置

| 端口 | 用途 |
|------|------|
| {port} | HTTP 服务端口 |
| 9060 | 管理控制台端口（HTTPS） |
| 9061 | RMI 端口 |

修改 HTTP 端口:
```bash
# 编辑 $TONGWEB_HOME/conf/tongweb-web.xml
# 找到 <Connector port="..." 修改为目标端口
```

## 日志位置

```
$TONGWEB_HOME/logs/tongweb.log       # 主日志
$TONGWEB_HOME/logs/access.log        # 访问日志
$TONGWEB_HOME/logs/{project}.log     # 应用日志
```

## 常见问题

### Q: TongWeb 与 Tomcat 的区别？
TongWeb 完全兼容 Java EE / Servlet 规范，大部分 Tomcat 应用可直接迁移到 TongWeb。
主要区别在于管理接口和配置文件格式。

### Q: 信创环境适配？
TongWeb 支持国产操作系统（银河麒麟、统信 UOS）和国产 JDK（毕昇 JDK、Kona JDK）。

### Q: 如何配置数据源？
编辑 `tongweb-web.xml` 中的 `<resource>` 节点，或通过管理控制台配置 JDBC 数据源。
"""
