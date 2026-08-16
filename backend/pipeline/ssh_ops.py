"""SSH 远程操作模块 - 支持密码和密钥认证"""

import io
import os
import sys
import time
import paramiko


def get_bundled_tools_path() -> str:
    """获取离线安装包目录路径（兼容开发和打包环境）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return os.path.join(sys._MEIPASS, 'bundled-tools')
    else:
        # 开发环境
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        return os.path.join(project_root, 'bundled-tools')


def has_bundled_tool(tool_name: str, arch: str = '') -> bool:
    """检查是否有某个工具的离线安装包"""
    tools_dir = get_bundled_tools_path()
    if arch:
        path = os.path.join(tools_dir, tool_name, arch)
    else:
        path = os.path.join(tools_dir, tool_name)
    return os.path.isdir(path) and len(os.listdir(path)) > 0


class SSHOps:
    """SSH 远程服务器操作（支持多跳链路）"""

    def __init__(self, host: str, port: int, username: str, credential: dict,
                 jump_host: str = "", jump_port: int = 22, jump_username: str = "root",
                 jump_credential: dict = None, jump_chain: list = None):
        """
        Args:
            host: 目标服务器地址
            port: 目标 SSH 端口
            username: 目标用户名
            credential: 目标服务器凭据
            jump_host: 单跳模式 - 中继服务器地址（向后兼容）
            jump_port: 单跳模式 - 中继端口
            jump_username: 单跳模式 - 中继用户名
            jump_credential: 单跳模式 - 中继凭据
            jump_chain: 多跳模式 - 有序跳转链路 [{"type", "host", "port", "username", "credential", "jumpCommand", "targetHost"}]
        """
        self.host = host
        self.port = port
        self.username = username
        self.credential = credential
        self.jump_host = jump_host
        self.jump_port = jump_port
        self.jump_username = jump_username
        self.jump_credential = jump_credential or {}
        self.jump_chain = jump_chain or []
        self.client = None
        self.jump_transports = []  # 多跳 transport 链

    def connect(self, log_callback=None) -> bool:
        """连接到远程服务器（支持多跳链路）"""
        log = log_callback or (lambda msg: None)

        self.client = paramiko.SSHClient()
        self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        try:
            connect_kwargs = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": 30,
            }

            auth_type = self.credential.get("authType", "password")

            if auth_type == "ssh_key":
                ssh_key_str = self.credential.get("sshKey", "")
                if ssh_key_str:
                    pkey = self._parse_ssh_key(ssh_key_str, log)
                    connect_kwargs["pkey"] = pkey
                    log("目标服务器使用 SSH 密钥认证")
                else:
                    raise SSHError("SSH 密钥为空")
            else:
                password = self.credential.get("password", "")
                if password:
                    connect_kwargs["password"] = password
                    log("目标服务器使用密码认证")
                else:
                    raise SSHError("密码为空")

            # 多跳链路模式
            if self.jump_chain:
                sock = self._connect_chain(self.jump_chain, log)
                connect_kwargs["sock"] = sock
                chain_desc = " → ".join([h.get("host", "?") for h in self.jump_chain])
                log(f"通过链路 [{chain_desc}] 跳转到目标 {self.host}")

            # 单跳兼容模式
            elif self.jump_host:
                log(f"正在连接中继服务器 {self.jump_host}:{self.jump_port}...")
                transport = self._connect_single_jump(
                    self.jump_host, self.jump_port, self.jump_username,
                    self.jump_credential, log
                )
                self.jump_transports.append(transport)
                channel = transport.open_channel(
                    "direct-tcpip",
                    (self.host, self.port),
                    ("127.0.0.1", 0)
                )
                connect_kwargs["sock"] = channel
                log(f"通过中继 {self.jump_host} 跳转到目标 {self.host}")

            self.client.connect(**connect_kwargs)
            log("SSH 连接成功")
            return True

        except paramiko.AuthenticationException:
            raise SSHError("SSH 认证失败，请检查用户名、密码或密钥")
        except paramiko.SSHException as e:
            raise SSHError(f"SSH 连接错误: {str(e)}")
        except TimeoutError:
            raise SSHError(f"连接超时，无法到达 {self.host}:{self.port}")
        except Exception as e:
            raise SSHError(f"连接失败: {str(e)}")

    def _connect_chain(self, chain: list, log_callback) -> paramiko.Channel:
        """连接多跳链路，返回最终的 socket channel"""
        log = log_callback
        type_labels = {"relay": "中继服务器", "bastion": "堡垒机", "zero_trust": "零信任网关"}

        current_host = "127.0.0.1"
        current_port = 0
        prev_transport = None

        for i, hop in enumerate(chain):
            hop_type = hop.get("type", "relay")
            hop_host = hop.get("host", "")
            hop_port = hop.get("port", 22)
            hop_username = hop.get("username", "root")
            hop_cred = hop.get("credential", {})
            label = type_labels.get(hop_type, hop_type)

            log(f"第{i+1}跳: 连接{label} {hop_host}:{hop_port}...")

            if i == 0:
                # 第一跳：直接连接
                transport = self._connect_single_jump(hop_host, hop_port, hop_username, hop_cred, log)
                self.jump_transports.append(transport)
            else:
                # 后续跳：通过前一跳的 transport 连接
                jump_command = hop.get("jumpCommand", "")
                if hop_type == "bastion" and jump_command:
                    # 堡垒机模式：执行跳转命令
                    log(f"通过堡垒机执行跳转命令: {jump_command}")
                    transport = self._connect_via_command(
                        prev_transport, jump_command, log
                    )
                    self.jump_transports.append(transport)
                else:
                    # 中继/零信任模式：通过 direct-tcpip 转发
                    target_host = hop.get("targetHost", "") or hop_host
                    channel = prev_transport.open_channel(
                        "direct-tcpip",
                        (target_host, hop_port),
                        ("127.0.0.1", 0)
                    )
                    transport = self._connect_via_channel(
                        channel, hop_username, hop_cred, log
                    )
                    self.jump_transports.append(transport)

            log(f"第{i+1}跳 {label} {hop_host} 连接成功")
            prev_transport = transport

        # 最后一跳连接到目标服务器
        last_hop = chain[-1]
        target_host = last_hop.get("targetHost", "") or self.host
        target_port = self.port

        channel = prev_transport.open_channel(
            "direct-tcpip",
            (target_host, target_port),
            ("127.0.0.1", 0)
        )
        return channel

    def _connect_single_jump(self, host, port, username, credential, log) -> paramiko.Transport:
        """连接单个跳板服务器，返回 Transport"""
        jump_client = paramiko.SSHClient()
        jump_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        jump_kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": 30,
        }

        auth = credential.get("authType", "password")
        if auth == "ssh_key":
            pkey = self._parse_ssh_key(credential.get("sshKey", ""), log)
            jump_kwargs["pkey"] = pkey
            log("使用 SSH 密钥认证")
        else:
            jump_kwargs["password"] = credential.get("password", "")
            log("使用密码认证")

        jump_client.connect(**jump_kwargs)
        return jump_client.get_transport()

    def _connect_via_channel(self, channel, username, credential, log) -> paramiko.Transport:
        """通过已有 channel 建立新的 SSH Transport"""
        transport = paramiko.Transport(channel)
        transport.connect()
        auth = credential.get("authType", "password")
        if auth == "ssh_key":
            pkey = self._parse_ssh_key(credential.get("sshKey", ""), log)
            transport.auth_publickey(username, pkey)
        else:
            transport.auth_password(username, credential.get("password", ""))
        return transport

    def _connect_via_command(self, transport, command, log) -> paramiko.Transport:
        """通过在已有连接上执行命令建立新连接（堡垒机跳转）"""
        channel = transport.open_session()
        channel.exec_command(command)
        # 等待命令执行完成并建立新 transport
        time.sleep(2)
        new_transport = paramiko.Transport(channel)
        new_transport.connect()
        return new_transport

    def _parse_ssh_key(self, key_str: str, log_callback=None):
        """解析 SSH 密钥字符串为 paramiko key 对象"""
        log = log_callback or (lambda msg: None)
        key_file = io.StringIO(key_str)
        try:
            pkey = paramiko.RSAKey.from_private_key(key_file)
        except Exception:
            key_file.seek(0)
            try:
                pkey = paramiko.Ed25519Key.from_private_key(key_file)
            except Exception:
                key_file.seek(0)
                pkey = paramiko.ECDSAKey.from_private_key(key_file)
        return pkey

    def exec_command(self, command: str, log_callback=None, timeout: int = 600) -> str:
        """执行远程命令并实时返回输出"""
        log = log_callback or (lambda msg: None)

        if not self.client:
            raise SSHError("SSH 未连接")

        log(f"$ {command}")

        try:
            stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
            output = stdout.read().decode("utf-8", errors="replace").strip()
            error = stderr.read().decode("utf-8", errors="replace").strip()
            exit_code = stdout.channel.recv_exit_status()

            if output:
                for line in output.split("\n"):
                    log(f"  {line}")
            if error and exit_code != 0:
                for line in error.split("\n"):
                    log(f"  [ERR] {line}")

            if exit_code != 0:
                raise SSHError(f"命令执行失败 (exit {exit_code}): {error[:200]}")

            return output

        except TimeoutError:
            raise SSHError(f"命令执行超时 ({timeout}s)")
        except SSHError:
            raise
        except Exception as e:
            raise SSHError(f"命令执行异常: {str(e)}")

    # ==================== 离线安装包（SCP 上传） ====================

    def upload_file(self, local_path: str, remote_path: str, log_callback=None):
        """通过 SCP 上传文件到远程服务器"""
        log = log_callback or (lambda msg: None)
        
        if not self.client:
            raise SSHError("SSH 未连接")
        
        if not os.path.exists(local_path):
            raise SSHError(f"本地文件不存在: {local_path}")
        
        file_size = os.path.getsize(local_path)
        file_name = os.path.basename(local_path)
        log(f"上传文件: {file_name} ({file_size / 1024 / 1024:.1f} MB) -> {remote_path}")
        
        try:
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            log(f"上传完成: {file_name}")
            return True
        except Exception as e:
            raise SSHError(f"文件上传失败: {str(e)}")

    def upload_bundled_tool(self, tool_name: str, arch: str, remote_dir: str, 
                             log_callback=None, filename_filter: str = None) -> bool:
        """上传离线安装包到远程服务器
        
        Args:
            tool_name: 工具名称 (jenkins, runner, jdk, docker)
            arch: 架构 (amd64, arm64, arm, x86_64, aarch64)
            remote_dir: 远程目标目录
            log_callback: 日志回调
            filename_filter: 文件名过滤，只上传匹配的文件（用于 JDK 多版本选择）
            
        Returns:
            bool: 是否成功上传
        """
        log = log_callback or (lambda msg: None)
        tools_dir = get_bundled_tools_path()
        
        # 架构映射
        arch_dir = arch
        if arch in ('x86_64', 'amd64'):
            arch_dir = 'amd64' if tool_name in ('runner', 'docker') else 'x86_64'
        elif arch in ('aarch64', 'arm64'):
            arch_dir = 'arm64' if tool_name in ('runner', 'docker') else 'aarch64'
        
        # 查找本地文件
        if tool_name in ('runner', 'docker', 'jdk'):
            local_dir = os.path.join(tools_dir, tool_name, arch_dir)
        else:
            local_dir = os.path.join(tools_dir, tool_name)
        
        if not os.path.isdir(local_dir):
            log(f"离线包不存在: {local_dir}")
            return False
        
        # 确保远程目录存在
        self.exec_command(f"mkdir -p {remote_dir}", log)
        
        # 上传目录中的文件
        uploaded = False
        for filename in os.listdir(local_dir):
            # 如果指定了文件名过滤器，只上传匹配的文件
            if filename_filter and filename != filename_filter:
                continue
            local_path = os.path.join(local_dir, filename)
            if os.path.isfile(local_path):
                remote_path = f"{remote_dir}/{filename}"
                try:
                    self.upload_file(local_path, remote_path, log)
                    uploaded = True
                except Exception as e:
                    log(f"上传 {filename} 失败: {e}")
        
        return uploaded

    def _install_jenkins_bundled(self, sys_info: dict, log, jdk_version: str = '17') -> bool:
        """使用离线包安装 Jenkins（兜底方案）
        
        Args:
            sys_info: 系统信息字典
            log: 日志回调
            jdk_version: JDK 版本 ('8' 或 '17')
        """
        arch = sys_info['arch']
        log(f"尝试使用离线安装包安装 Jenkins（JDK {jdk_version}）...")
        
        if not has_bundled_tool('jenkins'):
            log("离线安装包不可用")
            return False
        
        # 上传 Jenkins WAR 包
        if not self.upload_bundled_tool('jenkins', arch, '/opt', log):
            return False
        
        # 上传 JDK（如果没有 Java 环境）
        java_check = self.exec_command("java -version 2>&1 || echo 'not_found'")
        if 'not_found' in java_check:
            log(f"服务器上无 Java 环境，使用离线 JDK {jdk_version} 安装...")
            # 根据版本选择对应的文件
            jdk_file = 'openjdk8.tar.gz' if jdk_version == '8' else 'openjdk.tar.gz'
            if not self.upload_bundled_tool('jdk', arch, '/opt', log, filename_filter=jdk_file):
                log("JDK 离线包上传失败")
                return False
            
            # 根据版本选择解压不同的包
            jdk_dir_pattern = 'jdk8u*' if jdk_version == '8' else 'jdk-17*'
            
            self.exec_command(f"mkdir -p /opt/java && tar -xzf /opt/{jdk_file} -C /opt/java", log)
            self.exec_command(f"ln -sf /opt/java/{jdk_dir_pattern}/bin/java /usr/local/bin/java", log)
            self.exec_command(f"ln -sf /opt/java/{jdk_dir_pattern}/bin/javac /usr/local/bin/javac", log)
            log(f"JDK {jdk_version} 离线安装完成")
        
        # 创建 Jenkins 服务
        self.exec_command("""mkdir -p /var/lib/jenkins
cat > /etc/systemd/system/jenkins.service << 'EOF'
[Unit]
Description=Jenkins Continuous Integration Server
After=network.target

[Service]
Type=simple
User=root
Environment=JENKINS_HOME=/var/lib/jenkins
ExecStart=/usr/bin/java -jar /opt/jenkins.war --httpPort=8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable jenkins
systemctl start jenkins""", log)
        
        log("Jenkins 离线安装完成！")
        return True

    def _install_runner_bundled(self, sys_info: dict, log) -> bool:
        """使用离线包安装 GitLab Runner（兜底方案）"""
        arch = sys_info['arch']
        log("尝试使用离线安装包安装 GitLab Runner...")
        
        if not has_bundled_tool('runner'):
            log("离线安装包不可用")
            return False
        
        # 上传 Runner 二进制文件
        if not self.upload_bundled_tool('runner', arch, '/usr/local/bin', log):
            return False
        
        # 设置权限
        self.exec_command("chmod +x /usr/local/bin/gitlab-runner", log)
        
        # 创建用户
        self.exec_command("useradd --comment 'GitLab Runner' --create-home gitlab-runner 2>/dev/null || true", log)
        
        # 创建 systemd 服务
        self.exec_command("""cat > /etc/systemd/system/gitlab-runner.service << 'EOF'
[Unit]
Description=GitLab Runner
After=network.target

[Service]
Type=simple
User=gitlab-runner
ExecStart=/usr/local/bin/gitlab-runner run --working-directory /home/gitlab-runner
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
mkdir -p /home/gitlab-runner
chown gitlab-runner:gitlab-runner /home/gitlab-runner
systemctl daemon-reload
systemctl enable gitlab-runner
systemctl start gitlab-runner""", log)
        
        log("GitLab Runner 离线安装完成！")
        return True

    def _install_docker_bundled(self, sys_info: dict, log) -> bool:
        """使用离线包安装 Docker（兜底方案）"""
        arch = sys_info['arch']
        log("尝试使用离线安装包安装 Docker...")
        
        if not has_bundled_tool('docker'):
            log("离线安装包不可用")
            return False
        
        # 上传 Docker 静态二进制包
        if not self.upload_bundled_tool('docker', arch, '/tmp', log):
            return False
        
        # 解压并安装
        self.exec_command("""cd /tmp
tar -xzf docker.tgz
# 复制二进制文件
for f in docker/docker/*; do
    cp "$f" /usr/local/bin/ 2>/dev/null || cp "$f" /usr/bin/ 2>/dev/null
done
chmod +x /usr/local/bin/docker* 2>/dev/null || chmod +x /usr/bin/docker* 2>/dev/null
# 清理
rm -rf /tmp/docker /tmp/docker.tgz""", log)
        
        # 创建 systemd 服务
        self.exec_command("""cat > /etc/systemd/system/docker.service << 'EOF'
[Unit]
Description=Docker Application Container Engine
After=network-online.target firewalld.service
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/dockerd
ExecReload=/bin/kill -s HUP $MAINPID
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TimeoutStartSec=0
Delegate=yes
KillMode=process
Restart=on-failure
StartLimitBurst=3
StartLimitInterval=60s

[Install]
WantedBy=multi-user.target
EOF

# 创建 containerd 服务
cat > /etc/systemd/system/containerd.service << 'EOF'
[Unit]
Description=containerd container runtime
After=network.target local-fs.target

[Service]
ExecStart=/usr/local/bin/containerd
Restart=always
Delegate=yes
KillMode=process
LimitNPROC=infinity
LimitNOFILE=1048576
LimitCORE=infinity
TasksMax=infinity

[Install]
WantedBy=multi-user.target
EOF

mkdir -p /etc/docker
systemctl daemon-reload
systemctl enable containerd
systemctl start containerd
systemctl enable docker
systemctl start docker""", log)
        
        # 验证安装
        docker_ver = self.exec_command("docker --version 2>/dev/null || echo 'failed'")
        if 'failed' not in docker_ver:
            log(f"Docker 离线安装完成！{docker_ver.strip()}")
            return True
        else:
            log("Docker 离线安装失败")
            return False

    def detect_system_info(self, log_callback=None) -> dict:
        """检测服务器系统信息（OS、架构、镜像源）
        
        Returns:
            dict: {
                'os': 'debian' | 'ubuntu' | 'centos' | 'rhel' | 'kylin' | 'uos' | 'unknown',
                'os_family': 'debian' | 'redhat' | 'unknown',
                'arch': 'x86_64' | 'aarch64' | 'armv7l' | 'unknown',
                'is_china_os': bool,  # 是否国产 OS
                'is_arm': bool,
                'codename': str,  # 系统代号 (如 focal, bullseye)
            }
        """
        log = log_callback or (lambda msg: None)
        
        result = {
            'os': 'unknown',
            'os_family': 'unknown',
            'arch': 'unknown',
            'is_china_os': False,
            'is_arm': False,
            'codename': '',
        }
        
        # 检测架构
        log("检测系统架构...")
        arch_output = self.exec_command("uname -m 2>/dev/null || echo 'unknown'")
        arch = arch_output.strip().lower()
        
        if arch in ('x86_64', 'amd64'):
            result['arch'] = 'x86_64'
        elif arch in ('aarch64', 'arm64'):
            result['arch'] = 'aarch64'
            result['is_arm'] = True
        elif arch.startswith('arm'):
            result['arch'] = 'armv7l'
            result['is_arm'] = True
        else:
            result['arch'] = arch
        
        log(f"架构: {result['arch']}")
        
        # 检测操作系统
        log("检测操作系统...")
        os_release = self.exec_command("cat /etc/os-release 2>/dev/null || cat /etc/lsb-release 2>/dev/null || echo 'unknown'")
        os_lower = os_release.lower()
        
        # 国产 OS 检测
        if 'kylin' in os_lower or 'neokylin' in os_lower:
            result['os'] = 'kylin'
            result['is_china_os'] = True
            result['os_family'] = 'redhat'  # 麒麟基于 CentOS
            log("检测到国产操作系统: 麒麟 (Kylin)")
        elif 'uos' in os_lower or 'uniontech' in os_lower:
            result['os'] = 'uos'
            result['is_china_os'] = True
            result['os_family'] = 'debian'  # 统信 UOS 基于 Debian
            log("检测到国产操作系统: 统信 UOS")
        elif 'debian' in os_lower:
            result['os'] = 'debian'
            result['os_family'] = 'debian'
        elif 'ubuntu' in os_lower:
            result['os'] = 'ubuntu'
            result['os_family'] = 'debian'
        elif 'centos' in os_lower:
            result['os'] = 'centos'
            result['os_family'] = 'redhat'
        elif 'rhel' in os_lower or 'red hat' in os_lower:
            result['os'] = 'rhel'
            result['os_family'] = 'redhat'
        elif 'fedora' in os_lower:
            result['os'] = 'fedora'
            result['os_family'] = 'redhat'
        elif 'openeuler' in os_lower:
            result['os'] = 'openeuler'
            result['os_family'] = 'redhat'
            result['is_china_os'] = True
            log("检测到国产操作系统: openEuler")
        else:
            # 尝试通过包管理器判断
            has_apt = self.exec_command("which apt-get 2>/dev/null && echo 'yes' || echo 'no'")
            has_yum = self.exec_command("which yum 2>/dev/null && echo 'yes' || echo 'no'")
            if 'yes' in has_apt:
                result['os_family'] = 'debian'
                result['os'] = 'debian'
            elif 'yes' in has_yum:
                result['os_family'] = 'redhat'
                result['os'] = 'centos'
        
        # 获取系统代号
        codename = self.exec_command(". /etc/os-release 2>/dev/null && echo $VERSION_CODENAME || echo ''")
        result['codename'] = codename.strip()
        
        log(f"操作系统: {result['os']} ({result['os_family']} family)")
        
        return result

    def install_ci_tool(self, tool: str, tool_deploy: str, use_china_mirror: bool = False, log_callback=None):
        """安装 CI/CD 工具

        Args:
            tool: 工具类型 (jenkins, runner)
            tool_deploy: 部署位置 (dedicated, target)
            use_china_mirror: 是否使用国内镜像源
            log_callback: 日志回调
        """
        log = log_callback or (lambda msg: None)

        # 检测系统信息
        sys_info = self.detect_system_info(log)
        
        # 国产 OS 或国内环境自动使用国内镜像
        if sys_info['is_china_os']:
            use_china_mirror = True
            log("国产操作系统，自动启用国内镜像源")

        if tool == "jenkins":
            self._install_jenkins(sys_info, use_china_mirror, log)
        elif tool == "runner":
            self._install_runner(sys_info, use_china_mirror, log)
        else:
            log(f"不支持的工具类型: {tool}")

    def _install_jenkins(self, sys_info: dict, use_china_mirror: bool, log):
        """安装 Jenkins（支持多架构、国产 OS、国内镜像）
        
        Args:
            sys_info: 系统信息字典
            use_china_mirror: 是否使用国内镜像
            log: 日志回调
        """
        log("安装 Jenkins...")
        arch = sys_info['arch']
        os_family = sys_info['os_family']
        is_arm = sys_info['is_arm']

        # 检查是否已安装
        check = self.exec_command("which jenkins 2>/dev/null || echo 'not_found'")
        if 'not_found' not in check:
            log("Jenkins 已安装，跳过")
            return

        # 安装 JDK (Jenkins 需要)
        log("检查 Java 环境...")
        java_check = self.exec_command("java -version 2>&1 || echo 'not_found'")
        if 'not_found' in java_check:
            log("安装 OpenJDK 17...")
            if os_family == 'debian':
                self.exec_command("apt-get update -qq && apt-get install -y -qq openjdk-17-jdk", log)
            elif os_family == 'redhat':
                self.exec_command("yum install -y java-17-openjdk-devel", log)
            else:
                # 通用安装 - 下载 OpenJDK 二进制包
                log("使用通用方式安装 OpenJDK...")
                jdk_arch = 'aarch64' if is_arm else 'x64'
                jdk_url = f"https://download.java.net/java/GA/jdk17.0.2/dfd4a8d0985749f896bed50d7138ee7f/8/GPL/openjdk-17.0.2_linux-{jdk_arch}_bin.tar.gz"
                if use_china_mirror:
                    # 使用清华镜像
                    jdk_url = f"https://mirrors.tuna.tsinghua.edu.cn/Adoptium/17/jdk/{jdk_arch}/linux/OpenJDK17U-jdk_{jdk_arch.replace('x64', 'x64').replace('aarch64', 'aarch64')}_linux_hotspot_17.0.2_8.tar.gz"
                self.exec_command(f"curl -fsSL '{jdk_url}' -o /tmp/openjdk.tar.gz", log)
                self.exec_command("mkdir -p /opt/java && tar -xzf /tmp/openjdk.tar.gz -C /opt/java", log)
                self.exec_command("ln -sf /opt/java/jdk-17*/bin/java /usr/local/bin/java", log)
                self.exec_command("ln -sf /opt/java/jdk-17*/bin/javac /usr/local/bin/javac", log)

        # Jenkins 安装方式 - 三级降级策略
        install_success = False
        
        try:
            if use_china_mirror:
                # 国内镜像安装方式
                log("使用国内镜像安装 Jenkins...")
                self._install_jenkins_china_mirror(sys_info, log)
            else:
                # 官方源安装
                log("添加 Jenkins 官方仓库...")
                if os_family == 'debian':
                    self.exec_command("curl -fsSL https://pkg.jenkins.io/debian/jenkins.io.key | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null", log)
                    self.exec_command('echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://pkg.jenkins.io/debian-stable binary/ | tee /etc/apt/sources.list.d/jenkins.list > /dev/null', log)
                    self.exec_command("apt-get update -qq && apt-get install -y -qq jenkins", log)
                elif os_family == 'redhat':
                    self.exec_command("wget -O /etc/yum.repos.d/jenkins.repo https://pkg.jenkins.io/redhat-stable/jenkins.repo", log)
                    self.exec_command("rpm --import https://pkg.jenkins.io/redhat-stable/jenkins.io.key", log)
                    self.exec_command("yum install -y jenkins", log)
                else:
                    # WAR 包通用安装
                    log("使用 WAR 包安装 Jenkins...")
                    jenkins_url = "https://get.jenkins.io/latest/jenkins.war"
                    self.exec_command(f"curl -fsSL '{jenkins_url}' -o /opt/jenkins.war", log)
                    self.exec_command("""cat > /opt/jenkins.sh << 'EOF'
#!/bin/bash
export JENKINS_HOME=/var/lib/jenkins
mkdir -p $JENKINS_HOME
java -jar /opt/jenkins.war --httpPort=8080 &
EOF
chmod +x /opt/jenkins.sh""", log)
            install_success = True
        except Exception as e:
            log(f"在线安装失败: {e}")
            log("尝试使用离线安装包...")
        
        # 降级方案：离线安装包
        if not install_success:
            if self._install_jenkins_bundled(sys_info, log):
                install_success = True
            else:
                log("❌ Jenkins 安装失败：在线和离线方式均不可用")
                log("请手动安装 Jenkins 或使用 WAR 包方式")
                return

        # 启动 Jenkins 服务
        log("启动 Jenkins 服务...")
        self.exec_command("systemctl daemon-reload 2>/dev/null || true", log)
        self.exec_command("systemctl enable jenkins 2>/dev/null || true", log)
        self.exec_command("systemctl start jenkins 2>/dev/null || true", log)
        
        # 如果不是 systemd，尝试直接启动
        jenkins_running = self.exec_command("curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login 2>/dev/null || echo '000'")
        if jenkins_running.strip() == '000':
            log("尝试直接启动 Jenkins...")
            self.exec_command("nohup java -jar /opt/jenkins.war --httpPort=8080 > /var/log/jenkins.log 2>&1 &", log)

        # 等待 Jenkins 启动
        log("等待 Jenkins 启动...")
        import time
        for i in range(6):
            time.sleep(5)
            check = self.exec_command("curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login 2>/dev/null || echo '000'")
            if check.strip() != '000':
                break
            log(f"等待中... ({(i+1)*5}s)")

        # 获取初始密码
        log("获取 Jenkins 初始密码...")
        initial_pwd = self.exec_command("cat /var/lib/jenkins/secrets/initialAdminPassword 2>/dev/null || echo '请检查 Jenkins 日志获取初始密码'")
        log(f"Jenkins 初始密码: {initial_pwd}")
        log("Jenkins 安装完成！访问 http://<服务器IP>:8080 进行初始化配置")

    def _install_jenkins_china_mirror(self, sys_info: dict, log):
        """使用国内镜像安装 Jenkins"""
        os_family = sys_info['os_family']
        
        # 使用清华镜像或阿里云镜像
        if os_family == 'debian':
            # 清华大学 Jenkins 镜像
            self.exec_command("curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/jenkins-ci/debian/jenkins-ci.key | tee /usr/share/keyrings/jenkins-keyring.asc > /dev/null", log)
            self.exec_command('echo deb [signed-by=/usr/share/keyrings/jenkins-keyring.asc] https://mirrors.tuna.tsinghua.edu.cn/jenkins-ci/debian-stable binary/ | tee /etc/apt/sources.list.d/jenkins.list > /dev/null', log)
            self.exec_command("apt-get update -qq && apt-get install -y -qq jenkins", log)
        elif os_family == 'redhat':
            # 使用 WAR 包方式（更兼容）
            log("下载 Jenkins WAR 包（清华镜像）...")
            self.exec_command("curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war -o /opt/jenkins.war", log)
            # 创建 systemd 服务
            self.exec_command("""cat > /etc/systemd/system/jenkins.service << 'EOF'
[Unit]
Description=Jenkins Continuous Integration Server
After=network.target

[Service]
Type=simple
User=root
Environment=JENKINS_HOME=/var/lib/jenkins
ExecStart=/usr/bin/java -jar /opt/jenkins.war --httpPort=8080
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
mkdir -p /var/lib/jenkins
systemctl daemon-reload""", log)
        else:
            # 通用 WAR 包安装
            self.exec_command("curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/jenkins/war-stable/latest/jenkins.war -o /opt/jenkins.war", log)

    def _install_runner(self, sys_info: dict, use_china_mirror: bool, log):
        """安装 GitLab Runner（支持多架构、国产 OS、国内镜像）
        
        Args:
            sys_info: 系统信息字典
            use_china_mirror: 是否使用国内镜像
            log: 日志回调
        """
        log("安装 GitLab Runner...")
        arch = sys_info['arch']
        os_family = sys_info['os_family']
        is_arm = sys_info['is_arm']

        # 检查是否已安装
        check = self.exec_command("which gitlab-runner 2>/dev/null || echo 'not_found'")
        if 'not_found' not in check:
            log("GitLab Runner 已安装，跳过")
            return

        # 确定架构后缀
        arch_suffix = ''
        if arch == 'x86_64':
            arch_suffix = 'amd64'
        elif arch == 'aarch64':
            arch_suffix = 'arm64'
        elif arch == 'armv7l':
            arch_suffix = 'arm'
        else:
            arch_suffix = 'amd64'  # 默认
            log(f"未知架构 {arch}，使用 amd64 默认值")

        # 安装 GitLab Runner - 三级降级策略
        install_success = False
        
        try:
            if use_china_mirror:
                # 国内镜像安装
                log("使用国内镜像安装 GitLab Runner...")
                self._install_runner_china_mirror(sys_info, log)
            else:
                log(f"下载 GitLab Runner ({arch_suffix})...")
                if os_family == 'debian':
                    self.exec_command("curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.deb.sh | bash", log)
                    self.exec_command("apt-get install -y -qq gitlab-runner", log)
                elif os_family == 'redhat':
                    self.exec_command("curl -L https://packages.gitlab.com/install/repositories/runner/gitlab-runner/script.rpm.sh | bash", log)
                    self.exec_command("yum install -y gitlab-runner", log)
                else:
                    # 通用二进制安装（支持多架构）
                    log("使用通用二进制安装...")
                    runner_url = f"https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-{arch_suffix}"
                    self.exec_command(f"curl -L --output /usr/local/bin/gitlab-runner '{runner_url}'", log)
                    self.exec_command("chmod +x /usr/local/bin/gitlab-runner", log)
                    # 创建 gitlab-runner 用户
                    self.exec_command("useradd --comment 'GitLab Runner' --create-home gitlab-runner 2>/dev/null || true", log)
            install_success = True
        except Exception as e:
            log(f"在线安装失败: {e}")
            log("尝试使用离线安装包...")
        
        # 降级方案：离线安装包
        if not install_success:
            if self._install_runner_bundled(sys_info, log):
                install_success = True
            else:
                log("❌ GitLab Runner 安装失败：在线和离线方式均不可用")
                return

        # 启动 Runner 服务
        log("启动 GitLab Runner 服务...")
        self.exec_command("gitlab-runner start 2>/dev/null || true", log)
        self.exec_command("gitlab-runner verify 2>/dev/null || true", log)

        log("GitLab Runner 安装完成！")
        log("请使用以下命令注册 Runner:")
        log("  gitlab-runner register --url <GitLab_URL> --registration-token <TOKEN>")

    def _install_runner_china_mirror(self, sys_info: dict, log):
        """使用国内镜像安装 GitLab Runner"""
        arch = sys_info['arch']
        os_family = sys_info['os_family']
        
        # 确定架构后缀
        if arch == 'x86_64':
            arch_suffix = 'amd64'
        elif arch == 'aarch64':
            arch_suffix = 'arm64'
        elif arch == 'armv7l':
            arch_suffix = 'arm'
        else:
            arch_suffix = 'amd64'
        
        # 直接下载二进制文件（更兼容各种系统）
        log(f"下载 GitLab Runner 二进制文件 ({arch_suffix})...")
        runner_url = f"https://gitlab-runner-downloads.s3.amazonaws.com/latest/binaries/gitlab-runner-linux-{arch_suffix}"
        self.exec_command(f"curl -L --output /usr/local/bin/gitlab-runner '{runner_url}'", log)
        self.exec_command("chmod +x /usr/local/bin/gitlab-runner", log)
        
        # 创建 gitlab-runner 用户
        self.exec_command("useradd --comment 'GitLab Runner' --create-home gitlab-runner 2>/dev/null || true", log)
        
        # 创建 systemd 服务
        log("创建 GitLab Runner 服务...")
        self.exec_command("""cat > /etc/systemd/system/gitlab-runner.service << 'EOF'
[Unit]
Description=GitLab Runner
After=network.target

[Service]
Type=simple
User=gitlab-runner
ExecStart=/usr/local/bin/gitlab-runner run --working-directory /home/gitlab-runner
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
mkdir -p /home/gitlab-runner
chown gitlab-runner:gitlab-runner /home/gitlab-runner
systemctl daemon-reload""", log)

    def configure_jenkins_pipeline(self, project_name: str, repo_url: str, branch: str,
                                     git_credential: dict = None, server_config: dict = None,
                                     deploy_method: str = "direct", log_callback=None):
        """配置 Jenkins 流水线（创建 Job、设置凭据）"""
        log = log_callback or (lambda msg: None)

        log("配置 Jenkins 流水线...")

        # 等待 Jenkins 完全启动
        import time
        log("等待 Jenkins 服务就绪...")
        time.sleep(5)

        # 检查 Jenkins 是否可访问
        jenkins_check = self.exec_command("curl -s -o /dev/null -w '%{http_code}' http://localhost:8080/login 2>/dev/null || echo '000'")
        if jenkins_check.strip() == '000':
            log("警告: Jenkins 可能尚未完全启动，请稍后手动检查")
        else:
            log(f"Jenkins 服务已就绪 (HTTP {jenkins_check.strip()})")

        # 使用 Jenkins CLI 创建 Job
        log(f"创建流水线任务: {project_name}")

        # 检查 Job 是否已存在
        job_check = self.exec_command(f"curl -s -o /dev/null -w '%{{http_code}}' http://localhost:8080/job/{project_name} 2>/dev/null")
        if job_check.strip() == '200':
            log(f"Job '{project_name}' 已存在，跳过创建")
        else:
            # 通过 Jenkins CLI 或 REST API 创建 Job
            # 先获取初始密码（如果需要）
            initial_pwd = self.exec_command("cat /var/lib/jenkins/secrets/initialAdminPassword 2>/dev/null || echo ''")

            # 使用 Jenkins CLI 创建 Pipeline Job
            cli_jar = "/var/cache/jenkins/war/WEB-INF/jenkins-cli.jar"
            cli_check = self.exec_command(f"test -f {cli_jar} && echo 'exists' || echo 'not_found'")

            if 'exists' in cli_check:
                # 使用 CLI 创建 Job
                job_xml = f"""<?xml version='1.1' encoding='UTF-8'?>
<flow-definition plugin="workflow-job">
  <description>CI/CD Pipeline for {project_name}</description>
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
          <url>{repo_url}</url>
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
                # 写入临时文件并创建 Job
                self.exec_command(f"cat > /tmp/{project_name}-job.xml << 'XMLEOF'\n{job_xml}\nXMLEOF", log)

                if initial_pwd:
                    self.exec_command(
                        f"java -jar {cli_jar} -s http://localhost:8080/ -auth admin:{initial_pwd} create-job {project_name} < /tmp/{project_name}-job.xml",
                        log
                    )
                else:
                    self.exec_command(
                        f"java -jar {cli_jar} -s http://localhost:8080/ create-job {project_name} < /tmp/{project_name}-job.xml",
                        log
                    )
                self.exec_command(f"rm -f /tmp/{project_name}-job.xml", log)
                log(f"Job '{project_name}' 创建成功")
            else:
                log("Jenkins CLI 不可用，请手动创建 Job 或等待 Jenkins 初始化完成后通过 Web UI 创建")

        log(f"\n✅ Jenkins 流水线配置完成！")
        log(f"📍 访问地址: http://<服务器IP>:8080/job/{project_name}")
        log(f"🚀 触发方式: 在 Jenkins 中点击 'Build Now' 或推送代码到 {branch} 分支")
        log(f"📋 查看日志: 在 Job 页面点击构建编号查看 Console Output")

    def configure_runner(self, repo_url: str, git_credential: dict = None, log_callback=None):
        """配置 Runner（注册到 GitLab/GitHub）"""
        log = log_callback or (lambda msg: None)

        log("配置 Runner...")

        # 检查 Runner 是否已注册
        runner_status = self.exec_command("gitlab-runner verify 2>&1 || echo 'not_configured'")
        if 'not_configured' not in runner_status and 'no runners' not in runner_status.lower():
            log("Runner 已配置，跳过注册")
            return

        log("\nRunner 需要手动注册到 GitLab/GitHub:")
        log("\n📋 注册步骤:")
        log("1. 登录 GitLab → Settings → CI/CD → Runners")
        log("2. 点击 'New project runner' 或 'New group runner'")
        log("3. 复制 registration token")
        log("4. 在服务器上执行:")
        log("   gitlab-runner register")
        log("   - URL: 你的 GitLab 地址")
        log("   - Token: 复制的 token")
        log("   - Executor: shell 或 docker")
        log("   - Tags: 自定义标签")

        log("\n✅ Runner 安装完成，请按照上述步骤完成注册")
        log("📋 注册完成后，推送代码到仓库即可自动触发流水线")

    def setup_environment(self, project_type: str, config: dict, log_callback=None):
        """根据项目类型初始化服务器环境"""
        log = log_callback or (lambda msg: None)

        log("检测操作系统...")
        os_info = self.exec_command("cat /etc/os-release 2>/dev/null | head -3 || uname -a")
        is_debian = "debian" in os_info.lower() or "ubuntu" in os_info.lower()
        is_centos = "centos" in os_info.lower() or "rhel" in os_info.lower() or "fedora" in os_info.lower()

        if project_type == "java-maven":
            jdk = config.get("jdkVersion", "17") or "17"
            log(f"安装 Java {jdk} 和 Maven...")
            if is_debian:
                self.exec_command("apt-get update -qq", log)
                self.exec_command(f"apt-get install -y -qq openjdk-{jdk}-jdk maven", log)
            elif is_centos:
                self.exec_command(f"yum install -y java-{jdk}-openjdk-devel maven", log)
            else:
                self.exec_command(f"apt-get install -y -qq openjdk-{jdk}-jdk maven 2>/dev/null || yum install -y java-{jdk}-openjdk-devel maven", log)
            self.exec_command("java -version", log)
            self.exec_command("mvn -version", log)

        elif project_type == "java-gradle":
            jdk = config.get("jdkVersion", "17") or "17"
            log(f"安装 Java {jdk} 和 Gradle...")
            if is_debian:
                self.exec_command("apt-get update -qq", log)
                self.exec_command(f"apt-get install -y -qq openjdk-{jdk}-jdk unzip", log)
            elif is_centos:
                self.exec_command(f"yum install -y java-{jdk}-openjdk-devel unzip", log)
            else:
                self.exec_command(f"apt-get install -y -qq openjdk-{jdk}-jdk unzip 2>/dev/null || yum install -y java-{jdk}-openjdk-devel unzip", log)
            self.exec_command("java -version", log)
            log("安装 Gradle...")
            self.exec_command("curl -sL https://services.gradle.org/distributions/gradle-8.5-bin.zip -o /tmp/gradle.zip", log)
            self.exec_command("unzip -qo /tmp/gradle.zip -d /opt && ln -sf /opt/gradle-8.5/bin/gradle /usr/local/bin/gradle", log)
            self.exec_command("gradle --version", log)

        elif project_type in ("vue", "react"):
            node_ver = config.get("nodeVersion", "20") or "20"
            log(f"安装 Node.js {node_ver}...")
            if is_debian:
                self.exec_command("apt-get update -qq", log)
                self.exec_command("apt-get install -y -qq curl", log)
                self.exec_command(f"curl -fsSL https://deb.nodesource.com/setup_{node_ver}.x | bash -", log)
                self.exec_command("apt-get install -y -qq nodejs", log)
            elif is_centos:
                self.exec_command(f"curl -fsSL https://rpm.nodesource.com/setup_{node_ver}.x | bash -", log)
                self.exec_command("yum install -y nodejs", log)
            else:
                self.exec_command(f"curl -fsSL https://deb.nodesource.com/setup_{node_ver}.x | bash - 2>/dev/null || curl -fsSL https://rpm.nodesource.com/setup_{node_ver}.x | bash -", log)
                self.exec_command("apt-get install -y nodejs 2>/dev/null || yum install -y nodejs", log)
            self.exec_command("node --version", log)
            self.exec_command("npm --version", log)

        elif project_type == "python":
            log("安装 Python 3 和 pip...")
            if is_debian:
                self.exec_command("apt-get update -qq", log)
                self.exec_command("apt-get install -y -qq python3 python3-pip python3-venv", log)
            elif is_centos:
                self.exec_command("yum install -y python3 python3-pip", log)
            else:
                self.exec_command("apt-get install -y -qq python3 python3-pip 2>/dev/null || yum install -y python3 python3-pip", log)
            self.exec_command("python3 --version", log)
            self.exec_command("pip3 --version", log)

        elif project_type == "go":
            log("安装 Go 1.21...")
            self.exec_command("curl -fsSL https://go.dev/dl/go1.21.5.linux-amd64.tar.gz -o /tmp/go.tar.gz", log)
            self.exec_command("rm -rf /usr/local/go && tar -C /usr/local -xzf /tmp/go.tar.gz", log)
            self.exec_command("ln -sf /usr/local/go/bin/go /usr/local/bin/go", log)
            self.exec_command("go version", log)

        # 安装 nginx（前端项目）
        if project_type in ("vue", "react"):
            log("安装 Nginx...")
            if is_debian:
                self.exec_command("apt-get install -y -qq nginx", log)
            elif is_centos:
                self.exec_command("yum install -y nginx", log)
            else:
                self.exec_command("apt-get install -y nginx 2>/dev/null || yum install -y nginx", log)

        log("环境初始化完成")

    def backup_deploy(self, deploy_path: str, project_name: str, log_callback=None):
        """备份服务器上的旧版本

        Args:
            deploy_path: 部署根目录
            project_name: 项目名称
            log_callback: 日志回调
        """
        log = log_callback or (lambda msg: None)
        app_dir = f"{deploy_path}/{project_name}"
        backup_dir = f"{deploy_path}/backup"
        timestamp = "$(date +%Y%m%d_%H%M%S)"

        # 检查应用目录是否存在
        log(f"检查应用目录: {app_dir}")
        result = self.exec_command(f"test -d {app_dir} && echo 'exists' || echo 'not_exists'", log)

        if result and 'exists' in result:
            # 创建备份目录
            log(f"创建备份目录: {backup_dir}")
            self.exec_command(f"mkdir -p {backup_dir}", log)

            # 备份旧版本
            backup_name = f"{project_name}_{timestamp}"
            log(f"备份旧版本到: {backup_dir}/{backup_name}")
            self.exec_command(f"cp -r {app_dir} {backup_dir}/{backup_name}", log)

            # 保留最近 5 个备份，清理旧的
            log("清理旧备份（保留最近 5 个）...")
            self.exec_command(
                f"cd {backup_dir} && ls -dt {project_name}_* 2>/dev/null | tail -n +6 | xargs rm -rf 2>/dev/null || true",
                log
            )

            log(f"备份完成: {backup_dir}/{backup_name}")
        else:
            log(f"应用目录 {app_dir} 不存在，跳过备份（首次部署）")

    def deploy(self, repo_url: str, branch: str, project_type: str, project_name: str,
               port: int, deploy_path: str, git_credential: dict = None,
               tool: str = "", deploy_method: str = "direct", app_server: dict = None, log_callback=None):
        """在服务器上部署应用

        Args:
            deploy_method: "docker" | "direct" | "app_server"
            app_server: 应用服务器配置 {"type": "tongweb"|"tomcat", "home": "/opt/...", "port": 9060, "contextPath": "/app"}
        """
        log = log_callback or (lambda msg: None)

        # 创建部署目录
        app_dir = f"{deploy_path}/{project_name}"
        log(f"创建部署目录: {app_dir}")
        self.exec_command(f"mkdir -p {app_dir}", log)

        # 克隆或拉取代码
        log("在服务器上拉取代码...")
        auth_url = repo_url
        if git_credential and git_credential.get("type") == "password":
            from urllib.parse import urlparse, urlunparse
            username = git_credential.get("username", "")
            password = git_credential.get("password", "")
            if username and password:
                parsed = urlparse(repo_url)
                auth_netloc = f"{username}:{password}@{parsed.hostname}"
                if parsed.port:
                    auth_netloc += f":{parsed.port}"
                auth_url = urlunparse(parsed._replace(netloc=auth_netloc))

        self.exec_command(f"cd {app_dir} && git clone --branch {branch} --single-branch {auth_url} . 2>/dev/null || (cd {app_dir} && git pull origin {branch})", log)

        # 根据部署方式分发
        if deploy_method == "docker":
            self._deploy_docker(app_dir, project_type, project_name, port, tool, log)
        elif deploy_method == "app_server":
            self._deploy_app_server(app_dir, project_type, project_name, port, app_server or {}, log)
        else:
            self._deploy_direct(app_dir, project_type, project_name, port, tool, log)

        log(f"部署完成！应用运行在 {self.host}:{port}")

    def _deploy_docker(self, app_dir: str, project_type: str, project_name: str,
                       port: int, tool: str, log_callback):
        """Docker 容器化部署（支持多架构、国内镜像）"""
        log = log_callback or (lambda msg: None)
        container_name = project_name.lower().replace(" ", "-")

        # 检测系统信息
        sys_info = self.detect_system_info(log)
        use_china_mirror = sys_info['is_china_os']

        # 检查 Docker 是否安装
        log("检查 Docker 环境...")
        result = self.exec_command("docker --version", log)
        if not result or "Docker" not in (result if isinstance(result, str) else ""):
            log("⚠️ Docker 未安装，正在自动安装...")
            self._install_docker(sys_info, use_china_mirror, log)

        # 配置 Docker 镜像加速（国内环境）
        if use_china_mirror:
            log("配置 Docker 镜像加速...")
            self._configure_docker_mirror(log)

        # 检查是否有 Dockerfile，没有则自动生成
        log("检查 Dockerfile...")
        check_result = self.exec_command(f"test -f {app_dir}/Dockerfile && echo 'exists' || echo 'missing'", log)
        if check_result and "missing" in (check_result if isinstance(check_result, str) else ""):
            log("自动生成 Dockerfile...")
            dockerfile = self._generate_dockerfile(project_type, tool)
            self.exec_command(f"cat > {app_dir}/Dockerfile << 'DOCKERFILE_EOF'\n{dockerfile}\nDOCKERFILE_EOF", log)

        # 构建 Docker 镜像
        log(f"构建 Docker 镜像: {container_name}...")
        self.exec_command(f"cd {app_dir} && docker build -t {container_name} .", log)

        # 停止并删除旧容器
        log("清理旧容器...")
        self.exec_command(f"docker stop {container_name} 2>/dev/null; docker rm {container_name} 2>/dev/null", log)

        # 启动新容器
        log(f"启动容器: {container_name}（端口 {port}）...")
        self.exec_command(
            f"docker run -d --name {container_name} --restart=always -p {port}:{port} {container_name}",
            log
        )

        log(f"✅ Docker 容器 {container_name} 已启动，端口映射 {port}:{port}")

    def _install_docker(self, sys_info: dict, use_china_mirror: bool, log):
        """安装 Docker（支持多架构、国产 OS、国内镜像、离线包降级）
        
        Args:
            sys_info: 系统信息字典
            use_china_mirror: 是否使用国内镜像
            log: 日志回调
        """
        arch = sys_info['arch']
        os_family = sys_info['os_family']
        
        # 三级降级策略
        install_success = False
        
        try:
            if use_china_mirror:
                # 使用阿里云镜像安装 Docker
                log("使用阿里云镜像安装 Docker...")
                if os_family == 'debian':
                    self.exec_command("apt-get update -qq && apt-get install -y -qq apt-transport-https ca-certificates curl gnupg", log)
                    self.exec_command("curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | apt-key add -", log)
                    self.exec_command(f'add-apt-repository "deb [arch={arch}] https://mirrors.aliyun.com/docker-ce/linux/ubuntu $(lsb_release -cs) stable"', log)
                    self.exec_command("apt-get update -qq && apt-get install -y -qq docker-ce docker-ce-cli containerd.io", log)
                elif os_family == 'redhat':
                    self.exec_command("yum install -y yum-utils device-mapper-persistent-data lvm2", log)
                    self.exec_command("yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo", log)
                    self.exec_command("sed -i 's+download.docker.com+mirrors.aliyun.com/docker-ce+' /etc/yum.repos.d/docker-ce.repo", log)
                    self.exec_command("yum install -y docker-ce docker-ce-cli containerd.io", log)
                else:
                    # 通用脚本安装
                    self.exec_command("curl -fsSL https://get.docker.com | sh", log)
            else:
                # 官方源安装
                log("安装 Docker...")
                if os_family == 'debian':
                    self.exec_command("apt-get update -qq && apt-get install -y -qq docker.io", log)
                elif os_family == 'redhat':
                    self.exec_command("yum install -y docker", log)
                else:
                    self.exec_command("curl -fsSL https://get.docker.com | sh", log)
            install_success = True
        except Exception as e:
            log(f"在线安装失败: {e}")
            log("尝试使用离线安装包...")
        
        # 降级方案：离线安装包
        if not install_success:
            if self._install_docker_bundled(sys_info, log):
                install_success = True
            else:
                log("❌ Docker 安装失败：在线和离线方式均不可用")
                return
        
        # 启动 Docker
        log("启动 Docker 服务...")
        self.exec_command("systemctl start docker 2>/dev/null || service docker start", log)
        self.exec_command("systemctl enable docker 2>/dev/null || true", log)
        
        log("Docker 安装完成！")

    def _configure_docker_mirror(self, log):
        """配置 Docker 镜像加速（国内环境）"""
        mirror_config = '''{
  "registry-mirrors": [
    "https://docker.mirrors.ustc.edu.cn",
    "https://hub-mirror.c.163.com",
    "https://mirror.baidubce.com"
  ]
}'''
        self.exec_command(f"""mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{mirror_config}
EOF
systemctl restart docker 2>/dev/null || service docker restart""", log)
        log("Docker 镜像加速配置完成")

    def _deploy_direct(self, app_dir: str, project_type: str, project_name: str,
                       port: int, tool: str, log_callback):
        """直接部署（无容器）"""
        log = log_callback or (lambda msg: None)

        # TongWeb 部署
        if tool == "tongweb" and project_type.startswith("java"):
            self._deploy_tongweb(app_dir, project_type, project_name, port, log)
            return

        # 根据项目类型构建和启动
        if project_type == "java-maven":
            log("Maven 构建...")
            self.exec_command(f"cd {app_dir} && mvn clean package -DskipTests", log)
            log(f"启动 Java 应用（端口 {port}）...")
            self.exec_command(f"pkill -f '{project_name}.jar' 2>/dev/null; sleep 1", log)
            self.exec_command(f"cd {app_dir} && nohup java -jar target/{project_name}.jar --server.port={port} > /tmp/{project_name}.log 2>&1 &", log)

        elif project_type == "java-gradle":
            log("Gradle 构建...")
            self.exec_command(f"cd {app_dir} && gradle bootJar --no-daemon", log)
            log(f"启动 Java 应用（端口 {port}）...")
            self.exec_command(f"pkill -f '{project_name}.jar' 2>/dev/null; sleep 1", log)
            self.exec_command(f"cd {app_dir} && nohup java -jar build/libs/{project_name}-*.jar --server.port={port} > /tmp/{project_name}.log 2>&1 &", log)

        elif project_type in ("vue", "react"):
            log("构建前端...")
            self.exec_command(f"cd {app_dir} && npm ci && npm run build", log)
            log("配置 Nginx...")
            nginx_conf = f"""server {{
    listen {port};
    server_name _;
    root {app_dir}/dist;
    index index.html;
    location / {{
        try_files $uri $uri/ /index.html;
    }}
}}"""
            self.exec_command(f"echo '{nginx_conf}' > /etc/nginx/conf.d/{project_name}.conf", log)
            self.exec_command("nginx -t && systemctl reload nginx 2>/dev/null || nginx -s reload 2>/dev/null || nginx", log)

        elif project_type == "python":
            log("安装 Python 依赖...")
            self.exec_command(f"cd {app_dir} && pip3 install -r requirements.txt", log)
            log(f"启动 Python 应用...")
            self.exec_command(f"pkill -f 'python.*app.py' 2>/dev/null; sleep 1", log)
            self.exec_command(f"cd {app_dir} && nohup python3 app.py > /tmp/{project_name}.log 2>&1 &", log)

        elif project_type == "go":
            log("构建 Go 应用...")
            self.exec_command(f"cd {app_dir} && CGO_ENABLED=0 go build -o app .", log)
            log(f"启动 Go 应用（端口 {port}）...")
            self.exec_command(f"pkill -f './app' 2>/dev/null; sleep 1", log)
            self.exec_command(f"cd {app_dir} && nohup ./app > /tmp/{project_name}.log 2>&1 &", log)

    def _deploy_app_server(self, app_dir: str, project_type: str, project_name: str,
                           port: int, app_server: dict, log_callback):
        """部署到应用服务器（TongWeb/Tomcat）"""
        log = log_callback or (lambda msg: None)
        server_type = app_server.get("type", "tongweb")
        server_home = app_server.get("home", "")
        server_port = app_server.get("port", port)
        context_path = app_server.get("contextPath", "/app")

        if not server_home:
            server_home = "/opt/TongWeb7.0" if server_type == "tongweb" else "/opt/tomcat"

        log(f"部署到{server_type.upper()}应用服务器: {server_home}")

        # 检查应用服务器是否安装
        log(f"检查{server_type.upper()}安装...")
        result = self.exec_command(f"test -d {server_home} && echo 'exists' || echo 'missing'", log)
        if result and "missing" in (result if isinstance(result, str) else ""):
            raise SSHError(f"{server_type.upper()} 未安装在 {server_home}，请先安装")

        # 构建 WAR 包
        if project_type == "java-maven":
            log("Maven 构建 WAR 包...")
            self.exec_command(f"cd {app_dir} && mvn clean package -DskipTests", log)
            war_file = f"{app_dir}/target/{project_name}.war"
            # 检查是否生成了不同名称的 war
            self.exec_command(f"test -f {war_file} || mv {app_dir}/target/*.war {war_file} 2>/dev/null", log)
        elif project_type == "java-gradle":
            log("Gradle 构建 WAR 包...")
            self.exec_command(f"cd {app_dir} && gradle war --no-daemon", log)
            war_file = f"{app_dir}/build/libs/{project_name}.war"
            self.exec_command(f"test -f {war_file} || mv {app_dir}/build/libs/*.war {war_file} 2>/dev/null", log)
        else:
            raise SSHError(f"应用服务器部署仅支持 Java 项目，当前项目类型: {project_type}")

        # 确定部署目录
        if server_type == "tongweb":
            autodeploy_dir = f"{server_home}/autodeploy"
        else:  # tomcat
            autodeploy_dir = f"{server_home}/webapps"

        # 备份旧版本
        log("备份旧版本...")
        self.exec_command(f"mkdir -p {server_home}/backup", log)
        self.exec_command(f"cp {autodeploy_dir}/{project_name}.war {server_home}/backup/{project_name}.war.$(date +%Y%m%d%H%M%S) 2>/dev/null || true", log)

        # 部署 WAR 包
        log(f"部署 WAR 到 {autodeploy_dir}...")
        self.exec_command(f"cp {war_file} {autodeploy_dir}/{project_name}.war", log)

        # 重启应用服务器
        log(f"重启{server_type.upper()}...")
        if server_type == "tongweb":
            self.exec_command(f"{server_home}/bin/stopserver.sh 2>/dev/null || true", log)
            self.exec_command("sleep 3", log)
            self.exec_command(f"{server_home}/bin/startserver.sh", log)
        else:  # tomcat
            self.exec_command(f"{server_home}/bin/shutdown.sh 2>/dev/null || true", log)
            self.exec_command("sleep 3", log)
            self.exec_command(f"{server_home}/bin/startup.sh", log)

        log(f"✅ {server_type.upper()} 已重启，应用访问地址: http://{self.host}:{server_port}{context_path}")

    def _generate_dockerfile(self, project_type: str, tool: str = "") -> str:
        """根据项目类型生成 Dockerfile"""
        if project_type == "java-maven":
            return """FROM maven:3.9-eclipse-temurin-17 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn dependency:go-offline
COPY src ./src
RUN mvn clean package -DskipTests

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/target/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]"""
        elif project_type == "java-gradle":
            return """FROM gradle:8-jdk17 AS build
WORKDIR /app
COPY . .
RUN gradle bootJar --no-daemon

FROM eclipse-temurin:17-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.jar app.jar
EXPOSE 8080
CMD ["java", "-jar", "app.jar"]"""
        elif project_type == "vue":
            return """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf 2>/dev/null || true
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]"""
        elif project_type == "react":
            return """FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]"""
        elif project_type == "python":
            return """FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python3", "app.py"]"""
        elif project_type == "go":
            return """FROM golang:1.22-alpine AS build
WORKDIR /app
COPY . .
RUN CGO_ENABLED=0 go build -o app .

FROM alpine:3.19
WORKDIR /app
COPY --from=build /app/app .
EXPOSE 8080
CMD ["./app"]"""
        else:
            return f"""FROM ubuntu:22.04
WORKDIR /app
COPY . .
EXPOSE 8080
CMD ["bash"]"""

    def _deploy_tongweb(self, app_dir: str, project_type: str, project_name: str,
                        port: int, log_callback=None):
        """TongWeb 部署逻辑"""
        log = log_callback or (lambda msg: None)
        tongweb_home = "/opt/TongWeb7.0"

        log("检测 TongWeb 安装...")
        self.exec_command(f"test -d {tongweb_home} || echo 'TONGWEB_NOT_FOUND'", log)

        # 构建 WAR
        if project_type == "java-maven":
            log("Maven 构建 WAR...")
            self.exec_command(f"cd {app_dir} && mvn clean package -DskipTests", log)
            war_file = f"{app_dir}/target/{project_name}.war"
        elif project_type == "java-gradle":
            log("Gradle 构建 WAR...")
            self.exec_command(f"cd {app_dir} && gradle war -x test --no-daemon", log)
            war_file = f"{app_dir}/build/libs/{project_name}.war"
        else:
            raise SSHError("TongWeb 仅支持 Java 项目")

        # 停止 TongWeb
        log("停止 TongWeb...")
        self.exec_command(f"{tongweb_home}/bin/stopserver.sh 2>/dev/null || true", log)
        self.exec_command("sleep 3", log)

        # 备份旧版本
        log("备份旧版本...")
        self.exec_command(f"mkdir -p {tongweb_home}/backup", log)
        self.exec_command(f"cp {tongweb_home}/autodeploy/{project_name}.war {tongweb_home}/backup/{project_name}.w.$(date +%Y%m%d%H%M%S) 2>/dev/null || true", log)

        # 部署 WAR
        log(f"部署 WAR 到 TongWeb ({tongweb_home}/autodeploy/)...")
        self.exec_command(f"cp {war_file} {tongweb_home}/autodeploy/{project_name}.war", log)

        # 启动 TongWeb
        log("启动 TongWeb...")
        self.exec_command(f"{tongweb_home}/bin/startserver.sh", log)
        self.exec_command("sleep 5", log)

        log(f"TongWeb 部署完成！应用地址: http://{self.host}:{port}/{project_name}")
        log(f"管理控制台: https://{self.host}:9060/console")

    def close(self):
        """关闭 SSH 连接（包括所有跳转链路）"""
        if self.client:
            self.client.close()
            self.client = None
        for t in self.jump_transports:
            try:
                t.close()
            except Exception:
                pass
        self.jump_transports = []

    def _exec(self, command: str, log_callback=None, timeout: int = 600) -> str:
        """exec_command 的简写别名"""
        return self.exec_command(command, log_callback, timeout)

    def __del__(self):
        self.close()


class SSHError(Exception):
    """SSH 操作异常"""
    pass
