import sys
import os
import re
from pathlib import Path
from typing import Dict, Any

# Ensure UTF-8 output encoding across Windows shells and background logs
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Thư mục gốc dự án (Tự động nhận diện khi đóng gói PyInstaller .exe hoặc chạy mã nguồn)
if getattr(sys, "frozen", False):
    # Khi chạy từ file exe đóng gói
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

# Thư mục frontend và logo
FRONTEND_DIR = BUNDLE_DIR / "frontend" if (BUNDLE_DIR / "frontend").exists() else BASE_DIR / "frontend"
LOGO_DIR = BUNDLE_DIR / "logo" if (BUNDLE_DIR / "logo").exists() else BASE_DIR / "logo"
APP_ICON_PATH = LOGO_DIR / "app-logo.ico"

# Các thư mục lưu trữ dữ liệu (luôn nằm ở BASE_DIR nơi người dùng cài đặt)
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
RENDERED_DIR = DATA_DIR / "rendered"
LOGS_DIR = DATA_DIR / "logs"
MUSIC_DIR = DATA_DIR / "music"
LOG_FILE_PATH = LOGS_DIR / "app.log"
DB_PATH = DATA_DIR / "tiktok_tool.db"

# Tự động tạo thư mục nếu chưa tồn tại
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
RENDERED_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)
MUSIC_DIR.mkdir(parents=True, exist_ok=True)

# Khởi tạo các thư mục chủ đề nhạc nền mặc định
DEFAULT_BGM_THEMES = [
    ("horror_mystery", "Chuyện Ma / Rùng Rợn / U Ám"),
    ("lofi_chill", "Lo-Fi / Chill Beats / Tài Chính"),
    ("phonk_hype", "Phonk / Năng Động / Hành Động"),
    ("storytelling_piano", "Piano / Drama / Kể Chuyện"),
    ("general", "Nhạc Nền Tổng Hợp")
]
for theme_folder, _ in DEFAULT_BGM_THEMES:
    (MUSIC_DIR / theme_folder).mkdir(parents=True, exist_ok=True)

# Tự động đọc file .env nếu có
def _load_env_file(env_path: Path):
    if not env_path.exists():
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("\"'")
                    if key and key not in os.environ:
                        os.environ[key] = val
    except Exception:
        pass

_load_env_file(BASE_DIR / ".env")

# Cấu hình GPMLogin
GPM_API_BASE_URL = os.getenv("GPM_API_BASE_URL", "http://127.0.0.1:9495/api/v1")

# Cấu hình YouTube Data API v3 (Hỗ trợ 1 hoặc nhiều key cách nhau bằng dấu phẩy)
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")

# Cấu hình Telegram Bot cảnh báo 10k Follower
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Cấu hình AI Cloud API & Local Models
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")  # "deepseek" | "gemini" | "openai"
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")  # "deepseek-chat" | "deepseek-reasoner"
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")  # "gemini-2.5-flash" | "gemini-1.5-flash" | "gemini-1.5-pro"
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")  # "gpt-4o-mini" | "gpt-4o"
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")  # "tiny" | "base" | "small"
ENABLE_DYNAMIC_SUBTITLES = os.getenv("ENABLE_DYNAMIC_SUBTITLES", "true").lower() in ("true", "1", "yes")
ENABLE_ANTI_DETECT = os.getenv("ENABLE_ANTI_DETECT", "true").lower() in ("true", "1", "yes")
SUBTITLE_STYLE = os.getenv("SUBTITLE_STYLE", "karaoke_yellow")  # "karaoke_yellow" | "classic_white" | "tiktok_gradient" | "green_neon"
SUBTITLE_POSITION = os.getenv("SUBTITLE_POSITION", "center")   # "center" | "bottom"
SUBTITLE_FONT_SIZE = int(os.getenv("SUBTITLE_FONT_SIZE", 54))

# Server config
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8088

def save_env_config(updates: Dict[str, str]) -> bool:
    """Cập nhật các biến cấu hình vào file .env và cập nhật môi trường runtime"""
    env_path = BASE_DIR / ".env"
    lines = []
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    
    updated_keys = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k, _ = stripped.split("=", 1)
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}\n")
                updated_keys.add(k)
                os.environ[k] = str(updates[k])
                continue
        new_lines.append(line)
        
    for k, v in updates.items():
        if k not in updated_keys:
            new_lines.append(f"{k}={v}\n")
            os.environ[k] = str(v)
            
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)
        
    # Đồng bộ lại các biến toàn cục
    global YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GPM_API_BASE_URL
    global DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, AI_PROVIDER
    global DEEPSEEK_MODEL, GEMINI_MODEL, OPENAI_MODEL
    global WHISPER_MODEL_SIZE, ENABLE_DYNAMIC_SUBTITLES, ENABLE_ANTI_DETECT

    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    GPM_API_BASE_URL = os.getenv("GPM_API_BASE_URL", "http://127.0.0.1:9495/api/v1")
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    AI_PROVIDER = os.getenv("AI_PROVIDER", "deepseek")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "base")
    ENABLE_DYNAMIC_SUBTITLES = os.getenv("ENABLE_DYNAMIC_SUBTITLES", "true").lower() in ("true", "1", "yes")
    ENABLE_ANTI_DETECT = os.getenv("ENABLE_ANTI_DETECT", "true").lower() in ("true", "1", "yes")
    return True


