def generate_github(config, output_dir):
    files = []
    workflow_dir = ".github/workflows"
    files.append({"name": f"{workflow_dir}/ci.yml", "content": _build_workflow(config)})
    files.append({"name": f"{workflow_dir}/deploy.yml", "content": _build_deploy_workflow(config)})
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile", "content": dockerfile})
        dockerignore = _build_dockerignore(config)
        files.append({"name": ".dockerignore", "content": dockerignore})
        from generators.docker import build_docker_compose
        files.append({"name": "docker-compose.yml", "content": build_docker_compose(config)})

    # 多分支发布流程文件
    from generators.workflow import is_multi_branch_workflow, build_rollback_script, build_release_readme
    if is_multi_branch_workflow(config):
        # 添加发布流水线 workflow
        release_workflow = _build_release_workflow(config)
        files.append({"name": f"{workflow_dir}/release.yml", "content": release_workflow})
        rollback = build_rollback_script(config)
        files.append({"name": "rollback.sh", "content": rollback})
        release_readme = build_release_readme(config)
        files.append({"name": "README-Release.md", "content": release_readme})

    # 负载均衡文件：滚动部署脚本 + Nginx upstream 配置
    from generators.lb import has_load_balancer, build_rolling_deploy_script, build_nginx_upstream_conf
    if has_load_balancer(config):
        files.append({"name": "deploy/rolling-deploy.sh", "content": build_rolling_deploy_script(config)})
        files.append({"name": "deploy/nginx-lb.conf", "content": build_nginx_upstream_conf(config)})

    return files

def _get_build_cmd(c):
    from generators.offline import maven_build_cmd, npm_build_cmd, pip_install_cmd, go_build_cmd
    if c.projectType == "java-maven":
        return maven_build_cmd(c)
    elif c.projectType == "java-gradle":
        return "gradle bootJar --no-daemon"
    elif c.projectType in ("vue", "react"):
        return npm_build_cmd(c)
    elif c.projectType == "python":
        return pip_install_cmd(c)
    elif c.projectType == "go":
        return go_build_cmd(c, cgo_disabled=True)
    return "echo build"

def _get_test_cmd(c):
    from generators.offline import maven_test_cmd
    if c.projectType == "java-maven":
        return maven_test_cmd(c)
    elif c.projectType == "java-gradle":
        return "gradle test"
    elif c.projectType in ("vue", "react"):
        return "npm test"
    elif c.projectType == "python":
        return "pytest"
    elif c.projectType == "go":
        return "go test ./..."
    return "echo test"

def _get_artifact_path(c):
    if c.projectType == "java-maven":
        return "target/*.jar"
    elif c.projectType == "java-gradle":
        return "build/libs/*.jar"
    elif c.projectType in ("vue", "react"):
        return "dist/"
    elif c.projectType == "go":
        return "app"
    return "."

def _get_deploy_cmd(c):
    if c.projectType == "java-maven":
        return f"java -jar target/{c.projectName}.jar --server.port={c.port}"
    elif c.projectType == "java-gradle":
        return f"java -jar build/libs/{c.projectName}-*.jar --server.port={c.port}"
    elif c.projectType in ("vue", "react"):
        return f"npx serve -s dist -l {c.port}"
    elif c.projectType == "python":
        return "python app.py"
    elif c.projectType == "go":
        return "./app"
    return "echo deploy"

def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def _build_workflow(c):
    build = _get_build_cmd(c)
    test = _get_test_cmd(c)
    artifact = _get_artifact_path(c)
    branches = _get_branches(c)

    from generators.lb import is_integration_mode
    integration = is_integration_mode(c)

    jdk = c.jdkVersion or "17"
    node = c.nodeVersion or "20"

    setup_java = ""
    if c.projectType.startswith("java"):
        setup_java = f"""      - name: Set up JDK {jdk}
        uses: actions/setup-java@v4
        with:
          java-version: '{jdk}'
          distribution: 'temurin'
"""
    setup_node = ""
    if c.projectType in ("vue", "react"):
        setup_node = f"""      - name: Set up Node {node}
        uses: actions/setup-node@v4
        with:
          node-version: '{node}'
"""
    setup_go = ""
    if c.projectType == "go":
        setup_go = """      - name: Set up Go
        uses: actions/setup-go@v5
        with:
          go-version: '1.21'
"""
    setup_python = ""
    if c.projectType == "python":
        setup_python = """      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
"""

    # 集成测试模式：任意功能分支触发，检出触发分支本身（不固定 ref）
    if integration:
        branch_list = "'**'"
        matrix_section = ""
        checkout_ref = ""
    else:
        branch_list = ", ".join(branches)

        # 多分支时使用矩阵策略并行构建
        matrix_section = ""
        checkout_ref = ""
        if len(branches) > 1:
            matrix_branches = "\n".join(f"          - {b}" for b in branches)
            matrix_section = f"""    strategy:
      matrix:
        branch:
{matrix_branches}
      fail-fast: false
"""
            checkout_ref = f"""        ref: ${{{{ matrix.branch }}}}
"""
        else:
            checkout_ref = f"""        ref: {branches[0]}
"""

    # 依赖仓库检出步骤
    from generators.offline import has_dep_repo, dep_repo_url, dep_repo_branch
    checkout_deps_step = ""
    if has_dep_repo(c):
        checkout_deps_step = f"""      - name: Checkout Dependencies
        uses: actions/checkout@v4
        with:
          repository: {dep_repo_url(c).split(':')[-1].replace('.git', '')}
          ref: {dep_repo_branch(c)}
          path: .dep-repo
          token: ${{{{ secrets.DEP_REPO_TOKEN }}}}
"""

    # checkout 块（无 with 参数时省略 with 段）
    checkout_block = "      - uses: actions/checkout@v4"
    if checkout_ref or checkout_deps_step:
        checkout_block += f"""
        with:
{checkout_ref}{checkout_deps_step}"""

    # 集成测试模式：检出后先将功能分支临时合入环境集成分支
    integration_step = _build_integration_step(c) if integration else ""

    return f"""# GitHub Actions CI
# 项目: {c.projectName}
# 工具: GitHub Actions
# 模式: {c.projectType}
# 分支: {', '.join(branches)}
# 生成: auto-cicd

name: CI Pipeline

on:
  push:
    branches: [{branch_list}]
  pull_request:
    branches: [{branch_list}]
  workflow_dispatch:  # 支持手动触发流水线

jobs:
  build:
    runs-on: ubuntu-latest
{matrix_section}    steps:
{checkout_block}
{integration_step}{setup_java}{setup_node}{setup_go}{setup_python}      - name: Build
        run: {build}
      - name: Test
        run: {test}
      - name: Upload artifact
        uses: actions/upload-artifact@v4
        with:
          name: build-artifact
          path: |
            {artifact}
"""

def _build_integration_step(c):
    """集成测试模式：将触发的功能分支临时合入环境集成分支（仅 CI 工作区，不推送远端）"""
    from generators.lb import get_environments
    envs = get_environments(c)
    if not envs:
        return ""
    env = envs[0]
    env_branch = env.get('branch') or env.get('name', 'test')
    name = env.get('name', 'test')
    return f"""      - name: 集成到 {name} 环境
        if: github.ref_name != '{env_branch}'
        run: |
          git config user.name "auto-cicd" && git config user.email "auto-cicd@local"
          CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
          git fetch origin {env_branch} || true
          git checkout -B {env_branch} origin/{env_branch} 2>/dev/null || git checkout -b {env_branch}
          git merge $CURRENT_BRANCH --no-edit || {{ echo "❌ 合并冲突，集成测试中止"; exit 1; }}
          echo "✅ 已临时集成 $CURRENT_BRANCH 到 {env_branch}"
"""

def _build_deploy_workflow(c):
    branches = _get_branches(c)
    from generators.lb import is_integration_mode, has_load_balancer, get_environments
    integration = is_integration_mode(c)
    branch_list = "'**'" if integration else ", ".join(branches)

    # 服务器和堡垒机配置
    server_host = getattr(c, 'serverHost', '')
    server_user = getattr(c, 'serverUser', 'root')
    deploy_path = getattr(c, 'deployPath', '/opt/apps')
    bastion_host = getattr(c, 'bastionHost', '')
    bastion_port = getattr(c, 'bastionPort', 22)
    bastion_user = getattr(c, 'bastionUser', '')

    # 生成 SSH 选项
    ssh_options = "-o StrictHostKeyChecking=no"
    if bastion_host and bastion_user:
        ssh_options += f" -J {bastion_user}@{bastion_host}:{bastion_port}"

    # 部署 job：LB 滚动部署 > 多环境部署 > 默认部署
    jobs = []
    is_docker = getattr(c, 'deployMethod', 'direct') == 'docker'
    if has_load_balancer(c):
        jobs.append(_build_lb_deploy_job(c, integration))
    else:
        envs = get_environments(c)
        if envs and is_docker:
            for env in envs:
                server = env.get('server') or {}
                if server.get('host'):
                    jobs.append(_build_docker_deploy_job(
                        c, f"deploy-{env.get('name')}", integration,
                        host=server.get('host'), user=server.get('username', 'root')))
        if not jobs:
            if is_docker:
                jobs.append(_build_docker_deploy_job(c, "deploy", integration))
            else:
                jobs.append(_build_direct_deploy_job(c))
    jobs_yaml = "\n".join(jobs)

    # 多环境直接部署模式说明（GitHub 直接部署在 runner 本地运行，仅 Docker 模式支持多环境远程部署）
    env_note = ""
    if get_environments(c) and not is_docker and not has_load_balancer(c):
        env_note = "# 注意：多环境远程部署仅支持 Docker 部署模式，当前模式将部署到默认目标\n"

    return f"""# GitHub Actions Deploy
# 项目: {c.projectName}
# 工具: GitHub Actions
# 分支: {', '.join(branches)}
{env_note}

name: Deploy

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [{branch_list}]
  workflow_dispatch:  # 支持手动触发部署

env:
  SERVER_HOST: "{server_host}"
  SERVER_USER: "{server_user}"
  DEPLOY_PATH: "{deploy_path}"
  SSH_OPTIONS: "{ssh_options}"
  PROJECT_NAME: "{c.projectName}"
  SERVER_KEY: ${{{{ secrets.SERVER_SSH_KEY }}}}
  SERVER_PASSWORD: ${{{{ secrets.SERVER_PASSWORD }}}}
  SSHPASS: ${{{{ secrets.SERVER_PASSWORD }}}}

jobs:
{jobs_yaml}"""

def _indent_run(script, spaces=10):
    """将 run 脚本按 YAML 缩进格式化"""
    pad = " " * spaces
    return "\n".join(pad + line for line in script.splitlines())

def _ssh_key_setup_line():
    return 'mkdir -p ~/.ssh && echo "$SERVER_KEY" > ~/.ssh/id_rsa && chmod 600 ~/.ssh/id_rsa'

def _deploy_checkout_step(integration):
    """部署 workflow 的 checkout 步骤（集成模式检出触发分支）"""
    if integration:
        return """      - uses: actions/checkout@v4
        with:
          ref: ${{{{ github.event.workflow_run.head_branch || github.ref_name }}}}
"""
    return """      - uses: actions/checkout@v4
"""

def _docker_deploy_run_script(c):
    """Docker 部署 run 脚本：传输源码到目标服务器，docker-compose 构建运行

    支持密钥与密码两种 SSH 认证方式：通过 AUTH_PREFIX 统一前缀。
    """
    from generators.lb import github_ssh_setup_block
    return f"""{github_ssh_setup_block()}
tar --exclude='.git' --exclude='node_modules' --exclude='target' \\
    --exclude='build' --exclude='dist' --exclude='.dep-repo' \\
    -czf /tmp/${{PROJECT_NAME}}.tar.gz .
$AUTH_PREFIX scp $SSH_OPTIONS /tmp/${{PROJECT_NAME}}.tar.gz $SERVER_USER@$SERVER_HOST:/tmp/
$AUTH_PREFIX ssh $SSH_OPTIONS $SERVER_USER@$SERVER_HOST '
    DEPLOY_DIR=$DEPLOY_PATH/${{PROJECT_NAME}}
    mkdir -p "$DEPLOY_DIR"
    tar -xzf /tmp/${{PROJECT_NAME}}.tar.gz -C "$DEPLOY_DIR"
    rm -f /tmp/${{PROJECT_NAME}}.tar.gz
    cd "$DEPLOY_DIR"
    docker-compose down --remove-orphans 2>/dev/null || true
    docker-compose up -d --build
    docker image prune -f 2>/dev/null || true
    docker-compose ps
'"""

def _build_docker_deploy_job(c, job_name, integration, host=None, user=None):
    """Docker 部署 job（多环境时通过 job 级 env 覆盖 SERVER_HOST/SERVER_USER）"""
    env_name = job_name.removeprefix("deploy-") if host else ""
    env_override = ""
    if host:
        env_override = f"""    env:
      SERVER_HOST: "{host}"
      SERVER_USER: "{user or 'root'}"
"""
    step_title = f"Deploy to {env_name} with Docker" if host else "Deploy with Docker"
    integration_step = _build_integration_step(c) if integration else ""
    return f"""  {job_name}:
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' }}}}
{env_override}    steps:
{_deploy_checkout_step(integration)}{integration_step}      - name: {step_title}
        env:
          SERVER_KEY: ${{{{ secrets.SERVER_SSH_KEY }}}}
        run: |
{_indent_run(_docker_deploy_run_script(c))}
"""

def _lb_artifact_pack_cmd(c):
    """LB 直接部署模式：打包构建产物为 {project}-artifact.tar.gz（滚动脚本约定）"""
    p = c.projectName
    pack_cmds = {
        "java-maven": f"mkdir -p /tmp/lb-artifact && cp target/*.jar /tmp/lb-artifact/{p}.jar && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
        "java-gradle": f"mkdir -p /tmp/lb-artifact && cp build/libs/*.jar /tmp/lb-artifact/{p}.jar && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
        "vue": f"tar -czf {p}-artifact.tar.gz dist",
        "react": f"tar -czf {p}-artifact.tar.gz dist",
        "python": f"tar --exclude='.git' --exclude='__pycache__' -czf {p}-artifact.tar.gz .",
        "go": f"mkdir -p /tmp/lb-artifact && cp ./app /tmp/lb-artifact/ && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
    }
    return pack_cmds.get(c.projectType, pack_cmds["python"])

def _build_lb_deploy_job(c, integration):
    """负载均衡滚动部署 job：打包后执行 deploy/rolling-deploy.sh"""
    is_docker = getattr(c, 'deployMethod', 'direct') == 'docker'
    if is_docker:
        pack = """tar --exclude='.git' --exclude='node_modules' --exclude='target' \\
    --exclude='build' --exclude='dist' --exclude='.dep-repo' \\
    -czf /tmp/$PROJECT_NAME.tar.gz ."""
        cleanup = "rm -f /tmp/$PROJECT_NAME.tar.gz"
        download_step = ""
    else:
        pack = _lb_artifact_pack_cmd(c)
        cleanup = f"rm -f {c.projectName}-artifact.tar.gz"
        download_step = """      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: build-artifact
"""
    integration_step = _build_integration_step(c) if integration else ""
    from generators.lb import github_ssh_setup_block
    run_script = f"""{github_ssh_setup_block()}
{pack}
bash deploy/rolling-deploy.sh
{cleanup}"""
    return f"""  deploy:
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' }}}}
    steps:
{_deploy_checkout_step(integration)}{integration_step}{download_step}      - name: Deploy (负载均衡滚动部署)
        env:
          SERVER_KEY: ${{{{ secrets.SERVER_SSH_KEY }}}}
        run: |
{_indent_run(run_script)}
"""

def _build_direct_deploy_job(c):
    """直接部署 job（沿用默认行为：下载产物在 runner 运行）"""
    deploy_cmd = _get_deploy_cmd(c)
    return f"""  deploy:
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' }}}}
    steps:
      - uses: actions/checkout@v4
      - name: Download artifact
        uses: actions/download-artifact@v4
        with:
          name: build-artifact
      - name: Deploy
        run: {deploy_cmd}
"""

def _build_release_workflow(c):
    """生成多分支发布流程 workflow（审批 + 合并 + 回滚）"""
    from generators.workflow import get_release_strategy, get_branches
    strategy = get_release_strategy(c)
    branches = get_branches(c)
    main_branch = strategy.get("mainBranch", "main")
    merge_strategy = strategy.get("strategy", "auto_merge")
    branch_list = ", ".join(branches)

    return f"""# 多分支发布流程 - 审批/合并/回滚
# 项目: {c.projectName}
# 主分支: {main_branch}
# 策略: {merge_strategy}
# 生成: auto-cicd

name: Release Pipeline

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [{branch_list}]
  workflow_dispatch:  # 支持手动触发部署

jobs:
  approve-merge:
    name: 审批确认 - 合并到 {main_branch}
    runs-on: ubuntu-latest
    if: ${{{{ github.event.workflow_run.conclusion == 'success' }}}}
    environment:
      name: production
    steps:
      - name: 测试验证结果
        run: |
          echo "✅ CI 流水线测试通过"
          echo "源分支: ${{{{ github.event.workflow_run.head_branch }}}}"
          echo "目标分支: {main_branch}"
          echo "请在 GitHub Environment 中确认合并操作"

  merge-to-main:
    name: 合并到 {main_branch}
    needs: approve-merge
    runs-on: ubuntu-latest
    if: ${{{{ needs.approve-merge.result == 'success' }}}}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: {main_branch}
      - name: 合并分支
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git merge origin/${{{{ github.event.workflow_run.head_branch }}}} --no-edit
          git push origin {main_branch}
          # 打版本标签
          TAG="v$(date +%Y%m%d%H%M%S)"
          git tag $TAG
          git push origin $TAG
          echo "✅ 已合并到 {main_branch}，标签: $TAG"

  rollback:
    name: 回滚到上一稳定版本
    needs: approve-merge
    runs-on: ubuntu-latest
    if: ${{{{ needs.approve-merge.result == 'failure' }}}}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: {main_branch}
      - name: 回滚操作
        run: |
          PREV_TAG=$(git tag --sort=-creatordate | grep '^v[0-9]' | head -2 | tail -1)
          if [ -z "$PREV_TAG" ]; then
            echo "⚠️ 未找到可回滚的版本标签"
            exit 1
          fi
          echo "回滚到: $PREV_TAG"
          git checkout $PREV_TAG
          echo "✅ 回滚完成"
"""

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
