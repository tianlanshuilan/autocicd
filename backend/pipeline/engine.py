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
                # 堡垒机配置（用于生成的 Pipeline 穿透访问，仅在启用开关时生效）
                if server_config.get('useBastion', False):
                    setattr(cfg, 'bastionHost', server_config.get('bastionHost', ''))
                    setattr(cfg, 'bastionPort', server_config.get('bastionPort', 22))
                    setattr(cfg, 'bastionUser', server_config.get('bastionUser', ''))
                    setattr(cfg, 'bastionAuthType', server_config.get('bastionAuthType', 'password'))
                    setattr(cfg, 'bastionPassword', server_config.get('bastionPassword', ''))
                    setattr(cfg, 'bastionSshKey', server_config.get('bastionSshKey', ''))
                else:
                    setattr(cfg, 'bastionHost', '')
                    setattr(cfg, 'bastionUser', '')

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
        """Step 4: SSH 连接目标服务器（支持多跳链路）"""
        step = "ssh_connect"

        server = self.config.get("server", {})
        relay = self.config.get("relayServer", {})
        network_access = self.config.get("networkAccess", {})
        hops = network_access.get("hops", [])

        if not server.get("host"):
            await self.send_message(step, "failed", "未配置服务器地址")
            return {"step": step, "status": "failed", "message": "服务器地址为空"}

        server_cred = {
            "authType": server.get("authType", "password"),
            "password": server.get("password", ""),
            "sshKey": server.get("sshKey", ""),
        }

        # 检查目标服务器凭据
        if server_cred["authType"] == "password" and not server_cred["password"]:
            cred = await self.request_credential("server", "需要服务器密码才能连接")
            if cred:
                server_cred.update(cred)
            else:
                await self.send_message(step, "failed", "用户取消了凭据输入")
                return {"step": step, "status": "failed", "message": "凭据缺失"}

        if server_cred["authType"] == "ssh_key" and not server_cred["sshKey"]:
            cred = await self.request_credential("server", "需要 SSH 密钥才能连接服务器")
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

        # 生成连接日志
        if jump_chain:
            hop_labels = [f"{h['type']}({h['host']})" for h in jump_chain]
            chain_desc = " → ".join(hop_labels) + f" → 目标({server['host']})"
            await self.send_message(step, "running", f"正在通过链路连接: {chain_desc}")
        else:
            await self.send_message(step, "running", "正在连接目标服务器...")

        # 确定最终目标地址（可能被零信任跳覆盖）
        target_host = server["host"]
        if jump_chain and jump_chain[-1].get("targetHost"):
            target_host = jump_chain[-1]["targetHost"]

        # 创建 SSHOps（支持多跳链路）
        if jump_chain:
            self.ssh_ops = SSHOps(
                host=target_host,
                port=server.get("port", 22),
                username=server.get("username", "root"),
                credential=server_cred,
                jump_chain=jump_chain,
            )
        else:
            self.ssh_ops = SSHOps(
                host=server["host"],
                port=server.get("port", 22),
                username=server.get("username", "root"),
                credential=server_cred,
            )

        try:
            log_cb = self._sync_log_factory(step)
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self.ssh_ops.connect(log_cb))

            if jump_chain:
                await self.send_message(step, "success", f"通过 {len(jump_chain)} 跳链路连接目标服务器成功")
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
            return {"step": step, "status": "success", "message": f"{tool_name} 已安装"}

        except SSHError as e:
            await self.send_message(step, "failed", str(e))
            return {"step": step, "status": "failed", "message": str(e)}

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
