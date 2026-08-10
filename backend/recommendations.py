"""
部署建议引擎
根据项目类型、工具选择、网络环境等提供智能部署建议
"""


def get_deployment_recommendations(config: dict) -> dict:
    """
    根据配置生成部署建议
    返回：
    {
        "server": { ... },        # CI/CD 服务器部署建议
        "deployMethod": { ... },   # 部署方式建议（Docker/直接）
        "network": { ... },        # 网络方案建议
        "scenarios": [ ... ],      # 匹配的场景
        "tips": [ ... ]            # 额外提示
    }
    """
    tool = config.get("tool", "")
    project_type = config.get("projectType", "")
    has_relay = bool(config.get("relayServer"))
    tool_deploy = config.get("toolDeploy", "dedicated")
    network_access = config.get("networkAccess", {})
    server_config = config.get("server", {})

    result = {
        "server": _recommend_server(tool, project_type, server_config, has_relay, tool_deploy),
        "deployMethod": _recommend_deploy_method(project_type),
        "network": _recommend_network(config),
        "scenarios": _detect_scenarios(config),
        "tips": _generate_tips(config),
    }
    return result


def _recommend_server(tool: str, project_type: str, server_config: dict, has_relay: bool = False, tool_deploy: str = "dedicated") -> dict:
    """CI/CD 服务器部署位置建议"""
    recommendations = []
    best_practice = ""

    # 根据工具推荐
    if tool == "jenkins":
        recommendations.append({
            "location": "与代码仓库同云或专线连接",
            "reason": "Jenkins 需要频繁拉取代码，同云部署减少网络延迟",
            "priority": "high"
        })
        recommendations.append({
            "location": "可部署在 DMZ 区域",
            "reason": "Jenkins 作为 CI 节点，既需要访问代码仓库，也需要 SSH 到目标服务器",
            "priority": "medium"
        })
        best_practice = "建议将 Jenkins Master 部署在与代码仓库同一网络或可通过专线/VPN 访问的位置"
    elif tool == "github":
        recommendations.append({
            "location": "使用 GitHub-hosted Runner（推荐）",
            "reason": "无需自建服务器，GitHub 提供免费的 Runner 资源",
            "priority": "high"
        })
        recommendations.append({
            "location": "Self-hosted Runner 部署在目标服务器同网络",
            "reason": "如果需要访问内网资源，在目标服务器同网络部署 Runner",
            "priority": "medium"
        })
        best_practice = "优先使用 GitHub-hosted Runner，需要访问内网时再自建"
    elif tool == "gitlab":
        recommendations.append({
            "location": "GitLab Runner 与 GitLab Server 同网络",
            "reason": "Runner 需要与 GitLab Server 通信，同网络延迟最低",
            "priority": "high"
        })
        recommendations.append({
            "location": "Runner 可部署在目标服务器本地",
            "reason": "减少部署时的网络传输，适合大型项目",
            "priority": "medium"
        })
        best_practice = "GitLab Runner 建议与 GitLab Server 同网络，或部署在目标服务器本地"
    elif tool in ("aliyun", "huawei", "tencent"):
        cloud_name = {"aliyun": "阿里云", "huawei": "华为云", "tencent": "腾讯云"}[tool]
        recommendations.append({
            "location": f"部署在{cloud_name}同区域 ECS/CVM",
            "reason": f"流水线在{cloud_name}运行，同区域部署网络最快",
            "priority": "high"
        })
        best_practice = f"建议 CI/CD 组件部署在与代码仓库相同的{cloud_name}区域"
    else:
        recommendations.append({
            "location": "与目标部署服务器同网络",
            "reason": "减少部署时的网络传输",
            "priority": "medium"
        })
        best_practice = "建议 CI/CD 组件部署在与目标服务器可互通的网络位置"

    # 跨云场景额外建议
    if has_relay:
        recommendations.append({
            "location": "中继服务器部署在两个云的网络交界处",
            "reason": "中继服务器需要同时访问代码仓库云和目标服务器云",
            "priority": "high"
        })

    # 根据工具部署位置补充建议
    if tool_deploy == "dedicated":
        recommendations.append({
            "location": "独立服务器部署 CI/CD 工具",
            "reason": "工具服务器与目标服务器分离，互不影响，适合生产环境",
            "priority": "high"
        })
    elif tool_deploy == "target":
        recommendations.append({
            "location": "CI/CD 工具与目标服务器合并",
            "reason": "节省服务器资源，但构建任务可能影响应用运行",
            "priority": "medium"
        })
    elif tool_deploy == "managed":
        recommendations.append({
            "location": "使用云托管 CI/CD 服务",
            "reason": "免运维，但需确保托管服务能访问目标服务器网络",
            "priority": "high"
        })

    return {
        "recommendations": recommendations,
        "bestPractice": best_practice
    }


def _recommend_deploy_method(project_type: str) -> dict:
    """部署方式建议：Docker vs 直接部署"""
    recommendations = []

    # 根据项目类型推荐
    docker_recommended = ["java-maven", "java-gradle", "python", "go"]
    docker_optional = ["vue", "react"]

    if project_type in docker_recommended:
        recommendations.append({
            "method": "Docker 容器部署",
            "recommended": True,
            "reason": f"{_get_project_type_name(project_type)} 项目使用 Docker 可确保环境一致性，便于扩缩容",
            "pros": ["环境隔离", "一键部署", "易于回滚", "资源利用率高"],
            "cons": ["需要安装 Docker", "镜像占用磁盘"]
        })
        recommendations.append({
            "method": "直接部署（JAR/二进制）",
            "recommended": False,
            "reason": "适合服务器资源有限或已有部署体系的场景",
            "pros": ["无需额外依赖", "启动快", "资源占用少"],
            "cons": ["环境配置复杂", "回滚麻烦", "多版本管理困难"]
        })
    elif project_type in docker_optional:
        recommendations.append({
            "method": "Nginx + 静态文件",
            "recommended": True,
            "reason": "前端项目构建后为静态文件，Nginx 直接托管最高效",
            "pros": ["性能最优", "配置简单", "资源占用少"],
            "cons": ["需要 Nginx", "不支持 SSR"]
        })
        recommendations.append({
            "method": "Docker + Nginx",
            "recommended": False,
            "reason": "适合需要环境隔离或容器化编排的场景",
            "pros": ["环境隔离", "便于编排"],
            "cons": ["资源开销大", "调试稍复杂"]
        })

    # 根据部署模式补充
    if deploy_mode == "build":
        recommendations.append({
            "note": "「含产物构建」模式自动生成 Dockerfile，推荐使用 Docker 部署",
            "type": "info"
        })
    elif deploy_mode == "code":
        recommendations.append({
            "note": "「纯代码部署」模式适合直接部署，服务器需预装运行环境",
            "type": "info"
        })

    return {
        "recommendations": recommendations,
        "defaultChoice": "docker" if project_type in docker_recommended else "nginx"
    }


def _recommend_network(config: dict) -> dict:
    """网络方案建议，支持多跳链路"""
    has_relay = bool(config.get("relayServer"))
    server = config.get("server", {})
    relay = config.get("relayServer", {})
    network_access = config.get("networkAccess", {})
    hops = network_access.get("hops", [])
    hop_types = [h.get("type", "") for h in hops]
    access_method = network_access.get("method", "direct")

    recommendations = []
    scenario = _detect_network_scenario(config)

    if scenario == "same_cloud":
        recommendations.append({
            "scheme": "同云内网部署",
            "description": "代码仓库和目标服务器在同一云厂商，使用内网地址通信",
            "steps": [
                "使用内网 IP 或内网域名配置仓库地址",
                "CI/CD 服务器和目标服务器在同一 VPC 或安全组",
                "无需额外网络配置"
            ],
            "recommended": True
        })

    elif scenario == "cross_cloud":
        recommendations.append({
            "scheme": "云联网/专线连接",
            "description": "通过云厂商的云联网或专线打通两个云的网络",
            "steps": [
                "在两个云之间建立云联网/专线连接",
                "配置路由和安全组规则",
                "CI/CD 服务器通过内网访问目标服务器"
            ],
            "recommended": True,
            "cost": "中等，需要云联网费用"
        })
        recommendations.append({
            "scheme": "中继服务器转发",
            "description": "在可达两个云的位置部署中继服务器，通过 SSH 跳转",
            "steps": [
                "部署一台同时能访问两个云的服务器作为中继",
                "配置 SSH 隧道或端口转发",
                "CI/CD 通过中继服务器 SSH 到目标服务器"
            ],
            "recommended": True,
            "cost": "低，仅需一台中继服务器"
        })
        recommendations.append({
            "scheme": "VPN 互联",
            "description": "通过 IPSec/OpenVPN 建立站点间 VPN",
            "steps": [
                "在两个云各部署 VPN 网关",
                "建立 IPSec VPN 隧道",
                "配置路由使内网互通"
            ],
            "recommended": False,
            "cost": "低，但配置复杂"
        })

    elif scenario == "isolated_cloud":
        recommendations.append({
            "scheme": "中继服务器 + 离线包传输",
            "description": "通过中继服务器传输构建产物到隔离网络",
            "steps": [
                "在外网构建并打包产物",
                "通过中继服务器（DMZ）传输到隔离网络",
                "隔离网络内的 Runner/Jenkins 接收产物并部署"
            ],
            "recommended": True,
            "cost": "中等"
        })
        recommendations.append({
            "scheme": "专线/VPN 接入",
            "description": "通过专线或 VPN 将隔离网络接入公网",
            "steps": [
                "申请专线或 VPN 接入审批",
                "配置安全策略和防火墙规则",
                "CI/CD 通过专线访问隔离网络"
            ],
            "recommended": False,
            "cost": "高，需要审批和专线费用"
        })
        recommendations.append({
            "scheme": "完全离线构建",
            "description": "在隔离网络内部署完整的 CI/CD 和代码仓库",
            "steps": [
                "在隔离网络内部署 GitLab/Gitea 作为代码仓库",
                "定期从外部同步代码和依赖",
                "内部 CI/CD 完成构建和部署"
            ],
            "recommended": False,
            "cost": "高，需要完整基础设施"
        })

    # 堡垒机场景建议
    if access_method == "bastion" or ("bastion" in hop_types and "zero_trust" not in hop_types):
        recommendations.append({
            "scheme": "堡垒机 + SSH 代理跳转",
            "description": "通过堡垒机建立 SSH 代理通道，CI/CD 工具通过代理访问目标服务器",
            "steps": [
                "在堡垒机配置 CI/CD 服务器的 SSH 公钥白名单",
                "配置堡垒机到目标服务器的跳转规则",
                "CI/CD 服务器通过 SSH ProxyJump 或 ProxyCommand 连接"
            ],
            "recommended": True,
            "cost": "低，仅需堡垒机配置"
        })

    # 零信任场景建议
    if access_method == "zero_trust" or ("zero_trust" in hop_types and "bastion" not in hop_types):
        recommendations.append({
            "scheme": "零信任网关 + 临时凭证",
            "description": "CI/CD 服务器通过零信任平台获取临时访问凭证，动态授权访问目标服务器",
            "steps": [
                "在零信任平台注册 CI/CD 服务器为受信任设备",
                "配置 CI/CD 服务器的访问策略和目标资源",
                "通过 API 获取临时 Token 或证书进行连接"
            ],
            "recommended": True,
            "cost": "中等，需要零信任平台授权"
        })

    # 零信任 + 堡垒机组合场景
    if "bastion" in hop_types and "zero_trust" in hop_types:
        recommendations.append({
            "scheme": "零信任 + 堡垒机链路部署",
            "description": "CI/CD 先通过零信任网关接入隔离网络，再通过堡垒机审计通道到达目标服务器",
            "steps": [
                "在零信任平台注册 CI/CD 服务器，获取内网访问权限",
                "在堡垒机配置 CI/CD 服务器的 SSH 公钥白名单",
                "CI/CD 通过链路: 零信任网关 → 堡垒机 → 目标服务器 完成部署"
            ],
            "recommended": True,
            "cost": "中等，需要零信任 + 堡垒机双重配置"
        })

    return {
        "scenario": scenario,
        "scenarioName": _get_scenario_name(scenario),
        "recommendations": recommendations
    }


def _detect_scenarios(config: dict) -> list:
    """检测匹配的场景"""
    scenarios = []
    server = config.get("server", {})
    relay = config.get("relayServer", {})
    network_access = config.get("networkAccess", {})
    hops = network_access.get("hops", [])
    hop_types = [h.get("type", "") for h in hops]
    access_method = network_access.get("method", "direct")
    branches = config.get("branches", [])
    tool = config.get("tool", "")

    # 多分支发布场景
    if len(branches) > 1:
        scenarios.append({
            "name": "多分支并行发布",
            "description": "多个分支同时构建和部署，支持审批合并到主分支",
            "matched": True
        })

    # 跨云/隔离场景
    if relay.get("host") or (access_method == "relay" and network_access.get("host")):
        scenarios.append({
            "name": "跨云/隔离网络部署",
            "description": "代码仓库和目标服务器在不同网络，通过中继服务器桥接",
            "matched": True
        })

    # 堡垒机场景（仅堡垒机，无零信任）
    if access_method == "bastion" or ("bastion" in hop_types and "zero_trust" not in hop_types):
        scenarios.append({
            "name": "堡垒机安全通道部署",
            "description": "通过堡垒机审计通道访问目标服务器，所有操作可追溯",
            "matched": True
        })

    # 零信任场景（仅零信任，无堡垒机）
    if access_method == "zero_trust" or ("zero_trust" in hop_types and "bastion" not in hop_types):
        scenarios.append({
            "name": "零信任安全接入部署",
            "description": "通过零信任网关动态授权访问隔离网络内的目标服务器",
            "matched": True
        })

    # 零信任 + 堡垒机组合场景
    if "bastion" in hop_types and "zero_trust" in hop_types:
        scenarios.append({
            "name": "零信任 + 堡垒机链路部署",
            "description": "通过零信任网关接入隔离网络，再通过堡垒机审计通道到达目标服务器",
            "matched": True
        })

    # Docker 构建场景
    if config.get("deployMethod") == "docker":
        scenarios.append({
            "name": "容器化构建部署",
            "description": "使用 Docker 多阶段构建，自动打包为容器镜像",
            "matched": True
        })

    return scenarios


def _detect_network_scenario(config: dict) -> str:
    """检测网络场景类型"""
    relay = config.get("relayServer", {})
    server = config.get("server", {})
    network_access = config.get("networkAccess", {})
    hops = network_access.get("hops", [])

    # 新的多跳链路
    if hops:
        hop_types = [h.get("type", "") for h in hops]
        has_bastion = "bastion" in hop_types
        has_zero_trust = "zero_trust" in hop_types
        if has_bastion and has_zero_trust:
            return "zero_trust_bastion"
        elif has_zero_trust:
            return "zero_trust"
        elif has_bastion:
            return "bastion"
        else:
            return "isolated_cloud" if network_access.get("isolated", False) else "cross_cloud"

    # 向后兼容旧版单跳
    access_method = network_access.get("method", "direct")
    if access_method == "bastion":
        return "bastion"
    if access_method == "zero_trust":
        return "zero_trust"
    if access_method == "relay":
        return "isolated_cloud" if network_access.get("isolated", False) else "cross_cloud"

    # 旧中继服务器兼容
    if relay.get("host"):
        return "isolated_cloud" if relay.get("isolated", False) else "cross_cloud"

    # 检查服务器地址是否暗示同云
    server_host = server.get("host", "")
    if server_host and any(keyword in server_host for keyword in ["10.", "172.", "192.168"]):
        return "same_cloud"

    return "same_cloud"


def _get_scenario_name(scenario: str) -> str:
    names = {
        "same_cloud": "同云部署",
        "cross_cloud": "跨云部署",
        "isolated_cloud": "隔离网络部署（如首信云）",
        "bastion": "堡垒机安全通道",
        "zero_trust": "零信任安全接入",
        "zero_trust_bastion": "零信任 + 堡垒机链路",
    }
    return names.get(scenario, "标准部署")


def _get_project_type_name(pt: str) -> str:
    names = {
        "java-maven": "Java Maven",
        "java-gradle": "Java Gradle",
        "vue": "Vue.js",
        "react": "React",
        "python": "Python",
        "go": "Go"
    }
    return names.get(pt, pt)


def _generate_tips(config: dict) -> list:
    """生成额外提示"""
    tips = []
    tool = config.get("tool", "")
    project_type = config.get("projectType", "")
    relay = config.get("relayServer", {})
    network_access = config.get("networkAccess", {})
    hops = network_access.get("hops", [])
    hop_types = [h.get("type", "") for h in hops]
    access_method = network_access.get("method", "direct")
    tool_deploy = config.get("toolDeploy", "dedicated")

    # 安全提示
    if relay.get("host") or (access_method == "relay" and network_access.get("host")) or "relay" in hop_types:
        tips.append({
            "type": "warning",
            "text": "中继服务器请确保 SSH 密钥安全，建议使用专用密钥对"
        })

    # 堡垒机提示
    if access_method == "bastion" or "bastion" in hop_types:
        tips.append({
            "type": "warning",
            "text": "堡垒机请确保 SSH 公钥已加入白名单，并配置正确的跳转命令"
        })
        tips.append({
            "type": "info",
            "text": "所有通过堡垒机的操作均会被审计记录，建议使用最小权限账号"
        })

    # 零信任提示
    if access_method == "zero_trust" or "zero_trust" in hop_types:
        tips.append({
            "type": "warning",
            "text": "零信任平台的 Token/证书有过期时间，请确保定期刷新"
        })
        tips.append({
            "type": "info",
            "text": "建议在零信任平台为 CI/CD 创建专用服务账号，而非使用个人账号"
        })

    # 零信任 + 堡垒机组合提示
    if "bastion" in hop_types and "zero_trust" in hop_types:
        tips.append({
            "type": "warning",
            "text": "零信任 + 堡垒机链路需双重配置，请确认每一跳的凭据和权限均已就绪"
        })

    # 隔离网络提示
    if relay.get("isolated") or network_access.get("isolated"):
        tips.append({
            "type": "info",
            "text": "隔离网络环境建议预先同步依赖包到内部仓库（如 Nexus/Harbor）"
        })

    # 工具部署位置提示
    if tool_deploy == "managed" and ("bastion" in hop_types or "zero_trust" in hop_types):
        tips.append({
            "type": "warning",
            "text": "云托管 CI/CD 可能无法直接访问隔离网络，建议配合中继服务器或 Runner"
        })

    # Docker 提示
    if deploy_mode == "build":
        tips.append({
            "type": "info",
            "text": "构建产物模式会自动生成 Dockerfile，目标服务器需安装 Docker"
        })

    # 前端项目提示
    if project_type in ("vue", "react"):
        tips.append({
            "type": "info",
            "text": "前端项目建议配合 Nginx 反向代理，配置 HTTPS 和 gzip 压缩"
        })

    # 多分支提示
    branches = config.get("branches", [])
    if len(branches) > 1:
        tips.append({
            "type": "info",
            "text": f"检测到 {len(branches)} 个分支，建议为每个分支分配独立端口或域名"
        })

    # Runner 提示
    if tool == "runner":
        tips.append({
            "type": "info",
            "text": "Runner 建议部署在目标服务器同网络，减少部署时的网络传输"
        })

    return tips
