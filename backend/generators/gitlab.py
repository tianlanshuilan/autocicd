def generate_gitlab(config, output_dir):
    files = []
    files.append({"name": ".gitlab-ci.yml", "content": _build_pipeline(config)})
    if config.deployMethod == "docker":
        dockerfile = _build_dockerfile(config)
        files.append({"name": "Dockerfile", "content": dockerfile})
        dockerignore = _build_dockerignore(config)
        files.append({"name": ".dockerignore", "content": dockerignore})

    # 多分支发布流程文件
    from generators.workflow import is_multi_branch_workflow, build_rollback_script, build_release_readme
    if is_multi_branch_workflow(config):
        rollback = build_rollback_script(config)
        files.append({"name": "rollback.sh", "content": rollback})
        release_readme = build_release_readme(config)
        files.append({"name": "README-Release.md", "content": release_readme})

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

def _get_test_script(c):
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
    deploy_cmd = _get_deploy_cmd(c)
    branches = _get_branches(c)

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
    - {deploy_cmd}
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
{parallel_jobs}"""

    return f"""# GitLab CI Pipeline
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
  BRANCH: "{branches[0]}"
  PORT: "{c.port}"

build_job:
  stage: build
  image: {image}
  script:
    - {build_step}
  artifacts:
    paths:
      - {artifacts_path}
    expire_in: 1 week

test_job:
  stage: test
  image: {image}
  script:
    - {test_script}

deploy_job:
  stage: deploy
  image: {image}
  script:
    - {deploy_cmd}
  only:
    - {branches[0]}
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
