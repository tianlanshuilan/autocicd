"""离线构建命令生成

支持三种离线依赖来源：
1. 预拉取模式：平台从 BOM 地址拉取到 .offline-deps/
2. 本地检测模式：开发者已提交依赖到仓库（如 maven-repo/、vendor/）
3. 独立仓库模式：从独立依赖仓库克隆到 .dep-repo/

生成的流水线使用离线模式编译打包，无需外网访问，且不修改 BOM 依赖地址。
"""


def offline_enabled(c) -> bool:
    """判断是否启用离线构建（引擎预拉取或检测到本地依赖后设置 depsBundled=True）"""
    return bool(getattr(c, 'depsBundled', False))


def has_dep_repo(c) -> bool:
    """判断是否配置了独立依赖仓库"""
    return bool(getattr(c, 'depRepoUrl', ''))


def dep_repo_url(c) -> str:
    """获取依赖仓库地址"""
    return getattr(c, 'depRepoUrl', '')


def dep_repo_branch(c) -> str:
    """获取依赖仓库分支"""
    return getattr(c, 'depRepoBranch', 'main')


def _get_deps_path(c, default_path: str) -> str:
    """获取依赖路径（优先使用检测到的本地路径，否则使用默认路径）"""
    # 如果引擎检测到本地依赖，会在 config 中设置 detectedDepsPath
    detected = getattr(c, 'detectedDepsPath', '')
    if detected:
        return f"./{detected}"
    return default_path


def maven_build_cmd(c) -> str:
    if offline_enabled(c):
        repo_path = _get_deps_path(c, "./.offline-deps/maven-repo")
        # 支持多种 Maven 本地仓库路径
        if "maven-repo" in repo_path or ".m2/repository" in repo_path:
            return f"mvn -o -B -Dmaven.repo.local={repo_path} clean package -DskipTests"
        elif "lib" in repo_path:
            return f"mvn -o -B -Dmaven.repo.local={repo_path} clean package -DskipTests"
        else:
            return f"mvn -o -B -Dmaven.repo.local={repo_path} clean package -DskipTests"
    return "mvn clean package -DskipTests"


def maven_test_cmd(c) -> str:
    if offline_enabled(c):
        repo_path = _get_deps_path(c, "./.offline-deps/maven-repo")
        return f"mvn -o -B -Dmaven.repo.local={repo_path} test"
    return "mvn test"


def npm_install_cmd(c) -> str:
    if offline_enabled(c):
        cache_path = _get_deps_path(c, "./.offline-deps/npm-cache")
        # 如果检测到 node_modules，直接使用（无需 --offline）
        if "node_modules" in cache_path:
            return "npm ci"
        return f"npm ci --offline --cache {cache_path}"
    return "npm ci"


def npm_build_cmd(c) -> str:
    return f"{npm_install_cmd(c)} && npm run build"


def pip_install_cmd(c, target: str = "") -> str:
    suffix = f" -t {target}" if target else ""
    if offline_enabled(c):
        pkg_path = _get_deps_path(c, "./.offline-deps/pip-packages")
        return f"pip install --no-index --find-links={pkg_path} -r requirements.txt{suffix}"
    return f"pip install -r requirements.txt{suffix}"


def go_build_cmd(c, cgo_disabled: bool = False) -> str:
    prefix = "CGO_ENABLED=0 " if cgo_disabled else ""
    if offline_enabled(c):
        # Go 默认使用 vendor 目录（go 1.14+ 自动检测）
        return f"{prefix}go build -mod=vendor -o app ."
    return f"{prefix}go build -o app ."
