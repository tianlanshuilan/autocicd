# CI/CD 流水线自动搭建平台

一键生成 CI/CD 流水线配置文件，支持多种主流流水线工具和项目类型。

## 功能特性

- **8 种流水线工具**：Jenkins、阿里云效、华为云 CodeArts、腾讯云 TKE、GitHub Actions、GitLab CI、TongWeb（东方通）、Runner（GitLab/GitHub）
- **6 种项目类型**：Java Maven、Java Gradle、Vue.js、React、Python、Go
- **3 种部署模式**：纯代码部署、代码+依赖（产成品）、含产物构建
- **多分支并行构建**：支持配置多个分支同时走流水线，各分支独立构建互不干扰
- **发布审批流程**：测试通过后审批确认，支持自动合并到主分支、拒绝合并、回滚到上一版本
- **自动生成 Dockerfile**：在「含产物构建」模式下自动生成多阶段 Dockerfile
- **自动搭建流水线**：输入仓库地址、服务器信息，一键自动完成全流程部署
- **智能部署建议**：根据项目类型、工具选择、网络环境自动推荐最佳部署方案
- **跨云/隔离网络部署**：支持中继服务器跳转，解决代码在阿里云、部署在首信云等隔离网络场景
- **TongWeb 支持**：支持东方通 TongWeb 应用服务器的配置生成和自动部署
- **Runner 部署**：自动生成 GitLab Runner / GitHub Actions Runner 安装脚本和配置
- **可视化操作界面**：Web 前端表单填写，实时预览生成结果
- **一键下载**：生成的配置文件可直接下载或复制

## 快速开始

### 环境要求

| 组件 | 版本要求 |
|------|----------|
| Python | >= 3.9 |
| Node.js | >= 18 |
| npm | >= 9 |

### 安装与启动

#### 1. 克隆项目

```bash
git clone <repo-url>
cd auto-cicd
```

#### 2. 启动后端

```bash
cd backend

# 安装依赖
pip3 install -r requirements.txt

# 启动服务（默认端口 8000）
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000

# 或者直接运行
python3 main.py
```

后端启动后访问 `http://localhost:8000`，API 文档访问 `http://localhost:8000/docs`。

#### 3. 启动前端

```bash
cd frontend

# 安装依赖
npm install

# 启动开发服务器（默认端口 3000）
npm run dev
```

前端启动后访问 `http://localhost:3000`。

#### 4. 打开浏览器

访问 `http://localhost:3000` 即可使用。

## 使用指南

### 第一步：选择流水线工具

在主界面顶部选择你使用的 CI/CD 工具：

| 工具 | 说明 | 生成文件 |
|------|------|----------|
| Jenkins | 开源 CI/CD，经典 Pipeline | `Jenkinsfile` + `README-Jenkins.md` + `rollback.sh` |
| 阿里云效 | 阿里 DevOps 平台 | `.aliyunxiao.yml` + `rollback.sh` |
| 华为云流水线 | 华为云 CodeArts | `.huaweicloud.yml` + `rollback.sh` |
| 腾讯云 TKE | 腾讯云 CI/CD | `.tencent.yml` + `rollback.sh` |
| GitHub Actions | GitHub 原生 CI/CD | `.github/workflows/ci.yml` + `deploy.yml` + `release.yml` |
| GitLab CI | GitLab 内置流水线 | `.gitlab-ci.yml` + `rollback.sh` |
| TongWeb | 东方通应用服务器 | `deploy-tongweb.sh` + `tongweb-web.xml` + `Jenkinsfile.tongweb` |
| Runner | GitLab/GitHub Runner | `setup-runner.sh` + `config.toml` + `README-Runner.md` |

### 第二步：选择项目类型

| 类型 | 适用场景 | 构建工具 |
|------|----------|----------|
| Java Maven | Spring Boot / Maven 项目 | `mvn` |
| Java Gradle | Gradle 构建的 Java 项目 | `gradle` |
| Vue.js | Vue 2 / Vue 3 前端项目 | `npm` |
| React | React / Next.js 前端项目 | `npm` |
| Python | Django / Flask / FastAPI | `pip` |
| Go | Golang 项目 | `go build` |

### 第三步：选择部署模式

| 模式 | 说明 | 适用场景 |
|------|------|----------|
| 纯代码部署 | 直接拉取源代码部署 | 解释型语言快速部署 |
| 代码+依赖 | 打包代码和依赖产物 | 需要离线部署的场景 |
| 含产物构建 | 完整构建→测试→部署流程 | 生产环境标准流程，自动生成 Dockerfile |

### 第四步：填写项目信息

- **项目仓库 URL**：Git 仓库地址，如 `https://github.com/owner/repo`
- **项目名**：用于命名生成的配置文件和输出目录
- **分支**：要部署的分支，支持多分支并行构建
  - 点击「+ 添加分支」可添加更多分支
  - 多分支时各工具会生成并行构建配置
  - 例如：`main`、`develop`、`feature/xxx` 可同时构建
- **发布策略**（多分支时显示）：
  - **自动合并**：测试通过后自动合并到主分支
  - **手动合并**：测试通过后需手动确认是否合并
  - **不合并**：仅测试，不合并到主分支
- **主分支**：指定合并的目标分支，默认 `main`
- **启用回滚**：开启后支持回滚到上一稳定版本
- **端口号**：应用运行端口，默认 `8080`
- **JDK 版本**：Java 项目选择（8 / 11 / 17 / 21）
- **Node 版本**：前端项目选择（18 / 20 / 22）

#### 多分支并行构建说明

当配置多个分支时，各工具会生成不同的并行构建配置：

| 工具 | 多分支处理方式 |
|------|----------------|
| Jenkins | 生成 `parallel` 并行阶段，每个分支独立执行 |
| GitHub Actions | 使用 `matrix` 策略并行构建所有分支 |
| GitLab CI | 为每个分支生成独立的 job（build_xxx, test_xxx, deploy_xxx） |
| 阿里云效/华为云/腾讯云 | 添加 `triggers` 分支触发规则，推送任意分支自动触发 |
| TongWeb | 多分支并行部署到不同目录 |

**使用场景**：
- 多人协作开发，各分支独立测试
- 分支 A 的开发者测试 A 分支，分支 B 的开发者测试 B 分支
- 所有分支同时走流水线部署，互不影响

#### 多分支发布流程

配置多分支后，可选择发布策略来控制测试通过后的行为：

```
功能分支开发 → 提交代码 → 流水线测试 → 部署测试环境
                                         ↓
                                    审批确认弹窗
                                   /     |     \
                              合并   拒绝   回滚
                               ↓       ↓       ↓
                          合并到主分支  不合并  回滚到上一版本
```

**三种发布策略**：

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| 自动合并 | 测试通过后自动合并到主分支 | 快速迭代，信任测试覆盖 |
| 手动合并 | 测试通过后弹窗确认，可选择合并/拒绝/回滚 | 需要人工审核的生产发布 |
| 不合并 | 仅测试，不执行合并操作 | 仅做 CI 验证，不发布 |

**审批确认**：自动搭建模式下，部署到测试环境后会弹出审批对话框，可选择：
- ✅ **确认合并到主分支**：将测试通过的分支合并到主分支并打版本标签
- ❌ **拒绝合并**：不合并，分支保留但不影响主分支
- ↩️ **回滚到上一版本**：回滚到上一个稳定版本标签

**回滚机制**：每次合并会自动打版本标签（如 `v20260810120000`），回滚时自动查找上一个稳定版本并切换。项目根目录会生成 `rollback.sh` 脚本，支持手动回滚。

#### 智能部署建议

在自动搭建模式下，填写目标服务器信息后可点击「获取智能部署建议」，系统会根据配置自动分析并推荐：

- **CI/CD 服务器部署位置**：根据所选工具推荐最佳部署位置（如 Jenkins 建议与代码仓库同云）
- **部署方式建议**：Docker 容器部署 vs 直接部署，含优缺点对比
- **网络方案建议**：根据网络环境（同云/跨云/隔离网络）推荐网络连接方案
- **额外提示**：根据项目类型和配置给出注意事项

#### 跨云/隔离网络部署

对于代码仓库和目标服务器不在同一网络的场景（如代码在阿里云，部署在首信云），平台支持通过**中继服务器**实现自动化部署：

```
代码仓库（阿里云）
      ↓
中继服务器（可同时访问两个网络）
      ↓
目标服务器（首信云/隔离网络）
```

**配置方法**：
1. 在「目标服务器」部分填写实际部署服务器信息
2. 勾选「使用中继服务器」
3. 填写中继服务器地址和凭据
4. 勾选「目标网络为隔离网络」（如适用）

**工作原理**：
- 引擎先 SSH 连接到中继服务器
- 通过中继服务器的 SSH Transport 建立隧道
- 通过隧道连接目标服务器执行部署操作

**典型场景**：

| 场景 | 代码/依赖位置 | 部署目标 | 解决方案 |
|------|--------------|----------|----------|
| 跨云部署 | 阿里云 CodeUp | 华为云 ECS | 中继服务器或云联网 |
| 信创隔离网络 | 阿里云 | 首信云 | 中继服务器 + 离线包传输 |
| 混合云 | GitHub | 内网服务器 | Self-hosted Runner 或中继 |
| 完全隔离 | 内网 Gitea | 隔离网络 | 内部完整 CI/CD 环境 |

**隔离网络环境额外建议**：
- 预先同步依赖包到内部仓库（如 Nexus/Harbor）
- 中继服务器建议使用专用 SSH 密钥对
- 考虑在隔离网络内部署独立的代码仓库镜像

### 第五步：生成配置

点击「生成配置」按钮，右侧预览面板将展示生成的文件内容：

- 点击文件名切换查看不同配置文件
- 点击「下载全部」逐个下载所有文件
- 点击「复制全部」复制当前文件内容
- 底部显示文件输出路径，可复制

## 生成文件说明

### Jenkins

```
├── Jenkinsfile          # Pipeline 定义（多分支时含审批/合并/回滚阶段）
├── Dockerfile           # 多阶段构建（仅 build 模式）
├── .dockerignore        # Docker 忽略文件
├── rollback.sh          # 回滚脚本（多分支时生成）
├── README-Release.md    # 发布流程说明（多分支时生成）
└── pom.xml / package.json / ...  # 项目基础配置
```

### GitHub Actions

```
├── .github/
│   └── workflows/
│       ├── ci.yml       # CI 流水线（构建+测试）
│       ├── deploy.yml   # 部署流水线（CI 成功后触发）
│       └── release.yml  # 发布流水线（审批+合并+回滚，多分支时生成）
├── Dockerfile           # 多阶段构建（仅 build 模式）
├── .dockerignore
├── rollback.sh          # 回滚脚本（多分支时生成）
└── README-Release.md    # 发布流程说明（多分支时生成）
```

### GitLab CI

```
├── .gitlab-ci.yml       # 完整 Pipeline（build → test → deploy，多分支时含审批/合并/回滚）
├── Dockerfile           # 多阶段构建（仅 build 模式）
├── .dockerignore
├── rollback.sh          # 回滚脚本（多分支时生成）
└── README-Release.md    # 发布流程说明（多分支时生成）
```

### 阿里云效 / 华为云 / 腾讯云

```
├── .xxx.yml             # 流水线配置（stages: 构建 → 测试 → 部署）
├── Dockerfile           # 多阶段构建（仅 build 模式）
├── .dockerignore
├── README.md            # 配置说明
├── rollback.sh          # 回滚脚本（多分支时生成）
└── README-Release.md    # 发布流程说明（多分支时生成）
```

## API 接口

### 获取支持的工具和项目类型

```
GET /api/tools
```

响应示例：

```json
{
  "tools": ["jenkins", "aliyun", "huawei", "tencent", "github", "gitlab", "tongweb", "runner"],
  "types": ["java-maven", "java-gradle", "vue", "react", "python", "go"]
}
```

### 生成流水线配置文件

```
POST /api/generate-files
Content-Type: application/json
```

请求参数：

```json
{
  "tool": "jenkins",
  "projectType": "java-maven",
  "repoUrl": "https://github.com/owner/repo",
  "projectName": "my-app",
  "branch": "main",
  "branches": ["main", "develop", "feature/test"],
  "port": 8080,
  "jdkVersion": "17",
  "nodeVersion": "20",
  "releaseStrategy": {
    "strategy": "auto_merge",
    "mainBranch": "main",
    "enableRollback": true,
    "requireApproval": true
  }
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| tool | string | 是 | 流水线工具，可选值见上表 |
| projectType | string | 是 | 项目类型，可选值见上表 |
| repoUrl | string | 是 | 代码仓库地址 |
| projectName | string | 是 | 项目名称 |
| branch | string | 否 | 主分支（兼容旧版本），默认 `main` |
| branches | string[] | 否 | 多分支列表，支持并行构建 |
| port | int | 是 | 应用端口 |
| jdkVersion | string | 否 | JDK 版本，Java 项目填写 |
| nodeVersion | string | 否 | Node 版本，前端项目填写 |
| releaseStrategy | object | 否 | 发布策略配置（多分支时生效） |

**releaseStrategy 字段说明**：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| strategy | string | `auto_merge` | 发布策略：`auto_merge` / `manual_merge` / `no_merge` |
| mainBranch | string | `main` | 合并目标主分支 |
| enableRollback | bool | `true` | 是否启用回滚 |
| requireApproval | bool | `true` | 是否需要审批确认 |

响应示例：

```json
{
  "files": [
    { "name": "Jenkinsfile", "content": "..." },
    { "name": "Dockerfile", "content": "..." }
  ],
  "outputDir": "/path/to/output/my-app_jenkins_20260809120000",
  "tool": "jenkins",
  "projectName": "my-app"
}
```

### 获取智能部署建议

```
POST /api/recommendations
Content-Type: application/json
```

请求参数与 `/api/generate-files` 相同，额外支持 `server` 和 `relayServer` 字段。

响应示例：

```json
{
  "server": {
    "recommendations": [
      { "location": "与代码仓库同云", "reason": "...", "priority": "high" }
    ],
    "bestPractice": "建议将 Jenkins 部署在与代码仓库同一网络"
  },
  "deployMethod": {
    "recommendations": [
      { "method": "Docker 容器部署", "recommended": true, "pros": [...], "cons": [...] }
    ],
    "defaultChoice": "docker"
  },
  "network": {
    "scenario": "cross_cloud",
    "scenarioName": "跨云部署",
    "recommendations": [
      { "scheme": "云联网/专线", "description": "...", "steps": [...], "recommended": true }
    ]
  },
  "scenarios": [...],
  "tips": [...]
}
```

## 项目结构

```
auto-cicd/
├── backend/                    # 后端服务（FastAPI）
│   ├── generators/             # 配置生成器
│   │   ├── __init__.py
│   │   ├── jenkins.py          # Jenkins 配置生成
│   │   ├── aliyun.py           # 阿里云效配置生成
│   │   ├── huawei.py           # 华为云 CodeArts 配置生成
│   │   ├── tencent.py           # 腾讯云 TKE 配置生成
│   │   ├── github.py           # GitHub Actions 配置生成
│   │   ├── gitlab.py           # GitLab CI 配置生成
│   │   ├── tongweb.py          # 东方通 TongWeb 配置生成
│   │   ├── runner.py           # GitLab/GitHub Runner 配置生成
│   │   └── workflow.py         # 多分支发布流程工具（审批/合并/回滚）
│   ├── recommendations.py    # 智能部署建议引擎
│   ├── pipeline/              # 自动化编排引擎
│   │   ├── engine.py           # 编排引擎
│   │   ├── git_ops.py          # Git 操作
│   │   ├── ssh_ops.py          # SSH 远程操作
│   │   └── credential.py       # 凭据管理
│   ├── main.py                 # FastAPI 应用入口
│   └── requirements.txt        # Python 依赖
├── frontend/                   # 前端应用（Vue 3 + Vite）
│   ├── src/
│   │   ├── api/
│   │   │   └── index.js        # API 请求封装
│   │   ├── views/
│   │   │   └── MainView.vue    # 主界面
│   │   ├── App.vue             # 根组件
│   │   └── main.js             # 入口文件
│   ├── index.html
│   ├── package.json
│   └── vite.config.js          # Vite 配置（含 API 代理）
├── output/                     # 生成的配置文件输出目录
└── 项目.md                      # 需求文档
```

## 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Vue 3 + Vite |
| 后端 | Python FastAPI + Uvicorn |
| 配置生成 | Python 模板字符串 |
| 自动部署 | Paramiko (SSH) + Git CLI |
| 实时通信 | WebSocket |
| 数据模型 | Pydantic |

## 常见问题

### Q: 生成的文件如何使用？

将生成的配置文件复制到你的项目根目录对应位置即可。例如：
- Jenkins：将 `Jenkinsfile` 放到项目根目录
- GitHub Actions：将 `.github/workflows/` 目录放到项目根目录
- GitLab CI：将 `.gitlab-ci.yml` 放到项目根目录

### Q: Dockerfile 什么时候生成？

仅在「含产物构建」模式下自动生成 Dockerfile。该模式提供完整的多阶段构建，包含构建、测试和部署三个阶段。

### Q: 如何添加自定义的流水线工具？

在 `backend/generators/` 目录下新建 Python 文件，实现 `generate_xxx(config, output_dir)` 函数，返回文件列表。然后在 `main.py` 中注册即可。

### Q: TongWeb 是什么？

TongWeb（东方通）是国产 Java EE 应用服务器，广泛用政信创环境。选择 TongWeb 工具会生成：
- `deploy-tongweb.sh`：一键部署脚本
- `tongweb-web.xml`：应用部署描述文件
- `Jenkinsfile.tongweb`：Jenkins 流水线（TongWeb 专用）
- `README-TongWeb.md`：详细部署说明

### Q: Runner 工具生成什么？

选择 Runner 会生成 Self-hosted Runner 的安装和配置脚本：
- `setup-runner.sh`：GitLab Runner 自动安装注册脚本
- `setup-github-runner.sh`：GitHub Actions Runner 安装脚本
- `config.toml`：GitLab Runner 配置模板
- `gitlab-runner.service`：systemd 服务文件
- `README-Runner.md`：Runner 部署说明

### Q: 前端开发服务器无法连接后端？

确认后端运行在 `http://localhost:8000`，前端 Vite 配置中已设置 `/api` 代理到后端。开发时使用 `npm run dev` 启动前端。

### Q: 多分支并行构建如何使用？

在「项目信息」部分，点击「+ 添加分支」可添加多个分支。例如：
- 分支 1：`main`
- 分支 2：`develop`
- 分支 3：`feature/user-login`

生成配置时，各工具会自动生成多分支并行构建的配置：
- **Jenkins**：生成 `parallel` 块，每个分支独立执行构建/测试/部署
- **GitHub Actions**：使用 `matrix` 策略，每个分支作为一个 job 并行运行
- **GitLab CI**：为每个分支生成独立的 job（如 `build_main`、`build_develop`）

自动搭建时，多个分支会并行部署到服务器的不同目录（如 `/opt/apps/main`、`/opt/apps/develop`）。

### Q: 多分支部署时端口冲突怎么办？

多分支部署时，每个分支会使用不同的部署目录，但默认使用相同的端口。如果需要同时运行多个分支，建议：
1. 为不同分支配置不同的端口
2. 或者只部署一个主分支，其他分支仅做 CI 测试

### Q: 发布审批流程如何工作？

配置多分支并选择发布策略后，自动搭建模式下的完整流程：

1. **克隆代码**：拉取所有配置分支的代码
2. **生成配置**：生成含审批/合并/回滚阶段的流水线配置
3. **部署测试**：将各分支部署到测试环境
4. **审批确认**：弹出审批对话框，可选择：
   - ✅ 确认合并到主分支
   - ❌ 拒绝合并
   - ↩️ 回滚到上一版本
5. **执行操作**：根据选择执行合并、拒绝或回滚

生成的配置文件会自动包含审批门禁：
- Jenkins 使用 `input` 步骤暂停等待人工确认
- GitHub Actions 使用 Environment 保护规则
- GitLab CI 使用 `when: manual` 手动触发

### Q: 回滚脚本如何使用？

多分支配置时会自动生成 `rollback.sh` 脚本，使用方法：

```bash
chmod +x rollback.sh
./rollback.sh
```

脚本会列出最近的版本标签，输入要回滚的目标版本即可。回滚前会自动创建备份标签，可随时恢复。

### Q: 代码在阿里云，部署在首信云，如何实现自动化流水线？

这是典型的跨云/隔离网络场景。解决方案：

1. **准备中继服务器**：找一台同时能访问阿里云和首信云的服务器作为中继（可以是 VPN 网关、跳板机或 DMZ 区域的机器）
2. **配置中继**：在前端「目标服务器」部分勾选「使用中继服务器」，填写中继服务器地址和凭据
3. **勾选隔离网络**：如果首信云是网络隔离的，勾选「目标网络为隔离网络」
4. **同步依赖**：建议预先将 Maven/npm 依赖同步到首信云内部的 Nexus/Harbor 仓库
5. **开始搭建**：系统会自动通过中继服务器跳转，在首信云上完成部署

```
阿里云（代码仓库）
      ↓
中继服务器（DMZ/VPN）
      ↓
首信云（目标服务器，网络隔离）
```

### Q: Runner/Jenkins 应该部署在哪里？

根据场景推荐：

| 场景 | 推荐部署位置 | 原因 |
|------|--------------|------|
| 代码在 GitHub | GitHub-hosted Runner（免费） | 无需自建，需要内网时再自建 |
| 代码在 GitLab | Runner 与 GitLab Server 同网络 | 通信延迟最低 |
| 代码在阿里云，部署在阿里云 | 同区域 ECS | 内网通信，速度最快 |
| 代码在阿里云，部署在首信云 | 中继服务器或首信云内部 | 需要跨网络访问 |
| 多分支并行构建 | 与目标服务器同网络 | 减少部署时网络传输 |

### Q: Docker 部署和直接部署怎么选？

| 项目类型 | 推荐方式 | 原因 |
|----------|----------|------|
| Java Maven/Gradle | Docker 容器 | 环境一致，易于回滚和扩缩容 |
| Python | Docker 容器 | 依赖管理简单，避免环境冲突 |
| Go | Docker 或直接部署 | Go 编译为单二进制，两种方式都简单 |
| Vue/React | Nginx + 静态文件 | 前端构建后为静态文件，Nginx 直接托管最高效 |

「含产物构建」模式会自动生成 Dockerfile，推荐使用 Docker 部署。目标服务器需预装 Docker。

### Q: 智能部署建议如何工作？

在自动搭建模式下填写目标服务器地址后，点击「获取智能部署建议」，系统会分析：

1. **服务器位置建议**：根据所选工具（Jenkins/GitHub/GitLab 等）推荐最佳部署位置
2. **部署方式建议**：根据项目类型推荐 Docker 或直接部署，含优缺点对比
3. **网络方案建议**：检测是否跨云/隔离网络，推荐对应的网络连接方案
4. **额外提示**：根据配置给出注意事项（如多分支端口分配、依赖同步等）
