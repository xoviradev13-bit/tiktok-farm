import json
import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from backend.database import get_connection, log_event, log_campaign_event

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

    def schedule_campaign_upload(
        self,
        video_id: int,
        campaign: Dict[str, Any],
        title: str,
        tags: str
    ) -> Optional[Dict[str, Any]]:
        """
        Gán video đã render vào hàng đợi upload của chiến dịch:
        1. Chống trùng lặp (tránh gán 1 clip nhiều lần)
        2. Chọn profile GPM thích hợp (Round-Robin / Random) chưa vượt daily_limit
        3. Tính toán khung giờ đăng tiếp theo dựa trên post_schedule & random_delay_minutes
        4. Tạo task trong upload_tasks và ghi log chiến dịch
        """
        if self.is_clip_already_assigned(video_id):
            return None

        # 1. Lấy danh sách GPM profiles của chiến dịch
        gpm_ids = []
        try:
            gpm_ids = json.loads(campaign.get("gpm_profile_ids") or "[]")
        except Exception:
            pass
        if not gpm_ids and campaign.get("gpm_profile_id"):
            gpm_ids = [campaign["gpm_profile_id"]]

        if not gpm_ids:
            log_campaign_event(campaign.get("id", 0), "WARNING", "distribute", f"Chiến dịch không có profile GPMLogin nào để phân phối video #{video_id}.")
            return None

        conn = get_connection()
        cursor = conn.cursor()
        placeholders = ",".join("?" for _ in gpm_ids)
        cursor.execute(f"SELECT * FROM gpm_profiles WHERE id IN ({placeholders})", tuple(gpm_ids))
        profiles = [dict(r) for r in cursor.fetchall()]
        conn.close()

        if not profiles:
            return None

        # Sắp xếp hoặc chọn profile
        mode = campaign.get("distribution_mode", "round_robin")
        daily_limit = campaign.get("daily_limit", self.default_daily_limit)

        chosen_profile = None
        if mode == "random":
            random.shuffle(profiles)
            for p in profiles:
                if self.can_account_post_today(p["gpm_id"], max_daily=daily_limit):
                    chosen_profile = p
                    break
        else:
            # Round-Robin: ưu tiên profile có ít video hoàn thành hoặc queued trong ngày hôm nay nhất
            today_prefix = datetime.now().strftime("%Y-%m-%d")
            scored = []
            conn = get_connection()
            cursor = conn.cursor()
            for p in profiles:
                cursor.execute("""
                    SELECT COUNT(*) FROM upload_tasks
                    WHERE gpm_profile_id = ? AND (uploaded_at LIKE ? OR scheduled_time LIKE ?)
                """, (p["id"], f"{today_prefix}%", f"{today_prefix}%"))
                cnt = cursor.fetchone()[0]
                scored.append((cnt, p))
            conn.close()
            scored.sort(key=lambda x: x[0])

            for cnt, p in scored:
                if cnt < daily_limit and self.can_account_post_today(p["gpm_id"], max_daily=daily_limit):
                    chosen_profile = p
                    break

        if not chosen_profile:
            # Nếu tất cả đã chạm giới hạn hôm nay, vẫn gán cho profile ít việc nhất nhưng lên lịch vào ngày mai
            chosen_profile = profiles[0]

        # Tính toán scheduled_time
        schedule_str = campaign.get("post_schedule") or "11:30, 18:00, 20:30"
        random_delay = int(campaign.get("random_delay_minutes") or 10)
        scheduled_time = self._calculate_next_post_time(schedule_str, random_delay)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO upload_tasks (video_id, gpm_profile_id, title, tags, status, scheduled_time)
            VALUES (?, ?, ?, ?, 'queued', ?)
        """, (video_id, chosen_profile["id"], title, tags, scheduled_time))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()

        cid = campaign.get("id", 0)
        pname = chosen_profile.get("name") or chosen_profile.get("gpm_id")
        log_campaign_event(
            cid,
            "SUCCESS",
            "distribute",
            f"Đã lên lịch đăng video #{video_id} cho profile '{pname}' vào lúc {scheduled_time} (Task #{task_id})."
        )

        return {
            "task_id": task_id,
            "profile_id": chosen_profile["id"],
            "profile_name": pname,
            "scheduled_time": scheduled_time
        }

    def _calculate_next_post_time(self, schedule_str: str, random_delay_minutes: int = 10) -> str:
        """Tìm slot giờ đăng tiếp theo gần nhất từ danh sách post_schedule"""
        slots = [s.strip() for s in schedule_str.split(",") if s.strip()]
        now = datetime.now()
        candidates = []

        for s in slots:
            try:
                parts = s.split(":")
                sh, sm = int(parts[0]), int(parts[1])
                t_today = now.replace(hour=sh, minute=sm, second=0, microsecond=0)
                # Thêm độ trễ jitter ngẫu nhiên
                jitter = random.randint(-abs(random_delay_minutes), abs(random_delay_minutes))
                t_today += timedelta(minutes=jitter)

                if t_today > now + timedelta(minutes=5):
                    candidates.append(t_today)
                else:
                    candidates.append(t_today + timedelta(days=1))
            except Exception:
                pass

        if candidates:
            candidates.sort()
            return candidates[0].strftime("%Y-%m-%d %H:%M:%S")

        # Fallback 15 phút tới
        return (now + timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S")

distributor = ContentDistributor()
