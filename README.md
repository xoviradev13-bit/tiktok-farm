# TikTok Auto Farm & AI Video Engine (GPMLogin Integration)

Hệ thống Desktop App tự động hóa khai thác kênh YouTube và quản lý dàn tài khoản TikTok Beta qua GPMLogin.

## Tính năng chính

1. **Quét & Phân Tích Kênh YouTube (Theo Từ Khóa Ngách):**
   - Nhập từ khóa ngách -> Quét ra 50 - 100 kênh tiềm năng.
   - Phân tích chỉ số: Lượt Subscriber, Video count, Lượt view trung bình.
   - **Đo lường tần suất đăng bài:** Tính số ngày trung bình ra video và ngày ra video gần nhất để lọc kênh đang hoạt động mạnh.

2. **AI Video Transformer (Chuẩn Hóa Video TikTok Beta):**
   - Tự động cắt các đoạn viral có thời lượng **60s - 90s** (chuẩn >1 phút để kiếm tiền Creator Rewards).
   - Tự động format dọc 9:16 (Scale và làm mờ nền viền).
   - Lật video (Horizontal Flip), đổi tốc độ (1.03x), đổi tần số âm thanh (Pitch Shift) tối ưu hóa độ độc bản.
   - AI sinh Hook 3s đầu giữ chân người xem và bộ Hashtag chuẩn SEO TikTok.

3. **GPMLogin Farm & Auto Uploader (SSMA):**
   - Kết nối trực tiếp với GPMLogin Local API (`http://127.0.0.1:19995`).
   - Tự động lấy danh sách profiles và mở profile có gắn proxy sạch.
   - Dùng Playwright (CDP) tự động đưa video vào khung upload của TikTok Creator Center, điền tiêu đề + hashtag và ấn đăng.

4. **Theo Dõi Chỉ Số & Cảnh Báo 10.000 Follower:**
   - Quét định kỳ lượng Follower và View của từng profile.
   - Tự động bắn thông báo tức thì qua Telegram Bot khi có nick chạm mốc **10.000 Follower** để chủ kênh kịp thời nộp đơn tham gia Quỹ Sáng Tạo (TikTok Beta).

## Hướng Dẫn Khởi Chạy Nhanh Trên Windows

1. Cài đặt các thư viện cần thiết:
   ```bash
   python -m pip install -r requirements.txt
   ```
2. Cài đặt browser cho Playwright (nếu dùng Playwright standalone):
   ```bash
   python -m playwright install chromium
   ```
3. Khởi chạy phần mềm:
   - Cách 1: Click đúp vào file `run_app.bat`.
   - Cách 2: Chạy lệnh `python main.py`.
4. Mở trình duyệt và truy cập: `http://127.0.0.1:8088`.
