import time
import threading
from datetime import datetime
from backend.database import log_event, get_connection
from backend.modules.yt_monitor import yt_monitor
from backend.modules.distributor import distributor
from backend.modules.tiktok_uploader import tiktok_uploader

class BackgroundScheduler:
    """
    Điều phối các tác vụ chạy ngầm định kỳ:
    1. Quét RSS kênh YouTube (mỗi 15 phút) -> Tải video mới
    2. Kiểm tra hàng đợi đăng bài (mỗi 5 phút) -> Khởi chạy upload qua GPMLogin
    """
    def __init__(self):
        self.is_running = False
        self._thread = None
        self.rss_interval_minutes = 15
        self.upload_interval_seconds = 60
        self.auto_download = True
        self.auto_render = True
        self.max_videos_per_scan = 5
        self.channel_delay_seconds = 2
        self.load_settings()

    def load_settings(self):
        """Đọc cấu hình scheduler từ SQLite settings table"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings")
            db_settings = dict(cursor.fetchall())
            conn.close()
            if "scheduler_interval_minutes" in db_settings:
                self.rss_interval_minutes = max(1, int(db_settings["scheduler_interval_minutes"]))
            if "upload_interval_seconds" in db_settings:
                self.upload_interval_seconds = max(10, int(db_settings["upload_interval_seconds"]))
            if "auto_download" in db_settings:
                self.auto_download = db_settings["auto_download"] == "1"
            if "auto_render" in db_settings:
                self.auto_render = db_settings["auto_render"] == "1"
            if "max_videos_per_scan" in db_settings:
                self.max_videos_per_scan = max(1, int(db_settings["max_videos_per_scan"]))
            if "channel_delay_seconds" in db_settings:
                self.channel_delay_seconds = max(0, int(db_settings["channel_delay_seconds"]))
        except Exception as e:
            log_event("WARNING", f"Lỗi đọc cấu hình scheduler từ DB: {e}")

    def update_config(self, interval_minutes=None, upload_interval_seconds=None, auto_download=None, auto_render=None, max_videos_per_scan=None, channel_delay_seconds=None):
        """Cập nhật cấu hình runtime ngay lập tức"""
        if interval_minutes is not None:
            self.rss_interval_minutes = max(1, int(interval_minutes))
        if upload_interval_seconds is not None:
            self.upload_interval_seconds = max(10, int(upload_interval_seconds))
        if auto_download is not None:
            self.auto_download = bool(auto_download)
        if auto_render is not None:
            self.auto_render = bool(auto_render)
        if max_videos_per_scan is not None:
            self.max_videos_per_scan = max(1, int(max_videos_per_scan))
        if channel_delay_seconds is not None:
            self.channel_delay_seconds = max(0, int(channel_delay_seconds))

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log_event("INFO", f"Background Scheduler đã khởi động (chu kỳ quét {self.rss_interval_minutes} phút).")

    def stop(self):
        self.is_running = False

    def _loop(self):
        last_rss_check = 0
        last_upload_check = 0

        while self.is_running:
            now = time.time()

            # 1. Quét RSS định kỳ theo rss_interval_minutes
            rss_delay_secs = max(60, self.rss_interval_minutes * 60)
            if now - last_rss_check > rss_delay_secs:
                if self.auto_download:
                    try:
                        total_new = yt_monitor.scan_all_monitored_channels(
                            max_per_channel=self.max_videos_per_scan,
                            delay=float(self.channel_delay_seconds)
                        )
                        if total_new > 0:
                            log_event("INFO", f"[SCHEDULER] Đã quét chu kỳ ({self.rss_interval_minutes}p): phát hiện và tải về {total_new} video mới qua RSS.")
                    except Exception as e:
                        log_event("WARNING", f"[SCHEDULER] Lỗi quét RSS: {str(e)}")
                last_rss_check = now

            # 2. Kiểm tra các tác vụ upload tới giờ đăng theo upload_interval_seconds
            upload_delay_secs = max(10, self.upload_interval_seconds)
            if now - last_upload_check > upload_delay_secs:
                try:
                    self._process_pending_uploads()
                except Exception as e:
                    log_event("WARNING", f"[SCHEDULER] Lỗi xử lý hàng đợi upload: {str(e)}")
                last_upload_check = now

            time.sleep(5)

    def _process_pending_uploads(self):
        conn = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Lấy các task đang ở trạng thái queued và tới giờ đăng
        cursor.execute('''
        SELECT ut.id, ut.video_id, ut.title, ut.tags, v.rendered_path, gp.gpm_id
        FROM upload_tasks ut
        JOIN videos v ON ut.video_id = v.id
        JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
        WHERE ut.status = 'queued' AND (ut.scheduled_time IS NULL OR ut.scheduled_time <= ?)
        LIMIT 1
        ''', (now_str,))
        task = cursor.fetchone()

        if task:
            task_id = task["id"]
            video_path = task["rendered_path"]
            gpm_id = task["gpm_id"]
            title = task["title"]
            tags = task["tags"]

            cursor.execute("UPDATE upload_tasks SET status = 'processing' WHERE id = ?", (task_id,))
            conn.commit()
            conn.close()

            # Thực thi upload
            res = tiktok_uploader.upload_via_gpm(
                gpm_profile_id=gpm_id,
                video_path=video_path,
                title=title,
                tags=tags,
                auto_post=True
            )

            conn = get_connection()
            cursor = conn.cursor()
            if res.get("success"):
                cursor.execute("UPDATE upload_tasks SET status = 'completed', uploaded_at = ? WHERE id = ?", (now_str, task_id))
            else:
                cursor.execute("UPDATE upload_tasks SET status = 'failed', error_message = ? WHERE id = ?", (res.get("message"), task_id))
            conn.commit()
            conn.close()
        else:
            conn.close()

scheduler = BackgroundScheduler()
