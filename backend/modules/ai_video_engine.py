import os
import re
import unicodedata
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
from backend.config import RENDERED_DIR, ENABLE_DYNAMIC_SUBTITLES, ENABLE_ANTI_DETECT, WHISPER_MODEL_SIZE
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
        add_part_label: bool = True
    ) -> Optional[str]:
        """
        Xử lý video hoàn chỉnh chuẩn Enterprise SaaS:
        1. Format dọc 9:16 với nền mờ phóng to (Blurred backdrop)
        2. Tự động burn phụ đề động Karaoke nếu bật
        3. Áp dụng toàn bộ bộ lọc Anti-Detection (Color grading, Noise pHash, Audio pitch/resample)
        4. Tối ưu phần cứng với GPU NVENC hoặc CPU libx264
        5. Xóa sạch metadata gốc (-map_metadata -1)
        6. Kiểm tra chất lượng (Quality Check) trước khi xuất
        """
        if not os.path.exists(input_file):
            log_event("ERROR", f"Không tìm thấy file video đầu vào: {input_file}")
            return None

        # Tra cứu thông tin kênh và tiêu đề từ database nếu thiếu
        if not channel_name or not video_title or not output_dir:
            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT v.title, c.display_name, c.title as ch_title, c.render_dir as ch_render_dir
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
            except Exception:
                pass

        target_dir = Path(output_dir) if output_dir and os.path.exists(output_dir) else self.output_dir
        target_dir.mkdir(parents=True, exist_ok=True)

        safe_channel = sanitize_filename(channel_name, max_length=25)
        safe_title = sanitize_filename(video_title, max_length=35)

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
                    max_duration=duration
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

        cmd = [
            self.ffmpeg_bin,
            "-y",
            "-ss", str(start_time),
            "-t", str(duration),
            "-i", input_file,
            "-filter_complex", filter_complex,
            "-map", f"[{out_map}]",  # video: từ filter_complex
            "-map", "0:a",           # audio: trực tiếp từ luồng gốc
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
            process = subprocess.run(cmd, capture_output=True, timeout=600)
            stderr_text = process.stderr.decode("utf-8", errors="replace") if process.stderr else ""
            stdout_text = process.stdout.decode("utf-8", errors="replace") if process.stdout else ""

            # Nếu chạy bằng NVENC mà bị crash/lỗi encoder -> Fallback tự động sang CPU libx264
            if process.returncode != 0 and "nvenc" in " ".join(encoder_flags).lower():
                logger.warning("NVENC GPU Render thất bại. Đang tự động chuyển sang CPU libx264 fallback...")
                cpu_flags = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
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
                process = subprocess.run(fallback_cmd, capture_output=True, timeout=600)
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
        output_dir: Optional[str] = None
    ) -> List[str]:
        """
        Tự động cắt video dài thành nhiều Part bằng cách dùng Silence Detector để ngắt tại khoảng lặng câu
        """
        rendered_files = []
        if total_duration <= part_duration + 10:
            # Video ngắn -> Xử lý 1 part duy nhất
            f = self.process_transformative_video(
                input_file=input_file,
                video_id=video_id,
                part_number=1,
                start_time=0.0,
                duration=float(max(61, total_duration)),
                channel_name=channel_name,
                video_title=video_title,
                output_dir=output_dir
            )
            if f:
                rendered_files.append(f)
        else:
            # Video dài -> Dò khoảng lặng và cắt theo từng Part
            current_start = 0.0
            part_idx = 1
            max_parts = 5

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
                    output_dir=output_dir
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
        generate_hook: bool = True
    ) -> Dict[str, Any]:
        """
        Quy trình xử lý AI trọn gói (End-to-End Enterprise SaaS Workflow):
        1. Nhận diện giọng nói bằng faster-whisper (Local)
        2. Gửi transcript lên LLM (DeepSeek / Gemini / OpenAI) để chọn đoạn viral 60-90s và viết Hook
        3. Tự động sinh phụ đề động Karaoke dạng .ass
        4. Render video với toàn bộ bộ lọc chống quét bản quyền
        5. Cập nhật cơ sở dữ liệu và trả về kết quả hoàn chỉnh
        """
        log_event("INFO", f"Bắt đầu chuỗi Smart AI Render cho video {video_id}: {video_title} (Model: {custom_model or 'Default'})")

        # Bước 1: Transcribe âm thanh local
        transcript_segments = whisper_transcriber.transcribe(input_file, model_size=WHISPER_MODEL_SIZE)

        # Lấy tổng thời lượng video
        total_duration = 0.0
        if transcript_segments:
            total_duration = transcript_segments[-1].get("end", 0.0)

        if total_duration < 30:
            total_duration = 120.0  # Fallback ước lượng

        # Bước 2: Gọi LLM (DeepSeek / Gemini / OpenAI) chọn đoạn hay và viết copy
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

        # Bước 3 & 4: Render video với phụ đề Karaoke và Anti-detection
        sub_enabled = enable_subtitles if enable_subtitles is not None else ENABLE_DYNAMIC_SUBTITLES
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
            hook_text=hook_3s if generate_hook else None,
            flip_horizontal=flip_horizontal,
            speed_factor=speed_factor,
            add_part_label=add_part_label
        )

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
            "curation": curation,
            "ai_hook": hook_3s,
            "ai_title": viral_title,
            "ai_description": description,
            "ai_hashtags": hashtags
        }

ai_video_engine = AIVideoEngine()
