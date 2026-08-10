# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件 - CI/CD 流水线自动搭建平台（桌面应用版）
使用方法: pyinstaller auto-cicd-desktop.spec
"""
import os
import sys
import platform
from PyInstaller.utils.hooks import copy_metadata

block_cipher = None

# 项目根目录
ROOT = os.path.abspath('.')

# 收集所有需要打包的数据文件
datas = []

# 前端构建产物
frontend_dist = os.path.join(ROOT, 'frontend', 'dist')
if os.path.exists(frontend_dist):
    datas.append((frontend_dist, 'frontend/dist'))
else:
    print("WARNING: frontend/dist 目录不存在，请先运行 npm run build")

# 后端模板文件
templates_dir = os.path.join(ROOT, 'backend', 'templates')
if os.path.exists(templates_dir):
    datas.append((templates_dir, 'backend/templates'))

schemas_dir = os.path.join(ROOT, 'backend', 'schemas')
if os.path.exists(schemas_dir):
    datas.append((schemas_dir, 'backend/schemas'))

# 后端 Python 模块
backend_dir = os.path.join(ROOT, 'backend')
if os.path.isdir(backend_dir):
    for root_dir, dirs, files in os.walk(backend_dir):
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py'):
                src = os.path.join(root_dir, f)
                rel = os.path.relpath(root_dir, ROOT)
                datas.append((src, rel))
    print("INFO: 已包含后端 Python 模块")

# 桌面图标
icons_dir = os.path.join(ROOT, 'desktop', 'icons')
if os.path.isdir(icons_dir):
    datas.append((icons_dir, 'desktop/icons'))
    print("INFO: 已包含桌面图标")

# 离线安装包（可选，桌面版可不包含以减小体积）
include_bundled = os.environ.get('INCLUDE_BUNDLED_TOOLS', '0') == '1'
if include_bundled:
    bundled_tools_dir = os.path.join(ROOT, 'bundled-tools')
    if os.path.exists(bundled_tools_dir) and os.listdir(bundled_tools_dir):
        datas.append((bundled_tools_dir, 'bundled-tools'))
        print("INFO: 已包含离线安装包")
else:
    print("INFO: 桌面版默认不包含离线安装包（设置 INCLUDE_BUNDLED_TOOLS=1 可包含）")

# 图标路径
icon_path = None
if platform.system() == 'Darwin':
    icns = os.path.join(ROOT, 'desktop', 'icons', 'icon.icns')
    if os.path.exists(icns):
        icon_path = icns
elif platform.system() == 'Windows':
    ico = os.path.join(ROOT, 'desktop', 'icons', 'icon.ico')
    if os.path.exists(ico):
        icon_path = ico
else:
    png = os.path.join(ROOT, 'desktop', 'icons', 'icon.png')
    if os.path.exists(png):
        icon_path = png

a = Analysis(
    ['desktop/app.py'],
    pathex=[ROOT, os.path.join(ROOT, 'backend')],
    binaries=[],
    datas=datas,
    hiddenimports=[
        # FastAPI 相关
        'fastapi',
        'uvicorn',
        'starlette',
        'starlette.staticfiles',
        'starlette.websockets',
        'pydantic',
        # WebSocket
        'websockets',
        # HTTP 客户端
        'httpx',
        'requests',
        'aiohttp',
        # SSH
        'paramiko',
        'ssh2',
        # pywebview
        'webview',
        # 生成器模块
        'generators',
        'generators.jenkins',
        'generators.aliyun',
        'generators.huawei',
        'generators.tencent',
        'generators.github',
        'generators.gitlab',
        'generators.runner',
        # Pipeline 模块
        'pipeline',
        'pipeline.engine',
        'pipeline.credential',
        'pipeline.ssh_ops',
        'pipeline.git_ops',
        # 其他
        'recommendations',
        'yaml',
        'jinja2',
        'multipart',
        'python_multipart',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'matplotlib',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# macOS 上使用 onedir 模式生成 .app 包
if platform.system() == 'Darwin':
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name='AutoCICD',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        console=False,  # 不显示控制台
        disable_windowed_traceback=False,
        argv_emulation=True,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )
    
    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        upx_exclude=[],
        name='AutoCICD',
    )
    
    app = BUNDLE(
        coll,
        name='AutoCICD.app',
        icon=icon_path,
        bundle_identifier='com.autocicd.desktop',
        info_plist={
            'CFBundleName': 'CI/CD 流水线自动搭建平台',
            'CFBundleDisplayName': 'AutoCICD',
            'CFBundleShortVersionString': '1.0.0',
            'NSHighResolutionCapable': True,
            'LSMinimumSystemVersion': '10.15',
        }
    )
else:
    # Windows 和 Linux 使用单文件模式
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='AutoCICD',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,  # 不显示控制台
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon_path,
    )
