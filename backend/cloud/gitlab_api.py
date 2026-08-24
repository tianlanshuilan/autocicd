"""
GitLab CI/CD API 客户端

提供对 GitLab 项目 CI/CD Variables 的自动化配置能力。
GitLab 流水线通过推送到仓库的 .gitlab-ci.yml 自动启用，无需 API 创建；
但流水线引用的敏感变量（SSH 部署密钥、依赖仓库 Token）需要通过
CI/CD Variables API 预先写入（避免明文写进配置文件）。

认证方式：Personal Access Token 或 Project Access Token（需要 api 权限）
"""

from typing import Optional
from urllib.parse import quote

import httpx


class GitLabApiError(Exception):
    """GitLab API 错误"""
    pass


class GitLabApiClient:
    """GitLab API 客户端（CI/CD Variables 配置）"""

    def __init__(self, token: str, base_url: str = "https://gitlab.com"):
        """
        初始化 GitLab 客户端

        Args:
            token: Personal Access Token（api 权限）
            base_url: GitLab 实例地址（自建 GitLab 可自定义，如 https://gitlab.example.com）
        """
        self.token = token
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=f"{self.base_url}/api/v4",
            headers={"PRIVATE-TOKEN": token},
            timeout=30.0,
        )

    @staticmethod
    def parse_project_path(repo_url: str) -> str:
        """从仓库 URL 解析项目路径（namespace/project）

        支持格式：
        - https://gitlab.com/group/project.git
        - git@gitlab.com:group/project.git
        - 嵌套子组: https://gitlab.com/group/subgroup/project.git
        """
        url = repo_url.strip()
        if url.endswith(".git"):
            url = url[:-4]
        if ":" in url and "//" not in url:
            # git@gitlab.com:group/project
            path = url.split(":")[-1]
        else:
            # https://gitlab.com/group/project（跳过协议和域名部分）
            after_host = url.split("/", 3)
            path = after_host[3] if len(after_host) > 3 else ""
        path = path.strip("/")
        if not path or "/" not in path:
            raise GitLabApiError(f"无法从仓库地址解析项目路径: {repo_url}")
        return path

    def verify_token(self) -> dict:
        """验证 Token 有效性，返回用户信息"""
        resp = self._client.get("/user")
        if resp.status_code == 401:
            raise GitLabApiError("GitLab Token 无效或已过期")
        if resp.status_code != 200:
            raise GitLabApiError(f"验证 Token 失败: HTTP {resp.status_code} {resp.text[:200]}")
        return resp.json()

    def get_project(self, project_path: str) -> dict:
        """按路径获取项目信息（验证项目可访问）"""
        encoded = quote(project_path, safe="")
        resp = self._client.get(f"/projects/{encoded}")
        if resp.status_code == 404:
            raise GitLabApiError(f"项目 {project_path} 不存在或 Token 无权限访问")
        if resp.status_code != 200:
            raise GitLabApiError(f"获取项目失败: HTTP {resp.status_code}")
        return resp.json()

    def set_variable(self, project_id: int, key: str, value: str,
                     masked: bool = True, protected: bool = False) -> None:
        """创建或更新项目 CI/CD 变量（存在则更新）

        Args:
            project_id: 项目 ID
            key: 变量名（如 SERVER_SSH_KEY）
            value: 变量值
            masked: 是否在日志中脱敏（注意：masked 要求值满足 GitLab 格式约束）
            protected: 是否仅在受保护分支可用
        """
        payload = {"value": value, "masked": masked, "protected": protected}
        # 先尝试创建，409/400（已存在）则改为更新
        resp = self._client.post(f"/projects/{project_id}/variables", data=payload)
        if resp.status_code == 201:
            return
        if resp.status_code in (400, 409):
            # masked 可能因值格式不满足而被拒绝，降级为非 masked 重试
            if masked:
                payload["masked"] = False
                resp = self._client.post(f"/projects/{project_id}/variables", data=payload)
                if resp.status_code == 201:
                    return
            # 变量已存在 → 更新
            resp = self._client.put(f"/projects/{project_id}/variables/{key}", data=payload)
            if resp.status_code == 200:
                return
        raise GitLabApiError(f"写入变量 {key} 失败: HTTP {resp.status_code} {resp.text[:200]}")

    def set_variables(self, project_id: int, variables: dict, log=None) -> list:
        """批量写入 CI/CD 变量（跳过空值）

        Args:
            variables: {variable_key: value} 字典
            log: 日志回调
        Returns:
            实际写入的变量名列表
        """
        log = log or (lambda msg: None)
        written = []
        for key, value in variables.items():
            if not value:
                log(f"跳过变量 {key}（值为空）")
                continue
            self.set_variable(project_id, key, value)
            log(f"CI/CD 变量已写入: {key}")
            written.append(key)
        return written

    def close(self):
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
