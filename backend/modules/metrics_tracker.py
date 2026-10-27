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
        nickname: str = "",
        tiktok_uid: str = "",
        sec_uid: str = "",
        min_followers_threshold: int = 10000,
        min_views_threshold: int = 100000,
        require_views: bool = False
    ) -> Dict[str, Any]:
        """
        Cập nhật số follower, view, username, nickname, tiktok_uid & sec_uid cho profile. 
        Nếu phát hiện cùng tiktok_uid đăng nhập trên profile khác -> Tự động chuyển giao (migrate)
        và cập nhật chính xác tài khoản.
        """
        conn = get_connection()
        cursor = conn.cursor()
        
        # Kiểm tra trạng thái cũ
        cursor.execute("SELECT name, followers_count, eligible_10k, COALESCE(notify_status, 'tracking') AS notify_status FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
        row = cursor.fetchone()
        
        old_eligible = row["eligible_10k"] if row else 0
        profile_name = row["name"] if row else gpm_id
        current_notify_status = (row["notify_status"] if row and row["notify_status"] else "tracking").lower()
        
        # Làm sạch username, nickname, tiktok_uid & sec_uid
        clean_user = (username or "").strip().lstrip("@")
        clean_nick = (nickname or "").strip()
        clean_uid = (tiktok_uid or "").strip()
        clean_sec = (sec_uid or "").strip()

        # NẾU CÓ TIKTOK_UID HOẶC SEC_UID: Kiểm tra xem tài khoản này trước đó có gắn với profile GPM nào khác không
        other_profiles = []
        if clean_uid:
            cursor.execute("SELECT gpm_id, name FROM gpm_profiles WHERE tiktok_uid = ? AND gpm_id != ?", (clean_uid, gpm_id))
            other_profiles = cursor.fetchall()
        elif clean_sec:
            cursor.execute("SELECT gpm_id, name FROM gpm_profiles WHERE sec_uid = ? AND gpm_id != ?", (clean_sec, gpm_id))
            other_profiles = cursor.fetchall()

        for other in other_profiles:
            cursor.execute("""
                UPDATE gpm_profiles 
                SET tiktok_username = '', tiktok_nickname = '', tiktok_uid = '', sec_uid = '',
                    status = 'unlogged', status_reason = 'Tài khoản TikTok đã chuyển sang profile ' || ?
                WHERE gpm_id = ?
            """, (profile_name, other["gpm_id"]))
            log_event("INFO", f"🔄 [MIGRATE ACCOUNT] TikTok {clean_uid or clean_sec} (@{clean_user}) đã chuyển từ profile '{other['name']}' sang '{profile_name}'")

        # Kiểm tra điều kiện Creator Rewards (Follower + Views)
        meets_followers = followers >= min_followers_threshold
        meets_views = (total_views >= min_views_threshold) if require_views else True
        new_eligible = 1 if (meets_followers and meets_views) else 0
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Xác định trạng thái thông báo Telegram
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
            tiktok_nickname = COALESCE(NULLIF(?, ''), tiktok_nickname),
            tiktok_uid = COALESCE(NULLIF(?, ''), tiktok_uid),
            sec_uid = COALESCE(NULLIF(?, ''), sec_uid),
            eligible_10k = ?,
            notify_status = ?,
            last_checked = ?
        WHERE gpm_id = ?
        ''', (followers, total_views, clean_user, clean_nick, clean_uid, clean_sec, new_eligible, new_notify_status, now_str, gpm_id))
        conn.commit()
        conn.close()

        # Bắn thông báo Telegram khi đạt điều kiện theo dõi
        if should_send_alert:
            log_event("INFO", f"🎉 Tài khoản {profile_name} đã cán mốc {followers:,} followers! Gửi cảnh báo Telegram...")
            notifier.send_10k_alert(profile_name, clean_user, followers, total_views)

        return {
            "gpm_id": gpm_id,
            "followers": followers,
            "username": clean_user,
            "nickname": clean_nick,
            "tiktok_uid": clean_uid,
            "sec_uid": clean_sec,
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
