from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from generators.jenkins import generate_jenkins
from generators.aliyun import generate_aliyun
from generators.huawei import generate_huawei
from generators.tencent import generate_tencent
from generators.github import generate_github
from generators.gitlab import generate_gitlab
from generators.runner import generate_runner
from pipeline.engine import PipelineEngine, STEPS
from pipeline.credential import CredentialStore
from recommendations import get_deployment_recommendations
from pydantic import BaseModel
from typing import Optional, List
import os
import uuid
import json
import asyncio
from datetime import datetime

app = FastAPI(title="CI/CD 流水线生成器")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/output"

# 全局凭据存储
credential_store = CredentialStore()

# 活跃的任务引擎
active_engines: dict[str, PipelineEngine] = {}


class AppServerConfig(BaseModel):
    """应用服务器配置（TongWeb/Tomcat 等）"""
    type: str = "tongweb"       # tongweb | tomcat
    home: str = ""              # 安装路径
    port: int = 9060            # HTTP 端口
    contextPath: str = "/app"   # 应用上下文路径


class PipelineConfig(BaseModel):
    tool: str
    projectType: str
    deployMethod: str = "docker"  # docker | direct | app_server
    repoUrl: str
    projectName: str
    branch: str = "main"
    branches: List[str] = []  # 多分支支持
    port: int
    jdkVersion: str
    nodeVersion: str
    appServer: Optional[AppServerConfig] = None
    releaseStrategy: Optional[dict] = None  # 发布策略
    useChinaMirror: bool = False  # 是否使用国内镜像（用于国产 OS 或国内网络环境）


class ReleaseStrategy(BaseModel):
    strategy: str = "auto_merge"  # auto_merge | manual_merge | no_merge
    autoMergeDelay: int = 300  # 自动合并延迟（秒）
    requireApproval: bool = True
    enableRollback: bool = True
    mainBranch: str = "main"


class GitAuth(BaseModel):
    type: str = "password"
    username: str = ""
    password: str = ""
    sshKey: str = ""


class ServerConfig(BaseModel):
    host: str = ""
    port: int = 22
    username: str = "root"
    authType: str = "password"
    password: str = ""
    sshKey: str = ""
    deployPath: str = "/opt/apps"
    backupBeforeDeploy: bool = True  # 部署前备份旧版本
    # 堡垒机/跳板机配置（用于生成的 Pipeline 穿透访问）
    bastionHost: str = ""           # 堡垒机地址
    bastionPort: int = 22           # 堡垒机端口
    bastionUser: str = ""           # 堡垒机用户名
    bastionAuthType: str = "password"  # password | sshKey
    bastionPassword: str = ""       # 堡垒机密码
    bastionSshKey: str = ""         # 堡垒机 SSH 密钥


class RelayServerConfig(BaseModel):
    """中继服务器配置（用于跨云/隔离网络场景）"""
    host: str = ""              # 中继服务器地址
    port: int = 22
    username: str = "root"
    authType: str = "password"  # password | sshKey
    password: str = ""
    sshKey: str = ""
    isolated: bool = False      # 是否为隔离网络环境（如首信云）
    notes: str = ""             # 备注说明


class ToolServerConfig(BaseModel):
    """CI/CD 工具服务器配置（独立部署时）"""
    host: str = ""
    port: int = 22
    username: str = "root"
    authType: str = "password"
    password: str = ""
    sshKey: str = ""


class HopConfig(BaseModel):
    """单跳配置"""
    type: str = "relay"         # relay | bastion | zero_trust
    host: str = ""
    port: int = 22
    username: str = ""
    authType: str = "password"  # password | ssh_key | token | cert
    password: str = ""
    sshKey: str = ""
    jumpCommand: str = ""       # 堡垒机跳转命令
    targetHost: str = ""        # 零信任网关后的内网地址


class NetworkAccessConfig(BaseModel):
    """网络访问链路配置（多跳）"""
    hops: List[HopConfig] = []  # 有序跳转链路
    isolated: bool = False      # 是否为隔离网络
    # 向后兼容旧版单跳字段
    method: str = "direct"
    host: str = ""
    port: int = 22
    username: str = ""
    authType: str = "password"
    password: str = ""
    sshKey: str = ""
    jumpCommand: str = ""
    targetHost: str = ""


class AutoDeployConfig(BaseModel):
    tool: str
    projectType: str
    deployMethod: str = "docker"  # docker | direct | app_server
    repoUrl: str
    projectName: str
    branch: str = "main"
    branches: List[str] = []  # 多分支支持（用户在流水线运行时选择）
    port: int
    jdkVersion: str = ""
    nodeVersion: str = ""
    gitAuth: Optional[GitAuth] = None
    server: Optional[ServerConfig] = None
    relayServer: Optional[RelayServerConfig] = None  # 中继服务器（向后兼容）
    toolDeploy: str = "dedicated"  # dedicated | target | managed
    toolServer: Optional[ToolServerConfig] = None
    networkAccess: Optional[NetworkAccessConfig] = None
    appServer: Optional[AppServerConfig] = None
    releaseStrategy: Optional[dict] = None  # 发布策略


@app.get("/api/tools")
def list_tools():
    return {
        "tools": ["jenkins", "aliyun", "huawei", "tencent", "github", "gitlab", "runner"],
        "types": ["java-maven", "java-gradle", "vue", "react", "python", "go"]
    }


@app.get("/api/steps")
def list_steps():
    """返回自动化搭建的步骤定义"""
    return {"steps": STEPS}


@app.post("/api/generate-files")
def generate_pipeline_files(config: PipelineConfig):
    generators = {
        "jenkins": generate_jenkins,
        "aliyun": generate_aliyun,
        "huawei": generate_huawei,
        "tencent": generate_tencent,
        "github": generate_github,
        "gitlab": generate_gitlab,
        "runner": generate_runner,
    }
    generator = generators.get(config.tool)
    if not generator:
        return {"error": f"不支持的工具: {config.tool}"}

    output_subdir = f"{OUTPUT_DIR}/{config.projectName}_{config.tool}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
    os.makedirs(output_subdir, exist_ok=True)

    files = generator(config, output_subdir)
    for f in files:
        path = os.path.join(output_subdir, f["name"])
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(f["content"])

    return {
        "files": files,
        "outputDir": output_subdir,
        "tool": config.tool,
        "projectName": config.projectName
    }


@app.post("/api/auto-deploy")
async def start_auto_deploy(config: AutoDeployConfig):
    """启动自动化搭建流程，返回 task_id"""
    task_id = str(uuid.uuid4())[:8]

    # 构建完整配置
    full_config = config.model_dump()
    full_config["taskId"] = task_id

    # 存储凭据
    if config.gitAuth:
        credential_store.set_git_credential(task_id, config.gitAuth.model_dump())
    if config.server:
        credential_store.set_server_credential(task_id, config.server.model_dump())
    if config.relayServer:
        credential_store.set_relay_credential(task_id, config.relayServer.model_dump())
    if config.toolServer:
        credential_store.set_tool_server_credential(task_id, config.toolServer.model_dump())
    if config.networkAccess:
        credential_store.set_network_access_credential(task_id, config.networkAccess.model_dump())

    # 创建引擎
    engine = PipelineEngine(full_config, credential_store)
    active_engines[task_id] = engine

    return {
        "taskId": task_id,
        "wsUrl": f"/ws/pipeline/{task_id}",
        "steps": STEPS,
    }


@app.post("/api/recommendations")
def get_recommendations(config: dict):
    """根据配置获取部署建议"""
    return get_deployment_recommendations(config)


@app.websocket("/ws/pipeline/{task_id}")
async def pipeline_ws(websocket: WebSocket, task_id: str):
    """WebSocket 端点 - 实时推送搭建进度"""
    await websocket.accept()

    engine = active_engines.get(task_id)
    if not engine:
        await websocket.send_json({"step": "error", "status": "failed", "message": "任务不存在"})
        await websocket.close()
        return

    async def ws_send(message: str):
        try:
            await websocket.send_text(message)
        except Exception:
            pass

    engine.set_ws_send(ws_send)

    # 设置凭据等待器
    credential_waiter = asyncio.get_event_loop().create_future()
    engine._credential_waiter = credential_waiter

    try:
        # 启动执行流程（在后台任务中）
        async def run_pipeline():
            try:
                result = await engine.run()
                await websocket.send_json({
                    "step": "complete",
                    "status": "success" if result["success"] else "failed",
                    "message": "搭建完成" if result["success"] else "搭建失败",
                    "result": result,
                })
            except Exception as e:
                await websocket.send_json({
                    "step": "error",
                    "status": "failed",
                    "message": f"执行异常: {str(e)}",
                })

        task = asyncio.create_task(run_pipeline())

        # 监听前端消息（凭据回复等）
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)

                if msg.get("type") == "credential":
                    # 接收凭据
                    cred_type = msg.get("cred_type", "")
                    credential = msg.get("credential", {})

                    if cred_type == "git":
                        credential_store.set_git_credential(task_id, credential)
                    elif cred_type == "server":
                        credential_store.set_server_credential(task_id, credential)
                    elif cred_type == "relay":
                        credential_store.set_relay_credential(task_id, credential)

                    # 唤醒等待的引擎
                    if engine._credential_waiter and not engine._credential_waiter.done():
                        engine._credential_waiter.set_result(credential)

                elif msg.get("type") == "cancel":
                    task.cancel()
                    await websocket.send_json({"step": "cancel", "status": "failed", "message": "用户取消"})
                    break

            except WebSocketDisconnect:
                task.cancel()
                break
            except Exception:
                continue

    except WebSocketDisconnect:
        pass
    finally:
        if task_id in active_engines:
            del active_engines[task_id]
        credential_store.clear_task(task_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
