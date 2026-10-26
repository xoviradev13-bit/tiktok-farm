import os
import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.config import (
    BASE_DIR, FRONTEND_DIR, LOGO_DIR, SERVER_HOST, SERVER_PORT, save_env_config,
    YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY, OPENAI_API_KEY, GPM_API_BASE_URL,
    MUSIC_DIR
)
from backend.database import get_connection, log_event, log_campaign_event
from backend.modules.gpm_client import gpm_client
from backend.modules.yt_scanner import yt_scanner
from backend.modules.yt_downloader import yt_downloader
from backend.modules.ai_video_engine import ai_video_engine
from backend.modules.tiktok_uploader import tiktok_uploader
from backend.modules.metrics_tracker import metrics_tracker
from backend.modules.notifier import notifier
from backend.modules.yt_monitor import yt_monitor
from backend.modules.tiktok_tracker import tiktok_tracker
from backend.modules.audio_manager import audio_manager, sanitize_audio_filename, ALLOWED_AUDIO_EXTENSIONS
from backend.scheduler import scheduler
from backend.config import LOG_FILE_PATH
from backend.logger import (
    get_logger, get_recent_log_lines, get_log_file_info, clear_log_file
)
from backend.modules.diagnostics import run_environment_diagnostics

import ipaddress
from urllib.parse import urlparse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

logger = get_logger("api")

app = FastAPI(title="TikTok Auto Farm & AI Video Engine", version="1.0.0")

# --- Security Hardening (OWASP / NIST SP 800-218 / ISO 27034) ---
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Bổ sung các HTTP security headers chuẩn OWASP"""
    async def dispatch(self, request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        return response

app.add_middleware(SecurityHeadersMiddleware)

# Giới hạn CORS chỉ cho phép các origin cục bộ (localhost/127.0.0.1), chặn tấn công Cross-Site từ trình duyệt
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8088",
        "http://localhost:8088",
        "http://127.0.0.1",
        "http://localhost",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    first_error = exc.errors()[0] if exc.errors() else {}
    msg = first_error.get("msg", "Dữ liệu đầu vào không hợp lệ!")
    field = " -> ".join(str(l) for l in first_error.get("loc", []) if l != "body")
    error_text = f"Dữ liệu không hợp lệ tại [{field}]: {msg}" if field else f"Dữ liệu không hợp lệ: {msg}"
    return JSONResponse(
        status_code=400,
        content={"status": "error", "message": error_text, "detail": error_text, "errors": exc.errors()}
    )

def is_safe_external_url(url_str: str) -> bool:
    """Kiểm tra URL an toàn chống SSRF (OWASP A10 / NIST SP 800-218)"""
    try:
        if not url_str or len(url_str) > 2048:
            return False
        parsed = urlparse(url_str.strip())
        if parsed.scheme.lower() not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
        if hostname.lower() in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
            return False
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False

def is_valid_folder_name(name: str) -> bool:
    """Kiểm tra tên thư mục hợp lệ trên hệ điều hành Windows/Linux"""
    if not name or not name.strip():
        return False
    stripped = name.strip()
    if any(c in r'<>:"/\|?*' for c in stripped):
        return False
    if stripped.startswith(".") or stripped.endswith("."):
        return False
    if ".." in stripped:
        return False
    return True

def is_valid_hhmm(t_str: str) -> bool:
    """Kiểm tra định dạng thời gian HH:MM (00:00 - 23:59)"""
    if not t_str:
        return False
    return bool(re.match(r"^([01]\d|2[0-3]):[0-5]\d$", t_str.strip()))

# --- Models ---
class SearchKeywordRequest(BaseModel):
    keyword: str
    max_results: int = 50

class UnsaveChannelRequest(BaseModel):
    channel_id: str

class DownloadVideoRequest(BaseModel):
    url: str
    target_dir: Optional[str] = None
    is_studio: bool = True

class RenderVideoRequest(BaseModel):
    video_id: str
    part_number: int = 1
    duration: int = 65
    flip_horizontal: bool = True
    speed_factor: float = 1.025
    enable_subtitles: Optional[bool] = None
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    clips_count: Optional[int] = 1
    add_part_label: Optional[bool] = True
    subtitle_style: Optional[str] = None
    subtitle_position: Optional[str] = None
    bgm_folder: Optional[str] = None
    bgm_volume: Optional[float] = None

class SmartRenderVideoRequest(BaseModel):
    video_id: str
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None
    enable_subtitles: Optional[bool] = None
    target_duration: int = 65
    flip_horizontal: bool = True
    speed_factor: float = 1.03
    add_part_label: bool = True
    generate_hook: bool = True
    clips_count: Optional[int] = 1
    subtitle_style: Optional[str] = None
    subtitle_position: Optional[str] = None
    bgm_folder: Optional[str] = None
    bgm_volume: Optional[float] = None

class UploadVideoRequest(BaseModel):
    gpm_profile_id: str
    video_path: str
    title: str
    tags: str = "#viral #fyp #xuhuong"

class UpdateProfileStatsRequest(BaseModel):
    gpm_id: str
    followers: int
    views: int
    username: Optional[str] = ""

class UpdateProfileUsernameRequest(BaseModel):
    username: str

class UpdateProfileNotifyStatusRequest(BaseModel):
    status: str

class FollowerSchedulerRequest(BaseModel):
    enabled: bool
    mode: str = "daily_times"
    times: Optional[str] = "08:00, 20:00"
    interval_hours: Optional[int] = 6

class SearchAudioRequest(BaseModel):
    keyword: str
    max_results: int = 50

class CreateCategoryRequest(BaseModel):
    name: str
    display_name: Optional[str] = None

class RenameCategoryRequest(BaseModel):
    old_id: str
    new_name: str
    display_name: Optional[str] = None

class AudioSettingsRequest(BaseModel):
    music_dir: Optional[str] = None
    max_size_mb: Optional[int] = 50
    default_bitrate: Optional[str] = "192k"
    max_search_results: Optional[int] = 50
    normalize_audio: Optional[bool] = True

class DownloadYtAudioRequest(BaseModel):
    url: str
    category: str = "general"

class DeleteAudioRequest(BaseModel):
    category: str
    filename: str

class UpdateChannelSettingsRequest(BaseModel):
    channel_id: str
    display_name: Optional[str] = ""
    custom_proxy: Optional[str] = ""
    download_dir: Optional[str] = ""
    render_dir: Optional[str] = ""
    is_active: Optional[int] = 1
    auto_download: Optional[int] = 1
    auto_render: Optional[int] = 1
    bgm_folder: Optional[str] = ""
    bgm_volume: Optional[float] = 0.15

class ToggleChannelStatusRequest(BaseModel):
    channel_id: str
    is_active: Optional[int] = None

class ClearChannelHistoryRequest(BaseModel):
    channel_id: str
    delete_files: bool = True
    target: Optional[str] = "all"  # "all", "downloaded", "rendered"

class ScanChannelRequest(BaseModel):
    channel_id: str

class SaveApiKeysRequest(BaseModel):
    youtube_api_keys: Optional[str] = ""       # comma-separated list
    deepseek_api_key: Optional[str] = ""
    gemini_api_key: Optional[str] = ""
    openai_api_key: Optional[str] = ""
    ai_provider: Optional[str] = "deepseek"
    deepseek_model: Optional[str] = "deepseek-chat"
    gemini_model: Optional[str] = "gemini-2.5-flash"
    openai_model: Optional[str] = "gpt-4o-mini"
    whisper_model_size: Optional[str] = "base"
    enable_dynamic_subtitles: Optional[bool] = True
    enable_anti_detect: Optional[bool] = True
    subtitle_style: Optional[str] = "karaoke_yellow"
    subtitle_position: Optional[str] = "center"
    subtitle_font_size: Optional[int] = 54
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    gpm_api_base_url: Optional[str] = ""

class SystemTraySettingsRequest(BaseModel):
    autostart: Optional[bool] = None
    minimize_to_tray: Optional[bool] = None

class TelegramChannelCreateRequest(BaseModel):
    name: str
    chat_id: str
    is_active: Optional[bool] = True
    notify_10k: Optional[bool] = True
    notify_issues: Optional[bool] = True
    notify_daily_report: Optional[bool] = True
    daily_report_time: Optional[str] = "21:00"

class TelegramChannelUpdateRequest(BaseModel):
    name: str
    chat_id: str
    is_active: Optional[bool] = True
    notify_10k: Optional[bool] = True
    notify_issues: Optional[bool] = True
    notify_daily_report: Optional[bool] = True
    daily_report_time: Optional[str] = "21:00"

class TelegramSendReportRequest(BaseModel):
    report_date: Optional[str] = None
    channel_id: Optional[int] = None

class TelegramSendIssueRequest(BaseModel):
    title: str
    message: str
    solution: Optional[str] = ""
    severity: Optional[str] = "ERROR"
    details: Optional[str] = ""
    channel_id: Optional[int] = None

class TestApiKeyRequest(BaseModel):
    key: str

class CreateCampaignRequest(BaseModel):
    name: str
    channel_id: Optional[str] = ""
    channel_ids: Optional[List[str]] = []
    gpm_profile_id: Optional[int] = None
    gpm_profile_ids: Optional[List[int]] = []
    distribution_mode: Optional[str] = "round_robin"
    download_dir: Optional[str] = ""
    render_dir: Optional[str] = ""
    subtitle_enabled: Optional[int] = 0
    subtitle_style: Optional[str] = "karaoke_yellow"
    aspect_ratio: Optional[str] = "9:16_blur"
    preset_name: Optional[str] = "TikTok Beta Chuẩn 9:16"
    video_duration: Optional[int] = 65
    speed_factor: Optional[float] = 1.03
    flip_horizontal: Optional[int] = 1
    add_part_label: Optional[int] = 1
    clips_per_video: Optional[int] = 3
    daily_limit: Optional[int] = 3
    post_schedule: Optional[str] = "11:30, 18:00, 20:30"
    post_frequency: Optional[str] = "daily"
    post_interval_days: Optional[int] = 1
    post_days_of_week: Optional[str] = "mon,tue,wed,thu,fri,sat,sun"
    random_delay_minutes: Optional[int] = 10
    min_post_interval_minutes: Optional[int] = None
    warmup_mode: Optional[int] = 0
    ai_provider: Optional[str] = "default"
    ai_model: Optional[str] = "default"
    min_video_duration: Optional[int] = None
    max_video_duration: Optional[int] = None
    bgm_folder: Optional[str] = ""
    bgm_volume: Optional[float] = 0.15
    is_active: Optional[int] = 1

class DownloadFilterSettingsRequest(BaseModel):
    min_video_duration: int = 300
    max_video_duration: int = 3600

class CleanupSettingsRequest(BaseModel):
    retention_mode: str = "7"  # "0", "3", "7", "14", "30", "custom", "never"
    custom_days: Optional[int] = 7

class TriggerCleanupRequest(BaseModel):
    mode: Optional[str] = None
    custom_days: Optional[int] = None

# --- Dashboard API ---
def get_system_active_issues():
    """Tổng hợp toàn bộ các cảnh báo và vấn đề đang xảy ra trên toàn hệ thống để hiển thị lên UI"""
    issues = []
    try:
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Tài khoản bị Banned / Restricted / Checkpoint / Chưa đăng nhập / Chết Proxy
        cursor.execute("""
            SELECT gpm_id, name, tiktok_username, status, status_reason, last_checked
            FROM gpm_profiles
            WHERE status IS NOT NULL AND status NOT IN ('active', 'paused', '')
        """)
        for row in cursor.fetchall():
            st = (row["status"] or "unknown").lower()
            title_map = {
                "banned": "Tài khoản TikTok bị CẤM (Banned)",
                "restricted": "Tài khoản TikTok bị HẠN CHẾ",
                "checkpoint": "TikTok yêu cầu Captcha xác minh",
                "unlogged": "Tài khoản chưa đăng nhập hoặc hết phiên",
                "proxy_dead": "Proxy của Profile bị lỗi / chết"
            }
            severity = "error" if st in ("banned", "proxy_dead") else "warning"
            issues.append({
                "id": f"gpm_{row['gpm_id']}",
                "category": "tiktok_account",
                "severity": severity,
                "title": title_map.get(st, f"Vấn đề tài khoản ({st.upper()})"),
                "target": f"Profile: {row['name']} (@{row['tiktok_username'] or 'N/A'})",
                "message": row["status_reason"] or f"Trạng thái tài khoản hiện tại: {st.upper()}",
                "action": "open_gpm",
                "time": row["last_checked"] or "Vừa xong"
            })

        # 2. Lỗi tải video từ YouTube hoặc lỗi Render
        cursor.execute("""
            SELECT yt_video_id, title, original_url, status, error_message, created_at
            FROM videos
            WHERE status = 'error'
            ORDER BY id DESC LIMIT 12
        """)
        for row in cursor.fetchall():
            err_msg = row["error_message"] or "Lỗi không xác định khi tải/render video"
            issues.append({
                "id": f"vid_{row['yt_video_id']}",
                "category": "video_error",
                "severity": "warning",
                "title": "Lỗi Tải / Render Video",
                "target": row["title"] or f"Video ID: {row['yt_video_id']}",
                "message": err_msg,
                "action": "retry_video",
                "time": row["created_at"] or "Gần đây"
            })

        # 3. Lỗi đăng bài TikTok (Upload Tasks Failed)
        cursor.execute("""
            SELECT ut.id, ut.title, ut.error_message, ut.created_at, gp.name as profile_name
            FROM upload_tasks ut
            LEFT JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
            WHERE ut.status = 'failed'
            ORDER BY ut.id DESC LIMIT 10
        """)
        for row in cursor.fetchall():
            issues.append({
                "id": f"upload_{row['id']}",
                "category": "upload_failure",
                "severity": "error",
                "title": "Tác vụ đăng TikTok thất bại",
                "target": f"{row['title']} (GPM: {row['profile_name'] or 'N/A'})",
                "message": row["error_message"] or "Lỗi khi upload lên TikTok",
                "action": "retry_upload",
                "time": row["created_at"] or "Gần đây"
            })

        # 4. Lỗi gọi AI Models (Quota, Rate Limit 429, Invalid Key 401) trong 24h
        try:
            cursor.execute("""
                SELECT id, provider, model, task, error_message, created_at
                FROM ai_usage_logs
                WHERE status = 'error' AND datetime(created_at, 'localtime') >= datetime('now', '-24 hours', 'localtime')
                ORDER BY id DESC LIMIT 8
            """)
            for row in cursor.fetchall():
                err_m = row["error_message"] or "Lỗi gọi AI Model"
                sev = "error" if any(k in err_m.lower() for k in ("429", "401", "quota", "key")) else "warning"
                issues.append({
                    "id": f"ai_{row['id']}",
                    "category": "ai_limit",
                    "severity": sev,
                    "title": f"Lỗi AI {row['provider']} ({row['model']})",
                    "target": f"Nhiệm vụ: {row['task']}",
                    "message": err_m,
                    "action": "check_ai_settings",
                    "time": row["created_at"] or "Gần đây"
                })
        except Exception:
            pass

        conn.close()
    except Exception as e:
        logger.error(f"Lỗi truy vấn active issues: {e}")

    # 5. Kiểm tra tình trạng GPMLogin App
    gpm_health = gpm_client.check_health()
    if not gpm_health.get("running"):
        issues.append({
            "id": "gpm_offline",
            "category": "system_service",
            "severity": "warning",
            "title": "Phần mềm GPMLogin chưa mở",
            "target": "GPMLogin Local API (:9495 / :19995)",
            "message": gpm_health.get("message", "Chưa kết nối được cổng API GPMLogin"),
            "action": "start_gpm",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })

    return {
        "total_count": len(issues),
        "has_critical": any(i["severity"] == "error" for i in issues),
        "issues": issues
    }

@app.get("/api/dashboard/stats")
def get_dashboard_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM channels")
    total_channels = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM videos")
    total_videos = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM gpm_profiles")
    total_profiles = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM gpm_profiles WHERE eligible_10k = 1")
    eligible_10k = cursor.fetchone()[0]

    cursor.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT 20")
    logs = [dict(r) for r in cursor.fetchall()]

    conn.close()

    gpm_status = gpm_client.check_health()
    active_issues = get_system_active_issues()

    return {
        "total_channels": total_channels,
        "total_videos": total_videos,
        "total_profiles": total_profiles,
        "eligible_10k_count": eligible_10k,
        "gpm_health": gpm_status,
        "recent_logs": logs,
        "active_issues_count": active_issues["total_count"],
        "has_critical_issues": active_issues["has_critical"],
        "active_issues": active_issues["issues"][:6]
    }

# --- GPMLogin API ---
@app.get("/api/gpm/health")
def check_gpm_health():
    return gpm_client.check_health()

@app.post("/api/gpm/sync")
def sync_gpm_profiles():
    """Đồng bộ toàn bộ danh sách profile từ GPMLogin vào database (thêm mới, cập nhật và xóa profile đã bị xóa trên GPM)"""
    profiles = gpm_client.get_profiles()
    if not profiles:
        return {"status": "warning", "message": "Không tìm thấy profile nào từ GPMLogin (hoặc GPM chưa mở)", "synced": 0}

    conn = get_connection()
    cursor = conn.cursor()
    active_gpm_ids = set()
    synced = 0
    for p in profiles:
        active_gpm_ids.add(p["id"])
        cursor.execute('''
        INSERT INTO gpm_profiles (gpm_id, name, raw_proxy)
        VALUES (?, ?, ?)
        ON CONFLICT(gpm_id) DO UPDATE SET
            name = excluded.name,
            raw_proxy = excluded.raw_proxy
        ''', (p["id"], p["name"], p["raw_proxy"]))
        synced += 1

    # Xóa các profile trong DB mà không còn tồn tại trên GPMLogin
    removed_count = 0
    if active_gpm_ids:
        cursor.execute("SELECT gpm_id, name FROM gpm_profiles")
        for db_p in cursor.fetchall():
            if db_p["gpm_id"] not in active_gpm_ids:
                cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id = ?", (db_p["gpm_id"],))
                removed_count += 1
                log_event("INFO", f"Tự động gỡ bỏ profile '{db_p['name']}' ({db_p['gpm_id']}) do đã bị xóa trên GPMLogin.")

    conn.commit()
    conn.close()

    msg = f"Đã đồng bộ {synced} profile từ GPMLogin"
    if removed_count > 0:
        msg += f" (đã gỡ bỏ {removed_count} profile không còn tồn tại)"
    log_event("INFO", msg)
    return {"status": "success", "synced": synced, "removed": removed_count, "message": msg}

@app.get("/api/gpm/profiles")
def list_gpm_profiles():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gpm_profiles ORDER BY followers_count DESC, id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.delete("/api/gpm/profiles/{gpm_id}")
def delete_gpm_profile(gpm_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy profile GPMLogin")

    p_name = row["name"]
    cursor.execute("DELETE FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã xóa profile '{p_name}' ({gpm_id}) khỏi hệ thống quản lý Farm")
    return {"status": "success", "message": f"Đã xóa profile '{p_name}' thành công"}

# --- YouTube Intelligence API ---
@app.post("/api/youtube/search")
def search_youtube_channels(req: SearchKeywordRequest):
    """Tìm kiếm và lọc kênh theo từ khóa và tần suất ra video"""
    kw = (req.keyword or "").strip()
    if not kw:
        raise HTTPException(status_code=400, detail="Vui lòng nhập từ khóa tìm kiếm YouTube!")
    if req.max_results < 1 or req.max_results > 50:
        raise HTTPException(status_code=400, detail="Số lượng kênh tìm kiếm phải từ 1 đến 50!")
    results = yt_scanner.search_channels_by_keyword(kw, req.max_results)

    # Đánh dấu các kênh đã lưu trong DB
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT channel_id FROM channels")
        saved_ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        for ch in results:
            ch["is_saved"] = ch.get("channel_id") in saved_ids
    except Exception:
        for ch in results:
            ch["is_saved"] = False

    return {"keyword": req.keyword, "count": len(results), "channels": results}

@app.post("/api/youtube/save-channels")
def save_channels(channels: List[Dict[str, Any]]):
    yt_scanner.save_channels_to_db(channels)
    return {"status": "success", "saved": len(channels)}

@app.post("/api/youtube/unsave-channel")
def unsave_channel(req: UnsaveChannelRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (req.channel_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã bỏ lưu kênh YouTube (channel_id: {req.channel_id})")
    return {"status": "success", "deleted": deleted}

@app.delete("/api/youtube/channels/{channel_id}")
def delete_channel(channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM channels WHERE channel_id = ?", (channel_id,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã xóa kênh YouTube (channel_id: {channel_id})")
    return {"status": "success", "deleted": deleted}

@app.get("/api/youtube/channels")
def list_saved_channels():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, 
            (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id) as downloaded_count,
            (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id AND v.status = 'rendered') as rendered_count
        FROM channels c 
        ORDER BY c.is_active DESC, c.id DESC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

@app.get("/api/youtube/channels/{channel_id}")
def get_channel_detail(channel_id: str):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT c.*, 
            (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id) as downloaded_count,
            (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id AND v.status = 'rendered') as rendered_count
        FROM channels c 
        WHERE c.channel_id = ?
    ''', (channel_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        ch = dict(row)
        for field in ["keywords", "topic_categories", "recent_video_titles"]:
            if isinstance(ch.get(field), str):
                try:
                    ch[field] = json.loads(ch[field])
                except Exception:
                    ch[field] = []
        ch["is_saved"] = True
        return ch

    # Check scanner cache if not in saved channels table
    cached = yt_scanner._load_cached([channel_id])
    if channel_id in cached:
        ch = cached[channel_id]
        ch["is_saved"] = False
        return ch

    raise HTTPException(status_code=404, detail="Không tìm thấy thông tin kênh")

@app.post("/api/youtube/channels/update")
def update_channel_settings(req: UpdateChannelSettingsRequest):
    cid = (req.channel_id or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Mã kênh YouTube (channel_id) không được để trống!")
    if req.bgm_volume is not None and (req.bgm_volume < 0.0 or req.bgm_volume > 1.0):
        raise HTTPException(status_code=400, detail="Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0!")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE channels SET
            display_name = ?,
            custom_proxy = ?,
            download_dir = ?,
            render_dir = ?,
            is_active = ?,
            auto_download = ?,
            auto_render = ?,
            bgm_folder = ?,
            bgm_volume = ?
        WHERE channel_id = ?
    ''', (
        req.display_name or '',
        req.custom_proxy or '',
        req.download_dir or '',
        req.render_dir or '',
        1 if req.is_active else 0,
        1 if req.auto_download else 0,
        1 if req.auto_render else 0,
        req.bgm_folder or '',
        float(req.bgm_volume) if req.bgm_volume is not None else 0.15,
        req.channel_id
    ))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã cập nhật cài đặt kênh: {req.channel_id}")
    return {"status": "success", "message": "Đã lưu cài đặt kênh thành công"}

@app.post("/api/youtube/channels/toggle-status")
def toggle_channel_status(req: ToggleChannelStatusRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active, display_name, title FROM channels WHERE channel_id = ?", (req.channel_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh")
    
    current_status = row["is_active"]
    new_status = (1 if req.is_active else 0) if req.is_active is not None else (0 if current_status == 1 else 1)
    cursor.execute("UPDATE channels SET is_active = ?, auto_download = ? WHERE channel_id = ?", (new_status, new_status, req.channel_id))
    conn.commit()
    conn.close()
    name = row["display_name"] or row["title"]
    state_label = "Hoạt động (Tự động tải & render)" if new_status == 1 else "Tạm ngưng (Dừng tải & render)"
    log_event("INFO", f"Chuyển trạng thái kênh '{name}' sang: {state_label}")
    return {"status": "success", "is_active": new_status, "state_label": state_label}

@app.post("/api/youtube/channels/clear-history")
def clear_channel_history(req: ClearChannelHistoryRequest):
    conn = get_connection()
    cursor = conn.cursor()
    target = (req.target or "all").lower()

    files_deleted = 0
    deleted_count = 0

    if target == "downloaded":
        cursor.execute("SELECT id, download_path, rendered_path FROM videos WHERE channel_id = ? AND download_path IS NOT NULL AND download_path != ''", (req.channel_id,))
        rows = cursor.fetchall()
        for r in rows:
            if req.delete_files and r["download_path"] and os.path.exists(r["download_path"]):
                try:
                    os.remove(r["download_path"])
                    files_deleted += 1
                except Exception:
                    pass
            if r["rendered_path"]:
                cursor.execute("UPDATE videos SET download_path = NULL WHERE id = ?", (r["id"],))
                deleted_count += 1
            else:
                cursor.execute("DELETE FROM videos WHERE id = ?", (r["id"],))
                deleted_count += 1
        log_msg = f"Đã xóa lịch sử {deleted_count} video đã tải ({files_deleted} files) của kênh {req.channel_id}"

    elif target == "rendered":
        cursor.execute("SELECT id, download_path, rendered_path FROM videos WHERE channel_id = ? AND rendered_path IS NOT NULL AND rendered_path != ''", (req.channel_id,))
        rows = cursor.fetchall()
        for r in rows:
            if req.delete_files and r["rendered_path"] and os.path.exists(r["rendered_path"]):
                try:
                    os.remove(r["rendered_path"])
                    files_deleted += 1
                except Exception:
                    pass
            if r["download_path"]:
                cursor.execute("UPDATE videos SET rendered_path = NULL, status = 'downloaded' WHERE id = ?", (r["id"],))
                deleted_count += 1
            else:
                cursor.execute("DELETE FROM videos WHERE id = ?", (r["id"],))
                deleted_count += 1
        log_msg = f"Đã xóa lịch sử {deleted_count} video đã render ({files_deleted} files) của kênh {req.channel_id}"

    else:
        cursor.execute("SELECT id, download_path, rendered_path FROM videos WHERE channel_id = ?", (req.channel_id,))
        rows = cursor.fetchall()
        if req.delete_files:
            for r in rows:
                if r["download_path"] and os.path.exists(r["download_path"]):
                    try:
                        os.remove(r["download_path"])
                        files_deleted += 1
                    except Exception:
                        pass
                if r["rendered_path"] and os.path.exists(r["rendered_path"]):
                    try:
                        os.remove(r["rendered_path"])
                        files_deleted += 1
                    except Exception:
                        pass

        cursor.execute("DELETE FROM videos WHERE channel_id = ?", (req.channel_id,))
        deleted_count = cursor.rowcount
        log_msg = f"Đã xóa lịch sử {deleted_count} video ({files_deleted} files) của kênh {req.channel_id}"

    conn.commit()
    conn.close()
    log_event("INFO", log_msg)
    return {"status": "success", "deleted_videos": deleted_count, "files_deleted": files_deleted, "target": target}

@app.post("/api/youtube/channels/scan-now")
def scan_channel_now(req: ScanChannelRequest):
    result = yt_monitor.scan_single_channel(req.channel_id)
    return result

@app.get("/api/channels/{channel_id}/videos")
def get_channel_videos(channel_id: str):
    """Lấy danh sách toàn bộ video và trạng thái render thuộc một kênh theo dõi"""
    sync_local_videos_with_db()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.*, COALESCE(c.display_name, c.title, 'Kênh Nguồn') as channel_name, c.render_dir as ch_render_dir
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.channel_id = ?
        ORDER BY v.id DESC
    """, (channel_id,))
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    from backend.config import RENDERED_DIR
    for r in rows:
        vid_id = r.get("yt_video_id") or ""
        rendered_parts = []
        dirs_to_check = []
        if r.get("rendered_path") and os.path.exists(r["rendered_path"]):
            parent_dir = Path(r["rendered_path"]).parent
            if parent_dir not in dirs_to_check:
                dirs_to_check.append(parent_dir)
        if r.get("ch_render_dir") and os.path.exists(r["ch_render_dir"]):
            ch_dir = Path(r["ch_render_dir"])
            if ch_dir not in dirs_to_check:
                dirs_to_check.append(ch_dir)
        if RENDERED_DIR not in dirs_to_check and RENDERED_DIR.exists():
            dirs_to_check.append(RENDERED_DIR)

        found_files = set()
        for d in dirs_to_check:
            if vid_id and os.path.exists(d):
                for p in Path(d).rglob(f"*{vid_id}*.mp4"):
                    if str(p) not in found_files:
                        found_files.add(str(p))
                        part_m = re.search(r'Part(\d+)', p.name, re.IGNORECASE)
                        p_num = int(part_m.group(1)) if part_m else 1
                        rendered_parts.append({
                            "part": p_num,
                            "filename": p.name,
                            "path": str(p),
                            "url": f"/api/video/stream/{r['id']}?type=rendered&part={p_num}"
                        })

        part_map = {}
        for rp in rendered_parts:
            p_num = rp["part"]
            mtime = os.path.getmtime(rp["path"]) if os.path.exists(rp["path"]) else 0
            if p_num not in part_map or mtime > part_map[p_num]["mtime"]:
                part_map[p_num] = {"rp": rp, "mtime": mtime}
        rendered_parts = [v["rp"] for k, v in sorted(part_map.items())]
        r["rendered_parts"] = rendered_parts

        has_raw = bool(r.get("download_path") and os.path.exists(r["download_path"]))
        has_rendered = len(rendered_parts) > 0 or bool(r.get("rendered_path") and os.path.exists(r["rendered_path"]))
        r["has_raw"] = has_raw
        r["has_rendered"] = has_rendered

    return {"status": "success", "videos": rows, "count": len(rows)}

@app.get("/api/pipeline/status")
def get_pipeline_status():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM channels WHERE is_active = 1")
    active_channels = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM channels")
    total_channels = cursor.fetchone()[0]

    cursor.execute("SELECT status, COUNT(*) as cnt FROM videos GROUP BY status")
    video_stats = {r["status"]: r["cnt"] for r in cursor.fetchall()}

    cursor.execute("SELECT COUNT(*) FROM videos WHERE download_path IS NOT NULL AND download_path != ''")
    downloaded = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM videos WHERE rendered_path IS NOT NULL AND rendered_path != ''")
    rendered = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM upload_tasks WHERE status = 'queued'")
    queued = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM upload_tasks WHERE status = 'completed'")
    uploaded = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM campaigns WHERE is_active = 1")
    active_campaigns = cursor.fetchone()[0]

    cursor.execute('''
        SELECT v.id, v.title, v.duration, v.status, v.created_at, v.channel_id,
               COALESCE(c.display_name, c.title, 'Kênh ngoài') as channel_name
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        ORDER BY v.id DESC LIMIT 50
    ''')
    recent_videos = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
        SELECT ut.*, gp.name as gpm_profile_name, gp.tiktok_username, v.title as video_title
        FROM upload_tasks ut
        LEFT JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
        LEFT JOIN videos v ON ut.video_id = v.id
        ORDER BY ut.id DESC LIMIT 50
    ''')
    recent_tasks = [dict(r) for r in cursor.fetchall()]
    conn.close()

    return {
        "status": "success",
        "scheduler_running": scheduler.is_running,
        "scheduler_interval_minutes": getattr(scheduler, "rss_interval_minutes", 15),
        "upload_interval_seconds": getattr(scheduler, "upload_interval_seconds", 60),
        "auto_download": getattr(scheduler, "auto_download", True),
        "auto_render": getattr(scheduler, "auto_render", True),
        "max_videos_per_scan": getattr(scheduler, "max_videos_per_scan", 5),
        "channel_delay_seconds": getattr(scheduler, "channel_delay_seconds", 2),
        "active_channels": active_channels,
        "total_channels": total_channels,
        "downloaded_count": downloaded,
        "rendered_count": rendered,
        "queued_count": queued,
        "uploaded_count": uploaded,
        "active_campaigns": active_campaigns,
        "video_stats": {
            "pending": video_stats.get("pending", 0),
            "downloaded": video_stats.get("downloaded", downloaded),
            "rendering": video_stats.get("rendering", 0),
            "rendered": video_stats.get("rendered", rendered),
            "uploaded": video_stats.get("uploaded", uploaded),
            "error": video_stats.get("error", 0)
        },
        "recent_pipeline": recent_videos,
        "recent_upload_tasks": recent_tasks
    }

@app.post("/api/pipeline/toggle-scheduler")
def toggle_pipeline_scheduler():
    if scheduler.is_running:
        scheduler.stop()
        log_event("WARNING", "Đã tạm dừng Background Automation Scheduler.")
        running_flag = "0"
        state = False
    else:
        scheduler.start()
        log_event("INFO", f"Đã bật chạy Background Automation Scheduler ({scheduler.rss_interval_minutes}p/lần).")
        running_flag = "1"
        state = True
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scheduler_running', ?)", (running_flag,))
        conn.commit()
        conn.close()
    except Exception:
        pass
    return {"status": "success", "running": state, "scheduler_running": state}

@app.post("/api/pipeline/retry-upload/{task_id}")
def retry_upload_task(task_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM upload_tasks WHERE id = ?", (task_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy tác vụ upload")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        UPDATE upload_tasks 
        SET status = 'queued', 
            scheduled_time = ?, 
            retry_count = 0, 
            retry_after = NULL, 
            processing_started_at = NULL, 
            error_message = NULL 
        WHERE id = ?
    """, (now_str, task_id))
    conn.commit()
    conn.close()
    return {"status": "success", "message": f"Đã đưa tác vụ #{task_id} trở lại hàng đợi đăng bài ngay lập tức"}

@app.post("/api/pipeline/process-uploads")
def trigger_process_uploads(bg_tasks: BackgroundTasks):
    def _run_upload():
        try:
            scheduler._process_pending_uploads()
        except Exception as e:
            log_event("WARNING", f"Lỗi thủ công xử lý hàng đợi upload: {e}")
    bg_tasks.add_task(_run_upload)
    return {"status": "success", "message": "Đã kích hoạt kiểm tra và đăng hàng đợi upload"}

@app.post("/api/pipeline/scan-all")
def scan_all_channels_pipeline(bg_tasks: BackgroundTasks):
    def _do_scan():
        try:
            total = yt_monitor.scan_all_monitored_channels(
                max_per_channel=getattr(scheduler, "max_videos_per_scan", 5),
                delay=float(getattr(scheduler, "channel_delay_seconds", 2))
            )
            log_event("INFO", f"[PIPELINE SCAN] Quét xong toàn bộ kênh, tìm thấy {total} video mới.")
        except Exception as e:
            log_event("ERROR", f"[PIPELINE SCAN] Lỗi khi quét: {e}")
    bg_tasks.add_task(_do_scan)
    return {"status": "success", "message": "Đang chạy quét toàn bộ kênh ngầm..."}

def cleanup_uploaded_files(retention_mode=None, custom_days=None):
    """
    Tự động dọn dẹp các tệp tin video .mp4 (gốc và 9:16) của các video đã đăng thành công lên TikTok
    quá thời hạn lưu trữ (retention period).
    Dữ liệu SQLite (videos, upload_tasks, campaign_logs) được BẢO TỒN NGUYÊN VẸN để chống trùng lặp vĩnh viễn!
    """
    conn = get_connection()
    cursor = conn.cursor()

    if retention_mode is None:
        cursor.execute("SELECT value FROM settings WHERE key = 'cleanup_retention_mode'")
        row = cursor.fetchone()
        retention_mode = row["value"] if row else "7"

    if retention_mode == "never":
        conn.close()
        return {
            "status": "success",
            "files_deleted": 0,
            "bytes_freed": 0,
            "mb_freed": 0,
            "cleaned_videos": 0,
            "message": "Chế độ không bao giờ tự động xóa file đang được chọn"
        }

    if custom_days is None:
        cursor.execute("SELECT value FROM settings WHERE key = 'cleanup_custom_days'")
        row = cursor.fetchone()
        custom_days = int(row["value"]) if (row and str(row["value"]).isdigit()) else 7

    if retention_mode in ("0", "immediate"):
        target_days = 0
    elif retention_mode == "custom":
        target_days = max(1, int(custom_days))
    else:
        try:
            target_days = int(retention_mode)
        except Exception:
            target_days = 7

    cursor.execute('''
        SELECT ut.id as task_id, ut.video_id, ut.uploaded_at,
               v.download_path, v.rendered_path, v.title
        FROM upload_tasks ut
        JOIN videos v ON ut.video_id = v.id
        WHERE ut.status = 'completed'
          AND ut.uploaded_at IS NOT NULL
          AND (
            (v.download_path IS NOT NULL AND v.download_path != '')
            OR
            (v.rendered_path IS NOT NULL AND v.rendered_path != '')
          )
    ''')
    tasks = [dict(r) for r in cursor.fetchall()]

    files_deleted = 0
    bytes_freed = 0
    cleaned_video_ids = set()
    now = datetime.now()

    for t in tasks:
        uploaded_at_str = t["uploaded_at"]
        try:
            cleaned_str = str(uploaded_at_str).replace("T", " ").replace("Z", "")[:19]
            task_time = datetime.strptime(cleaned_str, "%Y-%m-%d %H:%M:%S")
        except Exception:
            task_time = now

        age_seconds = (now - task_time).total_seconds()
        threshold_seconds = target_days * 86400

        if age_seconds >= threshold_seconds:
            v_id = t["video_id"]
            dp = t.get("download_path")
            rp = t.get("rendered_path")
            removed_any = False

            if dp and os.path.exists(dp):
                try:
                    bytes_freed += os.path.getsize(dp)
                    os.remove(dp)
                    files_deleted += 1
                    removed_any = True
                except Exception:
                    pass

            if rp and os.path.exists(rp):
                try:
                    bytes_freed += os.path.getsize(rp)
                    os.remove(rp)
                    files_deleted += 1
                    removed_any = True
                except Exception:
                    pass

            if removed_any or (dp and not os.path.exists(dp)) or (rp and not os.path.exists(rp)):
                cursor.execute("UPDATE videos SET download_path = '', rendered_path = '' WHERE id = ?", (v_id,))
                cleaned_video_ids.add(v_id)

    conn.commit()
    conn.close()

    mb_freed = round(bytes_freed / (1024 * 1024), 2)
    if files_deleted > 0:
        log_event("INFO", f"[CLEANUP] Đã giải phóng {mb_freed} MB ({files_deleted} file mp4) từ {len(cleaned_video_ids)} video đã đăng (> {target_days} ngày).")

    return {
        "status": "success",
        "files_deleted": files_deleted,
        "bytes_freed": bytes_freed,
        "mb_freed": mb_freed,
        "cleaned_videos": len(cleaned_video_ids),
        "target_days": target_days
    }

@app.get("/api/settings/cleanup")
def get_cleanup_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('cleanup_retention_mode', 'cleanup_custom_days')")
    db_settings = dict(cursor.fetchall())
    conn.close()
    return {
        "status": "success",
        "retention_mode": db_settings.get("cleanup_retention_mode", "7"),
        "custom_days": int(db_settings.get("cleanup_custom_days", 7))
    }

@app.post("/api/settings/cleanup")
def save_cleanup_settings(req: CleanupSettingsRequest):
    if req.custom_days is not None and (req.custom_days < 1 or req.custom_days > 3650):
        raise HTTPException(status_code=400, detail="Số ngày dọn dẹp tùy chỉnh phải từ 1 đến 3650 ngày!")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cleanup_retention_mode', ?)", (req.retention_mode,))
    if req.custom_days is not None:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('cleanup_custom_days', ?)", (str(req.custom_days),))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã lưu chính sách dọn dẹp ổ đĩa: Chế độ '{req.retention_mode}' ({req.custom_days} ngày).")
    return {"status": "success", "message": "Đã lưu chính sách dọn dẹp ổ đĩa thành công"}

@app.post("/api/pipeline/cleanup-uploaded")
def trigger_pipeline_cleanup(req: Optional[TriggerCleanupRequest] = None):
    mode = req.mode if req else None
    days = req.custom_days if req else None
    res = cleanup_uploaded_files(retention_mode=mode, custom_days=days)
    return res

@app.get("/api/settings/download-filter")
def get_download_filter_settings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key IN ('download_min_duration', 'download_max_duration')")
    db_s = dict(cursor.fetchall())
    conn.close()
    return {
        "status": "success",
        "min_video_duration": int(db_s.get("download_min_duration", 300)),
        "max_video_duration": int(db_s.get("download_max_duration", 3600)),
    }

@app.post("/api/settings/download-filter")
def save_download_filter_settings(req: DownloadFilterSettingsRequest):
    if req.min_video_duration < 0:
        raise HTTPException(status_code=400, detail="Thời lượng tối thiểu không thể là số âm!")
    if req.max_video_duration <= req.min_video_duration:
        raise HTTPException(status_code=400, detail="Thời lượng tối đa phải lớn hơn thời lượng tối thiểu!")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_min_duration', ?)", (str(req.min_video_duration),))
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_max_duration', ?)", (str(req.max_video_duration),))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã lưu bộ lọc tải video: min={req.min_video_duration}s, max={req.max_video_duration}s")
    return {"status": "success", "message": "Đã lưu bộ lọc thời lượng video thành công"}

# --- Auto Campaigns API ---
@app.get("/api/campaigns")
def list_campaigns():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cp.*,
               COALESCE(c.display_name, c.title, cp.channel_id) as channel_name,
               gp.name as gpm_profile_name,
               gp.tiktok_username
        FROM campaigns cp
        LEFT JOIN channels c ON cp.channel_id = c.channel_id
        LEFT JOIN gpm_profiles gp ON cp.gpm_profile_id = gp.id
        ORDER BY cp.id DESC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    for r in rows:
        # Parse channel_ids
        ch_list = []
        if r.get("channel_ids"):
            try:
                ch_list = json.loads(r["channel_ids"])
            except Exception:
                ch_list = [r["channel_id"]] if r.get("channel_id") else []
        elif r.get("channel_id"):
            ch_list = [r["channel_id"]]
        r["channel_ids_list"] = ch_list
        r["channel_count"] = len(ch_list)

        # Parse gpm_profile_ids
        gpm_list = []
        if r.get("gpm_profile_ids"):
            try:
                gpm_list = json.loads(r["gpm_profile_ids"])
            except Exception:
                gpm_list = [r["gpm_profile_id"]] if r.get("gpm_profile_id") else []
        elif r.get("gpm_profile_id"):
            gpm_list = [r["gpm_profile_id"]]
        r["gpm_profile_ids_list"] = gpm_list
        r["gpm_count"] = len(gpm_list)
    return rows

def sanitize_campaign_schedule(raw_str: str) -> str:
    """Kiểm tra và chuẩn hóa khung giờ đăng bài HH:MM"""
    if not raw_str:
        return "11:30, 18:00, 20:30"
    valid_slots = []
    for part in str(raw_str).split(","):
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([0-1]?[0-9]|2[0-3]):([0-5][0-9])$", part)
        if m:
            h, m_val = int(m.group(1)), int(m.group(2))
            valid_slots.append(f"{h:02d}:{m_val:02d}")
    if not valid_slots:
        return "11:30, 18:00, 20:30"
    seen = set()
    clean = []
    for s in valid_slots:
        if s not in seen:
            seen.add(s)
            clean.append(s)
    return ", ".join(clean)

@app.post("/api/campaigns")
def create_campaign(req: CreateCampaignRequest):
    if not req.name or not req.name.strip():
        raise HTTPException(status_code=400, detail="Tên chiến dịch không được để trống!")
    ch_ids = req.channel_ids if req.channel_ids else ([req.channel_id] if req.channel_id else [])
    if not ch_ids:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất một kênh YouTube nguồn!")
    gpm_ids = req.gpm_profile_ids if req.gpm_profile_ids else ([req.gpm_profile_id] if req.gpm_profile_id else [])
    if not gpm_ids:
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất một Profile GPMLogin đích!")
    if req.min_video_duration is not None and req.max_video_duration is not None:
        if req.min_video_duration >= req.max_video_duration:
            raise HTTPException(status_code=400, detail="Thời lượng cắt tối thiểu phải nhỏ hơn thời lượng tối đa!")
    if req.clips_per_video is not None and (req.clips_per_video < 1 or req.clips_per_video > 20):
        raise HTTPException(status_code=400, detail="Số đoạn cắt mỗi video phải từ 1 đến 20!")
    if req.bgm_volume is not None and (req.bgm_volume < 0.0 or req.bgm_volume > 1.0):
        raise HTTPException(status_code=400, detail="Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0!")

    conn = get_connection()
    cursor = conn.cursor()

    main_ch = ch_ids[0] if ch_ids else ""
    main_gpm = gpm_ids[0] if gpm_ids else None

    # Validate daily_limit: can't be smaller than 1 and must be positive integer
    safe_daily_limit = max(1, int(req.daily_limit or 1))
    safe_schedule = sanitize_campaign_schedule(req.post_schedule)

    cursor.execute('''
        INSERT INTO campaigns (
            name, channel_id, gpm_profile_id, channel_ids, gpm_profile_ids,
            distribution_mode, download_dir, render_dir, subtitle_enabled,
            subtitle_style, aspect_ratio, preset_name, video_duration,
            speed_factor, flip_horizontal, daily_limit, post_schedule,
            post_frequency, post_interval_days, post_days_of_week,
            random_delay_minutes, warmup_mode, ai_provider, ai_model,
            min_video_duration, max_video_duration, add_part_label, clips_per_video,
            bgm_folder, bgm_volume, is_active, min_post_interval_minutes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        req.name,
        main_ch,
        main_gpm,
        json.dumps(ch_ids),
        json.dumps(gpm_ids),
        req.distribution_mode or 'round_robin',
        req.download_dir or '',
        req.render_dir or '',
        1 if req.subtitle_enabled else 0,
        req.subtitle_style or 'karaoke_yellow',
        req.aspect_ratio or '9:16_blur',
        req.preset_name or 'TikTok Beta Chuẩn 9:16',
        req.video_duration or 65,
        req.speed_factor or 1.03,
        1 if req.flip_horizontal else 0,
        safe_daily_limit,
        safe_schedule,
        req.post_frequency or 'daily',
        req.post_interval_days or 1,
        req.post_days_of_week or 'mon,tue,wed,thu,fri,sat,sun',
        req.random_delay_minutes if req.random_delay_minutes is not None else 10,
        1 if req.warmup_mode else 0,
        req.ai_provider or 'default',
        req.ai_model or 'default',
        req.min_video_duration,
        req.max_video_duration,
        1 if req.add_part_label != 0 else 0,
        req.clips_per_video or 3,
        req.bgm_folder or '',
        float(req.bgm_volume) if req.bgm_volume is not None else 0.15,
        1 if req.is_active else 0,
        req.min_post_interval_minutes
    ))
    campaign_id = cursor.lastrowid
    # Persist last used download/render dirs in settings table for future campaigns
    if req.download_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_download_dir', ?)", (req.download_dir.strip(),))
    if req.render_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_render_dir', ?)", (req.render_dir.strip(),))
    conn.commit()
    conn.close()
    log_campaign_event(campaign_id, "INFO", "system", f"Khởi tạo chiến dịch: '{req.name}' ({len(ch_ids)} kênh -> {len(gpm_ids)} nick GPM)")
    return {"status": "success", "id": campaign_id, "channels_count": len(ch_ids), "profiles_count": len(gpm_ids)}

@app.get("/api/campaigns/{campaign_id}")
def get_campaign(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT cp.*,
               COALESCE(c.display_name, c.title, cp.channel_id) as channel_name,
               gp.name as gpm_profile_name,
               gp.tiktok_username
        FROM campaigns cp
        LEFT JOIN channels c ON cp.channel_id = c.channel_id
        LEFT JOIN gpm_profiles gp ON cp.gpm_profile_id = gp.id
        WHERE cp.id = ?
    ''', (campaign_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    r = dict(row)
    # Parse channels & gpms
    ch_list = []
    if r.get("channel_ids"):
        try:
            ch_list = json.loads(r["channel_ids"])
        except Exception:
            ch_list = [r["channel_id"]] if r.get("channel_id") else []
    elif r.get("channel_id"):
        ch_list = [r["channel_id"]]
    r["channel_ids_list"] = ch_list

    gpm_list = []
    if r.get("gpm_profile_ids"):
        try:
            gpm_list = json.loads(r["gpm_profile_ids"])
        except Exception:
            gpm_list = [r["gpm_profile_id"]] if r.get("gpm_profile_id") else []
    elif r.get("gpm_profile_id"):
        gpm_list = [r["gpm_profile_id"]]
    r["gpm_profile_ids_list"] = gpm_list
    return r

@app.put("/api/campaigns/{campaign_id}")
def update_campaign(campaign_id: int, req: CreateCampaignRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM campaigns WHERE id = ?", (campaign_id,))
    existing = cursor.fetchone()
    if not existing:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch để cập nhật")

    if not req.name or not req.name.strip():
        conn.close()
        raise HTTPException(status_code=400, detail="Tên chiến dịch không được để trống!")
    ch_ids = req.channel_ids if req.channel_ids else ([req.channel_id] if req.channel_id else [])
    if not ch_ids:
        conn.close()
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất một kênh YouTube nguồn!")
    gpm_ids = req.gpm_profile_ids if req.gpm_profile_ids else ([req.gpm_profile_id] if req.gpm_profile_id else [])
    if not gpm_ids:
        conn.close()
        raise HTTPException(status_code=400, detail="Vui lòng chọn ít nhất một Profile GPMLogin đích!")
    if req.min_video_duration is not None and req.max_video_duration is not None:
        if req.min_video_duration >= req.max_video_duration:
            conn.close()
            raise HTTPException(status_code=400, detail="Thời lượng cắt tối thiểu phải nhỏ hơn thời lượng tối đa!")
    if req.clips_per_video is not None and (req.clips_per_video < 1 or req.clips_per_video > 20):
        conn.close()
        raise HTTPException(status_code=400, detail="Số đoạn cắt mỗi video phải từ 1 đến 20!")
    if req.bgm_volume is not None and (req.bgm_volume < 0.0 or req.bgm_volume > 1.0):
        conn.close()
        raise HTTPException(status_code=400, detail="Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0!")

    main_ch = ch_ids[0] if ch_ids else ""
    main_gpm = gpm_ids[0] if gpm_ids else None

    # Validate daily_limit: can't be smaller than 1 and must be positive integer
    safe_daily_limit = max(1, int(req.daily_limit or 1))
    safe_schedule = sanitize_campaign_schedule(req.post_schedule)

    cursor.execute('''
        UPDATE campaigns SET
            name = ?,
            channel_id = ?,
            gpm_profile_id = ?,
            channel_ids = ?,
            gpm_profile_ids = ?,
            distribution_mode = ?,
            download_dir = ?,
            render_dir = ?,
            subtitle_enabled = ?,
            subtitle_style = ?,
            aspect_ratio = ?,
            preset_name = ?,
            video_duration = ?,
            speed_factor = ?,
            flip_horizontal = ?,
            daily_limit = ?,
            post_schedule = ?,
            post_frequency = ?,
            post_interval_days = ?,
            post_days_of_week = ?,
            random_delay_minutes = ?,
            warmup_mode = ?,
            ai_provider = ?,
            ai_model = ?,
            min_video_duration = ?,
            max_video_duration = ?,
            add_part_label = ?,
            clips_per_video = ?,
            bgm_folder = ?,
            bgm_volume = ?,
            min_post_interval_minutes = ?
        WHERE id = ?
    ''', (
        req.name,
        main_ch,
        main_gpm,
        json.dumps(ch_ids),
        json.dumps(gpm_ids),
        req.distribution_mode or 'round_robin',
        req.download_dir or '',
        req.render_dir or '',
        1 if req.subtitle_enabled else 0,
        req.subtitle_style or 'karaoke_yellow',
        req.aspect_ratio or '9:16_blur',
        req.preset_name or 'TikTok Beta Chuẩn 9:16',
        req.video_duration or 65,
        req.speed_factor or 1.03,
        1 if req.flip_horizontal else 0,
        safe_daily_limit,
        safe_schedule,
        req.post_frequency or 'daily',
        req.post_interval_days or 1,
        req.post_days_of_week or 'mon,tue,wed,thu,fri,sat,sun',
        req.random_delay_minutes if req.random_delay_minutes is not None else 10,
        1 if req.warmup_mode else 0,
        req.ai_provider or 'default',
        req.ai_model or 'default',
        req.min_video_duration,
        req.max_video_duration,
        1 if req.add_part_label != 0 else 0,
        req.clips_per_video or 3,
        req.bgm_folder or '',
        float(req.bgm_volume) if req.bgm_volume is not None else 0.15,
        req.min_post_interval_minutes,
        campaign_id
    ))
    if req.download_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_download_dir', ?)", (req.download_dir.strip(),))
    if req.render_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_render_dir', ?)", (req.render_dir.strip(),))
    conn.commit()
    conn.close()
    log_campaign_event(campaign_id, "INFO", "system", f"Đã cập nhật chiến dịch: '{req.name}' ({len(ch_ids)} kênh -> {len(gpm_ids)} nick GPM)")
    return {"status": "success", "message": "Đã lưu thay đổi chiến dịch thành công"}

@app.get("/api/campaigns/{campaign_id}/logs")
def get_campaign_logs(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    camp = cursor.fetchone()
    if not camp:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    camp = dict(camp)
    
    # Lấy logs từ bảng campaign_logs
    cursor.execute("SELECT * FROM campaign_logs WHERE campaign_id = ? ORDER BY id DESC LIMIT 100", (campaign_id,))
    c_logs = [dict(r) for r in cursor.fetchall()]

    # Parse channels & GPM profiles
    ch_ids = []
    try:
        ch_ids = json.loads(camp.get("channel_ids") or "[]")
    except Exception:
        if camp.get("channel_id"): ch_ids = [camp["channel_id"]]
    
    gpm_ids = []
    try:
        gpm_ids = json.loads(camp.get("gpm_profile_ids") or "[]")
    except Exception:
        if camp.get("gpm_profile_id"): gpm_ids = [camp["gpm_profile_id"]]

    # Thống kê video liên quan đến các kênh của chiến dịch này (an toàn cho hàng ngàn kênh)
    total_videos = 0
    downloaded_videos = 0
    rendered_videos = 0
    if ch_ids:
        for i in range(0, len(ch_ids), 400):
            chunk = ch_ids[i:i + 400]
            ph = ",".join("?" for _ in chunk)
            cursor.execute(f"SELECT COUNT(*) FROM videos WHERE channel_id IN ({ph})", tuple(chunk))
            total_videos += cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM videos WHERE channel_id IN ({ph}) AND download_path IS NOT NULL AND download_path != ''", tuple(chunk))
            downloaded_videos += cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM videos WHERE channel_id IN ({ph}) AND rendered_path IS NOT NULL AND rendered_path != ''", tuple(chunk))
            rendered_videos += cursor.fetchone()[0]

    # Thống kê upload tasks của các profile GPM trong chiến dịch này (an toàn cho hàng ngàn profile)
    queued_tasks = 0
    completed_tasks = 0
    failed_tasks = 0
    if gpm_ids:
        for i in range(0, len(gpm_ids), 400):
            chunk = gpm_ids[i:i + 400]
            g_ph = ",".join("?" for _ in chunk)
            cursor.execute(f"SELECT COUNT(*) FROM upload_tasks WHERE gpm_profile_id IN ({g_ph}) AND status = 'queued'", tuple(chunk))
            queued_tasks += cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM upload_tasks WHERE gpm_profile_id IN ({g_ph}) AND status = 'completed'", tuple(chunk))
            completed_tasks += cursor.fetchone()[0]
            cursor.execute(f"SELECT COUNT(*) FROM upload_tasks WHERE gpm_profile_id IN ({g_ph}) AND status = 'failed'", tuple(chunk))
            failed_tasks += cursor.fetchone()[0]

    # Chi tiết danh sách video & tài khoản TikTok nhận bài của chiến dịch này
    campaign_videos = []
    if ch_ids:
        sample_ch_ids = ch_ids[:400]
        placeholders = ",".join("?" for _ in sample_ch_ids)
        cursor.execute(f'''
            SELECT v.id, v.title, v.duration, v.status, v.download_path, v.rendered_path, v.created_at,
                   v.channel_id, COALESCE(c.display_name, c.title, v.channel_id) as channel_name,
                   ut.id as upload_task_id, ut.status as upload_status, ut.scheduled_time, ut.uploaded_at,
                   gp.id as gpm_id, gp.name as gpm_name, gp.tiktok_username
            FROM videos v
            LEFT JOIN channels c ON v.channel_id = c.channel_id
            LEFT JOIN upload_tasks ut ON ut.video_id = v.id
            LEFT JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
            WHERE v.channel_id IN ({placeholders})
            ORDER BY v.id DESC LIMIT 50
        ''', tuple(sample_ch_ids))
        campaign_videos = [dict(r) for r in cursor.fetchall()]

    # Nếu campaign_logs chưa có nhiều, bổ sung logs từ system_logs có liên quan
    if len(c_logs) < 10:
        cursor.execute("SELECT id, level, message, details, created_at FROM system_logs WHERE message LIKE ? OR message LIKE '%SCHEDULER%' OR message LIKE '%PIPELINE%' ORDER BY id DESC LIMIT 30", (f"%{camp['name']}%",))
        for r in cursor.fetchall():
            c_logs.append({
                "id": r["id"],
                "campaign_id": campaign_id,
                "level": r["level"],
                "action": "system",
                "message": r["message"],
                "details": r["details"],
                "created_at": r["created_at"]
            })

    conn.close()
    return {
        "status": "success",
        "campaign": {
            "id": camp["id"],
            "name": camp["name"],
            "is_active": camp["is_active"],
            "created_at": camp["created_at"],
            "distribution_mode": camp["distribution_mode"],
            "post_frequency": camp["post_frequency"],
            "post_schedule": camp["post_schedule"],
            "channels_count": len(ch_ids),
            "gpm_count": len(gpm_ids)
        },
        "stats": {
            "total_videos": total_videos,
            "downloaded_videos": downloaded_videos,
            "rendered_videos": rendered_videos,
            "queued_tasks": queued_tasks,
            "completed_tasks": completed_tasks,
            "failed_tasks": failed_tasks
        },
        "videos": campaign_videos,
        "logs": c_logs[:80]
    }

@app.post("/api/campaigns/{campaign_id}/test-run")
def test_run_campaign(campaign_id: int, bg_tasks: BackgroundTasks):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM campaigns WHERE id = ?", (campaign_id,))
    camp = cursor.fetchone()
    conn.close()
    if not camp:
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    camp = dict(camp)
    
    def _do_campaign_scan():
        try:
            log_campaign_event(campaign_id, "INFO", "scan", f"Bắt đầu quét thủ công cho chiến dịch '{camp['name']}'...")
            ch_ids = []
            try:
                ch_ids = json.loads(camp.get("channel_ids") or "[]")
            except Exception:
                if camp.get("channel_id"): ch_ids = [camp["channel_id"]]

            if not ch_ids:
                log_campaign_event(campaign_id, "WARNING", "scan", "Chiến dịch chưa có kênh nào được liên kết.")
                return

            total_found = 0
            for cid in ch_ids:
                res = yt_monitor.scan_single_channel(cid, force_campaign_id=campaign_id)
                cnt = res.get("new_videos", 0)
                total_found += cnt
                if cnt > 0:
                    log_campaign_event(campaign_id, "INFO", "download", f"Kênh {cid}: Đã phát hiện và tải {cnt} video mới.")

            if total_found == 0:
                # Kiểm tra nếu đã có video tải về trước đó nhưng chưa render
                conn = get_connection()
                cursor = conn.cursor()
                placeholders = ",".join("?" for _ in ch_ids)
                cursor.execute(f"""
                    SELECT v.*, c.display_name, c.title as ch_title
                    FROM videos v
                    LEFT JOIN channels c ON v.channel_id = c.channel_id
                    WHERE v.channel_id IN ({placeholders}) AND (v.rendered_path IS NULL OR v.rendered_path = '')
                    ORDER BY v.id DESC LIMIT 1
                """, tuple(ch_ids))
                pending_v = cursor.fetchone()
                conn.close()

                if pending_v:
                    pending_v = dict(pending_v)
                    v_orig = pending_v.get("original_path")
                    if v_orig and os.path.exists(v_orig):
                        log_campaign_event(campaign_id, "INFO", "pipeline", f"Tìm thấy video có sẵn '{pending_v['title']}', tiến hành render Smart AI theo chiến dịch...")
                        yt_monitor.handle_video_post_download(
                            file_path=v_orig,
                            video_id=pending_v["yt_video_id"],
                            channel_id=pending_v["channel_id"],
                            channel_name=pending_v.get("display_name") or pending_v.get("ch_title") or "",
                            video_title=pending_v["title"],
                            duration=65,
                            channel_obj={"render_dir": camp.get("render_dir")},
                            force_campaign_id=campaign_id
                        )
                        total_found = 1

            log_campaign_event(campaign_id, "SUCCESS", "scan", f"Hoàn tất quét & xử lý chiến dịch '{camp['name']}': tổng cộng {total_found} video.")
        except Exception as e:
            log_campaign_event(campaign_id, "ERROR", "scan", f"Lỗi khi chạy quét chiến dịch: {str(e)}")

    bg_tasks.add_task(_do_campaign_scan)
    return {"status": "success", "message": f"Đang kích hoạt quét và kiểm tra chạy thử cho chiến dịch '{camp['name']}'..."}

@app.post("/api/campaigns/{campaign_id}/toggle")
def toggle_campaign(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_active, name FROM campaigns WHERE id = ?", (campaign_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy chiến dịch")
    new_state = 0 if row["is_active"] == 1 else 1
    cursor.execute("UPDATE campaigns SET is_active = ? WHERE id = ?", (new_state, campaign_id))
    conn.commit()
    conn.close()
    log_campaign_event(campaign_id, "INFO", "system", f"Chuyển trạng thái chiến dịch '{row['name']}' sang: {'Bật' if new_state else 'Tắt'}")
    return {"status": "success", "is_active": new_state}

@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    cursor.execute("DELETE FROM campaign_logs WHERE campaign_id = ?", (campaign_id,))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã xóa chiến dịch ID {campaign_id}")
    return {"status": "success"}



# --- Video Download & AI Edit API ---
@app.post("/api/video/download")
def download_video(req: DownloadVideoRequest, bg_tasks: BackgroundTasks):
    clean_url = (req.url or "").strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Vui lòng nhập link video YouTube!")
    if not is_safe_external_url(clean_url):
        raise HTTPException(
            status_code=400,
            detail="URL không hợp lệ hoặc bị từ chối vì lý do bảo mật (chỉ chấp nhận http/https công khai)"
        )
    target_dir = req.target_dir
    if not target_dir:
        from backend.config import DOWNLOADS_DIR
        direct_dir = DOWNLOADS_DIR / "Direct Links"
        direct_dir.mkdir(parents=True, exist_ok=True)
        target_dir = str(direct_dir)

    result = yt_downloader.download_video(clean_url, target_dir=target_dir, is_studio=req.is_studio)
    if not result:
        raise HTTPException(status_code=400, detail="Không thể tải video từ URL này")
    return {"status": "success", "video": result}

def sync_local_videos_with_db():
    """
    Đồng bộ 2 chiều giữa thư mục đĩa (data/downloads, data/rendered) và SQLite:
    1. Tự động xóa các bản ghi video đã bị xóa file khỏi ổ đĩa
    2. Tự động phát hiện và lập chỉ mục các file video được thêm/chép thủ công vào thư mục
    """
    from backend.config import DOWNLOADS_DIR, RENDERED_DIR
    from backend.modules.video_core.hardware_accel import get_ffmpeg_binary
    import re, subprocess, hashlib

    def _probe_duration(p):
        try:
            bin_path = get_ffmpeg_binary()
            res = subprocess.run([bin_path, "-i", str(p)], capture_output=True, text=True, errors="replace", timeout=8)
            m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", res.stderr)
            if m:
                return round(int(m.group(1))*3600 + int(m.group(2))*60 + float(m.group(3)), 1)
        except Exception:
            pass
        return 65.0

    conn = get_connection()
    cursor = conn.cursor()

    # 1. Quét và dọn dẹp các bản ghi trong DB mà file trên đĩa đã bị xóa
    cursor.execute("SELECT * FROM videos")
    existing_rows = [dict(r) for r in cursor.fetchall()]

    for r in existing_rows:
        has_raw = bool(r.get("download_path") and os.path.exists(r["download_path"]))
        has_ren = bool(r.get("rendered_path") and os.path.exists(r["rendered_path"]))
        vid_id = r.get("yt_video_id") or ""

        # Kiểm tra thêm part renders
        any_parts = False
        if vid_id:
            for d in [RENDERED_DIR, Path("data/test_renders")]:
                if d.exists() and list(d.glob(f"*{vid_id}*.mp4")):
                    any_parts = True
                    break

        if not has_raw and not has_ren and not any_parts:
            # File đã bị xóa hoàn toàn khỏi thư mục đĩa -> Xóa bản ghi
            cursor.execute("DELETE FROM videos WHERE id = ?", (r["id"],))
            cursor.execute("DELETE FROM upload_tasks WHERE video_id = ?", (r["id"],))
        else:
            if not has_raw and r.get("download_path"):
                cursor.execute("UPDATE videos SET download_path = NULL WHERE id = ?", (r["id"],))
            if not has_ren and r.get("rendered_path") and not any_parts:
                cursor.execute("UPDATE videos SET rendered_path = NULL WHERE id = ?", (r["id"],))

    conn.commit()

    # 2. Quét các file video mới được thêm/chép thủ công vào data/downloads
    known_paths = set()
    known_vid_ids = set()
    cursor.execute("SELECT id, yt_video_id, download_path, rendered_path FROM videos")
    for r in cursor.fetchall():
        if r["download_path"]:
            known_paths.add(os.path.abspath(r["download_path"]))
        if r["rendered_path"]:
            known_paths.add(os.path.abspath(r["rendered_path"]))
        if r["yt_video_id"]:
            known_vid_ids.add(r["yt_video_id"])

    # Quét DOWNLOADS_DIR (hỗ trợ thư mục con theo kênh và studio)
    if DOWNLOADS_DIR.exists():
        for ext in ["*.mp4", "*.mkv", "*.webm", "*.mov"]:
            for f in DOWNLOADS_DIR.rglob(ext):
                abs_f = os.path.abspath(str(f))
                if abs_f in known_paths:
                    continue

                fname = f.name
                vid_m = re.search(r'\[([a-zA-Z0-9_-]{11})\]', fname)
                if vid_m:
                    v_id = vid_m.group(1)
                else:
                    v_id = f"local_{hashlib.md5(fname.encode('utf-8', errors='ignore')).hexdigest()[:8]}"

                if v_id in known_vid_ids:
                    cursor.execute("UPDATE videos SET download_path = ? WHERE yt_video_id = ?", (str(f), v_id))
                    known_paths.add(abs_f)
                    continue

                clean_title = re.sub(r'\[[a-zA-Z0-9_-]{11}\]', '', fname)
                ch_m = re.match(r'^\[(.*?)\]_(.*)', clean_title)
                ch_name = ""
                if ch_m:
                    ch_name = ch_m.group(1).strip()
                    clean_title = ch_m.group(2).strip()
                clean_title = Path(clean_title).stem.strip() or fname

                duration = _probe_duration(f)

                cursor.execute("""
                    INSERT INTO videos (yt_video_id, title, duration, download_path, status, created_at)
                    VALUES (?, ?, ?, ?, 'downloaded', datetime('now', 'localtime'))
                """, (v_id, clean_title, duration, str(f)))
                known_paths.add(abs_f)
                known_vid_ids.add(v_id)

    # Quét RENDERED_DIR và data/test_renders (hỗ trợ thư mục con theo kênh)
    for d in [RENDERED_DIR, Path("data/test_renders")]:
        if d.exists():
            for f in d.rglob("*.mp4"):
                abs_f = os.path.abspath(str(f))
                fname = f.name
                vid_m = re.search(r'([a-zA-Z0-9_-]{11})', fname)
                if vid_m:
                    v_id = vid_m.group(1)
                    if v_id in known_vid_ids:
                        cursor.execute("SELECT rendered_path FROM videos WHERE yt_video_id = ?", (v_id,))
                        r_row = cursor.fetchone()
                        if not r_row or not r_row["rendered_path"] or not os.path.exists(r_row["rendered_path"]):
                            cursor.execute("UPDATE videos SET rendered_path = ?, status = 'rendered' WHERE yt_video_id = ?", (str(f), v_id))

    conn.commit()
    conn.close()

@app.post("/api/video/sync")
def sync_videos():
    """Đồng bộ ngay lập tức thư mục đĩa và cơ sở dữ liệu"""
    sync_local_videos_with_db()
    return {"status": "success", "message": "Đã đồng bộ thư viện video với thư mục đĩa"}

@app.get("/api/video/list")
def list_videos(sync: bool = True):
    if sync:
        sync_local_videos_with_db()

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT v.*, COALESCE(NULLIF(c.display_name, ''), NULLIF(c.title, ''), 'Dán trực tiếp') as channel_name, c.render_dir as ch_render_dir
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        ORDER BY v.id DESC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()

    from backend.config import RENDERED_DIR
    for r in rows:
        vid_id = r.get("yt_video_id") or ""
        # Quét toàn bộ các file Part đã render từ video này
        rendered_parts = []
        dirs_to_check = []
        if r.get("rendered_path") and os.path.exists(r["rendered_path"]):
            parent_dir = Path(r["rendered_path"]).parent
            if parent_dir not in dirs_to_check:
                dirs_to_check.append(parent_dir)
        if r.get("ch_render_dir") and os.path.exists(r["ch_render_dir"]):
            ch_dir = Path(r["ch_render_dir"])
            if ch_dir not in dirs_to_check:
                dirs_to_check.append(ch_dir)
        if RENDERED_DIR not in dirs_to_check and RENDERED_DIR.exists():
            dirs_to_check.append(RENDERED_DIR)

        found_files = set()
        for d in dirs_to_check:
            if vid_id and os.path.exists(d):
                for p in Path(d).rglob(f"*{vid_id}*.mp4"):
                    if str(p) not in found_files:
                        found_files.add(str(p))
                        part_m = re.search(r'Part(\d+)', p.name, re.IGNORECASE)
                        p_num = int(part_m.group(1)) if part_m else 1
                        rendered_parts.append({
                            "part": p_num,
                            "filename": p.name,
                            "path": str(p),
                            "url": f"/api/video/stream/{r['id']}?type=rendered&part={p_num}"
                        })

        # Deduplicate rendered parts by part number, keeping newest file
        part_map = {}
        for rp in rendered_parts:
            p_num = rp["part"]
            mtime = os.path.getmtime(rp["path"]) if os.path.exists(rp["path"]) else 0
            if p_num not in part_map or mtime > part_map[p_num]["mtime"]:
                part_map[p_num] = {"rp": rp, "mtime": mtime}
        rendered_parts = [v["rp"] for k, v in sorted(part_map.items())]
        r["rendered_parts"] = rendered_parts

        has_raw = bool(r.get("download_path") and os.path.exists(r["download_path"]))
        has_rendered = len(rendered_parts) > 0 or bool(r.get("rendered_path") and os.path.exists(r["rendered_path"]))

        r["has_raw"] = has_raw
        r["has_rendered"] = has_rendered
        r["raw_url"] = f"/api/video/stream/{r['id']}?type=original" if has_raw else ""
        r["media_url"] = rendered_parts[0]["url"] if rendered_parts else (r["raw_url"] if has_raw else "")

    return rows

@app.get("/api/video/stream/{video_id}")
def stream_video(video_id: int, type: str = "auto", part: int = 1):
    """Phát video trực tiếp: hỗ trợ chọn xem Video Gốc hoặc các Part đã Render 9:16"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.download_path, v.rendered_path, v.yt_video_id, c.render_dir as ch_render_dir
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.id = ?
    """, (video_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi video")

    from backend.config import RENDERED_DIR
    vid_id = row["yt_video_id"]
    file_path = None

    if type == "original":
        file_path = row["download_path"]
    elif type == "rendered":
        dirs_to_check = []
        if row["rendered_path"] and os.path.exists(row["rendered_path"]):
            dirs_to_check.append(Path(row["rendered_path"]).parent)
        if row["ch_render_dir"] and os.path.exists(row["ch_render_dir"]):
            dirs_to_check.append(Path(row["ch_render_dir"]))
        if RENDERED_DIR not in dirs_to_check and RENDERED_DIR.exists():
            dirs_to_check.append(RENDERED_DIR)

        for d in dirs_to_check:
            for p in d.rglob(f"*{vid_id}*Part{part}*.mp4"):
                file_path = str(p)
                break
            if file_path:
                break
        if not file_path:
            file_path = row["rendered_path"]
    else:
        file_path = row["rendered_path"] if row["rendered_path"] and os.path.exists(row["rendered_path"]) else row["download_path"]

    if not file_path or not os.path.exists(file_path) or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File video vật lý không tồn tại trên ổ đĩa máy tính")

    return FileResponse(file_path, media_type="video/mp4")

class UpdateVideoRequest(BaseModel):
    title: Optional[str] = None

@app.put("/api/video/{video_id}")
def update_video(video_id: str, req: UpdateVideoRequest):
    """Cập nhật thông tin video (tiêu đề)"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos WHERE id = ? OR yt_video_id = ?", (video_id, video_id))
    v = cursor.fetchone()
    if not v:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi video")
    
    updates = []
    params = []
    if req.title is not None and req.title.strip():
        updates.append("title = ?")
        params.append(req.title.strip())

    if updates:
        params.append(v["id"])
        cursor.execute(f"UPDATE videos SET {', '.join(updates)} WHERE id = ?", tuple(params))
        conn.commit()
    conn.close()
    return {"status": "success", "message": "Đã cập nhật thông tin video thành công"}

@app.delete("/api/video/{video_id}")
def delete_video(video_id: str):
    """Xóa video khỏi hệ thống, dọn dẹp toàn bộ file tải về và render trên ổ đĩa"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM videos WHERE id = ? OR yt_video_id = ?", (video_id, video_id))
    v = cursor.fetchone()
    if not v:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy bản ghi video")

    v = dict(v)
    v_db_id = v["id"]
    yt_vid_id = v.get("yt_video_id") or ""
    v_title = v.get("title") or f"#{v_db_id}"

    # 1. Xóa file gốc (download_path)
    if v.get("download_path") and os.path.exists(v["download_path"]):
        try:
            os.remove(v["download_path"])
        except Exception as e:
            logger.warning(f"Lỗi xóa file gốc download_path: {e}")

    # 2. Xóa file render chính (rendered_path)
    if v.get("rendered_path") and os.path.exists(v["rendered_path"]):
        try:
            os.remove(v["rendered_path"])
        except Exception as e:
            logger.warning(f"Lỗi xóa file rendered_path: {e}")

    # 3. Quét và dọn sạch các file clip Part đã render liên quan
    if yt_vid_id:
        from backend.config import RENDERED_DIR, DOWNLOADS_DIR
        for search_dir in [RENDERED_DIR, DOWNLOADS_DIR, Path("data/test_renders")]:
            if search_dir.exists():
                try:
                    for part_f in search_dir.rglob(f"*{yt_vid_id}*"):
                        if part_f.is_file():
                            try:
                                part_f.unlink()
                            except Exception:
                                pass
                except Exception:
                    pass

    # 4. Xóa các lịch đăng bài trong upload_tasks
    cursor.execute("DELETE FROM upload_tasks WHERE video_id = ?", (v_db_id,))
    # 5. Xóa bản ghi trong bảng videos
    cursor.execute("DELETE FROM videos WHERE id = ?", (v_db_id,))
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã xóa video #{v_db_id} '{v_title}' và dọn dẹp toàn bộ file đĩa liên quan.")
    return {"status": "success", "message": f"Đã xóa vĩnh viễn video '{v_title}' thành công"}

# ==========================================
# --- Audio Studio (Kho Âm Thanh & BGM) ---
# ==========================================

@app.get("/api/audio/categories")
def get_audio_categories():
    """Lấy danh sách các thư mục chủ đề nhạc nền kèm thống kê"""
    categories = audio_manager.get_categories()
    return {"status": "success", "categories": categories}

@app.post("/api/audio/categories/create")
def create_audio_category(req: CreateCategoryRequest):
    """Tạo thư mục chủ đề nhạc mới"""
    cat_name = (req.name or "").strip()
    if not cat_name:
        raise HTTPException(status_code=400, detail="Tên thư mục không được để trống!")
    if not is_valid_folder_name(cat_name):
        raise HTTPException(status_code=400, detail="Tên thư mục không hợp lệ hoặc chứa ký tự đặc biệt!")
    try:
        cat = audio_manager.create_category(cat_name, req.display_name)
        log_event("INFO", f"Đã tạo thư mục nhạc nền mới: {cat['name']}")
        return {"status": "success", "category": cat}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/audio/categories/rename")
def rename_audio_category(req: RenameCategoryRequest):
    """Đổi tên thư mục chủ đề nhạc"""
    if not req.old_id or not req.old_id.strip():
        raise HTTPException(status_code=400, detail="Mã thư mục cũ không được để trống!")
    new_name = (req.new_name or "").strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="Tên thư mục mới không được để trống!")
    if not is_valid_folder_name(new_name):
        raise HTTPException(status_code=400, detail="Tên thư mục mới không hợp lệ hoặc chứa ký tự đặc biệt!")
    try:
        cat = audio_manager.rename_category(req.old_id, new_name, req.display_name)
        log_event("INFO", f"Đã đổi tên thư mục nhạc nền: {req.old_id} -> {cat['name']}")
        return {"status": "success", "category": cat}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/api/audio/categories/{category_id}")
def delete_audio_category(category_id: str):
    """Xóa thư mục chủ đề nhạc nền"""
    try:
        ok = audio_manager.delete_category(category_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Không tìm thấy thư mục để xóa")
        log_event("INFO", f"Đã xóa thư mục nhạc nền: {category_id}")
        return {"status": "success", "category_id": category_id}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/api/audio/settings")
def get_audio_settings():
    """Lấy cài đặt cấu hình Thư viện Audio"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings WHERE key LIKE 'audio_%'")
    s = dict(cursor.fetchall())
    conn.close()
    return {
        "status": "success",
        "music_dir": s.get("audio_music_dir", str(audio_manager.music_dir)),
        "max_size_mb": int(s.get("audio_max_size_mb", 50)),
        "default_bitrate": s.get("audio_default_bitrate", "192k"),
        "max_search_results": int(s.get("audio_max_search_results", 50)),
        "normalize_audio": s.get("audio_normalize_audio", "1") == "1"
    }

@app.post("/api/audio/settings")
def save_audio_settings(req: AudioSettingsRequest):
    """Lưu cài đặt cấu hình Thư viện Audio"""
    if req.max_size_mb is not None and (req.max_size_mb < 1 or req.max_size_mb > 500):
        raise HTTPException(status_code=400, detail="Kích thước tối đa file nhạc phải từ 1 đến 500 MB!")
    if req.max_search_results is not None and (req.max_search_results < 1 or req.max_search_results > 100):
        raise HTTPException(status_code=400, detail="Số bài hát tìm kiếm tối đa phải từ 1 đến 100 bài!")

    conn = get_connection()
    cursor = conn.cursor()
    if req.music_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_music_dir', ?)", (req.music_dir.strip(),))
        p = Path(req.music_dir.strip())
        p.mkdir(parents=True, exist_ok=True)
        audio_manager.music_dir = p
    if req.max_size_mb is not None:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_max_size_mb', ?)", (str(req.max_size_mb),))
    if req.default_bitrate:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_default_bitrate', ?)", (req.default_bitrate,))
    if req.max_search_results is not None:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_max_search_results', ?)", (str(req.max_search_results),))
    if req.normalize_audio is not None:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('audio_normalize_audio', ?)", ("1" if req.normalize_audio else "0",))
    conn.commit()
    conn.close()
    log_event("INFO", "Đã cập nhật cài đặt Thư viện Audio")
    return {"status": "success", "message": "Đã lưu cài đặt Audio thành công!"}

@app.get("/api/audio/tracks")
def get_audio_tracks(category: str = "general"):
    """Lấy danh sách các bài hát trong thư mục chủ đề"""
    tracks = audio_manager.get_tracks_in_category(category)
    return {"status": "success", "category": category, "count": len(tracks), "tracks": tracks}

@app.post("/api/audio/search-youtube")
def search_youtube_audio_tracks(req: SearchAudioRequest):
    """Tìm kiếm nhạc YouTube No-Copyright theo từ khóa với giới hạn 20, 50, 100, 200 bài"""
    kw = (req.keyword or "").strip()
    if not kw:
        raise HTTPException(status_code=400, detail="Vui lòng nhập từ khóa tìm kiếm nhạc YouTube!")
    if req.max_results is not None and (req.max_results < 1 or req.max_results > 100):
        raise HTTPException(status_code=400, detail="Số lượng kết quả tìm kiếm phải từ 1 đến 100!")
    tracks = audio_manager.search_youtube_audio(kw, req.max_results)
    return {
        "status": "success",
        "keyword": kw,
        "max_results": req.max_results,
        "count": len(tracks),
        "tracks": tracks
    }

@app.get("/api/audio/yt-stream-url")
def get_youtube_stream_url(url: str):
    """Lấy direct streaming audio URL hoặc metadata preview cho video YouTube"""
    if not url:
        raise HTTPException(status_code=400, detail="Thiếu tham số url")

    vid_match = re.search(r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})', url)
    video_id = vid_match.group(1) if vid_match else url.strip()

    data = audio_manager.get_youtube_stream_url(url)
    if not data:
        return {
            "status": "fallback",
            "video_id": video_id,
            "embed_url": f"https://www.youtube-nocookie.com/embed/{video_id}?autoplay=1",
            "stream_url": None
        }

    return {
        "status": "success",
        "video_id": data.get("id") or video_id,
        "title": data.get("title"),
        "duration": data.get("duration"),
        "stream_url": data.get("stream_url"),
        "embed_url": f"https://www.youtube-nocookie.com/embed/{data.get('id') or video_id}?autoplay=1"
    }

@app.post("/api/audio/download-yt")
def download_youtube_audio_track(req: DownloadYtAudioRequest):
    """Tải bài hát từ YouTube No-Copyright vào thư mục chủ đề"""
    clean_url = (req.url or "").strip()
    if not clean_url:
        raise HTTPException(status_code=400, detail="Vui lòng nhập link hoặc Video ID YouTube!")
    if not is_safe_external_url(clean_url) and not re.match(r"^[a-zA-Z0-9_-]{11}$", clean_url):
        raise HTTPException(status_code=400, detail="URL hoặc Video ID không hợp lệ!")
    try:
        res = audio_manager.download_youtube_track(clean_url, req.category)
        log_event("INFO", f"Đã tải bài hát từ YouTube: {res.get('title')} -> [{req.category}]")
        return res
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/audio/upload")
async def upload_audio_files(
    category: str = Form("general"),
    files: List[UploadFile] = File(...)
):
    """Upload một hoặc nhiều file nhạc từ máy tính vào thư mục chủ đề"""
    safe_cat = os.path.basename(category) or "general"
    target_dir = MUSIC_DIR / safe_cat
    target_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    errors = []

    for file in files:
        original_name = file.filename or "track.mp3"
        ext = os.path.splitext(original_name)[1].lower()
        if ext not in ALLOWED_AUDIO_EXTENSIONS:
            errors.append(f"{original_name}: Định dạng '{ext}' không được hỗ trợ")
            continue

        safe_name = sanitize_audio_filename(original_name)
        target_path = target_dir / safe_name

        try:
            contents = await file.read()
            with open(target_path, "wb") as f_out:
                f_out.write(contents)
            saved_files.append(safe_name)
        except Exception as e:
            errors.append(f"{original_name}: Lỗi khi lưu file ({str(e)})")

    log_event("INFO", f"Đã upload {len(saved_files)} bài hát vào thư mục âm thanh '{safe_cat}'")
    return {
        "status": "success" if saved_files else "error",
        "category": safe_cat,
        "uploaded_count": len(saved_files),
        "files": saved_files,
        "errors": errors
    }

@app.get("/api/audio/stream/{category}/{filename}")
def stream_audio_file(category: str, filename: str):
    """Stream file audio để nghe thử trực tiếp trên trình duyệt"""
    safe_cat = os.path.basename(category)
    safe_file = os.path.basename(filename)
    file_path = MUSIC_DIR / safe_cat / safe_file

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File âm thanh không tồn tại")

    ext = file_path.suffix.lower()
    media_types = {
        ".mp3": "audio/mpeg",
        ".wav": "audio/wav",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".ogg": "audio/ogg",
        ".flac": "audio/flac"
    }
    media_type = media_types.get(ext, "audio/mpeg")
    return FileResponse(str(file_path), media_type=media_type)

@app.delete("/api/audio/tracks")
def delete_audio_track(req: DeleteAudioRequest):
    """Xóa file nhạc khỏi thư mục"""
    ok = audio_manager.delete_track(req.category, req.filename)
    if not ok:
        raise HTTPException(status_code=404, detail="Không tìm thấy file nhạc để xóa")
    return {"status": "success", "message": f"Đã xóa bài hát '{req.filename}'"}

@app.post("/api/video/render")
def render_video_ai(req: RenderVideoRequest):
    if not req.video_id or not req.video_id.strip():
        raise HTTPException(status_code=400, detail="Vui lòng chọn video hợp lệ để render!")
    if req.duration is not None and (req.duration < 10 or req.duration > 3600):
        raise HTTPException(status_code=400, detail="Thời lượng render phải từ 10 đến 3600 giây!")
    if req.clips_count is not None and (req.clips_count < 1 or req.clips_count > 20):
        raise HTTPException(status_code=400, detail="Số clip cắt phải từ 1 đến 20!")
    if req.bgm_volume is not None and (req.bgm_volume < 0.0 or req.bgm_volume > 1.0):
        raise HTTPException(status_code=400, detail="Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0!")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.download_path, v.title, v.duration, c.display_name, c.title as ch_title, c.render_dir as ch_render_dir
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.yt_video_id = ?
    """, (req.video_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row["download_path"] or not os.path.exists(row["download_path"]):
        raise HTTPException(status_code=404, detail="Không tìm thấy file video gốc đã tải")

    ch_name = row["display_name"] or row["ch_title"] or ""

    # Nếu yêu cầu cắt nhiều clip từ video gốc (clips_count > 1)
    if req.clips_count and req.clips_count > 1:
        parts = ai_video_engine.auto_slice_and_render_parts(
            input_file=row["download_path"],
            video_id=req.video_id,
            total_duration=int(row["duration"] or 120),
            part_duration=req.duration,
            channel_name=ch_name,
            video_title=row["title"],
            output_dir=row["ch_render_dir"] or None,
            max_clips=req.clips_count,
            add_part_label=req.add_part_label if req.add_part_label is not None else True,
            enable_subtitles=req.enable_subtitles,
            flip_horizontal=req.flip_horizontal,
            speed_factor=req.speed_factor,
            subtitle_style=req.subtitle_style,
            subtitle_position=req.subtitle_position,
            bgm_folder=req.bgm_folder,
            bgm_volume=req.bgm_volume
        )
        if not parts:
            raise HTTPException(status_code=500, detail="Lỗi khi render các part video AI")

        copy_data = ai_video_engine.generate_ai_hook_and_copy(row["title"])
        return {
            "status": "success",
            "rendered_file": parts[0],
            "rendered_files": parts,
            "parts_count": len(parts),
            "ai_copy": copy_data
        }

    rendered = ai_video_engine.process_transformative_video(
        input_file=row["download_path"],
        video_id=req.video_id,
        part_number=req.part_number,
        duration=req.duration,
        flip_horizontal=req.flip_horizontal,
        speed_factor=req.speed_factor,
        channel_name=ch_name,
        video_title=row["title"],
        output_dir=row["ch_render_dir"] or None,
        enable_subtitles=req.enable_subtitles,
        add_part_label=req.add_part_label if req.add_part_label is not None else True,
        subtitle_style=req.subtitle_style,
        subtitle_position=req.subtitle_position,
        bgm_folder=req.bgm_folder,
        bgm_volume=req.bgm_volume
    )

    if not rendered:
        raise HTTPException(status_code=500, detail="Lỗi khi render video AI")

    copy_data = ai_video_engine.generate_ai_hook_and_copy(row["title"])

    return {
        "status": "success",
        "rendered_file": rendered,
        "rendered_files": [rendered],
        "parts_count": 1,
        "ai_copy": copy_data
    }

@app.post("/api/video/render-smart-ai")
def render_smart_ai_video(req: SmartRenderVideoRequest):
    """
    Quy trình phân tích và render AI thông minh trọn gói:
    1. faster-whisper trích xuất transcript & word-level timestamps
    2. DeepSeek/Gemini/OpenAI chọn phân đoạn viral 60-90s và viết Hook/Tiêu đề
    3. Tự động tạo phụ đề động Karaoke dạng .ass
    4. Render lách bản quyền với bộ lọc Anti-Detection chuyên nghiệp
    """
    if not req.video_id or not req.video_id.strip():
        raise HTTPException(status_code=400, detail="Vui lòng chọn video hợp lệ để render!")
    if req.target_duration is not None and (req.target_duration < 10 or req.target_duration > 3600):
        raise HTTPException(status_code=400, detail="Thời lượng render phải từ 10 đến 3600 giây!")
    if req.clips_count is not None and (req.clips_count < 1 or req.clips_count > 20):
        raise HTTPException(status_code=400, detail="Số clip cắt phải từ 1 đến 20!")
    if req.bgm_volume is not None and (req.bgm_volume < 0.0 or req.bgm_volume > 1.0):
        raise HTTPException(status_code=400, detail="Âm lượng nhạc nền BGM phải từ 0.0 đến 1.0!")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT v.download_path, v.title, v.duration, c.display_name, c.title as ch_title, c.render_dir as ch_render_dir
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        WHERE v.yt_video_id = ?
    """, (req.video_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row["download_path"] or not os.path.exists(row["download_path"]):
        raise HTTPException(status_code=404, detail="Không tìm thấy file video gốc đã tải")

    ch_name = row["display_name"] or row["ch_title"] or ""
    result = ai_video_engine.process_smart_ai_video(
        input_file=row["download_path"],
        video_id=req.video_id,
        video_title=row["title"] or "",
        channel_name=ch_name,
        output_dir=row["ch_render_dir"] or None,
        custom_provider=req.ai_provider,
        custom_model=req.ai_model,
        enable_subtitles=req.enable_subtitles,
        target_duration=req.target_duration,
        flip_horizontal=req.flip_horizontal,
        speed_factor=req.speed_factor,
        add_part_label=req.add_part_label,
        generate_hook=req.generate_hook,
        clips_count=req.clips_count or 1,
        subtitle_style=req.subtitle_style,
        subtitle_position=req.subtitle_position,
        bgm_folder=req.bgm_folder,
        bgm_volume=req.bgm_volume
    )

    if result.get("status") != "success":
        raise HTTPException(status_code=500, detail="Lỗi trong quá trình AI phân tích và render video")

    return result


# --- TikTok Upload API ---
@app.post("/api/tiktok/upload")
def upload_tiktok(req: UploadVideoRequest):
    if not req.gpm_profile_id or not req.gpm_profile_id.strip():
        raise HTTPException(status_code=400, detail="Vui lòng chọn Profile GPMLogin để upload!")
    if not req.video_path or not req.video_path.strip():
        raise HTTPException(status_code=400, detail="Đường dẫn file video không được để trống!")
    if not os.path.exists(req.video_path):
        raise HTTPException(status_code=400, detail=f"Không tìm thấy file video tại: {req.video_path}")
    if not req.title or not req.title.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập tiêu đề cho video TikTok!")

    result = tiktok_uploader.upload_via_gpm(
        gpm_profile_id=req.gpm_profile_id,
        video_path=req.video_path,
        title=req.title,
        tags=req.tags,
        auto_post=True
    )
    return result

# --- Profile Stats & 10k Alert API ---
@app.post("/api/profiles/stats")
def update_profile_stats(req: UpdateProfileStatsRequest):
    if not req.gpm_id or not req.gpm_id.strip():
        raise HTTPException(status_code=400, detail="Mã profile GPM không được để trống!")
    if req.followers is not None and req.followers < 0:
        raise HTTPException(status_code=400, detail="Số lượng Follower không được là số âm!")
    if req.views is not None and req.views < 0:
        raise HTTPException(status_code=400, detail="Số lượt xem không được là số âm!")

    result = metrics_tracker.update_profile_stats(
        gpm_id=req.gpm_id,
        followers=req.followers,
        total_views=req.views,
        username=req.username or ""
    )
    return result

@app.post("/api/profiles/{gpm_id}/scan")
def scan_profile_now(gpm_id: str):
    res = tiktok_tracker.scan_single_gpm_profile(gpm_id, auto_close=True)
    return res

@app.post("/api/profiles/scan-all")
def scan_all_profiles_now(bg_tasks: BackgroundTasks):
    if tiktok_tracker.get_scan_progress().get("is_scanning", False):
        return {"status": "warning", "message": "Tiến trình quét toàn bộ profile đang chạy..."}
    bg_tasks.add_task(tiktok_tracker.scan_all_profiles)
    return {"status": "success", "message": "Đã bắt đầu tiến trình quét Follower toàn bộ nick GPM ngầm."}

@app.post("/api/profiles/scan-stop")
def stop_all_profiles_scan():
    res = tiktok_tracker.stop_scan()
    return res

@app.get("/api/profiles/scan-progress")
def get_profiles_scan_progress():
    return tiktok_tracker.get_scan_progress()

@app.get("/api/profiles/session-status")
def get_profiles_session_status():
    """
    Trả về trạng thái session cookie của từng GPM profile trên ổ đĩa máy cục bộ.
    ZeroRAM: đọc trực tiếp từ thư mục profile GPMLogin (ExportCookies.json).
    """
    from backend.modules.gpm_profile_reader import list_gpm_profiles_status, is_gpm_reader_available, get_gpm_storage_path
    status = list_gpm_profiles_status()
    profiles = status.get("profiles", [])
    session_map = {
        p["profile_id"]: {
            "gpm_id": p["profile_id"],
            "has_session_file": p["has_cookie_file"],
            "has_auth_cookie": p["has_sessionid"],
            "is_valid": p["has_sessionid"],
            "last_updated": p.get("last_updated")
        } 
        for p in profiles
    }
    return {
        "session_reader_available": is_gpm_reader_available(),
        "storage_path": get_gpm_storage_path(),
        "total_sessions": status.get("total_profiles", 0),
        "valid_sessions": status.get("logged_in_count", 0),
        "profiles": profiles,
        "session_map": session_map,
    }

@app.put("/api/profiles/{gpm_id}/username")
def update_profile_username(gpm_id: str, req: UpdateProfileUsernameRequest):
    if not req.username or not req.username.strip():
        raise HTTPException(status_code=400, detail="Username TikTok không được để trống!")
    cleaned_u = req.username.strip().replace("@", "")
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE gpm_profiles SET tiktok_username = ? WHERE gpm_id = ?", (cleaned_u, gpm_id))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã gán TikTok username @{cleaned_u} cho GPM profile {gpm_id}")
    return {"status": "success", "gpm_id": gpm_id, "username": cleaned_u}

@app.put("/api/profiles/{gpm_id}/notify-status")
@app.post("/api/profiles/{gpm_id}/notify-status")
def update_profile_notify_status(gpm_id: str, req: UpdateProfileNotifyStatusRequest):
    valid_statuses = {"tracking", "sent", "muted"}
    status = (req.status or "").strip().lower()
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Trạng thái không hợp lệ (phải là tracking, sent, hoặc muted)")
    
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy profile GPMLogin")
    
    profile_name = row["name"]
    cursor.execute("UPDATE gpm_profiles SET notify_status = ? WHERE gpm_id = ?", (status, gpm_id))
    conn.commit()
    conn.close()

    status_labels = {
        "tracking": "Đang theo dõi",
        "sent": "Đã gửi thông báo",
        "muted": "Bỏ theo dõi"
    }
    label = status_labels.get(status, status)
    log_event("INFO", f"Đã cập nhật trạng thái theo dõi 10K cho profile '{profile_name}' thành: {label}")
    return {"status": "success", "gpm_id": gpm_id, "notify_status": status, "label": label}

@app.get("/api/settings/follower-scheduler")
def get_follower_scheduler_settings():
    return {
        "enabled": scheduler.follower_scan_enabled,
        "mode": scheduler.follower_scan_mode,
        "times": scheduler.follower_scan_times,
        "interval_hours": scheduler.follower_scan_interval_hours,
        "last_scan": getattr(scheduler, "last_follower_scan", 0),
        "is_scanning": getattr(tiktok_tracker, "_is_scanning_all", False)
    }

@app.post("/api/settings/follower-scheduler")
def save_follower_scheduler_settings(req: FollowerSchedulerRequest):
    if req.interval_hours is not None and (req.interval_hours < 1 or req.interval_hours > 48):
        raise HTTPException(status_code=400, detail="Khoảng cách giữa các lần quét phải từ 1 đến 48 giờ!")
    if req.mode == "times" and req.times:
        for t in req.times.split(","):
            t = t.strip()
            if t and not is_valid_hhmm(t):
                raise HTTPException(status_code=400, detail=f"Khung giờ '{t}' không đúng định dạng HH:MM (00:00 - 23:59)!")

    scheduler.update_follower_config(
        enabled=req.enabled,
        mode=req.mode,
        times=req.times,
        interval_hours=req.interval_hours
    )
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('follower_scan_enabled', ?)", ("1" if req.enabled else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('follower_scan_mode', ?)", (req.mode,))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('follower_scan_times', ?)", (req.times or "08:00, 20:00",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('follower_scan_interval_hours', ?)", (str(req.interval_hours or 6),))
        conn.commit()
        conn.close()
    except Exception as e:
        log_event("WARNING", f"Lỗi lưu cấu hình scheduler vào settings: {e}")

    log_event("INFO", f"Đã lưu cấu hình quét Follower tự động: Bật={req.enabled}, Chế độ={req.mode}, Giờ={req.times}, Khoảng cách={req.interval_hours}h")
    return {"status": "success", "message": "Đã lưu cài đặt quét Follower tự động thành công"}

# --- System Tray & Auto-Start Settings ---
@app.get("/api/settings/system-tray")
def get_system_tray_settings():
    from backend.modules.tray_manager import is_autostart_enabled, is_minimize_to_tray_enabled
    return {
        "status": "success",
        "autostart": is_autostart_enabled(),
        "minimize_to_tray": is_minimize_to_tray_enabled()
    }

@app.post("/api/settings/system-tray")
def save_system_tray_settings(req: SystemTraySettingsRequest):
    from backend.modules.tray_manager import (
        set_autostart, 
        set_minimize_to_tray, 
        is_autostart_enabled, 
        is_minimize_to_tray_enabled
    )
    if req.autostart is not None:
        set_autostart(req.autostart)
    if req.minimize_to_tray is not None:
        set_minimize_to_tray(req.minimize_to_tray)
    return {
        "status": "success",
        "autostart": is_autostart_enabled(),
        "minimize_to_tray": is_minimize_to_tray_enabled(),
        "message": "Đã lưu cài đặt Khay Hệ Thống & Khởi Động thành công!"
    }

# --- Telegram Alert Channels Management ---
@app.get("/api/telegram/channels")
def get_telegram_channels():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, chat_id, is_active, notify_10k, notify_issues, notify_daily_report, daily_report_time, last_daily_report, created_at "
        "FROM telegram_channels ORDER BY id ASC"
    )
    rows = cursor.fetchall()
    conn.close()
    channels = [dict(r) for r in rows]
    return {
        "status": "success",
        "channels": channels,
        "total": len(channels),
        "active_count": sum(1 for c in channels if c.get("is_active"))
    }

@app.post("/api/telegram/channels")
def create_telegram_channel(req: TelegramChannelCreateRequest):
    name = (req.name or "").strip()
    chat_id = (req.chat_id or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tên kênh không được để trống")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Chat ID không được để trống")

    conn = get_connection()
    cursor = conn.cursor()
    is_active_int = 1 if req.is_active else 0
    notify_10k_int = 1 if req.notify_10k else 0
    notify_issues_int = 1 if req.notify_issues else 0
    notify_daily_int = 1 if req.notify_daily_report else 0
    daily_time = (req.daily_report_time or "21:00").strip()
    if daily_time and not is_valid_hhmm(daily_time):
        raise HTTPException(status_code=400, detail="Khung giờ báo cáo phải có định dạng HH:MM (00:00 - 23:59)!")
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    cursor.execute(
        "INSERT INTO telegram_channels (name, chat_id, is_active, notify_10k, notify_issues, notify_daily_report, daily_report_time, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, chat_id, is_active_int, notify_10k_int, notify_issues_int, notify_daily_int, daily_time, now_str)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã thêm kênh Telegram mới: {name} ({chat_id})")
    return {
        "status": "success",
        "message": f"Đã thêm kênh Telegram '{name}' thành công",
        "channel": {
            "id": new_id,
            "name": name,
            "chat_id": chat_id,
            "is_active": is_active_int,
            "notify_10k": notify_10k_int,
            "notify_issues": notify_issues_int,
            "notify_daily_report": notify_daily_int,
            "daily_report_time": daily_time,
            "created_at": now_str
        }
    }

@app.put("/api/telegram/channels/{channel_id}")
def update_telegram_channel(channel_id: int, req: TelegramChannelUpdateRequest):
    name = (req.name or "").strip()
    chat_id = (req.chat_id or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Tên kênh không được để trống")
    if not chat_id:
        raise HTTPException(status_code=400, detail="Chat ID không được để trống")

    daily_time = (req.daily_report_time or "21:00").strip()
    if daily_time and not is_valid_hhmm(daily_time):
        raise HTTPException(status_code=400, detail="Khung giờ báo cáo phải có định dạng HH:MM (00:00 - 23:59)!")

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM telegram_channels WHERE id = ?", (channel_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh Telegram")

    is_active_int = 1 if req.is_active else 0
    notify_10k_int = 1 if req.notify_10k else 0
    notify_issues_int = 1 if req.notify_issues else 0
    notify_daily_int = 1 if req.notify_daily_report else 0

    cursor.execute(
        "UPDATE telegram_channels SET name = ?, chat_id = ?, is_active = ?, notify_10k = ?, notify_issues = ?, notify_daily_report = ?, daily_report_time = ? WHERE id = ?",
        (name, chat_id, is_active_int, notify_10k_int, notify_issues_int, notify_daily_int, daily_time, channel_id)
    )
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã cập nhật kênh Telegram #{channel_id}: {name} ({chat_id}) - Bật: {bool(is_active_int)}")
    return {
        "status": "success",
        "message": f"Đã cập nhật kênh '{name}' thành công",
        "channel": {
            "id": channel_id,
            "name": name,
            "chat_id": chat_id,
            "is_active": is_active_int,
            "notify_10k": notify_10k_int,
            "notify_issues": notify_issues_int,
            "notify_daily_report": notify_daily_int,
            "daily_report_time": daily_time
        }
    }

@app.patch("/api/telegram/channels/{channel_id}/toggle")
def toggle_telegram_channel(channel_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, is_active FROM telegram_channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh Telegram")

    new_active = 0 if row["is_active"] else 1
    cursor.execute("UPDATE telegram_channels SET is_active = ? WHERE id = ?", (new_active, channel_id))
    conn.commit()
    conn.close()

    action_str = "BẬT" if new_active == 1 else "TẮT"
    log_event("INFO", f"Đã {action_str} nhận thông báo cho kênh Telegram: {row['name']} (#{channel_id})")
    return {
        "status": "success",
        "id": channel_id,
        "is_active": new_active,
        "message": f"Đã {action_str} kênh '{row['name']}'"
    }

@app.delete("/api/telegram/channels/{channel_id}")
def delete_telegram_channel(channel_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM telegram_channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh Telegram")

    ch_name = row["name"]
    cursor.execute("DELETE FROM telegram_channels WHERE id = ?", (channel_id,))
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã xóa kênh Telegram: {ch_name} (#{channel_id})")
    return {
        "status": "success",
        "message": f"Đã xóa kênh Telegram '{ch_name}'"
    }

@app.post("/api/telegram/channels/{channel_id}/test")
def test_specific_telegram_channel(channel_id: int, mode: Optional[str] = "connection"):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, chat_id, notify_10k, notify_issues, notify_daily_report, daily_report_time FROM telegram_channels WHERE id = ?", (channel_id,))
    row = cursor.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Không tìm thấy kênh Telegram")

    bot_token = notifier.get_bot_token()
    if not bot_token:
        return {"status": "failed", "message": "Chưa cấu hình Telegram Bot Token"}

    now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
    
    # 1. Test 10k Alert
    if mode == "10k":
        result = notifier.send_10k_alert_detailed(
            profile_name="Profile Demo #01",
            username="tiktok_creator_us",
            followers=10520,
            views=120000,
            target_chat_id=row["chat_id"]
        )
        return {
            "status": "success" if result.get("success") else "failed",
            "message": result.get("message")
        }
    
    # 2. Test Issue Alert
    elif mode == "issue":
        result = notifier.send_issue_alert_detailed(
            title="Lỗi Kết Nối GPMLogin & Proxy (Demo)",
            message="Không thể mở profile GPM ID 'abcdef123': Proxy SOCKS5 timed out sau 15 giây.",
            solution="1. Mở phần mềm GPMLogin trên máy.\n2. Kiểm tra proxy của profile (nhấn Check Proxy).\n3. Đổi proxy mới nếu proxy cũ đã hết hạn.",
            severity="HIGH",
            details="Profile: Profile Demo #01 | Proxy: 123.45.67.89:1080",
            target_chat_id=row["chat_id"]
        )
        return {
            "status": "success" if result.get("success") else "failed",
            "message": result.get("message")
        }
    
    # 3. Test Daily Report
    elif mode == "daily_report":
        result = notifier.send_daily_report(target_chat_id=row["chat_id"])
        return {
            "status": "success" if result.get("success") else "failed",
            "message": result.get("message")
        }

    # 4. Mặc định: Test kết nối chung
    types_active = []
    if row["notify_10k"]: types_active.append("🌟 Cảnh báo 10K Follower")
    if row["notify_issues"]: types_active.append("⚠️ Cảnh báo sự cố & cách khắc phục")
    if row["notify_daily_report"]: types_active.append(f"📊 Báo cáo hàng ngày ({row['daily_report_time'] or '21:00'})")
    types_str = "\n".join([f"• {t}" for t in types_active]) if types_active else "• (Chưa bật loại thông báo nào)"

    msg = (
        "🔔 *[TIKTOK FARM] KIỂM TRA KẾT NỐI KÊNH THÀNH CÔNG!*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"📢 *Tên Kênh:* `{row['name']}`\n"
        f"🆔 *Chat ID:* `{row['chat_id']}`\n"
        f"⏰ *Thời gian:* `{now_str}`\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📋 *Loại thông báo đang đăng ký nhận:*\n"
        f"{types_str}\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ Kênh này đã sẵn sàng hoạt động cùng TikTok Farm Auto-Pilot!"
    )
    ok, err_msg = notifier.send_message_to_chat(bot_token, row["chat_id"], msg)
    if ok:
        log_event("INFO", f"Đã gửi test alert thành công tới kênh Telegram '{row['name']}' ({row['chat_id']})")
        return {"status": "success", "message": f"Đã gửi tin nhắn thử nghiệm thành công tới '{row['name']}'"}
    else:
        log_event("ERROR", f"Gửi test alert thất bại tới kênh '{row['name']}': {err_msg}")
        return {"status": "failed", "message": f"Lỗi gửi tin nhắn: {err_msg}"}

@app.post("/api/telegram/test-alert")
def test_telegram_alert():
    result = notifier.send_10k_alert_detailed(
        profile_name="Profile Demo #01",
        username="mmo_creator_us",
        followers=10450,
        views=250000
    )
    return {
        "status": "success" if result.get("success") else "failed",
        "message": result.get("message", "Đã gửi test alert Telegram"),
        "sent_count": result.get("sent_count", 0),
        "total_active": result.get("total_active", 0),
        "channels": result.get("channels", [])
    }

@app.post("/api/telegram/test-issue-alert")
def test_telegram_issue_alert():
    """Gửi tin nhắn cảnh báo sự cố thử nghiệm kèm hướng dẫn khắc phục tới các kênh nhận notify_issues"""
    result = notifier.send_issue_alert_detailed(
        title="Lỗi Đăng Video TikTok (Thử Nghiệm)",
        message="Không thể click nút 'Đăng' do phiên đăng nhập trên GPMLogin hết hạn hoặc cần Captcha.",
        solution="1. Mở GPMLogin trên máy tính, vào Profile bị lỗi.\n2. Đăng nhập lại TikTok và lưu phiên.\n3. Nhấn 'Thử Lại' tác vụ trong tab Quản Lý Upload.",
        severity="HIGH",
        details="Tài khoản: @mmo_demo_us | Profile: US_Farm_01"
    )
    return {
        "status": "success" if result.get("success") else "failed",
        "message": result.get("message", "Đã gửi cảnh báo sự cố thử nghiệm"),
        "sent_count": result.get("sent_count", 0),
        "total_active": result.get("total_active", 0),
        "channels": result.get("channels", [])
    }

@app.post("/api/telegram/send-issue-alert")
def send_telegram_issue_alert(req: TelegramSendIssueRequest):
    """Gửi cảnh báo sự cố cụ thể tới các kênh hoặc kênh chỉ định"""
    target_chat = None
    if req.channel_id:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM telegram_channels WHERE id = ?", (req.channel_id,))
        row = cursor.fetchone()
        conn.close()
        if row:
            target_chat = row["chat_id"]

    ok = notifier.send_issue_alert(
        title=req.title,
        message=req.message,
        solution=req.solution or "",
        severity=req.severity or "ERROR",
        details=req.details or "",
        target_chat_id=target_chat,
        force=True
    )
    return {
        "status": "success" if ok else "failed",
        "message": "Đã gửi cảnh báo sự cố tới Telegram" if ok else "Gửi cảnh báo sự cố thất bại"
    }

@app.get("/api/telegram/daily-report-preview")
def preview_daily_report(date: Optional[str] = None):
    """Xem trước nội dung báo cáo hoạt động hàng ngày"""
    data = notifier.build_daily_report_data(report_date=date)
    text = notifier.format_daily_report_message(data)
    return {
        "status": "success",
        "report_date": data.get("report_date"),
        "preview_text": text,
        "summary": {
            "total_uploads": data.get("total_uploads"),
            "success_uploads": data.get("success_uploads"),
            "failed_uploads": data.get("failed_uploads"),
            "total_ai_cost_usd": data.get("total_ai_cost_usd"),
            "total_ai_cost_vnd": data.get("total_ai_cost_vnd")
        }
    }

@app.post("/api/telegram/send-daily-report")
def send_daily_report_now(req: Optional[TelegramSendReportRequest] = None):
    """Gửi ngay lập tức Báo cáo hoạt động ngày tới các kênh nhận notify_daily_report (hoặc kênh chỉ định)"""
    target_chat = None
    rep_date = None
    if req:
        rep_date = req.report_date
        if req.channel_id:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT chat_id FROM telegram_channels WHERE id = ?", (req.channel_id,))
            row = cursor.fetchone()
            conn.close()
            if row:
                target_chat = row["chat_id"]

    result = notifier.send_daily_report(report_date=rep_date, target_chat_id=target_chat)
    return {
        "status": "success" if result.get("success") else "failed",
        "message": result.get("message", "Đã gửi báo cáo ngày"),
        "sent_count": result.get("sent_count", 0),
        "total_active": result.get("total_active", 0),
        "channels": result.get("channels", [])
    }

# --- API Key Management & Settings Persistence ---
@app.get("/api/settings/keys")
def get_api_keys():
    import os
    import backend.config as cfg
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    db_settings = dict(cursor.fetchall())
    conn.close()

    raw = os.getenv("YOUTUBE_API_KEYS", os.getenv("YOUTUBE_API_KEY", db_settings.get("YOUTUBE_API_KEYS", "")))
    deepseek = os.getenv("DEEPSEEK_API_KEY", db_settings.get("DEEPSEEK_API_KEY", cfg.DEEPSEEK_API_KEY))
    gemini = os.getenv("GEMINI_API_KEY", db_settings.get("GEMINI_API_KEY", cfg.GEMINI_API_KEY))
    openai = os.getenv("OPENAI_API_KEY", db_settings.get("OPENAI_API_KEY", cfg.OPENAI_API_KEY))
    ai_provider = os.getenv("AI_PROVIDER", db_settings.get("AI_PROVIDER", cfg.AI_PROVIDER))
    deepseek_model = os.getenv("DEEPSEEK_MODEL", db_settings.get("DEEPSEEK_MODEL", cfg.DEEPSEEK_MODEL))
    gemini_model = os.getenv("GEMINI_MODEL", db_settings.get("GEMINI_MODEL", cfg.GEMINI_MODEL))
    openai_model = os.getenv("OPENAI_MODEL", db_settings.get("OPENAI_MODEL", cfg.OPENAI_MODEL))
    whisper_size = os.getenv("WHISPER_MODEL_SIZE", db_settings.get("WHISPER_MODEL_SIZE", cfg.WHISPER_MODEL_SIZE))
    enable_subs = os.getenv("ENABLE_DYNAMIC_SUBTITLES", db_settings.get("ENABLE_DYNAMIC_SUBTITLES", "true")).lower() in ("true", "1", "yes")
    enable_anti = os.getenv("ENABLE_ANTI_DETECT", db_settings.get("ENABLE_ANTI_DETECT", "true")).lower() in ("true", "1", "yes")
    tele_token = os.getenv("TELEGRAM_BOT_TOKEN", db_settings.get("TELEGRAM_BOT_TOKEN", cfg.TELEGRAM_BOT_TOKEN))
    tele_chat = os.getenv("TELEGRAM_CHAT_ID", db_settings.get("TELEGRAM_CHAT_ID", cfg.TELEGRAM_CHAT_ID))
    gpm_url = os.getenv("GPM_API_BASE_URL", db_settings.get("GPM_API_BASE_URL", cfg.GPM_API_BASE_URL))

    sub_style = os.getenv("SUBTITLE_STYLE", db_settings.get("SUBTITLE_STYLE", getattr(cfg, 'SUBTITLE_STYLE', 'karaoke_yellow')))
    sub_pos = os.getenv("SUBTITLE_POSITION", db_settings.get("SUBTITLE_POSITION", getattr(cfg, 'SUBTITLE_POSITION', 'center')))
    sub_size = int(os.getenv("SUBTITLE_FONT_SIZE", db_settings.get("SUBTITLE_FONT_SIZE", getattr(cfg, 'SUBTITLE_FONT_SIZE', 54))))

    pool_status = yt_scanner.key_pool.get_keys_status()
    return {
        "youtube_api_keys": raw,
        "youtube_key_pool": pool_status,
        "deepseek_api_key": deepseek,
        "gemini_api_key": gemini,
        "openai_api_key": openai,
        "ai_provider": ai_provider,
        "deepseek_model": deepseek_model,
        "gemini_model": gemini_model,
        "openai_model": openai_model,
        "whisper_model_size": whisper_size,
        "enable_dynamic_subtitles": enable_subs,
        "enable_anti_detect": enable_anti,
        "subtitle_style": sub_style,
        "subtitle_position": sub_pos,
        "subtitle_font_size": sub_size,
        "telegram_bot_token": tele_token,
        "telegram_chat_id": tele_chat,
        "gpm_api_base_url": gpm_url,
    }

@app.post("/api/settings/keys")
def save_api_keys(req: SaveApiKeysRequest):
    if req.subtitle_font_size is not None and (req.subtitle_font_size < 12 or req.subtitle_font_size > 120):
        raise HTTPException(status_code=400, detail="Cỡ chữ phụ đề phải từ 12 đến 120 pt!")
    if req.gpm_api_base_url is not None and req.gpm_api_base_url.strip():
        if not req.gpm_api_base_url.strip().lower().startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="Địa chỉ GPM API Base URL phải bắt đầu bằng http:// hoặc https://!")

    updates = {}
    if req.youtube_api_keys is not None:
        keys = [k.strip() for k in req.youtube_api_keys.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        raw = ",".join(keys)
        updates["YOUTUBE_API_KEY"] = raw
        updates["YOUTUBE_API_KEYS"] = raw
    if req.deepseek_api_key is not None:
        updates["DEEPSEEK_API_KEY"] = req.deepseek_api_key.strip()
    if req.gemini_api_key is not None:
        updates["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if req.openai_api_key is not None:
        updates["OPENAI_API_KEY"] = req.openai_api_key.strip()
    if req.ai_provider is not None:
        updates["AI_PROVIDER"] = req.ai_provider.strip()
    if req.deepseek_model is not None:
        updates["DEEPSEEK_MODEL"] = req.deepseek_model.strip()
    if req.gemini_model is not None:
        updates["GEMINI_MODEL"] = req.gemini_model.strip()
    if req.openai_model is not None:
        updates["OPENAI_MODEL"] = req.openai_model.strip()
    if req.whisper_model_size is not None:
        updates["WHISPER_MODEL_SIZE"] = req.whisper_model_size.strip()
    if req.enable_dynamic_subtitles is not None:
        updates["ENABLE_DYNAMIC_SUBTITLES"] = "true" if req.enable_dynamic_subtitles else "false"
    if req.enable_anti_detect is not None:
        updates["ENABLE_ANTI_DETECT"] = "true" if req.enable_anti_detect else "false"
    if req.subtitle_style is not None:
        updates["SUBTITLE_STYLE"] = req.subtitle_style.strip()
    if req.subtitle_position is not None:
        updates["SUBTITLE_POSITION"] = req.subtitle_position.strip()
    if req.subtitle_font_size is not None:
        updates["SUBTITLE_FONT_SIZE"] = str(req.subtitle_font_size)
    if req.telegram_bot_token is not None:
        updates["TELEGRAM_BOT_TOKEN"] = req.telegram_bot_token.strip()
    if req.telegram_chat_id is not None:
        updates["TELEGRAM_CHAT_ID"] = req.telegram_chat_id.strip()
    if req.gpm_api_base_url is not None and req.gpm_api_base_url.strip():
        updates["GPM_API_BASE_URL"] = req.gpm_api_base_url.strip()

    # 1. Save to .env file
    save_env_config(updates)

    # 2. Persist to SQLite settings table
    try:
        conn = get_connection()
        cursor = conn.cursor()
        for k, v in updates.items():
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (k, str(v)))
        conn.commit()
        conn.close()
    except Exception as e:
        log_event("WARNING", f"Lỗi lưu cấu hình vào DB: {e}")

    yt_scanner.reload_keys(updates.get("YOUTUBE_API_KEYS", ""))
    if "TELEGRAM_BOT_TOKEN" in updates:
        notifier.bot_token = updates["TELEGRAM_BOT_TOKEN"]
    log_event("INFO", f"Đã cập nhật cấu hình API keys và lưu vào DB: {list(updates.keys())}")
    return {"status": "ok", "message": "Đã lưu cấu hình thành công", "pool_size": yt_scanner.key_pool.total_keys}

class UpdateSchedulerSettingsRequest(BaseModel):
    interval_minutes: int = 15
    upload_interval_seconds: int = 60
    auto_download: bool = True
    auto_render: bool = True
    save_by_channel_folder: bool = False
    max_videos_per_scan: int = 5
    channel_delay_seconds: int = 2
    auto_retry_enabled: bool = True
    max_retries: int = 2
    retry_delay_minutes: int = 15
    watchdog_enabled: bool = True
    stuck_timeout_minutes: int = 15
    min_account_cooldown_minutes: Optional[int] = 60

@app.get("/api/settings/defaults")
def get_default_settings():
    """Retrieve saved folder defaults and general configurations from SQLite."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings_dict = dict(cursor.fetchall())
    conn.close()
    return {
        "download_dir": settings_dict.get("default_download_dir", "data/downloads"),
        "render_dir": settings_dict.get("default_render_dir", "data/rendered"),
        "scheduler_running": settings_dict.get("scheduler_running", "1") == "1",
        "scheduler_interval_minutes": int(settings_dict.get("scheduler_interval_minutes", getattr(scheduler, "rss_interval_minutes", 15))),
        "upload_interval_seconds": int(settings_dict.get("upload_interval_seconds", getattr(scheduler, "upload_interval_seconds", 60))),
        "auto_download": settings_dict.get("auto_download", "1") == "1",
        "auto_render": settings_dict.get("auto_render", "1") == "1",
        "save_by_channel_folder": settings_dict.get("save_by_channel_folder", "0") == "1",
        "max_videos_per_scan": int(settings_dict.get("max_videos_per_scan", getattr(scheduler, "max_videos_per_scan", 5))),
        "channel_delay_seconds": int(settings_dict.get("channel_delay_seconds", getattr(scheduler, "channel_delay_seconds", 2)))
    }

@app.get("/api/settings/scheduler")
def get_scheduler_settings():
    """Get current scheduler configuration."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    settings_dict = dict(cursor.fetchall())
    conn.close()
    return {
        "status": "success",
        "interval_minutes": int(settings_dict.get("scheduler_interval_minutes", getattr(scheduler, "rss_interval_minutes", 15))),
        "upload_interval_seconds": int(settings_dict.get("upload_interval_seconds", getattr(scheduler, "upload_interval_seconds", 60))),
        "auto_download": settings_dict.get("auto_download", "1") == "1",
        "auto_render": settings_dict.get("auto_render", "1") == "1",
        "save_by_channel_folder": settings_dict.get("save_by_channel_folder", "0") == "1",
        "max_videos_per_scan": int(settings_dict.get("max_videos_per_scan", getattr(scheduler, "max_videos_per_scan", 5))),
        "channel_delay_seconds": int(settings_dict.get("channel_delay_seconds", getattr(scheduler, "channel_delay_seconds", 2))),
        "auto_retry_enabled": settings_dict.get("upload_auto_retry", "1" if getattr(scheduler, "auto_retry_enabled", True) else "0") == "1",
        "max_retries": int(settings_dict.get("upload_max_retries", getattr(scheduler, "max_retries", 2))),
        "retry_delay_minutes": int(settings_dict.get("upload_retry_delay_minutes", getattr(scheduler, "retry_delay_minutes", 15))),
        "watchdog_enabled": settings_dict.get("watchdog_enabled", "1" if getattr(scheduler, "watchdog_enabled", True) else "0") == "1",
        "stuck_timeout_minutes": int(settings_dict.get("upload_stuck_timeout_minutes", getattr(scheduler, "stuck_timeout_minutes", 15))),
        "min_account_cooldown_minutes": int(settings_dict.get("min_account_cooldown_minutes", getattr(scheduler, "min_account_cooldown_minutes", 60))),
        "scheduler_running": scheduler.is_running
    }

@app.post("/api/settings/scheduler")
def update_scheduler_settings(req: UpdateSchedulerSettingsRequest):
    """Save and apply advanced scheduler settings."""
    if req.interval_minutes < 1 or req.interval_minutes > 1440:
        raise HTTPException(status_code=400, detail="Chu kỳ quét RSS phải từ 1 đến 1440 phút!")
    if req.upload_interval_seconds < 10 or req.upload_interval_seconds > 86400:
        raise HTTPException(status_code=400, detail="Khoảng cách giữa các lần kiểm tra Upload phải từ 10 đến 86400 giây!")
    if req.max_videos_per_scan < 1 or req.max_videos_per_scan > 50:
        raise HTTPException(status_code=400, detail="Số video tối đa mỗi lần quét phải từ 1 đến 50!")
    if req.channel_delay_seconds < 0 or req.channel_delay_seconds > 3600:
        raise HTTPException(status_code=400, detail="Độ trễ giữa các kênh phải từ 0 đến 3600 giây!")
    if req.max_retries < 1 or req.max_retries > 10:
        raise HTTPException(status_code=400, detail="Số lần thử lại tối đa phải từ 1 đến 10!")
    if req.retry_delay_minutes < 1 or req.retry_delay_minutes > 1440:
        raise HTTPException(status_code=400, detail="Độ trễ giữa các lần thử lại phải từ 1 đến 1440 phút!")
    if req.stuck_timeout_minutes < 5 or req.stuck_timeout_minutes > 180:
        raise HTTPException(status_code=400, detail="Thời gian timeout chống treo phải từ 5 đến 180 phút!")
    if req.min_account_cooldown_minutes is not None and (req.min_account_cooldown_minutes < 15 or req.min_account_cooldown_minutes > 1440):
        raise HTTPException(status_code=400, detail="Giãn cách tối thiểu giữa 2 lần đăng bài trên cùng 1 tài khoản phải từ 15 đến 1440 phút!")

    scheduler.update_config(
        interval_minutes=req.interval_minutes,
        upload_interval_seconds=req.upload_interval_seconds,
        auto_download=req.auto_download,
        auto_render=req.auto_render,
        save_by_channel_folder=req.save_by_channel_folder,
        max_videos_per_scan=req.max_videos_per_scan,
        channel_delay_seconds=req.channel_delay_seconds,
        auto_retry_enabled=req.auto_retry_enabled,
        max_retries=req.max_retries,
        retry_delay_minutes=req.retry_delay_minutes,
        watchdog_enabled=req.watchdog_enabled,
        stuck_timeout_minutes=req.stuck_timeout_minutes,
        min_account_cooldown_minutes=req.min_account_cooldown_minutes
    )
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scheduler_interval_minutes', ?)", (str(req.interval_minutes),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_interval_seconds', ?)", (str(req.upload_interval_seconds),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_download', ?)", ("1" if req.auto_download else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_render', ?)", ("1" if req.auto_render else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('save_by_channel_folder', ?)", ("1" if req.save_by_channel_folder else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('max_videos_per_scan', ?)", (str(req.max_videos_per_scan),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('channel_delay_seconds', ?)", (str(req.channel_delay_seconds),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_auto_retry', ?)", ("1" if req.auto_retry_enabled else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_max_retries', ?)", (str(req.max_retries),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_retry_delay_minutes', ?)", (str(req.retry_delay_minutes),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('watchdog_enabled', ?)", ("1" if req.watchdog_enabled else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_stuck_timeout_minutes', ?)", (str(req.stuck_timeout_minutes),))
        if req.min_account_cooldown_minutes is not None:
            cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('min_account_cooldown_minutes', ?)", (str(req.min_account_cooldown_minutes),))
        conn.commit()
        conn.close()
    except Exception as e:
        log_event("WARNING", f"Lỗi lưu cấu hình scheduler vào DB: {e}")

    log_event("INFO", f"Đã cập nhật cấu hình tự động: Quét RSS {req.interval_minutes}p/lần, kiểm tra Upload {req.upload_interval_seconds}s, Giãn cách đăng nick {req.min_account_cooldown_minutes or 60}p, Auto-Retry: {'BẬT' if req.auto_retry_enabled else 'TẮT'} ({req.max_retries} lần, cách {req.retry_delay_minutes}p), Watchdog: {'BẬT' if req.watchdog_enabled else 'TẮT'} ({req.stuck_timeout_minutes}p).")
    return {
        "status": "success",
        "message": f"Đã lưu cấu hình tự động quét ({req.interval_minutes} phút/lần) và Auto-Retry/Watchdog thành công!",
        "settings": {
            "interval_minutes": req.interval_minutes,
            "upload_interval_seconds": req.upload_interval_seconds,
            "auto_download": req.auto_download,
            "auto_render": req.auto_render,
            "save_by_channel_folder": req.save_by_channel_folder,
            "max_videos_per_scan": req.max_videos_per_scan,
            "channel_delay_seconds": req.channel_delay_seconds,
            "auto_retry_enabled": req.auto_retry_enabled,
            "max_retries": req.max_retries,
            "retry_delay_minutes": req.retry_delay_minutes,
            "watchdog_enabled": req.watchdog_enabled,
            "stuck_timeout_minutes": req.stuck_timeout_minutes,
            "scheduler_running": scheduler.is_running
        }
    }

@app.post("/api/settings/test-key")
def test_youtube_key(req: TestApiKeyRequest):
    if not req.key or not req.key.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập API Key cần kiểm tra!")
    result = yt_scanner.test_key(req.key.strip())
    return result

@app.post("/api/utils/browse-folder")
def browse_folder():
    """Opens a native Windows FolderBrowserDialog to pick a directory path."""
    import subprocess
    try:
        ps_cmd = (
            'Add-Type -AssemblyName System.Windows.Forms; '
            '$d = New-Object System.Windows.Forms.FolderBrowserDialog; '
            '$d.Description = "Chọn thư mục lưu trữ video TikTok Farm"; '
            '$d.ShowNewFolderButton = $true; '
            'if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }'
        )
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_cmd],
            capture_output=True,
            text=True,
            timeout=120
        )
        selected = proc.stdout.strip()
        if selected:
            norm_path = selected.replace("\\", "/")
            return {"status": "success", "path": norm_path}
        return {"status": "cancelled", "path": ""}
    except Exception as e:
        return {"status": "error", "message": str(e), "path": ""}

# --- AI Usage & Cost Tracking APIs ---
@app.get("/api/ai/usage")
def get_ai_usage(limit: int = 100):
    limit = max(1, min(limit, 500))
    from backend.database import get_ai_usage_stats
    return get_ai_usage_stats(limit=limit)

@app.post("/api/ai/usage/clear")
def clear_ai_usage():
    from backend.database import clear_ai_usage_logs
    success = clear_ai_usage_logs()
    return {"status": "ok" if success else "error"}

# --- System Diagnostics, File Logs & Active Issues APIs ---
@app.get("/api/system/active-issues")
def get_active_issues_endpoint():
    """Lấy danh sách chi tiết toàn bộ các cảnh báo và vấn đề lỗi đang tồn tại trên hệ thống"""
    return get_system_active_issues()

@app.get("/api/system/diagnostics")
def get_system_diagnostics():
    """Kiểm tra toàn diện môi trường runtime, FFmpeg, Node.js, Playwright, GPM và các API Keys"""
    return run_environment_diagnostics()

@app.get("/api/system/logs/file")
def get_file_logs(limit: int = 300, level: str = "ALL", search: str = ""):
    """Đọc các dòng log thực tế được ghi vào file data/logs/app.log với bộ lọc và giới hạn tài nguyên"""
    limit = max(1, min(limit, 2000))
    search = (search or "").strip()[:100]
    level = (level or "ALL").upper()[:20]
    logs = get_recent_log_lines(limit=limit, level_filter=level, search_query=search)
    file_info = get_log_file_info()
    return {
        "status": "success",
        "file_info": file_info,
        "count": len(logs),
        "logs": logs
    }

@app.get("/api/system/logs/info")
def get_log_info():
    """Lấy kích thước và tình trạng file log trên ổ cứng"""
    return get_log_file_info()

@app.get("/api/system/logs/download")
def download_log_file():
    """Cho phép tải trực tiếp file app.log về máy tính để gửi hỗ trợ hoặc debug"""
    if not LOG_FILE_PATH.exists():
        raise HTTPException(status_code=404, detail="File log chưa được tạo")
    return FileResponse(
        path=str(LOG_FILE_PATH),
        filename="tiktok_farm_debug.log",
        media_type="text/plain"
    )

@app.post("/api/system/logs/clear")
def clear_system_logs():
    """Làm sạch file log trên đĩa"""
    ok = clear_log_file()
    return {"status": "success" if ok else "error"}

@app.on_event("startup")
def on_startup():
    try:
        # 1. Restore environment settings from SQLite settings table
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM settings")
        db_settings = dict(cursor.fetchall())
        conn.close()
        for k, v in db_settings.items():
            if v and (k not in os.environ or not os.environ[k]):
                os.environ[k] = v
        if "YOUTUBE_API_KEYS" in db_settings:
            yt_scanner.reload_keys(db_settings["YOUTUBE_API_KEYS"])
        log_event("INFO", f"Đã phục hồi {len(db_settings)} cấu hình từ cơ sở dữ liệu SQLite.")
    except Exception as e:
        log_event("WARNING", f"Lỗi phục hồi cấu hình từ DB settings: {e}")

    try:
        # 2. Check if scheduler was previously paused or enabled
        scheduler.load_settings()
        saved_running = db_settings.get("scheduler_running", "1") if 'db_settings' in locals() else "1"
        should_run = (saved_running == "1")
        if should_run:
            scheduler.start()
            log_event("INFO", f"Tự động kích hoạt Background Automation Scheduler ({scheduler.rss_interval_minutes}p/chu kỳ).")
        else:
            scheduler.stop()
            log_event("INFO", "Background Automation Scheduler đang ở trạng thái TẠM DỪNG theo thiết lập đã lưu.")
    except Exception as e:
        log_event("WARNING", f"Không thể tự khởi động Background Scheduler: {e}")

# --- Static Frontend & Media Mount ---
# Chỉ mount các thư mục media video cụ thể (downloads, rendered), bảo vệ SQLite DB và file logs (OWASP A01 / Broken Access Control)
from backend.config import DOWNLOADS_DIR, RENDERED_DIR
if DOWNLOADS_DIR.exists():
    app.mount("/media/downloads", StaticFiles(directory=str(DOWNLOADS_DIR)), name="media_downloads")
if RENDERED_DIR.exists():
    app.mount("/media/rendered", StaticFiles(directory=str(RENDERED_DIR)), name="media_rendered")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

if LOGO_DIR.exists():
    app.mount("/logo", StaticFiles(directory=str(LOGO_DIR)), name="logo")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
