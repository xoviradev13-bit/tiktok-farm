"""
tray_manager.py
---------------
Quản lý Khay Hệ Thống (System Tray) và Khởi Động Cùng Windows (Auto-start)
cho ứng dụng Desktop TikTok Auto Farm.

Tính năng:
1. Thu nhỏ xuống System Tray khi bấm nút Đóng (X) hoặc Thu nhỏ (Minimize).
2. Biểu tượng khay với Menu điều khiển nhanh:
   - Mở Bảng Điều Khiển
   - Quét Follower Tất Cả Nick (ZeroRAM)
   - Bật / Tạm Dừng Lập Lịch Auto-Pilot
   - Khởi động cùng Windows (Bật/Tắt)
   - Thu nhỏ xuống Khay khi đóng (Bật/Tắt)
   - Thoát ứng dụng hoàn toàn
3. Tự khởi động cùng Windows qua Registry (HKEY_CURRENT_USER Run):
   - Dùng pythonw.exe để chạy ngầm hoàn toàn không hiện cửa sổ dòng lệnh đen.
   - Thêm cờ `--minimized` để ứng dụng tự ẩn vào System Tray khi Windows vừa mở.
"""

import os
import sys
import threading
import winreg
from typing import Optional, Dict, Any
from PIL import Image, ImageDraw
import pystray
from pystray import MenuItem as item, Menu

from backend.database import get_connection, log_event

RUN_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "TikTokAutoFarm"

_global_window = None
_tray_icon = None
_is_exiting = False

# ─── REGISTRY: AUTO-START WITH WINDOWS ────────────────────────────────────────

def get_main_script_path() -> str:
    """Trả về đường dẫn tuyệt đối đến file main.py"""
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base_dir, "main.py")


def is_autostart_enabled() -> bool:
    """Kiểm tra ứng dụng có đang được cấu hình khởi động cùng Windows không"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, APP_NAME)
            return bool(val)
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        log_event("WARNING", f"[TrayManager] Lỗi đọc registry autostart: {e}")
        return False


def set_autostart(enabled: bool) -> bool:
    """Bật hoặc tắt khởi động cùng Windows"""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY_PATH, 0, winreg.KEY_SET_VALUE)
        try:
            if enabled:
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}" --minimized'
                else:
                    # Ưu tiên dùng pythonw.exe để không hiện cửa sổ console đen khi bật máy
                    py_dir = os.path.dirname(sys.executable)
                    pyw = os.path.join(py_dir, "pythonw.exe")
                    exe = pyw if os.path.exists(pyw) else sys.executable
                    main_py = get_main_script_path()
                    cmd = f'"{exe}" "{main_py}" --minimized'
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
                log_event("INFO", f"[TrayManager] Đã BẬT khởi động cùng Windows: {cmd}")
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                    log_event("INFO", "[TrayManager] Đã TẮT khởi động cùng Windows.")
                except FileNotFoundError:
                    pass
            
            # Lưu trạng thái vào database settings
            _save_db_setting("autostart_windows", "1" if enabled else "0")
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as e:
        log_event("ERROR", f"[TrayManager] Lỗi cài đặt autostart: {e}")
        return False


# ─── DATABASE SETTINGS: MINIMIZE TO TRAY ──────────────────────────────────────

def _get_db_setting(key: str, default: str = "") -> str:
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default


def _save_db_setting(key: str, value: str):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
        conn.commit()
        conn.close()
    except Exception:
        pass


def is_minimize_to_tray_enabled() -> bool:
    """Mặc định True: khi bấm đóng cửa sổ thì thu nhỏ xuống khay hệ thống"""
    val = _get_db_setting("minimize_to_tray", "1")
    return val == "1"


def set_minimize_to_tray(enabled: bool):
    _save_db_setting("minimize_to_tray", "1" if enabled else "0")


# ─── TRAY ICON GENERATOR ──────────────────────────────────────────────────────

def get_tray_image() -> Image.Image:
    """Tải icon ứng dụng từ thư mục logo hoặc vẽ icon TikTok gradient nếu thiếu"""
    from backend.config import LOGO_DIR, BASE_DIR
    icon_paths = [
        str(LOGO_DIR / "app-logo.png"),
        str(LOGO_DIR / "app-logo.ico"),
        str(BASE_DIR / "logo" / "app-logo.png"),
        str(BASE_DIR / "logo" / "app-logo.ico"),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logo", "app-logo.png")),
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "logo", "app-logo.ico")),
    ]
    for p in icon_paths:
        if os.path.isfile(p):
            try:
                img = Image.open(p).convert("RGBA")
                return img
            except Exception:
                pass

    # Vẽ icon dự phòng nếu không tìm thấy file ảnh
    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    # Nền tròn gradient đậm
    draw.ellipse((4, 4, 60, 60), fill=(24, 24, 38, 255), outline=(0, 242, 234, 255), width=2)
    # Chữ T cách điệu
    draw.rectangle((26, 18, 38, 48), fill=(254, 44, 85, 255))
    draw.rectangle((18, 18, 46, 26), fill=(0, 242, 234, 255))
    return img


# ─── WINDOW ACTIONS ───────────────────────────────────────────────────────────

def show_window(icon=None, item_obj=None):
    """Hiện lại cửa sổ dashboard và đưa lên trước"""
    global _global_window
    if _global_window:
        try:
            _global_window.show()
            _global_window.restore()
        except Exception as e:
            log_event("WARNING", f"[TrayManager] Lỗi hiện window: {e}")


def hide_to_tray():
    """Ẩn cửa sổ vào System Tray"""
    global _global_window
    if _global_window:
        try:
            _global_window.hide()
            notify_tray("TikTok Auto Farm", "Ứng dụng đang chạy ngầm trong Khay Hệ Thống.")
        except Exception as e:
            log_event("WARNING", f"[TrayManager] Lỗi ẩn window: {e}")


def notify_tray(title: str, message: str):
    """Gửi bong bóng thông báo Windows qua System Tray"""
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.notify(message, title)
        except Exception:
            pass


def exit_application(icon=None, item_obj=None):
    """Thoát ứng dụng hoàn toàn"""
    global _is_exiting, _tray_icon, _global_window
    _is_exiting = True
    log_event("INFO", "🛑 Người dùng chọn Thoát Ứng Dụng từ System Tray.")
    
    # 1. Dừng icon khay
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass

    # 2. Đóng cửa sổ webview
    if _global_window:
        try:
            _global_window.destroy()
        except Exception:
            pass

    # 3. Kết thúc tiến trình
    os._exit(0)


# ─── MENU CALLBACKS ───────────────────────────────────────────────────────────

def _toggle_autostart_action(icon, item_obj):
    current = is_autostart_enabled()
    new_val = not current
    set_autostart(new_val)
    if new_val:
        notify_tray("Khởi Động Cùng Windows", "Đã BẬT tự khởi động ngầm khi mở máy.")
    else:
        notify_tray("Khởi Động Cùng Windows", "Đã TẮT tự khởi động cùng máy.")


def _toggle_minimize_to_tray_action(icon, item_obj):
    current = is_minimize_to_tray_enabled()
    set_minimize_to_tray(not current)


def _trigger_quick_scan_action(icon, item_obj):
    """Kích hoạt quét toàn bộ follower nick từ System Tray"""
    notify_tray("ZeroRAM Scan", "Đang quét Follower cho toàn bộ nick GPMLogin...")
    def run_scan():
        from backend.modules.tiktok_tracker import tiktok_tracker
        res = tiktok_tracker.scan_all_profiles(delay_seconds=0.5)
        sc = res.get("success_count", 0)
        tot = res.get("total", 0)
        notify_tray("ZeroRAM Scan Xong", f"Đã cập nhật chỉ số: {sc}/{tot} nick thành công!")
    threading.Thread(target=run_scan, daemon=True).start()


def _toggle_scheduler_action(icon, item_obj):
    """Bật / Tạm dừng bộ lập lịch Auto-Pilot từ System Tray"""
    from backend.scheduler import scheduler
    if scheduler.is_running:
        scheduler.stop()
        _save_db_setting("scheduler_running", "0")
        notify_tray("Auto-Pilot", "Đã TẠM DỪNG tiến trình tự động hóa.")
    else:
        scheduler.start()
        _save_db_setting("scheduler_running", "1")
        notify_tray("Auto-Pilot", "Đã TIẾP TỤC tiến trình tự động hóa.")


def _is_scheduler_running(item_obj):
    try:
        from backend.scheduler import scheduler
        return scheduler.is_running
    except Exception:
        return False


# ─── SETUP TRAY ICON ──────────────────────────────────────────────────────────

def setup_tray(window=None) -> pystray.Icon:
    """
    Khởi tạo và chạy System Tray icon trên thread nền độc lập.
    Không làm block giao diện chính của pywebview.
    """
    global _global_window, _tray_icon
    _global_window = window

    # Đăng ký sự kiện đóng cửa sổ của pywebview
    if window:
        def on_closing():
            if _is_exiting:
                return True
            if is_minimize_to_tray_enabled():
                hide_to_tray()
                return False  # Ngăn chặn đóng hẳn ứng dụng
            return True

        def on_minimized():
            if is_minimize_to_tray_enabled():
                # Có thể tự động ẩn khi bấm nút Minimize
                pass

        try:
            window.events.closing += on_closing
            window.events.minimized += on_minimized
        except Exception as e:
            log_event("WARNING", f"[TrayManager] Không thể gán window events: {e}")

    # Xây dựng Menu ngữ cảnh của System Tray
    menu = Menu(
        item("🖥️ Mở Bảng Điều Khiển", show_window, default=True),
        item("📊 Quét Follower Tất Cả Nick (ZeroRAM)", _trigger_quick_scan_action),
        item("🤖 Auto-Pilot (Tự Động Hóa)", _toggle_scheduler_action, checked=_is_scheduler_running),
        Menu.SEPARATOR,
        item("🔄 Khởi động cùng Windows", _toggle_autostart_action, checked=lambda item: is_autostart_enabled()),
        item("📌 Thu nhỏ vào Khay khi đóng", _toggle_minimize_to_tray_action, checked=lambda item: is_minimize_to_tray_enabled()),
        Menu.SEPARATOR,
        item("🛑 Thoát Ứng Dụng", exit_application),
    )

    image = get_tray_image()
    _tray_icon = pystray.Icon(
        name="TikTokAutoFarm",
        icon=image,
        title="TikTok Auto Farm & AI Engine (Đang chạy ngầm)",
        menu=menu
    )

    # Chạy trên thread nền không chặn main thread
    _tray_icon.run_detached()
    log_event("INFO", "🚀 System Tray Icon đã sẵn sàng tại góc màn hình Windows.")
    return _tray_icon
