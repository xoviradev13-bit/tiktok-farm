import time
import re
import threading
from typing import Dict, Any, Optional, List
from backend.database import get_connection, log_event
from backend.modules.gpm_client import gpm_client
from backend.modules.metrics_tracker import metrics_tracker
from backend.modules.account_health import account_health
from backend.logger import get_logger
from backend.modules.gpm_profile_reader import (
    fetch_account_info_from_gpm, 
    is_gpm_reader_available, 
    list_gpm_profiles_status
)

logger = get_logger("tiktok_tracker")

_busy_profiles_lock = threading.Lock()
_busy_profiles = set()
_is_scanning_all = False
_cancel_scan_flag = False
_scan_progress = {
    "is_scanning": False,
    "current": 0,
    "current_index": 0,
    "total": 0,
    "current_profile_name": "",
    "percent": 0,
    "success_count": 0,
    "status_message": "",
    "message": ""
}

def parse_followers(val: Any) -> int:
    """Chuyển đổi chuỗi follower (10.5K, 1.2M, 10,450, 1) sang số nguyên an toàn"""
    if val is None or val == "":
        return 0
    if isinstance(val, (int, float)):
        return int(val)
    s = str(val).strip().replace(',', '').replace(' ', '')
    m = re.search(r'([\d.]+)\s*([KMBkmb])?', s)
    if not m:
        return 0
    try:
        num = float(m.group(1))
        unit = (m.group(2) or '').upper()
        if unit == 'K':
            return int(num * 1000)
        elif unit == 'M':
            return int(num * 1000000)
        elif unit == 'B':
            return int(num * 1000000000)
        return int(num)
    except Exception:
        return 0

def is_profile_busy(gpm_id: str) -> bool:
    with _busy_profiles_lock:
        return gpm_id in _busy_profiles

def set_profile_busy(gpm_id: str, busy: bool = True):
    with _busy_profiles_lock:
        if busy:
            _busy_profiles.add(gpm_id)
        else:
            _busy_profiles.discard(gpm_id)

class TikTokTracker:
    def __init__(self):
        pass

    def extract_metrics_from_page(self, page) -> Dict[str, Any]:
        """
        Xác minh chính xác tài khoản ĐANG ĐĂNG NHẬP (Logged-in Account) trong phiên GPMLogin.
        Tuyệt đối không lấy nhầm public profile của người khác khi lướt web:
        1. Gọi TikTok Passport Session API (/passport/web/account/info/?app_id=1233) - Chỉ có khi đã đăng nhập.
        2. Gọi TikTok Studio User API (/tiktokstudio/api/web/user) - Chỉ trả về data của chủ sở hữu session.
        3. Đọc window.__UNIVERSAL_DATA_FOR_REHYDRATION__["__DEFAULT_SCOPE__"]["webapp.app-context"].user.
        4. Nếu KHÔNG có phiên đăng nhập hợp lệ -> Trả về is_logged_in = False.
        5. Nếu ĐÃ ĐĂNG NHẬP -> Dùng chính xác authenticated username đó để truy vấn Follower.
        """
        try:
            raw = page.evaluate(r"""
                async () => {
                    let authUsername = null;
                    let authNickname = null;
                    let authUserId = null;
                    let authSecUid = null;
                    let isLoggedIn = false;
                    let followersRaw = null;

                    // 1. KIỂM TRA QUA TIKTOK STUDIO USER SESSION API (ƯU TIÊN SỐ 1 - CHỨA UNIQID & NICKNAME MỚI NHẤT)
                    try {
                        const studioQs = "aid=1988&app_name=tiktok_creator_center&device_platform=web_pc&channel=tiktok_web&os=win&browser_name=Mozilla&browser_platform=Win32";
                        const sRes = await fetch(`https://www.tiktok.com/tiktokstudio/api/web/user?${studioQs}`, {
                            credentials: "include",
                            headers: { "Accept": "application/json" }
                        });
                        if (sRes.ok) {
                            const sData = await sRes.json();
                            const ub = sData?.userBaseInfo?.UserProfile?.UserBase;
                            if (ub && ub.Id) {
                                isLoggedIn = true;
                                authUserId = String(ub.Id);
                                if (ub.SecUid) authSecUid = String(ub.SecUid).trim();
                                if (ub.UniqId) authUsername = ub.UniqId;
                                if (ub.NickName) authNickname = ub.NickName;
                                const fc = ub.FanCount ?? ub.FanCnt;
                                if (fc !== undefined && fc !== null) followersRaw = fc;
                            }
                        }
                    } catch(e) {}

                    // 2. KIỂM TRA QUA SSR HYDRATION: webapp.app-context.user (AUTHENTICATED VIEWER)
                    try {
                        const scope = window.__UNIVERSAL_DATA_FOR_REHYDRATION__?.["__DEFAULT_SCOPE__"] || {};
                        const appUser = scope["webapp.app-context"]?.user;
                        if (appUser && (appUser.uniqueId || appUser.id)) {
                            isLoggedIn = true;
                            if (!authUserId && appUser.id) authUserId = String(appUser.id);
                            if (!authSecUid && appUser.secUid) authSecUid = String(appUser.secUid).trim();
                            if (!authUsername && appUser.uniqueId) authUsername = appUser.uniqueId;
                            if (!authNickname && appUser.nickname) authNickname = appUser.nickname;
                        }
                    } catch(e) {}

                    // 3. FALLBACK: KIỂM TRA QUA PASSPORT SESSION API (NẾU CHƯA CÓ HOẶC BỔ SUNG)
                    if (!authUsername || !authUserId) {
                        try {
                            const passRes = await fetch("https://www.tiktok.com/passport/web/account/info/?app_id=1233", {
                                credentials: "include",
                                headers: { "Accept": "application/json" }
                            });
                            if (passRes.ok) {
                                const pData = await passRes.json();
                                if (pData?.message === "success" && pData?.data?.user_id) {
                                    isLoggedIn = true;
                                    if (!authUserId) authUserId = String(pData.data.user_id);
                                    if (!authSecUid && pData.data.sec_user_id) authSecUid = String(pData.data.sec_user_id).trim();
                                    if (!authUsername) authUsername = pData.data.username || pData.data.screen_name || null;
                                    if (!authNickname) authNickname = pData.data.screen_name || null;
                                }
                            }
                        } catch(e) {}
                    }

                    // NẾU TẤT CẢ CÁC NGUỒN XÁC THỰC ĐỀU BÁO CHƯA ĐĂNG NHẬP:
                    if (!isLoggedIn || !authUsername) {
                        return {
                            isLoggedIn: false,
                            username: null,
                            nickname: null,
                            userId: null,
                            followersRaw: 0,
                            reason: "no_authenticated_session"
                        };
                    }

                    // 4. TRÍCH XUẤT FOLLOWER CHÍNH CHỦ CỦA AUTHENTICATED USER
                    // 4.1. Thử lấy từ container thông tin TikTok Studio DOM
                    try {
                        const hoverEl = document.querySelector('[data-tt*="UserInfo"]') || document.querySelector('[data-tt="NewHome_UserInfo_Hover"]');
                        if (hoverEl) {
                            const ht = hoverEl.innerText || '';
                            const hm = ht.match(/Follower[s]?\s*[\n:]?\s*([\d.,]+[KMBkmb]?)/i) || ht.match(/([\d.,]+[KMBkmb]?)\s*[\n:]?\s*Follower[s]?/i);
                            if (hm && (followersRaw === null || followersRaw === undefined)) {
                                followersRaw = hm[1];
                            }
                        }
                    } catch(e) {}

                    // 4.2. Truy vấn trực tiếp trang cá nhân chính chủ /@authUsername để lấy số follower chuẩn xác
                    if (followersRaw === null || followersRaw === undefined || followersRaw === 0 || followersRaw === '0') {
                        try {
                            const uClean = authUsername.replace(/^@/, '').trim();
                            const pRes = await fetch(`https://www.tiktok.com/@${uClean}`, {
                                credentials: "include"
                            });
                            if (pRes.ok) {
                                const htmlText = await pRes.text();
                                const rehyMatch = htmlText.match(/<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([\s\S]*?)<\/script>/);
                                if (rehyMatch) {
                                    const parsed = JSON.parse(rehyMatch[1]);
                                    const userInfo = parsed?.["__DEFAULT_SCOPE__"]?.["webapp.user-detail"]?.userInfo;
                                    // ĐẢM BẢO CHỈ LẤY SỐ LIỆU NẾU TRANG KHỚP CHÍNH XÁC AUTHENTICATED USERNAME
                                    if (userInfo?.user?.uniqueId && userInfo.user.uniqueId.toLowerCase() === uClean.toLowerCase()) {
                                        if (userInfo.stats?.followerCount !== undefined) {
                                            followersRaw = userInfo.stats.followerCount;
                                        }
                                    }
                                }
                                if (followersRaw === null || followersRaw === undefined) {
                                    const fm = htmlText.match(/"followerCount":\s*(\d+)/i) || htmlText.match(/"fanCount":\s*(\d+)/i);
                                    if (fm) followersRaw = parseInt(fm[1], 10);
                                }
                            }
                        } catch(e) {}
                    }

                    return {
                        isLoggedIn: true,
                        username: authUsername,
                        nickname: authNickname,
                        userId: authUserId,
                        secUid: authSecUid,
                        followersRaw: followersRaw
                    };
                }
            """)

            is_logged_in = raw.get("isLoggedIn", False)
            username = raw.get("username")
            if username:
                username = username.strip().replace("@", "")
            followers = parse_followers(raw.get("followersRaw"))

            return {
                "is_logged_in": is_logged_in,
                "username": username if is_logged_in else None,
                "nickname": raw.get("nickname") if is_logged_in else None,
                "user_id": raw.get("userId") if is_logged_in else None,
                "tiktok_uid": raw.get("userId") if is_logged_in else None,
                "sec_uid": raw.get("secUid") if is_logged_in else None,
                "followers": followers if is_logged_in else 0,
                "found": bool(is_logged_in and username)
            }
        except Exception as e:
            log_event("WARNING", f"Lỗi trích xuất thông số TikTok từ trang: {e}")
            return {"is_logged_in": False, "username": None, "nickname": None, "user_id": None, "tiktok_uid": None, "sec_uid": None, "followers": 0, "found": False}

    def scan_single_gpm_profile(self, gpm_id: str, auto_close: bool = True, force_browser: bool = False) -> Dict[str, Any]:
        """
        Quét chỉ số của 1 profile GPMLogin.

        Ưu tiên (ZeroRAM Path): Đọc cookie từ client-agent session file
        → Gọi TikTok API trực tiếp mà KHÔNG MỞ BROWSER.

        Fallback (Browser Path): Mở GPMLogin profile qua Playwright CDP
        khi session file không tồn tại hoặc cookie hết hạn/bị thu hồi.

        Args:
            gpm_id: GPMLogin profile UUID.
            auto_close: Tự động đóng browser sau khi quét (chỉ áp dụng khi cần Browser Path).
            force_browser: Bắt buộc dùng Browser Path dù session file tồn tại.
        """
        if is_profile_busy(gpm_id):
            return {
                "success": False,
                "busy": True,
                "message": f"Profile {gpm_id} đang bận (đang đăng video hoặc đang quét dở)."
            }

        set_profile_busy(gpm_id, True)
        try:
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # FAST PATH (ZeroRAM): Đọc cookie từ profile GPMLogin trên ổ đĩa → Gọi TikTok API
            # Không mở browser, không tốn RAM, hoàn thành trong ~0.3 - 0.8s/profile
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            if is_gpm_reader_available() and not force_browser:
                log_event("INFO", f"[ZeroRAM] Đang đọc cookie profile GPMLogin cho {gpm_id}...")
                session_result = fetch_account_info_from_gpm(gpm_id)

                if session_result.get("found") and session_result.get("is_logged_in"):
                    # Profile hợp lệ → cập nhật DB và trả về
                    u_name = session_result["username"]
                    n_name = session_result.get("nickname") or ""
                    t_uid = session_result.get("tiktok_uid") or session_result.get("user_id") or ""
                    s_uid = session_result.get("sec_uid") or ""
                    f_count = session_result.get("followers", 0)
                    v_7d = session_result.get("views_7d", 0)
                    update_res = metrics_tracker.update_profile_stats(
                        gpm_id=gpm_id,
                        followers=f_count,
                        total_views=v_7d,
                        username=u_name,
                        nickname=n_name,
                        tiktok_uid=t_uid,
                        sec_uid=s_uid
                    )
                    log_event("INFO", f"✅ [ZeroRAM] {gpm_id}: @{u_name} ({n_name}, uid={t_uid}) - {f_count:,} followers ({v_7d:,} views 7d, KHÔNG MỞ BROWSER)")
                    return {
                        "success": True,
                        "is_logged_in": True,
                        "gpm_id": gpm_id,
                        "username": u_name,
                        "nickname": n_name,
                        "tiktok_uid": t_uid,
                        "sec_uid": s_uid,
                        "followers": f_count,
                        "views_7d": v_7d,
                        "eligible_10k": update_res.get("eligible_10k", False),
                        "scan_method": "gpm_profile_disk",
                        "message": f"[ZeroRAM] @{u_name} ({f_count:,} followers)"
                    }
                elif session_result.get("source") == "api_error":
                    log_event("WARNING", f"[ZeroRAM] Cookie {gpm_id} bị TikTok từ chối. Chuyển sang Browser Path...")
                elif session_result.get("source") == "no_session":
                    log_event("WARNING", f"[ZeroRAM] Profile {gpm_id} chưa có sessionid TikTok. Chuyển sang Browser Path...")
                else:
                    log_event("INFO", f"[ZeroRAM] Chưa có file cookie cho {gpm_id}. Chuyển sang Browser Path...")

            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            # BROWSER PATH (Fallback): Mở GPMLogin profile qua Playwright CDP
            # Chỉ chạy khi không có cookie hoặc cookie đã hết hạn
            # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            log_event("INFO", f"[Browser] Mở GPM profile {gpm_id} để quét follower (Browser Path)...")
            gpm_client.ensure_gpm_running()
            remote_address = gpm_client.start_profile(gpm_id, low_ram_mode=True)
            if not remote_address:
                log_event("ERROR", f"Không thể khởi động GPM profile {gpm_id} để quét follower.")
                return {"success": False, "message": "Không thể kết nối cổng debug GPMLogin"}

            try:
                from playwright.sync_api import sync_playwright
            except ImportError:
                if auto_close:
                    gpm_client.stop_profile(gpm_id)
                return {"success": False, "message": "Playwright chưa được cài đặt"}

            result = {"username": None, "followers": 0, "found": False}
            try:
                with sync_playwright() as p:
                    browser = p.chromium.connect_over_cdp(f"http://{remote_address}")
                    ctx = browser.contexts[0] if browser.contexts else browser.new_context()

                    page = None
                    for pg in ctx.pages:
                        u = pg.url.lower()
                        if "tiktokstudio" in u or "creator-center" in u:
                            page = pg
                            break
                    if not page:
                        for pg in ctx.pages:
                            if "tiktok.com" in pg.url.lower():
                                page = pg
                                break
                    if not page:
                        page = ctx.pages[0] if ctx.pages else ctx.new_page()

                    if "tiktokstudio" not in page.url.lower():
                        page.goto("https://www.tiktok.com/tiktokstudio", timeout=30000, wait_until="domcontentloaded")
                    time.sleep(2.0)

                    # Kiểm tra dấu hiệu tài khoản bị banned, restricted, checkpoint hoặc proxy dead
                    health = account_health.check_page_account_health(page, gpm_id)
                    if not health.get("healthy"):
                        result = {
                            "is_logged_in": False,
                            "username": None,
                            "followers": 0,
                            "found": False,
                            "health_status": health.get("status"),
                            "reason": health.get("reason")
                        }
                    else:
                        metrics = self.extract_metrics_from_page(page)
                        is_logged_in = metrics.get("is_logged_in", False)
                        username = metrics.get("username")
                        followers = metrics.get("followers", 0)

                        result = {
                            "is_logged_in": is_logged_in,
                            "username": username,
                            "followers": followers,
                            "found": bool(is_logged_in and username)
                        }
                    browser.close()
            finally:
                if auto_close:
                    gpm_client.stop_profile(gpm_id)

            if result.get("health_status") and result.get("health_status") != "active":
                h_status = result["health_status"].upper()
                h_reason = result.get("reason", "")
                logger.warning(f"Profile GPM {gpm_id} phát hiện trạng thái [{h_status}]: {h_reason}")
                return {
                    "success": False,
                    "is_logged_in": False,
                    "gpm_id": gpm_id,
                    "status": result["health_status"],
                    "scan_method": "browser_cdp",
                    "message": f"[{h_status}] {h_reason}"
                }

            if result.get("is_logged_in") and result.get("username"):
                u_name = result.get("username")
                n_name = result.get("nickname") or ""
                t_uid = result.get("tiktok_uid") or result.get("user_id") or ""
                s_uid = result.get("sec_uid") or ""
                f_count = result.get("followers", 0)
                update_res = metrics_tracker.update_profile_stats(
                    gpm_id=gpm_id,
                    followers=f_count,
                    total_views=0,
                    username=u_name,
                    nickname=n_name,
                    tiktok_uid=t_uid,
                    sec_uid=s_uid
                )
                account_health.update_health_status(gpm_id, "active", "")
                log_event("INFO", f"✅ [Browser] Đã quét GPM profile {gpm_id}: @{u_name} ({n_name}, uid={t_uid}) - {f_count:,} followers (Đủ 10K: {update_res.get('eligible_10k')})")
                return {
                    "success": True,
                    "is_logged_in": True,
                    "gpm_id": gpm_id,
                    "username": u_name,
                    "nickname": n_name,
                    "tiktok_uid": t_uid,
                    "sec_uid": s_uid,
                    "followers": f_count,
                    "eligible_10k": update_res.get("eligible_10k", False),
                    "scan_method": "browser_cdp",
                    "message": f"[Browser] Cập nhật thành công: @{u_name} ({f_count:,} followers)"
                }
            else:
                account_health.update_health_status(gpm_id, "unlogged", "Chưa đăng nhập TikTok trên profile này")
                log_event("WARNING", f"Profile GPM {gpm_id} chưa đăng nhập tài khoản TikTok nào.")
                return {
                    "success": False,
                    "is_logged_in": False,
                    "gpm_id": gpm_id,
                    "status": "unlogged",
                    "scan_method": "browser_cdp",
                    "message": "Chưa đăng nhập TikTok trên profile này (hoặc phiên đăng nhập đã hết hạn)"
                }

        except Exception as e:
            log_event("ERROR", f"Loi quet GPM profile {gpm_id}: {str(e)}")
            return {"success": False, "message": str(e)}
        finally:
            set_profile_busy(gpm_id, False)

    def stop_scan(self) -> Dict[str, Any]:
        """Dừng ngay tiến trình quét toàn bộ profile theo yêu cầu của người dùng"""
        global _cancel_scan_flag, _is_scanning_all, _scan_progress
        if not _is_scanning_all:
            return {"success": True, "message": "Hiện không có tiến trình quét nào đang chạy."}
        _cancel_scan_flag = True
        _scan_progress["message"] = "Đang dừng tiến trình quét..."
        log_event("WARNING", "🛑 [TIKTOK TRACKER] Nhận được tín hiệu DỪNG QUÉT từ người dùng.")
        return {"success": True, "message": "Đang dừng tiến trình quét..."}

    def get_scan_progress(self) -> Dict[str, Any]:
        """Lấy thông tin tiến độ quét trực tiếp thời gian thực"""
        global _scan_progress
        return dict(_scan_progress)

    def scan_all_profiles(self, delay_seconds: float = 1.5) -> Dict[str, Any]:
        """Quét toàn bộ danh sách profile GPM tuần tự với chế độ Low-RAM và hỗ trợ Dừng Quét"""
        global _is_scanning_all, _cancel_scan_flag, _scan_progress
        if _is_scanning_all:
            return {"success": False, "message": "Tiến trình quét toàn bộ profile đang chạy..."}

        _is_scanning_all = True
        _cancel_scan_flag = False
        # Tự động đồng bộ với GPMLogin trước khi quét để thêm profile mới và xóa profile đã bị xóa trên GPM
        try:
            active_gpm_list = gpm_client.get_profiles()
            if active_gpm_list:
                conn_sync = get_connection()
                cursor_sync = conn_sync.cursor()
                active_ids = set()
                for p in active_gpm_list:
                    active_ids.add(p["id"])
                    cursor_sync.execute('''
                        INSERT INTO gpm_profiles (gpm_id, name, raw_proxy)
                        VALUES (?, ?, ?)
                        ON CONFLICT(gpm_id) DO UPDATE SET
                            name = excluded.name,
                            raw_proxy = excluded.raw_proxy
                    ''', (p["id"], p["name"], p["raw_proxy"]))

                # Xóa các profile trong DB mà không còn tồn tại trên GPMLogin
                cursor_sync.execute("SELECT gpm_id, name FROM gpm_profiles")
                for db_p in cursor_sync.fetchall():
                    if db_p["gpm_id"] not in active_ids:
                        cursor_sync.execute("DELETE FROM gpm_profiles WHERE gpm_id = ?", (db_p["gpm_id"],))
                        log_event("INFO", f"[AUTO-SYNC] Đã xóa profile '{db_p['name']}' ({db_p['gpm_id']}) do không còn trên GPMLogin.")

                conn_sync.commit()
                conn_sync.close()
        except Exception as sync_err:
            log_event("WARNING", f"[TIKTOK TRACKER] Bỏ qua tự động đồng bộ trước khi quét: {sync_err}")

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, gpm_id, name, tiktok_username, followers_count FROM gpm_profiles ORDER BY id ASC")
            profiles = [dict(r) for r in cursor.fetchall()]
            conn.close()

            if not profiles:
                _scan_progress = {
                    "is_scanning": False, 
                    "current": 0,
                    "current_index": 0, 
                    "total": 0, 
                    "percent": 0, 
                    "status_message": "Không có profile nào",
                    "message": "Không có profile nào"
                }
                _is_scanning_all = False
                return {"success": True, "scanned": 0, "message": "Không có profile nào trong DB"}

            results = []
            success_count = 0
            total_cnt = len(profiles)

            # Khởi tạo trạng thái ban đầu để frontend hiển thị ngay
            first_name = profiles[0].get("name") or profiles[0].get("gpm_id")
            _scan_progress = {
                "is_scanning": True,
                "current": 1,
                "current_index": 1,
                "total": total_cnt,
                "current_profile_name": first_name,
                "current_gpm_id": profiles[0].get("gpm_id"),
                "percent": int((1 / total_cnt) * 100) if total_cnt > 0 else 0,
                "success_count": 0,
                "status_message": f"Đang quét [1/{total_cnt}]: {first_name}",
                "message": f"Đang quét [1/{total_cnt}]: {first_name}"
            }

            for i, p in enumerate(profiles):
                # Kiểm tra nếu người dùng bấm nút Dừng Quét
                if _cancel_scan_flag:
                    log_event("WARNING", "🛑 [TIKTOK TRACKER] Đã dừng quét tuần tự theo yêu cầu của người dùng.")
                    _scan_progress["status_message"] = "Đã dừng quét"
                    _scan_progress["message"] = "Đã dừng quét"
                    break

                gpm_id = p["gpm_id"]
                p_name = p.get("name") or gpm_id
                current_pct = int(((i + 1) / total_cnt) * 100)
                
                # Cập nhật trạng thái tiến độ thời gian thực (đầy đủ cả current và current_index)
                _scan_progress = {
                    "is_scanning": True,
                    "current": i + 1,
                    "current_index": i + 1,
                    "total": total_cnt,
                    "current_profile_name": p_name,
                    "current_gpm_id": gpm_id,
                    "percent": current_pct,
                    "success_count": success_count,
                    "status_message": f"Đang quét [{i+1}/{total_cnt}]: {p_name}",
                    "message": f"Đang quét [{i+1}/{total_cnt}]: {p_name}"
                }

                # Bỏ qua nếu profile đang bận upload video
                if is_profile_busy(gpm_id):
                    log_event("INFO", f"Bỏ qua profile {p_name} do đang bận upload bài...")
                    results.append({"gpm_id": gpm_id, "name": p_name, "status": "skipped_busy"})
                    continue

                res = self.scan_single_gpm_profile(gpm_id, auto_close=True)
                if res.get("success"):
                    success_count += 1
                _scan_progress["success_count"] = success_count
                results.append({"gpm_id": gpm_id, "name": p_name, **res})

                # Nghỉ ngắn giữa các profile và kiểm tra lại cờ dừng
                if i < total_cnt - 1 and not _cancel_scan_flag:
                    time.sleep(delay_seconds)

            summary_msg = f"Hoàn tất quét {len(results)}/{total_cnt} profiles: {success_count} thành công"
            log_event("INFO", f"🏁 [TIKTOK TRACKER] {summary_msg}")
            _scan_progress = {
                "is_scanning": False,
                "current": len(results),
                "current_index": len(results),
                "total": total_cnt,
                "current_profile_name": "",
                "percent": 100,
                "success_count": success_count,
                "status_message": summary_msg,
                "message": summary_msg
            }
            return {
                "success": True,
                "total": total_cnt,
                "scanned_count": len(results),
                "success_count": success_count,
                "cancelled": _cancel_scan_flag,
                "results": results,
                "message": summary_msg
            }
        finally:
            _is_scanning_all = False
            _cancel_scan_flag = False
            _scan_progress["is_scanning"] = False

tiktok_tracker = TikTokTracker()
