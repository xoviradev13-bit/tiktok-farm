import os
import sys
import shutil
import platform
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List

from backend.config import (
    BASE_DIR, DATA_DIR, DOWNLOADS_DIR, RENDERED_DIR, LOGS_DIR,
    YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, AI_PROVIDER,
    DEEPSEEK_MODEL, GEMINI_MODEL, OPENAI_MODEL, WHISPER_MODEL_SIZE
)
from backend.modules.video_core.hardware_accel import get_ffmpeg_binary, is_nvenc_available
from backend.modules.gpm_client import gpm_client
from backend.logger import get_logger

logger = get_logger("diagnostics")

def check_directory_writable(p: Path) -> bool:
    try:
        p.mkdir(parents=True, exist_ok=True)
        test_file = p / ".test_write.tmp"
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("test")
        test_file.unlink()
        return True
    except Exception:
        return False

def get_disk_free_space(path: Path) -> Dict[str, Any]:
    try:
        total, used, free = shutil.disk_usage(path)
        return {
            "total_gb": round(total / (1024**3), 1),
            "free_gb": round(free / (1024**3), 1),
            "used_gb": round(used / (1024**3), 1),
            "percent_free": round((free / total) * 100, 1)
        }
    except Exception:
        return {"total_gb": 0, "free_gb": 0, "used_gb": 0, "percent_free": 0}

def run_environment_diagnostics() -> Dict[str, Any]:
    """
    Thực hiện kiểm tra toàn diện môi trường runtime và các phần mềm phụ thuộc.
    Đặc biệt hữu ích khi thiết lập trên máy tính mới hoặc debug lỗi setup.
    """
    logger.info("Bắt đầu chạy chẩn đoán hệ thống (System Diagnostics)...")
    checks: Dict[str, Any] = {}
    action_items: List[Dict[str, str]] = []

    # 1. Python & Hệ điều hành
    disk = get_disk_free_space(DATA_DIR)
    checks["python"] = {
        "status": "ok",
        "version": platform.python_version(),
        "executable": sys.executable,
        "os": f"{platform.system()} {platform.release()} ({platform.architecture()[0]})",
        "disk_free_gb": disk["free_gb"],
        "disk_percent_free": disk["percent_free"]
    }
    if disk["free_gb"] < 2.0:
        checks["python"]["status"] = "warning"
        action_items.append({
            "type": "warning",
            "category": "Dung lượng ổ cứng",
            "title": "Ổ đĩa chứa data sắp đầy",
            "message": f"Dung lượng trống chỉ còn {disk['free_gb']} GB. Nên dọn dẹp để tránh lỗi render video và tải YouTube."
        })

    # 2. FFmpeg & Tăng tốc phần cứng GPU
    ffmpeg_bin = get_ffmpeg_binary()
    ffmpeg_ok = False
    ffmpeg_version = "Không rõ"
    try:
        res = subprocess.run([ffmpeg_bin, "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            ffmpeg_ok = True
            lines = res.stdout.split("\n")
            ffmpeg_version = lines[0] if lines else "Installed"
    except Exception as e:
        ffmpeg_version = f"Lỗi thực thi: {e}"

    nvenc_ok = is_nvenc_available() if ffmpeg_ok else False

    checks["ffmpeg"] = {
        "status": "ok" if ffmpeg_ok else "error",
        "binary_path": ffmpeg_bin,
        "version": ffmpeg_version,
        "nvenc_accelerated": nvenc_ok,
        "encoder": "h264_nvenc (NVIDIA GPU)" if nvenc_ok else "libx264 (CPU)"
    }

    if not ffmpeg_ok:
        action_items.append({
            "type": "error",
            "category": "FFmpeg",
            "title": "Chưa cài đặt FFmpeg",
            "message": "Không tìm thấy FFmpeg trên máy. Chạy lệnh: pip install imageio[ffmpeg] hoặc cài FFmpeg vào PATH của Windows."
        })
    elif not nvenc_ok:
        checks["ffmpeg"]["status"] = "info"
        # Không xem là lỗi nếu dùng CPU

    # 3. Node.js (Rất quan trọng cho yt-dlp giải mã chữ ký YouTube)
    node_bin = shutil.which("node")
    node_ok = False
    node_version = ""
    if node_bin:
        try:
            res = subprocess.run([node_bin, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            if res.returncode == 0:
                node_ok = True
                node_version = res.stdout.strip()
        except Exception:
            pass

    checks["nodejs"] = {
        "status": "ok" if node_ok else "warning",
        "installed": node_ok,
        "path": node_bin or "Chưa cài",
        "version": node_version or "N/A"
    }

    if not node_ok:
        action_items.append({
            "type": "warning",
            "category": "Node.js (yt-dlp)",
            "title": "Chưa cài Node.js trên máy",
            "message": "yt-dlp cần Node.js để giải mã thuật toán JavaScript của YouTube (tránh lỗi 'Sign in to confirm you're not a bot'). Khuyến nghị tải & cài Node.js LTS từ https://nodejs.org."
        })

    # 4. Playwright (Dùng cho GPM Automation & Đăng bài TikTok)
    playwright_ok = False
    playwright_msg = ""
    try:
        import playwright
        from playwright.sync_api import sync_playwright
        playwright_ok = True
        playwright_msg = f"Đã cài đặt v{playwright.__version__ if hasattr(playwright, '__version__') else 'OK'}"
    except ImportError as e:
        playwright_msg = f"Chưa cài: {e}"

    checks["playwright"] = {
        "status": "ok" if playwright_ok else "error",
        "installed": playwright_ok,
        "detail": playwright_msg
    }

    if not playwright_ok:
        action_items.append({
            "type": "error",
            "category": "Playwright",
            "title": "Thiếu thư viện Playwright",
            "message": "Chạy lệnh: pip install playwright && playwright install chromium để kích hoạt tính năng tự động đăng TikTok."
        })

    # 5. GPMLogin App & Local API
    gpm_health = gpm_client.check_health()
    checks["gpm"] = {
        "status": "ok" if gpm_health.get("running") else "warning",
        "running": gpm_health.get("running", False),
        "api_url": gpm_client.cached_working_base or gpm_client.base_url,
        "profile_count": gpm_health.get("profile_count", 0),
        "message": gpm_health.get("message", "")
    }

    if not gpm_health.get("running"):
        action_items.append({
            "type": "warning",
            "category": "GPMLogin",
            "title": "Ứng dụng GPMLogin chưa mở",
            "message": "Hãy mở phần mềm GPMLogin trên máy tính và đảm bảo API mở tại cổng 9495 hoặc 19995."
        })

    # 6. AI Providers & Speech-to-Text (Whisper)
    has_deepseek = bool(DEEPSEEK_API_KEY and DEEPSEEK_API_KEY.strip())
    has_gemini = bool(GEMINI_API_KEY and GEMINI_API_KEY.strip())
    has_openai = bool(OPENAI_API_KEY and OPENAI_API_KEY.strip())
    any_ai_key = has_deepseek or has_gemini or has_openai

    whisper_lib_ok = False
    try:
        import faster_whisper
        whisper_lib_ok = True
    except ImportError:
        pass

    checks["ai"] = {
        "status": "ok" if any_ai_key else "warning",
        "active_provider": AI_PROVIDER,
        "has_deepseek": has_deepseek,
        "has_gemini": has_gemini,
        "has_openai": has_openai,
        "whisper_installed": whisper_lib_ok,
        "whisper_model_size": WHISPER_MODEL_SIZE
    }

    if not any_ai_key:
        action_items.append({
            "type": "warning",
            "category": "AI Cloud API",
            "title": "Chưa nhập API Key cho AI Engine",
            "message": "Hãy cấu hình API Key của DeepSeek, Gemini hoặc OpenAI trong tab Cài Đặt để sử dụng tính năng viết hook, tiêu đề và tóm tắt AI."
        })

    if not whisper_lib_ok:
        action_items.append({
            "type": "warning",
            "category": "faster-whisper",
            "title": "Chưa cài thư viện faster-whisper",
            "message": "Để tạo phụ đề động Karaoke tự động, hãy chạy: pip install faster-whisper."
        })

    # 7. YouTube Data API v3
    yt_keys = [k.strip() for k in (YOUTUBE_API_KEY or "").split(",") if k.strip()]
    checks["youtube"] = {
        "status": "ok" if yt_keys else "warning",
        "key_count": len(yt_keys),
        "configured": len(yt_keys) > 0
    }
    if not yt_keys:
        action_items.append({
            "type": "warning",
            "category": "YouTube API",
            "title": "Chưa cấu hình YouTube Data API Key",
            "message": "Không có YouTube Data API v3 Key. Bạn có thể thêm key trong tab Cài Đặt để tìm kiếm và quét kênh tự động."
        })

    # 8. Quyền ghi thư mục (Storage Permissions)
    dirs_check = {
        "data": check_directory_writable(DATA_DIR),
        "downloads": check_directory_writable(DOWNLOADS_DIR),
        "rendered": check_directory_writable(RENDERED_DIR),
        "logs": check_directory_writable(LOGS_DIR)
    }
    all_dirs_ok = all(dirs_check.values())
    checks["storage"] = {
        "status": "ok" if all_dirs_ok else "error",
        "writable": dirs_check
    }
    if not all_dirs_ok:
        action_items.append({
            "type": "error",
            "category": "Quyền ghi thư mục",
            "title": "Lỗi quyền ghi ổ đĩa",
            "message": "Ứng dụng không thể ghi file vào một số thư mục data/downloads/rendered/logs. Vui lòng chạy ứng dụng dưới quyền Administrator hoặc kiểm tra bảo mật thư mục."
        })

    # 9. Đánh giá trạng thái chung
    overall_status = "ok"
    if any(item["type"] == "error" for item in action_items):
        overall_status = "error"
    elif any(item["type"] == "warning" for item in action_items):
        overall_status = "warning"

    result = {
        "overall_status": overall_status,
        "checks": checks,
        "action_items": action_items,
        "timestamp": checks["python"]["os"]
    }
    logger.info(f"Hoàn thành chẩn đoán hệ thống: trạng thái [{overall_status.upper()}], {len(action_items)} lưu ý.")
    return result
