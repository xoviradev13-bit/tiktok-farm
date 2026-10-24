from typing import Dict, Any, Optional
from datetime import datetime
from backend.database import get_connection, log_event
from backend.logger import get_logger

logger = get_logger("account_health")

class AccountHealthManager:
    """
    Quản lý sức khỏe và trạng thái vận hành của các tài khoản TikTok GPM:
    - active: Bình thường, sẵn sàng đăng bài và quét follower
    - banned: Tài khoản bị khóa / đình chỉ vĩnh viễn bởi TikTok
    - restricted: Tài khoản bị hạn chế tạm thời (chặn đăng video / cảnh cáo vi phạm)
    - checkpoint: Bị yêu cầu giải Captcha / trượt hình xác minh
    - unlogged: Chưa đăng nhập hoặc phiên sessionid đã hết hạn
    - rate_limited: Bị TikTok giới hạn tần suất (đăng quá nhanh / đạt limit ngày)
    - proxy_dead: Proxy của profile bị chết, không tải được trang TikTok
    - paused: Tạm dừng thủ công bởi người dùng
    """

    VALID_STATUSES = [
        "active", "banned", "restricted", "checkpoint", 
        "unlogged", "rate_limited", "proxy_dead", "paused"
    ]

    def update_health_status(self, gpm_id: str, status: str, error_reason: str = "") -> Dict[str, Any]:
        """Cập nhật trạng thái sức khỏe tài khoản vào database và ghi nhật ký cảnh báo"""
        status = status.lower()
        if status not in self.VALID_STATUSES:
            status = "unknown"

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute('''
            UPDATE gpm_profiles SET
                status = ?,
                status_reason = ?,
                last_checked = ?
            WHERE gpm_id = ?
            ''', (status, error_reason, now_str, gpm_id))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Lỗi cập nhật trạng thái profile {gpm_id} vào DB: {e}")

        # Ghi log cảnh báo tùy theo mức độ nghiêm trọng
        if status in ["banned", "restricted"]:
            log_event("ERROR", f"🚨 [TIKTOK {status.upper()}] Tài khoản {gpm_id}: {error_reason}")
            logger.error(f"[TIKTOK HEALTH] {gpm_id} -> {status.upper()}: {error_reason}")
        elif status in ["checkpoint", "unlogged", "proxy_dead", "rate_limited"]:
            log_event("WARNING", f"⚠️ [TIKTOK {status.upper()}] Tài khoản {gpm_id}: {error_reason}")
            logger.warning(f"[TIKTOK HEALTH] {gpm_id} -> {status.upper()}: {error_reason}")
        elif status == "active":
            logger.debug(f"[TIKTOK HEALTH] {gpm_id} -> ACTIVE")

        return {"gpm_id": gpm_id, "status": status, "reason": error_reason}

    def check_page_account_health(self, page, gpm_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Kiểm tra trực tiếp trang web TikTok qua Playwright để phát hiện các dấu hiệu:
        banned, restricted, unlogged, captcha checkpoint, hoặc lỗi proxy.
        """
        if not page:
            return {"healthy": False, "status": "unknown", "reason": "Page không tồn tại"}

        try:
            current_url = page.url.lower()

            # 1. Kiểm tra qua URL
            if "/login" in current_url or "/signup" in current_url:
                res = {"healthy": False, "status": "unlogged", "reason": "Tài khoản chưa đăng nhập TikTok hoặc phiên đăng nhập đã hết hạn"}
                if gpm_id:
                    self.update_health_status(gpm_id, res["status"], res["reason"])
                return res

            if "/banned" in current_url or "/punishment" in current_url:
                res = {"healthy": False, "status": "banned", "reason": "Tài khoản đã bị đình chỉ / cấm vĩnh viễn trên TikTok"}
                if gpm_id:
                    self.update_health_status(gpm_id, res["status"], res["reason"])
                return res

            # 2. Quét DOM bằng JavaScript để tìm thông điệp cảnh báo
            health_check_js = """
                () => {
                    const text = document.body ? document.body.innerText.toLowerCase() : "";
                    const html = document.documentElement ? document.documentElement.innerHTML.toLowerCase() : "";

                    // Kiểm tra Banned
                    const bannedKws = [
                        "your account has been suspended",
                        "account suspended",
                        "tài khoản của bạn đã bị đình chỉ",
                        "tài khoản bị đình chỉ",
                        "tài khoản đã bị cấm vĩnh viễn",
                        "tài khoản bị cấm",
                        "permanently banned"
                    ];
                    for (const kw of bannedKws) {
                        if (text.includes(kw)) {
                            return { found: true, status: "banned", reason: "Tài khoản bị đình chỉ / cấm vĩnh viễn trên TikTok" };
                        }
                    }

                    // Kiểm tra Hạn chế (Restricted)
                    const restrictedKws = [
                        "your account was temporarily blocked",
                        "tài khoản bị tạm khóa",
                        "tài khoản bị hạn chế",
                        "bạn tạm thời bị chặn",
                        "temporarily restricted",
                        "account restricted",
                        "bị chặn đăng"
                    ];
                    for (const kw of restrictedKws) {
                        if (text.includes(kw)) {
                            return { found: true, status: "restricted", reason: "Tài khoản bị hạn chế tính năng / tạm khóa đăng video" };
                        }
                    }

                    // Kiểm tra Captcha / Checkpoint
                    const hasCaptchaEl = document.querySelector("#captcha-verify-image") ||
                                         document.querySelector(".secsdk-captcha-drag-wrapper") ||
                                         document.querySelector("[data-e2e='secsdk-captcha']");
                    if (hasCaptchaEl || text.includes("trượt để hoàn thành") || text.includes("slide to complete the puzzle") || text.includes("verify to continue")) {
                        return { found: true, status: "checkpoint", reason: "TikTok yêu cầu giải Captcha xác minh" };
                    }

                    // Kiểm tra Rate limit / Daily limit
                    if (text.includes("you are posting too fast") || text.includes("đăng bài quá thường xuyên") || text.includes("đạt giới hạn")) {
                        return { found: true, status: "rate_limited", reason: "TikTok giới hạn tần suất đăng bài (quá nhanh hoặc đạt limit ngày)" };
                    }

                    // Kiểm tra lỗi mạng / Proxy
                    if (text.includes("err_proxy_connection_failed") || text.includes("err_tunnel_connection_failed") || text.includes("err_connection_refused")) {
                        return { found: true, status: "proxy_dead", reason: "Proxy không thể kết nối tới TikTok (Proxy chết hoặc timeout)" };
                    }

                    return { found: false, status: "active", reason: "" };
                }
            """
            eval_res = page.evaluate(health_check_js)
            if eval_res and eval_res.get("found"):
                status = eval_res.get("status", "unknown")
                reason = eval_res.get("reason", "")
                if gpm_id:
                    self.update_health_status(gpm_id, status, reason)
                return {"healthy": False, "status": status, "reason": reason}

            return {"healthy": True, "status": "active", "reason": ""}

        except Exception as e:
            logger.warning(f"Lỗi khi kiểm tra sức khỏe trang TikTok: {e}")
            return {"healthy": True, "status": "active", "reason": f"Không thể kiểm tra DOM: {e}"}

    def is_account_eligible_to_post(self, gpm_id: str) -> bool:
        """Kiểm tra tài khoản có đang ở trạng thái active để được phép đăng video không"""
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT status, status_reason FROM gpm_profiles WHERE gpm_id = ?", (gpm_id,))
            row = cursor.fetchone()
            conn.close()

            if not row:
                return False
            # Chỉ cho phép đăng nếu status là active
            return row["status"] in ("active", "", None)
        except Exception:
            return True

account_health = AccountHealthManager()
