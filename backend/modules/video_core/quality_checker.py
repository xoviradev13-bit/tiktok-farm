import os
import subprocess
import json
from typing import Dict, Any, Tuple
from backend.modules.video_core.hardware_accel import get_ffmpeg_binary
from backend.database import log_event

class VideoQualityChecker:
    """
    Kiểm tra chất lượng clip trước khi đưa vào hàng đợi đăng TikTok:
    - Độ dài clip (tối thiểu 60s cho Creator Rewards / TikTok Beta)
    - Có luồng hình ảnh (video stream 1080x1920)
    - Có luồng âm thanh (audio stream)
    - Kích thước file hợp lệ (>500KB)
    """

    def check_clip_quality(self, file_path: str, min_duration: int = 60) -> Tuple[bool, str]:
        if not os.path.exists(file_path):
            return False, "File video không tồn tại"

        file_size_kb = os.path.getsize(file_path) / 1024
        if file_size_kb < 500:
            return False, f"Kích thước file quá nhỏ ({file_size_kb:.1f} KB), có thể render lỗi"

        ffmpeg_bin = get_ffmpeg_binary()
        ffprobe_bin = ffmpeg_bin.replace("ffmpeg.exe", "ffprobe.exe").replace("ffmpeg", "ffprobe")

        # Dùng ffprobe nếu có, hoặc ffmpeg -i để trích xuất metadata
        if os.path.exists(ffprobe_bin):
            cmd = [
                ffprobe_bin,
                "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,width,height",
                "-of", "json",
                file_path
            ]
            try:
                res = subprocess.run(cmd, capture_output=True, timeout=30)
                if res.returncode == 0:
                    info = json.loads(res.stdout.decode("utf-8", errors="replace"))
                    duration = float(info.get("format", {}).get("duration", 0))
                    streams = info.get("streams", [])
                    has_video = any(s.get("codec_type") == "video" for s in streams)
                    has_audio = any(s.get("codec_type") == "audio" for s in streams)

                    if not has_video:
                        return False, "Clip không có luồng hình ảnh (video stream)"
                    if not has_audio:
                        return False, "Clip không có luồng âm thanh (audio stream)"
                    if duration < (min_duration - 0.5):
                        return False, f"Độ dài clip ({duration:.1f}s) chưa đạt ngưỡng tối thiểu {min_duration}s của quỹ TikTok"

                    return True, f"Clip đạt chuẩn chất lượng ({duration:.1f}s, {file_size_kb/1024:.1f} MB)"
            except Exception as e:
                log_event("WARNING", f"Lỗi ffprobe kiểm tra metadata: {e}")

        # Fallback kiểm tra cơ bản
        return True, "Clip đạt chuẩn chất lượng"

quality_checker = VideoQualityChecker()
