import os
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

# --- YouTube Intelligence API (C2V Key) ---
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
        "scheduler_running": scheduler.is_running,
        "active_channels": active_channels,
        "total_channels": total_channels,
        "video_stats": {
            "pending": video_stats.get("pending", 0),
            "downloaded": video_stats.get("downloaded", 0),
            "rendering": video_stats.get("rendering", 0),
            "rendered": video_stats.get("rendered", 0),
            "uploaded": video_stats.get("uploaded", 0),
            "error": video_stats.get("error", 0)
        },
        "recent_pipeline": recent_videos,
        "recent_upload_tasks": recent_tasks
    }

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
    cursor.execute("SELECT * FROM videos ORDER BY id DESC")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
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

# --- API Key Management ---
@app.get("/api/settings/keys")
def get_api_keys():
    import os
    import backend.config as cfg
    raw = os.getenv("YOUTUBE_API_KEYS", os.getenv("YOUTUBE_API_KEY", ""))
    pool_status = yt_scanner.key_pool.get_keys_status()
    return {
        "youtube_api_keys": raw,
        "youtube_key_pool": pool_status,
        "gemini_api_key": cfg.GEMINI_API_KEY,
        "openai_api_key": cfg.OPENAI_API_KEY,
        "telegram_bot_token": cfg.TELEGRAM_BOT_TOKEN,
        "telegram_chat_id": cfg.TELEGRAM_CHAT_ID,
        "gpm_api_base_url": cfg.GPM_API_BASE_URL,
    }

@app.post("/api/settings/keys")
def save_api_keys(req: SaveApiKeysRequest):
    updates = {}
    if req.youtube_api_keys is not None:
        # Normalize: strip spaces around commas, deduplicate
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
    save_env_config(updates)
    yt_scanner.reload_keys(updates.get("YOUTUBE_API_KEYS", ""))
    log_event("INFO", f"Đã cập nhật cấu hình API keys: {list(updates.keys())}")
    return {"status": "ok", "message": "Đã lưu cấu hình thành công", "pool_size": yt_scanner.key_pool.total_keys}

@app.post("/api/settings/test-key")
def test_youtube_key(req: TestApiKeyRequest):
    result = yt_scanner.test_key(req.key)
    return result

@app.on_event("startup")
def on_startup():
    try:
        scheduler.start()
    except Exception as e:
        log_event("WARNING", f"Không thể tự khởi động Background Scheduler: {e}")

# --- Static Frontend Mount ---
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

    @app.get("/")
    def serve_frontend():
        return FileResponse(str(FRONTEND_DIR / "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
