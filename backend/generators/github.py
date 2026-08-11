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

    return files

def _get_build_cmd(c):
    if c.projectType == "java-maven":
        return "mvn clean package -DskipTests"
    elif c.projectType == "java-gradle":
        return "gradle bootJar --no-daemon"
    elif c.projectType in ("vue", "react"):
        return "npm ci && npm run build"
    elif c.projectType == "python":
        return "pip install -r requirements.txt"
    elif c.projectType == "go":
        return "CGO_ENABLED=0 go build -o app ."
    return "echo build"

def _get_test_cmd(c):
    if c.projectType == "java-maven":
        return "mvn test"
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

jobs:
  build:
    runs-on: ubuntu-latest
{matrix_section}    steps:
      - uses: actions/checkout@v4
        with:
{checkout_ref}{setup_java}{setup_node}{setup_go}{setup_python}      - name: Build
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

def _build_deploy_workflow(c):
    deploy_cmd = _get_deploy_cmd(c)
    branches = _get_branches(c)
    branch_list = ", ".join(branches)
    
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
    
    return f"""# GitHub Actions Deploy
# 项目: {c.projectName}
# 工具: GitHub Actions
# 分支: {', '.join(branches)}

name: Deploy

on:
  workflow_run:
    workflows: ["CI Pipeline"]
    types: [completed]
    branches: [{branch_list}]

env:
  SERVER_HOST: "{server_host}"
  SERVER_USER: "{server_user}"
  DEPLOY_PATH: "{deploy_path}"
  SSH_OPTIONS: "{ssh_options}"

jobs:
  deploy:
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
