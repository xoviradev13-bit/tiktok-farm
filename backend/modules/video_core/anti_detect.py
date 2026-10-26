import os
from typing import Dict, Any, List, Optional, Tuple

def escape_ffmpeg_path(path: str) -> str:
    r"""Format đường dẫn an toàn cho FFmpeg filter trên Windows (đổi \ thành / và escape dấu hai chấm)"""
    p = path.replace("\\", "/")
    p = p.replace(":", "\\:")
    return p

class AntiDetectEngine:
    """
    Bộ xử lý lách thuật toán kiểm duyệt Reup của TikTok/Facebook Reels theo chuẩn Enterprise SaaS:
    1. Visual Anti-Perceptual Hash:
       - 9:16 canvas (1080x1920) với nền mờ phóng to (blurred background)
       - Micro color grading (chỉnh nhẹ tương phản, độ bão hòa, sáng)
       - Micro noise injection (phá perceptual hash pHash/md5)
       - Sub-perceptual speed up (1.025x)
       - Horizontal flip (tùy chọn)
       - Part/Title banner ở top
       - Burn phụ đề động karaoke
    2. Audio Anti-Fingerprint:
       - Resample + Frequency shifting + Tempo micro-adjust
       - Thay đổi mã âm thanh gốc nhưng giọng nói vẫn tự nhiên
    3. Container Cleaning:
       - Xóa toàn bộ metadata gốc (-map_metadata -1)
    """

    def build_filter_complex(
        self,
        part_number: int = 1,
        hook_text: Optional[str] = None,
        flip_horizontal: bool = True,
        speed_factor: float = 1.025,
        subtitle_ass_path: Optional[str] = None,
        enable_anti_detect: bool = True,
        width: int = 1080,
        height: int = 1920,
        add_part_label: bool = True
    ) -> Tuple[str, str, str]:
        """
        Xây dựng chuỗi filter_complex, out_map, và audio_filter cho FFmpeg.
        Trả về (filter_complex_str, out_map_name, audio_filter_str)
        """
        # 1. Background mờ + Foreground ở giữa
        # Lưu ý: crop={width}:{height} sau boxblur để đảm bảo kích thước chính xác
        # tránh lỗi "Invalid argument" của libx264 khi kích thước không chia hết cho 2
        scale_filter = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur=25:5[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2[base]"
        )

        current_stream = "base"
        sub_filters = []

        # 2. Lật ngang (Horizontal Flip)
        if flip_horizontal:
            sub_filters.append(f"[{current_stream}]hflip[v_flip]")
            current_stream = "v_flip"

        # 3. Lách thuật toán màu sắc và thêm hạt noise (Anti-Detection)
        if enable_anti_detect:
            # Color grading nhẹ + Noise vi mô (phá mã hash pHash)
            anti_color = f"[{current_stream}]eq=contrast=1.03:brightness=0.01:saturation=1.04,noise=alls=2:allf=u[v_anti]"
            sub_filters.append(anti_color)
            current_stream = "v_anti"

        # 4. Tăng tốc độ vi mô (Speed Factor)
        pts_factor = round(1.0 / speed_factor, 4)
        sub_filters.append(f"[{current_stream}]setpts={pts_factor}*PTS[v_speed]")
        current_stream = "v_speed"

        # 5. Badge PART X
        if add_part_label:
            part_label = f"PART {part_number}"
            draw_part = (
                f"[{current_stream}]drawtext=text='{part_label}':fontcolor=white:fontsize=36:"
                f"box=1:boxcolor=black@0.75:boxborderw=10:x=(w-text_w)/2:y=140[v_part]"
            )
            sub_filters.append(draw_part)
            current_stream = "v_part"

        # 6. Banner Hook giật tít trên nền mờ phía trên (Y = 220-230)
        if hook_text and hook_text.strip():
            # Loại bỏ emoji và ký tự đặc biệt để tránh ô vuông ký tự lỗi trong FFmpeg drawtext
            import re as _re
            clean_hook = _re.sub(r'[^\w\s\-\?\!\,\.\:\(\)\/]', '', hook_text)
            clean_hook = clean_hook.replace("'", "").replace("%", "").replace("\\", "").replace(":", " - ").strip()

            # Cắt ngắn thông minh theo ranh giới từ (Smart Word-Boundary Truncation - tuyệt đối không cắt đôi từ)
            max_chars = 52
            if len(clean_hook) > max_chars:
                words = clean_hook[:max_chars].split()
                if len(words) > 1:
                    clean_hook = " ".join(words[:-1]).rstrip(" ,.-:") + "..."
                else:
                    clean_hook = clean_hook[:max_chars].rstrip() + "..."

            # Tự động điều chỉnh kích cỡ font chữ (Dynamic Font Scaling) theo độ dài tiêu đề
            # giúp tiêu đề luôn nằm trọn vẹn trong khung hình 1080px mà không bị tràn viền hay che mất chữ
            h_len = len(clean_hook)
            if h_len <= 26:
                hook_fontsize = 48
                hook_y = 220
            elif h_len <= 38:
                hook_fontsize = 40
                hook_y = 224
            elif h_len <= 48:
                hook_fontsize = 34
                hook_y = 228
            else:
                hook_fontsize = 30
                hook_y = 230

            draw_hook = (
                f"[{current_stream}]drawtext=font='Arial':text='{clean_hook}':fontcolor=yellow:fontsize={hook_fontsize}:"
                f"box=1:boxcolor=black@0.8:boxborderw=14:x=(w-text_w)/2:y={hook_y}[v_hook]"
            )
            sub_filters.append(draw_hook)
            current_stream = "v_hook"

        # 7. Burn phụ đề động Karaoke nếu có file .ass
        if subtitle_ass_path and os.path.exists(subtitle_ass_path):
            safe_sub_path = escape_ffmpeg_path(subtitle_ass_path)
            sub_filters.append(f"[{current_stream}]subtitles='{safe_sub_path}'[v_sub]")
            current_stream = "v_sub"

        # 8. Luôn chuẩn hóa pixel format yuv420p ở cuối chuỗi bộ lọc để libx264 tương thích 100%
        sub_filters.append(f"[{current_stream}]format=yuv420p[v_out]")
        current_stream = "v_out"

        # Tổng hợp toàn bộ filter complex
        filter_complex = scale_filter + ";" + ";".join(sub_filters)

        # 7. Xây dựng bộ lọc Audio chống quét bản quyền âm thanh
        if enable_anti_detect:
            # Shift tần số 1.5% rồi resample lại về 44.1kHz, đồng thời chỉnh tempo
            # Cách này làm thay đổi triệt để dạng sóng waveform mà tai người vẫn thấy giọng chuẩn
            shifted_rate = int(44100 * 1.015)  # = 44761 Hz
            atempo_val = round(speed_factor / 1.015, 4)
            audio_filter = f"asetrate={shifted_rate},aresample=44100,atempo={atempo_val}"
        else:
            audio_filter = f"atempo={speed_factor}"

        return filter_complex, current_stream, audio_filter

anti_detect_engine = AntiDetectEngine()
