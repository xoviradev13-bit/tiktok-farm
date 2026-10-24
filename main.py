import sys
import os
import time
import threading
import webbrowser
import uvicorn

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
try:
    import webview
except ImportError:
    webview = None

# Đảm bảo đường dẫn thư mục hiện tại nằm trong sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import socket
from backend.config import SERVER_HOST, SERVER_PORT
from backend.database import init_db, log_event
from backend.logger import get_logger

logger = get_logger("main")

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

def kill_process_on_port(port: int):
    """Tự động giải phóng cổng nếu có tiến trình cũ chiếm dụng (NIST SP 800-218 / Command Injection Prevention)"""
    try:
        import subprocess
        output = subprocess.check_output(["netstat", "-ano"], text=True, stderr=subprocess.DEVNULL)
        target = f":{port}"
        for line in output.strip().split("\n"):
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in parts and any(target in p for p in parts[:2]):
                pid = parts[-1]
                if pid.isdigit() and int(pid) > 0:
                    subprocess.run(["taskkill", "/F", "/PID", pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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

    # Khởi động bộ lập lịch chạy ngầm theo cấu hình đã lưu
    from backend.scheduler import scheduler
    from backend.database import get_connection
    scheduler.load_settings()
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'scheduler_running'")
        row = cursor.fetchone()
        conn.close()
        should_run = (row[0] == "1") if row else True
    except Exception:
        should_run = True

    if should_run:
        scheduler.start()
        print("[SCHEDULER] Auto-Pilot da khoi dong tu dong.")
    else:
        scheduler.stop()
        print("[SCHEDULER] Auto-Pilot dang o trang thai TAM DUNG theo cau hinh nguoi dung.")

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

    # Kiểm tra cờ khởi động ẩn vào Khay Hệ Thống (ví dụ khi Windows tự mở máy)
    is_minimized_boot = "--minimized" in sys.argv or "--tray" in sys.argv

    # Khởi tạo System Tray Icon (chạy độc lập trên background thread)
    from backend.modules.tray_manager import setup_tray

    # Chạy giao diện Desktop trên Main Thread (Bắt buộc cho Windows GUI)
    if webview:
        try:
            window = webview.create_window(
                "TikTok Auto Farm & AI Video Engine (GPMLogin)",
                dashboard_url,
                width=1380,
                height=860,
                min_size=(1024, 700),
                hidden=is_minimized_boot,
                maximized=not is_minimized_boot
            )
            # Kết nối cửa sổ với System Tray
            setup_tray(window)
            if is_minimized_boot:
                print("🔒 [BOOT] Khởi động ngầm thành công. Ứng dụng đang chạy trong Khay Hệ Thống.")
            webview.start()
            sys.exit(0)
        except Exception as e:
            print(f"[UI] Không thể mở pywebview window: {e}. Đang chuyển sang trình duyệt...")

    # Fallback nếu không dùng pywebview: Mở trình duyệt mặc định và giữ main thread sống
    setup_tray(window=None)
    if not is_minimized_boot:
        webbrowser.open(dashboard_url)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[STOP] Đã dừng ứng dụng.")
