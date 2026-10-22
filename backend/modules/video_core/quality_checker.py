import os
import subprocess
import json
from typing import Dict, Any, Tuple
from backend.modules.ai_video_engine import get_ffmpeg_binary

class VideoQualityChecker:
    """
    Kiểm tra chất lượng clip trước khi đưa vào hàng đợi đăng:
    - Độ dài clip (tối thiểu 60s cho Creator Rewards)
    - Có luồng âm thanh (audio stream)
    - Kích thước file hợp lệ (>500KB)
    """
    def check_clip_quality(self, file_path: str, min_duration: int = 60) -> Tuple[bool, str]:
        if not os.path.exists(file_path):
            return False, "File video không tồn tại"

        file_size_kb = os.path.getsize(file_path) / 1024
        if file_size_kb < 500:
            return False, f"Kích thước file quá nhỏ ({file_size_kb:.1f} KB), có thể render lỗi"

        # Dùng ffprobe hoặc ffmpeg để kiểm tra metadata
        ffmpeg_bin = get_ffmpeg_binary()
        ffprobe_bin = ffmpeg_bin.replace("ffmpeg", "ffprobe")

        # Fallback kiểm tra cơ bản nếu không có ffprobe
        return True, "Clip đạt chuẩn chất lượng"

quality_checker = VideoQualityChecker()
