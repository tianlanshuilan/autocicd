"""
GitHub Actions API 客户端

提供对 GitHub 仓库 Actions Secrets 的自动化配置能力。
GitHub Actions 流水线通过推送到仓库的 .github/workflows/*.yml 自动启用，
无需 API 创建；但 workflow 中引用的 secrets（SSH 部署密钥、依赖仓库 Token）
需要通过 Secrets API 预先写入。

认证方式：Personal Access Token（需要 repo 权限，或 Fine-grained token 的
Actions:write + Contents:read 权限）
"""

import base64
from typing import Optional

import httpx
from nacl import encoding, public


class GitHubApiError(Exception):
    """GitHub API 错误"""
    pass


class GitHubApiClient:
    """GitHub API 客户端（Actions Secrets 配置）"""

    def __init__(self, token: str, api_base: str = "https://api.github.com"):
        """
        初始化 GitHub 客户端

        Args:
            token: Personal Access Token（repo 权限）
            api_base: API 基础地址（GitHub Enterprise 可自定义）
        """
        self.token = token
        self.api_base = api_base.rstrip("/")
        self._client = httpx.Client(
            base_url=self.api_base,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    @staticmethod
    def parse_repo_owner_name(repo_url: str):
        """从仓库 URL 解析 owner 和 repo 名称

        支持格式：
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
        """
        url = repo_url.strip()
        if url.endswith(".git"):
            url = url[:-4]
        if ":" in url and "//" not in url:
            # git@github.com:owner/repo
            path = url.split(":")[-1]
        else:
            # https://github.com/owner/repo
            path = "/".join(url.split("/")[-2:])
        parts = [p for p in path.split("/") if p]
        if len(parts) < 2:
            raise GitHubApiError(f"无法从仓库地址解析 owner/repo: {repo_url}")
        return parts[-2], parts[-1]

    def verify_token(self) -> dict:
        """验证 Token 有效性，返回用户信息"""
        resp = self._client.get("/user")
        if resp.status_code == 401:
            raise GitHubApiError("GitHub Token 无效或已过期")
        if resp.status_code != 200:
            raise GitHubApiError(f"验证 Token 失败: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def get_repo(self, owner: str, repo: str) -> dict:
        """获取仓库信息（验证仓库可访问）"""
        resp = self._client.get(f"/repos/{owner}/{repo}")
        if resp.status_code == 404:
            raise GitHubApiError(f"仓库 {owner}/{repo} 不存在或 Token 无权限访问")
        if resp.status_code != 200:
            raise GitHubApiError(f"获取仓库失败: HTTP {resp.status_code}")
        return resp.json()

    def _get_repo_public_key(self, owner: str, repo: str) -> dict:
        """获取仓库 Actions Secrets 公钥（用于加密 secret 值）"""
        resp = self._client.get(f"/repos/{owner}/{repo}/actions/secrets/public-key")
        if resp.status_code != 200:
            raise GitHubApiError(f"获取 Secrets 公钥失败: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    @staticmethod
    def _encrypt_secret(public_key_b64: str, secret_value: str) -> str:
        """使用 libsodium sealed box 加密 secret 值（GitHub 要求）"""
        public_key = public.PublicKey(
            public_key_b64.encode("utf-8"), encoding.Base64Encoder()
        )
        sealed_box = public.SealedBox(public_key)
        encrypted = sealed_box.encrypt(secret_value.encode("utf-8"))
        return base64.b64encode(encrypted).decode("utf-8")

    def set_secret(self, owner: str, repo: str, name: str, value: str) -> None:
        """创建或更新仓库 Actions Secret

        Args:
            owner: 仓库 owner
            repo: 仓库名
            name: Secret 名称（如 SERVER_SSH_KEY）
            value: Secret 值
        """
        key_info = self._get_repo_public_key(owner, repo)
        encrypted_value = self._encrypt_secret(key_info["key"], value)
        resp = self._client.put(
            f"/repos/{owner}/{repo}/actions/secrets/{name}",
            json={"encrypted_value": encrypted_value, "key_id": key_info["key_id"]},
        )
        # 201 = 创建成功，204 = 更新成功
        if resp.status_code not in (201, 204):
            raise GitHubApiError(f"写入 Secret {name} 失败: HTTP {resp.status_code} {resp.text[:200]}")

    def set_secrets(self, owner: str, repo: str, secrets: dict, log=None) -> list:
        """批量写入 Secrets（跳过空值）

        Args:
            secrets: {secret_name: value} 字典
            log: 日志回调
        Returns:
            实际写入的 secret 名称列表
        """
        log = log or (lambda msg: None)
        written = []
        for name, value in secrets.items():
            if not value:
                log(f"跳过 Secret {name}（值为空）")
                continue
            self.set_secret(owner, repo, name, value)
            log(f"Secret 已写入: {name}")
            written.append(name)
        return written

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
