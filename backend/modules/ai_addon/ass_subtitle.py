import os
from pathlib import Path
from typing import List, Dict, Any, Optional

def format_ass_time(seconds: float) -> str:
    """Đổi giây (float) sang định dạng thời gian ASS: H:MM:SS.cc"""
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int(round((seconds - int(seconds)) * 100))
    if centis >= 100:
        centis = 99
    return f"{hrs}:{mins:02d}:{secs:02d}.{centis:02d}"

class ASSSubtitleGenerator:
    """
    Tạo file phụ đề ASS chuẩn TikTok Viral (Karaoke Pop-up Style):
    - Đặt ở vùng an toàn (Safe Zone): Tránh thanh menu dưới và icon bên phải của TikTok.
    - Chữ in hoa (UPPERCASE), font đậm, viền đen dày chống chìm màu nền.
    - Hiệu ứng đổi màu từ đang phát âm (Vàng Neon / Trắng).
    """

    def generate_karaoke_ass(
        self,
        transcript_segments: List[Dict[str, Any]],
        output_ass_path: str,
        start_offset: float = 0.0,
        max_duration: Optional[float] = None,
        font_name: str = "Arial Black",
        font_size: int = 54,
        primary_color: str = "&H00FFFFFF&",    # Màu chữ mặc định (Trắng)
        highlight_color: str = "&H0000FFFF&",  # Màu chữ đang nói (Vàng Neon)
        outline_color: str = "&H00000000&",    # Viền đen
        margin_v: int = 680                   # Khoảng cách từ đáy (Safe Zone TikTok)
    ) -> Optional[str]:
        """
        Sinh file .ass từ transcript segments có word-level timestamps.
        start_offset: Thời điểm bắt đầu của đoạn cắt (để đồng bộ time với clip đã cắt).
        """
        # Header chuẩn ASS cho tỉ lệ 1080x1920
        header = f"""[Script Info]
Title: TikTok Viral Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: TikTokKaraoke,{font_name},{font_size},{primary_color},{highlight_color},{outline_color},&H80000000&,1,0,0,0,100,100,1,0,1,6,3,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

        events = []
        # Duyệt qua các segments
        for seg in transcript_segments:
            seg_start = seg.get("start", 0.0)
            seg_end = seg.get("end", 0.0)

            # Nếu nằm hoàn toàn ngoài khoảng render của video đã cắt
            if seg_end <= start_offset:
                continue
            if max_duration is not None and seg_start >= (start_offset + max_duration):
                continue

            words = seg.get("words", [])
            if not words:
                # Nếu không có word timestamps, fallback hiển thị cả câu
                rel_start = max(0.0, seg_start - start_offset)
                rel_end = seg_end - start_offset
                if max_duration and rel_end > max_duration:
                    rel_end = max_duration
                if rel_end > rel_start:
                    t_start = format_ass_time(rel_start)
                    t_end = format_ass_time(rel_end)
                    clean_txt = seg.get("text", "").strip().upper()
                    events.append(f"Dialogue: 0,{t_start},{t_end},TikTokKaraoke,,0,0,0,,{clean_txt}")
                continue

            # Gom nhóm từ 3-4 từ mỗi dòng để đọc dễ và không bị tràn màn hình dọc
            chunk_size = 4
            for i in range(0, len(words), chunk_size):
                chunk = words[i:i + chunk_size]
                if not chunk:
                    continue

                c_start = chunk[0]["start"] - start_offset
                c_end = chunk[-1]["end"] - start_offset

                if c_end <= 0:
                    continue
                if max_duration and c_start >= max_duration:
                    continue

                c_start = max(0.0, c_start)
                if max_duration and c_end > max_duration:
                    c_end = max_duration

                if c_end <= c_start:
                    continue

                # Tạo mã karaoke {\k<centiseconds>} cho từng từ
                karaoke_text_parts = []
                for w in chunk:
                    w_dur = max(0.1, w["end"] - w["start"])
                    cs = int(round(w_dur * 100))
                    clean_w = w["word"].strip().upper()
                    karaoke_text_parts.append(f"{{\\k{cs}}}{clean_w}")

                dialogue_text = " ".join(karaoke_text_parts)
                t_start = format_ass_time(c_start)
                t_end = format_ass_time(c_end)
                events.append(f"Dialogue: 0,{t_start},{t_end},TikTokKaraoke,,0,0,0,,{dialogue_text}")

        # Ghi file .ass
        try:
            Path(output_ass_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_ass_path, "w", encoding="utf-8") as f:
                f.write(header)
                f.write("\n".join(events))
                f.write("\n")
            return output_ass_path
        except Exception as e:
            return None

ass_subtitle_generator = ASSSubtitleGenerator()
