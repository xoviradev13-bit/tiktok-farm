import os
import requests
from typing import Optional, List, Dict, Any, Tuple
from backend.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from backend.database import get_connection, log_event

class TelegramNotifier:
    def __init__(self, bot_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def get_bot_token(self) -> str:
        """Lấy Telegram Bot Token mới nhất từ settings DB hoặc .env/config"""
        import backend.config as cfg
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'TELEGRAM_BOT_TOKEN'")
            row = cursor.fetchone()
            conn.close()
            if row and row["value"] and row["value"].strip():
                return row["value"].strip()
        except Exception:
            pass
        return os.getenv("TELEGRAM_BOT_TOKEN", self.bot_token or cfg.TELEGRAM_BOT_TOKEN).strip()

    def get_channels(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Lấy danh sách các kênh Telegram từ DB. Nếu chưa có, fallback về cấu hình mặc định."""
        channels: List[Dict[str, Any]] = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            if active_only:
                cursor.execute(
                    "SELECT id, name, chat_id, is_active, created_at FROM telegram_channels WHERE is_active = 1 ORDER BY id ASC"
                )
            else:
                cursor.execute(
                    "SELECT id, name, chat_id, is_active, created_at FROM telegram_channels ORDER BY id ASC"
                )
            rows = cursor.fetchall()
            conn.close()
            channels = [dict(r) for r in rows]
        except Exception as e:
            log_event("WARNING", f"Lỗi đọc telegram_channels từ DB: {e}")

        # Fallback về TELEGRAM_CHAT_ID cũ nếu bảng telegram_channels hoàn toàn rỗng
        if not channels and not active_only:
            fallback = self.get_fallback_chat_id()
            if fallback:
                channels = [{
                    "id": 0,
                    "name": "Kênh Mặc Định",
                    "chat_id": fallback,
                    "is_active": 1,
                    "created_at": ""
                }]
        elif not channels and active_only:
            # Kiểm tra xem có kênh nào trong bảng không
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) AS cnt FROM telegram_channels")
                total_cnt = cursor.fetchone()["cnt"]
                conn.close()
                if total_cnt == 0:
                    fallback = self.get_fallback_chat_id()
                    if fallback:
                        channels = [{
                            "id": 0,
                            "name": "Kênh Mặc Định",
                            "chat_id": fallback,
                            "is_active": 1,
                            "created_at": ""
                        }]
            except Exception:
                pass

        return channels

    def get_fallback_chat_id(self) -> str:
        """Lấy chat_id từ settings hoặc config làm dự phòng"""
        import backend.config as cfg
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = 'TELEGRAM_CHAT_ID'")
            row = cursor.fetchone()
            conn.close()
            if row and row["value"] and row["value"].strip():
                return row["value"].strip()
        except Exception:
            pass
        return os.getenv("TELEGRAM_CHAT_ID", self.chat_id or cfg.TELEGRAM_CHAT_ID).strip()

    def send_message_to_chat(self, bot_token: str, chat_id: str, text: str) -> Tuple[bool, str]:
        """Gửi 1 tin nhắn Telegram tới chat_id cụ thể"""
        if not bot_token:
            return False, "Chưa cấu hình Telegram Bot Token"
        if not chat_id:
            return False, "Chat ID không hợp lệ hoặc để trống"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            resp = requests.post(url, json=payload, timeout=12)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 200 and data.get("ok"):
                return True, "Thành công"
            else:
                desc = data.get("description", f"HTTP {resp.status_code}: {resp.text[:120]}")
                return False, desc
        except Exception as e:
            return False, str(e)

    def send_message(self, text: str, target_chat_id: Optional[str] = None) -> bool:
        """
        Gửi tin nhắn Telegram.
        - Nếu target_chat_id có giá trị: gửi riêng đến kênh đó.
        - Nếu target_chat_id là None: tự động gửi tới TẤT CẢ các kênh Telegram đang BẬT (active).
        """
        bot_token = self.get_bot_token()
        if not bot_token:
            log_event("WARNING", f"Chưa cấu hình Telegram Bot Token. Không thể gửi thông báo: {text[:60]}...")
            return False

        if target_chat_id:
            ok, msg = self.send_message_to_chat(bot_token, target_chat_id, text)
            if not ok:
                log_event("ERROR", f"Lỗi gửi Telegram (Chat ID: {target_chat_id}): {msg}")
            return ok

        # Gửi tới toàn bộ kênh đang BẬT
        active_channels = self.get_channels(active_only=True)
        if not active_channels:
            log_event("WARNING", "Không có kênh Telegram nào đang BẬT (Active) để gửi cảnh báo.")
            return False

        sent_count = 0
        success_names = []
        fail_details = []

        for ch in active_channels:
            ch_name = ch.get("name") or "Kênh Telegram"
            ch_id = ch.get("chat_id")
            ok, err_msg = self.send_message_to_chat(bot_token, ch_id, text)
            if ok:
                sent_count += 1
                success_names.append(ch_name)
            else:
                fail_details.append(f"{ch_name} ({ch_id}): {err_msg}")

        if success_names:
            log_event("INFO", f"Đã gửi cảnh báo Telegram tới {len(success_names)} kênh: {', '.join(success_names)}")
        if fail_details:
            log_event("WARNING", f"Gửi thất bại tới {len(fail_details)} kênh: {'; '.join(fail_details)}")

        return sent_count > 0

    def send_10k_alert(self, profile_name: str, username: str, followers: int, views: int, target_chat_id: Optional[str] = None) -> bool:
        """Bắn cảnh báo nick đạt 10.000 Follower đủ điều kiện TikTok Beta tới các kênh đang bật"""
        msg = (
            "🚨 *[TIKTOK BETA ALERT] TÀI KHOẢN ĐỦ ĐIỀU KIỆN!*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Tài khoản:* `@{username or 'N/A'}`\n"
            f"🆔 *Profile GPM:* `{profile_name}`\n"
            f"📈 *Followers:* *{followers:,}* / 10,000 ✅\n"
            f"👁️ *Tổng Lượt Xem:* {views:,}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *Hành động:* Hãy vào ngay GPMLogin mở nick này và nộp đơn tham gia Quỹ Sáng Tạo (TikTok Creator Rewards Program)!"
        )
        return self.send_message(msg, target_chat_id=target_chat_id)

    def send_10k_alert_detailed(self, profile_name: str, username: str, followers: int, views: int) -> Dict[str, Any]:
        """Gửi cảnh báo và trả về chi tiết trạng thái từng kênh nhận được hay thất bại"""
        bot_token = self.get_bot_token()
        if not bot_token:
            return {
                "success": False,
                "message": "Chưa cấu hình Telegram Bot Token",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        active_channels = self.get_channels(active_only=True)
        if not active_channels:
            return {
                "success": False,
                "message": "Không có kênh Telegram nào đang BẬT. Vui lòng thêm hoặc bật kênh nhận thông báo.",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        msg = (
            "🚨 *[TIKTOK BETA ALERT] TÀI KHOẢN ĐỦ ĐIỀU KIỆN! (TEST)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Tài khoản:* `@{username or 'N/A'}`\n"
            f"🆔 *Profile GPM:* `{profile_name}`\n"
            f"📈 *Followers:* *{followers:,}* / 10,000 ✅\n"
            f"👁️ *Tổng Lượt Xem:* {views:,}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *Hành động:* Hãy vào ngay GPMLogin mở nick này và nộp đơn tham gia Quỹ Sáng Tạo (TikTok Creator Rewards Program)!"
        )

        results = []
        sent_count = 0
        for ch in active_channels:
            ch_name = ch.get("name") or "Kênh Telegram"
            ch_id = ch.get("chat_id")
            ok, err_msg = self.send_message_to_chat(bot_token, ch_id, msg)
            if ok:
                sent_count += 1
            results.append({
                "id": ch.get("id"),
                "name": ch_name,
                "chat_id": ch_id,
                "success": ok,
                "message": err_msg
            })

        total = len(active_channels)
        return {
            "success": sent_count > 0,
            "sent_count": sent_count,
            "total_active": total,
            "channels": results,
            "message": f"Đã gửi thành công tới {sent_count}/{total} kênh Telegram đang bật"
        }

notifier = TelegramNotifier()
