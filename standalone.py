"""
CI/CD 流水线自动搭建平台 - 独立打包入口
打包后运行此文件即可启动服务，同时提供 API 和前端静态文件
"""
import sys
import os
import webbrowser
import threading
import time

# PyInstaller 打包后的资源路径
def get_base_path():
    """获取应用基础路径（兼容开发环境和打包环境）"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后的路径
        return sys._MEIPASS
    else:
        # 开发环境
        return os.path.dirname(os.path.abspath(__file__))


def get_frontend_path():
    """获取前端静态文件路径"""
    base = get_base_path()
    
    # 打包后前端文件在 _MEIPASS/frontend/dist 目录
    frontend_path = os.path.join(base, 'frontend', 'dist')
    if os.path.exists(frontend_path):
        return frontend_path
    
    # 开发环境：从项目根目录的 frontend/dist 获取
    project_root = os.path.dirname(os.path.abspath(__file__))
    dev_frontend = os.path.join(project_root, 'frontend', 'dist')
    if os.path.exists(dev_frontend):
        return dev_frontend
    
    return None


def open_browser(port):
    """延迟打开浏览器"""
    time.sleep(2)
    url = f"http://localhost:{port}"
    print(f"\n{'='*50}")
    print(f"  CI/CD 流水线自动搭建平台已启动！")
    print(f"  访问地址: {url}")
    print(f"{'='*50}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    """主入口"""
    import uvicorn
    
    # 确保 backend 目录在 Python 路径中
    base_path = get_base_path()
    backend_path = os.path.join(base_path, 'backend')
    if os.path.isdir(backend_path) and backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    # 开发环境：也添加 backend 目录
    dev_backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
    if os.path.isdir(dev_backend) and dev_backend not in sys.path:
        sys.path.insert(0, dev_backend)

    # 导入后端 API
    from main import app

    # 挂载前端静态文件
    frontend_path = get_frontend_path()
    if frontend_path and os.path.exists(frontend_path):
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        
        print(f"前端文件路径: {frontend_path}")
        
        # 挂载静态资源目录
        assets_path = os.path.join(frontend_path, 'assets')
        if os.path.isdir(assets_path):
            app.mount("/assets", StaticFiles(directory=assets_path), name="static-assets")
        
        # 添加前端路由（放在最后，作为 fallback）
        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(os.path.join(frontend_path, "index.html"))
        
        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            # 如果是 API 路由，跳过
            api_prefixes = ("api/", "ws/", "docs", "openapi", "redoc")
            if any(path.startswith(p) for p in api_prefixes):
                return {"error": "Not found"}
            # 尝试返回静态文件
            file_path = os.path.join(frontend_path, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            # 否则返回 index.html（SPA fallback）
            return FileResponse(os.path.join(frontend_path, "index.html"))
    else:
        print(f"警告: 前端文件未找到，仅启动 API 服务")
        @app.get("/")
        async def no_frontend():
            return {
                "message": "CI/CD 流水线自动搭建平台 API",
                "docs": "/docs",
                "warning": "前端文件未找到，请确保 frontend/dist 目录存在"
            }

    # 启动参数
    port = int(os.environ.get("PORT", 8000))
    host = os.environ.get("HOST", "0.0.0.0")

    # 打开浏览器
    threading.Thread(target=open_browser, args=(port,), daemon=True).start()

    # 启动服务器
    print(f"启动 CI/CD 流水线自动搭建平台...")
    print(f"服务器地址: http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
