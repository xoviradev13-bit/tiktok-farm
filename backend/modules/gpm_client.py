import requests
from typing import List, Dict, Optional, Any
from backend.config import GPM_API_BASE_URL
from backend.database import log_event

# Các cổng thường dùng của GPMLogin (trích từ agent.js)
GPM_PORT_CANDIDATES = [9495, 9496, 19995, 19996, 19994, 8848]

class GPMClient:
    def __init__(self, base_url: str = GPM_API_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self.cached_working_base: Optional[str] = None

    def discover_api_base(self) -> Optional[str]:
        """Tự động dò cổng và phiên bản API (v1 / v3) của GPMLogin giống agent.js"""
        if self.cached_working_base:
            try:
                r = requests.get(f"{self.cached_working_base}/profiles?page=1&per_page=1", timeout=1.5)
                if r.status_code == 200:
                    return self.cached_working_base
            except Exception:
                self.cached_working_base = None

        # Dò qua các cổng ứng viên và versions với socket check siêu tốc
        import socket
        for port in GPM_PORT_CANDIDATES:
            # Kiểm tra nhanh cổng có đang mở không trước khi gửi HTTP request
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.06)
                    if s.connect_ex(("127.0.0.1", port)) != 0:
                        continue
            except Exception:
                continue

            for ver in ["v1", "v3"]:
                base = f"http://127.0.0.1:{port}/api/{ver}"
                try:
                    r = requests.get(f"{base}/profiles?page=1&per_page=1", timeout=1.0)
                    if r.status_code == 200:
                        data = r.json()
                        if isinstance(data, dict) and data.get("success"):
                            self.cached_working_base = base
                            return base
                except Exception:
                    continue

        return None

    def check_health(self) -> Dict[str, Any]:
        """Kiểm tra GPMLogin App có đang chạy trên máy không"""
        base = self.discover_api_base()
        if not base:
            return {
                "running": False,
                "profile_count": 0,
                "message": "Không thể kết nối GPMLogin API (Đã dò cổng 9495, 19995...)"
            }

        try:
            r = requests.get(f"{base}/profiles?page=1&per_page=100", timeout=3)
            if r.status_code == 200:
                json_data = r.json()
                total = 0
                data_field = json_data.get("data", {})
                if isinstance(data_field, dict):
                    total = data_field.get("total", len(data_field.get("data", [])))
                elif isinstance(data_field, list):
                    total = len(data_field)

                return {
                    "running": True,
                    "profile_count": total,
                    "base_url": base,
                    "message": f"GPMLogin đang online tại {base} ({total} profiles)"
                }
        except Exception as e:
            pass

        return {
            "running": False,
            "profile_count": 0,
            "message": "Không thể kết nối GPMLogin API"
        }

    def ensure_gpm_running(self) -> bool:
        """Kiểm tra nếu GPMLogin đang tắt thì tự động bật lên"""
        import os, time, subprocess
        status = self.check_health()
        if status.get("running"):
            return True

        candidates = [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\GPMLoginGlobal\GPMLoginGlobal.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\GPMLogin\GPMLogin.exe"),
            os.path.expandvars(r"%PROGRAMFILES%\GPMLoginGlobal\GPMLoginGlobal.exe"),
            r"C:\Program Files\GPMLogin\GPMLogin.exe",
            r"C:\Program Files (x86)\GPMLogin\GPMLogin.exe",
            os.path.expandvars(r"%APPDATA%\GPMLogin\GPMLogin.exe"),
        ]
        exe_path = None
        for p in candidates:
            if os.path.exists(p):
                exe_path = p
                break

        if exe_path:
            log_event("INFO", f"Phát hiện GPMLogin đang tắt. Đang tự động khởi chạy ứng dụng: {exe_path}")
            try:
                subprocess.Popen([exe_path], shell=False)
                # GPMLogin là ứng dụng Electron Desktop, chờ tối đa 30 giây để API local khởi động hoàn tất
                for attempt in range(1, 31):
                    time.sleep(1)
                    health = self.check_health()
                    if health.get("running"):
                        log_event("INFO", f"GPMLogin đã khởi động thành công và API sẵn sàng sau {attempt}s ({health.get('base_url')})!")
                        return True
                log_event("WARNING", "Đã khởi chạy GPMLogin nhưng API chưa sẵn sàng sau 30s. Vui lòng kiểm tra cửa sổ GPMLogin.")
            except Exception as e:
                log_event("ERROR", f"Không thể tự động bật GPMLogin: {e}")

        return False

    def get_profiles(self) -> List[Dict[str, Any]]:
        """Lấy toàn bộ danh sách profile từ GPMLogin (chuẩn pagination như agent.js)"""
        base = self.discover_api_base()
        if not base:
            self.ensure_gpm_running()
            base = self.discover_api_base()
        if not base:
            return []

        try:
            r = requests.get(f"{base}/profiles?page=1&per_page=100", timeout=5)
            if r.status_code == 200:
                json_data = r.json()
                data_field = json_data.get("data", {})
                rows = []
                if isinstance(data_field, dict):
                    rows = data_field.get("data", [])
                elif isinstance(data_field, list):
                    rows = data_field

                formatted = []
                for p in rows:
                    p_id = p.get("id") or p.get("profile_id")
                    if not p_id:
                        continue
                    formatted.append({
                        "id": str(p_id),
                        "name": p.get("name", f"Profile {p_id}"),
                        "raw_proxy": p.get("raw_proxy", "") or p.get("proxy", ""),
                        "group_id": p.get("group_id", ""),
                        "created_at": p.get("created_at", "")
                    })
                return formatted
        except Exception as e:
            log_event("WARNING", f"Lỗi lấy danh sách GPM profiles: {str(e)}")
        return []

    def start_profile(self, profile_id: str, target_url: str = "", low_ram_mode: bool = False) -> Optional[str]:
        """
        Khởi chạy profile trên GPMLogin
        Trả về remote_debugging_address (VD: 127.0.0.1:12345)
        - Tự động mở phần mềm GPMLogin nếu đang tắt.
        - low_ram_mode=True: Tiết kiệm tối đa RAM (tắt GPU, tắt load ảnh, ẩn cửa sổ offscreen)
        """
        base = self.discover_api_base()
        if not base:
            log_event("INFO", f"GPMLogin API chưa kết nối. Đang kích hoạt tự động mở GPMLogin để mở profile {profile_id}...")
            self.ensure_gpm_running()
            base = self.discover_api_base()
        if not base:
            log_event("WARNING", f"Không thể kết nối GPMLogin API sau khi thử tự mở. Vui lòng kiểm tra phần mềm GPMLogin.")
            return None

        def _do_start(api_base: str) -> Optional[str]:
            url = f"{api_base}/profiles/start/{profile_id}?skip_proxy_check=true"
            args_list = []
            if low_ram_mode:
                args_list.extend([
                    "--window-position=-2400,-2400",
                    "--window-size=240,240",
                    "--blink-settings=imagesEnabled=false",
                    "--disable-gpu",
                    "--disable-software-rasterizer",
                    "--mute-audio",
                    "--no-first-run"
                ])
            if target_url:
                args_list.append(target_url)

            if args_list:
                import urllib.parse
                combined_args = " ".join(args_list)
                encoded_args = urllib.parse.quote(combined_args)
                url += f"&addition_args={encoded_args}"
                if target_url:
                    url += f"&url={urllib.parse.quote(target_url)}"

            resp = requests.get(url, timeout=30)
            if resp.status_code == 200:
                json_data = resp.json()
                if json_data.get("success") is False:
                    log_event("ERROR", f"GPM trả về lỗi khi mở profile {profile_id}: {json_data.get('message')}")
                    return None

                data = json_data.get("data", {})
                if not isinstance(data, dict):
                    data = json_data

                remote_addr = self._extract_debug_address(data)
                if remote_addr:
                    log_event("INFO", f"Khởi động thành công GPM profile {profile_id} tại {remote_addr}")
                    return remote_addr

            log_event("ERROR", f"Không trích xuất được debug port từ GPM cho profile {profile_id}: {resp.text}")
            return None

        try:
            return _do_start(base)
        except requests.exceptions.ConnectionError as conn_err:
            log_event("WARNING", f"Mất kết nối tới GPMLogin API khi mở profile {profile_id}. Đang thử tự khởi động lại GPMLogin...")
            if self.ensure_gpm_running():
                new_base = self.discover_api_base()
                if new_base:
                    try:
                        return _do_start(new_base)
                    except Exception as retry_err:
                        log_event("ERROR", f"Lỗi thử lại sau khi bật GPMLogin: {retry_err}")
            return None
        except Exception as e:
            log_event("ERROR", f"Ngoại lệ khi mở profile GPM {profile_id}: {str(e)}")
            return None

    def stop_profile(self, profile_id: str) -> bool:
        """Đóng profile trên GPMLogin (hỗ trợ cả /stop và /close)"""
        base = self.discover_api_base()
        if not base:
            return False

        endpoints = [
            f"{base}/profiles/stop/{profile_id}",
            f"{base}/profiles/close/{profile_id}"
        ]
        for url in endpoints:
            try:
                resp = requests.get(url, timeout=8)
                if resp.status_code == 200:
                    return True
            except Exception:
                continue
        return False

    def _extract_debug_address(self, data: Dict[str, Any]) -> Optional[str]:
        """Trích xuất địa chỉ remote debug port (chuẩn trích từ agent.js:extractDebugPortFromProfile)"""
        candidates = [
            data.get("remote_debugging_address"),
            data.get("debugger_address"),
            data.get("remote_debugging_port"),
            data.get("debug_port"),
            data.get("websocket_debugging_url")
        ]
        for raw in candidates:
            if not raw:
                continue
            s_raw = str(raw)
            if "127.0.0.1:" in s_raw or "localhost:" in s_raw:
                return s_raw
            if s_raw.isdigit():
                return f"127.0.0.1:{s_raw}"
            if ":" in s_raw:
                parts = s_raw.split(":")
                port = parts[-1].split("/")[0]
                if port.isdigit():
                    return f"127.0.0.1:{port}"
        return None

gpm_client = GPMClient()
