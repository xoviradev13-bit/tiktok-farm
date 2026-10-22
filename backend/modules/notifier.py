import requests
from typing import Optional
from backend.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from backend.database import log_event

class TelegramNotifier:
    def __init__(self, bot_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> bool:
        """Gửi tin nhắn Telegram"""
        if not self.bot_token or not self.chat_id:
            log_event("WARNING", f"Chưa cấu hình Telegram Token/Chat ID. Nội dung: {text[:50]}...")
            return False

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }

        try:
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200
        except Exception as e:
            log_event("ERROR", f"Lỗi gửi Telegram: {str(e)}")
            return False

    def send_10k_alert(self, profile_name: str, username: str, followers: int, views: int) -> bool:
        """Bắn cảnh báo nick đạt 10.000 Follower đủ điều kiện TikTok Beta"""
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
        return self.send_message(msg)

notifier = TelegramNotifier()
