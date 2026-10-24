import json
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from backend.database import get_connection, log_event, log_campaign_event
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

    def handle_video_post_download(
        self,
        file_path: str,
        video_id: str,
        channel_id: str,
        channel_name: str,
        video_title: str,
        duration: float,
        channel_obj: dict,
        force_campaign_id: Optional[int] = None
    ):
        """
        Xử lý video sau khi tải về:
        1. Kiểm tra kênh này có thuộc Chiến Dịch (Campaign) nào đang hoạt động không.
        2. Nếu thuộc Campaign:
           - Áp dụng TOÀN BỘ công thức biên tập (Recipe) của Campaign:
             * video_duration (thời lượng mong muốn)
             * speed_factor (1.03x)
             * flip_horizontal (Lật video)
             * subtitle_enabled (Phụ đề Karaoke)
             * ai_provider & ai_model (Gemini / DeepSeek / OpenAI)
             * render_dir
           - Chạy quy trình Smart AI: Transcribe -> Chọn đoạn Viral -> Viết Hook/Title -> Render Anti-detect
           - Tự động phân phối và lên lịch đăng bài cho dàn nick GPM qua ContentDistributor
        3. Nếu không thuộc Campaign nhưng kênh bật auto_render:
           - Render theo thiết lập mặc định của kênh
        """
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (video_id,))
        v_row = cursor.fetchone()
        video_db_id = v_row["id"] if v_row else None

        if force_campaign_id:
            cursor.execute("SELECT * FROM campaigns WHERE id = ?", (force_campaign_id,))
        else:
            cursor.execute("SELECT * FROM campaigns WHERE is_active = 1")
        campaign_candidates = [dict(r) for r in cursor.fetchall()]
        conn.close()

        matched_campaigns = []
        for camp in campaign_candidates:
            ch_ids = []
            try:
                ch_ids = json.loads(camp.get("channel_ids") or "[]")
            except Exception:
                pass
            if not ch_ids and camp.get("channel_id"):
                ch_ids = [camp["channel_id"]]
            if channel_id in ch_ids or force_campaign_id == camp.get("id"):
                matched_campaigns.append(camp)

        if matched_campaigns:
            from backend.modules.ai_video_engine import ai_video_engine
            from backend.modules.distributor import distributor

            for camp in matched_campaigns:
                cid = camp["id"]
                log_campaign_event(cid, "INFO", "pipeline", f"Áp dụng công thức biên tập chiến dịch '{camp['name']}' cho video {video_id} ({video_title})")
                try:
                    res = ai_video_engine.process_smart_ai_video(
                        input_file=file_path,
                        video_id=video_id,
                        video_title=video_title,
                        channel_name=channel_name,
                        output_dir=camp.get("render_dir") or None,
                        custom_provider=camp.get("ai_provider"),
                        custom_model=camp.get("ai_model"),
                        enable_subtitles=bool(camp.get("subtitle_enabled", 0)),
                        target_duration=int(camp.get("video_duration") or 65),
                        flip_horizontal=bool(camp.get("flip_horizontal", 1)),
                        speed_factor=float(camp.get("speed_factor") or 1.03),
                        generate_hook=True
                    )
                    if res.get("status") == "success" and video_db_id:
                        log_campaign_event(cid, "SUCCESS", "render", f"Render Smart AI thành công video {video_id} -> {res.get('rendered_file')}")
                        distributor.schedule_campaign_upload(
                            video_id=video_db_id,
                            campaign=camp,
                            title=res.get("ai_title") or video_title,
                            tags=f"{res.get('ai_hashtags', '')}\n\n{res.get('ai_description', '')}"
                        )
                except Exception as e:
                    log_campaign_event(cid, "ERROR", "render", f"Lỗi render AI theo chiến dịch: {str(e)}")
        else:
            if channel_obj.get("auto_render", 1):
                try:
                    from backend.modules.ai_video_engine import ai_video_engine
                    ai_video_engine.auto_slice_and_render_parts(
                        input_file=file_path,
                        video_id=video_id,
                        total_duration=duration,
                        channel_name=channel_name,
                        video_title=video_title,
                        output_dir=channel_obj.get("render_dir") or None
                    )
                except Exception as re_err:
                    log_event("WARNING", f"Lỗi auto-render video {video_id}: {str(re_err)}")

    def get_effective_duration_limits(self, channel_id: str, force_campaign_id: Optional[int] = None) -> tuple[Optional[int], Optional[int]]:
        """
        Lấy ngưỡng thời lượng (min_seconds, max_seconds).
        Ưu tiên: Cài đặt riêng của chiến dịch liên quan > Cài đặt chung toàn cục > Mặc định (300s / 5 phút - 3600s / 1 giờ).
        """
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Đọc cài đặt toàn cục
        cursor.execute("SELECT key, value FROM settings WHERE key IN ('download_min_duration', 'download_max_duration')")
        db_s = dict(cursor.fetchall())
        global_min = int(db_s.get("download_min_duration", 300))
        global_max = int(db_s.get("download_max_duration", 3600))

        # 2. Tìm chiến dịch liên kết để kiểm tra ghi đè (override)
        camp_row = None
        if force_campaign_id:
            cursor.execute("SELECT min_video_duration, max_video_duration FROM campaigns WHERE id = ?", (force_campaign_id,))
            camp_row = cursor.fetchone()
        else:
            cursor.execute("SELECT id, channel_id, channel_ids, min_video_duration, max_video_duration FROM campaigns WHERE is_active = 1")
            for r in cursor.fetchall():
                c_dict = dict(r)
                c_ch_ids = []
                try:
                    c_ch_ids = json.loads(c_dict.get("channel_ids") or "[]")
                except Exception:
                    pass
                if not c_ch_ids and c_dict.get("channel_id"):
                    c_ch_ids = [c_dict["channel_id"]]
                if channel_id in c_ch_ids:
                    camp_row = r
                    break

        conn.close()

        eff_min = global_min
        eff_max = global_max
        if camp_row:
            cr = dict(camp_row)
            if cr.get("min_video_duration") is not None:
                eff_min = int(cr["min_video_duration"])
            if cr.get("max_video_duration") is not None:
                eff_max = int(cr["max_video_duration"])

        return eff_min, eff_max

    def scan_single_channel(self, channel_id: str, force_campaign_id: Optional[int] = None) -> Dict[str, Any]:
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

        ch_name = ch.get('display_name') or ch.get('title') or ""
        min_dur, max_dur = self.get_effective_duration_limits(channel_id, force_campaign_id)

        for v in videos:
            vid = v["video_id"]
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (vid,))
            exists = cursor.fetchone()
            conn.close()

            if not exists:
                log_event("INFO", f"Phát hiện video mới từ kênh '{ch_name}': {v['title']}")
                res = yt_downloader.download_video(
                    v["url"],
                    proxy=proxy,
                    target_dir=target_dir,
                    channel_name=ch_name,
                    min_duration=min_dur,
                    max_duration=max_dur
                )
                if res:
                    new_downloads += 1
                    new_items.append({"title": v["title"], "video_id": vid})

                    self.handle_video_post_download(
                        file_path=res.get("file_path"),
                        video_id=vid,
                        channel_id=channel_id,
                        channel_name=ch_name,
                        video_title=v["title"],
                        duration=res.get("duration", 65),
                        channel_obj=ch,
                        force_campaign_id=force_campaign_id
                    )

        return {
            "status": "success",
            "channel_id": channel_id,
            "title": ch_name,
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
            ch_name = ch.get("display_name") or ch.get("title") or ""
            proxy = ch.get("custom_proxy") or None
            target_dir = ch.get("download_dir") or None

            videos = self.check_channel_rss(ch_id)
            channel_downloaded = 0
            min_dur, max_dur = self.get_effective_duration_limits(ch_id)

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
                    log_event("INFO", f"Phát hiện video mới từ kênh '{ch_name}': {v['title']}")
                    res = yt_downloader.download_video(
                        v["url"],
                        proxy=proxy,
                        target_dir=target_dir,
                        channel_name=ch_name,
                        min_duration=min_dur,
                        max_duration=max_dur
                    )
                    if res:
                        total_new_downloaded += 1
                        channel_downloaded += 1

                        self.handle_video_post_download(
                            file_path=res.get("file_path"),
                            video_id=vid,
                            channel_id=ch_id,
                            channel_name=ch_name,
                            video_title=v["title"],
                            duration=res.get("duration", 65),
                            channel_obj=ch
                        )

        return total_new_downloaded

yt_monitor = YouTubeRSSMonitor()
