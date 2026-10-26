import os
import re
import random
import shutil
import unicodedata
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple, Union, cast
import yt_dlp

from backend.config import MUSIC_DIR, DEFAULT_BGM_THEMES
from backend.logger import get_logger
from backend.modules.video_core.hardware_accel import get_ffmpeg_binary
from backend.database import log_event

logger = get_logger("audio_manager")

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac"}

THEME_DISPLAY_NAMES = {folder: name for folder, name in DEFAULT_BGM_THEMES}

def sanitize_audio_filename(filename: str) -> str:
    """Loại bỏ ký tự nguy hiểm cho Windows và Web URL"""
    name, ext = os.path.splitext(filename)
    clean_ext = ext.lower()
    if clean_ext not in ALLOWED_AUDIO_EXTENSIONS:
        clean_ext = ".mp3"
    
    clean_name = unicodedata.normalize('NFKD', str(name))
    clean_name = re.sub(r'[\U00010000-\U0010ffff]', '', clean_name)
    clean_name = re.sub(r'[\\/*?:"<>|#%&\'`$!@^;=~,]', '', clean_name)
    clean_name = re.sub(r'[\s\t\n\r]+', '_', clean_name.strip())
    clean_name = re.sub(r'_+', '_', clean_name).strip(' ._-')
    if not clean_name:
        clean_name = f"track_{int(datetime.now().timestamp())}"
    return f"{clean_name[:60]}{clean_ext}"

class AudioManager:
    """
    Quản lý Thư viện Âm thanh & Nhạc nền (BGM Studio):
    - Tìm kiếm YouTube No-Copyright Audio (20, 50, 100, 200 bài)
    - Tải MP3 trực tiếp từ YouTube URL
    - Upload đa file từ máy tính
    - Phân loại thư mục chủ đề (Horror, Lo-Fi, Phonk, Storytelling...)
    """
    def __init__(self, music_dir: Path = MUSIC_DIR):
        self.music_dir = music_dir
        self.music_dir.mkdir(parents=True, exist_ok=True)
        for folder, _ in DEFAULT_BGM_THEMES:
            (self.music_dir / folder).mkdir(parents=True, exist_ok=True)

    def get_categories(self) -> List[Dict[str, Any]]:
        """Lấy danh sách các thư mục chủ đề kèm số lượng bài hát và dung lượng"""
        categories = []
        if not self.music_dir.exists():
            return categories

        for item in sorted(self.music_dir.iterdir()):
            if item.is_dir() and not item.name.startswith("."):
                folder_name = item.name
                tracks = [
                    f for f in item.glob("*.*")
                    if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
                ]
                total_bytes = sum(f.stat().st_size for f in tracks)
                display = THEME_DISPLAY_NAMES.get(folder_name, folder_name.replace("_", " ").title())
                categories.append({
                    "id": folder_name,
                    "name": folder_name,
                    "display_name": display,
                    "track_count": len(tracks),
                    "total_size_mb": round(total_bytes / (1024 * 1024), 2),
                    "path": str(item)
                })
        return categories

    def create_category(self, folder_name: str, display_name: Optional[str] = None) -> Dict[str, Any]:
        """Tạo thư mục chủ đề mới"""
        clean_name = re.sub(r'[^\w\-_]', '_', folder_name.strip().lower())
        clean_name = re.sub(r'_+', '_', clean_name).strip('_')
        if not clean_name:
            raise ValueError("Tên thư mục không hợp lệ")

        target_dir = self.music_dir / clean_name
        target_dir.mkdir(parents=True, exist_ok=True)
        if display_name:
            THEME_DISPLAY_NAMES[clean_name] = display_name

        log_event("INFO", f"Thư viện BGM: Tạo thư mục nhạc mới '{clean_name}' ({display_name or clean_name})")
        return {
            "id": clean_name,
            "name": clean_name,
            "display_name": display_name or clean_name.replace("_", " ").title(),
            "track_count": 0,
            "total_size_mb": 0.0
        }

    def rename_category(self, old_id: str, new_name: str, new_display_name: Optional[str] = None) -> Dict[str, Any]:
        """Đổi tên thư mục và tên hiển thị của danh mục nhạc"""
        old_dir = self.music_dir / old_id
        if not old_dir.exists() or not old_dir.is_dir():
            raise FileNotFoundError(f"Thư mục '{old_id}' không tồn tại")
        
        clean_new_id = re.sub(r'[^\w\-_]', '_', new_name.strip().lower())
        clean_new_id = re.sub(r'_+', '_', clean_new_id).strip('_')
        if not clean_new_id:
            raise ValueError("Tên thư mục mới không hợp lệ")

        new_dir = self.music_dir / clean_new_id
        if clean_new_id != old_id:
            if new_dir.exists():
                raise ValueError(f"Thư mục '{clean_new_id}' đã tồn tại")
            old_dir.rename(new_dir)
            if old_id in THEME_DISPLAY_NAMES:
                del THEME_DISPLAY_NAMES[old_id]
        
        final_display_name = new_display_name.strip() if new_display_name and new_display_name.strip() else clean_new_id.replace("_", " ").title()
        THEME_DISPLAY_NAMES[clean_new_id] = final_display_name

        total_bytes = sum(f.stat().st_size for f in new_dir.glob("*.*") if f.is_file())
        count = sum(1 for f in new_dir.glob("*.*") if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS)

        log_event("INFO", f"Thư viện BGM: Đổi tên thư mục '{old_id}' -> '{clean_new_id}' ({final_display_name})")
        return {
            "id": clean_new_id,
            "name": clean_new_id,
            "display_name": final_display_name,
            "track_count": count,
            "total_size_mb": round(total_bytes / (1024 * 1024), 2)
        }

    def delete_category(self, category_id: str) -> bool:
        """Xóa thư mục nhạc và toàn bộ file bên trong"""
        target_dir = self.music_dir / category_id
        if not target_dir.exists() or not target_dir.is_dir():
            return False
        import shutil
        shutil.rmtree(target_dir, ignore_errors=True)
        if category_id in THEME_DISPLAY_NAMES:
            del THEME_DISPLAY_NAMES[category_id]
        log_event("INFO", f"Thư viện BGM: Đã xóa thư mục '{category_id}' và toàn bộ file bên trong")
        return True

    def get_tracks_in_category(self, category: str) -> List[Dict[str, Any]]:
        """Lấy danh sách bài hát trong một danh mục"""
        target_dir = self.music_dir / category
        if not target_dir.exists() or not target_dir.is_dir():
            return []

        tracks = []
        for f in sorted(target_dir.glob("*.*"), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                st = f.stat()
                mtime_str = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M")
                tracks.append({
                    "filename": f.name,
                    "name": f.stem,
                    "ext": f.suffix.lower(),
                    "size_mb": round(st.st_size / (1024 * 1024), 2),
                    "size_bytes": st.st_size,
                    "modified_at": mtime_str,
                    "category": category,
                    "stream_url": f"/api/audio/stream/{category}/{f.name}"
                })
        return tracks

    def delete_track(self, category: str, filename: str) -> bool:
        """Xóa an toàn một file bài hát"""
        safe_cat = os.path.basename(category)
        safe_file = os.path.basename(filename)
        target_file = self.music_dir / safe_cat / safe_file
        if target_file.exists() and target_file.is_file():
            target_file.unlink()
            logger.info(f"Đã xóa bài hát: {target_file}")
            log_event("INFO", f"Thư viện BGM: Đã xóa file nhạc '{safe_file}' khỏi [{safe_cat}]")
            return True
        return False

    def search_youtube_audio(self, keyword: str, max_results: int = 50) -> List[Dict[str, Any]]:
        """
        Tìm kiếm nhạc No-Copyright trên YouTube với giới hạn 20, 50, 100, 200 bài:
        Trích xuất đầy đủ: Title, Duration, Views, Date, Uploader, Thumbnail, URL, và check đã tải về hay chưa.
        """
        kw = keyword.strip() if keyword else "no copyright music background"
        # Bổ sung từ khóa no copyright nếu người dùng chưa ghi
        search_term = kw if any(k in kw.lower() for k in ("no copyright", "ncs", "royalty free", "audio library")) else f"{kw} no copyright"

        # Lấy danh sách ID đã tải về trong tất cả các folder để hiển thị is_downloaded
        downloaded_ids = set()
        for f in self.music_dir.glob("*/*.*"):
            if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS:
                # Tìm ID trong ngoặc vuông [videoId]
                m = re.search(r'\[([a-zA-Z0-9_-]{11})\]', f.name)
                if m:
                    downloaded_ids.add(m.group(1))

        limit = max(1, min(int(max_results or 50), 200))
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'js_runtimes': {'node': {}},
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                }
            },
        }

        results = []
        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(f"ytsearch{limit}:{search_term}", download=False)
                entries = info.get('entries', []) if info else []
                for entry in entries:
                    if not entry:
                        continue
                    v_id = entry.get('id')
                    if not v_id:
                        continue

                    title = entry.get('title') or "Untitled Audio"
                    dur = int(entry.get('duration') or 0)
                    mins = dur // 60
                    secs = dur % 60
                    dur_str = f"{mins:02d}:{secs:02d}"

                    view_count = int(entry.get('view_count') or 0)
                    views_str = f"{view_count:,}" if view_count else "--"

                    uploader = entry.get('uploader') or entry.get('channel') or "YouTube Creator"
                    upload_date = entry.get('upload_date') or ""
                    if len(upload_date) == 8:
                        upload_date = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:]}"

                    thumbnails = entry.get('thumbnails') or []
                    thumb_url = thumbnails[-1].get('url') if thumbnails else f"https://i.ytimg.com/vi/{v_id}/hqdefault.jpg"

                    results.append({
                        "id": v_id,
                        "title": title,
                        "duration": dur,
                        "duration_string": dur_str,
                        "uploader": uploader,
                        "view_count": view_count,
                        "views_formatted": views_str,
                        "upload_date": upload_date,
                        "thumbnail": thumb_url,
                        "url": f"https://www.youtube.com/watch?v={v_id}",
                        "is_downloaded": v_id in downloaded_ids
                    })
        except Exception as e:
            logger.error(f"Lỗi tìm kiếm YouTube Audio: {e}")
            log_event("WARNING", f"Thư viện BGM: Lỗi tìm kiếm YouTube Audio: {e}")

        log_event("INFO", f"Thư viện BGM: Quét nhạc YouTube '{search_term}' -> {len(results)} bài hát")
        return results

    def get_youtube_stream_url(self, url_or_id: str) -> Optional[Dict[str, Any]]:
        """
        Lấy direct streaming audio URL từ YouTube để nghe thử trực tiếp trên trình duyệt
        mà không cần tải toàn bộ file về máy tính.
        """
        url = url_or_id.strip()
        m = re.search(r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})', url)
        clean_id = m.group(1) if m else url
        if not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={clean_id}"

        ydl_opts = {
            'format': 'bestaudio[ext=m4a]/bestaudio/best',
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
            'js_runtimes': {'node': {}},
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }

        cookies_file = Path("cookies.txt")
        if cookies_file.exists():
            ydl_opts['cookiefile'] = str(cookies_file)

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(url, download=False)
                if not info:
                    return None

                stream_url = info.get('url')
                if not stream_url:
                    formats = info.get('formats') or []
                    for f in reversed(formats):
                        if f.get('acodec') != 'none' and f.get('url'):
                            stream_url = f.get('url')
                            break

                return {
                    "id": info.get('id') or clean_id,
                    "title": info.get('title') or "Audio Track",
                    "duration": info.get('duration') or 0,
                    "stream_url": stream_url
                }
        except Exception as e:
            logger.warning(f"Lỗi lấy direct audio stream cho {url}: {e}")
            return None

    def download_youtube_track(self, url_or_id: str, category: str) -> Dict[str, Any]:
        """Tải bài hát từ YouTube và chuyển đổi sang MP3 lưu vào thư mục chủ đề"""
        safe_cat = os.path.basename(category) or "general"
        target_dir = self.music_dir / safe_cat
        target_dir.mkdir(parents=True, exist_ok=True)

        url = url_or_id.strip()
        m = re.search(r'(?:v=|\/|be\/)([a-zA-Z0-9_-]{11})', url)
        if m:
            clean_id = m.group(1)
            url = f"https://www.youtube.com/watch?v={clean_id}"
        elif not url.startswith("http"):
            url = f"https://www.youtube.com/watch?v={url}"

        log_event("INFO", f"Thư viện BGM: Bắt đầu tải nhạc từ YouTube ({url}) vào thư mục [{safe_cat}]...")

        ffmpeg_bin = get_ffmpeg_binary()

        # Output template: Ten_bai_hat [ID].mp3
        out_tmpl = str(target_dir / "%(title).50s [%(id)s].%(ext)s")

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': out_tmpl,
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False,
            'no_warnings': True,
            'retries': 5,
            'fragment_retries': 5,
            'js_runtimes': {'node': {}},
            'extractor_args': {
                'youtube': {
                    'player_client': ['android', 'ios', 'web'],
                }
            },
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            },
        }
        if ffmpeg_bin:
            ydl_opts['ffmpeg_location'] = ffmpeg_bin

        cookies_file = Path("cookies.txt")
        if cookies_file.exists():
            ydl_opts['cookiefile'] = str(cookies_file)

        try:
            with yt_dlp.YoutubeDL(cast(Any, ydl_opts)) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title') or "Audio Track"
                v_id = info.get('id') or ""

                # Tìm file MP3 vừa tải
                downloaded_file = None
                for f in target_dir.glob(f"*{v_id}*.mp3"):
                    downloaded_file = f
                    break

                if not downloaded_file:
                    for f in target_dir.glob("*.mp3"):
                        downloaded_file = f
                        break

                size_mb = round(downloaded_file.stat().st_size / (1024 * 1024), 2) if downloaded_file else 0.0

                logger.info(f"Tải thành công YouTube Audio vào {safe_cat}: {title}")
                log_event("INFO", f"Thư viện BGM: Tải thành công MP3 '{title}' [{v_id}] ({size_mb} MB) vào [{safe_cat}]")
                return {
                    "status": "success",
                    "title": title,
                    "filename": downloaded_file.name if downloaded_file else "",
                    "size_mb": size_mb,
                    "category": safe_cat,
                    "message": f"Đã tải thành công '{title}' vào thư mục {safe_cat}"
                }
        except Exception as e:
            logger.error(f"Lỗi tải YouTube Audio {url}: {e}")
            log_event("ERROR", f"Thư viện BGM: Lỗi tải nhạc từ YouTube ({url}): {e}")
            raise RuntimeError(f"Lỗi khi tải âm thanh từ YouTube: {str(e)}")

    def find_beat_drop_offset(self, audio_path: str) -> float:
        """
        Quét waveform/RMS để tìm điểm Beat Drop / Cao trào đầu tiên của bài nhạc.
        Bỏ qua đoạn intro êm dịu, giúp nhạc khớp ngay vào đoạn cao trào tại giây 2-3s của Hook.
        Kết quả được cache trong .drop_cache.json để tránh quét lại nhiều lần.
        """
        p = Path(audio_path)
        if not p.exists() or p.stat().st_size == 0:
            return 0.0

        cache_file = self.music_dir / ".drop_cache.json"
        cache = {}
        if cache_file.exists():
            try:
                import json
                cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                cache = {}

        file_key = f"{p.name}_{p.stat().st_mtime}"
        if file_key in cache:
            return float(cache[file_key])

        ffmpeg_bin = get_ffmpeg_binary()
        if not ffmpeg_bin:
            return 0.0

        try:
            import subprocess
            cmd = [
                ffmpeg_bin, "-i", str(p),
                "-t", "45",
                "-af", "asetnsamples=n=44100,astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-",
                "-f", "null", "-"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            lines = res.stdout.splitlines()

            samples = []
            cur_time = 0.0
            for line in lines:
                m_t = re.search(r"pts_time:([0-9.]+)", line)
                if m_t:
                    cur_time = float(m_t.group(1))
                m_r = re.search(r"RMS_level=([-\d.]+)", line)
                if m_r:
                    try:
                        rms = float(m_r.group(1))
                        samples.append((cur_time, rms))
                    except Exception:
                        pass

            if not samples:
                return 0.0

            # Tìm bước nhảy năng lượng (Drop) giữa giây 4 và 35
            best_drop_time = 0.0
            max_jump = 0.0

            for i in range(1, len(samples)):
                t, rms = samples[i]
                prev_t, prev_rms = samples[i - 1]
                if 4.0 <= t <= 35.0:
                    jump = rms - prev_rms
                    if jump > max_jump and rms >= -28.0:
                        max_jump = jump
                        best_drop_time = t

            if max_jump >= 3.5 and best_drop_time >= 4.0:
                drop_offset = max(0.0, best_drop_time - 1.5)
            else:
                drop_offset = 0.0

            cache[file_key] = round(drop_offset, 2)
            try:
                import json
                cache_file.write_text(json.dumps(cache, indent=2), encoding="utf-8")
            except Exception:
                pass

            return round(drop_offset, 2)
        except Exception as e:
            logger.debug(f"Không thể quét drop offset cho {p.name}: {e}")
            return 0.0

    def get_smart_bgm(self, folder_or_mood: Optional[str] = None, transcript_text: str = "") -> Tuple[Optional[str], float, str]:
        """
        Lựa chọn nhạc nền thông minh:
        1. Nhận diện Mood từ transcript hoặc folder chỉ định
        2. Chọn bài hát phù hợp nhất trong thư mục
        3. Dò điểm Beat Drop tối ưu để bắt đầu phát
        Trả về: (audio_path, start_offset_seconds, category_name)
        """
        import random
        target_folder = (folder_or_mood or "").strip().lower()

        # Mapping từ khóa cảm xúc sang thư mục mặc định
        text_lower = f"{target_folder} {transcript_text}".lower()

        if target_folder in ("auto", "", "default", "none", "inherit"):
            if any(k in text_lower for k in ("ma", "quỷ", "kinh dị", "u ám", "bí ẩn", "rùng rợn", "creepy", "horror", "ghost", "mystery", "scary", "dark")):
                target_folder = "horror_mystery"
            elif any(k in text_lower for k in ("chill", "lofi", "lo-fi", "tâm sự", "thư giãn", "podcast", "study", "relax", "tài chính", "tiền")):
                target_folder = "lofi_chill"
            elif any(k in text_lower for k in ("động lực", "hành động", "tốc độ", "speed", "xe", "drift", "workout", "gym", "hype", "phonk", "chiến", "viral")):
                target_folder = "phonk_hype"
            elif any(k in text_lower for k in ("buồn", "cảm động", "chia tay", "nước mắt", "piano", "drama", "câu chuyện", "bài học", "cuộc sống")):
                target_folder = "storytelling_piano"
            else:
                target_folder = "general"

        target_dir = self.music_dir / target_folder
        if not target_dir.exists() or not target_dir.is_dir():
            target_dir = self.music_dir / "general"
            target_folder = "general"

        valid_tracks = [
            f for f in target_dir.glob("*.*")
            if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
        ]

        if not valid_tracks:
            all_tracks = [
                f for f in self.music_dir.glob("*/*.*")
                if f.is_file() and f.suffix.lower() in ALLOWED_AUDIO_EXTENSIONS
            ]
            if not all_tracks:
                return None, 0.0, target_folder
            selected = random.choice(all_tracks)
            used_cat = selected.parent.name
        else:
            selected = random.choice(valid_tracks)
            used_cat = target_folder

        # Dò điểm Beat Drop tối ưu
        drop_offset = self.find_beat_drop_offset(str(selected))
        return str(selected), drop_offset, used_cat

audio_manager = AudioManager()

