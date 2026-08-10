"""多分支发布流程工具 - 审批门禁、自动合并、回滚"""


def get_release_strategy(c):
    """获取发布策略配置

    Returns:
        dict: {
            "strategy": "auto_merge" | "manual_merge" | "no_merge",
            "autoMergeDelay": int (秒),
            "requireApproval": bool,
            "enableRollback": bool,
            "mainBranch": str
        }
    """
    strategy = getattr(c, 'releaseStrategy', None)
    if strategy and isinstance(strategy, dict):
        return strategy
    return {
        "strategy": "auto_merge",
        "autoMergeDelay": 300,
        "requireApproval": True,
        "enableRollback": True,
        "mainBranch": "main",
    }


def get_branches(c):
    """获取分支列表"""
    branches = getattr(c, 'branches', None)
    if branches and isinstance(branches, list) and len(branches) > 0:
        return branches
    return [getattr(c, 'branch', 'main')]


def is_multi_branch_workflow(c):
    """是否启用了多分支发布流程"""
    branches = get_branches(c)
    strategy = get_release_strategy(c)
    return len(branches) > 1 and strategy.get("strategy") != "no_merge"


# ============================================================
# Jenkins 审批 + 合并 + 回滚阶段
# ============================================================

def jenkins_approval_stage(strategy):
    """Jenkins 审批门禁阶段"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""        stage('审批确认 - 合并到 {main_branch}') {{
            input {{
                message '测试环境验证通过，是否合并到 {main_branch} 分支？'
                ok '确认合并'
                parameters {{
                    choice(name: 'ACTION', choices: ['merge', 'reject', 'rollback'], description: '选择操作：merge=合并, reject=拒绝, rollback=回滚')
                }}
            }}
            steps {{
                script {{
                    env.MERGE_ACTION = env.ACTION
                    echo "审批结果: ${{env.MERGE_ACTION}}"
                }}
            }}
        }}"""


def jenkins_merge_stage(strategy):
    """Jenkins 自动合并阶段"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""        stage('合并到 {main_branch}') {{
            when {{
                expression {{ env.MERGE_ACTION == 'merge' }}
            }}
            steps {{
                script {{
                    sh '''
                        echo "===== 开始合并到 {main_branch} ====="
                        git checkout {main_branch}
                        git merge origin/${{BRANCH}} --no-edit
                        git push origin {main_branch}
                        echo "===== 合并完成 ====="
                    '''
                }}
            }}
        }}"""


def jenkins_reject_stage():
    """Jenkins 拒绝合并阶段"""
    return """        stage('拒绝合并') {
            when {
                expression { env.MERGE_ACTION == 'reject' }
            }
            steps {
                echo "⚠️ 审批未通过，分支不会合并到主分支"
                echo "请检查测试报告并修复问题后重新提交"
            }
        }"""


def jenkins_rollback_stage(strategy):
    """Jenkins 回滚阶段"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""        stage('回滚') {{
            when {{
                expression {{ env.MERGE_ACTION == 'rollback' }}
            }}
            steps {{
                script {{
                    sh '''
                        echo "===== 开始回滚 ====="
                        # 获取上一个稳定版本标签
                        PREV_TAG=$(git tag --sort=-creatordate | grep '^v[0-9]' | head -2 | tail -1)
                        if [ -z "$PREV_TAG" ]; then
                            echo "未找到可回滚的版本标签"
                            exit 1
                        fi
                        echo "回滚到版本: $PREV_TAG"
                        git checkout $PREV_TAG
                        echo "===== 回滚完成 ====="
                    '''
                }}
            }}
        }}"""


# ============================================================
# GitHub Actions 审批 + 合并 + 回滚
# ============================================================

def github_approval_job(strategy):
    """GitHub Actions 审批 job"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""
  approve-merge:
    name: 审批确认 - 合并到 {main_branch}
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: production
      url: ${{{{ github.server_url }}}}/${{{{ github.repository }}}}
    steps:
      - name: 等待审批
        run: |
          echo "✅ 测试环境验证通过"
          echo "分支: ${{{{ github.ref_name }}}}"
          echo "目标分支: {main_branch}"
          echo "请在 GitHub Environment 中确认合并操作"
"""


def github_merge_job(strategy):
    """GitHub Actions 自动合并 job"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""
  merge-to-main:
    name: 合并到 {main_branch}
    needs: approve-merge
    runs-on: ubuntu-latest
    if: ${{{{ needs.approve-merge.result == 'success' }}}}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: {main_branch}
      - name: 合并分支
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git merge origin/${{{{ github.ref_name }}}} --no-edit
          git push origin {main_branch}
          echo "✅ 已合并到 {main_branch}"
"""


def github_rollback_job(strategy):
    """GitHub Actions 回滚 job"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""
  rollback:
    name: 回滚到上一版本
    needs: approve-merge
    runs-on: ubuntu-latest
    if: ${{{{ needs.approve-merge.result == 'failure' }}}}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          ref: {main_branch}
      - name: 回滚
        run: |
          PREV_TAG=$(git tag --sort=-creatordate | grep '^v[0-9]' | head -2 | tail -1)
          if [ -z "$PREV_TAG" ]; then
            echo "⚠️ 未找到可回滚的版本"
            exit 1
          fi
          echo "回滚到: $PREV_TAG"
          git checkout $PREV_TAG
          echo "✅ 回滚完成"
"""


# ============================================================
# GitLab CI 审批 + 合并 + 回滚
# ============================================================

def gitlab_approval_jobs(strategy):
    """GitLab CI 审批 + 合并 + 回滚 jobs"""
    main_branch = strategy.get("mainBranch", "main")
    return f"""
approve_merge:
  stage: deploy
  script:
    - echo "✅ 测试验证通过，准备合并到 {main_branch}"
    - echo "请在 GitLab 中确认合并操作"
  environment:
    name: production
  when: manual
  only:
    - merge_requests
  allow_failure: false

merge_to_main:
  stage: deploy
  script:
    - git checkout {main_branch}
    - git merge origin/$CI_COMMIT_BRANCH --no-edit
    - git push origin {main_branch}
    - echo "✅ 已合并到 {main_branch}"
  only:
    - merge_requests
  needs: ["approve_merge"]

reject_merge:
  stage: deploy
  script:
    - echo "⚠️ 审批未通过，分支不会合并到主分支"
    - echo "请检查测试报告并修复问题"
  when: manual
  only:
    - merge_requests
  allow_failure: true

rollback_deploy:
  stage: deploy
  script:
    - echo "===== 开始回滚 ====="
    - PREV_TAG=$(git tag --sort=-creatordate | grep '^v[0-9]' | head -2 | tail -1)
    - echo "回滚到版本: $PREV_TAG"
    - git checkout $PREV_TAG
    - echo "===== 回滚完成 ====="
  when: manual
  only:
    - {main_branch}
  allow_failure: true
"""


# ============================================================
# 回滚脚本
# ============================================================

def build_rollback_script(c):
    """生成通用回滚脚本"""
    branches = get_branches(c)
    strategy = get_release_strategy(c)
    main_branch = strategy.get("mainBranch", "main")
    project = c.projectName

    return f"""#!/bin/bash
# ============================================
# 回滚脚本 - {project}
# 生成: auto-cicd
# 主分支: {main_branch}
# ============================================

set -e

RED='\\033[0;31m'
GREEN='\\033[0;32m'
YELLOW='\\033[1;33m'
NC='\\033[0m'

echo "========================================"
echo "  {project} 回滚工具"
echo "========================================"
echo ""

# 显示最近的版本标签
echo "最近的版本标签:"
git tag --sort=-creatordate | grep '^v[0-9]' | head -10 | nl
echo ""

# 选择回滚目标
read -p "请输入要回滚到的版本标签 (如 v1.0.0): " TARGET_TAG

if [ -z "$TARGET_TAG" ]; then
    echo -e "${{RED}}错误: 未输入版本标签${{NC}}"
    exit 1
fi

# 验证标签存在
if ! git rev-parse "$TARGET_TAG" >/dev/null 2>&1; then
    echo -e "${{RED}}错误: 版本标签 $TARGET_TAG 不存在${{NC}}"
    exit 1
fi

echo ""
echo -e "${{YELLOW}}即将回滚到: $TARGET_TAG${{NC}}"
echo -e "${{YELLOW}}当前分支: $(git branch --show-current)${{NC}}"
echo ""

read -p "确认回滚? (y/N): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "已取消回滚"
    exit 0
fi

# 创建回滚前的备份标签
BACKUP_TAG="rollback-backup-$(date +%Y%m%d%H%M%S)"
git tag "$BACKUP_TAG"
echo -e "${{GREEN}}已创建备份标签: $BACKUP_TAG${{NC}}"

# 执行回滚
CURRENT_BRANCH=$(git branch --show-current)
git checkout "$TARGET_TAG"

echo ""
echo -e "${{GREEN}}========================================${{NC}}"
echo -e "${{GREEN}}  回滚完成！${{NC}}"
echo -e "${{GREEN}}  已回滚到: $TARGET_TAG${{NC}}"
echo -e "${{GREEN}}  备份标签: $BACKUP_TAG${{NC}}"
echo -e "${{GREEN}}========================================${{NC}}"
echo ""
echo "如需恢复，执行: git checkout $CURRENT_BRANCH"
"""


# ============================================================
# 发布说明 README
# ============================================================

def build_release_readme(c):
    """生成多分支发布流程说明"""
    branches = get_branches(c)
    strategy = get_release_strategy(c)
    main_branch = strategy.get("mainBranch", "main")
    project = c.projectName
    merge_strategy = strategy.get("strategy", "auto_merge")

    strategy_desc = {
        "auto_merge": "自动合并（测试通过后自动合并到主分支）",
        "manual_merge": "手动合并（测试通过后需手动确认合并）",
        "no_merge": "不合并（仅测试，不合并到主分支）",
    }

    branch_list = "\\n".join(f"  - {b}" for b in branches)

    return f"""# {project} 多分支发布流程

## 发布策略

- **策略**: {strategy_desc.get(merge_strategy, merge_strategy)}
- **主分支**: `{main_branch}`
- **参与分支**:
{branch_list}

## 发布流程

```
功能分支开发 → 提交测试 → 测试验证 → 审批确认 → 合并到主分支
                                  ↓ 不通过
                              拒绝合并 / 回滚
```

### 详细步骤

1. **开发阶段**
   - 各开发者在独立分支上开发（{', '.join(branches)}）
   - 完成后提交到对应分支

2. **测试阶段**
   - 流水线自动拉取各分支代码
   - 执行构建、测试
   - 部署到测试环境

3. **审批阶段**
   - 测试通过后，触发审批流程
   - 审批人确认是否可以合并
   - 可选择：合并 / 拒绝 / 回滚

4. **合并阶段**
   - 审批通过后，自动合并到 `{main_branch}` 分支
   - 触发主分支的部署流水线

5. **回滚**
   - 如发现问题，可执行回滚
   - 回滚到上一个稳定版本标签

## 回滚操作

```bash
# 使用回滚脚本
./rollback.sh

# 或手动回滚
git tag --sort=-creatordate | grep '^v[0-9]' | head -5
git checkout <目标版本标签>
```

## 注意事项

- 合并前确保所有测试通过
- 回滚操作会创建备份标签，可随时恢复
- 建议每次发布前打版本标签（如 v1.0.0）
"""
