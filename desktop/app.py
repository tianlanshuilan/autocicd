"""
CI/CD 流水线自动搭建平台 - 桌面应用入口
使用 pywebview 创建原生窗口，内嵌 Web 界面
"""
import sys
import os
import threading
import time
import socket
import webbrowser


def get_base_path():
    """获取应用基础路径（兼容开发环境和打包环境）"""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def get_frontend_path():
    """获取前端静态文件路径"""
    base = get_base_path()
    
    # 打包后前端文件在 _MEIPASS/frontend/dist 目录
    frontend_path = os.path.join(base, 'frontend', 'dist')
    if os.path.exists(frontend_path):
        return frontend_path
    
    return None


def get_icon_path():
    """获取应用图标路径"""
    base = get_base_path()
    
    # 优先使用 desktop/icons 目录
    icon_candidates = [
        os.path.join(base, 'desktop', 'icons', 'icon.png'),
        os.path.join(base, 'desktop', 'icons', 'icon.ico'),
        os.path.join(base, 'frontend', 'dist', 'favicon.png'),
    ]
    
    for path in icon_candidates:
        if os.path.exists(path):
            return path
    
    return None


def find_free_port():
    """查找可用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


def start_server(port, ready_event):
    """在后台线程启动 FastAPI 服务"""
    import uvicorn
    
    # 确保 backend 目录在 Python 路径中
    base_path = get_base_path()
    backend_path = os.path.join(base_path, 'backend')
    if os.path.isdir(backend_path) and backend_path not in sys.path:
        sys.path.insert(0, backend_path)
    
    # 导入后端 API
    from main import app
    
    # 挂载前端静态文件
    frontend_path = get_frontend_path()
    if frontend_path and os.path.exists(frontend_path):
        from fastapi.staticfiles import StaticFiles
        from fastapi.responses import FileResponse
        
        # 挂载静态资源目录
        assets_path = os.path.join(frontend_path, 'assets')
        if os.path.isdir(assets_path):
            app.mount("/assets", StaticFiles(directory=assets_path), name="static-assets")
        
        @app.get("/", include_in_schema=False)
        async def serve_index():
            return FileResponse(os.path.join(frontend_path, "index.html"))
        
        @app.get("/{path:path}", include_in_schema=False)
        async def serve_spa(path: str):
            api_prefixes = ("api/", "ws/", "docs", "openapi", "redoc")
            if any(path.startswith(p) for p in api_prefixes):
                return {"error": "Not found"}
            file_path = os.path.join(frontend_path, path)
            if os.path.isfile(file_path):
                return FileResponse(file_path)
            return FileResponse(os.path.join(frontend_path, "index.html"))
    
    # 启动服务器
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    
    # 标记服务已启动
    ready_event.set()
    server.run()


class Api:
    """pywebview JS API"""
    def get_version(self):
        return "1.0.0"
    
    def open_external(self, url):
        """在外部浏览器打开链接"""
        webbrowser.open(url)


def main():
    """主入口"""
    import webview
    
    # 查找可用端口
    port = find_free_port()
    url = f"http://127.0.0.1:{port}"
    
    # 服务就绪事件
    ready_event = threading.Event()
    
    # 在后台线程启动服务
    server_thread = threading.Thread(
        target=start_server, 
        args=(port, ready_event),
        daemon=True
    )
    server_thread.start()
    
    # 等待服务启动
    ready_event.wait(timeout=10)
    time.sleep(0.5)  # 额外等待确保服务完全就绪
    
    # 创建窗口
    window = webview.create_window(
        title="CI/CD 流水线自动搭建平台",
        url=url,
        width=1280,
        height=800,
        min_size=(800, 600),
        resizable=True,
        text_select=True,
        js_api=Api()
    )
    
    # 启动 webview（阻塞）
    webview.start(debug=False)


if __name__ == "__main__":
    main()
