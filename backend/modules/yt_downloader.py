import os
from pathlib import Path
from typing import Dict, Any, Optional
import yt_dlp
from backend.config import DOWNLOADS_DIR
from backend.database import get_connection, log_event

class YouTubeDownloader:
    def __init__(self, download_dir: Path = DOWNLOADS_DIR):
        self.download_dir = download_dir

    def download_video(self, video_url: str, custom_filename: Optional[str] = None, proxy: Optional[str] = None, target_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Tải video/shorts YouTube chất lượng tốt nhất về thư mục local.
        Hỗ trợ proxy riêng và custom thư mục lưu.
        """
        save_dir = Path(target_dir) if target_dir and os.path.exists(target_dir) else self.download_dir
        save_dir.mkdir(parents=True, exist_ok=True)

        outtmpl = str(save_dir / (custom_filename or '%(id)s.%(ext)s'))
        ydl_opts = {
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'outtmpl': outtmpl,
            'quiet': False,
            'no_warnings': True,
            'ignoreerrors': False,
            'retries': 3,
        }
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

                video_id = info.get('id')
                title = info.get('title')
                duration = info.get('duration', 0)
                channel_id = info.get('channel_id')
                tags = ",".join(info.get('tags', [])[:10])

                # Tìm đường dẫn file đã lưu
                ext = info.get('ext', 'mp4')
                downloaded_file = str(self.download_dir / f"{video_id}.{ext}")
                if not os.path.exists(downloaded_file):
                    # Check file tương tự
                    for f in self.download_dir.glob(f"{video_id}.*"):
                        downloaded_file = str(f)
                        break

                # Lưu vào database
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                INSERT INTO videos (
                    channel_id, yt_video_id, title, original_url, duration, 
                    download_path, ai_tags, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'downloaded')
                ON CONFLICT(yt_video_id) DO UPDATE SET
                    download_path=excluded.download_path,
                    status='downloaded'
                ''', (channel_id, video_id, title, video_url, duration, downloaded_file, tags))
                
                cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (video_id,))
                row = cursor.fetchone()
                video_db_id = row[0] if row else None
                conn.commit()
                conn.close()

                log_event("INFO", f"Đã tải thành công video: {title} ({duration}s)")
                return {
                    "video_id": video_id,
                    "db_id": video_db_id,
                    "title": title,
                    "duration": duration,
                    "file_path": downloaded_file,
                    "tags": tags
                }

        except Exception as e:
            log_event("ERROR", f"Lỗi khi tải video {video_url}: {str(e)}")
            return None

yt_downloader = YouTubeDownloader()
