<template>
  <div class="container">
    <div class="header-banner">
      <header class="header">
        <div class="logo">⚡ CI/CD 流水线自动搭建平台</div>
        <p class="subtitle">选择工具、填写信息，一键生成配置或自动搭建流水线</p>
      </header>

      <!-- ========== 表单页 ========== -->
      <div class="form-page" v-if="page === 'form'">
        <!-- 模式切换 -->
        <div class="mode-switch">
        <div class="mode-btn-wrap">
          <button :class="{ active: mode === 'generate' }" @click="mode = 'generate'">仅生成配置</button>
          <div class="mode-tooltip">
            <div class="mode-tooltip-title">📄 仅生成配置</div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 功能</span>
              <span>根据所选工具和项目类型，自动生成 CI/CD 配置文件（Jenkinsfile、.gitlab-ci.yml 等）</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 适用场景</span>
              <span>已有服务器环境，只需生成流水线配置文件，手动部署或导入到现有系统</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 需提供</span>
              <span>仓库地址、项目类型、分支信息</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">🔒 安全性</span>
              <span>纯本地生成，不连接任何远程服务器，无需提供服务器凭据，代码不离开本机</span>
            </div>
          </div>
        </div>
        <div class="mode-btn-wrap">
          <button :class="{ active: mode === 'auto' }" @click="mode = 'auto'">自动搭建流水线</button>
          <div class="mode-tooltip">
            <div class="mode-tooltip-title">🚀 自动搭建流水线</div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 功能</span>
              <span>全自动完成：克隆仓库 → 生成配置 → 推送代码 → 连接服务器 → 环境初始化 → 部署启动</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 适用场景</span>
              <span>从零搭建完整 CI/CD 流水线，包含代码管理、配置生成、服务器部署全流程</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">✦ 需提供</span>
              <span>仓库地址 + Git 凭据、目标服务器 + SSH 凭据、隔离网络时可选中继服务器</span>
            </div>
            <div class="mode-tooltip-section">
              <span class="tooltip-label">🔒 安全性</span>
              <span>凭据通过 WebSocket 实时传输，仅在内存中暂存不落盘；支持中继服务器方案适配隔离网络环境</span>
            </div>
          </div>
        </div>
        <!-- 执行按钮 -->
        <button class="execute-btn" :class="{ active: canExecute }" :disabled="!canExecute" @click="executeAction">
          {{ mode === 'generate' ? '📄 生成配置' : '🚀 开始搭建' }}
        </button>
        </div>
      </div>
      </div>

      <!-- ========== 表单页 ========== -->
      <div class="form-page" v-if="page === 'form'">
      <div class="form-panel">
        <h2>配置流水线</h2>

        <!-- Step 1: Pipeline Tool -->
        <section class="section">
          <h3>1. 流水线工具</h3>
          <div class="tool-grid">
            <div
              v-for="tool in tools"
              :key="tool.id"
              class="tool-card"
              :class="{ active: form.tool === tool.id }"
              @click="form.tool = tool.id"
            >
              <div class="tool-icon">{{ tool.icon }}</div>
              <div class="tool-name">{{ tool.name }}</div>
              <div class="tool-desc">{{ tool.desc }}</div>
              <div class="tool-tooltip">
                <div class="tooltip-section">
                  <span class="tooltip-label">✦ 特点</span>
                  <span>{{ tool.features }}</span>
                </div>
                <div class="tooltip-section">
                  <span class="tooltip-label">✦ 适用</span>
                  <span>{{ tool.suitable }}</span>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Step 2: Project Type -->
        <section class="section">
          <h3>2. 项目类型</h3>
          <div class="type-grid">
            <div
              v-for="type in projectTypes"
              :key="type.id"
              class="type-card"
              :class="{ active: form.projectType === type.id }"
              @click="form.projectType = type.id"
            >
              <div class="type-icon">{{ type.icon }}</div>
              <div class="type-name">{{ type.name }}</div>
              <div class="type-langs">{{ type.langs }}</div>
            </div>
          </div>
        </section>

        <!-- Step 3: Deploy Method -->
        <section class="section">
          <h3>3. 部署方式</h3>
          <div class="mode-list">
            <label class="mode-item" :class="{ active: form.deployMethod === 'docker' }">
              <input type="radio" v-model="form.deployMethod" value="docker" />
              <div class="mode-text">
                <span class="mode-label">🐳 Docker 部署</span>
                <span class="mode-desc">容器化运行，环境一致性好，适合后端服务</span>
              </div>
            </label>
            <label class="mode-item" :class="{ active: form.deployMethod === 'direct' }">
              <input type="radio" v-model="form.deployMethod" value="direct" />
              <div class="mode-text">
                <span class="mode-label">📁 直接部署</span>
                <span class="mode-desc">直接运行在服务器上，简单轻量，适合前端静态资源</span>
              </div>
            </label>
            <label class="mode-item" :class="{ active: form.deployMethod === 'app_server' }" v-if="isJavaProject">
              <input type="radio" v-model="form.deployMethod" value="app_server" />
              <div class="mode-text">
                <span class="mode-label">🏛️ 应用服务器</span>
                <span class="mode-desc">部署到 TongWeb / Tomcat 等 Java 应用服务器，WAR 包方式</span>
              </div>
            </label>
          </div>

          <!-- 应用服务器子选项 -->
          <div class="sub-config" v-if="form.deployMethod === 'app_server'">
            <div class="app-server-row">
              <div class="form-group">
                <label>应用服务器类型</label>
                <select v-model="form.appServer.type">
                  <option value="tongweb">TongWeb（东方通）</option>
                  <option value="tomcat">Apache Tomcat</option>
                </select>
              </div>
              <div class="form-group">
                <label>安装路径</label>
                <input v-model="form.appServer.home" :placeholder="form.appServer.type === 'tongweb' ? '/opt/TongWeb7.0' : '/opt/tomcat'" />
              </div>
              <div class="form-group">
                <label>HTTP 端口</label>
                <input v-model.number="form.appServer.port" type="number" placeholder="9060" />
              </div>
              <div class="form-group">
                <label>应用上下文路径</label>
                <input v-model="form.appServer.contextPath" placeholder="/app" />
              </div>
            </div>
          </div>
        </section>

        <!-- Step 4: Details (generate mode only) -->
        <section class="section" v-if="mode === 'generate'">
          <h3>4. 项目信息</h3>
          <div class="form-group">
            <label>代码仓库地址</label>
            <input v-model="form.repoUrl" placeholder="https://github.com/owner/repo.git" />
          </div>

          <!-- 默认分支 -->
          <div class="form-group">
            <label>
              默认分支
              <span class="branch-hint">搭建完成后选择需要集成的分支</span>
            </label>
            <input v-model="form.branch" placeholder="main" />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label>端口号</label>
              <input v-model.number="form.port" type="number" placeholder="8080" />
            </div>
            <div class="form-group">
              <label>JDK 版本</label>
              <select v-model="form.jdkVersion">
                <option value="">不适用</option>
                <option value="8">Java 8</option>
                <option value="11">Java 11</option>
                <option value="17">Java 17</option>
                <option value="21">Java 21</option>
              </select>
            </div>
          </div>
          <div class="form-group" v-if="form.projectType === 'vue' || form.projectType === 'react'">
            <label>Node 版本</label>
            <select v-model="form.nodeVersion">
              <option value="18">Node 18</option>
              <option value="20">Node 20</option>
              <option value="22">Node 22</option>
            </select>
          </div>
        </section>

        <!-- 自动搭建模式额外表单 -->
        <template v-if="mode === 'auto'">
          <!-- 三栏布局：项目信息+Git认证 | 目标服务器 | 网络访问链路 -->
          <div class="auto-info-row">
            <!-- 左侧：项目信息 + Git 认证 -->
            <section class="section auto-info-col auto-info-left">
              <h3>4. 项目信息</h3>
              <div class="form-group">
                <label>代码仓库地址</label>
                <input v-model="form.repoUrl" placeholder="https://github.com/owner/repo.git" />
              </div>
              <div class="form-group">
                <label>
                  默认分支
                  <span class="branch-hint">搭建完成后选择需要集成的分支</span>
                </label>
                <input v-model="form.branch" placeholder="main" />
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>端口号</label>
                  <input v-model.number="form.port" type="number" placeholder="8080" />
                </div>
                <div class="form-group">
                  <label>JDK 版本</label>
                  <select v-model="form.jdkVersion">
                    <option value="">不适用</option>
                    <option value="8">Java 8</option>
                    <option value="11">Java 11</option>
                    <option value="17">Java 17</option>
                    <option value="21">Java 21</option>
                  </select>
                </div>
              </div>
              <div class="form-group" v-if="form.projectType === 'vue' || form.projectType === 'react'">
                <label>Node 版本</label>
                <select v-model="form.nodeVersion">
                  <option value="18">Node 18</option>
                  <option value="20">Node 20</option>
                  <option value="22">Node 22</option>
                </select>
              </div>

              <h3 style="margin-top: 20px;">5. Git 认证信息</h3>
              <div class="form-group">
                <label>认证方式</label>
                <select v-model="form.gitAuth.type">
                  <option value="password">用户名 + 密码</option>
                  <option value="ssh_key">SSH 密钥</option>
                </select>
              </div>
              <div class="form-group">
                <label>用户名</label>
                <input v-model="form.gitAuth.username" placeholder="Git 用户名" />
              </div>
              <div class="form-group" v-if="form.gitAuth.type === 'password'">
                <label>密码 / Token</label>
                <input v-model="form.gitAuth.password" type="password" placeholder="可留空，执行时弹窗输入" />
              </div>
              <div class="form-group" v-if="form.gitAuth.type === 'ssh_key'">
                <label>SSH 私钥</label>
                <textarea v-model="form.gitAuth.sshKey" rows="3" placeholder="粘贴 SSH 私钥内容，可留空执行时弹窗输入"></textarea>
              </div>
            </section>

            <!-- 中间：目标服务器 -->
            <section class="section auto-info-col auto-info-middle">
              <h3>6. 目标服务器</h3>
              <div class="form-row">
                <div class="form-group">
                  <label>服务器地址</label>
                  <input v-model="form.server.host" placeholder="192.168.1.100" />
                </div>
                <div class="form-group">
                  <label>SSH 端口</label>
                  <input v-model.number="form.server.port" type="number" placeholder="22" />
                </div>
              </div>
              <div class="form-group">
                <label>用户名</label>
                <input v-model="form.server.username" placeholder="root" />
              </div>
              <div class="form-group">
                <label>认证方式</label>
                <select v-model="form.server.authType">
                  <option value="password">密码</option>
                  <option value="ssh_key">SSH 密钥</option>
                </select>
              </div>
              <div class="form-group" v-if="form.server.authType === 'password'">
                <label>密码</label>
                <input v-model="form.server.password" type="password" placeholder="可留空，执行时弹窗输入" />
                <small class="form-hint" style="color: #e67e22;">
                  ⚠️ 密码认证需要目标服务器安装 sshpass，建议生产环境使用 SSH 密钥认证
                </small>
              </div>
              <div class="form-group" v-if="form.server.authType === 'ssh_key'">
                <label>SSH 私钥</label>
                <textarea v-model="form.server.sshKey" rows="3" placeholder="粘贴 SSH 私钥内容"></textarea>
              </div>
              <div class="form-group" v-if="form.deployMethod !== 'docker'">
                <label>部署路径</label>
                <input v-model="form.server.deployPath" placeholder="/opt/apps" />
              </div>
              <div class="form-group backup-option">
                <label class="checkbox-label">
                  <input type="checkbox" v-model="form.server.backupBeforeDeploy" />
                  <span class="checkmark"></span>
                  <span class="check-text">
                    <span class="check-title">部署前备份旧版本</span>
                    <span class="check-desc">部署前将服务器上的旧版本包备份到 backup 目录，便于回滚</span>
                  </span>
                </label>
              </div>
              <div class="form-group backup-option">
                <label class="checkbox-label">
                  <input type="checkbox" v-model="form.useChinaMirror" />
                  <span class="checkmark"></span>
                  <span class="check-text">
                    <span class="check-title">使用国内镜像源</span>
                    <span class="check-desc">适用于国产操作系统（麒麟、统信）或国内网络环境，加速 Jenkins/Docker 等工具安装</span>
                  </span>
                </label>
              </div>

              <!-- 依赖仓库配置 -->
              <div class="form-group">
                <label class="section-label">
                  <span>📦 依赖仓库（可选）</span>
                  <span class="section-hint">独立的依赖代码仓库，存放项目所需的离线依赖文件</span>
                </label>
                <input v-model="form.dependencyRepo.url" placeholder="依赖仓库地址，如 git@github.com:org/project-deps.git" />
                <div class="form-row" v-if="form.dependencyRepo.url">
                  <div class="form-group">
                    <label>分支</label>
                    <input v-model="form.dependencyRepo.branch" placeholder="main" />
                  </div>
                  <div class="form-group">
                    <label>认证方式</label>
                    <select v-model="form.dependencyRepo.authType">
                      <option value="password">密码</option>
                      <option value="sshKey">SSH 密钥</option>
                    </select>
                  </div>
                </div>
                <div class="form-row" v-if="form.dependencyRepo.url && form.dependencyRepo.authType === 'password'">
                  <div class="form-group">
                    <label>用户名</label>
                    <input v-model="form.dependencyRepo.username" placeholder="git 用户名" />
                  </div>
                  <div class="form-group">
                    <label>密码/Token</label>
                    <input v-model="form.dependencyRepo.password" type="password" placeholder="可留空，执行时弹窗输入" />
                  </div>
                </div>
                <div class="form-group" v-if="form.dependencyRepo.url && form.dependencyRepo.authType === 'sshKey'">
                  <label>SSH 私钥</label>
                  <textarea v-model="form.dependencyRepo.sshKey" rows="3" placeholder="粘贴 SSH 私钥内容"></textarea>
                </div>
              </div>

              <!-- 流水线模式 -->
              <div class="form-group">
                <label class="section-label">
                  <span>🔀 流水线模式</span>
                  <span class="section-hint">发布模式部署验证后合并主分支；集成测试模式将功能分支临时合入环境分支测试，不合主干</span>
                </label>
                <select v-model="form.pipelineMode">
                  <option value="release">发布模式（部署后合并到主分支）</option>
                  <option value="integration">集成测试模式（多分支临时集成，不合入主干）</option>
                </select>
              </div>

              <!-- 多环境配置 -->
              <div class="form-group">
                <label class="section-label">
                  <span>🌍 多环境部署（可选）</span>
                  <span class="section-hint">每个环境对应一个集成分支与独立服务器{{ form.pipelineMode === 'integration' ? '，第一个环境为集成目标' : '' }}</span>
                </label>
                <div class="env-item" v-for="(env, i) in form.environments" :key="i">
                  <div class="env-item-head">
                    <input v-model="env.name" placeholder="环境名，如 dev / test / staging" class="env-name" />
                    <input v-model="env.branch" placeholder="集成分支，如 env/dev" class="env-branch" />
                    <button class="btn-remove-env" @click="removeEnvironment(i)" title="删除环境">&times;</button>
                  </div>
                  <div class="env-item-server">
                    <input v-model="env.server.host" placeholder="环境服务器地址" />
                    <input v-model="env.server.username" placeholder="root" class="env-small" />
                    <input v-model="env.server.password" type="password" placeholder="密码（可留空）" class="env-small" />
                  </div>
                </div>
                <button class="btn-add-hop" @click="addEnvironment">+ 添加环境</button>
              </div>

              <!-- 负载均衡 -->
              <div class="form-group">
                <label class="section-label">
                  <span>⚖️ 负载均衡（可选）</span>
                  <span class="section-hint">多后端服务器 + Nginx 负载均衡，流水线滚动部署（逐台部署 + 健康检查，服务不中断）</span>
                </label>
                <label class="checkbox-label">
                  <input type="checkbox" v-model="form.loadBalancer.enabled" />
                  <span class="checkmark"></span>
                  <span class="check-text">
                    <span class="check-title">启用负载均衡部署</span>
                  </span>
                </label>
                <div v-if="form.loadBalancer.enabled" class="lb-config">
                  <div class="form-row">
                    <div class="form-group">
                      <label>LB 服务器地址</label>
                      <input v-model="form.loadBalancer.host" placeholder="192.168.1.1" />
                    </div>
                    <div class="form-group">
                      <label>对外监听端口</label>
                      <input v-model.number="form.loadBalancer.listenPort" type="number" placeholder="80" />
                    </div>
                  </div>
                  <div class="form-row">
                    <div class="form-group">
                      <label>用户名</label>
                      <input v-model="form.loadBalancer.username" placeholder="root" />
                    </div>
                    <div class="form-group">
                      <label>密码</label>
                      <input v-model="form.loadBalancer.password" type="password" placeholder="可留空，执行时弹窗输入" />
                    </div>
                  </div>
                  <div class="form-row">
                    <div class="form-group">
                      <label>健康检查路径</label>
                      <input v-model="form.loadBalancer.healthCheckPath" placeholder="/" />
                    </div>
                    <div class="form-group">
                      <label>健康检查重试次数</label>
                      <input v-model.number="form.loadBalancer.healthCheckRetries" type="number" placeholder="6" />
                    </div>
                  </div>
                  <label class="section-label"><span>后端服务器</span></label>
                  <div class="env-item" v-for="(s, i) in form.loadBalancer.servers" :key="i">
                    <div class="env-item-server">
                      <input v-model="s.host" placeholder="后端服务器地址" />
                      <input v-model="s.username" placeholder="root" class="env-small" />
                      <input v-model="s.deployPath" placeholder="/opt/apps" class="env-small" />
                      <button class="btn-remove-env" @click="form.loadBalancer.servers.splice(i, 1)" title="删除服务器">&times;</button>
                    </div>
                  </div>
                  <button class="btn-add-hop" @click="addLbServer">+ 添加后端服务器</button>
                </div>
              </div>
            </section>

            <!-- 右侧：网络访问链路 -->
            <section class="section auto-info-col auto-info-right">
              <h3>7. 网络访问链路</h3>

              <!-- 添加跳转按钮 -->
              <div class="hop-actions">
                <button class="btn-add-hop" @click="addHop('relay')">+ 中继服务器</button>
                <button class="btn-add-hop" @click="addHop('bastion')">+ 堡垒机</button>
                <button class="btn-add-hop" @click="addHop('zero_trust')">+ 零信任/VPN</button>
              </div>

              <!-- 选项卡导航 -->
              <div class="hop-tabs" v-if="form.networkAccess.hops.length > 0">
                <div
                  class="hop-tab"
                  v-for="(hop, index) in form.networkAccess.hops"
                  :key="index"
                  :class="{ active: activeHopIndex === index }"
                  @click="activeHopIndex = index"
                >
                  <span class="hop-tab-icon">{{ hop.type === 'relay' ? '🔗' : hop.type === 'bastion' ? '🛡️' : '🔐' }}</span>
                  <span class="hop-tab-label">第 {{ index + 1 }} 跳</span>
                  <button class="hop-tab-close" @click.stop="removeHop(index)">&times;</button>
                </div>
              </div>

              <!-- 当前选项卡的配置 -->
              <div class="hop-content" v-if="form.networkAccess.hops.length > 0 && activeHopIndex < form.networkAccess.hops.length">
                <div class="hop-item">
                  <!-- 跳类型选择 -->
                  <div class="form-group">
                    <label>类型</label>
                    <select v-model="form.networkAccess.hops[activeHopIndex].type">
                      <option value="relay">🔗 中继服务器（跨云跳转）</option>
                      <option value="bastion">🛡️ 堡垒机（安全审计通道）</option>
                      <option value="zero_trust">🔐 零信任/VPN 网关</option>
                    </select>
                  </div>

                  <!-- 通用字段 -->
                  <div class="form-row">
                    <div class="form-group">
                      <label>地址</label>
                      <input v-model="form.networkAccess.hops[activeHopIndex].host" :placeholder="hopPlaceholder(form.networkAccess.hops[activeHopIndex].type, 'host')" />
                    </div>
                    <div class="form-group">
                      <label>端口</label>
                      <input v-model.number="form.networkAccess.hops[activeHopIndex].port" type="number" :placeholder="form.networkAccess.hops[activeHopIndex].type === 'zero_trust' ? '443' : '22'" />
                    </div>
                  </div>
                  <div class="form-group">
                    <label>用户名</label>
                    <input v-model="form.networkAccess.hops[activeHopIndex].username" :placeholder="hopPlaceholder(form.networkAccess.hops[activeHopIndex].type, 'username')" />
                  </div>
                  <div class="form-group">
                    <label>认证方式</label>
                    <select v-model="form.networkAccess.hops[activeHopIndex].authType">
                      <option value="password">密码</option>
                      <option value="ssh_key">SSH 密钥</option>
                      <option value="token" v-if="form.networkAccess.hops[activeHopIndex].type === 'zero_trust'">Token / API Key</option>
                      <option value="cert" v-if="form.networkAccess.hops[activeHopIndex].type === 'zero_trust'">证书认证</option>
                    </select>
                  </div>
                  <div class="form-group" v-if="form.networkAccess.hops[activeHopIndex].authType === 'password'">
                    <label>密码</label>
                    <input v-model="form.networkAccess.hops[activeHopIndex].password" type="password" placeholder="可留空，执行时弹窗输入" />
                  </div>
                  <div class="form-group" v-if="form.networkAccess.hops[activeHopIndex].authType === 'ssh_key'">
                    <label>SSH 私钥</label>
                    <textarea v-model="form.networkAccess.hops[activeHopIndex].sshKey" rows="2" placeholder="粘贴 SSH 私钥内容"></textarea>
                  </div>

                  <!-- 零信任/堡垒机特殊字段 -->
                  <div class="form-group" v-if="form.networkAccess.hops[activeHopIndex].type === 'bastion'">
                    <label>跳转命令</label>
                    <input v-model="form.networkAccess.hops[activeHopIndex].jumpCommand" placeholder="如: ssh -W %h:%p target_host" />
                    <span class="field-hint">堡垒机跳转目标服务器的命令，留空则使用 SSH 直连</span>
                  </div>
                  <div class="form-group" v-if="form.networkAccess.hops[activeHopIndex].type === 'zero_trust'">
                    <label>目标主机标识</label>
                    <input v-model="form.networkAccess.hops[activeHopIndex].targetHost" placeholder="零信任网关中的目标主机标识或 IP" />
                  </div>
                </div>
              </div>

              <!-- 空状态 -->
              <div class="hop-empty" v-if="form.networkAccess.hops.length === 0">
                <p>暂无网络链路配置</p>
                <p class="hop-empty-hint">如果目标服务器在隔离网络或需要通过多跳访问，请添加链路</p>
              </div>

              <div class="form-group" v-if="form.networkAccess.hops.length > 0" style="margin-top: 12px;">
                <label>
                  <input type="checkbox" v-model="form.networkAccess.isolated" />
                  目标网络为隔离网络（如首信信创云）
                </label>
              </div>

              <!-- 说明文字 -->
              <div class="access-desc" style="margin-top: 12px; margin-bottom: 0;">🔗 配置从 CI/CD 端到目标服务器的网络链路。<br/>常见场景：阿里云效 → 零信任网关 → 堡垒机 → 目标服务器</div>
            </section>
          </div>

          <!-- 云服务凭据配置（仅云托管工具显示） -->
          <section class="section" v-if="isCloudService">
            <h3>8. 云服务凭据</h3>

            <!-- AccessKey 模式：云效/CodeArts/CODING（用于 API 创建流水线） -->
            <template v-if="cloudAuthMode === 'accesskey'">
              <div class="form-group">
                <label>云服务商</label>
                <select v-model="form.cloudCredential.provider">
                  <option value="aliyun">阿里云（云效 DevOps）</option>
                  <option value="huawei">华为云（CodeArts）</option>
                  <option value="tencent">腾讯云（CODING）</option>
                </select>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>AccessKey ID <span class="required">*</span></label>
                  <input v-model="form.cloudCredential.accessKeyId" placeholder="阿里云 AccessKey ID" />
                </div>
                <div class="form-group">
                  <label>AccessKey Secret <span class="required">*</span></label>
                  <input v-model="form.cloudCredential.accessKeySecret" type="password" placeholder="阿里云 AccessKey Secret" />
                </div>
              </div>
              <div class="form-row">
                <div class="form-group">
                  <label>区域</label>
                  <select v-model="form.cloudCredential.regionId">
                    <option v-for="r in currentRegions" :key="r.value" :value="r.value">{{ r.label }}</option>
                  </select>
                </div>
                <div class="form-group">
                  <label>组织 ID（可选）</label>
                  <input v-model="form.cloudCredential.organizationId" placeholder="云效组织 ID" />
                </div>
              </div>
              <div class="access-desc" style="margin-top: 8px;">
                <template v-if="form.cloudCredential.provider === 'aliyun'">
                  🔑 获取方式：登录阿里云控制台 → 右上角头像 → AccessKey 管理 → 创建 AccessKey<br/>
                  权限建议：使用 RAM 子账号，授予 AliyunDevOpsFullAccess 权限
                </template>
                <template v-else-if="form.cloudCredential.provider === 'huawei'">
                  🔑 获取方式：登录华为云控制台 → 右上角用户名 → 我的凭证 → 访问密钥 → 新增访问密钥<br/>
                  权限建议：使用 IAM 子用户，授予 CodeArts 相关权限
                </template>
                <template v-else>
                  🔑 获取方式：登录腾讯云控制台 → 右上角账号 → 访问管理 → API 密钥管理 → 新建密钥<br/>
                  权限建议：使用 CAM 子用户，授予 CODING 相关权限
                </template>
              </div>
            </template>

            <!-- Token 模式：GitHub Actions / GitLab CI（用于自动写入 Secrets/Variables） -->
            <template v-else>
              <div class="form-group">
                <label>Personal Access Token（可选，填写后自动配置 Secrets）</label>
                <input v-model="form.cloudCredential.token" type="password"
                       :placeholder="form.tool === 'github' ? 'ghp_xxx（repo 权限）' : 'glpat-xxx（api 权限）'" />
              </div>
              <div class="form-group" v-if="form.tool === 'gitlab'">
                <label>GitLab 实例地址（自建 GitLab 填写）</label>
                <input v-model="form.cloudCredential.baseUrl" placeholder="https://gitlab.com（默认）" />
              </div>
              <div class="access-desc" style="margin-top: 8px;">
                <template v-if="form.tool === 'github'">
                  🔑 获取方式：GitHub → Settings → Developer settings → Personal access tokens → Generate new token（勾选 repo 权限）<br/>
                  用途：自动写入 SERVER_SSH_KEY / DEP_REPO_TOKEN 等 Secrets；不填则需搭建后手动配置
                </template>
                <template v-else>
                  🔑 获取方式：GitLab → User Settings → Access Tokens → 创建 Token（勾选 api 权限）<br/>
                  用途：自动写入 CI/CD Variables（SERVER_SSH_KEY / DEP_REPO_TOKEN）；不填则需搭建后手动配置
                </template>
              </div>
            </template>
          </section>

          <!-- Step 8: CI/CD 工具部署位置 -->
          <section class="section">
            <h3>8. CI/CD 工具部署位置</h3>
            <div class="mode-list" v-if="!currentToolIsCloudOnly">
              <label class="mode-item" :class="{ active: form.toolDeploy === 'dedicated' }">
                <input type="radio" v-model="form.toolDeploy" value="dedicated" />
                <div class="mode-text">
                  <span class="mode-label">🖥️ 独立服务器</span>
                  <span class="mode-desc">Jenkins/Runner 部署在独立服务器上，与目标服务器分开，适合生产环境</span>
                </div>
              </label>
              <label class="mode-item" :class="{ active: form.toolDeploy === 'target' }">
                <input type="radio" v-model="form.toolDeploy" value="target" />
                <div class="mode-text">
                  <span class="mode-label">📦 目标服务器上</span>
                  <span class="mode-desc">CI/CD 工具直接安装在应用运行的同一台服务器上，简单但耦合</span>
                </div>
              </label>
            </div>
            <div class="mode-list" v-else>
              <label class="mode-item active">
                <input type="radio" v-model="form.toolDeploy" value="managed" checked />
                <div class="mode-text">
                  <span class="mode-label">☁️ 云托管服务</span>
                  <span class="mode-desc">使用云厂商托管 CI/CD 服务，无需自建，开箱即用</span>
                </div>
              </label>
            </div>

            <!-- 独立服务器配置 -->
            <div class="sub-config" v-if="form.toolDeploy === 'dedicated'">
              <div class="tool-server-row">
                <div class="form-group">
                  <label>工具服务器地址</label>
                  <input v-model="form.toolServer.host" placeholder="CI/CD 工具服务器 IP" />
                </div>
                <div class="form-group">
                  <label>SSH 端口</label>
                  <input v-model.number="form.toolServer.port" type="number" placeholder="22" />
                </div>
                <div class="form-group">
                  <label>用户名</label>
                  <input v-model="form.toolServer.username" placeholder="root" />
                </div>
                <div class="form-group">
                  <label>认证方式</label>
                  <select v-model="form.toolServer.authType">
                    <option value="password">密码</option>
                    <option value="ssh_key">SSH 密钥</option>
                  </select>
                </div>
                <div class="form-group" v-if="form.toolServer.authType === 'password'">
                  <label>密码</label>
                  <input v-model="form.toolServer.password" type="password" placeholder="可留空，执行时弹窗输入" />
                </div>
                <div class="form-group" v-if="form.toolServer.authType === 'ssh_key'">
                  <label>SSH 私钥</label>
                  <textarea v-model="form.toolServer.sshKey" rows="2" placeholder="粘贴 SSH 私钥内容"></textarea>
                </div>
              </div>
            </div>
          </section>

          <!-- 部署建议 -->
          <section class="section" v-if="form.server.host">
            <h3>8. 部署建议</h3>
            <button class="btn-get-rec" @click="fetchRecommendations" :disabled="loadingRec">
              {{ loadingRec ? '分析中...' : '获取智能部署建议' }}
            </button>
            <div class="rec-panel" v-if="recommendations">
              <div class="rec-section" v-if="recommendations.server">
                <h4>🖥️ CI/CD 服务器部署位置建议</h4>
                <p class="rec-best" v-if="recommendations.server.bestPractice">{{ recommendations.server.bestPractice }}</p>
                <div class="rec-item" v-for="(r, i) in recommendations.server.recommendations" :key="'s'+i">
                  <span class="rec-priority" :class="r.priority">{{ r.priority === 'high' ? '推荐' : '可选' }}</span>
                  <strong>{{ r.location }}</strong>
                  <p>{{ r.reason }}</p>
                </div>
              </div>
              <div class="rec-section" v-if="recommendations.deployMethod">
                <h4>📦 部署方式建议</h4>
                <div class="rec-method" v-for="(m, i) in recommendations.deployMethod.recommendations.filter(r => !r.type)" :key="'m'+i">
                  <div class="rec-method-header" :class="{ recommended: m.recommended }">
                    <strong>{{ m.method }}</strong>
                    <span class="rec-badge" v-if="m.recommended">推荐</span>
                  </div>
                  <p>{{ m.reason }}</p>
                  <div class="rec-pros-cons">
                    <span class="rec-pro" v-for="p in m.pros" :key="p">✅ {{ p }}</span>
                    <span class="rec-con" v-for="c in m.cons" :key="c">⚠️ {{ c }}</span>
                  </div>
                </div>
                <div class="rec-note" v-for="(n, i) in recommendations.deployMethod.recommendations.filter(r => r.type)" :key="'n'+i">
                  💡 {{ n.note }}
                </div>
              </div>
              <div class="rec-section" v-if="recommendations.network">
                <h4>🌐 网络方案建议（{{ recommendations.network.scenarioName }}）</h4>
                <div class="rec-item" v-for="(n, i) in recommendations.network.recommendations" :key="'n'+i">
                  <span class="rec-priority" :class="n.recommended ? 'high' : 'medium'">{{ n.recommended ? '推荐' : '可选' }}</span>
                  <strong>{{ n.scheme }}</strong>
                  <p>{{ n.description }}</p>
                  <ol class="rec-steps">
                    <li v-for="s in n.steps" :key="s">{{ s }}</li>
                  </ol>
                </div>
              </div>
              <div class="rec-tips" v-if="recommendations.tips && recommendations.tips.length">
                <h4>💡 提示</h4>
                <div class="rec-tip" v-for="(t, i) in recommendations.tips" :key="i" :class="t.type">
                  {{ t.type === 'warning' ? '⚠️' : 'ℹ️' }} {{ t.text }}
                </div>
              </div>
            </div>
          </section>
        </template>

        <!-- Error -->
        <div class="error-inline" v-if="error">
          <p class="error-text">❌ {{ error }}</p>
          <button class="btn-secondary" @click="error = null">重试</button>
        </div>
      </div>
    </div>

    <!-- ========== 结果页（仅生成模式） ========== -->
    <div class="result-page" v-if="page === 'result' && result">
      <div class="page-header">
        <button class="btn-back" @click="page = 'form'">← 返回配置</button>
        <h2>生成结果</h2>
        <div class="page-actions">
          <button class="btn-secondary" @click="downloadAll">下载全部</button>
          <button class="btn-secondary" @click="copyAll">复制全部</button>
        </div>
      </div>

      <div class="result-panel">
        <div class="file-tabs">
          <button
            v-for="file in result.files"
            :key="file.name"
            :class="{ active: activeFile === file.name }"
            @click="activeFile = file.name"
          >
            {{ file.name }}
          </button>
        </div>

        <div class="file-content">
          <pre v-if="currentFile">{{ currentFile.content }}</pre>
          <p v-else class="empty">请选择一个文件</p>
        </div>

        <div class="output-path">
          输出路径：<code>{{ outputDir }}</code>
          <button class="btn-small" @click="copyPath">复制路径</button>
        </div>
      </div>
    </div>

    <!-- ========== 进度页（自动搭建模式） ========== -->
    <div class="progress-page" v-if="page === 'progress'">
      <div class="page-header">
        <button class="btn-back" @click="page = 'form'" v-if="deployDone">← 返回配置</button>
        <h2>搭建进度</h2>
        <div class="page-actions">
          <button class="btn-secondary" @click="cancelDeploy" v-if="deploying && !deployDone">取消</button>
        </div>
      </div>

      <div class="progress-panel-full">
        <div class="step-list">
          <div
            v-for="step in pipelineSteps"
            :key="step.id"
            class="step-item"
            :class="getStepStatus(step.id)"
          >
            <span class="step-icon">{{ getStepIcon(step.id) }}</span>
            <span class="step-name">[{{ step.order }}/{{ pipelineSteps.length }}] {{ step.name }}</span>
            <span class="step-status">{{ getStepStatusText(step.id) }}</span>
          </div>
        </div>

        <div class="log-panel">
          <h4>实时日志</h4>
          <div class="log-content" ref="logContainer">
            <div v-for="(log, i) in deployLogs" :key="i" class="log-line">
              <span class="log-prefix">&gt;</span> {{ log }}
            </div>
          </div>
        </div>

        <!-- 流水线管理信息 -->
        <div class="pipeline-info-panel" v-if="deployDone && !hasFailedSteps">
          <h4>🎉 流水线搭建完成！</h4>
          <div class="pipeline-info-grid">
            <div class="pipeline-info-card">
              <div class="pipeline-info-title">📍 流水线管理地址</div>
              <div class="pipeline-info-content" v-html="pipelineManageUrl"></div>
            </div>
            <div class="pipeline-info-card">
              <div class="pipeline-info-title">🚀 如何触发构建</div>
              <div class="pipeline-info-content" v-html="pipelineTriggerInfo"></div>
            </div>
            <div class="pipeline-info-card">
              <div class="pipeline-info-title">📋 查看构建日志</div>
              <div class="pipeline-info-content" v-html="pipelineLogInfo"></div>
            </div>
          </div>
          <div class="pipeline-actions">
            <a :href="pipelineManageLink" target="_blank" class="btn-primary" v-if="pipelineManageLink">
              打开流水线管理 →
            </a>
            <button class="btn-secondary" @click="page = 'form'">返回配置页</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 凭据输入弹窗 -->
    <div class="modal-overlay" v-if="showCredentialDialog" @click.self="onCredentialCancel">
      <div class="modal">
        <h3>{{ credentialDialog.title }}</h3>
        <p class="modal-desc">{{ credentialDialog.reason }}</p>

        <div class="form-group" v-if="credentialDialog.cred_type === 'git'">
          <label>用户名</label>
          <input v-model="credentialInput.username" placeholder="Git 用户名" />
        </div>
        <div class="form-group" v-if="credentialDialog.type === 'password'">
          <label>密码</label>
          <input v-model="credentialInput.password" type="password" placeholder="请输入密码" />
        </div>
        <div class="form-group" v-if="credentialDialog.type === 'ssh_key'">
          <label>SSH 私钥</label>
          <textarea v-model="credentialInput.sshKey" rows="4" placeholder="粘贴 SSH 私钥"></textarea>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="onCredentialCancel">取消</button>
          <button class="generate-btn" style="width:auto;padding:8px 24px" @click="onCredentialSubmit">确认</button>
        </div>
      </div>
    </div>

    <!-- 审批确认弹窗 -->
    <div class="modal-overlay" v-if="showApprovalDialog">
      <div class="modal approval-modal">
        <h3>🔍 审批确认</h3>
        <p class="modal-desc">{{ approvalDialog.message }}</p>
        <div class="approval-info">
          <p>测试环境部署已完成，请确认下一步操作：</p>
        </div>
        <div class="approval-actions">
          <button class="btn-approve" @click="onApprovalAction('merge')">
            ✅ 确认合并到主分支
          </button>
          <button class="btn-reject" @click="onApprovalAction('reject')">
            ❌ 拒绝合并
          </button>
          <button class="btn-rollback" @click="onApprovalAction('rollback')">
            ↩️ 回滚到上一版本
          </button>
        </div>
      </div>
    </div>

    <!-- 分支选择弹窗 -->
    <div class="modal-overlay" v-if="showBranchSelectDialog">
      <div class="modal branch-modal">
        <h3>🌿 选择集成分支</h3>
        <p class="modal-desc">请选择需要集成和部署的分支（可多选）：</p>

        <div class="branch-select-list">
          <label v-for="br in availableBranches" :key="br" class="branch-checkbox">
            <input type="checkbox" :value="br" v-model="selectedBranches" />
            <span class="branch-name">{{ br }}</span>
          </label>
          <p v-if="availableBranches.length === 0" class="empty-branches">暂无可用分支</p>
        </div>

        <div class="release-strategy-section" v-if="selectedBranches.length > 1">
          <h4>发布策略</h4>
          <select v-model="branchReleaseStrategy">
            <option value="auto_merge">自动合并（测试通过后自动合并到主分支）</option>
            <option value="manual_merge">手动合并（测试通过后需手动确认合并）</option>
            <option value="no_merge">不合并（仅测试，不合并到主分支）</option>
          </select>
          <div class="strategy-options" v-if="branchReleaseStrategy !== 'no_merge'">
            <label>
              主分支：
              <input v-model="branchMainBranch" placeholder="main" style="width: 100px; padding: 4px 8px;" />
            </label>
            <label>
              <input type="checkbox" v-model="branchEnableRollback" />
              启用回滚
            </label>
          </div>
        </div>

        <div class="modal-actions">
          <button class="btn-secondary" @click="onBranchSelectCancel">取消</button>
          <button class="generate-btn" style="width:auto;padding:8px 24px" @click="onBranchSelectConfirm"
            :disabled="selectedBranches.length === 0">
            确认并继续
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, nextTick, watch } from 'vue'
import { generateFiles, startAutoDeploy, connectPipelineWs, getRecommendations } from '../api/index.js'

const tools = [
  { id: 'jenkins', name: 'Jenkins', icon: '🟠', desc: '开源 CI/CD，经典 Pipeline',
    features: '自由编排 Pipeline、丰富插件生态、支持分布式构建',
    suitable: '中大型团队、复杂流水线、自建服务器场景',
    hosted: false },
  { id: 'aliyun', name: '阿里云效', icon: '🔵', desc: '阿里 DevOps 平台',
    features: '云原生托管、内置代码托管与制品库、一键部署阿里云资源',
    suitable: '业务在阿里云上的团队、希望免运维的中小项目',
    hosted: true },
  { id: 'huawei', name: '华为云流水线', icon: '🔴', desc: '华为云 CodeArts（配置生成，需手动导入）',
    features: '深度集成华为云服务、支持信创环境、代码检查能力强',
    suitable: '华为云用户、信创/国产化需求、政企项目',
    hosted: true, manualImport: true },
  { id: 'tencent', name: '腾讯云 TKE', icon: '🟢', desc: '腾讯云 CI/CD（配置生成，需手动导入）',
    features: '与 TKE 容器服务深度集成、支持蓝绿/灰度发布',
    suitable: '腾讯云用户、K8s 容器化部署、微服务架构',
    hosted: true, manualImport: true },
  { id: 'github', name: 'GitHub Actions', icon: '⚫', desc: 'GitHub 原生 CI/CD',
    features: '与 GitHub 仓库无缝集成、海量社区 Action、YAML 配置简洁',
    suitable: '代码托管在 GitHub 的项目、开源项目、轻量级 CI/CD',
    hosted: true },
  { id: 'gitlab', name: 'GitLab CI', icon: '🟣', desc: 'GitLab 内置流水线',
    features: '与 GitLab 深度集成、.gitlab-ci.yml 配置、内置 Container Registry',
    suitable: '代码托管在 GitLab 的项目、一体化 DevOps 流程',
    hosted: true },
  { id: 'runner', name: 'Runner', icon: '🏃', desc: 'GitLab/GitHub Runner',
    features: '轻量级执行器、可部署在任意服务器、支持 Docker/Shell 执行',
    suitable: '需要在自有服务器上运行 CI/CD 任务、跨云构建场景',
    hosted: false },
]

const projectTypes = [
  { id: 'java-maven', name: 'Java Maven', icon: '☕', langs: 'Java / Maven / Spring Boot' },
  { id: 'java-gradle', name: 'Java Gradle', icon: '☕', langs: 'Java / Gradle' },
  { id: 'vue', name: 'Vue.js', icon: '🟢', langs: 'Vue 2 / Vue 3' },
  { id: 'react', name: 'React', icon: '⚛️', langs: 'React / Next.js' },
  { id: 'python', name: 'Python', icon: '🐍', langs: 'Python / Django / Flask' },
  { id: 'go', name: 'Go', icon: '🔵', langs: 'Go / Golang' },
]

const pipelineSteps = [
  { id: 'git_clone', name: '克隆代码仓库', order: 1 },
  { id: 'branch_select', name: '选择集成分支', order: 2 },
  { id: 'generate_config', name: '生成流水线配置', order: 3 },
  { id: 'git_push', name: '推送配置到仓库', order: 4 },
  { id: 'ssh_connect', name: '连接目标服务器', order: 5 },
  { id: 'install_tool', name: '安装 CI/CD 工具', order: 6 },
  { id: 'configure_pipeline', name: '配置流水线', order: 7 },
]

// 模式
const mode = ref('generate')

const form = reactive({
  tool: 'jenkins',
  projectType: 'java-maven',
  deployMethod: 'docker',
  repoUrl: '',
  projectName: '',
  branch: 'main',
  port: 8080,
  jdkVersion: '',
  nodeVersion: '20',
  // CI/CD 工具部署位置
  toolDeploy: 'dedicated',
  toolServer: {
    host: '',
    port: 22,
    username: 'root',
    authType: 'password',
    password: '',
    sshKey: '',
  },
  gitAuth: {
    type: 'password',
    username: '',
    password: '',
    sshKey: '',
  },
  server: {
    host: '',
    port: 22,
    username: 'root',
    authType: 'password',
    password: '',
    sshKey: '',
    deployPath: '/opt/apps',
    backupBeforeDeploy: true,
  },
  // 网络访问链路
  networkAccess: {
    hops: [], // [{type, host, port, username, authType, password, sshKey, jumpCommand, targetHost}]
    isolated: false,
  },
  // 应用服务器配置
  appServer: {
    type: 'tongweb',
    home: '',
    port: 9060,
    contextPath: '/app',
  },
  // 国内镜像选项
  useChinaMirror: false,  // 使用国内镜像源（适用于国产 OS 或国内网络）
  // 依赖仓库配置
  dependencyRepo: {
    url: '',
    branch: 'main',
    authType: 'password',
    username: '',
    password: '',
    sshKey: '',
  },
  // 云托管服务凭据（云效/CodeArts/GitHub/GitLab）
  cloudCredential: {
    provider: 'aliyun',
    accessKeyId: '',
    accessKeySecret: '',
    regionId: 'cn_hangzhou',
    organizationId: '',
    token: '',       // GitHub PAT / GitLab Token
    baseUrl: '',     // 自建实例地址（GitLab/GitHub Enterprise）
  },
  // 流水线模式：release（发布）| integration（集成测试）
  pipelineMode: 'release',
  // 多环境配置（每个环境 = 集成分支 + 独立服务器）
  environments: [],
  // 负载均衡配置（多后端服务器 + Nginx，滚动部署）
  loadBalancer: {
    enabled: false,
    type: 'nginx',
    host: '',
    port: 22,
    username: 'root',
    authType: 'password',
    password: '',
    sshKey: '',
    listenPort: 80,
    healthCheckPath: '/',
    healthCheckRetries: 6,
    servers: [],
  },
})

// 自动从 repoUrl 提取 projectName
watch(() => form.repoUrl, (url) => {
  if (url && url.trim()) {
    // 支持格式：
    // https://github.com/owner/project.git
    // git@github.com:owner/project.git
    // https://gitlab.com/group/subgroup/project.git
    const match = url.trim().match(/\/([^\/]+?)(?:\.git)?\/?$/) ||
                  url.trim().match(/:([^:\/]+?)(?:\.git)?\/?$/)
    if (match && match[1]) {
      form.projectName = match[1]
    } else {
      form.projectName = ''
    }
  } else {
    form.projectName = ''
  }
}, { immediate: true })

// 页面状态
const page = ref('form') // 'form' | 'result' | 'progress'

// 仅生成模式状态
const loading = ref(false)
const result = ref(null)
const error = ref(null)
const activeFile = ref('')
const outputDir = ref('')

const currentFile = computed(() =>
  result.value?.files.find(f => f.name === activeFile.value) || null
)

// 当前工具是否支持云托管
const currentToolSupportsHosted = computed(() => {
  const tool = tools.find(t => t.id === form.tool)
  return tool?.hosted ?? false
})

// 当前工具是否仅支持云托管（无法自建）
const currentToolIsCloudOnly = computed(() => {
  const tool = tools.find(t => t.id === form.tool)
  return tool?.hosted ?? false
})

// 是否为 Java 项目
const isJavaProject = computed(() => {
  return form.projectType === 'java-maven' || form.projectType === 'java-gradle'
})

// 是否为云托管服务（需要云服务凭据）
const isCloudService = computed(() => {
  return ['aliyun', 'huawei', 'tencent', 'github', 'gitlab'].includes(form.tool)
})

// 云服务凭据认证模式：github/gitlab 用 Token，其余用 AccessKey
const cloudAuthMode = computed(() => {
  return (form.tool === 'github' || form.tool === 'gitlab') ? 'token' : 'accesskey'
})

// 流水线管理信息
const pipelineManageLink = computed(() => {
  const tool = form.tool
  const serverHost = form.server.host || '<服务器IP>'
  
  if (tool === 'jenkins') {
    return `http://${serverHost}:8080`
  } else if (tool === 'aliyun') {
    return 'https://devops.aliyun.com'
  } else if (tool === 'huawei') {
    return 'https://console.huaweicloud.com/codearts'
  } else if (tool === 'tencent') {
    return 'https://console.cloud.tencent.com/tke'
  } else if (tool === 'github') {
    return `${form.repoUrl.replace('.git', '')}/actions`
  } else if (tool === 'gitlab') {
    return `${form.repoUrl.replace('.git', '')}/-/pipelines`
  }
  return ''
})

const pipelineManageUrl = computed(() => {
  const tool = form.tool
  const serverHost = form.server.host || '<服务器IP>'
  const link = pipelineManageLink.value
  
  if (tool === 'jenkins') {
    return `Jenkins Web UI：<a href="${link}" target="_blank">${link}</a>`
  } else if (tool === 'aliyun') {
    return `阿里云效控制台：<a href="${link}" target="_blank">${link}</a><br>路径：云效 DevOps → 流水线`
  } else if (tool === 'huawei') {
    return `华为云 CodeArts：<a href="${link}" target="_blank">${link}</a><br>路径：CodeArts → 流水线`
  } else if (tool === 'tencent') {
    return `腾讯云 TKE：<a href="${link}" target="_blank">${link}</a><br>路径：TKE → CI/CD`
  } else if (tool === 'github') {
    return `GitHub Actions：<a href="${link}" target="_blank">${link}</a>`
  } else if (tool === 'gitlab') {
    return `GitLab Pipelines：<a href="${link}" target="_blank">${link}</a>`
  }
  return '请查看对应云平台的控制台'
})

const pipelineTriggerInfo = computed(() => {
  const tool = form.tool
  const branch = form.branch || 'main'
  
  if (tool === 'jenkins') {
    return `1. 登录 Jenkins Web UI<br>2. 找到项目 <strong>${form.projectName}</strong><br>3. 点击「Build Now」触发构建<br>4. 或配置 Webhook 自动触发`
  } else if (tool === 'github') {
    return `1. 推送代码到 <strong>${branch}</strong> 分支自动触发<br>2. 或在 Actions 页面手动触发<br>3. 创建 Pull Request 也会触发检查`
  } else if (tool === 'gitlab') {
    return `1. 推送代码到 <strong>${branch}</strong> 分支自动触发<br>2. 或在 CI/CD → Pipelines 页面点击「Run pipeline」<br>3. 合并请求也会触发流水线`
  } else if (tool === 'runner') {
    return `1. 确保 Runner 已注册到 GitLab/GitHub<br>2. 推送代码到 <strong>${branch}</strong> 分支<br>3. Runner 会自动接收并执行任务`
  } else {
    return `1. 推送代码到 <strong>${branch}</strong> 分支自动触发<br>2. 或在控制台手动触发流水线`
  }
})

const pipelineLogInfo = computed(() => {
  const tool = form.tool
  
  if (tool === 'jenkins') {
    return `1. 在 Jenkins 任务页面<br>2. 点击构建编号（如 #1, #2）<br>3. 点击「Console Output」查看完整日志`
  } else if (tool === 'github') {
    return `1. 在 Actions 页面点击工作流运行记录<br>2. 点击具体的 job 查看步骤日志<br>3. 可展开每个 step 查看详细输出`
  } else if (tool === 'gitlab') {
    return `1. 在 Pipelines 页面点击流水线<br>2. 点击具体 job 查看日志<br>3. 支持实时日志流式输出`
  } else {
    return `1. 在流水线列表点击运行记录<br>2. 查看各阶段的执行日志<br>3. 失败时可查看详细错误信息`
  }
})

// 检查是否有失败的步骤
const hasFailedSteps = computed(() => {
  return Object.values(stepStatuses).some(s => s === 'failed')
})

// 工具切换时，自动设置 toolDeploy
watch(() => form.tool, (newTool) => {
  const tool = tools.find(t => t.id === newTool)
  if (tool) {
    if (tool.hosted) {
      // 云托管工具（阿里云效、华为云等）→ 只能云托管
      form.toolDeploy = 'managed'
    } else {
      // 自建工具（Jenkins、Runner）→ 如果当前是云托管，回退到独立服务器
      if (form.toolDeploy === 'managed') {
        form.toolDeploy = 'dedicated'
      }
    }
  }
  // 云服务凭据提供商随流水线工具自动联动
  if (['aliyun', 'huawei', 'tencent', 'github', 'gitlab'].includes(newTool)) {
    form.cloudCredential.provider = newTool
  }
})

// 云服务区域选项（按云服务商区分）
const cloudRegions = {
  aliyun: [
    { value: 'cn_hangzhou', label: '华东 1（杭州）' },
    { value: 'cn_shanghai', label: '华东 2（上海）' },
    { value: 'cn_beijing', label: '华北 2（北京）' },
    { value: 'cn_shenzhen', label: '华南 1（深圳）' },
    { value: 'cn_qingdao', label: '华北 1（青岛）' },
    { value: 'cn_zhangjiakou', label: '华北 3（张家口）' },
    { value: 'cn_chengdu', label: '西南 1（成都）' },
  ],
  huawei: [
    { value: 'cn-north-4', label: '华北四（北京）' },
    { value: 'cn-north-1', label: '华北一（北京）' },
    { value: 'cn-east-3', label: '上海二' },
    { value: 'cn-east-2', label: '上海一' },
    { value: 'cn-south-1', label: '华南一（广州）' },
    { value: 'cn-southwest-2', label: '西南一（贵阳）' },
  ],
  tencent: [
    { value: 'ap-guangzhou', label: '广州' },
    { value: 'ap-beijing', label: '北京' },
    { value: 'ap-shanghai', label: '上海' },
    { value: 'ap-shenzhen', label: '深圳' },
    { value: 'ap-chengdu', label: '成都' },
    { value: 'ap-chongqing', label: '重庆' },
  ],
}
const currentRegions = computed(() => cloudRegions[form.cloudCredential.provider] || cloudRegions.aliyun)

// 切换云服务商时，区域重置为该服务商的默认区域
watch(() => form.cloudCredential.provider, (p) => {
  const defaults = { aliyun: 'cn_hangzhou', huawei: 'cn-north-4', tencent: 'ap-guangzhou' }
  const def = defaults[p]
  if (def && !(cloudRegions[p] || []).some(r => r.value === form.cloudCredential.regionId)) {
    form.cloudCredential.regionId = def
  }
})

// 执行按钮条件检查
const canExecute = computed(() => {
  // 基本条件：仓库 URL 和项目名称
  if (!form.repoUrl || !form.projectName) return false
  
  if (mode.value === 'auto') {
    // 自动搭建模式需要更多条件
    if (!form.server.host) return false
    if (!form.branch || form.branch.trim() === '') return false
    // 专用服务器模式：工具服务器地址必填
    if (form.toolDeploy === 'dedicated' && !form.toolServer.host) return false
    // 云托管工具：AccessKey 模式必填（github/gitlab 用可选 Token，不强制）
    if (isCloudService.value && cloudAuthMode.value === 'accesskey'
        && (!form.cloudCredential.accessKeyId || !form.cloudCredential.accessKeySecret)) return false
  }
  
  return true
})

// 执行动作
function executeAction() {
  if (!canExecute.value) return
  
  if (mode.value === 'generate') {
    onGenerate()
  } else {
    onAutoDeploy()
  }
}

// 自动搭建状态
const deploying = ref(false)
const deployDone = ref(false)
const deployLogs = ref([])
const stepStatuses = reactive({})
const wsConnection = ref(null)
const logContainer = ref(null)

// 凭据弹窗
const showCredentialDialog = ref(false)
const credentialDialog = reactive({ title: '', reason: '', cred_type: '', type: '' })
const credentialInput = reactive({ username: '', password: '', sshKey: '' })

// 审批弹窗
const showApprovalDialog = ref(false)
const approvalDialog = reactive({ message: '' })

// 分支选择弹窗
const showBranchSelectDialog = ref(false)
const availableBranches = ref([])
const selectedBranches = ref([])
const branchReleaseStrategy = ref('auto_merge')
const branchMainBranch = ref('main')
const branchEnableRollback = ref(true)

// 网络访问配置开关
const showAccessConfig = ref(false)
const activeHopIndex = ref(0)

// 跳转链路操作
function addHop(type) {
  form.networkAccess.hops.push({
    type,
    host: '',
    port: type === 'zero_trust' ? 443 : 22,
    username: '',
    authType: 'password',
    password: '',
    sshKey: '',
    jumpCommand: '',
    targetHost: '',
  })
  // 自动切换到新添加的选项卡
  activeHopIndex.value = form.networkAccess.hops.length - 1
}

function addEnvironment() {
  form.environments.push({
    name: '',
    branch: '',
    server: {
      host: '',
      port: 22,
      username: 'root',
      authType: 'password',
      password: '',
      sshKey: '',
      deployPath: form.server.deployPath || '/opt/apps',
      backupBeforeDeploy: true,
    },
  })
}

function removeEnvironment(index) {
  form.environments.splice(index, 1)
}

function addLbServer() {
  form.loadBalancer.servers.push({
    host: '',
    port: 22,
    username: 'root',
    authType: 'password',
    password: '',
    sshKey: '',
    deployPath: form.server.deployPath || '/opt/apps',
    backupBeforeDeploy: true,
  })
}

// 有效的环境配置（名称 + 服务器地址均填写）
function validEnvironments() {
  return form.environments.filter(e => e.name && e.server && e.server.host)
}

// 有效的负载均衡配置（启用 + LB 地址 + 至少一台后端）
function validLoadBalancer() {
  const lb = form.loadBalancer
  if (!lb.enabled || !lb.host) return null
  const servers = lb.servers.filter(s => s.host)
  if (servers.length === 0) return null
  const { enabled, ...rest } = lb
  return { ...rest, servers }
}
function removeHop(index) {
  form.networkAccess.hops.splice(index, 1)
  // 如果删除的是当前激活的选项卡，切换到相邻的选项卡
  if (activeHopIndex.value >= form.networkAccess.hops.length) {
    activeHopIndex.value = Math.max(0, form.networkAccess.hops.length - 1)
  }
}
function hopTypeLabel(type) {
  const labels = { relay: '中继服务器', bastion: '堡垒机', zero_trust: '零信任/VPN' }
  return labels[type] || type
}
function hopPlaceholder(type, field) {
  if (field === 'host') {
    const ph = { relay: '中继服务器 IP', bastion: '堡垒机 IP 或域名', zero_trust: '零信任网关 IP 或域名' }
    return ph[type] || 'IP 地址'
  }
  if (field === 'username') {
    const ph = { relay: 'root', bastion: '堡垒机用户名', zero_trust: '平台用户名' }
    return ph[type] || '用户名'
  }
  return ''
}

// 部署建议
const recommendations = ref(null)
const loadingRec = ref(false)

function showApproval(message) {
  approvalDialog.message = message
  showApprovalDialog.value = true
}

function onApprovalAction(action) {
  showApprovalDialog.value = false
  if (wsConnection.value) {
    wsConnection.value.sendCredential('approval', { action })
  }
  if (action === 'merge') {
    addLog('✅ 审批通过，准备合并到主分支...')
  } else if (action === 'reject') {
    addLog('❌ 审批拒绝，不合并到主分支')
  } else if (action === 'rollback') {
    addLog('↩️ 执行回滚到上一稳定版本...')
  }
}

function onGenerate() {
  if (!form.repoUrl || !form.projectName) {
    error.value = '请填写项目仓库 URL 和项目名称'
    return
  }
  error.value = null
  loading.value = true
  generateFiles(form)
    .then(data => {
      result.value = data
      outputDir.value = data.outputDir
      activeFile.value = data.files[0]?.name || ''
      page.value = 'result'
    })
    .catch(err => {
      error.value = err.message || '生成失败'
    })
    .finally(() => {
      loading.value = false
    })
}

async function onAutoDeploy() {
  if (!form.repoUrl || !form.projectName) {
    error.value = '请填写项目仓库 URL 和项目名称'
    return
  }
  if (!form.server.host) {
    error.value = '请填写目标服务器地址'
    return
  }
  // 专用服务器模式：必须填写工具服务器地址
  if (form.toolDeploy === 'dedicated' && !form.toolServer.host) {
    error.value = '已选择专用服务器部署，请填写 CI/CD 工具服务器地址'
    return
  }
  // 集成测试模式：至少需要一个有效环境
  if (form.pipelineMode === 'integration' && validEnvironments().length === 0) {
    error.value = '集成测试模式需要至少配置一个环境（环境名 + 集成分支 + 服务器地址）'
    return
  }
  // 负载均衡：启用后必须填写 LB 地址与至少一台后端服务器
  if (form.loadBalancer.enabled && !validLoadBalancer()) {
    error.value = '已启用负载均衡，请填写 LB 服务器地址并添加至少一台后端服务器'
    return
  }

  error.value = null
  deploying.value = true
  deployDone.value = false
  deployLogs.value = []
  Object.keys(stepStatuses).forEach(k => delete stepStatuses[k])

  try {
    if (!form.branch || form.branch.trim() === '') {
      error.value = '请填写默认分支名'
      deploying.value = false
      return
    }

    const payload = {
      tool: form.tool,
      projectType: form.projectType,
      deployMethod: form.deployMethod,
      repoUrl: form.repoUrl,
      projectName: form.projectName,
      branch: form.branch.trim(),
      port: form.port,
      jdkVersion: form.jdkVersion,
      nodeVersion: form.nodeVersion,
      gitAuth: form.gitAuth,
      server: form.server,
      toolDeploy: form.toolDeploy,
      toolServer: form.toolDeploy === 'dedicated' ? form.toolServer : null,
      networkAccess: showAccessConfig.value && form.networkAccess.hops.length > 0 ? form.networkAccess : null,
      appServer: form.deployMethod === 'app_server' ? form.appServer : null,
      useChinaMirror: form.useChinaMirror,  // 国内镜像选项
      dependencyRepo: form.dependencyRepo.url ? form.dependencyRepo : null,  // 独立依赖仓库
      cloudCredential: isCloudService.value ? form.cloudCredential : null,  // 云托管服务凭据
      pipelineMode: form.pipelineMode,  // 流水线模式：release | integration
      environments: validEnvironments().length > 0 ? validEnvironments() : null,  // 多环境配置
      loadBalancer: validLoadBalancer(),  // 负载均衡配置
    }

    const { taskId } = await startAutoDeploy(payload)

    page.value = 'progress'

    wsConnection.value = connectPipelineWs(taskId, {
      onOpen: () => {
        addLog('WebSocket 连接成功，开始执行...')
      },
      onMessage: (data) => {
        handleWsMessage(data)
      },
      onError: () => {
        addLog('WebSocket 连接错误')
      },
      onClose: () => {
        addLog('WebSocket 连接关闭')
      },
    })
  } catch (err) {
    error.value = err.message || '启动搭建失败'
    deploying.value = false
  }
}

function handleWsMessage(data) {
  const { step, status, message, log, result: taskResult } = data

  if (step === 'complete') {
    deployDone.value = true
    deploying.value = false
    addLog(status === 'success' ? '✅ 搭建完成！' : '❌ 搭建失败')
    if (taskResult?.success) {
      addLog(`部署结果: ${message}`)
    }
    return
  }

  if (step === 'error' || step === 'cancel') {
    deployDone.value = true
    deploying.value = false
    addLog(`${step === 'cancel' ? '已取消' : '错误'}: ${message}`)
    return
  }

  // 更新步骤状态
  if (step && status) {
    stepStatuses[step] = status
  }

  // 记录日志
  if (message) {
    addLog(message)
  }

  // 处理凭据请求、审批确认和分支选择
  if (status === 'waiting_input') {
    if (step === 'approval') {
      // 审批确认
      showApproval(message || '测试部署完成，是否合并到主分支？')
    } else if (step === 'branch_select') {
      // 分支选择 - 从 log 字段解析分支列表
      let branches = []
      try {
        const logData = JSON.parse(log || '{}')
        branches = logData.branches || []
      } catch (e) {
        branches = []
      }
      showBranchSelect(branches, form.branch)
    } else {
      // 凭据请求
      const credType = step
      const reason = message || '需要认证信息'
      showCredential(credType, reason)
    }
  }
}

function showCredential(credType, reason) {
  credentialDialog.cred_type = credType
  credentialDialog.reason = reason
  credentialDialog.type = 'password'
  credentialDialog.title = credType === 'git' ? 'Git 认证' : '服务器认证'
  credentialInput.username = ''
  credentialInput.password = ''
  credentialInput.sshKey = ''
  showCredentialDialog.value = true
}

function onCredentialSubmit() {
  showCredentialDialog.value = false
  const credential = { ...credentialInput }
  if (wsConnection.value) {
    wsConnection.value.sendCredential(credentialDialog.cred_type, credential)
  }
}

function onCredentialCancel() {
  showCredentialDialog.value = false
  if (wsConnection.value) {
    wsConnection.value.sendCredential(credentialDialog.cred_type, {})
  }
}

function showBranchSelect(branches, defaultBranch) {
  availableBranches.value = branches.length > 0 ? branches : [defaultBranch || 'main']
  selectedBranches.value = [defaultBranch || 'main']
  branchReleaseStrategy.value = 'auto_merge'
  branchMainBranch.value = defaultBranch || 'main'
  branchEnableRollback.value = true
  showBranchSelectDialog.value = true
}

function onBranchSelectConfirm() {
  showBranchSelectDialog.value = false
  if (wsConnection.value) {
    wsConnection.value.sendCredential('branch_select', {
      branches: selectedBranches.value,
      releaseStrategy: selectedBranches.value.length > 1 ? {
        strategy: branchReleaseStrategy.value,
        mainBranch: branchMainBranch.value,
        enableRollback: branchEnableRollback.value,
      } : null,
    })
  }
}

function onBranchSelectCancel() {
  showBranchSelectDialog.value = false
  if (wsConnection.value) {
    wsConnection.value.sendCredential('branch_select', {})
  }
}

function cancelDeploy() {
  if (wsConnection.value) {
    wsConnection.value.cancel()
  }
  deploying.value = false
  deployDone.value = true
  addLog('已取消搭建')
}

function addLog(msg) {
  deployLogs.value.push(msg)
  nextTick(() => {
    if (logContainer.value) {
      logContainer.value.scrollTop = logContainer.value.scrollHeight
    }
  })
}

function getStepStatus(stepId) {
  return stepStatuses[stepId] || 'pending'
}

function getStepIcon(stepId) {
  const status = stepStatuses[stepId]
  if (status === 'success') return '✅'
  if (status === 'running') return '⏳'
  if (status === 'failed') return '❌'
  if (status === 'waiting_input') {
    if (stepId === 'branch_select') return '🌿'
    return '🔑'
  }
  return '⬜'
}

function getStepStatusText(stepId) {
  const status = stepStatuses[stepId]
  if (status === 'success') return '完成'
  if (status === 'running') return '进行中...'
  if (status === 'failed') return '失败'
  if (status === 'waiting_input') {
    if (stepId === 'branch_select') return '请选择分支'
    return '等待输入'
  }
  return '等待中'
}

function downloadAll() {
  if (!result.value) return
  result.value.files.forEach(file => {
    const blob = new Blob([file.content], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = file.name
    a.click()
    URL.revokeObjectURL(url)
  })
}

function copyAll() {
  if (!currentFile.value?.content) return
  navigator.clipboard.writeText(currentFile.value.content)
    .then(() => alert('已复制到剪贴板'))
}

function copyPath() {
  navigator.clipboard.writeText(outputDir.value)
    .then(() => alert('路径已复制'))
}

async function fetchRecommendations() {
  loadingRec.value = true
  recommendations.value = null
  try {
    const payload = {
      tool: form.tool,
      projectType: form.projectType,
      deployMethod: form.deployMethod,
      repoUrl: form.repoUrl,
      projectName: form.projectName,
      branch: form.branch,
      port: form.port,
      jdkVersion: form.jdkVersion,
      nodeVersion: form.nodeVersion,
      server: form.server,
      toolDeploy: form.toolDeploy,
      toolServer: form.toolDeploy === 'dedicated' ? form.toolServer : null,
      networkAccess: showAccessConfig.value && form.networkAccess.hops.length > 0 ? form.networkAccess : null,
      appServer: form.deployMethod === 'app_server' ? form.appServer : null,
    }
    recommendations.value = await getRecommendations(payload)
  } catch (err) {
    console.error('获取建议失败:', err)
  } finally {
    loadingRec.value = false
  }
}
</script>

<style scoped>
.container { max-width: 100%; margin: 0 auto; padding: 24px 48px; }
.header-banner {
  background: url('/cicd-banner.png') center center / cover no-repeat;
  border-radius: 12px;
  margin-bottom: 12px;
  position: relative;
}
.header-banner::before {
  content: '';
  position: absolute;
  inset: 0;
  background: rgba(255, 255, 255, 0.55);
  border-radius: 12px;
}
.header-banner > * {
  position: relative;
  z-index: 1;
}
.header {
  text-align: center;
  padding: 24px 0 8px;
}
.logo { font-size: 26px; font-weight: 700; color: #1a1a2e; letter-spacing: -0.5px; }
.subtitle { color: #666; margin-top: 6px; font-size: 13px; }

/* 模式切换 */
.mode-switch {
  display: flex;
  justify-content: center;
  gap: 8px;
  margin-bottom: 0;
  padding: 8px 40px 14px;
}
.mode-switch button {
  padding: 9px 28px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: #fff;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-switch button.active {
  border-color: #4a90d9;
  background: #f0f6ff;
  color: #4a90d9;
}
.mode-switch button:hover { border-color: #4a90d9; }

/* 执行按钮 */
.execute-btn {
  padding: 9px 28px;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  background: #f5f5f5;
  font-size: 14px;
  font-weight: 600;
  cursor: not-allowed;
  transition: all 0.15s;
  color: #999;
  margin-left: auto;
}
.execute-btn.active {
  background: #4a90d9;
  border-color: #4a90d9;
  color: #fff;
  cursor: pointer;
}
.execute-btn.active:hover {
  background: #3a7bc8;
  border-color: #3a7bc8;
}

/* 模式按钮包装与提示 */
.mode-btn-wrap { position: relative; }
.mode-tooltip {
  display: none;
  position: absolute;
  top: calc(100% + 10px);
  left: 50%;
  transform: translateX(-50%);
  width: 320px;
  max-width: calc(100vw - 40px);
  background: #1a1a2e;
  color: #e0e0e0;
  border-radius: 10px;
  padding: 14px 16px;
  font-size: 12px;
  line-height: 1.6;
  z-index: 200;
  box-shadow: 0 6px 24px rgba(0,0,0,0.25);
  pointer-events: none;
}
.mode-tooltip::after {
  content: '';
  position: absolute;
  bottom: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-bottom-color: #1a1a2e;
}
.mode-btn-wrap:hover .mode-tooltip { display: block; }
.mode-tooltip-title { font-size: 14px; font-weight: 700; margin-bottom: 10px; color: #fff; }
.mode-tooltip-section { margin-bottom: 8px; }
.mode-tooltip-section:last-child { margin-bottom: 0; }

/* 表单页 */
.form-page { width: 100%; }

.form-panel {
  background: #fff;
  border-radius: 12px;
  padding: 28px 36px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
  width: 100%;
}
.form-panel > h2 { font-size: 18px; font-weight: 700; color: #1a1a2e; margin-bottom: 24px; padding-bottom: 14px; border-bottom: 1px solid #eee; }
.section { margin-bottom: 24px; }
.section h3 { font-size: 12px; color: #999; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }

/* 自动搭建模式三栏布局 */
.auto-info-row {
  display: flex;
  gap: 16px;
  margin-bottom: 24px;
}
.auto-info-col {
  min-width: 0;
  margin-bottom: 0;
  padding: 16px;
  background: #fafafa;
  border-radius: 8px;
  border: 1px solid #eee;
}
.auto-info-left {
  flex: 1.2;
}
.auto-info-middle {
  flex: 0.9;
}
.auto-info-right {
  flex: 1.4;
}
.auto-info-col h3 {
  font-size: 11px;
  margin-bottom: 12px;
}

.tool-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; }
.tool-card {
  position: relative;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  padding: 10px 6px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.tool-card:hover { border-color: #4a90d9; }
.tool-card.active { border-color: #4a90d9; background: #f0f6ff; }
.tool-icon { font-size: 22px; }
.tool-name { font-size: 12px; font-weight: 600; margin-top: 3px; }
.tool-desc { font-size: 10px; color: #888; margin-top: 2px; }

/* 工具悬停提示 */
.tool-tooltip {
  display: none;
  position: absolute;
  bottom: calc(100% + 8px);
  left: 50%;
  transform: translateX(-50%);
  width: 260px;
  background: #1a1a2e;
  color: #e0e0e0;
  border-radius: 8px;
  padding: 12px 14px;
  font-size: 12px;
  line-height: 1.5;
  z-index: 100;
  box-shadow: 0 4px 16px rgba(0,0,0,0.2);
  pointer-events: none;
}
.tool-tooltip::after {
  content: '';
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 6px solid transparent;
  border-top-color: #1a1a2e;
}
.tool-card:hover .tool-tooltip { display: block; }
.tooltip-section { margin-bottom: 6px; }
.tooltip-section:last-child { margin-bottom: 0; }
.tooltip-label { color: #7eb8f7; font-weight: 600; margin-right: 4px; }

.type-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 8px; }
.type-card {
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  padding: 10px 8px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s;
}
.type-card:hover { border-color: #4a90d9; }
.type-card.active { border-color: #4a90d9; background: #f0f6ff; }
.type-icon { font-size: 22px; }
.type-name { font-size: 12px; font-weight: 600; margin-top: 3px; }
.type-langs { font-size: 10px; color: #888; margin-top: 2px; }

/* 备份选项 */
.backup-option { margin-top: 4px; }
.checkbox-label {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}
.checkbox-label input[type="checkbox"] {
  width: 18px;
  height: 18px;
  margin-top: 2px;
  accent-color: #4a90d9;
  cursor: pointer;
  flex-shrink: 0;
}
.check-text { display: flex; flex-direction: column; gap: 2px; }
.check-title { font-size: 13px; font-weight: 600; color: #333; }
.check-desc { font-size: 11px; color: #888; line-height: 1.4; }

.mode-list { display: flex; flex-direction: row; gap: 8px; flex-wrap: wrap; }
.mode-item {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px;
  border: 2px solid #e8e8e8;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.mode-item:hover { border-color: #4a90d9; }
.mode-item.active { border-color: #4a90d9; background: #f0f6ff; }
.mode-item.disabled {
  opacity: 0.5;
  cursor: not-allowed;
  pointer-events: none;
}
.mode-item.disabled:hover { border-color: #e8e8e8; }
.mode-item input { width: auto; flex-shrink: 0; margin: 0; }
.mode-text { display: flex; flex-direction: column; gap: 1px; }
.mode-label { font-size: 13px; font-weight: 600; line-height: 1.3; }
.mode-desc { font-size: 11px; color: #888; line-height: 1.3; }

.form-group { margin-bottom: 12px; }
.form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.required { color: #e53935; font-weight: 400; }
label { display: block; font-size: 12px; color: #555; margin-bottom: 4px; font-weight: 500; }
input, select, textarea {
  width: 100%;
  padding: 8px 10px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s;
  font-family: inherit;
}
input:focus, select:focus, textarea:focus { border-color: #4a90d9; }
textarea { resize: vertical; }

/* 分支提示 */
.branch-hint { font-size: 11px; color: #888; font-weight: normal; margin-left: 8px; }

/* 进度页 */
.progress-panel-full {
  background: #fff;
  border-radius: 12px;
  padding: 28px 36px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.step-list { margin-bottom: 20px; }
.step-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-radius: 8px;
  margin-bottom: 6px;
  font-size: 14px;
  transition: background 0.15s;
}
.step-item.running { background: #fff8e1; }
.step-item.success { background: #e8f5e9; }
.step-item.failed { background: #ffebee; }
.step-item.waiting_input { background: #e3f2fd; }
.step-icon { font-size: 18px; }
.step-name { font-weight: 500; flex: 1; }
.step-status { font-size: 13px; color: #888; }

.log-panel { margin-top: 20px; }
.log-panel h4 { font-size: 14px; color: #888; margin-bottom: 10px; }
.log-content {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 16px;
  max-height: 500px;
  overflow-y: auto;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  font-size: 13px;
}
.log-line { color: #d4d4d4; line-height: 1.6; }
.log-prefix { color: #6a9955; }

/* 流水线管理信息面板 */
.pipeline-info-panel {
  margin-top: 24px;
  padding: 24px;
  background: linear-gradient(135deg, #f0f6ff 0%, #e8f5e9 100%);
  border-radius: 12px;
  border: 2px solid #4a90d9;
}
.pipeline-info-panel h4 {
  font-size: 18px;
  color: #1a1a2e;
  margin-bottom: 16px;
}
.pipeline-info-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 20px;
}
.pipeline-info-card {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}
.pipeline-info-title {
  font-size: 14px;
  font-weight: 600;
  color: #333;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px solid #eee;
}
.pipeline-info-content {
  font-size: 13px;
  color: #555;
  line-height: 1.7;
}
.pipeline-info-content a {
  color: #4a90d9;
  text-decoration: none;
  font-weight: 500;
}
.pipeline-info-content a:hover {
  text-decoration: underline;
}
.pipeline-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.pipeline-actions .btn-primary {
  padding: 10px 24px;
  background: #4a90d9;
  color: #fff;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  display: inline-block;
}
.pipeline-actions .btn-primary:hover {
  background: #3a7bc8;
}
.pipeline-actions .btn-secondary {
  padding: 10px 24px;
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
}
.pipeline-actions .btn-secondary:hover {
  background: #f5f5f5;
}

/* 结果页 */
.result-panel {
  background: #fff;
  border-radius: 12px;
  padding: 28px 36px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.08);
}

.file-tabs { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; }
.file-tabs button {
  padding: 8px 14px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.file-tabs button.active { background: #4a90d9; color: #fff; border-color: #4a90d9; }

.file-content {
  background: #1e1e1e;
  border-radius: 8px;
  padding: 20px;
  overflow: auto;
  max-height: 600px;
  min-height: 300px;
}
.file-content pre {
  color: #d4d4d4;
  font-size: 13px;
  font-family: 'JetBrains Mono', 'Fira Code', monospace;
  white-space: pre;
  margin: 0;
  line-height: 1.6;
}
.empty { color: #888; font-size: 14px; padding: 60px 20px; text-align: center; }

.output-path {
  margin-top: 16px;
  font-size: 13px;
  color: #888;
  display: flex;
  align-items: center;
  gap: 10px;
}
.output-path code {
  background: #f5f5f5;
  padding: 4px 8px;
  border-radius: 4px;
  font-family: monospace;
  font-size: 12px;
}

/* 页面头部 */
.page-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 24px;
  padding: 18px 28px;
  background: #fff;
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
.page-header h2 { font-size: 18px; font-weight: 700; flex: 1; }
.page-actions { display: flex; gap: 10px; }

.btn-back {
  padding: 8px 18px;
  border: 1px solid #ddd;
  border-radius: 6px;
  background: #fff;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-back:hover { border-color: #4a90d9; color: #4a90d9; }

.btn-secondary {
  padding: 8px 16px;
  background: #f0f0f0;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
  font-weight: 500;
}
.btn-secondary:hover { background: #e0e0e0; }
.btn-small {
  padding: 5px 10px;
  background: #f0f0f0;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  margin-left: 8px;
}

/* 凭据弹窗 */
.modal-overlay {
  position: fixed;
  top: 0; left: 0; right: 0; bottom: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: #fff;
  border-radius: 12px;
  padding: 24px;
  width: 420px;
  max-width: 90vw;
  box-shadow: 0 8px 32px rgba(0,0,0,0.2);
}
.modal h3 { font-size: 16px; font-weight: 700; margin-bottom: 8px; }
.modal-desc { font-size: 13px; color: #666; margin-bottom: 16px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 16px; }

/* 审批弹窗 */
.approval-modal { width: 480px; }
.approval-info {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 16px;
  font-size: 13px;
  color: #555;
}
.approval-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.btn-approve, .btn-reject, .btn-rollback {
  padding: 12px 16px;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
}
.btn-approve {
  background: #e8f5e9;
  color: #2e7d32;
}
.btn-approve:hover { background: #c8e6c9; }
.btn-reject {
  background: #ffebee;
  color: #c62828;
}
.btn-reject:hover { background: #ffcdd2; }
.btn-rollback {
  background: #fff3e0;
  color: #e65100;
}
.btn-rollback:hover { background: #ffe0b2; }

/* 分支选择弹窗 */
.branch-modal { width: 520px; }
.branch-select-list {
  max-height: 240px;
  overflow-y: auto;
  border: 1px solid #eee;
  border-radius: 8px;
  padding: 8px;
  margin-bottom: 16px;
}
.branch-checkbox {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.1s;
  font-size: 13px;
}
.branch-checkbox:hover { background: #f5f7fa; }
.branch-checkbox input { width: auto; margin: 0; }
.branch-name { font-family: 'JetBrains Mono', monospace; font-size: 13px; }
.empty-branches { color: #999; font-size: 13px; text-align: center; padding: 20px; }

.release-strategy-section {
  margin-bottom: 16px;
  padding: 12px;
  background: #f8f9fa;
  border-radius: 8px;
}
.release-strategy-section h4 { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.release-strategy-section select {
  width: 100%;
  padding: 8px;
  border: 1px solid #ddd;
  border-radius: 6px;
  font-size: 12px;
  margin-bottom: 8px;
}
.strategy-options {
  display: flex;
  align-items: center;
  gap: 16px;
  font-size: 12px;
}

/* 中继服务器 */
.relay-toggle { margin-top: 16px; padding-top: 12px; border-top: 1px dashed #ddd; }
.relay-toggle-label { display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.relay-toggle-label input { width: auto; }
.relay-hint { display: block; font-size: 11px; color: #888; margin-top: 4px; margin-left: 22px; }
.relay-config {
  margin-top: 12px;
  padding: 16px;
  background: #f8f9fa;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
}

/* 子配置块（工具服务器配置） */
.sub-config {
  margin-top: 12px;
  padding: 14px;
  background: #fafbfc;
  border-radius: 8px;
  border: 1px dashed #d0d0d0;
}

/* 应用服务器配置行 */
.app-server-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.app-server-row > .form-group {
  flex: 1;
  min-width: 120px;
  margin-bottom: 0;
}

/* 工具服务器配置行 */
.tool-server-row {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.tool-server-row > .form-group {
  flex: 1;
  min-width: 120px;
  margin-bottom: 0;
}

/* 访问方式描述 */
.access-desc {
  font-size: 12px;
  color: #555;
  background: #e8f4fd;
  padding: 8px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  line-height: 1.5;
}

/* 字段提示 */
.field-hint {
  display: block;
  font-size: 11px;
  color: #888;
  margin-top: 4px;
}

/* 跳转链路样式 */
.hop-list { display: flex; flex-direction: column; gap: 12px; margin-bottom: 12px; }
.hop-item {
  padding: 12px;
  background: #fff;
  border: 1px solid #d0d7de;
  border-radius: 8px;
  position: relative;
}
.hop-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  padding-bottom: 8px;
  border-bottom: 1px dashed #e8e8e8;
}
.hop-index {
  font-size: 12px;
  font-weight: 700;
  color: #4a90d9;
}
.hop-type-badge {
  font-size: 11px;
  background: #e8f4fd;
  color: #4a90d9;
  padding: 2px 8px;
  border-radius: 4px;
  font-weight: 600;
}
.hop-remove {
  margin-left: auto;
  background: none;
  border: none;
  font-size: 18px;
  color: #999;
  cursor: pointer;
  padding: 0 4px;
  line-height: 1;
}
.hop-remove:hover { color: #e74c3c; }

/* 跳转链路选项卡 */
.hop-tabs {
  display: flex;
  gap: 4px;
  margin-bottom: 16px;
  border-bottom: 2px solid #e8e8e8;
  padding-bottom: 0;
}
.hop-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-bottom: none;
  border-radius: 6px 6px 0 0;
  cursor: pointer;
  font-size: 12px;
  position: relative;
  bottom: -2px;
  transition: all 0.15s;
}
.hop-tab:hover {
  background: #e8f4fd;
}
.hop-tab.active {
  background: #fff;
  border-color: #4a90d9;
  border-bottom: 2px solid #fff;
  font-weight: 600;
}
.hop-tab-icon {
  font-size: 14px;
}
.hop-tab-label {
  color: #333;
}
.hop-tab-close {
  background: none;
  border: none;
  font-size: 14px;
  color: #999;
  cursor: pointer;
  padding: 0 2px;
  line-height: 1;
  margin-left: 4px;
}
.hop-tab-close:hover {
  color: #e74c3c;
}
.hop-content {
  padding: 16px;
  background: #fff;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  margin-bottom: 12px;
}
.hop-empty {
  text-align: center;
  padding: 24px;
  color: #999;
  background: #f9f9f9;
  border-radius: 8px;
  margin-bottom: 12px;
}
.hop-empty p {
  margin: 0;
}
.hop-empty-hint {
  font-size: 12px;
  color: #bbb;
  margin-top: 8px !important;
}

.hop-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.btn-add-hop {
  padding: 6px 12px;
  background: #f8f9fa;
  border: 1px dashed #ccc;
  border-radius: 6px;
  font-size: 12px;
  color: #666;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-add-hop:hover {
  border-color: #4a90d9;
  color: #4a90d9;
  background: #f0f6ff;
}

/* 多环境 / 负载均衡 */
.env-item {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  background: #fafbfc;
}
.env-item-head {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}
.env-item-head .env-name {
  flex: 2;
}
.env-item-head .env-branch {
  flex: 3;
}
.env-item-server {
  display: flex;
  gap: 8px;
}
.env-item-server input {
  flex: 3;
}
.env-item-server .env-small {
  flex: 2;
}
.btn-remove-env {
  flex: 0 0 auto;
  width: 28px;
  border: 1px solid #e8e8e8;
  border-radius: 6px;
  background: #fff;
  color: #999;
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-remove-env:hover {
  border-color: #e53935;
  color: #e53935;
  background: #fff5f5;
}
.lb-config {
  margin-top: 10px;
  padding: 12px;
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  background: #fafbfc;
}

/* 部署建议 */
.btn-get-rec {
  padding: 8px 16px;
  background: #f0f6ff;
  border: 1px solid #4a90d9;
  border-radius: 6px;
  color: #4a90d9;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-get-rec:hover { background: #e3f2fd; }
.btn-get-rec:disabled { opacity: 0.5; cursor: not-allowed; }

.rec-panel { margin-top: 16px; }
.rec-section {
  margin-bottom: 16px;
  padding: 12px;
  background: #fafbfc;
  border-radius: 8px;
  border: 1px solid #eee;
}
.rec-section h4 { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.rec-best {
  font-size: 12px;
  color: #2e7d32;
  background: #e8f5e9;
  padding: 8px 10px;
  border-radius: 6px;
  margin-bottom: 8px;
}
.rec-item {
  padding: 8px 0;
  border-bottom: 1px solid #eee;
  font-size: 12px;
}
.rec-item:last-child { border-bottom: none; }
.rec-item strong { display: block; margin-top: 4px; }
.rec-item p { color: #666; margin-top: 2px; }
.rec-priority {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.rec-priority.high { background: #e8f5e9; color: #2e7d32; }
.rec-priority.medium { background: #fff3e0; color: #e65100; }

.rec-method { padding: 8px 0; border-bottom: 1px solid #eee; font-size: 12px; }
.rec-method:last-of-type { border-bottom: none; }
.rec-method-header { display: flex; align-items: center; gap: 8px; }
.rec-method-header.recommended strong { color: #2e7d32; }
.rec-badge {
  background: #e8f5e9;
  color: #2e7d32;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 600;
}
.rec-method p { color: #666; margin-top: 4px; }
.rec-pros-cons { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.rec-pro { font-size: 11px; color: #2e7d32; }
.rec-con { font-size: 11px; color: #e65100; }
.rec-note {
  margin-top: 8px;
  padding: 6px 10px;
  background: #e3f2fd;
  border-radius: 6px;
  font-size: 12px;
  color: #1565c0;
}

.rec-steps {
  margin: 6px 0 0 20px;
  font-size: 12px;
  color: #555;
}
.rec-steps li { margin-bottom: 2px; }

.rec-tips { margin-top: 12px; }
.rec-tips h4 { font-size: 13px; font-weight: 600; margin-bottom: 8px; }
.rec-tip {
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12px;
  margin-bottom: 6px;
}
.rec-tip.info { background: #e3f2fd; color: #1565c0; }
.rec-tip.warning { background: #fff3e0; color: #e65100; }

/* 响应式布局 */
@media (max-width: 900px) {
  .form-panel, .result-panel, .progress-panel-full { padding: 20px 24px; }
  .page-header { padding: 14px 20px; }
}
@media (max-width: 640px) {
  .container { padding: 12px; }
  .header { padding: 16px 0 8px; }
  .logo { font-size: 20px; }
  .tool-grid { grid-template-columns: repeat(2, 1fr); }
  .type-grid { grid-template-columns: repeat(2, 1fr); }
  .form-row { grid-template-columns: 1fr; }
  .form-panel { padding: 16px; }
  .result-panel, .progress-panel-full { padding: 16px; }
  .page-header { flex-wrap: wrap; padding: 12px 16px; }
  .page-header h2 { font-size: 16px; }
}
</style>
