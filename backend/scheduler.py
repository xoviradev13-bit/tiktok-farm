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
        
        # Cấu hình quét follower định kỳ & giờ cố định hàng ngày
        self.follower_scan_enabled = True
        self.follower_scan_mode = "daily_times"  # "daily_times" hoặc "interval"
        self.follower_scan_times = "08:00, 20:00"
        self.follower_scan_interval_hours = 6
        self._triggered_follower_scans = set()
        self.last_follower_scan = 0
        
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
            if "follower_scan_enabled" in db_settings:
                self.follower_scan_enabled = db_settings["follower_scan_enabled"] == "1"
            if "follower_scan_mode" in db_settings:
                self.follower_scan_mode = db_settings["follower_scan_mode"]
            if "follower_scan_times" in db_settings:
                self.follower_scan_times = db_settings["follower_scan_times"]
            if "follower_scan_interval_hours" in db_settings:
                self.follower_scan_interval_hours = max(1, int(db_settings["follower_scan_interval_hours"]))
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

    def update_follower_config(self, enabled=None, mode=None, times=None, interval_hours=None):
        """Cập nhật cấu hình quét follower runtime"""
        if enabled is not None:
            self.follower_scan_enabled = bool(enabled)
        if mode is not None:
            self.follower_scan_mode = str(mode)
        if times is not None:
            self.follower_scan_times = str(times)
        if interval_hours is not None:
            self.follower_scan_interval_hours = max(1, int(interval_hours))

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
        last_cleanup_check = 0

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

            # 3. Tự động kiểm tra dọn dẹp file MP4 đã đăng quá hạn (mỗi 1 giờ)
            if now - last_cleanup_check > 3600:
                try:
                    from backend.app import cleanup_uploaded_files
                    cleanup_uploaded_files()
                except Exception as e:
                    pass
                last_cleanup_check = now

            # 4. Tự động kiểm tra lịch quét chỉ số / Follower TikTok định kỳ
            try:
                self._check_and_trigger_follower_scan(now)
            except Exception as e:
                pass

            time.sleep(5)

    def _check_and_trigger_follower_scan(self, now):
        """Kểm tra thời gian và kích hoạt quét follower tự động theo cấu hình"""
        if not self.follower_scan_enabled:
            return

        should_trigger = False
        today_str = datetime.now().strftime("%Y-%m-%d")
        now_hm = datetime.now().strftime("%H:%M")

        if self.follower_scan_mode == "daily_times":
            # Ví dụ: "08:00, 20:00"
            raw_times = [t.strip() for t in self.follower_scan_times.split(",") if t.strip()]
            for t in raw_times:
                if t == now_hm:
                    trigger_key = f"{today_str}_{t}"
                    if trigger_key not in self._triggered_follower_scans:
                        self._triggered_follower_scans.add(trigger_key)
                        self._triggered_follower_scans = {k for k in self._triggered_follower_scans if k.startswith(today_str)}
                        should_trigger = True
                        break
        elif self.follower_scan_mode == "interval":
            interval_secs = max(1800, self.follower_scan_interval_hours * 3600)
            if self.last_follower_scan == 0:
                self.last_follower_scan = now
            elif now - self.last_follower_scan > interval_secs:
                should_trigger = True

        if should_trigger:
            self.last_follower_scan = now
            def _async_scan():
                try:
                    from backend.modules.tiktok_tracker import tiktok_tracker
                    log_event("INFO", f"[SCHEDULER] ⏰ Kích hoạt quét Follower tự động ({self.follower_scan_mode})...")
                    tiktok_tracker.scan_all_profiles()
                except Exception as e:
                    log_event("WARNING", f"[SCHEDULER] Lỗi quét follower tự động: {e}")
            t = threading.Thread(target=_async_scan, daemon=True)
            t.start()


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

            # Kiểm tra an toàn: Nếu profile đang bận quét follower thì tạm hoãn để không gây xung đột browser
            from backend.modules.tiktok_tracker import is_profile_busy
            if is_profile_busy(gpm_id):
                conn.close()
                return

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
                conn.commit()
                try:
                    cursor.execute("SELECT value FROM settings WHERE key = 'cleanup_retention_mode'")
                    s_row = cursor.fetchone()
                    if s_row and s_row["value"] in ("0", "immediate"):
                        from backend.app import cleanup_uploaded_files
                        cleanup_uploaded_files(retention_mode="0")
                except Exception:
                    pass
            else:
                fail_msg = res.get("message", "Lỗi không xác định khi upload")
                cursor.execute("UPDATE upload_tasks SET status = 'failed', error_message = ? WHERE id = ?", (fail_msg, task_id))
                log_event("WARNING", f"Tác vụ đăng bài #{task_id} (GPM: {gpm_id}) thất bại: {fail_msg}")
            conn.commit()
            conn.close()
        else:
            conn.close()

scheduler = BackgroundScheduler()
