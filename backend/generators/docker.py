"""Docker 部署配置生成

deployMethod=docker 时生成 docker-compose.yml，
流水线在目标服务器上使用 docker-compose 构建并运行容器。
多阶段 Dockerfile 使构建完全在容器内进行，目标服务器只需 Docker 环境。
"""


def build_docker_compose(c) -> str:
    """生成 docker-compose.yml（按项目类型配置服务）"""
    project_name = getattr(c, 'projectName', 'app') or 'app'
    port = getattr(c, 'port', 8080) or 8080

    # 前端项目容器内 nginx 默认监听 80，宿主机端口映射到用户配置端口
    container_port = 80 if c.projectType in ("vue", "react") else port

    return f"""# docker-compose.yml - {project_name}
# 生成: auto-cicd
# 使用: docker-compose up -d --build

version: '3.8'

services:
  {project_name}:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: {project_name}
    ports:
      - "{port}:{container_port}"
    restart: always
    environment:
      - TZ=Asia/Shanghai
"""


def docker_deploy_commands(c) -> list:
    """生成目标服务器上的 Docker 部署命令序列（供各生成器复用）"""
    project_name = getattr(c, 'projectName', 'app') or 'app'
    return [
        f"docker-compose -p {project_name} down --remove-orphans 2>/dev/null || true",
        f"docker-compose -p {project_name} up -d --build",
        f"docker image prune -f 2>/dev/null || true",
    ]
