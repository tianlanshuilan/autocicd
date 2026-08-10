def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def generate_huawei(config, output_dir):
    files = []
    files.append({"name": ".huaweicloud.yml", "content": _build_pipeline(config)})
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile", "content": dockerfile})
        dockerignore = _build_dockerignore(config)
        files.append({"name": ".dockerignore", "content": dockerignore})
    files.append({"name": "README.md", "content": f"# {config.projectName}\n\n华为云 CodeArts 流水线配置。\n"})

    # 多分支发布流程文件
    from generators.workflow import is_multi_branch_workflow, build_rollback_script, build_release_readme
    if is_multi_branch_workflow(config):
        rollback = build_rollback_script(config)
        files.append({"name": "rollback.sh", "content": rollback})
        release_readme = build_release_readme(config)
        files.append({"name": "README-Release.md", "content": release_readme})

    return files

def _build_pipeline(c):
    branches = _get_branches(c)
    branch_list = ", ".join(branches)

    # Auto-determine build steps based on project type
    if c.projectType.startswith("java"):
        build_step = _build_build_step(c)
    elif c.projectType == "go":
        build_step = _build_build_step(c)
    elif c.projectType in ("vue", "react"):
        build_step = _build_build_step(c)
    elif c.projectType == "python":
        build_step = _build_artifact_step(c)
    else:
        build_step = _build_code_step(c)
    test_step = _build_test_step(c)
    deploy_step = _build_deploy_step(c)

    # 多分支时添加分支触发规则
    branch_trigger = ""
    if len(branches) > 1:
        branch_trigger = "\ntriggers:\n  on_push:\n    branches:\n"
        for b in branches:
            branch_trigger += f"      - {b}\n"

    return f"""# 华为云 CodeArts Pipeline 配置
# 项目: {c.projectName}
# 工具: 华为云流水线
# 模式: {c.projectType}
# 分支: {branch_list}
# 生成: auto-cicd

stages:
  - name: 构建
    steps:
{build_step}
  - name: 测试
    steps:
{test_step}
  - name: 部署
    steps:
{deploy_step}

environment:
  REPO_URL: "{c.repoUrl}"
  BRANCH: "{branches[0]}"
  PORT: "{c.port}"
{branch_trigger}"""

def _build_build_step(c):
    if c.projectType == "java-maven":
        return f"""      - name: Maven构建
        type: shell
        command: mvn clean package -DskipTests
      - name: 上传制品
        type: artifact
        path: target/{c.projectName}-*.jar
      """
    elif c.projectType == "java-gradle":
        return f"""      - name: Gradle构建
        type: shell
        command: gradle bootJar --no-daemon
      - name: 上传制品
        type: artifact
        path: build/libs/*.jar
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - name: npm安装
        type: shell
        command: npm ci
      - name: npm构建
        type: shell
        command: npm run build
      - name: 上传静态资源
        type: artifact
        path: dist/
      """
    elif c.projectType == "python":
        return f"""      - name: pip安装
        type: shell
        command: pip install -r requirements.txt -t build/
      """
    elif c.projectType == "go":
        return f"""      - name: go构建
        type: shell
        command: CGO_ENABLED=0 go build -o app .
      - name: 上传二进制
        type: artifact
        path: app
      """
    return "      - name: build\n        type: shell\n        command: echo 'build'\n      "

def _build_artifact_step(c):
    if c.projectType == "java-maven":
        return f"""      - name: Maven打包
        type: shell
        command: mvn package -DskipTests
      - name: 上传Jar包
        type: artifact
        path: target/{c.projectName}-*.jar
      """
    elif c.projectType == "java-gradle":
        return f"""      - name: Gradle打包
        type: shell
        command: gradle bootJar --no-daemon
      - name: 上传Jar包
        type: artifact
        path: build/libs/*.jar
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - name: 安装依赖并构建
        type: shell
        command: npm ci && npm run build
      - name: 上传产物
        type: artifact
        path: dist/
      """
    elif c.projectType == "python":
        return f"""      - name: 打包依赖
        type: shell
        command: pip install -r requirements.txt -t build/
      - name: 上传依赖包
        type: artifact
        path: build/
      """
    elif c.projectType == "go":
        return f"""      - name: 构建Go二进制
        type: shell
        command: CGO_ENABLED=0 go build -o app .
      - name: 上传二进制
        type: artifact
        path: app
      """
    return "      - name: artifact\n        type: shell\n        command: echo 'artifact'\n      "

def _build_code_step(c):
    return """      - name: 拉取代码
        type: shell
        command: git checkout $BRANCH
      """

def _build_test_step(c):
    if c.projectType == "java-maven":
        return """      - name: Maven测试
        type: shell
        command: mvn test
      """
    elif c.projectType == "java-gradle":
        return """      - name: Gradle测试
        type: shell
        command: gradle test
      """
    elif c.projectType in ("vue", "react"):
        return """      - name: npm测试
        type: shell
        command: npm test
      """
    elif c.projectType == "python":
        return """      - name: pytest测试
        type: shell
        command: pytest
      """
    elif c.projectType == "go":
        return """      - name: go测试
        type: shell
        command: go test ./...
      """
    return "      - name: test\n        type: shell\n        command: echo 'test'\n      "

def _build_deploy_step(c):
    if c.projectType == "java-maven":
        return f"""      - name: 部署Java应用
        type: shell
        command: java -jar target/{c.projectName}.jar --server.port={c.port}
      """
    elif c.projectType == "java-gradle":
        return f"""      - name: 部署Java应用
        type: shell
        command: java -jar build/libs/{c.projectName}-*.jar --server.port={c.port}
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - name: 部署前端
        type: shell
        command: npx serve -s dist -l {c.port}
      """
    elif c.projectType == "python":
        return """      - name: 部署Python应用
        type: shell
        command: python app.py
      """
    elif c.projectType == "go":
        return """      - name: 部署Go应用
        type: shell
        command: ./app
      """
    return "      - name: deploy\n        type: shell\n        command: echo 'deploy'\n      "

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
