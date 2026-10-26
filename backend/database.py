import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from backend.config import DB_PATH

def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    
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
        "bgm_folder": "TEXT DEFAULT ''",
        "bgm_volume": "REAL DEFAULT 0.15",
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
        notify_status TEXT DEFAULT 'tracking',
        last_checked TEXT,
        status TEXT DEFAULT 'active',
        status_reason TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration columns cho gpm_profiles nếu chưa có
    cursor.execute("PRAGMA table_info(gpm_profiles)")
    existing_gpm_cols = {row["name"] for row in cursor.fetchall()}
    if "status_reason" not in existing_gpm_cols:
        try:
            cursor.execute("ALTER TABLE gpm_profiles ADD COLUMN status_reason TEXT DEFAULT ''")
        except Exception:
            pass
    if "notify_status" not in existing_gpm_cols:
        try:
            cursor.execute("ALTER TABLE gpm_profiles ADD COLUMN notify_status TEXT DEFAULT 'tracking'")
            cursor.execute("UPDATE gpm_profiles SET notify_status = 'sent' WHERE eligible_10k = 1 OR followers_count >= 10000")
            cursor.execute("UPDATE gpm_profiles SET notify_status = 'tracking' WHERE notify_status IS NULL OR notify_status = ''")
        except Exception:
            pass

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

    # Migration columns cho upload_tasks nếu chưa có
    cursor.execute("PRAGMA table_info(upload_tasks)")
    existing_ut_cols = {row["name"] for row in cursor.fetchall()}
    for col, col_type in [
        ("video_path", "TEXT DEFAULT ''"),
        ("part_number", "INTEGER DEFAULT 1"),
        ("retry_count", "INTEGER DEFAULT 0"),
        ("retry_after", "TEXT"),
        ("processing_started_at", "TEXT"),
    ]:
        if col not in existing_ut_cols:
            try:
                cursor.execute(f"ALTER TABLE upload_tasks ADD COLUMN {col} {col_type}")
            except Exception:
                pass

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

    # Bảng Kênh Telegram nhận thông báo (hỗ trợ nhiều kênh, bật/tắt độc lập và phân loại thông báo)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS telegram_channels (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        chat_id TEXT NOT NULL,
        is_active INTEGER DEFAULT 1,
        notify_10k INTEGER DEFAULT 1,
        notify_issues INTEGER DEFAULT 1,
        notify_daily_report INTEGER DEFAULT 1,
        daily_report_time TEXT DEFAULT '21:00',
        last_daily_report TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Migration columns cho telegram_channels nếu chưa có
    cursor.execute("PRAGMA table_info(telegram_channels)")
    existing_tg_cols = {row["name"] for row in cursor.fetchall()}
    new_tg_cols = {
        "notify_10k": "INTEGER DEFAULT 1",
        "notify_issues": "INTEGER DEFAULT 1",
        "notify_daily_report": "INTEGER DEFAULT 1",
        "daily_report_time": "TEXT DEFAULT '21:00'",
        "last_daily_report": "TEXT DEFAULT ''",
    }
    for col, col_type in new_tg_cols.items():
        if col not in existing_tg_cols:
            try:
                cursor.execute(f"ALTER TABLE telegram_channels ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # Đảm bảo các giá trị NULL được chuẩn hóa về mặc định
    try:
        cursor.execute("UPDATE telegram_channels SET notify_10k = 1 WHERE notify_10k IS NULL")
        cursor.execute("UPDATE telegram_channels SET notify_issues = 1 WHERE notify_issues IS NULL")
        cursor.execute("UPDATE telegram_channels SET notify_daily_report = 1 WHERE notify_daily_report IS NULL")
        cursor.execute("UPDATE telegram_channels SET daily_report_time = '21:00' WHERE daily_report_time IS NULL OR daily_report_time = ''")
        cursor.execute("UPDATE telegram_channels SET last_daily_report = '' WHERE last_daily_report IS NULL")
    except Exception:
        pass

    # Tự động nạp kênh mặc định từ cấu hình cũ nếu bảng telegram_channels còn trống
    try:
        cursor.execute("SELECT COUNT(*) AS cnt FROM telegram_channels")
        row_cnt = cursor.fetchone()
        if row_cnt and row_cnt["cnt"] == 0:
            cursor.execute("SELECT value FROM settings WHERE key = 'TELEGRAM_CHAT_ID'")
            setting_chat = cursor.fetchone()
            seed_chat = setting_chat["value"].strip() if setting_chat and setting_chat["value"] else ""
            if not seed_chat:
                import os
                seed_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
            if seed_chat:
                cursor.execute(
                    "INSERT INTO telegram_channels (name, chat_id, is_active, notify_10k, notify_issues, notify_daily_report, daily_report_time) VALUES (?, ?, 1, 1, 1, 1, '21:00')",
                    ("Kênh Mặc Định", seed_chat)
                )
    except Exception:
        pass

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
        "ai_provider": "TEXT DEFAULT 'default'",
        "ai_model": "TEXT DEFAULT 'default'",
        "min_video_duration": "INTEGER DEFAULT NULL",
        "max_video_duration": "INTEGER DEFAULT NULL",
        "add_part_label": "INTEGER DEFAULT 1",
        "clips_per_video": "INTEGER DEFAULT 3",
        "bgm_folder": "TEXT DEFAULT ''",
        "bgm_volume": "REAL DEFAULT 0.15",
        "min_post_interval_minutes": "INTEGER DEFAULT 60",
    }
    for col, col_type in new_camp_cols.items():
        if col not in existing_camp_cols:
            try:
                cursor.execute(f"ALTER TABLE campaigns ADD COLUMN {col} {col_type}")
            except Exception:
                pass

    # Bảng Lịch sử hoạt động riêng cho từng chiến dịch (Campaign Run Logs)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS campaign_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        campaign_id INTEGER,
        level TEXT DEFAULT 'INFO',
        action TEXT DEFAULT 'system',
        message TEXT,
        details TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (campaign_id) REFERENCES campaigns(id) ON DELETE CASCADE
    )
    ''')

    # Bảng Theo dõi mức sử dụng AI Models & Chi phí (AI Usage Tracking)
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS ai_usage_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider TEXT NOT NULL,
        model TEXT NOT NULL,
        task TEXT NOT NULL,
        video_id TEXT DEFAULT '',
        prompt_tokens INTEGER DEFAULT 0,
        completion_tokens INTEGER DEFAULT 0,
        total_tokens INTEGER DEFAULT 0,
        estimated_cost REAL DEFAULT 0.0,
        duration_ms INTEGER DEFAULT 0,
        status TEXT DEFAULT 'success',
        error_message TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')

    # Các chỉ mục tối ưu hóa hiệu năng cao cho hàng ngàn bản ghi & đa luồng
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_tasks_status_sched ON upload_tasks(status, scheduled_time)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_tasks_profile_status ON upload_tasks(gpm_profile_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_upload_tasks_video_part ON upload_tasks(video_id, part_number)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_campaign_logs_camp_id ON campaign_logs(campaign_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_system_logs_created ON system_logs(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_videos_channel_status ON videos(channel_id, status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_channels_active ON channels(is_active, auto_download)")

    conn.commit()
    conn.close()

def log_event(level: str, message: str, details: str = ""):
    # 1. Ghi vào SQLite system_logs
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
        print(f"[DB LOG ERROR] {e}")

    # 2. Ghi song song vào file app.log chi tiết
    try:
        from backend.logger import get_logger
        l = get_logger("system")
        lvl = (level or "INFO").upper()
        formatted_msg = message
        if details:
            formatted_msg += f" | Chi tiết: {details}"
        if lvl in ("ERROR", "CRITICAL"):
            l.error(formatted_msg)
        elif lvl == "WARNING":
            l.warning(formatted_msg)
        elif lvl == "DEBUG":
            l.debug(formatted_msg)
        else:
            l.info(formatted_msg)
    except Exception:
        pass

def log_campaign_event(campaign_id: int, level: str, action: str, message: str, details: str = ""):
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO campaign_logs (campaign_id, level, action, message, details) VALUES (?, ?, ?, ?, ?)",
            (campaign_id, level, action, message, details)
        )
        cursor.execute(
            "INSERT INTO system_logs (level, message, details) VALUES (?, ?, ?)",
            (level, f"[Chiến dịch #{campaign_id}] {message}", details)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[CAMPAIGN LOG ERROR] {e}")

    # Ghi song song vào file app.log chi tiết
    try:
        from backend.logger import get_logger
        l = get_logger("system")
        lvl = (level or "INFO").upper()
        formatted_msg = f"[Chiến dịch #{campaign_id}] {message}"
        if details:
            formatted_msg += f" | Chi tiết: {details}"
        if lvl in ("ERROR", "CRITICAL"):
            l.error(formatted_msg)
        elif lvl == "WARNING":
            l.warning(formatted_msg)
        elif lvl == "DEBUG":
            l.debug(formatted_msg)
        else:
            l.info(formatted_msg)
    except Exception:
        pass

def record_ai_usage(
    provider: str,
    model: str,
    task: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: Optional[int] = None,
    estimated_cost: float = 0.0,
    duration_ms: int = 0,
    video_id: str = "",
    status: str = "success",
    error_message: str = ""
):
    """Ghi nhận một lượt gọi AI Model vào bảng ai_usage_logs"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        actual_total_tokens = total_tokens if total_tokens is not None else (prompt_tokens + completion_tokens)
        cursor.execute('''
            INSERT INTO ai_usage_logs (
                provider, model, task, video_id,
                prompt_tokens, completion_tokens, total_tokens,
                estimated_cost, duration_ms, status, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            provider, model, task, video_id,
            prompt_tokens, completion_tokens, actual_total_tokens,
            estimated_cost, duration_ms, status, error_message
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[AI USAGE LOG ERROR] {e}")

def get_ai_usage_stats(limit: int = 100) -> Dict[str, Any]:
    """Lấy thống kê tổng quan và nhật ký sử dụng AI Models"""
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Thống kê tổng quan
        cursor.execute('''
            SELECT 
                COUNT(*) as total_calls,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                COALESCE(SUM(prompt_tokens), 0) as total_prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as total_completion_tokens,
                COALESCE(SUM(estimated_cost), 0.0) as total_cost_usd
            FROM ai_usage_logs
        ''')
        summary = dict(cursor.fetchone() or {})

        # 2. Thống kê hôm nay
        cursor.execute('''
            SELECT 
                COUNT(*) as calls_today,
                COALESCE(SUM(total_tokens), 0) as tokens_today,
                COALESCE(SUM(estimated_cost), 0.0) as cost_today_usd
            FROM ai_usage_logs
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
        ''')
        today_summary = dict(cursor.fetchone() or {})

        # 3. Phân chia theo Provider / Model
        cursor.execute('''
            SELECT 
                provider,
                model,
                COUNT(*) as calls,
                COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                ROUND(COALESCE(SUM(estimated_cost), 0.0), 6) as cost_usd,
                ROUND(COALESCE(AVG(duration_ms), 0), 0) as avg_duration_ms
            FROM ai_usage_logs
            GROUP BY provider, model
            ORDER BY calls DESC
        ''')
        by_provider = []
        for row in cursor.fetchall():
            d = dict(row)
            d["cost_vnd"] = round(d["cost_usd"] * 25400, 0)
            by_provider.append(d)

        # 4. Danh sách log gần nhất
        cursor.execute('''
            SELECT * FROM ai_usage_logs
            ORDER BY id DESC
            LIMIT ?
        ''', (limit,))
        recent_logs = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # Quy đổi ước tính USD sang VND (tỉ giá tạm tính 25,400)
        total_vnd = summary.get("total_cost_usd", 0.0) * 25400
        today_vnd = today_summary.get("cost_today_usd", 0.0) * 25400

        try:
            import backend.config as cfg
            active_provider = getattr(cfg, "AI_PROVIDER", "deepseek")
            active_model = getattr(cfg, "DEEPSEEK_MODEL", "deepseek-chat")
            if active_provider == "gemini":
                active_model = getattr(cfg, "GEMINI_MODEL", "gemini-2.5-flash")
            elif active_provider == "openai":
                active_model = getattr(cfg, "OPENAI_MODEL", "gpt-4o-mini")
        except Exception:
            active_provider = "deepseek"
            active_model = "deepseek-chat"

        stats_dict = {
            **summary,
            "today_calls": today_summary.get("calls_today", 0),
            "today_tokens": today_summary.get("tokens_today", 0),
            "cost_today_usd": today_summary.get("cost_today_usd", 0.0),
            "total_cost_vnd": round(total_vnd, 0),
            "cost_today_vnd": round(today_vnd, 0),
            "active_provider": active_provider,
            "active_model": active_model
        }

        return {
            "stats": stats_dict,
            "summary": stats_dict,
            "model_breakdown": by_provider,
            "by_provider": by_provider,
            "recent_logs": recent_logs
        }
    except Exception as e:
        print(f"[AI STATS ERROR] {e}")
        return {
            "stats": {"total_calls": 0, "total_tokens": 0, "total_cost_usd": 0.0, "total_cost_vnd": 0, "today_calls": 0, "today_tokens": 0},
            "summary": {"total_calls": 0, "total_tokens": 0, "total_cost_usd": 0.0, "total_cost_vnd": 0},
            "model_breakdown": [],
            "by_provider": [],
            "recent_logs": []
        }

def clear_ai_usage_logs() -> bool:
    """Xóa sạch nhật ký sử dụng AI"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM ai_usage_logs")
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False

def is_save_by_channel_folder_enabled() -> bool:
    """Kiểm tra xem tính năng lưu video theo thư mục riêng từng kênh có đang bật không (mặc định bật)"""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM settings WHERE key = 'save_by_channel_folder'")
        row = cursor.fetchone()
        conn.close()
        if not row:
            return True
        return bool(row["value"] == "1" or row["value"] is True or str(row["value"]).lower() == "true")
    except Exception:
        return True

# Khởi tạo DB ngay khi nạp module
init_db()

