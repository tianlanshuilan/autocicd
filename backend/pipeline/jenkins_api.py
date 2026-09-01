"""Jenkins HTTP API 客户端 — 用于连接已部署的 Jenkins 实例

在 toolDeploy='existing' 模式下，平台不安装 Jenkins，而是通过 HTTP REST API
连接到用户已运行的 Jenkins，完成：
  1. 连通性/认证校验
  2. 注入部署目标服务器凭据（SSH 私钥 或 用户名/密码）
  3. 创建/更新 Pipeline Job（从仓库 SCM 读取 Jenkinsfile）

仅使用标准库 urllib，避免额外依赖。
"""

import base64
import json
import urllib.request
import urllib.parse
import urllib.error


class JenkinsAPIError(Exception):
    """Jenkins API 操作异常"""


class JenkinsAPI:
    """已部署 Jenkins 实例的 HTTP API 封装"""

    def __init__(self, base_url: str, username: str, password: str = "",
                 api_token: str = "", verify_ssl: bool = True, log_callback=None):
        self.base_url = (base_url or "").rstrip("/")
        self.username = username or "admin"
        # API Token 优先，其次登录密码
        self.secret = api_token or password or ""
        # 默认校验 TLS 证书；仅当调用方显式传入 verify_ssl=False（自签名内网
        # Jenkins 且用户已确认风险）时才关闭，避免全局降级为不安全连接。
        self.verify_ssl = verify_ssl
        self.log = log_callback or (lambda msg: None)
        self._crumb = None

        if not self.base_url:
            raise JenkinsAPIError("Jenkins 地址为空")
        if not self.secret:
            raise JenkinsAPIError("Jenkins 密码或 API Token 为空")

    # ------------------------------------------------------------------ #
    # 底层请求
    # ------------------------------------------------------------------ #
    def _auth_header(self):
        token = f"{self.username}:{self.secret}".encode()
        return "Basic " + base64.b64encode(token).decode()

    def _ssl_context(self):
        if self.verify_ssl:
            return None
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        return ctx

    def _request(self, method: str, path: str, data=None, headers=None,
                 content_type=None, timeout=30):
        url = f"{self.base_url}{path}"
        hdrs = {"Authorization": self._auth_header()}
        if headers:
            hdrs.update(headers)
        if content_type:
            hdrs["Content-Type"] = content_type

        body = None
        if data is not None:
            if isinstance(data, (bytes, bytearray)):
                body = bytes(data)
            elif isinstance(data, str):
                body = data.encode("utf-8")
            else:
                body = urllib.parse.urlencode(data).encode("utf-8")
                hdrs.setdefault("Content-Type", "application/x-www-form-urlencoded")

        req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
        try:
            resp = urllib.request.urlopen(req, timeout=timeout, context=self._ssl_context())
            return resp.status, resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as e:
            raise JenkinsAPIError(f"无法连接 Jenkins ({self.base_url}): {e.reason}")

    # ------------------------------------------------------------------ #
    # CSRF Crumb
    # ------------------------------------------------------------------ #
    def get_crumb(self):
        """获取 CSRF crumb（部分 Jenkins 关闭了 CSRF 则返回空）"""
        if self._crumb is not None:
            return self._crumb
        try:
            status, body = self._request("GET", "/crumbIssuer/api/json")
            if status == 200:
                data = json.loads(body)
                self._crumb = {data["crumbRequestField"]: data["crumb"]}
            else:
                self._crumb = {}
        except Exception:
            self._crumb = {}
        return self._crumb

    # ------------------------------------------------------------------ #
    # 连通性
    # ------------------------------------------------------------------ #
    def test_connection(self):
        """校验地址可达且认证通过，返回 (ok, message)"""
        try:
            status, body = self._request("GET", "/api/json?tree=mode,nodeName", timeout=15)
        except JenkinsAPIError as e:
            return False, str(e)
        if status == 200:
            return True, "Jenkins 连接成功，认证通过"
        if status in (401, 403):
            return False, f"Jenkins 认证失败 (HTTP {status})，请检查账号/密码或 API Token"
        return False, f"Jenkins 返回异常状态 HTTP {status}"

    # ------------------------------------------------------------------ #
    # 凭据注入
    # ------------------------------------------------------------------ #
    def upsert_credential(self, cred_xml: str, cred_id: str, scope: str = "system"):
        """创建或更新全局凭据（scope=system → 系统级；user → 当前用户）

        通过 /credentials/store/<scope>/domain/_/ 接口，存在则更新，不存在则创建。
        """
        if scope == "system":
            base = "/credentials/store/system/domain/_"
        else:
            base = "/credentials/store/system/domain/_"

        # 先查询是否存在
        check_path = f"{base}/credential/{urllib.parse.quote(cred_id)}/api/json"
        status, _ = self._request("GET", check_path)
        exists = (status == 200)

        crumb = self.get_crumb()
        encoded = urllib.parse.quote(cred_xml, safe="")
        if exists:
            path = f"{base}/credential/{urllib.parse.quote(cred_id)}/config.xml"
            method = "POST"
            # 更新使用 config.xml + POST
            status, body = self._request(
                method, path, data=cred_xml,
                headers=crumb, content_type="application/xml"
            )
            action = "更新"
        else:
            path = f"{base}/createCredentials"
            form = {"credentials": cred_xml}
            status, body = self._request(
                "POST", path, data=form, headers=crumb
            )
            action = "创建"

        if status in (200, 201, 302):
            self.log(f"✅ 凭据 '{cred_id}' {action}成功")
            return True
        self.log(f"⚠️ 凭据 '{cred_id}' {action}失败 (HTTP {status}): {body[:200]}")
        return False

    def inject_ssh_key_credential(self, cred_id: str, username: str,
                                  private_key: str, passphrase: str = "",
                                  description: str = ""):
        """注入 SSH 私钥凭据（com.cloudbees...BasicSSHUserPrivateKey）"""
        desc = description or f"Deploy SSH key for {username}"
        # 转义 XML 特殊字符
        pk_escaped = (private_key or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        pass_escaped = (passphrase or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cred_xml = f"""<com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey>
  <scope>GLOBAL</scope>
  <id>{cred_id}</id>
  <description>{desc}</description>
  <username>{username}</username>
  <passphrase>{pass_escaped}</passphrase>
  <privateKeySource class="com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey$DirectEntryPrivateKeySource">
    <privateKey>{pk_escaped}</privateKey>
  </privateKeySource>
</com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey>"""
        return self.upsert_credential(cred_xml, cred_id)

    def inject_username_password_credential(self, cred_id: str, username: str,
                                            password: str, description: str = ""):
        """注入用户名/密码凭据（UsernamePasswordCredentialsImpl）"""
        desc = description or f"Deploy password for {username}"
        pass_escaped = (password or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cred_xml = f"""<com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>
  <scope>GLOBAL</scope>
  <id>{cred_id}</id>
  <description>{desc}</description>
  <username>{username}</username>
  <password>{pass_escaped}</password>
</com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl>"""
        return self.upsert_credential(cred_xml, cred_id)

    # ------------------------------------------------------------------ #
    # Job 管理
    # ------------------------------------------------------------------ #
    def job_exists(self, project_name: str):
        status, _ = self._request("GET", f"/job/{urllib.parse.quote(project_name)}/api/json")
        return status == 200

    def create_or_update_job(self, project_name: str, job_xml: str):
        """创建或更新 Pipeline Job"""
        crumb = self.get_crumb()
        name = urllib.parse.quote(project_name)
        if self.job_exists(project_name):
            status, body = self._request(
                "POST", f"/job/{name}/config.xml",
                data=job_xml, headers=crumb, content_type="application/xml"
            )
            action = "更新"
        else:
            status, body = self._request(
                "POST", f"/createItem?name={name}",
                data=job_xml, headers=crumb, content_type="application/xml"
            )
            action = "创建"

        if status in (200, 201, 302):
            self.log(f"✅ Pipeline Job '{project_name}' {action}成功")
            return True
        self.log(f"❌ Job '{project_name}' {action}失败 (HTTP {status}): {body[:300]}")
        return False

    def build_job(self, project_name: str):
        """触发一次构建（可选）"""
        crumb = self.get_crumb()
        name = urllib.parse.quote(project_name)
        status, _ = self._request("POST", f"/job/{name}/build", headers=crumb)
        return status in (200, 201, 302)


def build_pipeline_job_xml(project_name: str, repo_url: str, branch: str,
                           git_cred_id: str = ""):
    """生成 Pipeline Job 的 config.xml（从 SCM 读取 Jenkinsfile）

    git_cred_id 非空时，为 SCM 配置 Git 凭据（私有仓库）。
    """
    repo_escaped = (repo_url or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    cred_tag = f"<credentialsId>{git_cred_id}</credentialsId>" if git_cred_id else ""
    return f"""<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>CI/CD Pipeline for {project_name} (auto-cicd)</description>
  <keepDependencies>false</keepDependencies>
  <properties>
    <org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>
      <triggers>
        <hudson.triggers.SCMTrigger>
          <spec>H/2 * * * *</spec>
          <ignorePostCommitHooks>false</ignorePostCommitHooks>
        </hudson.triggers.SCMTrigger>
      </triggers>
    </org.jenkinsci.plugins.workflow.job.properties.PipelineTriggersJobProperty>
  </properties>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsScmFlowDefinition" plugin="workflow-cps">
    <scm class="hudson.plugins.git.GitSCM" plugin="git">
      <configVersion>2</configVersion>
      <userRemoteConfigs>
        <hudson.plugins.git.UserRemoteConfig>
          <url>{repo_escaped}</url>
          {cred_tag}
        </hudson.plugins.git.UserRemoteConfig>
      </userRemoteConfigs>
      <branches>
        <hudson.plugins.git.BranchSpec>
          <name>*/{branch}</name>
        </hudson.plugins.git.BranchSpec>
      </branches>
    </scm>
    <scriptPath>Jenkinsfile</scriptPath>
    <lightweight>true</lightweight>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>"""
