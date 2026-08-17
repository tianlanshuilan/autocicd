def generate_jenkins(config, output_dir):
    files = []

    # Jenkinsfile
    jenkinsfile = _build_jenkinsfile(config)
    files.append({"name": "Jenkinsfile", "content": jenkinsfile})

    # Dockerfile (if docker deploy)
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile", "content": dockerfile})
        dockerignore = _build_dockerignore(config)
        files.append({"name": ".dockerignore", "content": dockerignore})
        from generators.docker import build_docker_compose
        files.append({"name": "docker-compose.yml", "content": build_docker_compose(config)})

    # 项目基础文件
    if config.projectType.startswith("java"):
        pom = _build_pom(config)
        files.append({"name": "pom.xml", "content": pom})
    elif config.projectType in ("vue", "react"):
        pkg = _build_package_json(config)
        files.append({"name": "package.json", "content": pkg})
    elif config.projectType == "python":
        req = _build_requirements(config)
        files.append({"name": "requirements.txt", "content": req})
    elif config.projectType == "go":
        mod = _build_go_mod(config)
        files.append({"name": "go.mod", "content": mod})

    # Jenkins 部署说明
    readme = _build_jenkins_readme(config)
    files.append({"name": "README-Jenkins.md", "content": readme})

    # 多分支发布流程文件
    from generators.workflow import is_multi_branch_workflow, build_rollback_script, build_release_readme
    if is_multi_branch_workflow(config):
        rollback = build_rollback_script(config)
        files.append({"name": "rollback.sh", "content": rollback})
        release_readme = build_release_readme(config)
        files.append({"name": "README-Release.md", "content": release_readme})

    return files

def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def _build_jenkinsfile(c):
    branches = _get_branches(c)

    if len(branches) > 1:
        return _build_multibranch_jenkinsfile(c, branches)

    stages = []

    # 如果配置了独立依赖仓库，先克隆依赖仓库
    from generators.offline import has_dep_repo, dep_repo_url, dep_repo_branch
    if has_dep_repo(c):
        stages.append(_build_checkout_deps_stage(c))

    # Auto-determine build stages based on project type
    if c.projectType.startswith("java"):
        stages.append(_build_build_stage(c))  # Maven/Gradle build
    elif c.projectType == "go":
        stages.append(_build_build_stage(c))  # Go build
    elif c.projectType in ("vue", "react"):
        stages.append(_build_build_stage(c))  # npm run build
    elif c.projectType == "python":
        stages.append(_build_artifact_stage(c))  # pip install
    else:
        stages.append(_build_code_stage(c))  # Just deploy code
    stages.append(_build_test_stage(c))
    stages.append(_build_deploy_stage(c))

    stage_blocks = "\n".join(stages)

    # 服务器配置
    server_host = getattr(c, 'serverHost', '')
    server_user = getattr(c, 'serverUser', 'root')
    deploy_path = getattr(c, 'deployPath', '/opt/apps')
    
    # 堡垒机配置
    bastion_host = getattr(c, 'bastionHost', '')
    bastion_port = getattr(c, 'bastionPort', 22)
    bastion_user = getattr(c, 'bastionUser', '')
    
    # 生成 SSH 选项（用于穿透堡垒机）
    ssh_options = "-o StrictHostKeyChecking=no"
    if bastion_host and bastion_user:
        ssh_options += f" -J {bastion_user}@{bastion_host}:{bastion_port}"

    # 依赖仓库环境变量
    dep_repo_env = ""
    if has_dep_repo(c):
        dep_repo_env = f"""
        DEP_REPO_URL = '{dep_repo_url(c)}'
        DEP_REPO_BRANCH = '{dep_repo_branch(c)}'"""

    env_block = f"""    environment {{
        PROJECT_NAME = '{c.projectName}'
        REPO_URL = '{c.repoUrl}'
        BRANCH = '{branches[0]}'
        PORT = '{c.port}'
        SERVER_HOST = '{server_host}'
        SERVER_USER = '{server_user}'
        DEPLOY_PATH = '{deploy_path}'
        SSH_OPTIONS = '{ssh_options}'{dep_repo_env}
    }}"""

    return f"""// Jenkins Pipeline - {c.projectName}
// Tool: Jenkins
// Generated: auto-cicd

pipeline {{
    agent any

    triggers {{
        pollSCM('H/2 * * * *')  // 每 2 分钟轮询，有新提交自动触发
    }}

{env_block}

    stages {{
{stage_blocks}
    }}

    post {{
        always {{
            echo 'Pipeline finished'
        }}
        success {{
            echo 'Build succeeded'
        }}
        failure {{
            echo 'Build failed'
        }}
    }}
}}
"""

def _build_multibranch_jenkinsfile(c, branches):
    """生成多分支并行构建的 Jenkinsfile（含审批/合并/回滚）"""
    from generators.workflow import get_release_strategy, is_multi_branch_workflow
    strategy = get_release_strategy(c)
    main_branch = strategy.get("mainBranch", "main")
    merge_strategy = strategy.get("strategy", "auto_merge")

    branch_list = ", ".join(f"'{b}'" for b in branches)
    parallel_stages = []
    for b in branches:
        safe_name = b.replace("/", "-").replace(".", "-")
        parallel_stages.append(f"""            '{b}' {{
                agent any
                environment {{
                    BRANCH = '{b}'
                    DEPLOY_DIR = "${{WORKSPACE}}/{c.projectName}-{safe_name}"
                }}
                stages {{
{_indent_stages(_get_branch_stages(c, b), 3)}
                }}
            }}""")

    parallel_block = "\n".join(parallel_stages)

    # 审批/合并/回滚阶段
    workflow_stages = ""
    if is_multi_branch_workflow(c):
        from generators.workflow import (
            jenkins_approval_stage,
            jenkins_merge_stage,
            jenkins_reject_stage,
            jenkins_rollback_stage,
        )
        if merge_strategy in ("auto_merge", "manual_merge"):
            workflow_stages = f"""
{jenkins_approval_stage(strategy)}

{jenkins_merge_stage(strategy)}

{jenkins_reject_stage()}

{jenkins_rollback_stage(strategy)}"""

    return f"""// Jenkins Multi-Branch Pipeline - {c.projectName}
// Tool: Jenkins
// Branches: {', '.join(branches)}
// Main Branch: {main_branch}
// Release Strategy: {merge_strategy}
// Generated: auto-cicd

pipeline {{
    agent none

    triggers {{
        pollSCM('H/2 * * * *')  // 每 2 分钟轮询，有新提交自动触发
    }}

    environment {{
        PROJECT_NAME = '{c.projectName}'
        REPO_URL = '{c.repoUrl}'
        PORT = '{c.port}'
        MAIN_BRANCH = '{main_branch}'
    }}

    stages {{
        stage('多分支并行构建') {{
            parallel {{
{parallel_block}
            }}
        }}
{workflow_stages}
    }}

    post {{
        always {{
            echo 'Pipeline 执行完成'
        }}
        success {{
            echo '所有分支构建成功'
        }}
        failure {{
            echo '部分分支构建失败，请检查对应分支日志'
        }}
    }}
}}
"""

def _get_branch_stages(c, branch):
    """为指定分支生成阶段列表"""
    stages = []
    # Auto-determine build stages based on project type
    if c.projectType.startswith("java"):
        stages.append(_build_build_stage(c))  # Maven/Gradle build
    elif c.projectType == "go":
        stages.append(_build_build_stage(c))  # Go build
    elif c.projectType in ("vue", "react"):
        stages.append(_build_build_stage(c))  # npm run build
    elif c.projectType == "python":
        stages.append(_build_artifact_stage(c))  # pip install
    else:
        stages.append(_build_code_stage(c))  # Just deploy code
    stages.append(_build_test_stage(c))
    stages.append(_build_deploy_stage(c))
    return "\n".join(stages)

def _indent_stages(text, level):
    """增加缩进"""
    prefix = "    " * level
    lines = text.split("\n")
    return "\n".join(prefix + line if line.strip() else line for line in lines)

def _build_checkout_deps_stage(c):
    """生成克隆依赖仓库的阶段"""
    from generators.offline import dep_repo_url, dep_repo_branch
    return f"""        stage('Checkout Dependencies') {{
            steps {{
                echo 'Cloning dependency repository...'
                dir('.dep-repo') {{
                    git url: "${{DEP_REPO_URL}}", branch: "${{DEP_REPO_BRANCH}}", credentialsId: 'dep-repo-cred'
                }}
            }}
        }}"""

def _build_build_stage(c):
    from generators.offline import maven_build_cmd, npm_install_cmd, pip_install_cmd, go_build_cmd
    if c.projectType == "java-maven":
        return f"""        stage('Build') {{
            steps {{
                sh '{maven_build_cmd(c)}'
            }}
        }}"""
    elif c.projectType == "java-gradle":
        return """        stage('Build') {
            steps {
                sh 'gradle build -x test'
            }
        }"""
    elif c.projectType in ("vue", "react"):
        return f"""        stage('Build') {{
            steps {{
                sh '{npm_install_cmd(c)}'
                sh 'npm run build'
            }}
        }}"""
    elif c.projectType == "python":
        return f"""        stage('Build') {{
            steps {{
                sh '{pip_install_cmd(c)}'
            }}
        }}"""
    elif c.projectType == "go":
        return f"""        stage('Build') {{
            steps {{
                sh '{go_build_cmd(c)}'
            }}
        }}"""
    return ""

def _build_artifact_stage(c):
    from generators.offline import npm_install_cmd, pip_install_cmd, go_build_cmd
    if c.projectType == "java-maven":
        from generators.offline import maven_build_cmd
        return f"""        stage('Build & Package') {{
            steps {{
                sh '{maven_build_cmd(c)}'
                archiveArtifacts artifacts: 'target/*.jar', fingerprint: true
            }}
        }}"""
    elif c.projectType == "java-gradle":
        return """        stage('Build & Package') {
            steps {
                sh 'gradle bootJar'
                archiveArtifacts artifacts: 'build/libs/*.jar', fingerprint: true
            }
        }"""
    elif c.projectType in ("vue", "react"):
        return f"""        stage('Build & Package') {{
            steps {{
                sh '{npm_install_cmd(c)}'
                sh 'npm run build'
            }}
        }}"""
    elif c.projectType == "python":
        return f"""        stage('Build & Package') {{
            steps {{
                sh '{pip_install_cmd(c, "build/")}'
            }}
        }}"""
    elif c.projectType == "go":
        return f"""        stage('Build & Package') {{
            steps {{
                sh '{go_build_cmd(c, cgo_disabled=True)}'
            }}
        }}"""
    return ""

def _build_code_stage(c):
    return """        stage('Checkout') {
            steps {
                checkout scm
            }
        }"""

def _build_test_stage(c):
    from generators.offline import maven_test_cmd
    if c.projectType == "java-maven":
        return f"""        stage('Test') {{
            steps {{
                sh '{maven_test_cmd(c)}'
            }}
        }}"""
    elif c.projectType == "java-gradle":
        return """        stage('Test') {
            steps {
                sh 'gradle test'
            }
        }"""
    elif c.projectType in ("vue", "react"):
        return """        stage('Test') {
            steps {
                sh 'npm test'
            }
        }"""
    elif c.projectType == "python":
        return """        stage('Test') {
            steps {
                sh 'pytest'
            }
        }"""
    elif c.projectType == "go":
        return """        stage('Test') {
            steps {
                sh 'go test ./...'
            }
        }"""
    return ""

def _build_deploy_stage(c):
    """生成部署阶段（包含备份、部署、启动）"""
    # Docker 部署模式：目标服务器上构建并运行容器
    if getattr(c, 'deployMethod', 'direct') == 'docker':
        return _build_docker_deploy_stage(c)

    from generators.offline import pip_install_cmd
    server_host = getattr(c, 'serverHost', '${SERVER_HOST}')
    deploy_path = getattr(c, 'deployPath', '/opt/apps')
    backup_enabled = getattr(c, 'backupBeforeDeploy', True)
    # Python 目标机安装依赖（scp 会把 .offline-deps 一并传到目标机）
    pip_remote_cmd = pip_install_cmd(c) + " -q"

    # 备份步骤
    backup_step = ""
    if backup_enabled:
        backup_step = f"""
                // 备份旧版本
                echo '备份旧版本...'
                ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                    DEPLOY_DIR={deploy_path}/${{PROJECT_NAME}}
                    BACKUP_DIR={deploy_path}/backup
                    if [ -d \"$DEPLOY_DIR\" ]; then
                        mkdir -p \"$BACKUP_DIR\"
                        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
                        cp -r \"$DEPLOY_DIR\" \"$BACKUP_DIR/${{PROJECT_NAME}}_$TIMESTAMP\"
                        echo \"备份完成: $BACKUP_DIR/${{PROJECT_NAME}}_$TIMESTAMP\"
                        # 保留最近 5 个备份
                        cd \"$BACKUP_DIR\" && ls -dt ${{PROJECT_NAME}}_* 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true
                    else
                        echo \"首次部署，跳过备份\"
                    fi
                '''"""

    if c.projectType == "java-maven":
        return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器...'
{backup_step}
                    // 停止旧服务
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        pkill -f "{c.projectName}.jar" 2>/dev/null || true
                        sleep 2
                    '''
                    // 传输新包
                    scp ${{SSH_OPTIONS}} target/{c.projectName}.jar ${{SERVER_USER}}@${{SERVER_HOST}}:{deploy_path}/${{PROJECT_NAME}}/
                    // 启动新服务
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        cd {deploy_path}/${{PROJECT_NAME}}
                        nohup java -jar {c.projectName}.jar --server.port={c.port} > app.log 2>&1 &
                        echo "应用已启动，端口: {c.port}"
                    '''
                }}
            }}
        }}"""
    elif c.projectType == "java-gradle":
        return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器...'
{backup_step}
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        pkill -f "{c.projectName}" 2>/dev/null || true
                        sleep 2
                    '''
                    scp ${{SSH_OPTIONS}} build/libs/{c.projectName}-*.jar ${{SERVER_USER}}@${{SERVER_HOST}}:{deploy_path}/${{PROJECT_NAME}}/
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        cd {deploy_path}/${{PROJECT_NAME}}
                        nohup java -jar {c.projectName}-*.jar --server.port={c.port} > app.log 2>&1 &
                        echo "应用已启动，端口: {c.port}"
                    '''
                }}
            }}
        }}"""
    elif c.projectType in ("vue", "react"):
        return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器...'
{backup_step}
                    // 清理旧文件并传输新文件
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        rm -rf {deploy_path}/${{PROJECT_NAME}}/dist/*
                    '''
                    scp ${{SSH_OPTIONS}} -r dist/* ${{SERVER_USER}}@${{SERVER_HOST}}:{deploy_path}/${{PROJECT_NAME}}/dist/
                    // 重启 Nginx
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        sudo nginx -s reload 2>/dev/null || sudo systemctl reload nginx
                        echo "Nginx 已重新加载"
                    '''
                }}
            }}
        }}"""
    elif c.projectType == "python":
        return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器...'
{backup_step}
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        pkill -f "python.*{c.projectName}" 2>/dev/null || true
                        sleep 2
                    '''
                    scp ${{SSH_OPTIONS}} -r . ${{SERVER_USER}}@${{SERVER_HOST}}:{deploy_path}/${{PROJECT_NAME}}/
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        cd {deploy_path}/${{PROJECT_NAME}}
                        {pip_remote_cmd}
                        nohup python app.py > app.log 2>&1 &
                        echo "应用已启动，端口: {c.port}"
                    '''
                }}
            }}
        }}"""
    elif c.projectType == "go":
        return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器...'
{backup_step}
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        pkill -f "./app" 2>/dev/null || true
                        sleep 2
                    '''
                    scp ${{SSH_OPTIONS}} ./app ${{SERVER_USER}}@${{SERVER_HOST}}:{deploy_path}/${{PROJECT_NAME}}/
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        cd {deploy_path}/${{PROJECT_NAME}}
                        chmod +x app
                        nohup ./app > app.log 2>&1 &
                        echo "应用已启动，端口: {c.port}"
                    '''
                }}
            }}
        }}"""
    return ""

def _build_docker_deploy_stage(c):
    """生成 Docker 部署阶段：传输源码到目标服务器，docker-compose 构建并运行容器。

    Dockerfile 为多阶段构建，构建过程完全在容器内进行，
    目标服务器只需 Docker + docker-compose 环境，无需 JDK/Node 等构建工具。
    """
    deploy_path = getattr(c, 'deployPath', '/opt/apps')
    return f"""        stage('Deploy') {{
            steps {{
                script {{
                    echo '部署到目标服务器（Docker 模式）...'
                    // 打包源码（排除构建产物与缓存），传输到目标服务器
                    sh '''
                        tar --exclude='.git' --exclude='node_modules' --exclude='target' \\
                            --exclude='build' --exclude='dist' --exclude='.dep-repo' \\
                            -czf /tmp/${{PROJECT_NAME}}.tar.gz .
                        scp ${{SSH_OPTIONS}} /tmp/${{PROJECT_NAME}}.tar.gz ${{SERVER_USER}}@${{SERVER_HOST}}:/tmp/
                        rm -f /tmp/${{PROJECT_NAME}}.tar.gz
                    '''
                    // 在目标服务器解压并用 docker-compose 构建运行
                    ssh ${{SSH_OPTIONS}} ${{SERVER_USER}}@${{SERVER_HOST}} '''
                        DEPLOY_DIR={deploy_path}/${{PROJECT_NAME}}
                        mkdir -p "$DEPLOY_DIR"
                        tar -xzf /tmp/${{PROJECT_NAME}}.tar.gz -C "$DEPLOY_DIR"
                        rm -f /tmp/${{PROJECT_NAME}}.tar.gz
                        cd "$DEPLOY_DIR"
                        echo "停止旧容器..."
                        docker-compose down --remove-orphans 2>/dev/null || true
                        echo "构建并启动容器..."
                        docker-compose up -d --build
                        docker image prune -f 2>/dev/null || true
                        echo "容器状态:"
                        docker-compose ps
                    '''
                }}
            }}
        }}"""

def _build_dockerfile(c):
    if c.projectType == "java-maven":
        jdk = c.jdkVersion or "17"
        return f"""FROM maven:3.9-eclipse-temurin-{jdk} AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests

FROM eclipse-temurin:{jdk}-jre-alpine
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE {c.port}
ENTRYPOINT ["java", "-jar", "app.jar", "--server.port={c.port}"]
"""
    elif c.projectType == "java-gradle":
        jdk = c.jdkVersion or "17"
        return f"""FROM gradle:8-jdk{jdk} AS build
WORKDIR /app
COPY build.gradle settings.gradle ./
COPY src ./src
RUN gradle bootJar --no-daemon

FROM eclipse-temurin:{jdk}-jre-alpine
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE {c.port}
ENTRYPOINT ["java", "-jar", "app.jar", "--server.port={c.port}"]
"""
    elif c.projectType in ("vue", "react"):
        return f"""FROM node:{c.nodeVersion}-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE {c.port}
"""
    elif c.projectType == "python":
        return f"""FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE {c.port}
CMD ["python", "app.py"]
"""
    elif c.projectType == "go":
        return f"""FROM golang:1.21 AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o app .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/app .
EXPOSE {c.port}
CMD ["./app"]
"""
    return ""

def _build_dockerignore(c):
    ignore = ".git\nnode_modules\ndist\nbuild\n*.class\n.env\n"
    if c.projectType.startswith("java"):
        ignore += "target\n"
    if c.projectType in ("vue", "react"):
        ignore += ".npm\n"
    return ignore

def _build_pom(c):
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>{c.projectName}</artifactId>
    <version>1.0.0</version>
    <packaging>jar</packaging>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.2.0</version>
    </parent>
    <properties>
        <java.version>{c.jdkVersion or '17'}</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
"""

def _build_package_json(c):
    return f"""{{
  "name": "{c.projectName}",
  "version": "1.0.0",
  "scripts": {{
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview"
  }},
  "dependencies": {{
    "vue": "^3.4.0"
  }}
}}
"""

def _build_requirements(c):
    return "flask==3.0.0\nrequests==2.31.0\npytest==7.4.0\n"

def _build_go_mod(c):
    return f"""module {c.projectName}\n\ngo 1.21\n
"""

def _build_jenkins_readme(c):
    project = c.projectName
    port = c.port
    return f"""# {project} - Jenkins 部署说明

## Jenkins 安装

### 方式一：Docker 安装（推荐）

```bash
docker run -d --name jenkins \
  -p 8080:8080 -p 50000:50000 \
  -v jenkins_home:/var/jenkins_home \
  jenkins/jenkins:lts
```

访问 `http://localhost:8080`，按提示完成初始化。

### 方式二：系统安装

```bash
# Ubuntu/Debian
curl -fsSL https://pkg.jenkins.io/debian-stable/jenkins.io.key | sudo apt-key add -
echo "deb https://pkg.jenkins.io/debian-stable binary/" | sudo tee /etc/apt/sources.list.d/jenkins.list
sudo apt-get update && sudo apt-get install -y jenkins
sudo systemctl start jenkins

# CentOS/RHEL
sudo wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo
sudo rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io.key
sudo yum install -y jenkins
sudo systemctl start jenkins
```

## 配置流水线

### 1. Pipeline from SCM

1. 登录 Jenkins → 新建任务 → Pipeline
2. Pipeline → Definition: Pipeline script from SCM
3. SCM: Git
4. Repository URL: 填写代码仓库地址
5. Branch: `{c.branch}`
6. Script Path: `Jenkinsfile`
7. 保存并立即构建

### 2. 直接使用 Jenkinsfile

将生成的 `Jenkinsfile` 放入项目根目录，Jenkins 会自动识别。

## 构建节点配置

### 添加构建工具

进入 Jenkins → Manage Jenkins → Global Tool Configuration:

| 工具 | 配置 |
|------|------|
| JDK | 添加 JDK {c.jdkVersion or '17'} |
| Maven | 添加 Maven（自动安装） |
| Gradle | 添加 Gradle（自动安装） |
| Node.js | 安装 NodeJS 插件后配置 |

### 添加 Agent 节点

```bash
# 在从节点服务器上
# 1. 确保已安装 Java
java -version

# 2. 从 Jenkins 下载 agent.jar
# 进入 Jenkins → Manage Jenkins → Nodes → New Node
# 下载 agent.jar 到从节点

# 3. 启动 agent
java -jar agent.jar -jnlpUrl http://<jenkins-url>/computer/<node-name>/slave-agent.jnlp
```

## 部署模式说明

| 模式 | 说明 |
|------|------|
| 纯代码 | 仅拉取代码，不做构建 |
| 代码+依赖 | 打包代码和依赖产物 |
| 含产物构建 | 完整构建→测试→部署，生成 Dockerfile |

## 常用管理命令

```bash
# 查看 Jenkins 状态
sudo systemctl status jenkins

# 重启 Jenkins
sudo systemctl restart jenkins

# 查看日志
sudo tail -f /var/log/jenkins/jenkins.log

# 获取初始密码
sudo cat /var/lib/jenkins/secrets/initialAdminPassword
```
"""
