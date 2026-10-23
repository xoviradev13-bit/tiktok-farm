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

    # Bảng Chiến dịch tự động hóa (Auto-Pilot Campaigns)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campaigns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        channel_id TEXT,
        gpm_profile_id INTEGER,
        preset_name TEXT DEFAULT 'TikTok Beta Chuẩn 9:16',
        video_duration INTEGER DEFAULT 65,
        speed_factor REAL DEFAULT 1.03,
        flip_horizontal INTEGER DEFAULT 1,
        daily_limit INTEGER DEFAULT 3,
        post_schedule TEXT DEFAULT '11:30, 18:00, 20:30',
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (channel_id) REFERENCES channels(channel_id),
        FOREIGN KEY (gpm_profile_id) REFERENCES gpm_profiles(id)
    )
    ''')

    # Migration columns cho campaigns nếu chưa có
    cursor.execute("PRAGMA table_info(campaigns)")
    existing_camp_cols = {row["name"] for row in cursor.fetchall()}
    new_camp_cols = {
        "channel_ids": "TEXT DEFAULT ''",
        "gpm_profile_ids": "TEXT DEFAULT ''",
        "distribution_mode": "TEXT DEFAULT 'round_robin'",
        "download_dir": "TEXT DEFAULT ''",
        "render_dir": "TEXT DEFAULT ''",
        "subtitle_enabled": "INTEGER DEFAULT 0",
        "subtitle_style": "TEXT DEFAULT 'karaoke_yellow'",
        "aspect_ratio": "TEXT DEFAULT '9:16_blur'",
        "post_frequency": "TEXT DEFAULT 'daily'",
        "post_interval_days": "INTEGER DEFAULT 1",
        "post_days_of_week": "TEXT DEFAULT 'mon,tue,wed,thu,fri,sat,sun'",
        "random_delay_minutes": "INTEGER DEFAULT 10",
        "warmup_mode": "INTEGER DEFAULT 0",
    }
    for col, col_type in new_camp_cols.items():
        if col not in existing_camp_cols:
            try:
                cursor.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {col_type}")
            except Exception:
                pass

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
