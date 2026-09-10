# run_studio.py
"""
DataSphere Studio - Navicat Web Edition 启动入口
运行命令: python run_studio.py [端口，默认8088]
"""
import sys
import webbrowser
import threading
import time
from web.server import start_server

if __name__ == '__main__':
    port = 8088
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except Exception:
            pass

    url = f"http://localhost:{port}"

    def open_browser():
        time.sleep(1.2)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    # 后台线程尝试唤起默认浏览器
    threading.Thread(target=open_browser, daemon=True).start()

    # 启动多线程 Web 服务器
    start_server(port=port)
