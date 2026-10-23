import os
import json
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from backend.config import BASE_DIR, SERVER_HOST, SERVER_PORT, save_env_config, YOUTUBE_API_KEY, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GEMINI_API_KEY, OPENAI_API_KEY, GPM_API_BASE_URL
from backend.database import get_connection, log_event
from backend.modules.gpm_client import gpm_client
from backend.modules.yt_scanner import yt_scanner
from backend.modules.yt_downloader import yt_downloader
from backend.modules.ai_video_engine import ai_video_engine
from backend.modules.tiktok_uploader import tiktok_uploader
from backend.modules.metrics_tracker import metrics_tracker
from backend.modules.notifier import notifier
from backend.modules.yt_monitor import yt_monitor
from backend.scheduler import scheduler

app = FastAPI(title="TikTok Auto Farm & AI Video Engine", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = BASE_DIR / "frontend"

# --- Models ---
class SearchKeywordRequest(BaseModel):
    keyword: str
    max_results: int = 50

class UnsaveChannelRequest(BaseModel):
    channel_id: str

class DownloadVideoRequest(BaseModel):
    url: str

class RenderVideoRequest(BaseModel):
    video_id: str
    part_number: int = 1
    duration: int = 65
    flip_horizontal: bool = True
    speed_factor: float = 1.03

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

class UpdateChannelSettingsRequest(BaseModel):
    channel_id: str
    display_name: Optional[str] = ""
    custom_proxy: Optional[str] = ""
    download_dir: Optional[str] = ""
    render_dir: Optional[str] = ""
    is_active: Optional[int] = 1
    auto_download: Optional[int] = 1
    auto_render: Optional[int] = 1

class ToggleChannelStatusRequest(BaseModel):
    channel_id: str
    is_active: Optional[int] = None

class ClearChannelHistoryRequest(BaseModel):
    channel_id: str
    delete_files: bool = True

class ScanChannelRequest(BaseModel):
    channel_id: str

class SaveApiKeysRequest(BaseModel):
    youtube_api_keys: Optional[str] = ""       # comma-separated list
    gemini_api_key: Optional[str] = ""
    openai_api_key: Optional[str] = ""
    telegram_bot_token: Optional[str] = ""
    telegram_chat_id: Optional[str] = ""
    gpm_api_base_url: Optional[str] = ""

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
    daily_limit: Optional[int] = 3
    post_schedule: Optional[str] = "11:30, 18:00, 20:30"
    post_frequency: Optional[str] = "daily"
    post_interval_days: Optional[int] = 1
    post_days_of_week: Optional[str] = "mon,tue,wed,thu,fri,sat,sun"
    random_delay_minutes: Optional[int] = 10
    warmup_mode: Optional[int] = 0
    is_active: Optional[int] = 1

# --- Dashboard API ---
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

    return {
        "total_channels": total_channels,
        "total_videos": total_videos,
        "total_profiles": total_profiles,
        "eligible_10k_count": eligible_10k,
        "gpm_health": gpm_status,
        "recent_logs": logs
    }

# --- GPMLogin API ---
@app.get("/api/gpm/health")
def check_gpm_health():
    return gpm_client.check_health()

@app.post("/api/gpm/sync")
def sync_gpm_profiles():
    """Đồng bộ toàn bộ danh sách profile từ GPMLogin vào database"""
    profiles = gpm_client.get_profiles()
    if not profiles:
        return {"status": "warning", "message": "Không tìm thấy profile nào từ GPMLogin (hoặc GPM chưa mở)", "synced": 0}

    conn = get_connection()
    cursor = conn.cursor()
    synced = 0
    for p in profiles:
        cursor.execute('''
        INSERT INTO gpm_profiles (gpm_id, name, raw_proxy)
        VALUES (?, ?, ?)
        ON CONFLICT(gpm_id) DO UPDATE SET
            name = excluded.name,
            raw_proxy = excluded.raw_proxy
        ''', (p["id"], p["name"], p["raw_proxy"]))
        synced += 1
    conn.commit()
    conn.close()

    log_event("INFO", f"Đã đồng bộ {synced} profile từ GPMLogin")
    return {"status": "success", "synced": synced}

@app.get("/api/gpm/profiles")
def list_gpm_profiles():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM gpm_profiles ORDER BY followers_count DESC, id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows

# --- YouTube Intelligence API ---
@app.post("/api/youtube/search")
def search_youtube_channels(req: SearchKeywordRequest):
    """Tìm kiếm và lọc kênh theo từ khóa và tần suất ra video"""
    results = yt_scanner.search_channels_by_keyword(req.keyword, req.max_results)

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
            auto_render = ?
        WHERE channel_id = ?
    ''', (
        req.display_name or '',
        req.custom_proxy or '',
        req.download_dir or '',
        req.render_dir or '',
        1 if req.is_active else 0,
        1 if req.auto_download else 0,
        1 if req.auto_render else 0,
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
    cursor.execute("SELECT id, download_path, rendered_path FROM videos WHERE channel_id = ?", (req.channel_id,))
    rows = cursor.fetchall()

    files_deleted = 0
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
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã xóa lịch sử {deleted_count} video ({files_deleted} files) của kênh {req.channel_id}")
    return {"status": "success", "deleted_videos": deleted_count, "files_deleted": files_deleted}

@app.post("/api/youtube/channels/scan-now")
def scan_channel_now(req: ScanChannelRequest):
    result = yt_monitor.scan_single_channel(req.channel_id)
    return result

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
        ORDER BY v.id DESC LIMIT 15
    ''')
    recent_videos = [dict(r) for r in cursor.fetchall()]

    cursor.execute('''
        SELECT ut.*, gp.name as gpm_profile_name
        FROM upload_tasks ut
        LEFT JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
        ORDER BY ut.id DESC LIMIT 10
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

@app.post("/api/campaigns")
def create_campaign(req: CreateCampaignRequest):
    conn = get_connection()
    cursor = conn.cursor()

    ch_ids = req.channel_ids if req.channel_ids else ([req.channel_id] if req.channel_id else [])
    gpm_ids = req.gpm_profile_ids if req.gpm_profile_ids else ([req.gpm_profile_id] if req.gpm_profile_id else [])
    main_ch = ch_ids[0] if ch_ids else ""
    main_gpm = gpm_ids[0] if gpm_ids else None

    cursor.execute('''
        INSERT INTO campaigns (
            name, channel_id, gpm_profile_id, channel_ids, gpm_profile_ids,
            distribution_mode, download_dir, render_dir, subtitle_enabled,
            subtitle_style, aspect_ratio, preset_name, video_duration,
            speed_factor, flip_horizontal, daily_limit, post_schedule,
            post_frequency, post_interval_days, post_days_of_week,
            random_delay_minutes, warmup_mode, is_active
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        req.daily_limit or 3,
        req.post_schedule or '11:30, 18:00, 20:30',
        req.post_frequency or 'daily',
        req.post_interval_days or 1,
        req.post_days_of_week or 'mon,tue,wed,thu,fri,sat,sun',
        req.random_delay_minutes if req.random_delay_minutes is not None else 10,
        1 if req.warmup_mode else 0,
        1 if req.is_active else 0
    ))
    campaign_id = cursor.lastrowid
    # Persist last used download/render dirs in settings table for future campaigns
    if req.download_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_download_dir', ?)", (req.download_dir.strip(),))
    if req.render_dir:
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('default_render_dir', ?)", (req.render_dir.strip(),))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã tạo chiến dịch: '{req.name}' ({len(ch_ids)} kênh -> {len(gpm_ids)} nick GPM)")
    return {"status": "success", "id": campaign_id, "channels_count": len(ch_ids), "profiles_count": len(gpm_ids)}

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
    log_event("INFO", f"Chuyển trạng thái chiến dịch '{row['name']}' sang: {'Bật' if new_state else 'Tắt'}")
    return {"status": "success", "is_active": new_state}

@app.delete("/api/campaigns/{campaign_id}")
def delete_campaign(campaign_id: int):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM campaigns WHERE id = ?", (campaign_id,))
    conn.commit()
    conn.close()
    log_event("INFO", f"Đã xóa chiến dịch ID {campaign_id}")
    return {"status": "success"}



# --- Video Download & AI Edit API ---
@app.post("/api/video/download")
def download_video(req: DownloadVideoRequest, bg_tasks: BackgroundTasks):
    result = yt_downloader.download_video(req.url)
    if not result:
        raise HTTPException(status_code=400, detail="Không thể tải video từ URL này")
    return {"status": "success", "video": result}

@app.get("/api/video/list")
def list_videos():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT v.*, COALESCE(c.display_name, c.title, 'Dán trực tiếp') as channel_name
        FROM videos v
        LEFT JOIN channels c ON v.channel_id = c.channel_id
        ORDER BY v.id DESC
    ''')
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    data_dir = BASE_DIR / "data"
    for r in rows:
        if r.get("rendered_path") and os.path.exists(r["rendered_path"]):
            try:
                rel = os.path.relpath(r["rendered_path"], data_dir).replace("\\", "/")
                r["media_url"] = f"/media/{rel}"
            except Exception:
                r["media_url"] = ""
        elif r.get("download_path") and os.path.exists(r["download_path"]):
            try:
                rel = os.path.relpath(r["download_path"], data_dir).replace("\\", "/")
                r["media_url"] = f"/media/{rel}"
            except Exception:
                r["media_url"] = ""
        else:
            r["media_url"] = ""
    return rows

@app.post("/api/video/render")
def render_video_ai(req: RenderVideoRequest):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT download_path, title, duration FROM videos WHERE yt_video_id = ?", (req.video_id,))
    row = cursor.fetchone()
    conn.close()

    if not row or not row["download_path"] or not os.path.exists(row["download_path"]):
        raise HTTPException(status_code=404, detail="Không tìm thấy file video gốc đã tải")

    rendered = ai_video_engine.process_transformative_video(
        input_file=row["download_path"],
        video_id=req.video_id,
        part_number=req.part_number,
        duration=req.duration,
        flip_horizontal=req.flip_horizontal,
        speed_factor=req.speed_factor
    )

    if not rendered:
        raise HTTPException(status_code=500, detail="Lỗi khi render video AI")

    copy_data = ai_video_engine.generate_ai_hook_and_copy(row["title"])

    return {
        "status": "success",
        "rendered_file": rendered,
        "ai_copy": copy_data
    }

# --- TikTok Upload API ---
@app.post("/api/tiktok/upload")
def upload_tiktok(req: UploadVideoRequest):
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
    result = metrics_tracker.update_profile_stats(
        gpm_id=req.gpm_id,
        followers=req.followers,
        total_views=req.views,
        username=req.username or ""
    )
    return result

@app.post("/api/telegram/test-alert")
def test_telegram_alert():
    success = notifier.send_10k_alert(
        profile_name="Profile Demo #01",
        username="mmo_creator_us",
        followers=10450,
        views=250000
    )
    return {"status": "success" if success else "failed", "message": "Đã gửi test alert Telegram"}

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
    gemini = os.getenv("GEMINI_API_KEY", db_settings.get("GEMINI_API_KEY", cfg.GEMINI_API_KEY))
    openai = os.getenv("OPENAI_API_KEY", db_settings.get("OPENAI_API_KEY", cfg.OPENAI_API_KEY))
    tele_token = os.getenv("TELEGRAM_BOT_TOKEN", db_settings.get("TELEGRAM_BOT_TOKEN", cfg.TELEGRAM_BOT_TOKEN))
    tele_chat = os.getenv("TELEGRAM_CHAT_ID", db_settings.get("TELEGRAM_CHAT_ID", cfg.TELEGRAM_CHAT_ID))
    gpm_url = os.getenv("GPM_API_BASE_URL", db_settings.get("GPM_API_BASE_URL", cfg.GPM_API_BASE_URL))

    pool_status = yt_scanner.key_pool.get_keys_status()
    return {
        "youtube_api_keys": raw,
        "youtube_key_pool": pool_status,
        "gemini_api_key": gemini,
        "openai_api_key": openai,
        "telegram_bot_token": tele_token,
        "telegram_chat_id": tele_chat,
        "gpm_api_base_url": gpm_url,
    }

@app.post("/api/settings/keys")
def save_api_keys(req: SaveApiKeysRequest):
    updates = {}
    if req.youtube_api_keys is not None:
        keys = [k.strip() for k in req.youtube_api_keys.replace(";", ",").replace("\n", ",").split(",") if k.strip()]
        raw = ",".join(keys)
        updates["YOUTUBE_API_KEY"] = raw
        updates["YOUTUBE_API_KEYS"] = raw
    if req.gemini_api_key is not None:
        updates["GEMINI_API_KEY"] = req.gemini_api_key.strip()
    if req.openai_api_key is not None:
        updates["OPENAI_API_KEY"] = req.openai_api_key.strip()
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
    log_event("INFO", f"Đã cập nhật cấu hình API keys và lưu vào DB: {list(updates.keys())}")
    return {"status": "ok", "message": "Đã lưu cấu hình thành công", "pool_size": yt_scanner.key_pool.total_keys}

class UpdateSchedulerSettingsRequest(BaseModel):
    interval_minutes: int = 15
    upload_interval_seconds: int = 60
    auto_download: bool = True
    auto_render: bool = True
    max_videos_per_scan: int = 5
    channel_delay_seconds: int = 2

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
        "max_videos_per_scan": int(settings_dict.get("max_videos_per_scan", getattr(scheduler, "max_videos_per_scan", 5))),
        "channel_delay_seconds": int(settings_dict.get("channel_delay_seconds", getattr(scheduler, "channel_delay_seconds", 2))),
        "scheduler_running": scheduler.is_running
    }

@app.post("/api/settings/scheduler")
def update_scheduler_settings(req: UpdateSchedulerSettingsRequest):
    """Save and apply advanced scheduler settings."""
    scheduler.update_config(
        interval_minutes=req.interval_minutes,
        upload_interval_seconds=req.upload_interval_seconds,
        auto_download=req.auto_download,
        auto_render=req.auto_render,
        max_videos_per_scan=req.max_videos_per_scan,
        channel_delay_seconds=req.channel_delay_seconds
    )
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('scheduler_interval_minutes', ?)", (str(req.interval_minutes),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('upload_interval_seconds', ?)", (str(req.upload_interval_seconds),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_download', ?)", ("1" if req.auto_download else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_render', ?)", ("1" if req.auto_render else "0",))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('max_videos_per_scan', ?)", (str(req.max_videos_per_scan),))
        cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('channel_delay_seconds', ?)", (str(req.channel_delay_seconds),))
        conn.commit()
        conn.close()
    except Exception as e:
        log_event("WARNING", f"Lỗi lưu cấu hình scheduler vào DB: {e}")

    log_event("INFO", f"Đã cập nhật cấu hình tự động: Quét RSS {req.interval_minutes}p/lần, kiểm tra Upload {req.upload_interval_seconds}s, Max/kênh {req.max_videos_per_scan}.")
    return {
        "status": "success",
        "message": f"Đã lưu cấu hình tự động quét ({req.interval_minutes} phút/lần) thành công!",
        "settings": {
            "interval_minutes": req.interval_minutes,
            "upload_interval_seconds": req.upload_interval_seconds,
            "auto_download": req.auto_download,
            "auto_render": req.auto_render,
            "max_videos_per_scan": req.max_videos_per_scan,
            "channel_delay_seconds": req.channel_delay_seconds,
            "scheduler_running": scheduler.is_running
        }
    }

@app.post("/api/settings/test-key")
def test_youtube_key(req: TestApiKeyRequest):
    result = yt_scanner.test_key(req.key)
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
        should_run = db_settings.get("scheduler_running", "1") == "1" if 'db_settings' in locals() else True
        if should_run:
            scheduler.start()
            log_event("INFO", f"Tự động kích hoạt Background Automation Scheduler ({scheduler.rss_interval_minutes}p/chu kỳ).")
    except Exception as e:
        log_event("WARNING", f"Không thể tự khởi động Background Scheduler: {e}")

# --- Static Frontend & Media Mount ---
DATA_DIR = BASE_DIR / "data"
if DATA_DIR.exists():
    app.mount("/media", StaticFiles(directory=str(DATA_DIR)), name="media")

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
