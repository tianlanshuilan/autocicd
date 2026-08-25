"""负载均衡与多环境部署辅助

提供两类能力的共享生成逻辑（供 Jenkins/GitHub/GitLab 生成器复用）：

1. 负载均衡（LoadBalancerConfig）
   - Nginx upstream 配置文件生成
   - 滚动部署脚本：逐台部署 + 健康检查，任一后端失败即中止（服务不中断）

2. 多环境（EnvironmentConfig）
   - 环境列表读取辅助（dev/test/staging → 各自的集成分支与服务器）

3. 流水线模式（pipelineMode）
   - release：部署验证后合并到主分支（发布流程）
   - integration：功能分支临时合入环境集成分支做集成测试，不合入主干

4. SSH 认证辅助
   - 统一密钥认证与密码认证（sshpass）的凭据设置片段
"""


# ============================================================
# 读取辅助
# ============================================================

def get_pipeline_mode(c) -> str:
    """流水线模式：release | integration"""
    return getattr(c, 'pipelineMode', 'release') or 'release'


def is_integration_mode(c) -> bool:
    return get_pipeline_mode(c) == 'integration'


def get_environments(c) -> list:
    """获取环境配置列表（统一为 dict 结构）"""
    envs = getattr(c, 'environments', None)
    if not envs:
        return []
    result = []
    for env in envs:
        if hasattr(env, 'model_dump'):
            env = env.model_dump()
        elif not isinstance(env, dict):
            continue
        if env.get('name'):
            result.append(env)
    return result


def has_environments(c) -> bool:
    return len(get_environments(c)) > 0


def get_load_balancer(c) -> dict:
    """获取负载均衡配置（dict，未启用返回空 dict）"""
    lb = getattr(c, 'loadBalancer', None)
    if not lb:
        return {}
    if hasattr(lb, 'model_dump'):
        lb = lb.model_dump()
    if not lb.get('host') or not lb.get('servers'):
        return {}
    return lb


def has_load_balancer(c) -> bool:
    return bool(get_load_balancer(c))


# ============================================================
# SSH 认证辅助（密钥 / sshpass 密码两种模式）
# ============================================================

def get_server_auth_type(c) -> str:
    """判断目标服务器的 SSH 认证方式：'ssh_key' | 'password'

    优先使用 c.server.sshKey；其次使用 c.serverAuthType；默认 password。
    """
    server = getattr(c, 'server', None)
    if server:
        if hasattr(server, 'model_dump'):
            server = server.model_dump()
        if isinstance(server, dict) and server.get('sshKey'):
            return 'ssh_key'
    auth = getattr(c, 'serverAuthType', '')
    if auth == 'ssh_key':
        return 'ssh_key'
    return 'password'


def github_ssh_setup_block(github_env_name: str = "$GITHUB_ENV") -> str:
    """GitHub Actions run 块：设置 SSH 认证（密钥或 sshpass）

    执行后在 $GITHUB_ENV 写入 AUTH_PREFIX 供后续 ssh/scp 使用：
    - 密钥模式：AUTH_PREFIX 为空，写入 ~/.ssh/id_rsa
    - 密码模式：AUTH_PREFIX=sshpass -e，SSHPASS 从 job env 读取
    """
    return """if [ -n "$SERVER_KEY" ]; then
  mkdir -p ~/.ssh
  echo "$SERVER_KEY" > ~/.ssh/id_rsa
  chmod 600 ~/.ssh/id_rsa
  echo "AUTH_PREFIX=" >> """ + github_env_name + """
else
  command -v sshpass >/dev/null 2>&1 || (sudo apt-get update -qq && sudo apt-get install -y -qq sshpass 2>/dev/null) || (sudo yum install -y sshpass 2>/dev/null)
  echo "AUTH_PREFIX=sshpass -e" >> """ + github_env_name + """
fi"""


def gitlab_ssh_setup_block() -> str:
    """GitLab CI before_script：设置 SSH 认证（密钥或 sshpass）

    export AUTH_PREFIX，在同一个 shell 会话中的后续 script 项生效。
    """
    return """if [ -n "$SERVER_SSH_KEY" ]; then
  mkdir -p ~/.ssh && echo "$SERVER_SSH_KEY" > ~/.ssh/id_rsa && chmod 600 ~/.ssh/id_rsa
  export AUTH_PREFIX=""
else
  command -v sshpass >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y -qq sshpass 2>/dev/null) || (yum install -y sshpass 2>/dev/null) || (sudo apt-get install -y sshpass 2>/dev/null)
  export SSHPASS="$SERVER_PASSWORD"
  export AUTH_PREFIX="sshpass -e"
fi"""


def rolling_deploy_ssh_setup() -> str:
    """滚动部署脚本 SSH 认证设置（bash，使用 AUTH_PREFIX 变量）

    密钥模式：写 id_rsa，AUTH_PREFIX 为空
    密码模式：从 SERVER_PASSWORD 环境变量读取，AUTH_PREFIX=sshpass -e
    """
    return """if [ -n "$SERVER_KEY" ]; then
    mkdir -p ~/.ssh && echo "$SERVER_KEY" > ~/.ssh/id_rsa && chmod 600 ~/.ssh/id_rsa
    AUTH_PREFIX=""
else
    command -v sshpass >/dev/null 2>&1 || (apt-get update -qq && apt-get install -y sshpass 2>/dev/null) || (yum install -y sshpass 2>/dev/null)
    export SSHPASS="$SERVER_PASSWORD"
    AUTH_PREFIX="sshpass -e"
fi"""


# ============================================================
# Nginx 负载均衡配置生成
# ============================================================

def build_nginx_upstream_conf(c) -> str:
    """生成 Nginx 负载均衡配置（部署到 LB 服务器 /etc/nginx/conf.d/）

    包含：
    - upstream 后端池（被动健康检查：max_fails/fail_timeout）
    - 反向代理 server 块（监听 LB 对外端口）
    """
    lb = get_load_balancer(c)
    project_name = getattr(c, 'projectName', 'app') or 'app'
    listen_port = lb.get('listenPort', 80) or 80
    backend_port = getattr(c, 'port', 8080) or 8080
    health_path = lb.get('healthCheckPath', '/') or '/'

    upstream_servers = "\n".join(
        f"    server {s.get('host')}:{backend_port} max_fails=3 fail_timeout=30s;"
        for s in lb.get('servers', [])
    )

    return f"""# Nginx 负载均衡配置 - {project_name}
# 生成: auto-cicd
# 安装位置: /etc/nginx/conf.d/{project_name}-lb.conf（LB 服务器）

upstream {project_name}_backend {{
{upstream_servers}
    keepalive 32;
}}

server {{
    listen {listen_port};
    server_name _;

    # 健康检查端点（供外部探活）
    location = /lb-health {{
        access_log off;
        return 200 'ok';
    }}

    location / {{
        proxy_pass http://{project_name}_backend;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Connection "";
        proxy_next_upstream error timeout http_502 http_503 http_504;
        proxy_next_upstream_tries 2;
        proxy_connect_timeout 5s;
        proxy_read_timeout 60s;
    }}
}}
"""


# ============================================================
# 滚动部署脚本生成
# ============================================================

def build_rolling_deploy_script(c, ssh_options: str = "-o StrictHostKeyChecking=no") -> str:
    """生成滚动部署 shell 脚本（在 CI 执行机上运行）

    流程（逐台后端）：
    1. 传输部署内容到后端服务器
    2. 启动/重启应用
    3. 健康检查（HTTP 探活，重试 N 次，间隔 5 秒）
    4. 健康检查失败 → 中止滚动（已部署的保留，未部署的不受影响）

    按 deployMethod 区分：
    - docker：传输源码，docker-compose up -d --build
    - direct：传输产物，按项目类型启动
    """
    lb = get_load_balancer(c)
    project_name = getattr(c, 'projectName', 'app') or 'app'
    backend_port = getattr(c, 'port', 8080) or 8080
    health_path = lb.get('healthCheckPath', '/') or '/'
    retries = lb.get('healthCheckRetries', 6) or 6
    deploy_method = getattr(c, 'deployMethod', 'direct')
    project_type = getattr(c, 'projectType', '')

    servers = lb.get('servers', [])
    server_list = " ".join(f'"{s.get("host")}"' for s in servers)
    user_map = " ".join(f'"{s.get("username", "root")}"' for s in servers)
    path_map = " ".join(f'"{s.get("deployPath", "/opt/apps")}"' for s in servers)

    if deploy_method == 'docker':
        deploy_cmds = f"""    # Docker 模式：传输源码，docker-compose 构建运行
    $AUTH_PREFIX scp $SSH_OPTIONS /tmp/{project_name}.tar.gz $USER@$HOST:/tmp/
    $AUTH_PREFIX ssh $SSH_OPTIONS $USER@$HOST "
        DEPLOY_DIR=$DEPLOY_PATH/{project_name}
        mkdir -p \\"$DEPLOY_DIR\\"
        tar -xzf /tmp/{project_name}.tar.gz -C \\"$DEPLOY_DIR\\"
        rm -f /tmp/{project_name}.tar.gz
        cd \\"$DEPLOY_DIR\\"
        docker-compose down --remove-orphans 2>/dev/null || true
        docker-compose up -d --build
    "
    HEALTH_PORT={backend_port}"""
    else:
        start_cmd = _get_direct_start_cmd(project_type, project_name, backend_port)
        deploy_cmds = f"""    # 直接部署模式：传输产物并启动
    $AUTH_PREFIX scp $SSH_OPTIONS {project_name}-artifact.tar.gz $USER@$HOST:/tmp/
    $AUTH_PREFIX ssh $SSH_OPTIONS $USER@$HOST "
        DEPLOY_DIR=$DEPLOY_PATH/{project_name}
        mkdir -p \\"$DEPLOY_DIR\\"
        tar -xzf /tmp/{project_name}-artifact.tar.gz -C \\"$DEPLOY_DIR\\"
        rm -f /tmp/{project_name}-artifact.tar.gz
        cd \\"$DEPLOY_DIR\\"
        # 停止旧进程
        pkill -f '{project_name}' 2>/dev/null || true
        sleep 2
        {start_cmd}
    "
    HEALTH_PORT={backend_port}"""

    ssh_setup = rolling_deploy_ssh_setup()
    return f"""#!/bin/bash
# 滚动部署脚本 - {project_name}
# 生成: auto-cicd
# 策略: 逐台部署 + 健康检查，失败即中止（保证服务不中断）

set -u
SSH_OPTIONS="{ssh_options}"
SERVERS=({server_list})
USERS=({user_map})
DEPLOY_PATHS=({path_map})
HEALTH_PATH="{health_path}"
RETRIES={retries}
TOTAL=${{#SERVERS[@]}}

# SSH 认证设置（密钥优先，回退 sshpass 密码认证）
{ssh_setup}

echo "[rolling] 开始滚动部署: $TOTAL 台后端服务器"

for i in "${{!SERVERS[@]}}"; do
    HOST=${{SERVERS[$i]}}
    USER=${{USERS[$i]}}
    DEPLOY_PATH=${{DEPLOY_PATHS[$i]}}
    echo ""
    echo "[rolling] ($((i+1))/$TOTAL) 部署后端: $HOST"

{deploy_cmds}

    # 健康检查
    echo "[rolling] 等待健康检查 http://$HOST:$HEALTH_PORT$HEALTH_PATH ..."
    HEALTHY=0
    for r in $(seq 1 $RETRIES); do
        sleep 5
        if curl -sf "http://$HOST:$HEALTH_PORT$HEALTH_PATH" > /dev/null 2>&1; then
            HEALTHY=1
            break
        fi
        echo "[rolling]   第 $r 次检查未通过，重试..."
    done

    if [ "$HEALTHY" -ne 1 ]; then
        echo "[rolling] ❌ 后端 $HOST 健康检查失败，中止滚动部署！"
        echo "[rolling] 已成功部署的节点保持新版本，其余节点保持旧版本，请人工介入"
        exit 1
    fi
    echo "[rolling] ✅ 后端 $HOST 部署成功并通过健康检查"
done

echo ""
echo "[rolling] 🎉 全部 $TOTAL 台后端部署完成"
"""


def _get_direct_start_cmd(project_type: str, project_name: str, port: int) -> str:
    """直接部署模式下各类型应用的启动命令"""
    if project_type == 'java-maven':
        return f'nohup java -jar {project_name}.jar --server.port={port} > app.log 2>&1 &'
    elif project_type == 'java-gradle':
        return f'nohup java -jar *.jar --server.port={port} > app.log 2>&1 &'
    elif project_type in ('vue', 'react'):
        return f'nohup npx serve -s dist -l {port} > app.log 2>&1 &'
    elif project_type == 'python':
        return 'nohup python3 app.py > app.log 2>&1 &'
    elif project_type == 'go':
        return 'nohup ./app > app.log 2>&1 &'
    return 'echo "启动命令未定义"'


def build_integration_script(env_branch: str, feature_branches: list) -> str:
    """生成集成测试模式的分支合并脚本

    在 CI 工作区将多个功能分支临时合入环境集成分支（仅本地，不推送），
    合并冲突时中止流水线。
    """
    merges = "\n".join(
        f'git merge origin/{b} --no-edit --no-ff || {{ echo "❌ 合并 {b} 冲突，集成测试中止"; exit 1; }}'
        for b in feature_branches
    )
    return f"""# 临时集成分支（仅 CI 工作区，不推送远端）
git checkout -B {env_branch} origin/{env_branch} 2>/dev/null || git checkout -b {env_branch}
{merges}
echo "✅ 已集成 {len(feature_branches)} 个功能分支到 {env_branch}（临时）\""""
