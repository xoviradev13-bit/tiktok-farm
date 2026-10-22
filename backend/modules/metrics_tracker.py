from datetime import datetime
from typing import Dict, Any, List
from backend.database import get_connection, log_event
from backend.modules.notifier import notifier

class MetricsTracker:
    def update_profile_stats(
        self,
        gpm_id: str,
        followers: int,
        total_views: int,
        username: str = "",
        min_followers_threshold: int = 10000,
        min_views_threshold: int = 100000,
        require_views: bool = False
    ) -> Dict[str, Any]:
        """
        Cập nhật số follower & view cho profile. 
        Nếu đạt >= ngưỡng cấu hình (Mặc định 10.000 Follower & tùy chọn 100.000 views)
        -> Tự động kích hoạt thông báo Telegram
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # Kiểm tra trạng thái cũ
        cursor.execute("SELECT name, followers_count, eligible_10k FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
        row = cursor.fetchone()
        
        old_eligible = row["eligible_10k"] if row else 0
        profile_name = row["name"] if row else gpm_id
        
        # Kiểm tra điều kiện Creator Rewards (Follower + Views)
        meets_followers = followers >= min_followers_threshold
        meets_views = (total_views >= min_views_threshold) if require_views else True
        new_eligible = 1 if (meets_followers and meets_views) else 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute('''
        UPDATE gpm_profiles SET
            followers_count = ?,
            total_views = ?,
            tiktok_username = COALESCE(NULLIF(?, ''), tiktok_username),
            eligible_10k = ?,
            last_checked = ?
        WHERE gpm_id = ?
        ''', (followers, total_views, username, new_eligible, now_str, gpm_id))
        conn.commit()
        conn.close()

        # Nếu vừa mới cán mốc 10.000 Follower lần đầu -> Bắn tin nhắn
        if new_eligible == 1 and old_eligible == 0:
            log_event("INFO", f"🎉 Tài khoản {profile_name} đã cán mốc {followers} followers! Gửi cảnh báo Telegram...")
            notifier.send_10k_alert(profile_name, username, followers, total_views)

        return {
            "gpm_id": gpm_id,
            "followers": followers,
            "eligible_10k": bool(new_eligible)
        }

    def get_all_eligible_profiles(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các nick đã đủ 10k Follower"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles WHERE eligible_10k = 1 ORDER BY followers_count DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

metrics_tracker = MetricsTracker()
