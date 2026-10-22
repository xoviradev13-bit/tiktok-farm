from typing import Dict, Any, Optional
from datetime import datetime
from backend.database import get_connection, log_event

class AccountHealthManager:
    """
    Quản lý sức khỏe tài khoản TikTok:
    - Nhận diện các trạng thái: active, unlogged, checkpoint, banned, rate_limited
    - Tự động tạm dừng (pause) các tài khoản có vấn đề, tránh spam retry
    """
    def update_health_status(self, gpm_id: str, status: str, error_reason: str = "") -> Dict[str, Any]:
        valid_statuses = ["active", "unlogged", "checkpoint", "banned", "rate_limited", "paused"]
        if status not in valid_statuses:
            status = "unknown"

        conn = get_connection()
        cursor = conn.cursor()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        cursor.execute('''
        UPDATE gpm_profiles SET
            status = ?,
            last_checked = ?
        WHERE gpm_id = ?
        ''', (status, now_str, gpm_id))

        conn.commit()
        conn.close()

        if status in ["checkpoint", "banned", "unlogged"]:
            log_event("WARNING", f"Tài khoản {gpm_id} chuyển sang trạng thái [{status}]: {error_reason}")

        return {"gpm_id": gpm_id, "status": status, "reason": error_reason}

    def is_account_eligible_to_post(self, gpm_id: str) -> bool:
        """Kiểm tra tài khoản có đang ở trạng thái active để đăng video không"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return False
        return row["status"] == "active"

account_health = AccountHealthManager()
