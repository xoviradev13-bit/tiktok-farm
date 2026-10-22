import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_connection, log_event

class ContentDistributor:
    """
    Phân phối nội dung theo tài khoản:
    - Gán kênh nguồn cho nhóm tài khoản
    - Chống đăng trùng: mỗi clip chỉ gán cho 1 tài khoản duy nhất
    - Giới hạn số video mỗi ngày (daily cap) & giờ đăng ngẫu nhiên
    - Hỗ trợ làm nóng tài khoản mới (warm-up pacing)
    """
    def __init__(self, default_daily_limit: int = 2):
        self.default_daily_limit = default_daily_limit

    def can_account_post_today(self, gpm_id: str, max_daily: Optional[int] = None) -> bool:
        """Kiểm tra tài khoản đã đạt giới hạn video trong ngày chưa"""
        limit = max_daily or self.default_daily_limit
        today_prefix = datetime.now().strftime("%Y-%m-%d")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
        SELECT COUNT(*) FROM upload_tasks ut
        JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
        WHERE gp.gpm_id = ? AND ut.status = 'completed' AND ut.uploaded_at LIKE ?
        ''', (gpm_id, f"{today_prefix}%"))
        count = cursor.fetchone()[0]
        conn.close()

        return count < limit

    def is_clip_already_assigned(self, video_id: int) -> bool:
        """Kiểm tra clip này đã từng được gán hoặc đăng bởi tài khoản nào chưa"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM upload_tasks WHERE video_id = ?", (video_id,))
        row = cursor.fetchone()
        conn.close()
        return row is not None

    def generate_random_schedule_time(self, start_hour: int = 9, end_hour: int = 22) -> str:
        """Tạo thời gian đăng ngẫu nhiên trong khung giờ quy định"""
        now = datetime.now()
        target_hour = random.randint(start_hour, end_hour)
        target_minute = random.randint(0, 59)
        scheduled = now.replace(hour=target_hour, minute=target_minute, second=0)

        # Nếu giờ đã qua trong ngày -> Lên lịch cho ngày mai
        if scheduled <= now:
            scheduled += timedelta(days=1)

        return scheduled.strftime("%Y-%m-%d %H:%M:%S")

distributor = ContentDistributor()
