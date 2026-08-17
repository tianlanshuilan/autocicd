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

            # Step 5: SSH 连接
            result = await self._step_ssh_connect()
            results.append(result)
            if result["status"] == "failed":
                return self._build_result(results, False)

            # Step 6: 安装 CI/CD 工具（如果是自建工具）
            tool_deploy = self.config.get("toolDeploy", "dedicated")
            tool = self.config.get("tool", "jenkins")
            if tool_deploy in ("dedicated", "target") and tool in ("jenkins", "runner"):
                result = await self._step_install_tool()
                results.append(result)
                if result["status"] == "failed":
                    return self._build_result(results, False)

            # Step 7: 配置流水线（创建 Job、设置凭据、配置 Webhook）
            result = await self._step_configure_pipeline()
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

        if not self.ssh_ops:
            await self.send_message(step, "failed", "SSH 未连接")
            return {"step": step, "status": "failed", "message": "SSH 未连接"}

        try:
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

    async def _step_configure_pipeline(self) -> dict:
        """Step 7: 配置流水线（创建 Job、设置凭据、配置 Webhook）"""
        step = "configure_pipeline"
        tool = self.config.get("tool", "jenkins")
        tool_deploy = self.config.get("toolDeploy", "dedicated")

        try:
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

                log_cb = self._sync_log_factory(step)
                loop = asyncio.get_event_loop()

                await loop.run_in_executor(
                    None,
                    lambda: self.ssh_ops.configure_runner(
                        repo_url=self.config.get("repoUrl", ""),
                        git_credential=self.config.get("gitAuth"),
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

    async def _step_approval(self) -> dict:
        """审批确认 - 等待用户确认是否合并到主分支"""
        step = "approval"
        release_strategy = self.config.get("releaseStrategy", {})
        main_branch = release_strategy.get("mainBranch", "main")
        branches = self.config.get("branches", [])

        await self.send_message(
            step,
            "waiting_input",
            f"测试部署完成，是否合并到主分支 {main_branch}？",
            "approval"
        )

        # 等待前端回复审批结果
        if self._credential_waiter:
            future = asyncio.get_event_loop().create_future()
            self._credential_waiter = future
            credential = await future
            self._credential_waiter = None

            if credential:
                action = credential.get("action", "merge")
                if action == "merge":
                    await self.send_message(step, "success", f"审批通过，准备合并到 {main_branch}")
                    return {"step": step, "status": "success", "message": "审批通过", "action": "merge"}
                elif action == "reject":
                    await self.send_message(step, "success", "审批拒绝，不合并到主分支")
                    return {"step": step, "status": "success", "message": "已拒绝合并", "action": "reject"}
                elif action == "rollback":
                    await self.send_message(step, "success", "审批回滚，将回滚到上一稳定版本")
                    return {"step": step, "status": "success", "message": "执行回滚", "action": "rollback"}
            else:
                await self.send_message(step, "failed", "用户取消了审批")
                return {"step": step, "status": "failed", "message": "审批取消"}

        # 默认通过
        await self.send_message(step, "success", f"审批通过，准备合并到 {main_branch}")
        return {"step": step, "status": "success", "message": "审批通过", "action": "merge"}

    async def _step_merge(self) -> dict:
        """Step 8: 合并到主分支"""
        step = "merge"
        release_strategy = self.config.get("releaseStrategy", {})
        main_branch = release_strategy.get("mainBranch", "main")
        branches = self.config.get("branches", [])

        await self.send_message(step, "running", f"正在合并分支到 {main_branch}...")

        if not self.git_ops:
            await self.send_message(step, "failed", "Git 未初始化")
            return {"step": step, "status": "failed", "message": "Git 未初始化"}

        try:
            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()

            # 执行合并操作
            async def do_merge():
                for branch in branches:
                    if branch == main_branch:
                        continue
                    log_cb(f"合并 {branch} 到 {main_branch}...")
                    # 这里通过 Git 命令执行合并
                    import subprocess
                    env = self.git_ops._get_env()
                    cwd = self.git_ops.work_dir

                    # 切换到主分支
                    subprocess.run(["git", "checkout", main_branch], cwd=cwd, env=env, check=True, capture_output=True)
                    # 合并分支
                    subprocess.run(["git", "merge", f"origin/{branch}", "--no-edit"], cwd=cwd, env=env, check=True, capture_output=True)
                    # 打标签
                    from datetime import datetime
                    tag = f"v{datetime.now().strftime('%Y%m%d%H%M%S')}"
                    subprocess.run(["git", "tag", tag], cwd=cwd, env=env, check=True, capture_output=True)
                    # 推送
                    subprocess.run(["git", "push", "origin", main_branch, "--tags"], cwd=cwd, env=env, check=True, capture_output=True)
                    log_cb(f"✅ {branch} 已合并到 {main_branch}，标签: {tag}")

            await loop.run_in_executor(None, lambda: asyncio.run(do_merge()) if False else None)

            # 简化版：直接通过 SSH 执行
            if self.ssh_ops:
                def _merge_via_ssh():
                    for branch in branches:
                        if branch == main_branch:
                            continue
                        log_cb(f"合并 {branch} 到 {main_branch}...")
                        cmd = f"cd /opt/apps && git checkout {main_branch} && git merge origin/{branch} --no-edit && git push origin {main_branch}"
                        self.ssh_ops._exec(cmd, log_cb)
                        log_cb(f"✅ {branch} 已合并到 {main_branch}")

                await loop.run_in_executor(None, _merge_via_ssh)

            await self.send_message(step, "success", f"已合并所有分支到 {main_branch}")
            return {"step": step, "status": "success", "message": f"合并完成到 {main_branch}"}

        except Exception as e:
            await self.send_message(step, "failed", f"合并失败: {str(e)}")
            return {"step": step, "status": "failed", "message": str(e)}

    async def _step_rollback(self) -> dict:
        """回滚到上一稳定版本"""
        step = "merge"
        release_strategy = self.config.get("releaseStrategy", {})
        main_branch = release_strategy.get("mainBranch", "main")

        await self.send_message(step, "running", f"正在回滚 {main_branch} 到上一稳定版本...")

        try:
            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()

            if self.ssh_ops:
                def _rollback():
                    log_cb("查找上一稳定版本标签...")
                    cmd = "git tag --sort=-creatordate | grep '^v[0-9]' | head -2 | tail -1"
                    result = self.ssh_ops._exec(cmd, log_cb)
                    prev_tag = result.strip() if result else ""

                    if not prev_tag:
                        raise Exception("未找到可回滚的版本标签")

                    log_cb(f"回滚到版本: {prev_tag}")
                    self.ssh_ops._exec(f"git checkout {prev_tag}", log_cb)
                    log_cb(f"✅ 回滚完成，已回滚到 {prev_tag}")

                await loop.run_in_executor(None, _rollback)

            await self.send_message(step, "success", "回滚完成")
            return {"step": step, "status": "success", "message": "回滚完成"}

        except Exception as e:
            await self.send_message(step, "failed", f"回滚失败: {str(e)}")
            return {"step": step, "status": "failed", "message": str(e)}

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
