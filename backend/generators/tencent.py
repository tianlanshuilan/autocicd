def _get_branches(c):
    """获取分支列表，兼容单分支和多分支"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]

def generate_tencent(config, output_dir):
    files = []
    files.append({"name": ".tencent.yml", "content": _build_pipeline(config)})
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile", "content": dockerfile})
        dockerignore = _build_dockerignore(config)
        files.append({"name": ".dockerignore", "content": dockerignore})
    files.append({"name": "README.md", "content": f"# {config.projectName}\n\n腾讯云 CI/CD 流水线配置。\n"})

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
        branch_trigger = "\ntriggers:\n  push:\n    branches:\n"
        for b in branches:
            branch_trigger += f"      - {b}\n"

    return f"""# 腾讯云 CI/CD Pipeline 配置
# 项目: {c.projectName}
# 工具: 腾讯云 TKE
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

env:
  REPO_URL: "{c.repoUrl}"
  BRANCH: "{branches[0]}"
  PORT: "{c.port}"
{branch_trigger}"""

def _build_build_step(c):
    if c.projectType == "java-maven":
        return f"""      - run:
          name: Maven构建
          command: mvn clean package -DskipTests
      - artifact:
          name: 发布Jar包
          path: target/{c.projectName}-*.jar
      """
    elif c.projectType == "java-gradle":
        return f"""      - run:
          name: Gradle构建
          command: gradle bootJar --no-daemon
      - artifact:
          name: 发布Jar包
          path: build/libs/*.jar
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - run:
          name: npm安装
          command: npm ci
      - run:
          name: npm构建
          command: npm run build
      - artifact:
          name: 发布静态资源
          path: dist/
      """
    elif c.projectType == "python":
        return f"""      - run:
          name: pip安装
          command: pip install -r requirements.txt -t build/
      """
    elif c.projectType == "go":
        return f"""      - run:
          name: go构建
          command: CGO_ENABLED=0 go build -o app .
      - artifact:
          name: 发布二进制
          path: app
      """
    return "      - run:\n          command: echo 'build'\n      "

def _build_artifact_step(c):
    if c.projectType == "java-maven":
        return f"""      - run:
          name: Maven打包
          command: mvn package -DskipTests
      - artifact:
          name: 发布Jar包
          path: target/{c.projectName}-*.jar
      """
    elif c.projectType == "java-gradle":
        return f"""      - run:
          name: Gradle打包
          command: gradle bootJar --no-daemon
      - artifact:
          name: 发布Jar包
          path: build/libs/*.jar
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - run:
          name: 安装依赖并构建
          command: npm ci && npm run build
      - artifact:
          name: 发布产物
          path: dist/
      """
    elif c.projectType == "python":
        return f"""      - run:
          name: 打包依赖
          command: pip install -r requirements.txt -t build/
      - artifact:
          name: 发布依赖包
          path: build/
      """
    elif c.projectType == "go":
        return f"""      - run:
          name: 构建Go二进制
          command: CGO_ENABLED=0 go build -o app .
      - artifact:
          name: 发布二进制
          path: app
      """
    return "      - run:\n          command: echo 'artifact'\n      "

def _build_code_step(c):
    return """      - run:
          name: 拉取代码
          command: git checkout $BRANCH
      """

def _build_test_step(c):
    if c.projectType == "java-maven":
        return """      - run:
          name: Maven测试
          command: mvn test
      """
    elif c.projectType == "java-gradle":
        return """      - run:
          name: Gradle测试
          command: gradle test
      """
    elif c.projectType in ("vue", "react"):
        return """      - run:
          name: npm测试
          command: npm test
      """
    elif c.projectType == "python":
        return """      - run:
          name: pytest测试
          command: pytest
      """
    elif c.projectType == "go":
        return """      - run:
          name: go测试
          command: go test ./...
      """
    return "      - run:\n          command: echo 'test'\n      "

def _build_deploy_step(c):
    if c.projectType == "java-maven":
        return f"""      - run:
          name: 部署Java应用
          command: java -jar target/{c.projectName}.jar --server.port={c.port}
      """
    elif c.projectType == "java-gradle":
        return f"""      - run:
          name: 部署Java应用
          command: java -jar build/libs/{c.projectName}-*.jar --server.port={c.port}
      """
    elif c.projectType in ("vue", "react"):
        return f"""      - run:
          name: 部署前端
          command: npx serve -s dist -l {c.port}
      """
    elif c.projectType == "python":
        return """      - run:
          name: 部署Python应用
          command: python app.py
      """
    elif c.projectType == "go":
        return """      - run:
          name: 部署Go应用
          command: ./app
      """
    return "      - run:\n          command: echo 'deploy'\n      "

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
