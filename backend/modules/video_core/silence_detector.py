import os
import subprocess
import re
from typing import List, Tuple, Optional
from backend.modules.video_core.hardware_accel import get_ffmpeg_binary
from backend.database import log_event

class SilenceDetector:
    """
    Phát hiện khoảng lặng (silence / pause) trong âm thanh video:
    - Giúp cắt video chính xác tại ranh giới kết thúc câu nói.
    - Tránh việc cắt đứt giữa từ làm mất ngữ nghĩa và giảm trải nghiệm người xem.
    """

    def find_silence_pauses(
        self,
        video_path: str,
        start_search: float,
        end_search: float,
        noise_threshold_db: int = -30,
        min_silence_dur: float = 0.25
    ) -> List[float]:
        """
        Tìm các mốc thời gian im lặng trong khoảng [start_search, end_search].
        Trả về danh sách các thời điểm (giây) im lặng lý tưởng để cắt.
        """
        ffmpeg_bin = get_ffmpeg_binary()
        dur = max(1.0, end_search - start_search)
        cmd = [
            ffmpeg_bin,
            "-ss", str(start_search),
            "-t", str(dur),
            "-i", video_path,
            "-af", f"silencedetect=noise={noise_threshold_db}dB:d={min_silence_dur}",
            "-f", "null",
            "-"
        ]

        pauses = []
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=120)
            stderr = res.stderr.decode("utf-8", errors="replace") if res.stderr else ""
            # Tìm dòng: [silencedetect @ ...] silence_start: 62.45
            for match in re.finditer(r"silence_start:\s*([0-9\.]+)", stderr):
                rel_t = float(match.group(1))
                pauses.append(start_search + rel_t)
        except Exception as e:
            log_event("WARNING", f"Lỗi dò khoảng lặng silence: {e}")

        return pauses

    def get_optimal_cut_point(
        self,
        video_path: str,
        start_time: float,
        target_duration: float = 65.0,
        min_duration: float = 60.5,
        max_duration: float = 85.0
    ) -> float:
        """
        Tìm điểm cắt tối ưu nhất gần target_duration nhưng đảm bảo:
        - duration >= min_duration (đủ chuẩn quỹ > 1 phút)
        - duration <= max_duration
        - Cắt ngay tại khoảng dừng câu nói
        """
        search_start = start_time + min_duration
        search_end = start_time + max_duration

        pauses = self.find_silence_pauses(video_path, search_start, search_end)
        ideal_target = start_time + target_duration

        if pauses:
            # Chọn khoảng dừng gần với ideal_target nhất
            best_pause = min(pauses, key=lambda p: abs(p - ideal_target))
            return round(best_pause, 2)

        # Nếu không tìm thấy khoảng im lặng rõ ràng, lấy theo ideal_target
        return round(ideal_target, 2)

silence_detector = SilenceDetector()
