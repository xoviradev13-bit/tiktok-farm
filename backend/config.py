import os
import re
from pathlib import Path
from typing import Dict, Any

# Thư mục gốc dự án
BASE_DIR = Path(__file__).resolve().parent.parent

# Các thư mục lưu trữ dữ liệu
DATA_DIR = BASE_DIR / "data"
DOWNLOADS_DIR = DATA_DIR / "downloads"
RENDERED_DIR = DATA_DIR / "rendered"
DB_PATH = DATA_DIR / "tiktok_tool.db"

# Tự động tạo thư mục nếu chưa tồn tại
DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
RENDERED_DIR.mkdir(parents=True, exist_ok=True)

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

# Cấu hình AI API (Tùy chọn: Gemini hoặc OpenAI)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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
    global YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY, OPENAI_API_KEY, GPM_API_BASE_URL
    YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    GPM_API_BASE_URL = os.getenv("GPM_API_BASE_URL", "http://127.0.0.1:9495/api/v1")
    return True
