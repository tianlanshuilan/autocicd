# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 配置文件 - CI/CD 流水线自动搭建平台
使用方法: pyinstaller auto-cicd.spec
"""
import os
import sys
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

# 后端模板文件（如果有）
templates_dir = os.path.join(ROOT, 'backend', 'templates')
if os.path.exists(templates_dir):
    datas.append((templates_dir, 'backend/templates'))

schemas_dir = os.path.join(ROOT, 'backend', 'schemas')
if os.path.exists(schemas_dir):
    datas.append((schemas_dir, 'backend/schemas'))

# 后端 Python 模块（作为数据文件打包，确保运行时可访问）
backend_dir = os.path.join(ROOT, 'backend')
if os.path.isdir(backend_dir):
    # 收集所有 .py 文件
    for root_dir, dirs, files in os.walk(backend_dir):
        # 跳过 __pycache__
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for f in files:
            if f.endswith('.py'):
                src = os.path.join(root_dir, f)
                rel = os.path.relpath(root_dir, ROOT)
                datas.append((src, rel))
    print("INFO: 已包含后端 Python 模块")

# 离线安装包（兜底方案）
bundled_tools_dir = os.path.join(ROOT, 'bundled-tools')
if os.path.exists(bundled_tools_dir) and os.listdir(bundled_tools_dir):
    datas.append((bundled_tools_dir, 'bundled-tools'))
    print("INFO: 已包含离线安装包（兜底方案）")
else:
    print("WARNING: bundled-tools 目录为空或不存在，离线安装包不可用")
    print("  运行 ./download-bundled-tools.sh 下载离线包")

a = Analysis(
    ['standalone.py'],
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
        'aiohttp',
        # SSH
        'paramiko',
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
        'numpy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='auto-cicd',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # 显示控制台输出
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # 可以设置图标路径
)
