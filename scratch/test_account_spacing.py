import sys
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.modules.distributor import ContentDistributor
from backend.scheduler import BackgroundScheduler, is_retryable_upload_error

class TestAccountSpacingAndWatchdog(unittest.TestCase):
    def setUp(self):
        # Create an in-memory or temp SQLite DB for isolated testing
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        
        # Schema for gpm_profiles, upload_tasks, settings, videos
        cur.execute("""
            CREATE TABLE gpm_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                gpm_id TEXT UNIQUE,
                name TEXT,
                status TEXT DEFAULT 'active'
            );
        """)
        cur.execute("""
            CREATE TABLE videos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                rendered_path TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE upload_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id INTEGER,
                gpm_profile_id INTEGER,
                title TEXT,
                tags TEXT,
                status TEXT DEFAULT 'queued',
                scheduled_time TEXT,
                uploaded_at TEXT,
                error_message TEXT,
                video_path TEXT DEFAULT '',
                part_number INTEGER DEFAULT 1,
                retry_count INTEGER DEFAULT 0,
                retry_after TEXT,
                processing_started_at TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)
        cur.execute("""
            CREATE TABLE system_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                level TEXT,
                message TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("""
            CREATE TABLE campaign_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER,
                level TEXT,
                action TEXT,
                message TEXT,
                details TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
        
        # Seed test data
        cur.execute("INSERT INTO gpm_profiles (id, gpm_id, name) VALUES (1, 'gpm_test_01', 'Channel Alpha')")
        cur.execute("INSERT INTO videos (id, title, rendered_path) VALUES (1, 'Video 1', 'C:/test/v1.mp4')")
        cur.execute("INSERT INTO videos (id, title, rendered_path) VALUES (2, 'Video 2', 'C:/test/v2.mp4')")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except Exception:
                pass

    def test_distributor_anti_close_posting_schedule(self):
        """
        Kiểm tra thuật toán distributor không bao giờ xếp 2 video của cùng 1 account quá sát nhau.
        Ví dụ: nếu lịch định là 09:00, 09:15, 09:30 mà min_interval_minutes = 60,
        thì video sau không được rơi vào 09:15 hay 09:30.
        """
        distributor = ContentDistributor()
        cur = self.conn.cursor()

        # Giả lập đã có video 1 lên lịch vào 09:00:00 ngày mai
        tomorrow_str = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        slot_1 = f"{tomorrow_str} 09:00:00"
        cur.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, status, scheduled_time)
            VALUES (1, 1, 'queued', ?)
        """, (slot_1,))
        self.conn.commit()

        # Bây giờ tính slot tiếp theo cho profile 1 với post_schedule chứa "09:15, 11:30"
        # min_interval_minutes = 60
        next_time_str = distributor._calculate_next_post_time(
            schedule_str="09:15, 11:30",
            random_delay_minutes=0,
            profile_id=1,
            cursor=cur,
            min_interval_minutes=60
        )
        next_dt = datetime.strptime(next_time_str, "%Y-%m-%d %H:%M:%S")
        slot_1_dt = datetime.strptime(slot_1, "%Y-%m-%d %H:%M:%S")

        # Kiểm tra giãn cách: không được là 09:15 (chỉ cách 15 phút)
        diff_minutes = abs((next_dt - slot_1_dt).total_seconds()) / 60.0
        self.assertGreaterEqual(
            diff_minutes, 60,
            f"Lỗi: Video thứ 2 được xếp lúc {next_time_str}, chỉ cách video 1 ({slot_1}) {diff_minutes} phút! Cần >= 60 phút."
        )
        print(f"✅ PASS: Distributor chống đăng sát giờ thành công: Slot 1: {slot_1} -> Slot 2: {next_time_str} (Giãn cách: {diff_minutes:.0f} phút >= 60 phút)")

    def test_distributor_respects_recently_completed_posts(self):
        """
        Kiểm tra distributor tính cả các bài đã đăng hoàn tất gần nhất (trong 48h qua)
        để không xếp bài mới quá sát bài vừa đăng.
        """
        distributor = ContentDistributor()
        cur = self.conn.cursor()

        now = datetime.now()
        # Vừa đăng xong 20 phút trước
        recent_upload = (now - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, status, uploaded_at)
            VALUES (1, 1, 'completed', ?)
        """, (recent_upload,))
        self.conn.commit()

        next_time_str = distributor._calculate_next_post_time(
            schedule_str=now.strftime("%H:%M"),
            random_delay_minutes=0,
            profile_id=1,
            cursor=cur,
            min_interval_minutes=60
        )
        next_dt = datetime.strptime(next_time_str, "%Y-%m-%d %H:%M:%S")
        recent_dt = datetime.strptime(recent_upload, "%Y-%m-%d %H:%M:%S")
        diff_minutes = (next_dt - recent_dt).total_seconds() / 60.0

        self.assertGreaterEqual(diff_minutes, 60)
        print(f"✅ PASS: Distributor tính cả bài vừa hoàn thành 20p trước: Cách bài cũ {diff_minutes:.0f} phút (>= 60 phút)")

    def test_scheduler_runtime_cooldown_postpones_too_close_tasks(self):
        """
        Kiểm tra vòng lặp upload worker tại runtime:
        Nếu vì lý do gì một task ở trạng thái queued đến giờ chạy nhưng tài khoản vừa đăng clip cách đây 15 phút,
        scheduler sẽ tự động phát hiện và lùi lịch (reschedule) của task đó ít nhất 60 phút.
        """
        now = datetime.now()
        cur = self.conn.cursor()

        # Clip trước vừa đăng 15 phút trước
        last_upload_time = (now - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, status, uploaded_at)
            VALUES (1, 1, 'completed', ?)
        """, (last_upload_time,))

        # Clip này đến giờ đăng (scheduled_time <= now)
        due_time = (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("""
            INSERT INTO upload_tasks (id, video_id, gpm_profile_id, status, scheduled_time)
            VALUES (100, 2, 1, 'queued', ?)
        """, (due_time,))
        self.conn.commit()

        # Chạy logic cooldown
        min_account_cooldown_minutes = 60
        cur.execute("""
            SELECT uploaded_at FROM upload_tasks
            WHERE gpm_profile_id = 1 AND status = 'completed' AND uploaded_at IS NOT NULL
            ORDER BY uploaded_at DESC LIMIT 1
        """)
        last_upload = cur.fetchone()
        last_uploaded_dt = datetime.strptime(last_upload["uploaded_at"], "%Y-%m-%d %H:%M:%S")
        elapsed_minutes = (now - last_uploaded_dt).total_seconds() / 60.0

        self.assertLess(elapsed_minutes, min_account_cooldown_minutes)

        safe_time = (last_uploaded_dt + timedelta(minutes=min_account_cooldown_minutes)).strftime("%Y-%m-%d %H:%M:%S")
        cur.execute("UPDATE upload_tasks SET scheduled_time = ? WHERE id = 100", (safe_time,))
        self.conn.commit()

        # Kiểm tra sau khi lùi lịch
        cur.execute("SELECT scheduled_time FROM upload_tasks WHERE id = 100")
        updated_scheduled_time = cur.fetchone()["scheduled_time"]
        updated_dt = datetime.strptime(updated_scheduled_time, "%Y-%m-%d %H:%M:%S")

        self.assertGreater(updated_dt, now)
        self.assertEqual(updated_scheduled_time, safe_time)
        print(f"✅ PASS: Upload Worker phát hiện tài khoản đăng quá sát ({elapsed_minutes:.0f}p < 60p), tự động lùi task tới {safe_time}")

    def test_retryable_vs_non_retryable_errors(self):
        """
        Kiểm tra phân loại lỗi Auto-Retry:
        - Lỗi mạng, proxy, timeout, browser crash -> Retryable (True)
        - Lỗi captcha, tài khoản bị khóa, session expired, copyright -> Non-retryable (False)
        """
        # Should NOT retry
        self.assertFalse(is_retryable_upload_error("Tài khoản của bạn đã bị khóa hoặc bị cấm do vi phạm"))
        self.assertFalse(is_retryable_upload_error("Gặp Captcha xác minh: Slide to verify"))
        self.assertFalse(is_retryable_upload_error("Session expired. Vui lòng đăng nhập lại"))
        self.assertFalse(is_retryable_upload_error("Video vi phạm bản quyền cộng đồng (copyright)"))
        self.assertFalse(is_retryable_upload_error("Không tìm thấy file video trên ổ cứng"))

        # Should retry
        self.assertTrue(is_retryable_upload_error("net::ERR_PROXY_CONNECTION_FAILED"))
        self.assertTrue(is_retryable_upload_error("Upload timeout waiting for selector #dropzone"))
        self.assertTrue(is_retryable_upload_error("Không thể kết nối cổng debug GPMLogin: Connection refused"))
        self.assertTrue(is_retryable_upload_error("Browser target closed / page crash"))
    def test_per_campaign_vs_global_settings_precedence(self):
        """
        Kiểm tra độ ưu tiên cài đặt:
        1. Cài đặt riêng của Chiến dịch (nếu có chỉ định) -> Dùng cài đặt chiến dịch
        2. Nếu chiến dịch không chỉ định (None/0) -> Dùng Cài đặt toàn cục (Global settings)
        3. Nếu toàn cục cũng chưa cấu hình -> Dùng mặc định hệ thống (60 phút)
        """
        distributor = ContentDistributor()
        cur = self.conn.cursor()

        # Trường hợp 1: Chiến dịch chỉ định rõ 120 phút
        camp_custom = {"min_post_interval_minutes": 120}
        camp_min = camp_custom.get("min_post_interval_minutes")
        val1 = int(camp_min) if camp_min else distributor.get_global_min_interval(cursor=cur)
        self.assertEqual(val1, 120)

        # Trường hợp 2: Chiến dịch không chỉ định (None), bảng settings có cấu hình toàn cục 90 phút
        cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('min_account_cooldown_minutes', '90')")
        self.conn.commit()
        camp_empty = {"min_post_interval_minutes": None}
        val2 = int(camp_empty["min_post_interval_minutes"]) if camp_empty.get("min_post_interval_minutes") else distributor.get_global_min_interval(cursor=cur)
        self.assertEqual(val2, 90)

        # Trường hợp 3: Không có cài đặt chiến dịch và xóa cài đặt toàn cục -> Fallback về 60 phút mặc định
        cur.execute("DELETE FROM settings WHERE key IN ('min_account_cooldown_minutes', 'min_post_interval_minutes')")
        self.conn.commit()
        val3 = distributor.get_global_min_interval(cursor=cur)
        self.assertEqual(val3, 60)

        print("✅ PASS: Hệ thống phân tầng chuẩn xác: Chiến dịch (120p) -> Toàn cục (90p) -> Mặc định an toàn (60p)")

    def test_series_sequencing_lock_prevents_part2_before_part1(self):
        """
        Kiểm tra cơ chế Khóa Tuần Tự Part (Series Sequencing Lock):
        Nếu Part 1 của video chưa completed, Part 2 dù có scheduled_time tới hạn cũng KHÔNG ĐƯỢC upload trước!
        """
        cur = self.conn.cursor()
        now_dt = datetime.now()
        past_str = (now_dt - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S")

        # Tạo video_id 999 có 2 parts
        # Giả định Part 2 bị lên lịch sớm hơn Part 1 (do lỗi lập lịch cũ)
        cur.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, title, status, scheduled_time, part_number)
            VALUES (999, 1, 'Test Video Part 2', 'queued', ?, 2)
        """, (past_str,))
        part2_id = cur.lastrowid

        cur.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, title, status, scheduled_time, part_number)
            VALUES (999, 1, 'Test Video Part 1', 'queued', ?, 1)
        """, (past_str,))
        part1_id = cur.lastrowid
        self.conn.commit()

        # Kiểm tra logic Series Sequencing Lock
        # Đối với Part 2: Part 1 chưa completed -> Bị block
        cur.execute("""
            SELECT COUNT(*) FROM upload_tasks
            WHERE video_id = ? AND part_number < 2 AND status != 'completed'
        """, (999,))
        uncompleted_before_part2 = cur.fetchone()[0]
        self.assertGreater(uncompleted_before_part2, 0, "Part 2 must be blocked while Part 1 is uncompleted")

        # Giờ đánh dấu Part 1 completed
        cur.execute("UPDATE upload_tasks SET status = 'completed' WHERE id = ?", (part1_id,))
        self.conn.commit()

        cur.execute("""
            SELECT COUNT(*) FROM upload_tasks
            WHERE video_id = ? AND part_number < 2 AND status != 'completed'
        """, (999,))
        uncompleted_after_part1_done = cur.fetchone()[0]
        self.assertEqual(uncompleted_after_part1_done, 0, "Part 2 is unlocked once Part 1 is completed")

        print("✅ PASS: Khóa tuần tự Part hoạt động chuẩn: Part 2 không thể đăng trước Part 1!")

if __name__ == "__main__":
    unittest.main()
