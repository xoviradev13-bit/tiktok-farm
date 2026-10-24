"""
gpm_profile_reader.py
---------------------
Đọc cookie và thông tin TikTok trực tiếp từ thư mục lưu trữ profile của ứng dụng GPMLogin
trên máy tính cục bộ (local disk) — HOÀN TOÀN KHÔNG CẦN MỞ BROWSER (ZeroRAM).

Hoạt động trên MỌI MÁY TÍNH có cài GPMLogin:
1. Tự động phát hiện đường dẫn lưu trữ profile của GPMLogin qua file `setting.dat`:
   - %APPDATA%\\GPMLoginGlobal\\setting.dat ("local_storage_path")
   - %APPDATA%\\GPMLogin\\setting.dat
   - Quét tất cả thư mục User trên máy Windows
   - Biến môi trường GPM_STORAGE_PATH (nếu muốn cấu hình thủ công)
   - Fallback về các thư mục mặc định của GPMLogin (Profiles)
2. Đọc file ExportCookies.json do GPMLogin tự động xuất trong mỗi profile:
   {storage_path}\\{profile_id}\\Default\\GPMSoft\\Exporter\\ExportCookies.json
3. Gọi TikTok API trực tiếp bằng requests HTTP (Passport API + Aweme Insight API):
   - Lấy username, screen_name, user_id
   - Lấy follower_count chính xác từ Aweme Insight API (/aweme/v2/data/insight/)
   - Lấy 7-day video views
   - Thời gian xử lý: ~0.3 - 0.8 giây/profile, 0MB RAM trình duyệt!
"""

import os
import json
import time
import re
import requests
from typing import Optional, Dict, Any, List
from concurrent.futures import ThreadPoolExecutor
from backend.database import log_event

# ─── GPMLOGIN STORAGE AUTO-DISCOVERY ─────────────────────────────────────────

def discover_gpm_storage_path() -> Optional[str]:
    """
    Tự động phát hiện đường dẫn thư mục chứa profile GPMLogin trên máy tính bất kỳ.
    Không hardcode đường dẫn người dùng.
    """
    # 1. Biến môi trường tuỳ chỉnh (nếu có cấu hình trong .env hoặc hệ thống)
    env_override = os.environ.get("GPM_STORAGE_PATH", "").strip()
    if env_override and os.path.isdir(env_override):
        return env_override

    # 2. Tìm trong setting.dat của GPMLogin / GPMLoginGlobal
    setting_candidates = []
    
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    
    if appdata:
        setting_candidates.extend([
            os.path.join(appdata, "GPMLoginGlobal", "setting.dat"),
            os.path.join(appdata, "GPMLogin", "setting.dat"),
        ])
    if localappdata:
        setting_candidates.extend([
            os.path.join(localappdata, "GPMLoginGlobal", "setting.dat"),
            os.path.join(localappdata, "GPMLogin", "setting.dat"),
        ])

    # Quét thêm tất cả profile user trên Windows (hỗ trợ multi-user)
    if os.name == "nt":
        sys_drive = os.environ.get("SYSTEMDRIVE", "C:")
        users_dir = os.path.join(sys_drive, "\\Users")
        if os.path.isdir(users_dir):
            try:
                for u in os.listdir(users_dir):
                    u_roaming = os.path.join(users_dir, u, "AppData", "Roaming")
                    setting_candidates.append(os.path.join(u_roaming, "GPMLoginGlobal", "setting.dat"))
                    setting_candidates.append(os.path.join(u_roaming, "GPMLogin", "setting.dat"))
            except Exception:
                pass

    for s_path in setting_candidates:
        if os.path.isfile(s_path):
            try:
                with open(s_path, "r", encoding="utf-8") as f:
                    setting_json = json.load(f)
                storage_path = setting_json.get("local_storage_path", "").strip()
                if storage_path and os.path.isdir(storage_path):
                    return storage_path
            except Exception:
                continue

    # 3. Fallback: Các thư mục Profiles mặc định thường gặp của GPMLogin
    fallback_candidates = []
    if appdata:
        fallback_candidates.extend([
            os.path.join(appdata, "GPMLoginGlobal", "Profiles"),
            os.path.join(appdata, "GPMLoginGlobal", "Data", "Profiles"),
            os.path.join(appdata, "GPMLogin", "Profiles"),
        ])
    if localappdata:
        fallback_candidates.extend([
            os.path.join(localappdata, "GPMLoginGlobal", "Profiles"),
            os.path.join(localappdata, "GPMLogin", "Profiles"),
        ])

    for fb in fallback_candidates:
        if os.path.isdir(fb):
            return fb

    return None


# Cache đường dẫn để tránh scan nhiều lần
_CACHED_GPM_STORAGE: Optional[str] = None

def get_gpm_storage_path(force_refresh: bool = False) -> Optional[str]:
    """Lấy đường dẫn storage của GPMLogin (dùng cache, tự refresh khi cần)"""
    global _CACHED_GPM_STORAGE
    if _CACHED_GPM_STORAGE and not force_refresh and os.path.isdir(_CACHED_GPM_STORAGE):
        return _CACHED_GPM_STORAGE
    _CACHED_GPM_STORAGE = discover_gpm_storage_path()
    return _CACHED_GPM_STORAGE


def is_gpm_reader_available() -> bool:
    """Kiểm tra máy hiện tại có thể đọc profile GPMLogin từ ổ đĩa không"""
    path = get_gpm_storage_path()
    return bool(path and os.path.isdir(path))


# ─── COOKIE & PROFILE EXTRACTION ──────────────────────────────────────────────

AUTH_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt"}

_CHROME_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.tiktok.com/tiktokstudio",
}


def find_profile_cookie_file(profile_id: str, storage_path_hint: Optional[str] = None) -> Optional[str]:
    """
    Tìm file cookies của profile GPMLogin trên ổ đĩa.
    Kiểm tra cả profile_id và storage_path_hint (nếu khác nhau).
    """
    base_storage = get_gpm_storage_path()
    if not base_storage or not os.path.isdir(base_storage):
        return None

    candidates = [profile_id]
    if storage_path_hint and storage_path_hint != profile_id:
        candidates.append(storage_path_hint)

    for pid in candidates:
        profile_dir = os.path.join(base_storage, pid)
        if not os.path.isdir(profile_dir):
            continue

        # 1. GPMSoft Exporter JSON (Ưu tiên số 1 - Plaintext đầy đủ do GPMLogin tự xuất)
        export_file = os.path.join(profile_dir, "Default", "GPMSoft", "Exporter", "ExportCookies.json")
        if os.path.isfile(export_file):
            return export_file

        # Fallback profile root exporter
        alt_export = os.path.join(profile_dir, "GPMSoft", "Exporter", "ExportCookies.json")
        if os.path.isfile(alt_export):
            return alt_export

    return None


def load_gpm_profile_cookies(profile_id: str, storage_path_hint: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Đọc danh sách cookie từ profile GPMLogin.
    Trả về list cookie dạng [{name: ..., value: ..., domain: ...}]
    """
    cookie_file = find_profile_cookie_file(profile_id, storage_path_hint)
    if not cookie_file:
        return None

    try:
        with open(cookie_file, "r", encoding="utf-8") as f:
            cookie_data = json.load(f)

        if not isinstance(cookie_data, list):
            return None

        # Lọc các cookie thuộc tiktok
        tt_cookies = [
            c for c in cookie_data 
            if isinstance(c, dict) and "tiktok" in c.get("domain", "")
        ]

        # Kiểm tra có cookie xác thực phiên không
        has_auth = any(c.get("name") in AUTH_COOKIE_NAMES for c in tt_cookies)
        if not has_auth:
            log_event("DEBUG", f"[GPMProfileReader] Profile {profile_id} không có sessionid TikTok.")
            return None

        return tt_cookies

    except Exception as e:
        log_event("ERROR", f"[GPMProfileReader] Lỗi đọc cookie file cho {profile_id}: {e}")
        return None


def build_requests_session(cookies: List[Dict[str, Any]]) -> requests.Session:
    """Tạo requests.Session đã cấu hình đầy đủ cookies & headers để gọi TikTok API"""
    sess = requests.Session()
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        domain = c.get("domain", ".tiktok.com").lstrip(".")
        path = c.get("path", "/")
        if name and value:
            sess.cookies.set(name, value, domain=domain, path=path)

    sess.headers.update(_CHROME_HEADERS)
    for c in cookies:
        if c.get("name") == "tt-target-idc":
            idc = c.get("value", "")
            if idc:
                sess.headers["tt-target-idc"] = idc
            break

    return sess


def fetch_account_info_from_gpm(profile_id: str, storage_path_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Lấy thông tin tài khoản TikTok (username, nickname, user_id, followers, views 7 ngày)
    trực tiếp từ file profile GPMLogin trên máy cục bộ.
    KHÔNG MỞ BROWSER (ZeroRAM).

    Trả về dict:
    {
        "found": bool,
        "is_logged_in": bool,
        "username": str | None,
        "nickname": str | None,
        "user_id": str | None,
        "followers": int,
        "views_7d": int,
        "source": "gpm_profile" | "no_profile" | "no_session" | "api_error",
        "message": str,
    }
    """
    cookies = load_gpm_profile_cookies(profile_id, storage_path_hint)
    if not cookies:
        cookie_file = find_profile_cookie_file(profile_id, storage_path_hint)
        if not cookie_file:
            return {
                "found": False,
                "is_logged_in": False,
                "username": None,
                "nickname": None,
                "user_id": None,
                "followers": 0,
                "views_7d": 0,
                "source": "no_profile",
                "message": f"Không tìm thấy file cookies cho profile GPM {profile_id} trên ổ đĩa."
            }
        else:
            return {
                "found": False,
                "is_logged_in": False,
                "username": None,
                "nickname": None,
                "user_id": None,
                "followers": 0,
                "views_7d": 0,
                "source": "no_session",
                "message": f"Profile {profile_id} chưa đăng nhập TikTok (không có cookie sessionid)."
            }

    sess = build_requests_session(cookies)

    username: Optional[str] = None
    nickname: Optional[str] = None
    user_id: Optional[str] = None
    followers: int = 0
    views_7d: int = 0
    is_logged_in: bool = False

    # ─── BƯỚC 1: TikTok Passport Session API (<1s, xác định user đăng nhập) ──
    try:
        r_pass = sess.get("https://www.tiktok.com/passport/web/account/info/?app_id=1233", timeout=8)
        if r_pass.status_code == 200:
            pdata = r_pass.json().get("data", {})
            if pdata.get("user_id"):
                is_logged_in = True
                user_id = str(pdata["user_id"])
                username = pdata.get("username") or pdata.get("screen_name")
                nickname = pdata.get("screen_name") or username
                log_event("DEBUG", f"[GPMProfileReader] {profile_id} Passport -> @{username} ({nickname})")
    except Exception as e:
        log_event("DEBUG", f"[GPMProfileReader] {profile_id} Passport API error: {e}")

    # ─── BƯỚC 2: TikTok Studio User API (Fallback nếu Passport thiếu user) ───
    if not username:
        try:
            studio_qs = (
                "aid=1988&app_name=tiktok_creator_center"
                "&device_platform=web_pc&channel=tiktok_web"
                "&os=win&browser_name=Mozilla&browser_platform=Win32"
            )
            r_st = sess.get(f"https://www.tiktok.com/tiktokstudio/api/web/user?{studio_qs}", timeout=8)
            if r_st.status_code == 200:
                ub = (r_st.json().get("userBaseInfo") or {}).get("UserProfile", {}).get("UserBase", {})
                if ub and ub.get("Id"):
                    is_logged_in = True
                    if not user_id:
                        user_id = str(ub["Id"])
                    if not username and ub.get("UniqId"):
                        username = ub["UniqId"]
                    if not nickname and ub.get("NickName"):
                        nickname = ub["NickName"]
        except Exception as e:
            log_event("DEBUG", f"[GPMProfileReader] {profile_id} Studio user API error: {e}")

    # ─── BƯỚC 3: Aweme Insight API (Lấy chính xác Follower Count & 7d Views) ─
    # Endpoint này trả về JSON trực tiếp mà không bị TikTok WAF 403 như trang cá nhân HTML
    try:
        tz_offset = -25200  # GMT+7
        type_req = json.dumps([
            {"insigh_type": "vv_history", "days": 7, "end_days": 1},
            {"insigh_type": "follower_num_history", "days": 7, "end_days": 1},
        ])
        r_aweme = sess.get(
            f"https://www.tiktok.com/aweme/v2/data/insight/?tz_offset={tz_offset}&type_requests={type_req}",
            timeout=8
        )
        if r_aweme.status_code == 200:
            adata = r_aweme.json()
            fn_hist = adata.get("follower_num_history") or []
            if fn_hist:
                for item in reversed(fn_hist):
                    if item.get("value") is not None:
                        followers = int(item["value"])
                        break
            vv_hist = adata.get("vv_history") or []
            if vv_hist:
                views_7d = sum(item.get("value", 0) for item in vv_hist if item.get("value"))
            log_event("DEBUG", f"[GPMProfileReader] {profile_id} Aweme Insight -> {followers:,} followers, {views_7d:,} 7d views")
    except Exception as e:
        log_event("DEBUG", f"[GPMProfileReader] {profile_id} Aweme Insight API error: {e}")

    # ─── BƯỚC 4: Fallback trang cá nhân công khai (Nếu Insight chưa có số) ───
    if is_logged_in and username and followers == 0:
        try:
            u_clean = username.lstrip("@").strip()
            r_page = sess.get(f"https://www.tiktok.com/@{u_clean}", timeout=10)
            if r_page.status_code == 200:
                html = r_page.text
                rehy_match = re.search(r'<script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"[^>]*>([\s\S]*?)</script>', html)
                if rehy_match:
                    try:
                        parsed = json.loads(rehy_match.group(1))
                        stats = (
                            parsed
                            .get("__DEFAULT_SCOPE__", {})
                            .get("webapp.user-detail", {})
                            .get("userInfo", {})
                            .get("stats", {})
                        )
                        fc = stats.get("followerCount")
                        if fc:
                            followers = int(fc)
                    except Exception:
                        pass
                if not followers:
                    fm = re.search(r'"followerCount":\s*(\d+)', html) or re.search(r'"fanCount":\s*(\d+)', html)
                    if fm:
                        followers = int(fm.group(1))
        except Exception:
            pass

    if not is_logged_in or not username:
        return {
            "found": False,
            "is_logged_in": False,
            "username": None,
            "nickname": None,
            "user_id": None,
            "followers": 0,
            "views_7d": 0,
            "source": "api_error",
            "message": f"Cookie profile {profile_id} đã hết hạn hoặc bị TikTok từ chối."
        }

    log_event("INFO", f"✅ [GPMZeroRAM] {profile_id}: @{username} ({nickname}) - {followers:,} followers (0 browser)")
    return {
        "found": True,
        "is_logged_in": True,
        "username": username.lstrip("@").strip(),
        "nickname": nickname,
        "user_id": user_id,
        "followers": followers,
        "views_7d": views_7d,
        "source": "gpm_profile",
        "message": f"OK: @{username} ({followers:,} followers)"
    }


def list_gpm_profiles_status() -> Dict[str, Any]:
    """
    Kiểm tra trạng thái cookie của các profile GPMLogin ĐANG HOẠT ĐỘNG trong GPMLogin App.
    Chỉ áp dụng cho các profile có mặt trong GPMLogin App (lấy qua gpm_client.get_profiles),
    bỏ qua các thư mục rác, backup hoặc profile đã bị xoá trên ổ đĩa.
    """
    from backend.modules.gpm_client import gpm_client

    storage_path = get_gpm_storage_path()
    if not storage_path or not os.path.isdir(storage_path):
        return {
            "available": False,
            "storage_path": None,
            "total_profiles": 0,
            "logged_in_count": 0,
            "profiles": []
        }

    # 1. Lấy danh sách profile ĐANG ACTIVE trong GPMLogin App
    active_gpm_profiles = gpm_client.get_profiles()
    
    profiles_status = []
    logged_in_count = 0

    if active_gpm_profiles:
        # Chỉ quét các profile đang tồn tại trong GPMLogin App
        for p in active_gpm_profiles:
            pid = p["id"]
            p_name = p.get("name", pid)
            export_file = os.path.join(storage_path, pid, "Default", "GPMSoft", "Exporter", "ExportCookies.json")
            has_file = os.path.isfile(export_file)
            has_session = False
            mtime = None

            if has_file:
                try:
                    mtime = os.path.getmtime(export_file)
                    with open(export_file, "r", encoding="utf-8") as f:
                        cookies = json.load(f)
                    has_session = any(
                        isinstance(c, dict) and c.get("name") == "sessionid" and "tiktok" in c.get("domain", "")
                        for c in cookies
                    )
                except Exception:
                    pass

            if has_session:
                logged_in_count += 1

            profiles_status.append({
                "profile_id": pid,
                "name": p_name,
                "has_cookie_file": has_file,
                "has_sessionid": has_session,
                "is_active_in_gpm": True,
                "last_updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)) if mtime else None
            })

        return {
            "available": True,
            "storage_path": storage_path,
            "total_profiles": len(active_gpm_profiles),
            "logged_in_count": logged_in_count,
            "profiles": profiles_status
        }

    # 2. Fallback: Nếu GPMLogin App tắt API, quét thư mục storage trên ổ đĩa
    try:
        entries = [
            d for d in os.listdir(storage_path)
            if os.path.isdir(os.path.join(storage_path, d)) and not d.startswith(".") and d != "_backup"
        ]
    except Exception as e:
        log_event("ERROR", f"[GPMProfileReader] Lỗi đọc thư mục {storage_path}: {e}")
        return {
            "available": False,
            "storage_path": storage_path,
            "total_profiles": 0,
            "logged_in_count": 0,
            "profiles": []
        }

    for pid in entries:
        export_file = os.path.join(storage_path, pid, "Default", "GPMSoft", "Exporter", "ExportCookies.json")
        has_file = os.path.isfile(export_file)
        has_session = False
        mtime = None

        if has_file:
            try:
                mtime = os.path.getmtime(export_file)
                with open(export_file, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                has_session = any(
                    isinstance(c, dict) and c.get("name") == "sessionid" and "tiktok" in c.get("domain", "")
                    for c in cookies
                )
            except Exception:
                pass

        if has_session:
            logged_in_count += 1

        profiles_status.append({
            "profile_id": pid,
            "name": pid,
            "has_cookie_file": has_file,
            "has_sessionid": has_session,
            "is_active_in_gpm": False,
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)) if mtime else None
        })

    return {
        "available": True,
        "storage_path": storage_path,
        "total_profiles": len(entries),
        "logged_in_count": logged_in_count,
        "profiles": profiles_status
    }
