import sqlite3
import json
from datetime import datetime
from backend.config import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Bảng kênh YouTube theo dõi
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT UNIQUE,
        title TEXT,
        url TEXT,
        subscriber_count INTEGER DEFAULT 0,
        video_count INTEGER DEFAULT 0,
        avg_views INTEGER DEFAULT 0,
        upload_cadence_days REAL DEFAULT 0,
        last_upload_date TEXT,
        is_active INTEGER DEFAULT 1,
        auto_download INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration columns cho channels nếu chưa có
    cursor.execute("PRAGMA table_info(channels)")
    existing_cols = {row["name"] for row in cursor.fetchall()}
    new_cols = {
        "display_name": "TEXT DEFAULT ''",
        "custom_proxy": "TEXT DEFAULT ''",
        "download_dir": "TEXT DEFAULT ''",
        "render_dir": "TEXT DEFAULT ''",
        "auto_render": "INTEGER DEFAULT 1",
    }
    for col, col_type in new_cols.items():
        if col not in existing_cols:
            try:
                cursor.execute(f"ALTER TABLE channels ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # Bảng video tải về và xử lý
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS videos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel_id TEXT,
        yt_video_id TEXT UNIQUE,
        title TEXT,
        original_url TEXT,
        duration INTEGER DEFAULT 0,
        download_path TEXT,
        rendered_path TEXT,
        ai_hook TEXT,
        ai_title TEXT,
        ai_tags TEXT,
        status TEXT DEFAULT 'pending', -- pending, downloaded, rendering, rendered, uploaded, error
        error_message TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Bảng Profile GPMLogin và chỉ số TikTok
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS gpm_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        gpm_id TEXT UNIQUE,
        name TEXT,
        raw_proxy TEXT,
        tiktok_username TEXT,
        followers_count INTEGER DEFAULT 0,
        total_views INTEGER DEFAULT 0,
        eligible_10k INTEGER DEFAULT 0,
        last_checked TEXT,
        status TEXT DEFAULT 'active',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Bảng Lịch trình đăng bài (Upload Tasks)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS upload_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id INTEGER,
        gpm_profile_id INTEGER,
        title TEXT,
        tags TEXT,
        status TEXT DEFAULT 'queued', -- queued, processing, completed, failed
        scheduled_time TEXT,
        uploaded_at TEXT,
        error_message TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (video_id) REFERENCES videos(id),
        FOREIGN KEY (gpm_profile_id) REFERENCES gpm_profiles(id)
    )
    ''')

    # Bảng Nhật ký hệ thống (Logs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        level TEXT DEFAULT 'INFO',
        message TEXT,
        details TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Bảng Cấu hình chung (Key-Value)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    ''')

    conn.commit()
    conn.close()

def log_event(level: str, message: str, details: str = ""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO system_logs (level, message, details) VALUES (?, ?, ?)",
            (level, message, details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[LOG ERROR] {e}")

# Khởi tạo DB ngay khi nạp module
init_db()
