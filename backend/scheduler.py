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

    def start(self):
        if self.is_running:
            return
        self.is_running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log_event("INFO", "Background Scheduler đã khởi động.")

    def stop(self):
        self.is_running = False

    def _loop(self):
        last_rss_check = 0
        last_upload_check = 0

        while self.is_running:
            now = time.time()

            # 1. Quét RSS định kỳ mỗi 15 phút (900s)
            if now - last_rss_check > 900:
                try:
                    total_new = yt_monitor.scan_all_monitored_channels()
                    if total_new > 0:
                        log_event("INFO", f"[SCHEDULER] Đã phát hiện và tải về {total_new} video mới qua RSS.")
                except Exception as e:
                    log_event("WARNING", f"[SCHEDULER] Lỗi quét RSS: {str(e)}")
                last_rss_check = now

            # 2. Kiểm tra các tác vụ upload tới giờ đăng (mỗi 60s)
            if now - last_upload_check > 60:
                try:
                    self._process_pending_uploads()
                except Exception as e:
                    log_event("WARNING", f"[SCHEDULER] Lỗi xử lý hàng đợi upload: {str(e)}")
                last_upload_check = now

            time.sleep(10)

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
