import os
import sys
import re
import json
import unicodedata
import subprocess
import shutil
import random
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from backend.config import (
    RENDERED_DIR, MUSIC_DIR, ENABLE_DYNAMIC_SUBTITLES, ENABLE_ANTI_DETECT, WHISPER_MODEL_SIZE,
    SUBTITLE_STYLE, SUBTITLE_POSITION, SUBTITLE_FONT_SIZE
)
from backend.database import get_connection, log_event
from backend.logger import get_logger

logger = get_logger("ai_video_engine")

# Import các phân hệ video core và AI add-on
from backend.modules.video_core.hardware_accel import get_ffmpeg_binary, get_optimal_video_encoder_flags, is_nvenc_available
from backend.modules.video_core.anti_detect import anti_detect_engine
from backend.modules.video_core.silence_detector import silence_detector
from backend.modules.video_core.quality_checker import quality_checker
from backend.modules.ai_addon.llm_curator import llm_curator
from backend.modules.ai_addon.whisper_transcriber import whisper_transcriber
from backend.modules.ai_addon.ass_subtitle import ass_subtitle_generator
from backend.modules.audio_manager import audio_manager

def sanitize_filename(text: Optional[str], max_length: int = 30) -> str:
    """Loại bỏ emoji, ký tự cấm của Windows và ký tự gây lỗi FFmpeg/URL, giữ ký tự an toàn và rút gọn độ dài"""
    if not text:
        return ""
    text = unicodedata.normalize('NFKD', str(text))
    # Loại bỏ emoji và ký tự Unicode đặc biệt ngoài dải thông thường
    text = re.sub(r'[\U00010000-\U0010ffff]', '', text)
    # Thay thế các ký tự không hợp lệ trong Windows file system và FFmpeg: \ / : * ? " < > | # % & ' ` $ ! @
    cleaned = re.sub(r'[\\/*?:"<>|#%&\'`$!@^;=~,]', '', text)
    # Thay thế khoảng trắng hoặc ký tự phân cách bằng gạch dưới
    cleaned = re.sub(r'[\s\t\n\r]+', '_', cleaned.strip())
    # Bỏ các dấu gạch dưới liên tiếp
    cleaned = re.sub(r'_+', '_', cleaned)
    cleaned = cleaned.strip(' ._-')
    return cleaned[:max_length].rstrip(' ._-')

class AIVideoEngine:
    """
    Enterprise SaaS AI Video Engine for TikTok Farm:
    - Multi-provider Cloud LLM: DeepSeek, Gemini, OpenAI
    - Local Speech-to-Text: faster-whisper (CTranslate2)
    - Dynamic Subtitles: ASS Karaoke word-level popups
    - Anti-Reup Evasion: Color jitter, micro-noise, sub-perceptual speed, audio pitching, metadata wiping
    - Hardware Acceleration: Dynamic NVENC / libx264
    - Smart Cuts: Silence detection snapping
    """

    def __init__(self, output_dir: Path = RENDERED_DIR):
        self.output_dir = output_dir
        self.ffmpeg_bin = get_ffmpeg_binary()

    def _get_exact_media_duration(self, file_path: str) -> float:
        """Đo thời lượng chính xác của file video/audio bằng ffprobe"""
        if not file_path or not os.path.exists(file_path):
            return 0.0
        try:
            ffmpeg_bin = get_ffmpeg_binary()
            ffprobe_bin = ffmpeg_bin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")
            if os.path.exists(ffprobe_bin):
                cmd = [
                    ffprobe_bin,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "json",
                    file_path
                ]
                res = subprocess.run(cmd, capture_output=True, timeout=15)
                if res.returncode == 0:
                    info = json.loads(res.stdout.decode("utf-8", errors="replace"))
                    return float(info.get("format", {}).get("duration", 0.0))
        except Exception:
            pass
        return 0.0

    def generate_ai_hook_and_copy(self, raw_title: str) -> Dict[str, str]:
        """Gọi LLM (DeepSeek / Gemini / OpenAI) sinh Hook 3s, Tiêu đề giật tít, Caption và Hashtags"""
        return llm_curator.generate_hook_and_copy(raw_title)

    def process_transformative_video(
        self,
        input_file: str,
        video_id: str,
        part_number: int = 1,
        start_time: float = 0.0,
        duration: float = 65.0,  # Chuẩn > 60s cho TikTok Creator Rewards
        flip_horizontal: bool = True,
        speed_factor: float = 1.025,
        channel_name: Optional[str] = None,
        video_title: Optional[str] = None,
        output_dir: Optional[str] = None,
        enable_subtitles: Optional[bool] = None,
        transcript_segments: Optional[List[Dict[str, Any]]] = None,
        hook_text: Optional[str] = None,
        add_part_label: bool = True,
        subtitle_style: Optional[str] = None,
        subtitle_position: Optional[str] = None,
        bgm_folder: Optional[str] = None,
        bgm_volume: Optional[float] = None
    ) -> Optional[str]:
        """
        Xử lý video hoàn chỉnh chuẩn Enterprise SaaS:
        1. Format dọc 9:16 với nền mờ phóng to (Blurred backdrop)
        2. Tự động burn phụ đề động Karaoke nếu bật
        3. Áp dụng toàn bộ bộ lọc Anti-Detection (Color grading, Noise pHash, Audio pitch/resample)
        4. Tối ưu phần cứng với GPU NVENC hoặc CPU libx264
        5. Tích hợp nhạc nền BGM chủ đề theo kênh (Shuffle + Volume ducking + Fade-out 2s)
        6. Xóa sạch metadata gốc (-map_metadata -1)
        7. Kiểm tra chất lượng (Quality Check) trước khi xuất
        """
        if not os.path.exists(input_file):
            log_event("ERROR", f"Không tìm thấy file video đầu vào: {input_file}")
            return None

        # Tra cứu thông tin kênh, tiêu đề và cấu hình BGM từ database nếu thiếu
        if not channel_name or not video_title or not output_dir or bgm_folder is None:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT v.title, c.display_name, c.title as ch_title, c.render_dir as ch_render_dir,
                           c.bgm_folder, c.bgm_volume
                    FROM videos v
                    LEFT JOIN channels c ON v.channel_id = c.channel_id
                    WHERE v.yt_video_id = ?
                ''', (video_id,))
                row = cursor.fetchone()
                conn.close()
                if row:
                    if not video_title:
                        video_title = row["title"] or ""
                    if not channel_name:
                        channel_name = row["display_name"] or row["ch_title"] or ""
                    if not output_dir and row["ch_render_dir"] and os.path.exists(row["ch_render_dir"]):
                        output_dir = row["ch_render_dir"]
                    if bgm_folder is None and "bgm_folder" in row.keys():
                        bgm_folder = row["bgm_folder"] or ""
                    if bgm_volume is None and "bgm_volume" in row.keys() and row["bgm_volume"]:
                        bgm_volume = float(row["bgm_volume"])
            except Exception:
                pass

        safe_channel = sanitize_filename(channel_name, max_length=25)
        safe_title = sanitize_filename(video_title, max_length=35)

        base_target_dir = Path(output_dir) if output_dir and os.path.exists(output_dir) else self.output_dir
        if channel_name and channel_name.strip() and channel_name.strip() not in ("Dán trực tiếp", "Direct Links"):
            clean_ch = re.sub(r'[\\/*?:"<>|]', '', channel_name).strip()
            target_dir = base_target_dir / (clean_ch or "Direct Links")
        else:
            target_dir = base_target_dir / "Direct Links"
        target_dir.mkdir(parents=True, exist_ok=True)

        parts = []
        if safe_channel:
            parts.append(f"[{safe_channel}]")
        if safe_title:
            parts.append(safe_title)
        parts.append(video_id)
        parts.append(f"Part{part_number}")

        clean_filename = "_".join(parts) + ".mp4"
        output_file = str(target_dir / clean_filename)
        log_event("INFO", f"Bắt đầu render video AI Reup {video_id} (Part {part_number}, duration {duration:.1f}s) -> {clean_filename}")

        # Chọn bài hát BGM thông minh (Mood / Cảm xúc + Dò điểm Beat Drop)
        selected_bgm = None
        bgm_start_offset = 0.0
        used_bgm_cat = ""
        target_bgm_vol = bgm_volume if bgm_volume is not None else 0.15

        if bgm_folder and bgm_folder.strip():
            transcript_sample = ""
            if transcript_segments:
                transcript_sample = " ".join(s.get("text", "") for s in transcript_segments[:8])
            elif video_title:
                transcript_sample = video_title

            selected_bgm, bgm_start_offset, used_bgm_cat = audio_manager.get_smart_bgm(
                folder_or_mood=bgm_folder.strip(),
                transcript_text=transcript_sample
            )
            if selected_bgm:
                log_event(
                    "INFO",
                    f"🎵 Áp dụng BGM thông minh [{used_bgm_cat}]: {Path(selected_bgm).name} "
                    f"(Beat Drop: {bgm_start_offset:.1f}s, Sidechain Auto-Ducking: BẬT, Vol: {int(target_bgm_vol*100)}%) "
                    f"cho {clean_filename}"
                )
            else:
                logger.warning(f"Thư mục nhạc nền [{bgm_folder}] chưa có bài hát nào, sẽ render âm thanh gốc.")

        # Chuẩn bị phụ đề Karaoke .ass nếu bật
        sub_ass_path = None
        should_sub = enable_subtitles if enable_subtitles is not None else ENABLE_DYNAMIC_SUBTITLES
        if should_sub:
            if transcript_segments is None:
                # Thử tự động transcribe phần âm thanh
                try:
                    transcript_segments = whisper_transcriber.transcribe(input_file, model_size=WHISPER_MODEL_SIZE)
                except Exception as e:
                    log_event("WARNING", f"Không thể tự động transcribe: {e}")

            if transcript_segments:
                temp_ass = str(target_dir / f"{video_id}_part{part_number}_temp.ass")
                sub_ass_path = ass_subtitle_generator.generate_karaoke_ass(
                    transcript_segments=transcript_segments,
                    output_ass_path=temp_ass,
                    start_offset=start_time,
                    max_duration=duration,
                    style_name=subtitle_style or SUBTITLE_STYLE,
                    position=subtitle_position or SUBTITLE_POSITION,
                    font_size=SUBTITLE_FONT_SIZE
                )

        # Xây dựng Filter Complex chống kiểm duyệt
        filter_complex, out_map, audio_filter = anti_detect_engine.build_filter_complex(
            part_number=part_number,
            hook_text=hook_text,
            flip_horizontal=flip_horizontal,
            speed_factor=speed_factor,
            subtitle_ass_path=sub_ass_path,
            enable_anti_detect=ENABLE_ANTI_DETECT,
            add_part_label=add_part_label
        )

        # Cờ encoder tối ưu (NVENC hoặc CPU libx264)
        encoder_flags = get_optimal_video_encoder_flags()

        has_bgm = bool(selected_bgm and os.path.exists(selected_bgm))
        fade_start = max(0.0, float(duration) - 2.0)

        if has_bgm:
            # Smart Auto-Ducking (Sidechain Compression):
            # Khi có giọng nói: Nhạc tự động nén xuống -12dB (êm dịu làm nền)
            # Khi ngắt câu / khoảng lặng: Nhạc tự dâng lên nhịp nhàng (+6dB) tạo nhịp điệu cuốn hút
            bgm_boost_vol = min(1.0, target_bgm_vol * 1.6)
            full_filter_complex = (
                f"{filter_complex};"
                f"[0:a]{audio_filter}[a_voice];"
                f"[1:a]volume={bgm_boost_vol:.2f},afade=t=out:st={fade_start:.1f}:d=2[a_bgm_raw];"
                f"[a_bgm_raw][a_voice]sidechaincompress=threshold=0.08:ratio=3.5:attack=50:release=350[a_bgm_ducked];"
                f"[a_voice][a_bgm_ducked]amix=inputs=2:duration=first:dropout_transition=2[a_out]"
            )
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", input_file,
                "-ss", str(bgm_start_offset),
                "-stream_loop", "-1",
                "-i", selected_bgm,
                "-filter_complex", full_filter_complex,
                "-map", f"[{out_map}]",
                "-map", "[a_out]"
            ]
        else:
            full_filter_complex = filter_complex
            cmd = [
                self.ffmpeg_bin,
                "-y",
                "-ss", str(start_time),
                "-t", str(duration),
                "-i", input_file,
                "-filter_complex", filter_complex,
                "-map", f"[{out_map}]",
                "-map", "0:a",
                "-af", audio_filter
            ]

        cmd.extend(encoder_flags)
        cmd.extend([
            "-c:a", "aac",
            "-b:a", "128k",
            "-ar", "44100",
            "-map_metadata", "-1",       # Xóa toàn bộ metadata gốc chống đối soát bản quyền
            "-movflags", "+faststart",   # Web-optimized MP4
            output_file
        ])

        try:
            logger.debug(f"Thực thi lệnh FFmpeg render: {' '.join(cmd[:12])}...")
            cflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            process = subprocess.run(cmd, capture_output=True, timeout=900, creationflags=cflags)
            stderr_text = process.stderr.decode("utf-8", errors="replace") if process.stderr else ""
            stdout_text = process.stdout.decode("utf-8", errors="replace") if process.stdout else ""

            # Nếu chạy bằng NVENC mà bị crash/lỗi encoder -> Fallback tự động sang CPU libx264
            if process.returncode != 0 and "nvenc" in " ".join(encoder_flags).lower():
                logger.warning("NVENC GPU Render thất bại. Đang tự động chuyển sang CPU libx264 fallback...")
                cpu_flags = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
                if has_bgm:
                    fallback_cmd = [
                        self.ffmpeg_bin, "-y",
                        "-ss", str(start_time),
                        "-t", str(duration),
                        "-i", input_file,
                        "-ss", str(bgm_start_offset),
                        "-stream_loop", "-1",
                        "-i", selected_bgm,
                        "-filter_complex", full_filter_complex,
                        "-map", f"[{out_map}]",
                        "-map", "[a_out]"
                    ]
                else:
                    fallback_cmd = [
                        self.ffmpeg_bin, "-y",
                        "-ss", str(start_time),
                        "-t", str(duration),
                        "-i", input_file,
                        "-filter_complex", filter_complex,
                        "-map", f"[{out_map}]",
                        "-map", "0:a",
                        "-af", audio_filter
                    ]
                fallback_cmd.extend(cpu_flags)
                fallback_cmd.extend([
                    "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                    "-map_metadata", "-1", "-movflags", "+faststart",
                    output_file
                ])
                process = subprocess.run(fallback_cmd, capture_output=True, timeout=900, creationflags=cflags)
                stderr_text = process.stderr.decode("utf-8", errors="replace") if process.stderr else ""

            if process.returncode == 0 and os.path.exists(output_file):
                # Kiểm tra chất lượng (Quality Check)
                is_valid, qc_msg = quality_checker.check_clip_quality(output_file, min_duration=min(60, int(duration - 2)))
                if not is_valid:
                    log_event("WARNING", f"Cảnh báo QC cho {clean_filename}: {qc_msg}")

                log_event("INFO", f"Render thành công video AI: {output_file} ({qc_msg})")

                # Cập nhật đường dẫn rendered vào DB
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE videos SET rendered_path = ?, status = 'rendered', error_message = NULL WHERE yt_video_id = ?",
                    (output_file, video_id)
                )
                conn.commit()
                conn.close()

                return output_file
            else:
                err_lower = stderr_text.lower()
                classified_msg = "Lỗi không xác định khi render FFmpeg"
                if "cannot allocate memory" in err_lower or "out of memory" in err_lower:
                    classified_msg = "Không đủ bộ nhớ RAM để render video (Out of Memory)"
                elif "no space left on device" in err_lower:
                    classified_msg = "Hết dung lượng ổ đĩa khi lưu video render"
                elif "invalid data found" in err_lower:
                    classified_msg = "File video đầu vào bị lỗi hoặc không thể đọc"
                elif "subtitles" in err_lower or ".ass" in err_lower:
                    classified_msg = "Lỗi biên dịch phụ đề ASS Karaoke trong filter FFmpeg"
                elif stderr_text:
                    classified_msg = f"Lỗi FFmpeg (Exit code {process.returncode}): {stderr_text[-300:].strip()}"

                logger.error(f"Lỗi render video {video_id}: {classified_msg}\nFFmpeg Stderr:\n{stderr_text[-1200:]}")
                log_event("ERROR", f"Lỗi render video {video_id}: {classified_msg}", details=stderr_text[-600:])

                try:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute(
                        "UPDATE videos SET status = 'error', error_message = ? WHERE yt_video_id = ?",
                        (classified_msg, video_id)
                    )
                    conn.commit()
                    conn.close()
                except Exception:
                    pass

        except Exception as e:
            logger.exception(f"Ngoại lệ khi render video {video_id}: {e}")
            log_event("ERROR", f"Ngoại lệ khi render video {video_id}: {str(e)}")
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE videos SET status = 'error', error_message = ? WHERE yt_video_id = ?",
                    (f"Lỗi hệ thống render: {str(e)}", video_id)
                )
                conn.commit()
                conn.close()
            except Exception:
                pass
        finally:
            # Dọn dẹp file .ass tạm thời
            if sub_ass_path and os.path.exists(sub_ass_path):
                try:
                    os.remove(sub_ass_path)
                except Exception:
                    pass

        return None

    def auto_slice_and_render_parts(
        self,
        input_file: str,
        video_id: str,
        total_duration: int,
        part_duration: int = 65,
        channel_name: Optional[str] = None,
        video_title: Optional[str] = None,
        output_dir: Optional[str] = None,
        max_clips: int = 5,
        add_part_label: bool = True,
        enable_subtitles: Optional[bool] = None,
        flip_horizontal: bool = True,
        speed_factor: float = 1.025,
        subtitle_style: Optional[str] = None,
        subtitle_position: Optional[str] = None,
        bgm_folder: Optional[str] = None,
        bgm_volume: Optional[float] = None,
        disable_subtitle_for_shorts: bool = False
    ) -> List[str]:
        """
        Tự động cắt video dài thành nhiều Part bằng cách dùng Silence Detector để ngắt tại khoảng lặng câu
        """
        rendered_files = []

        # Đo thời lượng thực tế chính xác và kiểm tra có phải là Shorts/Short-form không (<= 180s)
        actual_dur = self._get_exact_media_duration(input_file)
        if actual_dur > 0:
            total_duration = actual_dur
        is_short_form = (total_duration <= 180.0)

        effective_enable_subtitles = enable_subtitles
        if is_short_form and disable_subtitle_for_shorts:
            effective_enable_subtitles = False

        if is_short_form or total_duration <= part_duration + 10 or max_clips <= 1:
            # Video ngắn / Shorts hoặc chỉ yêu cầu 1 clip -> Xử lý 1 part duy nhất
            # Đối với Shorts: không đóng dấu chữ PART và giữ trọn vẹn độ dài video
            effective_part_label = False if is_short_form else add_part_label
            eff_dur = total_duration if is_short_form else float(max(61, total_duration if total_duration <= part_duration + 10 else part_duration))
            f = self.process_transformative_video(
                input_file=input_file,
                video_id=video_id,
                part_number=1,
                start_time=0.0,
                duration=eff_dur,
                channel_name=channel_name,
                video_title=video_title,
                output_dir=output_dir,
                enable_subtitles=effective_enable_subtitles,
                flip_horizontal=flip_horizontal,
                speed_factor=speed_factor,
                add_part_label=effective_part_label,
                subtitle_style=subtitle_style,
                subtitle_position=subtitle_position,
                bgm_folder=bgm_folder,
                bgm_volume=bgm_volume
            )
            if f:
                rendered_files.append(f)
        else:
            # Video dài (Long-form > 3 phút) -> Dò khoảng lặng và cắt theo từng Part (tối đa max_clips)
            current_start = 0.0
            part_idx = 1
            max_parts = max_clips if max_clips < 100 else 99

            while current_start < (total_duration - 45) and part_idx <= max_parts:
                # Tìm điểm cắt thông minh bằng silence detector
                cut_point = silence_detector.get_optimal_cut_point(
                    video_path=input_file,
                    start_time=current_start,
                    target_duration=float(part_duration),
                    min_duration=60.5,
                    max_duration=float(part_duration + 20)
                )

                chunk_dur = cut_point - current_start
                if chunk_dur < 60:
                    chunk_dur = float(part_duration)

                f = self.process_transformative_video(
                    input_file=input_file,
                    video_id=video_id,
                    part_number=part_idx,
                    start_time=current_start,
                    duration=chunk_dur,
                    channel_name=channel_name,
                    video_title=video_title,
                    output_dir=output_dir,
                    enable_subtitles=enable_subtitles,
                    flip_horizontal=flip_horizontal,
                    speed_factor=speed_factor,
                    add_part_label=add_part_label,
                    subtitle_style=subtitle_style,
                    subtitle_position=subtitle_position,
                    bgm_folder=bgm_folder,
                    bgm_volume=bgm_volume
                )
                if f:
                    rendered_files.append(f)

                current_start = cut_point
                part_idx += 1

        return rendered_files

    def process_smart_ai_video(
        self,
        input_file: str,
        video_id: str,
        video_title: str = "",
        channel_name: str = "",
        output_dir: Optional[str] = None,
        custom_provider: Optional[str] = None,
        custom_model: Optional[str] = None,
        enable_subtitles: Optional[bool] = None,
        target_duration: int = 65,
        flip_horizontal: bool = True,
        speed_factor: float = 1.03,
        add_part_label: bool = True,
        generate_hook: bool = True,
        clips_count: int = 1,
        subtitle_style: Optional[str] = None,
        subtitle_position: Optional[str] = None,
        bgm_folder: Optional[str] = None,
        bgm_volume: Optional[float] = None,
        disable_subtitle_for_shorts: bool = False
    ) -> Dict[str, Any]:
        """
        Quy trình xử lý AI trọn gói (End-to-End Enterprise SaaS Workflow):
        1. Nhận diện giọng nói bằng faster-whisper (Local)
        2. Gửi transcript lên LLM (DeepSeek / Gemini / OpenAI) để chọn đoạn viral 60-90s và viết Hook
        3. Tự động sinh phụ đề động Karaoke dạng .ass
        4. Render video với toàn bộ bộ lọc chống quét bản quyền
        5. Cập nhật cơ sở dữ liệu và trả về kết quả hoàn chỉnh
        """
        log_event("INFO", f"Bắt đầu chuỗi Smart AI Render cho video {video_id}: {video_title} (Model: {custom_model or 'Default'}, clips_count: {clips_count})")

        # Bước 1: Transcribe âm thanh local
        transcript_segments = whisper_transcriber.transcribe(input_file, model_size=WHISPER_MODEL_SIZE)

        # Lấy tổng thời lượng video chính xác bằng ffprobe
        actual_dur = self._get_exact_media_duration(input_file)
        if actual_dur > 0:
            total_duration = actual_dur
        elif transcript_segments and transcript_segments[-1].get("end", 0.0) > 0:
            total_duration = transcript_segments[-1].get("end", 0.0)
        else:
            total_duration = 60.0

        # Kiểm tra Short-form (YouTube Shorts <= 3 phút) vs Long-form
        is_short_form = (total_duration <= 180.0)

        if is_short_form:
            # SHORT-FORM / YouTube Shorts (<= 180s):
            # Xuất 1 clip trọn vẹn duy nhất từ 0.0 đến hết, KHÔNG gắn nhãn PART X
            start_time = 0.0
            duration = total_duration
            effective_clips_count = 1
            effective_add_part_label = False
            curation = llm_curator.generate_hook_and_copy(video_title, video_id=video_id)
            viral_title = curation.get("viral_title") or video_title
            primary_hook = curation.get("hook") or viral_title
            description = curation.get("description", "")
            hashtags = curation.get("tags", "")
            log_event("INFO", f"Video {video_id} là Short-form ({total_duration:.1f}s <= 180s) -> Xuất 1 clip trọn vẹn, không chèn chữ Part.")
        else:
            # LONG-FORM (> 3 phút):
            # Cho phép cắt nhiều Part, dùng LLM chọn phân đoạn kịch tính nhất
            effective_clips_count = clips_count
            effective_add_part_label = add_part_label
            curation = llm_curator.curate_viral_segment(
                transcript_segments=transcript_segments,
                total_duration=total_duration,
                target_duration=target_duration,
                video_title=video_title,
                video_id=video_id,
                custom_provider=custom_provider,
                custom_model=custom_model
            )
            start_time = curation["start_time"]
            duration = curation["duration"]
            hook_3s = curation["hook_3s"] if generate_hook else ""
            viral_title = curation["viral_title"]
            description = curation["description"]
            hashtags = curation["hashtags"]
            primary_hook = hook_3s.strip() if (hook_3s and hook_3s.strip()) else viral_title.strip()

        # Bước 3 & 4: Render video Part 1 với phụ đề Karaoke và Anti-detection
        sub_enabled = enable_subtitles if enable_subtitles is not None else ENABLE_DYNAMIC_SUBTITLES
        if is_short_form and disable_subtitle_for_shorts:
            sub_enabled = False
        part1_hook = primary_hook if generate_hook else None

        rendered_file = self.process_transformative_video(
            input_file=input_file,
            video_id=video_id,
            part_number=1,
            start_time=start_time,
            duration=duration,
            channel_name=channel_name,
            video_title=viral_title,
            output_dir=output_dir,
            enable_subtitles=sub_enabled,
            transcript_segments=transcript_segments,
            hook_text=part1_hook,
            flip_horizontal=flip_horizontal,
            speed_factor=speed_factor,
            add_part_label=effective_add_part_label,
            subtitle_style=subtitle_style,
            subtitle_position=subtitle_position,
            bgm_folder=bgm_folder,
            bgm_volume=bgm_volume
        )

        rendered_files = [rendered_file] if rendered_file else []

        # Nếu yêu cầu cắt nhiều clip từ video này (CHỈ KHI LÀ LONG-FORM VÀ clips_count > 1)
        if not is_short_form and effective_clips_count > 1 and total_duration > (duration + 20):
            curr_start = start_time + duration
            part_num = 2
            while part_num <= clips_count and curr_start < (total_duration - 20):
                # 1. Tìm điểm cắt thông minh bằng silence detector (khoảng lặng kết thúc câu nói)
                cut_point = silence_detector.get_optimal_cut_point(
                    video_path=input_file,
                    start_time=curr_start,
                    target_duration=float(target_duration),
                    min_duration=60.5,
                    max_duration=float(target_duration + 20)
                )

                # 2. Nếu có transcript từ Whisper, snap chuẩn xác vào thời điểm kết thúc câu nói (tránh cắt giữa câu)
                if transcript_segments:
                    valid_sentence_ends = [
                        seg["end"] for seg in transcript_segments
                        if (curr_start + 60.5) <= seg.get("end", 0) <= min(total_duration, curr_start + target_duration + 25)
                    ]
                    if valid_sentence_ends:
                        # Chọn mốc kết thúc câu tự nhiên gần với target_duration nhất
                        cut_point = min(valid_sentence_ends, key=lambda e: abs(e - (curr_start + target_duration)))

                part_dur = max(60.5, cut_point - curr_start)
                if (curr_start + part_dur) > total_duration:
                    part_dur = max(60.0, total_duration - curr_start)

                if generate_hook:
                    if add_part_label:
                        # Badge PART X đã hiển thị ở Y=140 nên banner chỉ cần nội dung hook nguyên vẹn, không lặp lại "Part X - "
                        part_hook = primary_hook
                    else:
                        part_hook = f"Part {part_num} - {primary_hook}"
                else:
                    part_hook = None

                next_p = self.process_transformative_video(
                    input_file=input_file,
                    video_id=video_id,
                    part_number=part_num,
                    start_time=curr_start,
                    duration=part_dur,
                    channel_name=channel_name,
                    video_title=f"{viral_title} Part {part_num}",
                    output_dir=output_dir,
                    enable_subtitles=sub_enabled,
                    transcript_segments=transcript_segments,
                    hook_text=part_hook,
                    flip_horizontal=flip_horizontal,
                    speed_factor=speed_factor,
                    add_part_label=add_part_label,
                    subtitle_style=subtitle_style,
                    subtitle_position=subtitle_position,
                    bgm_folder=bgm_folder,
                    bgm_volume=bgm_volume
                )
                if next_p:
                    rendered_files.append(next_p)
                curr_start = cut_point
                part_num += 1

        # Cập nhật thông tin AI Copy vào Database
        if rendered_file:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE videos
                    SET ai_hook = ?, ai_title = ?, ai_tags = ?, status = 'rendered', rendered_path = ?
                    WHERE yt_video_id = ?
                """, (hook_3s, viral_title, f"{hashtags}\n\n{description}", rendered_file, video_id))
                conn.commit()
                conn.close()
            except Exception as e:
                log_event("WARNING", f"Lỗi cập nhật AI copy vào DB: {e}")

        return {
            "status": "success" if rendered_file else "failed",
            "rendered_file": rendered_file,
            "rendered_files": rendered_files,
            "curation": curation,
            "ai_hook": hook_3s,
            "ai_title": viral_title,
            "ai_description": description,
            "ai_hashtags": hashtags
        }

ai_video_engine = AIVideoEngine()
