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
        cursor.execute("SELECT name, followers_count, eligible_10k, COALESCE(notify_status, 'tracking') AS notify_status FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
        row = cursor.fetchone()
        
        old_eligible = row["eligible_10k"] if row else 0
        profile_name = row["name"] if row else gpm_id
        current_notify_status = (row["notify_status"] if row and row["notify_status"] else "tracking").lower()
        
        # Kiểm tra điều kiện Creator Rewards (Follower + Views)
        meets_followers = followers >= min_followers_threshold
        meets_views = (total_views >= min_views_threshold) if require_views else True
        new_eligible = 1 if (meets_followers and meets_views) else 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Xác định trạng thái thông báo Telegram:
        # - 'tracking' (Đang theo dõi): Khi đạt ngưỡng 10k -> Bắn thông báo Telegram & chuyển sang 'sent'
        # - 'sent' (Đã gửi): Đã gửi rồi, không gửi lại nữa (trừ khi người dùng chủ động đổi về 'tracking')
        # - 'muted' (Bỏ theo dõi): Không gửi thông báo dù vượt ngưỡng 10k
        new_notify_status = current_notify_status
        should_send_alert = False

        if new_eligible == 1 and current_notify_status == 'tracking':
            should_send_alert = True
            new_notify_status = 'sent'

        cursor.execute('''
        UPDATE gpm_profiles SET
            followers_count = ?,
            total_views = ?,
            tiktok_username = COALESCE(NULLIF(?, ''), tiktok_username),
            eligible_10k = ?,
            notify_status = ?,
            last_checked = ?
        WHERE gpm_id = ?
        ''', (followers, total_views, username, new_eligible, new_notify_status, now_str, gpm_id))
        conn.commit()
        conn.close()

        # Bắn thông báo Telegram khi đạt điều kiện theo dõi
        if should_send_alert:
            log_event("INFO", f"🎉 Tài khoản {profile_name} đã cán mốc {followers:,} followers! Gửi cảnh báo Telegram...")
            notifier.send_10k_alert(profile_name, username, followers, total_views)

        return {
            "gpm_id": gpm_id,
            "followers": followers,
            "eligible_10k": bool(new_eligible),
            "notify_status": new_notify_status
        }

    def update_notify_status(self, gpm_id: str, status: str) -> bool:
        """Cập nhật trạng thái theo dõi thông báo 10K cho profile ('tracking', 'sent', 'muted')"""
        status_clean = (status or "").strip().lower()
        if status_clean not in ("tracking", "sent", "muted"):
            return False
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE gpm_profiles SET notify_status = ? WHERE gpm_id = ?", (status_clean, gpm_id))
        conn.commit()
        conn.close()
        return True

    def get_all_eligible_profiles(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các nick đã đủ 10k Follower"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM gpm_profiles WHERE eligible_10k = 1 ORDER BY followers_count DESC")
        rows = cursor.fetchall()
        conn.close()
        return [dict(r) for r in rows]

metrics_tracker = MetricsTracker()
