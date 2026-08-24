def generate_gitlab(config, output_dir):
    files = []
    files.append({"name": ".gitlab-ci.yml", "content": _build_pipeline(config)})
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

def _get_image(c):
    if c.projectType == "java-maven":
        jdk = c.jdkVersion or "17"
        return f"maven:3.9-eclipse-temurin-{jdk}"
    elif c.projectType == "java-gradle":
        jdk = c.jdkVersion or "17"
        return f"gradle:8-jdk{jdk}"
    elif c.projectType in ("vue", "react"):
        node = c.nodeVersion or "20"
        return f"node:{node}-alpine"
    elif c.projectType == "python":
        return "python:3.11-slim"
    elif c.projectType == "go":
        return "golang:1.21"
    return "alpine:latest"

def _get_build_script(c):
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

def _get_test_script(c):
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

def _get_artifacts_path(c):
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

def _get_deploy_scripts(c):
    """返回部署脚本行列表。Docker 模式传输源码到目标服务器并 docker-compose 构建运行。"""
    if getattr(c, 'deployMethod', 'direct') == 'docker':
        return [
            "echo 'Deploying with Docker...'",
            "tar --exclude='.git' --exclude='node_modules' --exclude='target' --exclude='build' --exclude='dist' --exclude='.dep-repo' -czf /tmp/$CI_PROJECT_NAME.tar.gz .",
            "scp $SSH_OPTIONS /tmp/$CI_PROJECT_NAME.tar.gz $SERVER_USER@$SERVER_HOST:/tmp/",
            "ssh $SSH_OPTIONS $SERVER_USER@$SERVER_HOST 'DEPLOY_DIR=$DEPLOY_PATH/$CI_PROJECT_NAME; mkdir -p $DEPLOY_DIR; tar -xzf /tmp/$CI_PROJECT_NAME.tar.gz -C $DEPLOY_DIR; rm -f /tmp/$CI_PROJECT_NAME.tar.gz; cd $DEPLOY_DIR; docker-compose down --remove-orphans 2>/dev/null || true; docker-compose up -d --build; docker image prune -f 2>/dev/null || true; docker-compose ps'",
            "rm -f /tmp/$CI_PROJECT_NAME.tar.gz",
        ]
    return [_get_deploy_cmd(c)]

def _get_lb_deploy_scripts(c):
    """负载均衡滚动部署脚本行：打包后执行 deploy/rolling-deploy.sh

    runner 镜像需具备 ssh/scp/curl（与现有 SSH 部署要求一致）。
    """
    p = c.projectName
    if getattr(c, 'deployMethod', 'direct') == 'docker':
        return [
            "echo '负载均衡滚动部署（Docker 模式：打包源码）...'",
            f"tar --exclude='.git' --exclude='node_modules' --exclude='target' --exclude='build' --exclude='dist' --exclude='.dep-repo' -czf /tmp/{p}.tar.gz .",
            "bash deploy/rolling-deploy.sh",
            f"rm -f /tmp/{p}.tar.gz",
        ]
    pack_cmds = {
        "java-maven": f"mkdir -p /tmp/lb-artifact && cp target/*.jar /tmp/lb-artifact/{p}.jar && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
        "java-gradle": f"mkdir -p /tmp/lb-artifact && cp build/libs/*.jar /tmp/lb-artifact/{p}.jar && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
        "vue": f"tar -czf {p}-artifact.tar.gz dist",
        "react": f"tar -czf {p}-artifact.tar.gz dist",
        "python": f"tar --exclude='.git' --exclude='__pycache__' -czf {p}-artifact.tar.gz .",
        "go": f"mkdir -p /tmp/lb-artifact && cp ./app /tmp/lb-artifact/ && tar -czf {p}-artifact.tar.gz -C /tmp/lb-artifact .",
    }
    pack = pack_cmds.get(c.projectType, pack_cmds["python"])
    return [
        "echo '负载均衡滚动部署（直接部署模式：打包产物）...'",
        pack,
        "bash deploy/rolling-deploy.sh",
        f"rm -f {p}-artifact.tar.gz",
    ]

def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def _build_pipeline(c):
    image = _get_image(c)
    build_script = _get_build_script(c)
    test_script = _get_test_script(c)
    artifacts_path = _get_artifacts_path(c)
    branches = _get_branches(c)

    # 部署脚本：负载均衡时走滚动部署
    from generators.lb import has_load_balancer, is_integration_mode, get_environments
    if has_load_balancer(c):
        deploy_scripts = _get_lb_deploy_scripts(c)
    else:
        deploy_scripts = _get_deploy_scripts(c)
    deploy_block = "\n".join(f"    - {s}" for s in deploy_scripts)
    
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

    # Auto-determine build steps based on project type
    if c.projectType.startswith("java"):
        build_step = build_script
    elif c.projectType == "go":
        build_step = build_script
    elif c.projectType in ("vue", "react"):
        build_step = build_script
    elif c.projectType == "python":
        build_step = build_script
    else:
        build_step = "echo '纯代码模式，跳过构建'"

    branch_list = ", ".join(branches)

    # 依赖仓库配置
    from generators.offline import has_dep_repo, dep_repo_url, dep_repo_branch
    dep_repo_vars = ""
    dep_repo_before = ""
    if has_dep_repo(c):
        dep_repo_vars = f"""  DEP_REPO_URL: "{dep_repo_url(c)}"
  DEP_REPO_BRANCH: "{dep_repo_branch(c)}"
"""
        dep_repo_before = f"""    - git clone --branch $DEP_REPO_BRANCH --depth 1 $DEP_REPO_URL .dep-repo
"""

    # 集成测试模式：功能分支临时合入环境集成分支（YAML anchor，供各 job 复用）
    integration_anchor = ""
    integration_before = ""
    integration = is_integration_mode(c)
    envs = get_environments(c)
    if integration and envs:
        env_branch = envs[0].get('branch') or envs[0].get('name', 'test')
        integration_anchor = f"""
# 集成测试模式：功能分支临时合入 {env_branch}（仅 CI 工作区，不推送远端）
.integration_merge: &integration_merge |-
  if [ "$CI_COMMIT_BRANCH" != "{env_branch}" ]; then
    git config user.name "auto-cicd" && git config user.email "auto-cicd@local"
    git fetch origin {env_branch} || true
    git checkout -B {env_branch} origin/{env_branch} 2>/dev/null || git checkout -b {env_branch}
    git merge "$CI_COMMIT_BRANCH" --no-edit || {{ echo "❌ 合并冲突，集成测试中止"; exit 1; }}
    echo "✅ 已临时集成 $CI_COMMIT_BRANCH 到 {env_branch}"
  fi
"""
        integration_before = "    - *integration_merge\n"

    # only 限制：集成测试模式下任意分支触发
    only_block = "" if integration else f"""  only:
    - {branches[0]}
"""
    test_before = f"  before_script:\n{integration_before}" if integration_before else ""
    deploy_before = f"  before_script:\n{integration_before}" if integration_before else ""

    # 多分支时生成并行 job
    if len(branches) > 1:
        branch_rules = "\n".join(f"    - {b}" for b in branches)
        parallel_jobs = ""
        for b in branches:
            safe_name = b.replace("/", "-").replace(".", "-")
            parallel_jobs += f"""
build_{safe_name}:
  stage: build
  image: {image}
  variables:
    BRANCH: "{b}"
  script:
    - git checkout {b}
    - {build_step}
  artifacts:
    paths:
      - {artifacts_path}
    expire_in: 1 week
  only:
    - {b}

test_{safe_name}:
  stage: test
  image: {image}
  variables:
    BRANCH: "{b}"
  script:
    - git checkout {b}
    - {test_script}
  only:
    - {b}

deploy_{safe_name}:
  stage: deploy
  image: {image}
  variables:
    BRANCH: "{b}"
  script:
{deploy_block}
  only:
    - {b}
"""
        return f"""# GitLab CI Multi-Branch Pipeline
# 项目: {c.projectName}
# 工具: GitLab CI
# 模式: {c.projectType}
# 分支: {branch_list}
# 生成: auto-cicd

stages:
  - build
  - test
  - deploy

variables:
  REPO_URL: "{c.repoUrl}"
  PORT: "{c.port}"
  SERVER_HOST: "{server_host}"
  SERVER_USER: "{server_user}"
  DEPLOY_PATH: "{deploy_path}"
  SSH_OPTIONS: "{ssh_options}"
{dep_repo_vars}{parallel_jobs}"""

    # 多环境部署 job（Docker 模式，无负载均衡时）：job 级 variables 覆盖 SERVER_HOST/SERVER_USER
    env_jobs = ""
    use_env_jobs = False
    if not has_load_balancer(c) and envs and getattr(c, 'deployMethod', 'direct') == 'docker':
        jobs = []
        for env in envs:
            server = env.get('server') or {}
            if not server.get('host'):
                continue
            safe_name = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in env.get('name', 'env'))
            env_before = f"  before_script:\n{integration_before}" if integration_before else ""
            jobs.append(f"""
deploy_{safe_name}:
  stage: deploy
  image: {image}
  variables:
    SERVER_HOST: "{server.get('host')}"
    SERVER_USER: "{server.get('username', 'root')}"
{env_before}  script:
{deploy_block}
{only_block}""")
        if jobs:
            env_jobs = "".join(jobs)
            use_env_jobs = True

    default_deploy_job = "" if use_env_jobs else f"""
deploy_job:
  stage: deploy
  image: {image}
{deploy_before}  script:
{deploy_block}
{only_block}"""

    # 多环境直接部署模式说明（直接部署模式在 runner 本地运行，仅 Docker 模式支持多环境远程部署）
    env_note = ""
    if envs and getattr(c, 'deployMethod', 'direct') != 'docker' and not has_load_balancer(c):
        env_note = "# 注意：多环境远程部署仅支持 Docker 部署模式，当前模式将部署到默认目标\n"

    return f"""# GitLab CI Pipeline
# 项目: {c.projectName}
# 工具: GitLab CI
# 模式: {c.projectType}
# 分支: {branch_list}
# 生成: auto-cicd
{env_note}

stages:
  - build
  - test
  - deploy

variables:
  REPO_URL: "{c.repoUrl}"
  BRANCH: "{branches[0]}"
  PORT: "{c.port}"
  SERVER_HOST: "{server_host}"
  SERVER_USER: "{server_user}"
  DEPLOY_PATH: "{deploy_path}"
  SSH_OPTIONS: "{ssh_options}"
{dep_repo_vars}{integration_anchor}
build_job:
  stage: build
  image: {image}
  before_script:
{integration_before}{dep_repo_before}  script:
    - {build_step}
  artifacts:
    paths:
      - {artifacts_path}
    expire_in: 1 week

test_job:
  stage: test
  image: {image}
{test_before}  script:
    - {test_script}
{default_deploy_job}{env_jobs}
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
