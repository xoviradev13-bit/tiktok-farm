import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from backend.database import get_connection, log_event
from backend.modules.yt_downloader import yt_downloader

class YouTubeRSSMonitor:
    """
    Giám sát kênh YouTube qua RSS Feed chính thức:
    - URL: https://www.youtube.com/feeds/videos.xml?channel_id=...
    - KHÔNG TỐN QUOTA API YouTube Data API v3
    - Tự động phát hiện video/shorts mới nhất
    """
    def check_channel_rss(self, channel_id: str) -> List[Dict[str, str]]:
        rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
        new_videos = []

        try:
            req = urllib.request.Request(
                rss_url,
                headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
            )
            with urllib.request.urlopen(req, timeout=10) as response:
                xml_data = response.read()

            root = ET.fromstring(xml_data)
            # Namespace của YouTube RSS
            ns = {
                "atom": "http://www.w3.org/2005/Atom",
                "yt": "http://www.youtube.com/xml/schemas/2015",
                "media": "http://search.yahoo.com/mrss/"
            }

            for entry in root.findall("atom:entry", ns):
                video_id_el = entry.find("yt:videoId", ns)
                title_el = entry.find("atom:title", ns)
                published_el = entry.find("atom:published", ns)

                if video_id_el is not None and title_el is not None:
                    vid = video_id_el.text
                    title = title_el.text
                    pub = published_el.text if published_el is not None else ""
                    new_videos.append({
                        "video_id": vid,
                        "title": title,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "published_at": pub
                    })

        except urllib.error.HTTPError as e:
            if e.code in [404, 410]:
                log_event("WARNING", f"Kênh {channel_id} không còn khả dụng hoặc đã bị xóa (HTTP {e.code})")
                self._mark_channel_unavailable(channel_id)
            else:
                log_event("WARNING", f"Lỗi HTTP khi đọc RSS kênh {channel_id}: {str(e)}")
        except Exception as e:
            log_event("WARNING", f"Ngoại lệ khi kiểm tra RSS kênh {channel_id}: {str(e)}")

        return new_videos

    def _mark_channel_unavailable(self, channel_id: str):
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE channels SET is_active = 0 WHERE channel_id = ?", (channel_id,))
        conn.commit()
        conn.close()

    def scan_single_channel(self, channel_id: str) -> Dict[str, Any]:
        """Quét ngay lập tức 1 kênh cụ thể và tải video mới nếu có"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return {"status": "error", "message": "Không tìm thấy kênh trong danh sách theo dõi", "new_videos": 0}

        ch = dict(row)
        proxy = ch.get("custom_proxy") or None
        target_dir = ch.get("download_dir") or None

        videos = self.check_channel_rss(channel_id)
        new_downloads = 0
        new_items = []

        for v in videos:
            vid = v["video_id"]
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (vid,))
            exists = cursor.fetchone()
            conn.close()

            if not exists:
                log_event("INFO", f"Phát hiện video mới từ kênh '{ch.get('display_name') or ch.get('title')}': {v['title']}")
                res = yt_downloader.download_video(v["url"], proxy=proxy, target_dir=target_dir)
                if res:
                    new_downloads += 1
                    new_items.append({"title": v["title"], "video_id": vid})

        return {
            "status": "success",
            "channel_id": channel_id,
            "title": ch.get("display_name") or ch.get("title"),
            "total_rss": len(videos),
            "new_videos": new_downloads,
            "items": new_items
        }

    def scan_all_monitored_channels(self, max_per_channel: int = 5, delay: float = 2.0) -> int:
        """Quét toàn bộ danh sách kênh theo dõi đang hoạt động (is_active = 1 và auto_download = 1)"""
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channels WHERE is_active = 1 AND auto_download = 1")
        channels = [dict(r) for r in cursor.fetchall()]
        conn.close()

        total_new_downloaded = 0
        for idx, ch in enumerate(channels):
            if idx > 0 and delay > 0:
                time.sleep(delay)

            ch_id = ch["channel_id"]
            proxy = ch.get("custom_proxy") or None
            target_dir = ch.get("download_dir") or None

            videos = self.check_channel_rss(ch_id)
            channel_downloaded = 0
            for v in videos:
                if max_per_channel > 0 and channel_downloaded >= max_per_channel:
                    break
                vid = v["video_id"]
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (vid,))
                exists = cursor.fetchone()
                conn.close()

                if not exists:
                    log_event("INFO", f"Phát hiện video mới từ kênh '{ch.get('display_name') or ch.get('title')}': {v['title']}")
                    res = yt_downloader.download_video(v["url"], proxy=proxy, target_dir=target_dir)
                    if res:
                        total_new_downloaded += 1
                        channel_downloaded += 1

        return total_new_downloaded

yt_monitor = YouTubeRSSMonitor()
