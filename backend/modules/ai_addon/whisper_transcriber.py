import os
import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional
from backend.database import log_event

class WhisperTranscriber:
    """
    Local Speech-to-Text Engine using faster-whisper (CTranslate2).
    - Runs 100% offline on Windows.
    - Word-level timestamps for Dynamic TikTok Karaoke subtitles.
    - Dynamic device selection (CUDA GPU if available, else CPU int8).
    """

    def __init__(self):
        self._model = None
        self._current_model_size = None

    def _get_ffmpeg_exe(self) -> str:
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
            if exe and os.path.exists(exe):
                return exe
        except ImportError:
            pass
        return shutil.which("ffmpeg") or "ffmpeg"

    def _load_model(self, model_size: str = "base"):
        if self._model is not None and self._current_model_size == model_size:
            return self._model

        import ctranslate2
        from faster_whisper import WhisperModel

        has_cuda = "cuda" in ctranslate2.get_supported_compute_types("cuda")
        device = "cuda" if has_cuda else "cpu"
        compute_type = "float16" if has_cuda else "int8"

        log_event("INFO", f"Khởi tạo faster-whisper (model={model_size}, device={device}, compute={compute_type})")
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        self._current_model_size = model_size
        return self._model

    def extract_audio(self, video_path: str, output_wav: Optional[str] = None) -> Optional[str]:
        """Tách luồng âm thanh 16kHz mono từ video bằng FFmpeg để nhận dạng nhanh nhất"""
        if not output_wav:
            output_wav = str(Path(video_path).with_suffix(".temp_audio.wav"))

        ffmpeg_bin = self._get_ffmpeg_exe()
        cmd = [
            ffmpeg_bin, "-y",
            "-i", video_path,
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", "16000",
            "-ac", "1",
            output_wav
        ]

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=300)
            if res.returncode == 0 and os.path.exists(output_wav):
                return output_wav
        except Exception as e:
            log_event("ERROR", f"Lỗi tách audio cho whisper: {e}")

        return None

    @staticmethod
    def _ensure_pyav_compat():
        """Bảo đảm tương thích PyAV trên Python 3.14 (bỏ qua metadata_errors nếu không được hỗ trợ)"""
        try:
            import av
            orig_open = av.open
            def safe_av_open(*args, **kwargs):
                kwargs.pop("metadata_errors", None)
                return orig_open(*args, **kwargs)
            av.open = safe_av_open
        except Exception:
            pass

    def transcribe(
        self,
        video_or_audio_path: str,
        model_size: str = "base",
        language: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Nhận diện giọng nói và xuất word-level timestamps.
        Trả về danh sách các segments kèm mốc thời gian từng từ.
        Tự động lưu/đọc bộ đệm (JSON Cache) để tái sử dụng tức thì.
        """
        import json
        p = Path(video_or_audio_path)
        cache_path = p.with_name(f"{p.stem}.transcript.json")

        # 1. Đọc từ Cache nếu đã từng nhận dạng
        if cache_path.exists():
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = json.load(f)
                if isinstance(cached_data, list) and len(cached_data) > 0:
                    log_event("INFO", f"Nạp {len(cached_data)} câu phụ đề từ bộ nhớ đệm cache: {cache_path.name}")
                    return cached_data
            except Exception as e:
                log_event("WARNING", f"Không thể đọc file cache phụ đề {cache_path.name}: {e}")

        self._ensure_pyav_compat()

        temp_audio = None
        target_path = video_or_audio_path

        # Luôn trích xuất audio WAV 16kHz trước để tránh lỗi đọc container trực tiếp
        if not video_or_audio_path.lower().endswith(".wav"):
            temp_audio = self.extract_audio(video_or_audio_path)
            if temp_audio:
                target_path = temp_audio
            else:
                log_event("WARNING", "Không thể tách audio WAV, thử transcribe trực tiếp từ video")

        results = []
        import time
        from backend.database import record_ai_usage
        t0 = time.time()
        try:
            model = self._load_model(model_size)
            import faster_whisper.audio
            audio_arr = faster_whisper.audio.decode_audio(target_path)

            segments, info = model.transcribe(
                audio_arr,
                beam_size=5,
                word_timestamps=True,
                language=language
            )

            for segment in segments:
                words_list = []
                if segment.words:
                    for w in segment.words:
                        words_list.append({
                            "word": w.word.strip(),
                            "start": round(w.start, 2),
                            "end": round(w.end, 2),
                            "probability": round(w.probability, 2)
                        })

                results.append({
                    "start": round(segment.start, 2),
                    "end": round(segment.end, 2),
                    "text": segment.text.strip(),
                    "words": words_list
                })

            dur_ms = int((time.time() - t0) * 1000)
            record_ai_usage(
                provider="Local Whisper",
                model=f"faster-whisper-{model_size}",
                task="speech_to_text",
                video_id=Path(video_or_audio_path).stem,
                prompt_tokens=len(results),
                completion_tokens=sum(len(s.get("words", [])) for s in results),
                estimated_cost=0.0,
                duration_ms=dur_ms,
                status="success"
            )

            # Lưu vào file JSON cache
            if results:
                try:
                    with open(cache_path, "w", encoding="utf-8") as f:
                        json.dump(results, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

            log_event("INFO", f"Whisper nhận dạng thành công {len(results)} câu (Ngôn ngữ: {info.language}, {dur_ms}ms)")
        except Exception as e:
            dur_ms = int((time.time() - t0) * 1000)
            record_ai_usage(
                provider="Local Whisper",
                model=f"faster-whisper-{model_size}",
                task="speech_to_text",
                video_id=Path(video_or_audio_path).stem,
                duration_ms=dur_ms,
                status="error",
                error_message=str(e)
            )
            log_event("ERROR", f"Lỗi khi transcribe bằng faster-whisper: {e}")
        finally:
            if temp_audio and os.path.exists(temp_audio):
                try:
                    os.remove(temp_audio)
                except Exception:
                    pass

        return results


whisper_transcriber = WhisperTranscriber()
