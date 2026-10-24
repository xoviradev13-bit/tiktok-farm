import os
import subprocess
import shutil
from typing import Dict, Any, List

_NVENC_CACHE = None

def get_ffmpeg_binary() -> str:
    """Tìm đường dẫn thực thi của FFmpeg"""
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and os.path.exists(exe):
            return exe
    except ImportError:
        pass

    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    return "ffmpeg"

def is_nvenc_available() -> bool:
    """Kiểm tra thực tế xem card đồ họa NVIDIA và driver có hỗ trợ h264_nvenc không"""
    global _NVENC_CACHE
    if _NVENC_CACHE is not None:
        return _NVENC_CACHE

    ffmpeg_bin = get_ffmpeg_binary()
    cmd = [
        ffmpeg_bin, "-y",
        "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
        "-c:v", "h264_nvenc",
        "-f", "null", "-"
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        _NVENC_CACHE = (res.returncode == 0)
    except Exception:
        _NVENC_CACHE = False

    return _NVENC_CACHE

def get_optimal_video_encoder_flags() -> List[str]:
    """Trả về cờ mã hóa tối ưu nhất: NVENC nếu có GPU, ngược lại CPU libx264"""
    if is_nvenc_available():
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "22", "-b:v", "0"]
    else:
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p"]
