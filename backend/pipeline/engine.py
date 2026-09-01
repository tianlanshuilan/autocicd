"""自动化编排引擎 - 按步骤执行流水线搭建任务"""

import os
import json
import asyncio
import tempfile
import shutil
from datetime import datetime

from .git_ops import GitOps, GitError
from .ssh_ops import SSHOps, SSHError
from .credential import CredentialStore


# 步骤定义
STEPS = [
    {"id": "git_clone", "name": "克隆代码仓库", "order": 1},
    {"id": "branch_select", "name": "选择集成分支", "order": 2},
    {"id": "generate_config", "name": "生成配置文件", "order": 3},
    {"id": "git_push", "name": "推送配置到仓库", "order": 4},
    {"id": "ssh_connect", "name": "连接目标服务器", "order": 5},
    {"id": "install_tool", "name": "安装 CI/CD 工具", "order": 6},
    {"id": "configure_pipeline", "name": "配置流水线", "order": 7},
    {"id": "configure_cloud_service", "name": "配置云服务", "order": 8},
]


class PipelineEngine:
    """自动化流水线编排引擎"""

    def __init__(self, config: dict, credential_store: CredentialStore):
        """
        Args:
            config: 完整的部署配置
            credential_store: 凭据存储
        """
        self.config = config
        self.task_id = config.get("taskId", "")
        self.credential_store = credential_store
        self.work_dir = None
        self.generated_files = []
        self.git_ops = None
        self.ssh_ops = None
        self.jump_chain = []  # 已解析的跳转链路（复用给部署目标连接）
        self._ws_send = None
        self._credential_waiter = None

    def set_ws_send(self, send_func):
        """设置 WebSocket 消息发送函数"""
        self._ws_send = send_func

    async def send_message(self, step: str, status: str, message: str, log: str = ""):
        """发送进度消息到前端"""
        if self._ws_send:
            await self._ws_send(json.dumps({
                "step": step,
                "status": status,
                "message": message,
                "log": log,
            }, ensure_ascii=False))

    def _log(self, step: str, message: str):
        """同步日志回调（用于 Git/SSH 操作）"""
        # 在线程中通过 asyncio.run_coroutine_threadsafe 发送
        pass

    async def _async_log(self, step: str, message: str):
        """异步日志回调"""
        await self.send_message(step, "running", message)

    def _sync_log_factory(self, step: str):
        """创建同步日志回调函数"""
        loop = asyncio.get_event_loop()

        def log_callback(message: str):
            if self._ws_send:
                asyncio.run_coroutine_threadsafe(
                    self.send_message(step, "running", message),
                    loop
                )
        return log_callback

    async def request_credential(self, cred_type: str, reason: str) -> dict | None:
        """向前端请求凭据

        Args:
            cred_type: "git" | "server"
            reason: 请求原因

        Returns:
            用户输入的凭据 dict，或 None（用户取消）
        """
        await self.send_message(
            cred_type,
            "waiting_input",
            reason,
            json.dumps({"cred_type": cred_type}, ensure_ascii=False)
        )

        # 等待前端回复凭据
        if self._credential_waiter:
            future = asyncio.get_event_loop().create_future()
            self._credential_waiter = future
            credential = await future
            self._credential_waiter = None
            return credential
        return None

    def set_credential(self, credential: dict):
        """接收前端发来的凭据"""
        if self._credential_waiter and not self._credential_waiter.done():
            self._credential_waiter.set_result(credential)

    async def run(self):
        """执行完整的自动化搭建流程"""
        try:
            # 创建工作目录
            self.work_dir = tempfile.mkdtemp(prefix=f"cicd_{self.task_id}_")

            results = []

            # Step 1: Git Clone
            result = await self._step_git_clone()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 2: 分支选择（在生成配置前，确保多分支选择生效）
            result = await self._step_branch_select()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 3: 生成配置文件
            result = await self._step_generate_config()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 4: Git Push
            result = await self._step_git_push()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 5: SSH 连接（Android 应用分发 + 云托管工具不需要 SSH）
            tool = self.config.get("tool", "jenkins")
            is_app_distribute = self.config.get("projectType") == "android"
            is_cloud_tool = tool in ("github", "gitlab", "aliyun", "huawei", "tencent")
            if is_app_distribute and is_cloud_tool:
                await self.send_message("ssh_connect", "success", "应用分发模式，跳过服务器连接")
            else:
                result = await self._step_ssh_connect()
                results.append(result)
                if result["status"] == "failed":
                    return self._build_result(results, False)

            # Step 6: 安装 CI/CD 工具（自建工具）；existing 模式跳过安装仅准备运行环境
            tool_deploy = self.config.get("toolDeploy", "dedicated")
            tool = self.config.get("tool", "jenkins")
            if tool_deploy in ("dedicated", "target", "existing") and tool in ("jenkins", "runner"):
                result = await self._step_install_tool()
                results.append(result)
                if result["status"] == "failed":
                    return self._build_result(results, False)

            # Step 7: 配置流水线（创建 Job、设置凭据、配置 Webhook）
            result = await self._step_configure_pipeline()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 8: 配置云服务（云托管服务需要）
            # - aliyun/huawei/tencent: 通过 OpenAPI 创建流水线
            # - github/gitlab: 流水线随配置文件推送自动启用，此步骤写入 Secrets/Variables
            tool = self.config.get("tool", "jenkins")
            if tool in ("aliyun", "huawei", "tencent", "github", "gitlab"):
                result = await self._step_configure_cloud_service()
                results.append(result)
                if result["status"] == "failed":
                    return self._build_result(results, False)

            success = all(r["status"] not in ("failed",) for r in results)
            return self._build_result(results, success)

        except Exception as e:
            await self.send_message("error", "failed", f"执行异常: {str(e)}")
            return self._build_result([], False, error=str(e))

        finally:
            self._cleanup()

    async def _step_git_clone(self) -> dict:
        """Step 1: 克隆代码仓库"""
        step = "git_clone"
        branches = self.config.get("branches", [])
        if not branches:
            branches = [self.config.get("branch", "main")]

        if len(branches) > 1:
            await self.send_message(step, "running", f"正在克隆代码仓库（多分支: {', '.join(branches)}）...")
        else:
            await self.send_message(step, "running", "正在克隆代码仓库...")

        git_cred = self.config.get("gitAuth", {})

        # 检查是否需要弹窗补充凭据
        if git_cred.get("type") == "password" and not git_cred.get("password"):
            cred = await self.request_credential("git", "需要 Git 密码才能克隆仓库")
            if cred:
                git_cred.update(cred)
                self.config["gitAuth"] = git_cred
            else:
                await self.send_message(step, "failed", "用户取消了凭据输入")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        if git_cred.get("type") == "ssh_key" and not git_cred.get("sshKey"):
            cred = await self.request_credential("git", "需要 SSH 密钥才能克隆仓库")
            if cred:
                git_cred.update(cred)
                self.config["gitAuth"] = git_cred
            else:
                await self.send_message(step, "failed", "用户取消了凭据输入")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        # 多分支时克隆所有分支
        branch_to_clone = branches[0] if len(branches) == 1 else "--all"
        self.git_ops = GitOps(
            repo_url=self.config["repoUrl"],
            branch=branch_to_clone,
            credential=git_cred
        )

        try:
            log_cb = self._sync_log_factory(step)
            await asyncio.get_event_loop().run_in_executor(
                None,
                lambda: self.git_ops.clone(self.work_dir, log_cb)
            )
            if len(branches) > 1:
                await self.send_message(step, "success", f"代码仓库克隆成功（含 {len(branches)} 个分支）")
            else:
                await self.send_message(step, "success", "代码仓库克隆成功")
            return {"step": step, "status": "success", "message": "克隆完成"}
        except GitError as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

    def _bundle_dependencies_sync(self, log) -> bool:
        """依赖离线构建支持（三种模式）

        模式 A（预拉取）：按 BOM 原始地址拉取依赖到 .offline-deps/
        模式 B（本地检测）：检测仓库中已存在的依赖文件（开发者已提交）
        模式 C（独立仓库）：从独立依赖仓库克隆并检测
        """
        import subprocess

        project_type = self.config.get("projectType", "")
        work_dir = getattr(self.git_ops, "work_dir", None) if self.git_ops else None
        if not work_dir or not os.path.isdir(work_dir):
            log("仓库尚未克隆，跳过依赖处理")
            return False

        # ===== 模式 C：从独立依赖仓库克隆 =====
        dep_repo_config = self.config.get("dependencyRepo", {})
        dep_repo_url = dep_repo_config.get("url", "") if dep_repo_config else ""
        if dep_repo_url:
            log(f"检测到独立依赖仓库配置: {dep_repo_url}")
            dep_repo_dir = os.path.join(work_dir, ".dep-repo")
            if self._clone_dependency_repo(dep_repo_config, dep_repo_dir, log):
                detected_path = self._detect_local_dependencies(project_type, dep_repo_dir, log)
                if detected_path:
                    log(f"✅ 在依赖仓库中检测到: {detected_path}")
                    log("   流水线将从依赖仓库获取依赖进行离线构建")
                    # 设置配置，让生成器知道依赖在 .dep-repo/<detected_path>
                    self.config["detectedDepsPath"] = f".dep-repo/{detected_path}"
                    self.config["depRepoUrl"] = dep_repo_url
                    self.config["depRepoBranch"] = dep_repo_config.get("branch", "main")
                    return True
                else:
                    log(f"⚠️ 依赖仓库中未检测到 {project_type} 类型的依赖文件")
            else:
                log("⚠️ 依赖仓库克隆失败，跳过依赖处理")

        # ===== 模式 B：检测本地已存在的依赖 =====
        detected_path = self._detect_local_dependencies(project_type, work_dir, log)
        if detected_path:
            log(f"✅ 检测到仓库中已存在依赖文件: {detected_path}")
            log("   流水线将直接使用本地依赖进行离线构建")
            # 写入标记文件，告知生成器使用检测到的路径
            marker = os.path.join(work_dir, ".offline-deps", "LOCAL-DEPS-DETECTED.txt")
            os.makedirs(os.path.dirname(marker), exist_ok=True)
            with open(marker, "w") as f:
                f.write(f"detected_path={detected_path}\nproject_type={project_type}\n")
            # 设置配置，让生成器使用检测到的路径
            self.config["detectedDepsPath"] = detected_path
            return True

        # ===== 模式 A：从 BOM 地址预拉取 =====
        log("未检测到本地依赖，尝试从 BOM 地址预拉取...")
        return self._pull_dependencies_from_bom(project_type, work_dir, log)

    def _clone_dependency_repo(self, dep_repo_config: dict, target_dir: str, log) -> bool:
        """克隆独立依赖仓库到指定目录"""
        import subprocess
        
        url = dep_repo_config.get("url", "")
        branch = dep_repo_config.get("branch", "main")
        auth_type = dep_repo_config.get("authType", "password")
        username = dep_repo_config.get("username", "")
        password = dep_repo_config.get("password", "")
        ssh_key = dep_repo_config.get("sshKey", "")
        
        if not url:
            return False
        
        # 清理目标目录
        if os.path.exists(target_dir):
            import shutil
            shutil.rmtree(target_dir)
        
        # 构建克隆 URL（密码认证时嵌入凭据）
        clone_url = url
        if auth_type == "password" and username and password:
            # 将 https://github.com/org/repo.git 转为 https://user:pass@github.com/org/repo.git
            if url.startswith("https://"):
                clone_url = url.replace("https://", f"https://{username}:{password}@")
        
        log(f"   正在克隆依赖仓库 (分支: {branch})...")
        try:
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", clone_url, target_dir],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode != 0:
                err = (result.stderr or "").strip()[-300:]
                log(f"   ❌ 依赖仓库克隆失败: {err}")
                return False
            log(f"   ✅ 依赖仓库克隆成功")
            return True
        except subprocess.TimeoutExpired:
            log("   ❌ 依赖仓库克隆超时（超过 5 分钟）")
            return False
        except Exception as e:
            log(f"   ❌ 依赖仓库克隆异常: {e}")
            return False

    def _detect_local_dependencies(self, project_type: str, work_dir: str, log) -> str:
        """检测仓库中是否已存在依赖文件（开发者已提交）
        
        Returns: 检测到的依赖路径（相对于 work_dir），未检测到返回空字符串
        """
        # 各类型项目可能的本地依赖目录
        checks = {
            "java-maven": [
                ("maven-repo", "Maven 本地仓库"),
                (".m2/repository", "Maven .m2 仓库"),
                ("lib", "lib 依赖目录"),
            ],
            "java-gradle": [
                ("gradle-cache", "Gradle 缓存"),
                ("lib", "lib 依赖目录"),
            ],
            "vue": [
                ("node_modules", "node_modules"),
                ("npm-cache", "npm 离线缓存"),
            ],
            "react": [
                ("node_modules", "node_modules"),
                ("npm-cache", "npm 离线缓存"),
            ],
            "python": [
                ("pip-packages", "pip 离线包"),
                ("wheels", "Python wheels"),
                ("requirements-local", "本地依赖目录"),
            ],
            "go": [
                ("vendor", "Go vendor 目录"),
            ],
        }

        paths = checks.get(project_type, [])
        for path, desc in paths:
            full_path = os.path.join(work_dir, path)
            if os.path.exists(full_path) and os.path.isdir(full_path):
                # 检查目录是否非空
                if os.listdir(full_path):
                    log(f"   检测到 {desc}: {path}/")
                    return path
        
        return ""

    def _pull_dependencies_from_bom(self, project_type: str, work_dir: str, log) -> bool:
        """从 BOM 声明的原始地址预拉取依赖到 .offline-deps/"""
        import subprocess

        deps_dir = os.path.join(work_dir, ".offline-deps")
        os.makedirs(deps_dir, exist_ok=True)

        # 项目类型 → (所需工具, 拉取命令)；命令为 None 表示暂不支持
        tasks = {
            "java-maven": ("mvn", ["mvn", "-q", "-B", "dependency:go-offline",
                                   f"-Dmaven.repo.local={os.path.join(deps_dir, 'maven-repo')}"]),
            "java-gradle": ("gradle", None),
            "vue": ("npm", ["npm", "ci", "--cache", os.path.join(deps_dir, "npm-cache")]),
            "react": ("npm", ["npm", "ci", "--cache", os.path.join(deps_dir, "npm-cache")]),
            "python": ("pip3", ["pip3", "download", "-r", "requirements.txt",
                                "-d", os.path.join(deps_dir, "pip-packages")]),
            "go": ("go", ["go", "mod", "vendor"]),
        }

        task = tasks.get(project_type)
        if not task:
            log(f"项目类型 {project_type} 不支持依赖预拉取")
            return False
        tool_name, cmd = task
        if cmd is None:
            log("Gradle 项目暂不支持将依赖缓存提交到仓库，流水线保持在线模式")
            return False

        if not shutil.which(tool_name):
            log(f"⚠️ 本机未安装 {tool_name}，无法预拉取依赖，流水线保持在线模式构建")
            return False

        # 校验 BOM 文件存在
        bom_files = {"java-maven": "pom.xml", "vue": "package-lock.json", "react": "package-lock.json",
                     "python": "requirements.txt", "go": "go.mod"}
        bom = bom_files.get(project_type)
        if bom and not os.path.exists(os.path.join(work_dir, bom)):
            log(f"⚠️ 仓库中未找到 {bom}，跳过依赖预拉取")
            return False

        log(f"执行依赖拉取: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd, cwd=work_dir, capture_output=True, text=True, timeout=1800
            )
            if result.returncode != 0:
                err = (result.stderr or result.stdout or "").strip()[-500:]
                log(f"❌ 依赖拉取失败: {err}")
                return False
        except subprocess.TimeoutExpired:
            log("❌ 依赖拉取超时（超过 30 分钟）")
            return False
        except Exception as e:
            log(f"❌ 依赖拉取异常: {e}")
            return False

        # 写入说明文件，便于流水线与使用者识别离线依赖包
        with open(os.path.join(deps_dir, "OFFLINE-DEPS.txt"), "w") as f:
            f.write(
                "本目录由 auto-cicd 平台预拉取生成，用于内网离线构建。\n"
                f"项目类型: {project_type}\n"
                "依赖按 BOM 声明的原始地址拉取，未修改任何依赖地址。\n"
                "流水线构建时以离线模式使用本目录，无需外网访问。\n"
            )
        log("✅ 依赖预拉取完成（.offline-deps/），将随代码推送到仓库")
        return True

    async def _step_generate_config(self) -> dict:
        """Step 2: 生成 CI/CD 配置文件"""
        step = "generate_config"
        await self.send_message(step, "running", "正在生成配置文件...")

        try:
            from generators.jenkins import generate_jenkins
            from generators.aliyun import generate_aliyun
            from generators.huawei import generate_huawei
            from generators.tencent import generate_tencent
            from generators.github import generate_github
            from generators.gitlab import generate_gitlab

            generators = {
                "jenkins": generate_jenkins,
                "aliyun": generate_aliyun,
                "huawei": generate_huawei,
                "tencent": generate_tencent,
                "github": generate_github,
                "gitlab": generate_gitlab,
            }

            generator = generators.get(self.config["tool"])
            if not generator:
                raise ValueError(f"不支持的工具: {self.config['tool']}")

            # 自动检测本地依赖（依赖即代码模式）
            self.config["depsBundled"] = False
            self.config["detectedDepsPath"] = ""
            await self.send_message(step, "running", "正在检测仓库中的本地依赖...")
            log_cb = self._sync_log_factory(step)
            loop_bg = asyncio.get_event_loop()
            bundled = await loop_bg.run_in_executor(
                None, lambda: self._bundle_dependencies_sync(log_cb)
            )
            self.config["depsBundled"] = bundled
            if bundled:
                detected_path = self.config.get("detectedDepsPath", "")
                if detected_path:
                    await self.send_message(step, "running", f"✅ 检测到本地依赖: {detected_path}，流水线将以离线模式构建")
                else:
                    await self.send_message(step, "running", "✅ 依赖预拉取完成，将随代码推送到仓库，流水线以离线模式构建")
            else:
                await self.send_message(step, "running", "未检测到本地依赖，生成的流水线将保持在线模式构建")

            output_dir = os.path.join(self.work_dir, "config_output")
            os.makedirs(output_dir, exist_ok=True)

            # 构建 config 对象（模拟 Pydantic model）
            class ConfigObj:
                pass

            cfg = ConfigObj()
            for k, v in self.config.items():
                setattr(cfg, k, v)

            # 将 server 配置平铺到顶层，方便生成器访问
            server_config = self.config.get("server", {})
            if server_config:
                setattr(cfg, 'serverHost', server_config.get('host', ''))
                setattr(cfg, 'serverUser', server_config.get('username', 'root'))
                setattr(cfg, 'deployPath', server_config.get('deployPath', '/opt/apps'))
                setattr(cfg, 'backupBeforeDeploy', server_config.get('backupBeforeDeploy', True))
                # SSH 认证方式（ssh_key / password），供生成器判断部署凭据路径
                setattr(cfg, 'serverAuthType', server_config.get('authType', 'password'))
                setattr(cfg, 'serverPassword', server_config.get('password', ''))
                setattr(cfg, 'serverSshKey', server_config.get('sshKey', ''))

            # 从 networkAccess.hops 中提取堡垒机信息（用于生成的 Pipeline 穿透访问）
            network_access = self.config.get("networkAccess", {})
            hops = network_access.get("hops", [])
            bastion_host = ""
            bastion_port = 22
            bastion_user = ""
            bastion_auth_type = "password"
            bastion_password = ""
            bastion_ssh_key = ""
            
            # 查找第一个 bastion 类型的 hop
            for hop in hops:
                if hop.get("type") == "bastion":
                    bastion_host = hop.get("host", "")
                    bastion_port = hop.get("port", 22)
                    bastion_user = hop.get("username", "")
                    bastion_auth_type = hop.get("authType", "password")
                    bastion_password = hop.get("password", "")
                    bastion_ssh_key = hop.get("sshKey", "")
                    break
            
            # 设置堡垒机字段（供生成器使用）
            setattr(cfg, 'bastionHost', bastion_host)
            setattr(cfg, 'bastionPort', bastion_port)
            setattr(cfg, 'bastionUser', bastion_user)
            setattr(cfg, 'bastionAuthType', bastion_auth_type)
            setattr(cfg, 'bastionPassword', bastion_password)
            setattr(cfg, 'bastionSshKey', bastion_ssh_key)

            loop = asyncio.get_event_loop()
            self.generated_files = await loop.run_in_executor(
                None, generator, cfg, output_dir
            )

            for f in self.generated_files:
                await self.send_message(step, "running", f"生成: {f['name']}")

            await self.send_message(step, "success", f"已生成 {len(self.generated_files)} 个配置文件")
            return {"step": step, "status": "success", "message": f"生成 {len(self.generated_files)} 个文件"}

        except Exception as e:
            await self.send_message(step, "failed", f"生成失败: {str(e)}")
            return {"step": step, "status": "failed", "message": str(e)}

    async def _step_git_push(self) -> dict:
        """Step 3: 推送配置文件到仓库"""
        step = "git_push"
        await self.send_message(step, "running", "正在推送配置文件到仓库...")

        if not self.git_ops:
            await self.send_message(step, "failed", "Git 未初始化")
            return {"step": step, "status": "failed", "message": "Git 未初始化"}

        try:
            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()

            # 复制文件到仓库
            await loop.run_in_executor(
                None,
                lambda: self.git_ops.copy_files_to_repo(self.generated_files, log_cb)
            )

            # 提交并推送
            await loop.run_in_executor(
                None,
                lambda: self.git_ops.commit_and_push(self.config["projectName"], log_cb)
            )

            await self.send_message(step, "success", "配置文件已推送到远程仓库")
            return {"step": step, "status": "success", "message": "推送成功"}

        except (GitError, Exception) as e:
            await self.send_message(step, "failed", f"推送失败: {str(e)}")
            return {"step": step, "status": "failed", "message": str(e)}

    async def _step_branch_select(self) -> dict:
        """Step 4: 等待用户选择需要集成的分支"""
        step = "branch_select"
        default_branch = self.config.get("branch", "main")

        await self.send_message(step, "running", "正在获取仓库分支列表...")

        # 获取仓库所有分支
        available_branches = []
        if self.git_ops:
            try:
                loop = asyncio.get_event_loop()
                available_branches = await loop.run_in_executor(
                    None, self.git_ops.list_branches
                )
            except Exception:
                pass

        # 如果获取失败，至少包含默认分支
        if not available_branches:
            available_branches = [default_branch]

        # 发送分支列表给前端，等待用户选择
        import json as _json
        await self.send_message(
            step,
            "waiting_input",
            f"仓库共有 {len(available_branches)} 个分支，请选择需要集成的分支",
            _json.dumps({"branches": available_branches}, ensure_ascii=False)
        )

        # 等待前端回复选择的分支
        if self._credential_waiter:
            future = asyncio.get_event_loop().create_future()
            self._credential_waiter = future
            selection = await future
            self._credential_waiter = None

            if selection and selection.get("branches"):
                selected = selection["branches"]
                release_strategy = selection.get("releaseStrategy")

                # 更新 config 中的分支和发布策略
                self.config["branches"] = selected
                if release_strategy:
                    self.config["releaseStrategy"] = release_strategy

                if len(selected) > 1:
                    await self.send_message(
                        step, "success",
                        f"已选择 {len(selected)} 个分支: {', '.join(selected)}"
                    )
                else:
                    await self.send_message(
                        step, "success",
                        f"已选择分支: {selected[0]}"
                    )
                return {"step": step, "status": "success", "message": f"已选择 {len(selected)} 个分支"}
            else:
                # 用户取消，使用默认分支
                self.config["branches"] = [default_branch]
                await self.send_message(step, "success", f"使用默认分支: {default_branch}")
                return {"step": step, "status": "success", "message": "使用默认分支"}

        # 默认使用默认分支
        self.config["branches"] = [default_branch]
        await self.send_message(step, "success", f"使用默认分支: {default_branch}")
        return {"step": step, "status": "success", "message": "使用默认分支"}

    async def _step_ssh_connect(self) -> dict:
        """Step 4: SSH 连接工具安装目标服务器（支持多跳链路）"""
        step = "ssh_connect"

        server = self.config.get("server", {})
        relay = self.config.get("relayServer", {})
        network_access = self.config.get("networkAccess", {})
        hops = network_access.get("hops", [])

        if not server.get("host"):
            await self.send_message(step, "failed", "未配置服务器地址")
            return {"step": step, "status": "failed", "message": "服务器地址为空"}

        # 确定实际安装目标：专用服务器模式下工具装到 toolServer，否则装到目标服务器
        tool_deploy = self.config.get("toolDeploy", "target")
        tool_server = self.config.get("toolServer", {}) or {}
        use_dedicated = (tool_deploy == "dedicated" and tool_server.get("host"))

        if use_dedicated:
            install_host = tool_server["host"]
            install_port = tool_server.get("port", 22)
            install_username = tool_server.get("username", "root")
            target_label = f"专用工具服务器 {install_host}"
        else:
            install_host = server["host"]
            install_port = server.get("port", 22)
            install_username = server.get("username", "root")
            target_label = f"目标服务器 {install_host}"

        server_cred = {
            "authType": (tool_server.get("authType", "password") if use_dedicated else server.get("authType", "password")),
            "password": (tool_server.get("password", "") if use_dedicated else server.get("password", "")),
            "sshKey": (tool_server.get("sshKey", "") if use_dedicated else server.get("sshKey", "")),
        }
        # 兼容旧字段名
        server_cred["authType"] = server_cred.get("authType") or server_cred.get("auth_type", "password")
        server_cred["password"] = server_cred.get("password") or server_cred.get("passwd", "")
        server_cred["sshKey"] = server_cred.get("sshKey") or server_cred.get("ssh_key", "")

        # 检查安装目标服务器凭据
        cred_type = "tool_server" if use_dedicated else "server"
        if server_cred["authType"] == "password" and not server_cred["password"]:
            cred = await self.request_credential(cred_type, f"需要{target_label}密码才能连接")
            if cred:
                server_cred.update(cred)
            else:
                await self.send_message(step, "failed", "用户取消了凭据输入")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        if server_cred["authType"] == "ssh_key" and not server_cred["sshKey"]:
            cred = await self.request_credential(cred_type, f"需要{target_label} SSH 密钥才能连接")
            if cred:
                server_cred.update(cred)
            else:
                await self.send_message(step, "failed", "用户取消了凭据输入")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        # 构建跳转链路
        jump_chain = []

        # 优先使用新的 hops 数组
        if hops:
            for i, hop in enumerate(hops):
                hop_cred = {
                    "authType": hop.get("authType", "password"),
                    "password": hop.get("password", ""),
                    "sshKey": hop.get("sshKey", ""),
                }
                # 检查凭据
                if hop_cred["authType"] == "password" and not hop_cred["password"]:
                    type_labels = {"relay": "中继服务器", "bastion": "堡垒机", "zero_trust": "零信任网关"}
                    label = type_labels.get(hop.get("type", ""), f"第{i+1}跳")
                    cred = await self.request_credential("relay", f"需要{label}密码")
                    if cred:
                        hop_cred.update(cred)
                    else:
                        await self.send_message(step, "failed", "用户取消了凭据输入")
                        return {"step": step, "status": "failed", "message": "凭据缺失"}

                jump_chain.append({
                    "type": hop.get("type", "relay"),
                    "host": hop.get("host", ""),
                    "port": hop.get("port", 22),
                    "username": hop.get("username", "root"),
                    "credential": hop_cred,
                    "jumpCommand": hop.get("jumpCommand", ""),
                    "targetHost": hop.get("targetHost", ""),
                })

        # 向后兼容旧版单跳配置
        elif relay.get("host"):
            relay_cred = {
                "authType": relay.get("authType", "password"),
                "password": relay.get("password", ""),
                "sshKey": relay.get("sshKey", ""),
            }
            jump_chain.append({
                "type": "relay",
                "host": relay["host"],
                "port": relay.get("port", 22),
                "username": relay.get("username", "root"),
                "credential": relay_cred,
            })

        # 保存已解析的链路，供部署目标服务器连接复用
        self.jump_chain = jump_chain

        # 生成连接日志
        if jump_chain:
            hop_labels = [f"{h['type']}({h['host']})" for h in jump_chain]
            chain_desc = " → ".join(hop_labels) + f" → 目标({install_host})"
            await self.send_message(step, "running", f"正在通过链路连接: {chain_desc}")
        elif use_dedicated:
            await self.send_message(step, "running", f"正在连接专用工具服务器 {install_host}:{install_port}...")
        else:
            await self.send_message(step, "running", "正在连接目标服务器...")

        # 确定最终目标地址（可能被零信任跳覆盖）
        target_host = install_host
        if jump_chain and jump_chain[-1].get("targetHost"):
            target_host = jump_chain[-1]["targetHost"]

        # 创建 SSHOps（支持多跳链路；专用服务器模式直连）
        if jump_chain and not use_dedicated:
            self.ssh_ops = SSHOps(
                host=target_host,
                port=install_port,
                username=install_username,
                credential=server_cred,
                jump_chain=jump_chain,
            )
        else:
            self.ssh_ops = SSHOps(
                host=install_host,
                port=install_port,
                username=install_username,
                credential=server_cred,
            )

        try:
            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.ssh_ops.connect(log_cb))

            if jump_chain and not use_dedicated:
                await self.send_message(step, "success", f"通过 {len(jump_chain)} 跳链路连接目标服务器成功")
            elif use_dedicated:
                await self.send_message(step, "success", f"专用工具服务器 {install_host} 连接成功")
            else:
                await self.send_message(step, "success", "服务器连接成功")
            return {"step": step, "status": "success", "message": "连接成功"}

        except SSHError as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

    async def _step_install_tool(self) -> dict:
        """Step 6: 安装 CI/CD 工具"""
        step = "install_tool"
        tool = self.config.get("tool", "jenkins")
        tool_deploy = self.config.get("toolDeploy", "dedicated")
        use_china_mirror = self.config.get("useChinaMirror", False)  # 是否使用国内镜像

        # 已部署工具模式：跳过安装，仅在部署目标服务器准备运行环境
        if tool_deploy == "existing":
            await self.send_message(step, "running", "检测到已部署的 CI/CD 工具，跳过安装，准备部署目标运行环境...")
            if self.ssh_ops:
                try:
                    await self._prepare_target_runtime(use_china_mirror)
                    await self._prepare_extra_runtimes(use_china_mirror)
                except SSHError as e:
                    await self.send_message(step, "running", f"⚠️ 部署目标运行环境准备警告: {e}")
            else:
                await self.send_message(step, "running", "未配置部署目标服务器，跳过运行环境准备")
            await self.send_message(step, "success", "已复用现有 CI/CD 工具，无需安装")
            return {"step": step, "status": "success", "message": "复用现有工具"}

        if not self.ssh_ops:
            await self.send_message(step, "failed", "SSH 未连接")
            return {"step": step, "status": "failed", "message": "SSH 未连接"}

        try:
            # 云托管工具（阿里云效/GitHub Actions/GitLab CI 等）无需安装 CI 工具，
            # 仅需在部署目标服务器准备项目运行环境
            if tool in ("aliyun", "huawei", "tencent", "github", "gitlab"):
                await self.send_message(step, "running", "云托管服务无需安装 CI 工具，正在准备部署目标运行环境...")
                await self._prepare_target_runtime(use_china_mirror)
                await self._prepare_extra_runtimes(use_china_mirror)
                return {"step": step, "status": "success", "message": "部署目标运行环境已就绪"}

            tool_names = {
                "jenkins": "Jenkins",
                "runner": "GitLab/GitHub Runner"
            }
            tool_name = tool_names.get(tool, tool)
            await self.send_message(step, "running", f"正在安装 {tool_name}...")

            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()

            await loop.run_in_executor(
                None,
                lambda: self.ssh_ops.install_ci_tool(tool, tool_deploy, use_china_mirror, log_cb)
            )

            await self.send_message(step, "success", f"{tool_name} 安装完成")

            # 在部署目标服务器上准备项目运行环境（Docker 或语言运行时）
            await self._prepare_target_runtime(use_china_mirror)

            # 负载均衡/多环境：额外服务器运行环境准备
            await self._prepare_extra_runtimes(use_china_mirror)

            return {"step": step, "status": "success", "message": f"{tool_name} 已安装"}

        except SSHError as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

    async def _prepare_target_runtime(self, use_china_mirror: bool = False):
        """在部署目标服务器上准备项目运行环境

        - deployMethod=docker：安装/检查 Docker + docker-compose
        - deployMethod=direct/app_server：按项目类型安装 Java/Node/Python/Go 运行时

        工具装在目标服务器时复用当前连接；专用工具服务器模式下
        单独通过跳转链路连接部署目标服务器。运行环境准备失败不阻断
        整体流程（记录警告，用户可手动处理）。
        """
        step = "install_tool"
        deploy_method = self.config.get("deployMethod", "direct")
        project_type = self.config.get("projectType", "")

        runtime_desc = "Docker 环境" if deploy_method == "docker" else f"{project_type} 运行环境"
        await self.send_message(step, "running", f"正在准备部署服务器{runtime_desc}...")

        log_cb = self._sync_log_factory(step)
        loop = asyncio.get_event_loop()

        tool_deploy = self.config.get("toolDeploy", "target")
        tool_server = self.config.get("toolServer", {}) or {}
        use_dedicated = (tool_deploy == "dedicated" and tool_server.get("host"))

        try:
            if not use_dedicated:
                # 工具与部署目标同一台服务器，复用当前连接
                await loop.run_in_executor(
                    None,
                    lambda: self.ssh_ops.prepare_deploy_runtime(
                        deploy_method, project_type, self.config, use_china_mirror, log_cb)
                )
            else:
                # 专用工具服务器：单独连接部署目标服务器
                server = self.config.get("server", {})
                server_cred = {
                    "authType": server.get("authType", "password"),
                    "password": server.get("password", ""),
                    "sshKey": server.get("sshKey", ""),
                }
                if server_cred["authType"] == "password" and not server_cred["password"]:
                    cred = await self.request_credential("server", f"需要部署目标服务器 {server.get('host')} 密码")
                    if cred:
                        server_cred.update(cred)
                if server_cred["authType"] in ("ssh_key", "sshKey") and not server_cred["sshKey"]:
                    cred = await self.request_credential("server", f"需要部署目标服务器 {server.get('host')} SSH 密钥")
                    if cred:
                        server_cred.update(cred)

                target_ops = SSHOps(
                    host=server.get("host", ""),
                    port=server.get("port", 22),
                    username=server.get("username", "root"),
                    credential=server_cred,
                    jump_chain=self.jump_chain,
                )
                try:
                    await loop.run_in_executor(None, lambda: target_ops.connect(log_cb))
                    await loop.run_in_executor(
                        None,
                        lambda: target_ops.prepare_deploy_runtime(
                            deploy_method, project_type, self.config, use_china_mirror, log_cb)
                    )
                finally:
                    target_ops.close()

            await self.send_message(step, "success", f"部署服务器{runtime_desc}准备完成")

        except SSHError as e:
            # 运行环境准备失败不阻断流程，记录警告
            await self.send_message(step, "running", f"⚠️ 运行环境准备失败（{e}），部署前请确认目标服务器环境")

    async def _prepare_extra_runtimes(self, use_china_mirror: bool = False):
        """负载均衡/多环境：在额外服务器上准备运行环境（失败不阻断）

        - 负载均衡后端服务器：按 deployMethod 准备 Docker/语言运行时
        - 多环境服务器：同上
        - 负载均衡服务器：安装 Nginx 并部署 upstream 配置
        """
        step = "install_tool"
        loop = asyncio.get_event_loop()
        log_cb = self._sync_log_factory(step)

        lb = self.config.get("loadBalancer") or {}
        lb_enabled = bool(lb.get("host") and lb.get("servers"))
        envs = self.config.get("environments") or []
        if not lb_enabled and not envs:
            return

        deploy_method = self.config.get("deployMethod", "direct")
        project_type = self.config.get("projectType", "")
        main_host = (self.config.get("server") or {}).get("host", "")

        # 收集额外服务器（按 host 去重，跳过主服务器）
        targets = []
        if lb_enabled:
            for i, s in enumerate(lb["servers"]):
                if s.get("host") and s.get("host") != main_host:
                    targets.append((s, f"负载均衡后端 #{i + 1}（{s['host']}）"))
        for env in envs:
            s = env.get("server") or {}
            if s.get("host") and s.get("host") != main_host:
                targets.append((s, f"{env.get('name', 'env')} 环境服务器（{s['host']}）"))

        # 去重（同一 host 只准备一次）
        seen = set()
        for server, label in targets:
            host = server["host"]
            if host in seen:
                continue
            seen.add(host)
            try:
                await self.send_message(step, "running", f"正在准备{label}运行环境...")
                ops = await self._connect_extra_server(server, label)
                try:
                    await loop.run_in_executor(
                        None,
                        lambda ops=ops: ops.prepare_deploy_runtime(
                            deploy_method, project_type, self.config, use_china_mirror, log_cb)
                    )
                finally:
                    ops.close()
            except Exception as e:
                await self.send_message(step, "running", f"⚠️ {label}运行环境准备失败（{e}），部署前请手动确认")

        # 负载均衡服务器：安装 Nginx 并部署 upstream 配置
        if lb_enabled and lb.get("host") != main_host:
            try:
                await self.send_message(step, "running", f"正在配置负载均衡服务器 {lb['host']}（Nginx）...")
                ops = await self._connect_extra_server(lb, f"负载均衡服务器 {lb['host']}")
                try:
                    await loop.run_in_executor(None, lambda: self._setup_lb_nginx_sync(ops, log_cb))
                finally:
                    ops.close()
            except Exception as e:
                await self.send_message(step, "running", f"⚠️ 负载均衡服务器配置失败（{e}），请手动安装 Nginx 并部署 deploy/nginx-lb.conf")

    async def _connect_extra_server(self, server: dict, label: str):
        """连接额外服务器（负载均衡后端/环境服务器/LB 服务器），复用跳转链路"""
        server_cred = {
            "authType": server.get("authType", "password"),
            "password": server.get("password", ""),
            "sshKey": server.get("sshKey", ""),
        }
        if server_cred["authType"] == "password" and not server_cred["password"]:
            cred = await self.request_credential("server", f"需要{label}密码")
            if cred:
                server_cred.update(cred)
            else:
                raise SSHError(f"{label}凭据缺失")
        if server_cred["authType"] in ("ssh_key", "sshKey") and not server_cred["sshKey"]:
            cred = await self.request_credential("server", f"需要{label} SSH 密钥")
            if cred:
                server_cred.update(cred)
            else:
                raise SSHError(f"{label}凭据缺失")

        ops = SSHOps(
            host=server.get("host", ""),
            port=server.get("port", 22),
            username=server.get("username", "root"),
            credential=server_cred,
            jump_chain=self.jump_chain,
        )
        log_cb = self._sync_log_factory("install_tool")
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: ops.connect(log_cb))
        return ops

    def _setup_lb_nginx_sync(self, ops, log_cb):
        """在负载均衡服务器上安装 Nginx 并部署 upstream 配置（同步）"""
        import os
        import tempfile
        from generators.lb import build_nginx_upstream_conf

        class _AttrDict:
            """dict 配置的属性访问适配器（lb 生成函数使用 getattr）"""
            def __init__(self, d):
                self.__dict__.update(d)

        project_name = self.config.get("projectName", "app")
        conf_content = build_nginx_upstream_conf(_AttrDict(self.config))

        # 安装 Nginx（幂等）
        ops.exec_command(
            "command -v nginx >/dev/null 2>&1 && echo 'Nginx 已安装' || "
            "{ (apt-get update -qq && apt-get install -y nginx) || yum install -y nginx; }",
            log_callback=log_cb, timeout=600)

        # 上传 upstream 配置并 reload
        fd, tmp_path = tempfile.mkstemp(suffix=".conf", prefix="nginx-lb-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(conf_content)
            remote_conf = f"/etc/nginx/conf.d/{project_name}-lb.conf"
            ops.upload_file(tmp_path, remote_conf, log_callback=log_cb)
        finally:
            os.unlink(tmp_path)

        ops.exec_command(
            f"nginx -t && (nginx -s reload 2>/dev/null || systemctl restart nginx) && "
            f"echo 'Nginx 负载均衡配置已生效: {remote_conf}'",
            log_callback=log_cb, timeout=120)

    async def _step_configure_pipeline(self) -> dict:
        """Step 7: 配置流水线（创建 Job、设置凭据、配置 Webhook）"""
        step = "configure_pipeline"
        tool = self.config.get("tool", "jenkins")
        tool_deploy = self.config.get("toolDeploy", "dedicated")

        try:
            # 已部署工具：通过 HTTP API 连接现有 Jenkins / 复用现有 Runner
            if tool_deploy == "existing" and tool == "jenkins":
                return await self._configure_existing_jenkins()

            if tool_deploy == "existing" and tool == "runner":
                await self.send_message(step, "running", "复用已注册的 Runner，校验流水线配置...")
                await self.send_message(
                    step, "success",
                    "已复用现有 Runner，配置已推送到仓库，流水线自动生效"
                )
                return {"step": step, "status": "success", "message": "复用现有 Runner"}

            if tool_deploy in ("dedicated", "target") and tool == "jenkins":
                # Jenkins: 创建 Job、配置凭据
                await self.send_message(step, "running", "正在配置 Jenkins 流水线...")

                if not self.ssh_ops:
                    await self.send_message(step, "failed", "SSH 未连接")
                    return {"step": step, "status": "failed", "message": "SSH 未连接"}

                log_cb = self._sync_log_factory(step)
                loop = asyncio.get_event_loop()

                await loop.run_in_executor(
                    None,
                    lambda: self.ssh_ops.configure_jenkins_pipeline(
                        project_name=self.config.get("projectName", "app"),
                        repo_url=self.config.get("repoUrl", ""),
                        branch=self.config.get("branch", "main"),
                        git_credential=self.config.get("gitAuth"),
                        server_config=self.config.get("server", {}),
                        deploy_method=self.config.get("deployMethod", "direct"),
                        log_callback=log_cb
                    )
                )

                await self.send_message(step, "success", "Jenkins 流水线配置完成")
                return {"step": step, "status": "success", "message": "流水线已就绪"}

            elif tool == "runner":
                # Runner: 注册到 GitLab/GitHub
                await self.send_message(step, "running", "正在配置 Runner...")

                if not self.ssh_ops:
                    await self.send_message(step, "failed", "SSH 未连接")
                    return {"step": step, "status": "failed", "message": "SSH 未连接"}

                # 请求 Runner 注册 token（从 GitLab/GitHub UI 获取）
                registration_token = self.config.get("runnerToken", "")
                if not registration_token:
                    cred = await self.request_credential(
                        "runner_token",
                        "请输入 Runner 注册 Token（从 GitLab → Settings → CI/CD → Runners 获取）"
                    )
                    if cred and cred.get("token"):
                        registration_token = cred["token"]
                        self.config["runnerToken"] = registration_token

                log_cb = self._sync_log_factory(step)
                loop = asyncio.get_event_loop()

                await loop.run_in_executor(
                    None,
                    lambda: self.ssh_ops.configure_runner(
                        repo_url=self.config.get("repoUrl", ""),
                        git_credential=self.config.get("gitAuth"),
                        registration_token=registration_token,
                        log_callback=log_cb
                    )
                )

                await self.send_message(step, "success", "Runner 配置完成")
                return {"step": step, "status": "success", "message": "Runner 已就绪"}

            else:
                # 云托管工具（阿里云效、华为云、GitHub Actions、GitLab CI）
                # 配置文件已推送到仓库，流水线自动可用
                await self.send_message(step, "running", "验证流水线配置...")
                await self.send_message(step, "success", "流水线配置已推送到仓库，可直接使用")
                return {"step": step, "status": "success", "message": "流水线已就绪"}

        except SSHError as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

    async def _configure_existing_jenkins(self) -> dict:
        """通过 HTTP API 连接已部署的 Jenkins：注入凭据 + 创建/更新 Job"""
        step = "configure_pipeline"
        et = self.config.get("existingTool", {}) or {}
        url = (et.get("url") or "").strip()
        username = et.get("username") or "admin"
        auth_type = et.get("authType", "password")
        password = et.get("password") or ""
        api_token = et.get("apiToken") or ""
        skip_tls = bool(et.get("skipTlsVerify", False))

        if not url:
            await self.send_message(step, "failed", "未提供 Jenkins 地址")
            return {"step": step, "status": "failed", "message": "Jenkins 地址为空"}

        # 密码/Token 缺失时弹窗补充
        secret = api_token if auth_type == "token" else password
        if not secret:
            cred = await self.request_credential(
                "jenkins_admin",
                "请输入已部署 Jenkins 的管理员密码或 API Token"
            )
            if cred:
                if auth_type == "token":
                    api_token = cred.get("token") or cred.get("password") or ""
                else:
                    password = cred.get("password") or ""
                secret = api_token or password
            if not secret:
                await self.send_message(step, "failed", "缺少 Jenkins 管理员凭据")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        await self.send_message(step, "running", f"连接已部署的 Jenkins: {url}")

        project_name = self.config.get("projectName", "app")
        repo_url = self.config.get("repoUrl", "")
        branch = self.config.get("branch", "main")
        server_config = self.config.get("server", {}) or {}
        git_cred = self.config.get("gitAuth", {}) or {}
        log_cb = self._sync_log_factory(step)

        def _do_configure():
            from .jenkins_api import JenkinsAPI, JenkinsAPIError, build_pipeline_job_xml
            api = JenkinsAPI(
                url, username, password=password, api_token=api_token,
                verify_ssl=not skip_tls, log_callback=log_cb
            )
            ok, msg = api.test_connection()
            if not ok:
                raise JenkinsAPIError(msg)
            log_cb(msg)

            # 1. 注入部署目标服务器凭据（供 Jenkinsfile 使用）
            if server_config.get("host"):
                s_user = server_config.get("username", "root")
                if server_config.get("authType") == "ssh_key" and server_config.get("sshKey"):
                    api.inject_ssh_key_credential(
                        "deploy-server-cred", s_user, server_config["sshKey"],
                        description=f"Deploy SSH key for {project_name}"
                    )
                elif server_config.get("password"):
                    api.inject_username_password_credential(
                        "deploy-server-cred", s_user, server_config["password"],
                        description=f"Deploy password for {project_name}"
                    )

            # 2. 注入 Git 仓库凭据（私有仓库）
            git_cred_id = ""
            if git_cred.get("type") == "password" and git_cred.get("username") and git_cred.get("password"):
                git_cred_id = "git-repo-cred"
                api.inject_username_password_credential(
                    git_cred_id, git_cred["username"], git_cred["password"],
                    description=f"Git credential for {project_name}"
                )
            elif git_cred.get("type") == "ssh_key" and git_cred.get("sshKey"):
                git_cred_id = "git-repo-cred"
                api.inject_ssh_key_credential(
                    git_cred_id, "git", git_cred["sshKey"],
                    description=f"Git SSH key for {project_name}"
                )

            # 3. 创建/更新 Pipeline Job
            job_xml = build_pipeline_job_xml(project_name, repo_url, branch, git_cred_id)
            if not api.create_or_update_job(project_name, job_xml):
                raise JenkinsAPIError("创建 Jenkins Job 失败，请检查账号权限")
            return True

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, _do_configure)
            job_url = f"{url.rstrip('/')}/job/{project_name}"
            await self.send_message(
                step, "success",
                f"已在现有 Jenkins 上配置流水线: {job_url}"
            )
            return {"step": step, "status": "success", "message": job_url}
        except Exception as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

    async def _step_configure_cloud_service(self) -> dict:
        """Step 8: 配置云服务（云效/CodeArts 等云托管服务）"""
        step = "configure_cloud_service"
        tool = self.config.get("tool", "aliyun")
        
        try:
            if tool == "aliyun":
                await self.send_message(step, "running", "正在配置阿里云效流水线...")
                
                # 获取云服务凭据
                cloud_cred = self.config.get("cloudCredential", {})
                if not cloud_cred.get("accessKeyId") or not cloud_cred.get("accessKeySecret"):
                    cred = await self.request_credential("cloud", "需要阿里云 AccessKey 才能配置云效流水线")
                    if cred:
                        cloud_cred.update(cred)
                        self.config["cloudCredential"] = cloud_cred
                    else:
                        await self.send_message(step, "failed", "用户取消了凭据输入")
                        return {"step": step, "status": "failed", "message": "凭据缺失"}
                
                # 导入云效客户端
                from cloud.aliyun_devops import AliyunDevOpsClient, AliyunDevOpsError
                
                log_cb = self._sync_log_factory(step)
                loop = asyncio.get_event_loop()
                
                # 创建云效客户端并配置流水线
                def configure_aliyun():
                    client = AliyunDevOpsClient(
                        access_key_id=cloud_cred.get("accessKeyId"),
                        access_key_secret=cloud_cred.get("accessKeySecret"),
                        region_id=cloud_cred.get("regionId", "cn_hangzhou")
                    )
                    
                    # 创建项目（如果未指定组织 ID）
                    project_name = self.config.get("projectName", "app")
                    org_id = cloud_cred.get("organizationId", "")
                    
                    log_cb(f"创建云效项目: {project_name}")
                    project = client.create_project(
                        name=project_name,
                        description=f"CI/CD 自动搭建项目 - {project_name}",
                        organization_id=org_id
                    )
                    log_cb(f"项目创建成功: {project['url']}")
                    
                    # 创建代码源服务连接
                    log_cb("配置代码源连接...")
                    repo_url = self.config.get("repoUrl", "")
                    connection = client.create_service_connection(
                        project_id=project["project_id"],
                        name="代码仓库",
                        connection_type="git",
                        config={
                            "url": repo_url,
                            "authType": self.config.get("gitAuth", {}).get("type", "password"),
                            "username": self.config.get("gitAuth", {}).get("username", ""),
                            "password": self.config.get("gitAuth", {}).get("password", ""),
                        }
                    )
                    log_cb(f"代码源连接创建成功: {connection['connection_id']}")
                    
                    # 创建流水线
                    log_cb("创建流水线...")
                    pipeline = client.create_pipeline(
                        project_id=project["project_id"],
                        name=f"{project_name}-pipeline",
                        service_connection_id=connection["connection_id"],
                        repo_url=repo_url,
                        branch=self.config.get("branch", "main")
                    )
                    log_cb(f"流水线创建成功: {pipeline['url']}")
                    
                    return {
                        "project": project,
                        "connection": connection,
                        "pipeline": pipeline
                    }
                
                result = await loop.run_in_executor(None, configure_aliyun)
                
                await self.send_message(
                    step, 
                    "success", 
                    f"云效流水线配置完成！项目: {result['project']['url']}"
                )
                return {
                    "step": step, 
                    "status": "success", 
                    "message": "云效流水线已就绪",
                    "data": result
                }
            
            elif tool == "github":
                # GitHub Actions: 流水线随配置文件推送自动启用，此步骤写入 Secrets
                return await self._configure_github_secrets(step)

            elif tool == "gitlab":
                # GitLab CI: 流水线随配置文件推送自动启用，此步骤写入 CI/CD Variables
                return await self._configure_gitlab_variables(step)

            elif tool in ("huawei", "tencent"):
                # 华为云和腾讯云暂不支持 API 自动配置，提示用户手动配置
                await self.send_message(
                    step, 
                    "running", 
                    f"云托管服务 {tool} 的 API 自动配置暂未实现，配置文件已推送到仓库，请手动在控制台导入"
                )
                await self.send_message(step, "success", f"{tool} 配置文件已就绪，请手动导入")
                return {
                    "step": step, 
                    "status": "success", 
                    "message": f"{tool} 配置文件已推送到仓库"
                }
            
            else:
                await self.send_message(step, "success", "云服务配置完成")
                return {"step": step, "status": "success", "message": "云服务已就绪"}
        
        except Exception as e:
            error_msg = f"配置云服务失败: {str(e)}"
            await self.send_message(step, "failed", error_msg)
            return {"step": step, "status": "failed", "message": error_msg}

    def _collect_cloud_secrets(self) -> dict:
        """收集需要写入云平台的敏感值（Secrets/CI Variables）

        - SERVER_SSH_KEY: 部署目标服务器的 SSH 私钥（SSH 部署阶段使用）
        - SERVER_PASSWORD: 部署目标服务器密码（sshpass 模式使用）
        - DEP_REPO_TOKEN: 独立依赖仓库的访问凭据（克隆依赖仓库使用）
        - PGYER_API_KEY: 蒲公英 API Key（Android 应用分发）
        - ANDROID_KEYSTORE_BASE64: Android 签名密钥库 base64
        - FIREBASE_APP_ID / FIREBASE_CREDENTIALS: Firebase 分发凭据
        """
        server = self.config.get("server", {}) or {}
        dep_repo = self.config.get("dependencyRepo", {}) or {}
        secrets = {}
        if server.get("sshKey"):
            secrets["SERVER_SSH_KEY"] = server["sshKey"]
        if server.get("password"):
            secrets["SERVER_PASSWORD"] = server["password"]
        if dep_repo.get("url") and dep_repo.get("password"):
            secrets["DEP_REPO_TOKEN"] = dep_repo["password"]
        # Android 应用分发凭据
        dist_platform = self.config.get("distributePlatform", "pgyer")
        dist_key = self.config.get("distributeApiKey", "")
        if dist_key:
            if dist_platform == "firebase":
                secrets["FIREBASE_APP_ID"] = self.config.get("firebaseAppId", "")
                secrets["FIREBASE_CREDENTIALS"] = dist_key
            else:
                secrets["PGYER_API_KEY"] = dist_key
        keystore = self.config.get("androidKeystore", "")
        if keystore:
            # keystore 已经是 base64 编码的字符串（前端上传时编码）
            secrets["ANDROID_KEYSTORE_BASE64"] = keystore
        return secrets

    async def _configure_github_secrets(self, step: str) -> dict:
        """GitHub Actions: 将 Secrets 写入仓库（需要 PAT）

        流水线已随 .github/workflows 推送自动启用；
        未提供 Token 时跳过并提示手动配置（保持向后兼容）。
        """
        cloud_cred = self.config.get("cloudCredential", {}) or {}
        token = cloud_cred.get("token", "")
        secrets = self._collect_cloud_secrets()

        if not secrets:
            await self.send_message(step, "success", "GitHub Actions 流水线已启用，无需配置 Secrets")
            return {"step": step, "status": "success", "message": "流水线已启用"}

        secret_names = ", ".join(secrets.keys())
        if not token:
            msg = (f"GitHub Actions 流水线已启用。请在仓库 Settings → Secrets and variables → Actions "
                   f"中手动添加以下 Secrets: {secret_names}")
            await self.send_message(step, "success", msg)
            return {"step": step, "status": "success", "message": "流水线已启用，Secrets 需手动配置"}

        await self.send_message(step, "running", f"正在通过 API 写入 GitHub Secrets: {secret_names}")
        log_cb = self._sync_log_factory(step)
        loop = asyncio.get_event_loop()

        def write_secrets():
            from cloud.github_api import GitHubApiClient, GitHubApiError
            with GitHubApiClient(token) as client:
                client.verify_token()
                owner, repo = GitHubApiClient.parse_repo_owner_name(self.config.get("repoUrl", ""))
                client.get_repo(owner, repo)
                log_cb(f"仓库验证通过: {owner}/{repo}")
                written = client.set_secrets(owner, repo, secrets, log_cb)
                return owner, repo, written

        owner, repo, written = await loop.run_in_executor(None, write_secrets)
        await self.send_message(
            step, "success",
            f"GitHub Secrets 配置完成（{owner}/{repo}）: {', '.join(written) or '无'}"
        )
        return {"step": step, "status": "success", "message": f"已写入 {len(written)} 个 Secrets",
                "data": {"repo": f"{owner}/{repo}", "secrets": written}}

    async def _configure_gitlab_variables(self, step: str) -> dict:
        """GitLab CI: 将敏感值写入项目 CI/CD Variables（需要 Token）

        流水线已随 .gitlab-ci.yml 推送自动启用；
        未提供 Token 时跳过并提示手动配置（保持向后兼容）。
        """
        cloud_cred = self.config.get("cloudCredential", {}) or {}
        token = cloud_cred.get("token", "")
        base_url = cloud_cred.get("baseUrl", "") or "https://gitlab.com"
        variables = self._collect_cloud_secrets()

        if not variables:
            await self.send_message(step, "success", "GitLab 流水线已启用，无需配置 CI/CD 变量")
            return {"step": step, "status": "success", "message": "流水线已启用"}

        var_names = ", ".join(variables.keys())
        if not token:
            msg = (f"GitLab 流水线已启用。请在项目 Settings → CI/CD → Variables "
                   f"中手动添加以下变量: {var_names}")
            await self.send_message(step, "success", msg)
            return {"step": step, "status": "success", "message": "流水线已启用，变量需手动配置"}

        await self.send_message(step, "running", f"正在通过 API 写入 GitLab CI/CD 变量: {var_names}")
        log_cb = self._sync_log_factory(step)
        loop = asyncio.get_event_loop()

        def write_variables():
            from cloud.gitlab_api import GitLabApiClient, GitLabApiError
            with GitLabApiClient(token, base_url) as client:
                client.verify_token()
                project_path = GitLabApiClient.parse_project_path(self.config.get("repoUrl", ""))
                project = client.get_project(project_path)
                log_cb(f"项目验证通过: {project_path} (ID: {project['id']})")
                written = client.set_variables(project["id"], variables, log_cb)
                return project_path, written

        project_path, written = await loop.run_in_executor(None, write_variables)
        await self.send_message(
            step, "success",
            f"GitLab CI/CD 变量配置完成（{project_path}）: {', '.join(written) or '无'}"
        )
        return {"step": step, "status": "success", "message": f"已写入 {len(written)} 个变量",
                "data": {"project": project_path, "variables": written}}

    def _build_result(self, results: list, success: bool, error: str = "") -> dict:
        """构建最终结果"""
        return {
            "taskId": self.task_id,
            "success": success,
            "steps": results,
            "error": error,
            "files": self.generated_files,
            "timestamp": datetime.now().isoformat(),
        }

    def _cleanup(self):
        """清理资源"""
        if self.git_ops:
            self.git_ops.cleanup()
        if self.ssh_ops:
            self.ssh_ops.close()
        # 保留工作目录供调试，可改为删除
        # if self.work_dir and os.path.exists(self.work_dir):
        #     shutil.rmtree(self.work_dir, ignore_errors=True)
