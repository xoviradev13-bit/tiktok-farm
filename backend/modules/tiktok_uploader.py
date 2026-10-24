import os
import time
from typing import Dict, Any, Optional
from backend.modules.gpm_client import gpm_client
from backend.modules.account_health import account_health
from backend.database import log_event, get_connection
from backend.logger import get_logger
from backend.config import DATA_DIR

logger = get_logger("tiktok_uploader")

SCREENSHOT_DIR = DATA_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

# URL upload TikTok đã được xác nhận cho VN region (từ spike test)
# TikTok Studio dùng iframe tại: tiktokstudio/upload?from=creator_center&tab=video
TIKTOK_UPLOAD_URLS = [
    "https://www.tiktok.com/tiktokstudio/upload?from=creator_center&tab=video",
    "https://www.tiktok.com/creator-center/upload?from=upload",
    "https://www.tiktok.com/creator-center/upload",
]


def dismiss_tiktok_modals(page) -> None:
    """
    Tự động phát hiện và đóng tất cả các loại popup/modal của TikTok Studio:
    1. 'Bật kiểm tra nội dung tự động?' -> Bấm nút 'Bật' (Turn on)
    2. 'Bổ sung tính năng chỉnh sửa mới' -> Bấm nút 'Đã hiểu' (Got it)
    3. Hộp thoại xác nhận hủy nhầm -> Bấm 'Tiếp tục chỉnh sửa'
    4. Các thông báo gợi ý/overlay khác -> Escape
    """
    try:
        # 1. Bật kiểm tra bản quyền & nội dung tự động (như trong modal chụp màn hình)
        btn_turn_on = page.locator('button:has-text("Bật"), button:has-text("Turn on")').first
        if btn_turn_on.is_visible(timeout=1000):
            log_event("INFO", "Phát hiện modal 'Bật kiểm tra nội dung tự động' -> Đang bấm 'Bật'")
            btn_turn_on.click()
            time.sleep(1)
    except Exception:
        pass

    try:
        # 2. Popup thông báo tính năng mới / hướng dẫn
        btn_got_it = page.locator('button:has-text("Đã hiểu"), button:has-text("Got it")').first
        if btn_got_it.is_visible(timeout=1000):
            log_event("INFO", "Phát hiện popup tính năng mới -> Đang bấm 'Đã hiểu'")
            btn_got_it.click()
            time.sleep(1)
    except Exception:
        pass

    try:
        # 3. Nếu vô tình kích hoạt modal hủy, giữ lại bài đăng
        btn_keep = page.locator('button:has-text("Tiếp tục chỉnh sửa")').first
        if btn_keep.is_visible(timeout=800):
            btn_keep.click()
            time.sleep(1)
    except Exception:
        pass

    try:
        # 4. Gỡ bỏ overlay tour guide của react-joyride (nguyên nhân gây chặn click nút Đăng)
        page.evaluate("""
            () => {
                const joyride = document.querySelector('#react-joyride-portal');
                if (joyride) joyride.remove();
                const overlays = document.querySelectorAll('.react-joyride__overlay, .TUXModal-overlay');
                overlays.forEach(el => el.remove());
            }
        """)
    except Exception:
        pass

    try:
        # 5. Nhấn Escape để đóng các floating tooltip/gợi ý còn sót
        page.keyboard.press("Escape")
    except Exception:
        pass


class TikTokUploader:
    def upload_via_gpm(
        self,
        gpm_profile_id: str,
        video_path: str,
        title: str,
        tags: str = "#viral #fyp #trending",
        auto_post: bool = True,
        close_browser_on_finish: bool = False
    ) -> Dict[str, Any]:
        """
        Tự động hóa đăng video lên TikTok bằng GPMLogin qua Playwright CDP.
        Hỗ trợ:
        - Dù trình duyệt profile ĐANG MỞ SẴN hay CHƯA MỞ đều hoạt động trơn tru.
        - Tự động đóng modal 'Bật kiểm tra nội dung tự động' và các popup của TikTok Studio.
        - Trả về dict: { success: bool, message: str }
        """
        if not os.path.exists(video_path):
            return {"success": False, "message": f"Không tìm thấy file video: {video_path}"}

        try:
            from backend.modules.tiktok_tracker import set_profile_busy
            set_profile_busy(gpm_profile_id, True)
        except Exception:
            pass

        log_event("INFO", f"Bắt đầu upload lên GPM profile {gpm_profile_id}: {os.path.basename(video_path)}")

        # 1. Mở hoặc kết nối profile GPMLogin (nếu profile đã mở sẵn, GPM trả về port hiện tại)
        remote_address = gpm_client.start_profile(gpm_profile_id)
        if not remote_address:
            try:
                from backend.modules.tiktok_tracker import set_profile_busy
                set_profile_busy(gpm_profile_id, False)
            except Exception:
                pass
            return {"success": False, "message": f"Không thể lấy cổng debug GPM cho profile {gpm_profile_id}"}

        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            if close_browser_on_finish:
                gpm_client.stop_profile(gpm_profile_id)
            try:
                from backend.modules.tiktok_tracker import set_profile_busy
                set_profile_busy(gpm_profile_id, False)
            except Exception:
                pass
            return {"success": False, "message": "Playwright chưa được cài. Chạy: pip install playwright && playwright install chromium"}

        result = {"success": False, "message": "Chưa bắt đầu"}

        try:
            with sync_playwright() as p:
                log_event("INFO", f"Kết nối Playwright CDP tới http://{remote_address}")
                browser = p.chromium.connect_over_cdp(f"http://{remote_address}")
                context = browser.contexts[0] if browser.contexts else browser.new_context()

                # Tự động tìm tab đã mở sẵn TikTok Studio nếu profile đã mở sẵn từ trước
                page = None
                for pg in context.pages:
                    u = pg.url.lower()
                    if "tiktokstudio" in u or "creator-center" in u or "upload" in u:
                        page = pg
                        log_event("INFO", f"Tìm thấy tab TikTok Studio đang mở sẵn: {pg.url}")
                        break

                if not page:
                    for pg in context.pages:
                        if "tiktok.com" in pg.url.lower():
                            page = pg
                            break

                if not page:
                    page = context.pages[0] if context.pages else context.new_page()

                try:
                    page.bring_to_front()
                except Exception:
                    pass

                # 2. Điều hướng đến trang upload TikTok nếu chưa ở đó
                current_url = page.url.lower()
                upload_reached = "tiktokstudio" in current_url or "creator-center" in current_url or "upload" in current_url

                if not upload_reached:
                    for url_try in TIKTOK_UPLOAD_URLS:
                        try:
                            log_event("INFO", f"Thử mở: {url_try}")
                            page.goto(url_try, wait_until="domcontentloaded", timeout=60000)
                            time.sleep(3)
                            if "tiktok.com" in page.url:
                                log_event("INFO", f"Đã mở thành công: {page.url}")
                                upload_reached = True
                                break
                        except Exception as nav_err:
                            log_event("WARNING", f"Timeout với {url_try}: {nav_err}")
                            continue

                if not upload_reached:
                    # Kiểm tra xem có phải do lỗi proxy hay mạng không
                    health = account_health.check_page_account_health(page, gpm_profile_id)
                    reason = health.get("reason") if not health.get("healthy") else "Không thể mở trang upload TikTok. Hãy kiểm tra kết nối mạng hoặc Proxy của profile."
                    logger.error(f"[UPLOAD] {gpm_profile_id}: {reason}")
                    result = {"success": False, "error_type": "PAGE_UNREACHABLE", "message": reason}
                    return result

                # Kiểm tra toàn diện sức khỏe tài khoản (Banned, Restricted, Checkpoint, Unlogged)
                health = account_health.check_page_account_health(page, gpm_profile_id)
                if not health.get("healthy"):
                    logger.error(f"[UPLOAD ABORT] Tài khoản {gpm_profile_id} có vấn đề: {health['status'].upper()} - {health['reason']}")
                    result = {
                        "success": False,
                        "error_type": f"ACCOUNT_{health['status'].upper()}",
                        "message": health["reason"]
                    }
                    return result

                # Dọn sạch các modal nếu có sẵn khi vào trang
                dismiss_tiktok_modals(page)

                # 3. Kiểm tra xem video đã được đưa vào chưa, nếu chưa thì tìm input[type="file"]
                has_uploaded_video = page.locator('button:has-text("Thay thế"), button:has-text("Replace")').count() > 0

                if not has_uploaded_video:
                    file_input_set = False

                    # Thử trong trang chính
                    fi = page.locator('input[type="file"]')
                    if fi.count() > 0:
                        fi.first.set_input_files(video_path)
                        file_input_set = True
                        log_event("INFO", "Đã set file input tại trang chính")
                    else:
                        # Thử trong các iframe
                        for frame in page.frames:
                            try:
                                fi = frame.locator('input[type="file"]')
                                if fi.count() > 0:
                                    fi.first.set_input_files(video_path)
                                    file_input_set = True
                                    log_event("INFO", f"Đã set file input qua iframe: {frame.url}")
                                    break
                            except Exception:
                                continue

                    if not file_input_set:
                        # Fallback: click nút "Tải lên" trên navbar để mở upload
                        log_event("WARNING", "Không thấy input file, thử click nút Tải lên trên navbar...")
                        upload_btn = page.locator(
                            'a[href*="upload"], button:has-text("Tải lên"), button:has-text("Upload"), [data-e2e="upload-icon"]'
                        ).first
                        try:
                            if upload_btn.is_visible(timeout=5000):
                                upload_btn.click()
                                time.sleep(3)
                                for frame in page.frames:
                                    try:
                                        fi = frame.locator('input[type="file"]')
                                        if fi.count() > 0:
                                            fi.first.set_input_files(video_path)
                                            file_input_set = True
                                            log_event("INFO", f"Đã set file input sau click navbar: {frame.url}")
                                            break
                                    except Exception:
                                        continue
                        except Exception as btn_err:
                            log_event("WARNING", f"Lỗi khi click navbar upload: {btn_err}")

                    if not file_input_set:
                        ss_path = str(SCREENSHOT_DIR / f"upload_fail_{gpm_profile_id[:8]}.png")
                        try:
                            page.screenshot(path=ss_path)
                        except Exception:
                            pass
                        result = {"success": False, "message": f"Không tìm thấy khung upload trên TikTok. Screenshot: {ss_path}"}
                        return result

                # 4. Chờ video upload và phân tích
                log_event("INFO", "Đang chờ TikTok xử lý video và đóng modal gợi ý...")
                for _ in range(8):
                    time.sleep(1.5)
                    dismiss_tiktok_modals(page)

                # 5. Điền Caption & Hashtag
                full_caption = f"{title} {tags}"
                log_event("INFO", f"Điền caption: {full_caption[:60]}...")

                caption_editor = page.locator('div[contenteditable="true"]').first
                typed = False
                try:
                    if caption_editor.is_visible(timeout=4000):
                        caption_editor.click(timeout=4000)
                        page.keyboard.press("Control+A")
                        page.keyboard.press("Backspace")
                        page.keyboard.type(full_caption, delay=40)
                        typed = True
                except Exception:
                    pass

                if not typed:
                    # Fallback: JS focus() để bỏ qua overlay
                    try:
                        page.evaluate("""
                            const el = document.querySelector('div[contenteditable="true"]');
                            if (el) {
                                el.focus();
                                document.execCommand('selectAll', false, null);
                                document.execCommand('delete', false, null);
                            }
                        """)
                        time.sleep(0.5)
                        page.keyboard.type(full_caption, delay=40)
                        typed = True
                        log_event("INFO", "Đã điền caption qua JS fallback")
                    except Exception as js_err:
                        log_event("WARNING", f"Không điền được caption: {js_err}")

                # Đóng các modal phát sinh sau khi nhập caption
                dismiss_tiktok_modals(page)
                time.sleep(2)

                # 6. Nhấn Đăng (nếu auto_post=True)
                if auto_post:
                    log_event("INFO", "Chuẩn bị nhấn nút Đăng (Post)...")
                    dismiss_tiktok_modals(page)

                    # Tìm chính xác nút Đăng thực sự (data-e2e="post_video_button" hoặc type-primary, TRÁNH nhầm với menu 'Bài đăng' ở sidebar)
                    post_btn = page.locator('button[data-e2e="post_video_button"]').first
                    if not post_btn.is_visible():
                        post_btn = page.locator(
                            'button.Button__root--type-primary:has-text("Đăng"), '
                            'button.Button__root--type-primary:has-text("Post"), '
                            'button:text-is("Đăng"), '
                            'button:text-is("Post")'
                        ).first

                    try:
                        post_btn.scroll_into_view_if_needed(timeout=5000)
                        time.sleep(1)

                        if post_btn.is_visible(timeout=5000):
                            # Thực hiện click JS trực tiếp để bỏ qua hoàn toàn overlay react-joyride
                            try:
                                post_btn.evaluate("el => el.click()")
                            except Exception:
                                post_btn.click(timeout=5000)

                            time.sleep(6)
                            log_event("INFO", f"✅ Đã đăng video thành công - Profile {gpm_profile_id}")
                            result = {"success": True, "message": "Video đã được đăng lên TikTok thành công"}

                            # Tự động cập nhật chỉ số (Username & Followers) ngay trong phiên làm việc
                            try:
                                from backend.modules.tiktok_tracker import tiktok_tracker
                                from backend.modules.metrics_tracker import metrics_tracker
                                stats = tiktok_tracker.extract_metrics_from_page(page)
                                if stats.get("is_logged_in") and stats.get("username"):
                                    metrics_tracker.update_profile_stats(
                                        gpm_id=gpm_profile_id,
                                        followers=stats.get("followers", 0),
                                        total_views=0,
                                        username=stats.get("username") or ""
                                    )
                                    log_event("INFO", f"Tự động cập nhật chỉ số sau khi đăng bài: @{stats.get('username')} ({stats.get('followers')} followers)")
                            except Exception as st_err:
                                log_event("WARNING", f"Lỗi cập nhật stats sau upload: {st_err}")
                        else:
                            result = {"success": False, "message": "Không tìm thấy nút Đăng"}
                    except Exception as post_err:
                        result = {"success": False, "message": f"Lỗi khi nhấn Đăng: {post_err}"}
                else:
                    result = {"success": True, "message": "Video đã được chuẩn bị thành công (dry-run, chưa nhấn Đăng)"}

        except Exception as e:
            logger.exception(f"Lỗi Playwright upload profile {gpm_profile_id}: {e}")
            log_event("ERROR", f"Lỗi Playwright upload profile {gpm_profile_id}: {str(e)}")
            result = {"success": False, "message": str(e)}
        finally:
            try:
                from backend.modules.tiktok_tracker import set_profile_busy
                set_profile_busy(gpm_profile_id, False)
            except Exception:
                pass
            # Chỉ tắt browser nếu caller yêu cầu đóng (mặc định giữ lại để không ngắt phiên làm việc của user)
            if close_browser_on_finish:
                gpm_client.stop_profile(gpm_profile_id)

        return result


tiktok_uploader = TikTokUploader()
