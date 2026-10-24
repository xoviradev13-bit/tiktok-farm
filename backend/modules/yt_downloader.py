import os
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp
from backend.config import DOWNLOADS_DIR
from backend.database import get_connection, log_event
from backend.logger import get_logger

logger = get_logger("yt_downloader")

class YouTubeDownloader:
    def __init__(self, download_dir: Path = DOWNLOADS_DIR):
        self.download_dir = download_dir

    def download_video(
        self,
        video_url: str,
        custom_filename: Optional[str] = None,
        proxy: Optional[str] = None,
        target_dir: Optional[str] = None,
        channel_name: Optional[str] = None,
        min_duration: Optional[int] = None,
        max_duration: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Tải video/shorts YouTube chất lượng tốt nhất về thư mục local.
        Hỗ trợ proxy riêng, custom thư mục lưu, bộ lọc thời lượng và định dạng tên file thông minh.
        """
        from backend.modules.ai_video_engine import sanitize_filename

        save_dir = Path(target_dir) if target_dir and os.path.exists(target_dir) else self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        if custom_filename:
            # Ngăn chặn Path Traversal theo chuẩn OWASP A01 & NIST SP 800-218
            safe_name = Path(custom_filename).name
            outtmpl = str(save_dir / safe_name)
        elif channel_name:
            safe_ch = sanitize_filename(channel_name, 25)
            outtmpl = str(save_dir / f"[{safe_ch}]_%(title).35s_[%(id)s].%(ext)s")
        else:
            outtmpl = str(save_dir / "[%(uploader)s]_%(title).35s_[%(id)s].%(ext)s")

        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': outtmpl,
            'quiet': False,
            'no_warnings': True,
            'ignoreerrors': False,
            'retries': 5,
            'fragment_retries': 5,
            # Use node.js as JS runtime (node v20 is installed; deno is not)
            # Format must be a dict: {runtime_name: {config}}
            'js_runtimes': {'node': {}},
            # Robust player client fallback order
            'extractor_args': {
                'youtube': {
                    'player_client': ['web', 'android', 'ios'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }

        # Filter duration before downloading if specified
        if min_duration is not None or max_duration is not None:
            def duration_filter(info_dict, *, incomplete=False):
                dur = info_dict.get('duration')
                if dur is not None:
                    if min_duration is not None and dur < min_duration:
                        return f"Thời lượng video ({dur}s) ngắn hơn mức tối thiểu ({min_duration}s)"
                    if max_duration is not None and dur > max_duration:
                        return f"Thời lượng video ({dur}s) dài hơn mức tối đa ({max_duration}s)"
                return None
            ydl_opts['match_filter'] = duration_filter

        if proxy and proxy.strip():
            p = proxy.strip()
            if not p.startswith("http://") and not p.startswith("https://") and not p.startswith("socks5://"):
                p = f"http://{p}"
            ydl_opts['proxy'] = p

        # Check for cookies.txt if exists
        cookies_file = Path("cookies.txt")
        if cookies_file.exists():
            ydl_opts['cookiefile'] = str(cookies_file.absolute())

        try:
            log_event("INFO", f"Bắt đầu tải video: {video_url}")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=True)
                if not info:
                    return None

                if info.get('_match_filter_reason'):
                    log_event("INFO", f"Bỏ qua tải '{info.get('title', video_url)}': {info.get('_match_filter_reason')}")
                    return None

                video_id = info.get('id')
                title = info.get('title')
                duration = info.get('duration', 0)
                channel_id = info.get('channel_id')
                tags = ",".join(info.get('tags', [])[:10])

                # Secondary safeguard for duration
                if min_duration is not None and duration and duration < min_duration:
                    log_event("INFO", f"Bỏ qua video '{title}' ({duration}s): ngắn hơn tối thiểu {min_duration}s")
                    return None
                if max_duration is not None and duration and duration > max_duration:
                    log_event("INFO", f"Bỏ qua video '{title}' ({duration}s): dài hơn tối đa {max_duration}s")
                    return None

                # Tìm đường dẫn file đã lưu chính xác
                downloaded_file = ydl.prepare_filename(info)
                if not os.path.exists(downloaded_file):
                    base_stem = os.path.splitext(downloaded_file)[0]
                    for ext_cand in ["mp4", "mkv", "webm", "m4a"]:
                        cand = f"{base_stem}.{ext_cand}"
                        if os.path.exists(cand):
                            downloaded_file = cand
                            break
                if not os.path.exists(downloaded_file):
                    for f in save_dir.glob(f"*{video_id}*"):
                        downloaded_file = str(f)
                        break
                    else:
                        for f in self.download_dir.glob(f"*{video_id}*"):
                            downloaded_file = str(f)
                            break

                if not os.path.exists(downloaded_file):
                    warn_msg = f"Không tìm thấy file tải về cho video '{title}' ({video_url})"
                    log_event("WARNING", warn_msg)
                    return {"success": False, "message": warn_msg}

                # Lưu vào database
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO videos (
                    channel_id, yt_video_id, title, original_url, duration, 
                    download_path, ai_tags, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'downloaded', NULL)
                ON CONFLICT(yt_video_id) DO UPDATE SET
                    download_path=excluded.download_path,
                    status='downloaded',
                    error_message=NULL
                ''', (channel_id, video_id, title, video_url, duration, downloaded_file, tags))
                
                cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (video_id,))
                row = cursor.fetchone()
                video_db_id = row[0] if row else None
                conn.commit()
                conn.close()

                log_event("INFO", f"Đã tải thành công video: {title} ({duration}s)")
                return {
                    "success": True,
                    "video_id": video_id,
                    "db_id": video_db_id,
                    "title": title,
                    "duration": duration,
                    "file_path": downloaded_file,
                    "tags": tags
                }

        except Exception as e:
            err_str = str(e)
            classified = classify_youtube_error(err_str)
            logger.exception(f"Lỗi tải video YouTube {video_url} [{classified['type']}]: {err_str}")
            log_event("ERROR", f"[{classified['title']}] {classified['message']} (URL: {video_url})", details=err_str)

            # Cố gắng lưu trạng thái lỗi vào DB nếu nhận dạng được video ID
            try:
                import re
                m = re.search(r'(?:v=|\/shorts\/|\/be\/)([a-zA-Z0-9_-]{11})', video_url)
                if m:
                    extracted_id = m.group(1)
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute('''
                        INSERT INTO videos (yt_video_id, original_url, status, error_message)
                        VALUES (?, ?, 'error', ?)
                        ON CONFLICT(yt_video_id) DO UPDATE SET
                            status = 'error',
                            error_message = excluded.error_message
                    ''', (extracted_id, video_url, classified["message"]))
                    conn.commit()
                    conn.close()
            except Exception:
                pass

            return {
                "success": False,
                "error": classified,
                "message": classified["message"]
            }

def classify_youtube_error(err_str: str) -> Dict[str, str]:
    """Phân loại chi tiết nguyên nhân lỗi tải YouTube cho người dùng và giao diện UI"""
    err_lower = err_str.lower()
    if any(k in err_lower for k in ("proxy", "tunnel connection failed", "connection refused", "proxyerror", "socks5")):
        return {
            "type": "PROXY_ERROR",
            "title": "Lỗi Kết Nối Proxy",
            "message": "Không thể kết nối qua Proxy YouTube (Proxy chết, timeout hoặc sai thông tin xác thực). Vui lòng kiểm tra lại cấu hình Proxy.",
            "action": "check_proxy"
        }
    elif any(k in err_lower for k in ("sign in to confirm you're not a bot", "bot confirmation", "confirm you're not a bot", "bot detection")):
        return {
            "type": "BOT_DETECTION",
            "title": "YouTube Chặn Bot Detection",
            "message": "YouTube yêu cầu xác minh bot. Cần bổ sung file cookies.txt tại thư mục gốc, cài Node.js runtime hoặc đổi IP proxy.",
            "action": "add_cookies"
        }
    elif "private video" in err_lower:
        return {
            "type": "VIDEO_PRIVATE",
            "title": "Video Riêng Tư",
            "message": "Video này được tác giả đặt ở chế độ riêng tư và không thể tải về.",
            "action": "skip_video"
        }
    elif any(k in err_lower for k in ("video unavailable", "has been removed", "deleted")):
        return {
            "type": "VIDEO_UNAVAILABLE",
            "title": "Video Không Khả Dụng",
            "message": "Video đã bị xóa hoặc không còn tồn tại trên YouTube.",
            "action": "skip_video"
        }
    elif any(k in err_lower for k in ("age-restricted", "sign in to confirm your age")):
        return {
            "type": "AGE_RESTRICTED",
            "title": "Video Giới Hạn Độ Tuổi",
            "message": "Video bị giới hạn độ tuổi 18+, yêu cầu tài khoản đã đăng nhập qua file cookies.txt.",
            "action": "add_cookies"
        }
    elif any(k in err_lower for k in ("georestricted", "not available in your country")):
        return {
            "type": "GEO_RESTRICTED",
            "title": "Video Giới Hạn Vùng Địa Lý",
            "message": "Video bị chặn theo quốc gia. Hãy sử dụng proxy hoặc VPN phù hợp với quốc gia của kênh.",
            "action": "use_proxy"
        }
    elif any(k in err_lower for k in ("js runtime", "deno", "node")):
        return {
            "type": "JS_RUNTIME_MISSING",
            "title": "Thiếu Node.js Runtime",
            "message": "yt-dlp cần Node.js để giải mã thuật toán YouTube signature. Vui lòng cài đặt Node.js trên máy.",
            "action": "install_nodejs"
        }
    elif "ffmpeg" in err_lower:
        return {
            "type": "FFMPEG_MISSING",
            "title": "Lỗi FFmpeg Ghép File",
            "message": "Không tìm thấy FFmpeg để ghép luồng video + audio chất lượng cao.",
            "action": "install_ffmpeg"
        }
    else:
        return {
            "type": "GENERAL_DOWNLOAD_ERROR",
            "title": "Lỗi Tải Video YouTube",
            "message": f"Không thể tải video: {err_str[:220]}",
            "action": "retry"
        }

yt_downloader = YouTubeDownloader()
