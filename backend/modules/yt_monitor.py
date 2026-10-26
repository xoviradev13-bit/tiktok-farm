import json
import time
import urllib.request
import urllib.error
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
                
                # Lấy toàn bộ cài đặt render hiệu lực: Kênh > Chiến dịch > Toàn cục
                sub_settings = self.get_effective_subtitle_settings(channel_obj, camp)
                render_settings = self.get_effective_render_settings(channel_obj, camp)

                try:
                    res = ai_video_engine.process_smart_ai_video(
                        input_file=file_path,
                        video_id=video_id,
                        video_title=video_title,
                        channel_name=channel_name,
                        output_dir=render_settings["render_dir"],
                        custom_provider=camp.get("ai_provider"),
                        custom_model=camp.get("ai_model"),
                        enable_subtitles=sub_settings["enable_subtitles"],
                        target_duration=int(camp.get("video_duration") or 65),
                        flip_horizontal=bool(camp.get("flip_horizontal", 1)),
                        speed_factor=float(camp.get("speed_factor") or 1.03),
                        add_part_label=bool(camp.get("add_part_label", 1)),
                        generate_hook=True,
                        clips_count=int(camp.get("clips_per_video") or 1),
                        subtitle_style=sub_settings["subtitle_style"],
                        subtitle_position=sub_settings["subtitle_position"],
                        bgm_folder=render_settings["bgm_folder"],
                        bgm_volume=render_settings["bgm_volume"],
                        disable_subtitle_for_shorts=sub_settings["disable_subtitle_for_shorts"]
                    )
                    if res.get("status") == "success" and video_db_id:
                        rendered_files = res.get("rendered_files") or ([res.get("rendered_file")] if res.get("rendered_file") else [])
                        log_campaign_event(cid, "SUCCESS", "render", f"Render Smart AI thành công video {video_id} ({len(rendered_files)} clip) -> {rendered_files[0] if rendered_files else ''}")
                        
                        assigned_profile_id = None
                        for idx, r_file in enumerate(rendered_files, 1):
                            part_title = res.get("ai_title") or video_title
                            if len(rendered_files) > 1 and f"Part {idx}" not in part_title:
                                part_title = f"{part_title} - Part {idx}"
                            
                            sched_res = distributor.schedule_campaign_upload(
                                video_id=video_db_id,
                                campaign=camp,
                                title=part_title,
                                tags=f"{res.get('ai_hashtags', '')}\n\n{res.get('ai_description', '')}",
                                video_path=r_file,
                                part_number=idx,
                                force_profile_id=assigned_profile_id
                            )
                            # Khóa cùng 1 profile GPM cho chuỗi Part 1, Part 2, Part 3... để người xem theo dõi liền mạch
                            if sched_res and not assigned_profile_id:
                                assigned_profile_id = sched_res.get("profile_id")
                except Exception as e:
                    log_campaign_event(cid, "ERROR", "render", f"Lỗi render AI theo chiến dịch: {str(e)}")
        else:
            if channel_obj.get("auto_render", 1):
                try:
                    from backend.modules.ai_video_engine import ai_video_engine
                    sub_settings = self.get_effective_subtitle_settings(channel_obj, None)
                    render_settings = self.get_effective_render_settings(channel_obj, None)
                    ai_video_engine.auto_slice_and_render_parts(
                        input_file=file_path,
                        video_id=video_id,
                        total_duration=int(duration or 65),
                        channel_name=channel_name,
                        video_title=video_title,
                        output_dir=render_settings["render_dir"],
                        enable_subtitles=sub_settings["enable_subtitles"],
                        subtitle_style=sub_settings["subtitle_style"],
                        subtitle_position=sub_settings["subtitle_position"],
                        bgm_folder=render_settings["bgm_folder"],
                        bgm_volume=render_settings["bgm_volume"],
                        disable_subtitle_for_shorts=sub_settings["disable_subtitle_for_shorts"]
                    )
                except Exception as re_err:
                    log_event("WARNING", f"Lỗi auto-render video {video_id}: {str(re_err)}")

    def get_effective_render_settings(self, channel_obj: Optional[dict], camp: Optional[dict] = None) -> dict:
        """
        Lấy cài đặt render hiệu lực theo thứ tự ưu tiên chặt chẽ:
        Kênh (Channel) > Chiến dịch (Campaign) > Toàn cục (Global).
        
        Bao gồm: render_dir, bgm_folder, bgm_volume
        """
        import os
        from backend.config import RENDERED_DIR

        # === Global defaults ===
        global_render_dir = str(RENDERED_DIR)
        global_bgm_folder = ""
        global_bgm_volume = 0.15

        # === Campaign level ===
        camp_render_dir = (camp.get("render_dir") or "").strip() if camp else ""
        camp_bgm_folder = (camp.get("bgm_folder") or "").strip() if camp else ""
        camp_bgm_volume = camp.get("bgm_volume") if camp else None

        # === Channel level (highest priority) ===
        ch_render_dir = (channel_obj.get("render_dir") or "").strip() if channel_obj else ""
        ch_bgm_folder = (channel_obj.get("bgm_folder") or "").strip() if channel_obj else ""
        ch_bgm_volume = channel_obj.get("bgm_volume") if channel_obj else None

        # === Apply Ch > Camp > Global ===

        # 1) render_dir: Channel > Campaign > Global
        if ch_render_dir and os.path.exists(ch_render_dir):
            eff_render_dir = ch_render_dir
        elif camp_render_dir and os.path.exists(camp_render_dir):
            eff_render_dir = camp_render_dir
        elif camp_render_dir:
            # Campaign has a configured path even if it doesn't exist yet (will be created)
            eff_render_dir = camp_render_dir
        elif ch_render_dir:
            eff_render_dir = ch_render_dir
        else:
            eff_render_dir = global_render_dir

        # 2) bgm_folder: Channel > Campaign > Global
        # Special "inherit" values mean "use parent level"
        if ch_bgm_folder and ch_bgm_folder not in ("inherit", ""):
            eff_bgm_folder = ch_bgm_folder
            eff_bgm_volume = float(ch_bgm_volume) if ch_bgm_volume is not None else global_bgm_volume
        elif camp_bgm_folder and camp_bgm_folder not in ("inherit", ""):
            eff_bgm_folder = camp_bgm_folder
            eff_bgm_volume = float(camp_bgm_volume) if camp_bgm_volume is not None else global_bgm_volume
        else:
            eff_bgm_folder = global_bgm_folder or None
            eff_bgm_volume = global_bgm_volume

        return {
            "render_dir": eff_render_dir or None,
            "bgm_folder": eff_bgm_folder or None,
            "bgm_volume": eff_bgm_volume,
        }



    def get_effective_subtitle_settings(self, channel_obj: Optional[dict], camp: Optional[dict] = None) -> dict:
        """
        Xác định cấu hình phụ đề với thứ tự ưu tiên chặt chẽ:
        Kênh (Channel) > Chiến dịch (Campaign) > Toàn cục (Global).
        """
        import os
        from backend.database import get_connection

        # 1. Toàn cục (Global)
        global_enable_subs = os.getenv("ENABLE_DYNAMIC_SUBTITLES", "true").lower() in ("true", "1", "yes")
        global_sub_style = os.getenv("SUBTITLE_STYLE", "karaoke_yellow")
        global_sub_pos = os.getenv("SUBTITLE_POSITION", "center")
        global_disable_shorts = False

        # Thử đọc settings từ DB nếu có
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM settings WHERE key IN ('ENABLE_DYNAMIC_SUBTITLES', 'SUBTITLE_STYLE', 'SUBTITLE_POSITION')")
            s_dict = dict(cursor.fetchall())
            conn.close()
            if "ENABLE_DYNAMIC_SUBTITLES" in s_dict:
                global_enable_subs = s_dict["ENABLE_DYNAMIC_SUBTITLES"].lower() in ("true", "1", "yes")
            if "SUBTITLE_STYLE" in s_dict and s_dict["SUBTITLE_STYLE"]:
                global_sub_style = s_dict["SUBTITLE_STYLE"]
            if "SUBTITLE_POSITION" in s_dict and s_dict["SUBTITLE_POSITION"]:
                global_sub_pos = s_dict["SUBTITLE_POSITION"]
        except Exception:
            pass

        # 2. Chiến dịch (Campaign)
        camp_enable_subs = camp.get("subtitle_enabled") if camp else None
        camp_sub_style = camp.get("subtitle_style") if camp else None
        camp_sub_pos = camp.get("subtitle_position") if camp else None
        camp_disable_shorts = bool(camp.get("disable_subtitle_for_shorts", 0)) if camp else False

        # 3. Kênh nguồn (Channel)
        ch_enable_subs = channel_obj.get("subtitle_enabled") if channel_obj else None
        ch_sub_style = channel_obj.get("subtitle_style") if channel_obj else None
        ch_sub_pos = channel_obj.get("subtitle_position") if channel_obj else None
        ch_disable_shorts = bool(channel_obj.get("disable_subtitle_for_shorts", 0)) if channel_obj else False

        # --- Áp dụng thứ tự ưu tiên: Channel > Campaign > Global ---

        # 1) enable_subtitles
        if ch_enable_subs is not None:
            eff_enable = bool(ch_enable_subs)
        elif camp_enable_subs is not None:
            eff_enable = bool(camp_enable_subs)
        else:
            eff_enable = global_enable_subs

        # 2) disable_subtitle_for_shorts
        if channel_obj and channel_obj.get("disable_subtitle_for_shorts") is not None and channel_obj.get("disable_subtitle_for_shorts") != 0:
            eff_disable_shorts = True
        elif camp and camp.get("disable_subtitle_for_shorts"):
            eff_disable_shorts = True
        else:
            eff_disable_shorts = global_disable_shorts

        # 3) subtitle_style
        clean_ch_style = ch_sub_style if (ch_sub_style and ch_sub_style not in ("inherit", "")) else None
        clean_camp_style = camp_sub_style if (camp_sub_style and camp_sub_style not in ("inherit_channel", "inherit", "")) else None

        if camp_sub_style == "inherit_channel":
            eff_style = clean_ch_style or global_sub_style
        elif clean_ch_style:
            eff_style = clean_ch_style
        elif clean_camp_style:
            eff_style = clean_camp_style
        else:
            eff_style = global_sub_style

        # 4) subtitle_position
        clean_ch_pos = ch_sub_pos if (ch_sub_pos and ch_sub_pos not in ("inherit", "")) else None
        clean_camp_pos = camp_sub_pos if (camp_sub_pos and camp_sub_pos not in ("inherit_channel", "inherit", "")) else None

        if camp_sub_pos == "inherit_channel":
            eff_pos = clean_ch_pos or global_sub_pos
        elif clean_ch_pos:
            eff_pos = clean_ch_pos
        elif clean_camp_pos:
            eff_pos = clean_camp_pos
        else:
            eff_pos = global_sub_pos

        return {
            "enable_subtitles": eff_enable,
            "subtitle_style": eff_style,
            "subtitle_position": eff_pos,
            "disable_subtitle_for_shorts": eff_disable_shorts
        }

    def get_effective_duration_limits(self, channel_id: str, force_campaign_id: Optional[int] = None) -> tuple:
        """
        Lấy ngưỡng thời lượng và định dạng video (min_seconds, max_seconds, include_shorts, include_longform).
        Ưu tiên chặt chẽ: Kênh (Channel) > Chiến dịch (Campaign) > Toàn cục (Global).
        """
        conn = get_connection()
        cursor = conn.cursor()

        # 1. Đọc cài đặt toàn cục (Global)
        cursor.execute("SELECT key, value FROM settings WHERE key IN ('download_min_duration', 'download_max_duration', 'download_include_shorts', 'download_include_longform')")
        db_s = dict(cursor.fetchall())
        global_min = int(db_s.get("download_min_duration", 300))
        global_max = int(db_s.get("download_max_duration", 3600))
        global_shorts = db_s.get("download_include_shorts", "1") == "1"
        global_longform = db_s.get("download_include_longform", "1") == "1"

        # 2. Tìm chiến dịch liên kết (Campaign)
        camp_row = None
        if force_campaign_id:
            cursor.execute("SELECT min_video_duration, max_video_duration, include_shorts, include_longform FROM campaigns WHERE id = ?", (force_campaign_id,))
            camp_row = cursor.fetchone()
        else:
            cursor.execute("SELECT id, channel_id, channel_ids, min_video_duration, max_video_duration, include_shorts, include_longform FROM campaigns WHERE is_active = 1")
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

        # 3. Đọc cài đặt riêng của kênh (Channel)
        cursor.execute("SELECT min_video_duration, max_video_duration, include_shorts, include_longform FROM channels WHERE channel_id = ?", (channel_id,))
        channel_row = cursor.fetchone()

        conn.close()

        eff_min = global_min
        eff_max = global_max
        eff_shorts = global_shorts
        eff_longform = global_longform

        # Ưu tiên 2: Chiến dịch ghi đè toàn cục
        if camp_row:
            cr = dict(camp_row)
            if cr.get("min_video_duration") is not None:
                eff_min = int(cr["min_video_duration"])
            if cr.get("max_video_duration") is not None:
                eff_max = int(cr["max_video_duration"])
            if cr.get("include_shorts") is not None:
                eff_shorts = bool(cr["include_shorts"])
            if cr.get("include_longform") is not None:
                eff_longform = bool(cr["include_longform"])

        # Ưu tiên 1: Cài đặt kênh (cao nhất) ghi đè chiến dịch và toàn cục
        if channel_row:
            chr_d = dict(channel_row)
            if chr_d.get("min_video_duration") is not None:
                eff_min = int(chr_d["min_video_duration"])
            if chr_d.get("max_video_duration") is not None:
                eff_max = int(chr_d["max_video_duration"])
            if chr_d.get("include_shorts") is not None:
                eff_shorts = bool(chr_d["include_shorts"])
            if chr_d.get("include_longform") is not None:
                eff_longform = bool(chr_d["include_longform"])

        return eff_min, eff_max, eff_shorts, eff_longform

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
        min_dur, max_dur, inc_shorts, inc_longform = self.get_effective_duration_limits(channel_id, force_campaign_id)

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
                    max_duration=max_dur,
                    include_shorts=inc_shorts,
                    include_longform=inc_longform
                )
                if res:
                    new_downloads += 1
                    new_items.append({"title": v["title"], "video_id": vid})

                    self.handle_video_post_download(
                        file_path=str(res.get("file_path") or ""),
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
            min_dur, max_dur, inc_shorts, inc_longform = self.get_effective_duration_limits(ch_id)

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
                        max_duration=max_dur,
                        include_shorts=inc_shorts,
                        include_longform=inc_longform
                    )
                    if res:
                        total_new_downloaded += 1
                        channel_downloaded += 1

                        self.handle_video_post_download(
                            file_path=str(res.get("file_path") or ""),
                            video_id=vid,
                            channel_id=ch_id,
                            channel_name=ch_name,
                            video_title=v["title"],
                            duration=res.get("duration", 65),
                            channel_obj=ch
                        )

        return total_new_downloaded

yt_monitor = YouTubeRSSMonitor()
