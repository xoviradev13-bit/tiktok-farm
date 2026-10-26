import os
import time
import requests
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from backend.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from backend.database import get_connection, log_event

class TelegramNotifier:
    def __init__(self, bot_token: str = TELEGRAM_BOT_TOKEN, chat_id: str = TELEGRAM_CHAT_ID):
        self.bot_token = bot_token
        self.chat_id = chat_id
        # Lưu vết các cảnh báo sự cố đã gửi gần đây để chống spam lặp lại (cooldown 30 phút)
        self._recent_issue_alerts: Dict[str, float] = {}

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

    def get_channels(self, active_only: bool = True, notification_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lấy danh sách các kênh Telegram từ DB.
        notification_type:
            - None: tất cả kênh
            - '10k': kênh có bật notify_10k = 1
            - 'issues': kênh có bật notify_issues = 1
            - 'daily_report': kênh có bật notify_daily_report = 1
        """
        channels: List[Dict[str, Any]] = []
        try:
            conn = get_connection()
            cursor = conn.cursor()
            
            query = "SELECT id, name, chat_id, is_active, notify_10k, notify_issues, notify_daily_report, daily_report_time, last_daily_report, created_at FROM telegram_channels"
            conditions = []
            if active_only:
                conditions.append("is_active = 1")
            
            if notification_type == "10k":
                conditions.append("notify_10k = 1")
            elif notification_type == "issues":
                conditions.append("notify_issues = 1")
            elif notification_type == "daily_report":
                conditions.append("notify_daily_report = 1")

            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            
            query += " ORDER BY id ASC"
            cursor.execute(query)
            rows = cursor.fetchall()
            conn.close()
            channels = [dict(r) for r in rows]
        except Exception as e:
            log_event("WARNING", f"Lỗi đọc telegram_channels từ DB: {e}")

        # Fallback về TELEGRAM_CHAT_ID cũ nếu bảng telegram_channels hoàn toàn rỗng
        if not channels:
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
                            "notify_10k": 1,
                            "notify_issues": 1,
                            "notify_daily_report": 1,
                            "daily_report_time": "21:00",
                            "last_daily_report": "",
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
        """Gửi 1 tin nhắn Telegram tới chat_id cụ thể qua HTTP POST"""
        if not bot_token:
            return False, "Chưa cấu hình Telegram Bot Token"
        if not chat_id:
            return False, "Chat ID không hợp lệ hoặc để trống"

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }

        try:
            resp = requests.post(url, json=payload, timeout=15)
            data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
            if resp.status_code == 200 and data.get("ok"):
                return True, "Thành công"
            else:
                desc = data.get("description", f"HTTP {resp.status_code}: {resp.text[:120]}")
                # Nếu lỗi Markdown parse, thử gửi lại với text thường (không parse_mode)
                if "can't parse entities" in desc.lower() or "markdown" in desc.lower():
                    plain_payload = {
                        "chat_id": chat_id,
                        "text": text.replace("*", "").replace("`", "").replace("_", ""),
                        "disable_web_page_preview": True
                    }
                    retry_resp = requests.post(url, json=plain_payload, timeout=12)
                    retry_data = retry_resp.json() if retry_resp.headers.get("content-type", "").startswith("application/json") else {}
                    if retry_resp.status_code == 200 and retry_data.get("ok"):
                        return True, "Thành công (fallback text thuần)"
                return False, desc
        except Exception as e:
            return False, str(e)

    def send_message(self, text: str, target_chat_id: Optional[str] = None, notification_type: Optional[str] = None) -> bool:
        """
        Gửi tin nhắn Telegram.
        - Nếu target_chat_id có giá trị: gửi riêng đến kênh đó.
        - Nếu target_chat_id là None: tự động gửi tới TẤT CẢ các kênh phù hợp với notification_type đang BẬT.
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

        # Gửi tới các kênh đang BẬT thỏa mãn notification_type
        active_channels = self.get_channels(active_only=True, notification_type=notification_type)
        if not active_channels:
            type_label = f"[{notification_type}] " if notification_type else ""
            log_event("INFO", f"Không có kênh Telegram nào đang BẬT nhận thông báo {type_label}để gửi tin.")
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
            log_event("INFO", f"Đã gửi Telegram ({notification_type or 'all'}) tới {len(success_names)} kênh: {', '.join(success_names)}")
        if fail_details:
            log_event("WARNING", f"Gửi Telegram thất bại tới {len(fail_details)} kênh: {'; '.join(fail_details)}")

        return sent_count > 0

    # =========================================================================
    # 1. THÔNG BÁO NICK ĐẠT 10.000 FOLLOWER
    # =========================================================================
    def send_10k_alert(self, profile_name: str, username: str, followers: int, views: int = 0, target_chat_id: Optional[str] = None) -> bool:
        """Bắn cảnh báo nick đạt 10.000 Follower đủ điều kiện TikTok Beta tới các kênh nhận notify_10k"""
        now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "🚨 *[TIKTOK BETA ALERT] TÀI KHOẢN ĐỦ ĐIỀU KIỆN!*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Tài khoản:* `@{username or 'N/A'}`\n"
            f"🆔 *Profile GPM:* `{profile_name}`\n"
            f"📈 *Followers:* *{followers:,}* / 10,000 ✅\n"
            f"⏰ *Thời điểm đạt:* `{now_str}`\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "👉 *Hành động ngay:*\n"
            "1. Mở phần mềm GPMLogin và bật profile này.\n"
            "2. Truy cập TikTok Studio / Creator Rewards Program.\n"
            "3. Bấm **Nộp Đơn (Apply)** để kích hoạt tính năng kiếm tiền Beta!"
        )
        return self.send_message(msg, target_chat_id=target_chat_id, notification_type="10k")

    def send_10k_alert_detailed(self, profile_name: str, username: str, followers: int, views: int = 0, target_chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Gửi cảnh báo và trả về chi tiết từng kênh thành công/thất bại (Dùng cho test alert)"""
        bot_token = self.get_bot_token()
        if not bot_token:
            return {
                "success": False,
                "message": "Chưa cấu hình Telegram Bot Token",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        if target_chat_id:
            active_channels = [{"id": 0, "name": "Kênh Đã Chọn", "chat_id": target_chat_id}]
        else:
            active_channels = self.get_channels(active_only=True, notification_type="10k")

        if not active_channels:
            return {
                "success": False,
                "message": "Không có kênh Telegram nào đang BẬT tùy chọn nhận 'Cảnh báo 10K Follower'.",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
        msg = (
            "🚨 *[TIKTOK BETA ALERT] TÀI KHOẢN ĐỦ ĐIỀU KIỆN! (TEST)*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"👤 *Tài khoản:* `@{username or 'demo_user'}`\n"
            f"🆔 *Profile GPM:* `{profile_name}`\n"
            f"📈 *Followers:* *{followers:,}* / 10,000 ✅\n"
            f"⏰ *Thời điểm:* `{now_str}`\n"
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
            "message": f"Đã gửi cảnh báo 10K tới {sent_count}/{total} kênh Telegram đang bật nhận loại tin này."
        }

    # =========================================================================
    # 2. CẢNH BÁO SỰ CỐ NGHIÊM TRỌNG + HƯỚNG DẪN KHẮC PHỤC (ISSUE ALERT + FIX)
    # =========================================================================
    def get_solution_for_error(self, error_msg: str, category: str = "general") -> str:
        """Tự động phân tích thông điệp lỗi và đưa ra hướng dẫn khắc phục chi tiết, cụ thể"""
        e = (error_msg or "").lower()

        # 1. GPMLogin không kết nối được
        if "cổng debug gpm" in e or "gpm" in e and ("kết nối" in e or "port" in e or "refused" in e or "connect" in e):
            return (
                "1️⃣ Mở phần mềm **GPMLogin** trên máy tính (đảm bảo ứng dụng đang chạy).\n"
                "2️⃣ Vào **Cài Đặt GPMLogin** → Đảm bảo **Local API** đang bật (Port 9495 hoặc 19995).\n"
                "3️⃣ Nhấn nút 'Check Proxy' trong GPMLogin của profile xem proxy còn sống không."
            )

        # 2. Proxy chết / lỗi mạng
        if "proxy" in e or "err_proxy" in e or "proxyconnectionfailed" in e or "tunnel" in e:
            return (
                "1️⃣ Proxy gắn với Profile này đã bị mất kết nối hoặc hết hạn băng thông.\n"
                "2️⃣ Vào GPMLogin → Click chuột phải vào Profile → Chỉnh sửa Proxy mới (SOCKS5/HTTP).\n"
                "3️⃣ Kiểm tra IP mạng hoặc gia hạn gói Proxy."
            )

        # 3. Phiên đăng nhập TikTok hết hạn / Cần đăng nhập lại
        if "hết phiên" in e or "login" in e or "đăng nhập" in e or "session" in e or "authenticate" in e:
            return (
                "1️⃣ Mở Profile GPMLogin này bằng tay trên máy.\n"
                "2️⃣ Truy cập `tiktok.com` xem nick có bị văng đăng xuất hoặc bắt xác minh Captcha/OTP không.\n"
                "3️⃣ Tiến hành đăng nhập lại thủ công và chọn 'Lưu phiên đăng nhập'."
            )

        # 4. Thiếu thư viện Playwright
        if "playwright" in e:
            return (
                "1️⃣ Mở Terminal (PowerShell hoặc CMD).\n"
                "2️⃣ Chạy lệnh: `pip install playwright`\n"
                "3️⃣ Chạy tiếp: `playwright install chromium` rồi khởi động lại app."
            )

        # 5. FFmpeg chưa cài hoặc lỗi render
        if "ffmpeg" in e:
            return (
                "1️⃣ Chạy lệnh: `pip install imageio[ffmpeg]` trong PowerShell.\n"
                "2️⃣ Hoặc tải FFmpeg từ ffmpeg.org và thêm vào biến môi trường Windows PATH.\n"
                "3️⃣ Kiểm tra xem phần mềm diệt virus có chặn file `ffmpeg.exe` không."
            )

        # 6. Hết dung lượng ổ cứng
        if "disk" in e or "space" in e or "đầy" in e or "no space" in e:
            return (
                "1️⃣ Ổ cứng chứa dữ liệu data/render của ứng dụng sắp đầy (< 2GB).\n"
                "2️⃣ Vào tab **Cài Đặt** → Chọn **Dọn Dẹp File Tự Động** hoặc xóa các file MP4 cũ trong thư mục `rendered/`."
            )

        # 7. Quota hoặc API Key YouTube / AI
        if "quota" in e or "api key" in e or "403" in e or "unauthorized" in e or "credit" in e:
            return (
                "1️⃣ Hạn mức API Key (YouTube Data API hoặc OpenAI/DeepSeek) đã đạt trần hoặc hết số dư.\n"
                "2️⃣ Vào tab **Cài Đặt** → Cập nhật API Key mới hoặc thêm nhiều Key YouTube cách nhau bằng dấu phẩy.\n"
                "3️⃣ Hạn mức YouTube sẽ tự reset vào lúc 14:00 hàng ngày (giờ VN)."
            )

        # 8. Mặc định
        return (
            "1️⃣ Mở tab **Nhật Ký & Chẩn Đoán Hệ Thống** trên thanh điều hướng để xem chi tiết log lỗi.\n"
            "2️⃣ Kiểm tra đường truyền Internet và trạng thái tài khoản trên GPMLogin.\n"
            "3️⃣ Khởi động lại ứng dụng nếu lỗi tiếp tục tái diễn."
        )

    def send_issue_alert(
        self,
        title: str,
        message: str,
        solution: str = "",
        severity: str = "ERROR",
        details: str = "",
        target_chat_id: Optional[str] = None,
        force: bool = False
    ) -> bool:
        """
        Bắn cảnh báo lỗi nghiêm trọng kèm cách xử lý tới các kênh có bật notify_issues.
        Có cơ chế chống spam (cooldown 30 phút cho cùng một lỗi).
        """
        issue_key = f"{title}_{message[:60]}"
        now = time.time()
        if not force and issue_key in self._recent_issue_alerts:
            if now - self._recent_issue_alerts[issue_key] < 1800:
                # Đang trong cooldown 30 phút, không spam lại
                return False

        self._recent_issue_alerts[issue_key] = now
        # Dọn dẹp cache cũ hơn 2 giờ
        self._recent_issue_alerts = {k: v for k, v in self._recent_issue_alerts.items() if now - v < 7200}

        if not solution:
            solution = self.get_solution_for_error(f"{title} {message} {details}")

        now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
        severity_tag = "🔴 [NGHIÊM TRỌNG]" if severity.upper() in ("CRITICAL", "ERROR", "HIGH") else "🟡 [CẢNH BÁO]"

        text = (
            f"🚨 *[HỆ THỐNG CẢNH BÁO SỰ CỐ]* {severity_tag}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *Sự cố:* *{title}*\n"
            f"📝 *Mô tả lỗi:* `{message}`\n"
        )
        if details:
            text += f"🔍 *Chi tiết ngữ cảnh:* `{details}`\n"
        text += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *HƯỚNG DẪN KHẮC PHỤC (ACTION PLAN):*\n"
            f"{solution}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ *Thời điểm:* `{now_str}`"
        )

        return self.send_message(text, target_chat_id=target_chat_id, notification_type="issues")

    def send_issue_alert_detailed(
        self,
        title: str,
        message: str,
        solution: str = "",
        severity: str = "ERROR",
        details: str = "",
        target_chat_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Gửi cảnh báo sự cố thử nghiệm và trả về kết quả từng kênh"""
        bot_token = self.get_bot_token()
        if not bot_token:
            return {
                "success": False,
                "message": "Chưa cấu hình Telegram Bot Token",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        if target_chat_id:
            active_channels = [{"id": 0, "name": "Kênh Đã Chọn", "chat_id": target_chat_id}]
        else:
            active_channels = self.get_channels(active_only=True, notification_type="issues")

        if not active_channels:
            return {
                "success": False,
                "message": "Không có kênh Telegram nào đang BẬT tùy chọn nhận 'Cảnh báo sự cố (Issue alert)'.",
                "sent_count": 0,
                "total_active": 0,
                "channels": []
            }

        if not solution:
            solution = self.get_solution_for_error(f"{title} {message} {details}")

        now_str = datetime.now().strftime("%H:%M:%S %d/%m/%Y")
        severity_tag = "🔴 [NGHIÊM TRỌNG]" if severity.upper() in ("CRITICAL", "ERROR", "HIGH") else "🟡 [CẢNH BÁO]"

        text = (
            f"🚨 *[HỆ THỐNG CẢNH BÁO SỰ CỐ - TEST]* {severity_tag}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 *Sự cố:* *{title}*\n"
            f"📝 *Mô tả lỗi:* `{message}`\n"
        )
        if details:
            text += f"🔍 *Chi tiết:* `{details}`\n"
        text += (
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *HƯỚNG DẪN KHẮC PHỤC:*\n"
            f"{solution}\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"⏰ *Thời điểm:* `{now_str}`"
        )

        results = []
        sent_count = 0
        for ch in active_channels:
            ch_name = ch.get("name") or "Kênh Telegram"
            ch_id = ch.get("chat_id")
            ok, err_msg = self.send_message_to_chat(bot_token, ch_id, text)
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
            "message": f"Đã gửi cảnh báo sự cố tới {sent_count}/{total} kênh Telegram đang bật nhận loại tin này."
        }

    # =========================================================================
    # 3. BÁO CÁO HOẠT ĐỘNG HÀNG NGÀY (DAILY REPORT: VIDEOS, CHANNELS, COSTS, STATS)
    # =========================================================================
    def build_daily_report_data(self, report_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Tổng hợp toàn bộ số liệu hoạt động trong ngày:
        - Các video YouTube đã tải về
        - Các video đã render
        - Danh sách chi tiết tác vụ đăng TikTok (Video nào gửi tới nick TikTok nào, nguồn YouTube nào, kết quả Thành công/Thất bại)
        - Chi phí AI Models (OpenAI, Gemini, DeepSeek...)
        - Tình hình tài khoản TikTok (số lượng, nick đủ 10K)
        """
        if not report_date:
            report_date = datetime.now().strftime("%Y-%m-%d")

        conn = get_connection()
        cursor = conn.cursor()

        # 1. Danh sách chi tiết tác vụ đăng bài trong ngày
        cursor.execute('''
            SELECT 
                ut.id, ut.status, ut.title as task_title, ut.uploaded_at, ut.scheduled_time, 
                ut.error_message, ut.created_at,
                v.title as video_title, v.yt_video_id,
                c.title as yt_channel_title, c.display_name as yt_channel_display_name,
                gp.name as gpm_name, gp.tiktok_username, gp.gpm_id
            FROM upload_tasks ut
            LEFT JOIN videos v ON ut.video_id = v.id
            LEFT JOIN channels c ON v.channel_id = c.channel_id
            LEFT JOIN gpm_profiles gp ON ut.gpm_profile_id = gp.id
            WHERE date(COALESCE(ut.uploaded_at, ut.created_at), 'localtime') = date(?, 'localtime')
            ORDER BY ut.id DESC
        ''', (report_date,))
        tasks_rows = [dict(r) for r in cursor.fetchall()]

        total_uploads = len(tasks_rows)
        success_uploads = sum(1 for t in tasks_rows if t.get("status") == "completed")
        failed_uploads = sum(1 for t in tasks_rows if t.get("status") == "failed")
        queued_uploads = sum(1 for t in tasks_rows if t.get("status") in ("queued", "processing"))

        # 2. Thống kê video YouTube tải & render trong ngày
        cursor.execute('''
            SELECT COUNT(*) as downloaded_count 
            FROM videos 
            WHERE date(created_at, 'localtime') = date(?, 'localtime')
        ''', (report_date,))
        downloaded_count = cursor.fetchone()["downloaded_count"]

        cursor.execute('''
            SELECT COUNT(*) as rendered_count 
            FROM videos 
            WHERE rendered_path IS NOT NULL AND rendered_path != '' 
              AND date(created_at, 'localtime') = date(?, 'localtime')
        ''', (report_date,))
        rendered_count = cursor.fetchone()["rendered_count"]

        # 3. Thống kê chi phí AI Models trong ngày (từ ai_usage_logs)
        cursor.execute('''
            SELECT 
                provider,
                model,
                COUNT(*) as calls,
                COALESCE(SUM(prompt_tokens), 0) as prompt_tokens,
                COALESCE(SUM(completion_tokens), 0) as completion_tokens,
                COALESCE(SUM(total_tokens), 0) as total_tokens,
                ROUND(COALESCE(SUM(estimated_cost), 0.0), 6) as cost_usd
            FROM ai_usage_logs
            WHERE date(created_at, 'localtime') = date(?, 'localtime')
            GROUP BY provider, model
            ORDER BY cost_usd DESC
        ''', (report_date,))
        ai_rows = [dict(r) for r in cursor.fetchall()]

        total_ai_calls = sum(r["calls"] for r in ai_rows)
        total_ai_tokens = sum(r["total_tokens"] for r in ai_rows)
        total_ai_cost_usd = sum(r["cost_usd"] for r in ai_rows)
        total_ai_cost_vnd = round(total_ai_cost_usd * 25400, 0)

        # 4. Thống kê nick TikTok & theo dõi 10K
        cursor.execute('SELECT COUNT(*) as total_profiles FROM gpm_profiles')
        total_profiles = cursor.fetchone()["total_profiles"]

        cursor.execute('SELECT COUNT(*) as eligible_10k FROM gpm_profiles WHERE eligible_10k = 1')
        eligible_10k_count = cursor.fetchone()["eligible_10k"]

        cursor.execute('SELECT COUNT(*) as tracking_count FROM gpm_profiles WHERE notify_status = "tracking"')
        tracking_count = cursor.fetchone()["tracking_count"]

        # 5. Kênh YouTube đang theo dõi
        cursor.execute('SELECT COUNT(*) as total_yt_channels FROM channels WHERE is_active = 1')
        total_yt_channels = cursor.fetchone()["total_yt_channels"]

        conn.close()

        return {
            "report_date": report_date,
            "tasks": tasks_rows,
            "total_uploads": total_uploads,
            "success_uploads": success_uploads,
            "failed_uploads": failed_uploads,
            "queued_uploads": queued_uploads,
            "downloaded_count": downloaded_count,
            "rendered_count": rendered_count,
            "ai_stats": ai_rows,
            "total_ai_calls": total_ai_calls,
            "total_ai_tokens": total_ai_tokens,
            "total_ai_cost_usd": total_ai_cost_usd,
            "total_ai_cost_vnd": total_ai_cost_vnd,
            "total_profiles": total_profiles,
            "eligible_10k_count": eligible_10k_count,
            "tracking_count": tracking_count,
            "total_yt_channels": total_yt_channels
        }

    def format_daily_report_message(self, data: Dict[str, Any]) -> str:
        """Định dạng bản tin báo cáo hàng ngày cực kỳ trực quan, sang trọng, đầy đủ chi tiết"""
        date_str = data.get("report_date", datetime.now().strftime("%Y-%m-%d"))
        try:
            d_obj = datetime.strptime(date_str, "%Y-%m-%d")
            display_date = d_obj.strftime("%d/%m/%Y")
        except Exception:
            display_date = date_str

        total_up = data.get("total_uploads", 0)
        success_up = data.get("success_uploads", 0)
        failed_up = data.get("failed_uploads", 0)
        queued_up = data.get("queued_uploads", 0)

        rate_str = f"{round((success_up / total_up) * 100, 1)}%" if total_up > 0 else "0%"

        msg = (
            f"📊 *[BÁO CÁO HOẠT ĐỘNG HÀNG NGÀY - {display_date}]*\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚡ *TỔNG QUAN TỰ ĐỘNG HÓA:*\n"
            f"• 📺 Kênh YouTube đang quét: *{data.get('total_yt_channels', 0)} kênh*\n"
            f"• 📥 Video mới tải về hôm nay: *{data.get('downloaded_count', 0)} video*\n"
            f"• 🎬 Video render hoàn tất: *{data.get('rendered_count', 0)} video*\n"
            f"• 📤 Tổng lượt đăng TikTok: *{total_up} lượt*\n"
            f"   ↳ ✅ Thành công: *{success_up}* ({rate_str})\n"
            f"   ↳ ❌ Thất bại: *{failed_up}*\n"
        )
        if queued_up > 0:
            msg += f"   ↳ ⏳ Đang đợi / xử lý: *{queued_up}*\n"

        # CHI TIẾT PHÂN PHỐI VIDEO LÊN TIKTOK (Which video sent to which TikTok channel)
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📱 *CHI TIẾT PHÂN PHỐI VIDEO LÊN TIKTOK:*\n"
        tasks = data.get("tasks", [])
        if not tasks:
            msg += "_(Hôm nay chưa phát sinh tác vụ đăng bài nào)_\n"
        else:
            # Hiển thị tối đa 8 tác vụ gần nhất để không vượt giới hạn tin nhắn Telegram (4096 chars)
            max_show = 8
            displayed_tasks = tasks[:max_show]
            for i, t in enumerate(displayed_tasks, start=1):
                status_icon = "✅" if t.get("status") == "completed" else ("❌" if t.get("status") == "failed" else "⏳")
                status_label = "Thành công" if t.get("status") == "completed" else ("Thất bại" if t.get("status") == "failed" else "Đang chờ")
                
                v_title = t.get("video_title") or t.get("task_title") or "Video TikTok"
                if len(v_title) > 42:
                    v_title = v_title[:40] + "..."
                
                yt_name = t.get("yt_channel_display_name") or t.get("yt_channel_title") or "YouTube"
                if len(yt_name) > 24:
                    yt_name = yt_name[:22] + ".."
                
                user_label = f"@{t.get('tiktok_username')}" if t.get("tiktok_username") else f"`{t.get('gpm_name') or t.get('gpm_id')}`"
                
                msg += f"{i}. {status_icon} *{v_title}*\n"
                msg += f"   ↳ 📺 Nguồn: `{yt_name}`\n"
                msg += f"   ↳ 🎯 Đăng lên: *{user_label}* ({status_label})\n"
                if t.get("status") == "failed" and t.get("error_message"):
                    err_short = t.get("error_message")[:65]
                    msg += f"   ↳ ⚠️ Lỗi: `{err_short}`\n"

            if len(tasks) > max_show:
                msg += f"_(...và còn {len(tasks) - max_show} tác vụ đăng bài khác trong ngày)_\n"

        # BẢNG THỐNG KÊ CHI PHÍ (COST BREAKDOWN)
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "💰 *THỐNG KÊ CHI PHÍ AI & TÀI NGUYÊN (COST BREAKDOWN):*\n"
        ai_stats = data.get("ai_stats", [])
        if not ai_stats:
            msg += "• Chi phí AI hôm nay: *$0.00 USD* (Không phát sinh lượt gọi AI có phí)\n"
        else:
            msg += f"• Tổng lượt gọi AI: *{data.get('total_ai_calls', 0):,} lượt* (*{data.get('total_ai_tokens', 0):,} tokens*)\n"
            for st in ai_stats:
                p_name = (st.get("provider") or "").capitalize()
                m_name = st.get("model") or ""
                cost = st.get("cost_usd", 0.0)
                msg += f"   ↳ 🔹 *{p_name}* (`{m_name}`): *${cost:.4f}*\n"
            msg += f"💵 *Tổng chi phí hôm nay:* *${data.get('total_ai_cost_usd', 0.0):.4f} USD* (~*{data.get('total_ai_cost_vnd', 0):,} VNĐ*)\n"

        # TÌNH HÌNH DÀN NICK TIKTOK
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "📈 *TÌNH HÌNH DÀN NICK TIKTOK BETA:*\n"
        msg += f"• Tổng profile GPMLogin: *{data.get('total_profiles', 0)} profile*\n"
        msg += f"• Nick đang theo dõi mốc 10K: *{data.get('tracking_count', 0)} nick*\n"
        msg += f"• Nick đã cán mốc 10.000 Follower: *{data.get('eligible_10k_count', 0)} nick* 🏆\n"

        msg += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        msg += "🤖 *TikTok Farm Automation System* | Chúc bạn một ngày nổ view triệu view!"
        return msg

    def send_daily_report(self, report_date: Optional[str] = None, target_chat_id: Optional[str] = None) -> Dict[str, Any]:
        """Tạo và gửi báo cáo ngày tới tất cả kênh Telegram có bật notify_daily_report = 1 (hoặc target_chat_id)"""
        bot_token = self.get_bot_token()
        if not bot_token:
            return {
                "success": False,
                "message": "Chưa cấu hình Telegram Bot Token",
                "sent_count": 0,
                "channels": []
            }

        if target_chat_id:
            active_channels = [{"id": 0, "name": "Kênh Đã Chọn", "chat_id": target_chat_id}]
        else:
            active_channels = self.get_channels(active_only=True, notification_type="daily_report")

        if not active_channels:
            return {
                "success": False,
                "message": "Không có kênh Telegram nào đang BẬT nhận 'Báo cáo hàng ngày (Daily report)'.",
                "sent_count": 0,
                "channels": []
            }

        data = self.build_daily_report_data(report_date=report_date)
        report_text = self.format_daily_report_message(data)

        sent_count = 0
        results = []
        for ch in active_channels:
            ch_name = ch.get("name") or "Kênh Telegram"
            ch_id = ch.get("chat_id")
            ok, err_msg = self.send_message_to_chat(bot_token, ch_id, report_text)
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
            "report_text": report_text,
            "message": f"Đã gửi báo cáo hoạt động ngày tới {sent_count}/{total} kênh Telegram đang bật."
        }

notifier = TelegramNotifier()
