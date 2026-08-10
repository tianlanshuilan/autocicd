"""Git 操作模块 - 支持 HTTPS 密码认证和 SSH 密钥认证"""

import os
import subprocess
import tempfile
import shutil
from urllib.parse import urlparse, urlunparse


class GitOps:
    """Git 仓库操作"""

    def __init__(self, repo_url: str, branch: str, credential: dict | None = None):
        """
        Args:
            repo_url: 仓库 URL
            branch: 分支名
            credential: {
                "type": "password" | "ssh_key",
                "username": str,
                "password": str,
                "sshKey": str
            }
        """
        self.repo_url = repo_url
        self.branch = branch
        self.credential = credential or {}
        self.work_dir = None
        self._ssh_key_file = None

    def _get_auth_url(self) -> str:
        """将凭据注入到仓库 URL 中"""
        if self.credential.get("type") == "password":
            username = self.credential.get("username", "")
            password = self.credential.get("password", "")
            if username and password:
                parsed = urlparse(self.repo_url)
                auth_netloc = f"{username}:{password}@{parsed.hostname}"
                if parsed.port:
                    auth_netloc += f":{parsed.port}"
                return urlunparse(parsed._replace(netloc=auth_netloc))
        return self.repo_url

    def _setup_ssh_key(self) -> str | None:
        """将 SSH 密钥写入临时文件"""
        if self.credential.get("type") == "ssh_key":
            ssh_key = self.credential.get("sshKey", "")
            if ssh_key:
                fd, path = tempfile.mkstemp(prefix="git_ssh_key_")
                with os.fdopen(fd, "w") as f:
                    f.write(ssh_key)
                os.chmod(path, 0o600)
                self._ssh_key_file = path
                return path
        return None

    def _get_env(self) -> dict:
        """获取带凭据的环境变量"""
        env = os.environ.copy()
        if self._ssh_key_file:
            env["GIT_SSH_COMMAND"] = f"ssh -i {self._ssh_key_file} -o StrictHostKeyChecking=no"
        env["GIT_TERMINAL_PROMPT"] = "0"
        return env

    def clone(self, target_dir: str, log_callback=None) -> str:
        """克隆仓库到指定目录

        Returns:
            克隆后的本地路径
        """
        log = log_callback or (lambda msg: None)

        self.work_dir = os.path.join(target_dir, "repo")
        auth_url = self._get_auth_url()
        ssh_key = self._setup_ssh_key()

        log(f"正在克隆仓库: {self.repo_url}")

        # 多分支时克隆所有分支
        if self.branch == "--all":
            log("克隆所有分支...")
            cmd = ["git", "clone", auth_url, self.work_dir]
        else:
            log(f"分支: {self.branch}")
            cmd = ["git", "clone", "--branch", self.branch, "--single-branch", auth_url, self.work_dir]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                env=self._get_env(),
                timeout=300
            )
            if result.returncode != 0:
                error_msg = result.stderr.strip()
                log(f"克隆失败: {error_msg}")
                raise GitError(f"Git clone 失败: {error_msg}")

            log(f"克隆成功: {self.work_dir}")
            return self.work_dir

        except subprocess.TimeoutExpired:
            raise GitError("Git clone 超时（超过 5 分钟）")
        except FileNotFoundError:
            raise GitError("未找到 git 命令，请确认已安装 Git")

    def copy_files_to_repo(self, generated_files: list[dict], log_callback=None):
        """将生成的配置文件复制到仓库目录"""
        log = log_callback or (lambda msg: None)

        if not self.work_dir or not os.path.exists(self.work_dir):
            raise GitError("仓库尚未克隆")

        for f in generated_files:
            file_path = os.path.join(self.work_dir, f["name"])
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as fp:
                fp.write(f["content"])
            log(f"已写入: {f['name']}")

    def commit_and_push(self, project_name: str, log_callback=None) -> bool:
        """提交并推送配置文件到远程仓库"""
        log = log_callback or (lambda msg: None)

        if not self.work_dir or not os.path.exists(self.work_dir):
            raise GitError("仓库尚未克隆")

        env = self._get_env()

        # git add
        log("添加配置文件到暂存区...")
        subprocess.run(["git", "add", "-A"], cwd=self.work_dir, env=env, check=True)

        # git commit
        commit_msg = f"chore: add CI/CD pipeline config for {project_name}"
        log(f"提交: {commit_msg}")
        subprocess.run(
            ["git", "commit", "-m", commit_msg],
            cwd=self.work_dir, env=env, check=True
        )

        # git push
        auth_url = self._get_auth_url()
        log("推送到远程仓库...")
        result = subprocess.run(
            ["git", "push", "origin", self.branch],
            cwd=self.work_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode != 0:
            # 尝试设置 remote URL 带认证再推
            subprocess.run(
                ["git", "remote", "set-url", "origin", auth_url],
                cwd=self.work_dir, env=env, check=True
            )
            result = subprocess.run(
                ["git", "push", "origin", self.branch],
                cwd=self.work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=120
            )
            if result.returncode != 0:
                raise GitError(f"Git push 失败: {result.stderr.strip()}")

        log("推送成功")
        return True

    def list_branches(self) -> list[str]:
        """获取远程仓库的所有分支名"""
        if not self.work_dir or not os.path.exists(self.work_dir):
            raise GitError("仓库尚未克隆")

        env = self._get_env()
        try:
            result = subprocess.run(
                ["git", "ls-remote", "--heads", "origin"],
                cwd=self.work_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                return []

            branches = []
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    # 格式: <sha>\trefs/heads/<branch>
                    ref = line.split("\t")[-1]
                    branch = ref.replace("refs/heads/", "")
                    branches.append(branch)
            return branches

        except Exception:
            return []

    def cleanup(self):
        """清理临时文件"""
        if self._ssh_key_file and os.path.exists(self._ssh_key_file):
            os.remove(self._ssh_key_file)
            self._ssh_key_file = None
        if self.work_dir and os.path.exists(self.work_dir):
            shutil.rmtree(self.work_dir, ignore_errors=True)
            self.work_dir = None

    def __del__(self):
        self.cleanup()


class GitError(Exception):
    """Git 操作异常"""
    pass
