import sys
import os
import time
import threading
import webbrowser
import uvicorn
try:
    import webview
except ImportError:
    webview = None

# Đảm bảo đường dẫn thư mục hiện tại nằm trong sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import socket
from backend.config import SERVER_HOST, SERVER_PORT
from backend.database import init_db, log_event

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def kill_process_on_port(port: int):
    """Tự động giải phóng cổng nếu có tiến trình cũ chiếm dụng"""
    try:
        import subprocess
        output = subprocess.check_output(f"netstat -ano | findstr :{port}", shell=True, text=True)
        for line in output.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in parts:
                pid = parts[-1]
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(0.5)
    except Exception:
        pass

def start_server():
    """Khởi động máy chủ FastAPI Local"""
    config = uvicorn.Config("backend.app:app", host=SERVER_HOST, port=SERVER_PORT, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    init_db()
    log_event("INFO", "Khởi động ứng dụng Desktop TikTok Farm...")

    # Giải phóng port nếu bị kẹt từ phiên trước
    if is_port_in_use(SERVER_PORT, SERVER_HOST):
        print(f"[PORT] Cổng {SERVER_PORT} đang bận, đang tự động giải phóng...")
        kill_process_on_port(SERVER_PORT)

    # Khởi động bộ lập lịch chạy ngầm
    from backend.scheduler import scheduler
    scheduler.start()

    # Khởi chạy server FastAPI trong background thread
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Chờ server khởi động
    time.sleep(1.2)
    dashboard_url = f"http://{SERVER_HOST}:{SERVER_PORT}"
    print(f"\n=======================================================")
    print(f"🚀 TIKTOK AUTO FARM & AI ENGINE ĐANG CHẠY TẠI:")
    print(f"👉 {dashboard_url}")
    print(f"=======================================================\n")

    # Chạy giao diện Desktop trên Main Thread (Bắt buộc cho Windows GUI)
    if webview:
        try:
            webview.create_window(
                "TikTok Auto Farm & AI Video Engine (GPMLogin)",
                dashboard_url,
                width=1380,
                height=860,
                min_size=(1024, 700)
            )
            webview.start()
            sys.exit(0)
        except Exception as e:
            print(f"[UI] Không thể mở pywebview window: {e}. Đang chuyển sang trình duyệt...")

    # Fallback nếu không dùng pywebview: Mở trình duyệt mặc định và giữ main thread sống
    webbrowser.open(dashboard_url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Đã dừng ứng dụng.")
