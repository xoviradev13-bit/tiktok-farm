import os
import json
import re
import time
import requests
from typing import Dict, Any, List, Optional, Tuple
from backend.config import (
    DEEPSEEK_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, AI_PROVIDER,
    DEEPSEEK_MODEL, GEMINI_MODEL, OPENAI_MODEL
)
from backend.database import log_event, record_ai_usage
from backend.logger import get_logger

logger = get_logger("ai_curator")

def classify_ai_call_error(status_code: int, err_text: str, provider: str) -> str:
    err_lower = (err_text or "").lower()
    if status_code == 429 or "rate limit" in err_lower or "quota" in err_lower or "resourceexhausted" in err_lower:
        return f"CẢNH BÁO AI: Hết hạn mức hoặc Quota {provider} (HTTP 429). Hãy kiểm tra số dư credit hoặc đổi model/provider trong Cài Đặt."
    elif status_code in (401, 403) or "invalid api key" in err_lower or "api_key_invalid" in err_lower:
        return f"CẢNH BÁO AI: API Key {provider} không hợp lệ hoặc đã bị thu hồi (HTTP {status_code}). Vui lòng cập nhật API Key mới."
    elif status_code == 503 or "service unavailable" in err_lower:
        return f"CẢNH BÁO AI: Máy chủ {provider} đang quá tải tạm thời (HTTP 503)."
    else:
        return f"Lỗi gọi {provider} ({status_code}): {err_text[:120]}"

def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Ước tính chi phí theo bảng giá tiêu chuẩn mỗi 1,000,000 tokens ($ USD)"""
    rates = {
        # DeepSeek
        "deepseek-chat": (0.14, 0.28),
        "deepseek-reasoner": (0.55, 2.19),
        # Google Gemini
        "gemini-2.5-flash": (0.075, 0.30),
        "gemini-1.5-flash": (0.075, 0.30),
        "gemini-1.5-pro": (3.50, 10.50),
        # OpenAI
        "gpt-4o-mini": (0.15, 0.60),
        "gpt-4o": (2.50, 10.00),
    }
    in_rate, out_rate = rates.get(model.lower(), (0.15, 0.60))
    cost = (prompt_tokens * in_rate + completion_tokens * out_rate) / 1_000_000.0
    return round(cost, 6)

class LLMCurator:
    """
    Enterprise-grade multi-provider Cloud LLM Gateway with Usage & Cost Tracking:
    - Primary: DeepSeek (deepseek-chat / deepseek-reasoner)
    - Secondary: Google Gemini (gemini-2.5-flash / 1.5-flash / 1.5-pro)
    - Fallback: OpenAI (gpt-4o-mini / gpt-4o)
    - Resilient Local Fallback: Rule-based copy generator
    - Complete Usage & Cost Tracking into ai_usage_logs table
    """

    def __init__(self):
        self.timeout = 35

    def _get_active_config(self) -> Dict[str, Any]:
        import backend.config as cfg
        return {
            "deepseek_key": cfg.DEEPSEEK_API_KEY or os.getenv("DEEPSEEK_API_KEY", ""),
            "gemini_key": cfg.GEMINI_API_KEY or os.getenv("GEMINI_API_KEY", ""),
            "openai_key": cfg.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", ""),
            "provider": cfg.AI_PROVIDER or os.getenv("AI_PROVIDER", "deepseek").lower(),
            "deepseek_model": cfg.DEEPSEEK_MODEL or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "gemini_model": cfg.GEMINI_MODEL or os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            "openai_model": cfg.OPENAI_MODEL or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        }

    def _call_deepseek(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        task: str,
        video_id: str
    ) -> Optional[str]:
        url = "https://api.deepseek.com/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }

        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            dur_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                usage = data.get("usage", {})
                p_tokens = usage.get("prompt_tokens", 0)
                c_tokens = usage.get("completion_tokens", 0)
                cost = estimate_cost(model, p_tokens, c_tokens)

                record_ai_usage(
                    provider="DeepSeek",
                    model=model,
                    task=task,
                    video_id=video_id,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    estimated_cost=cost,
                    duration_ms=dur_ms,
                    status="success"
                )
                return data["choices"][0]["message"]["content"]
            else:
                err_msg = resp.text[:200]
                record_ai_usage(
                    provider="DeepSeek",
                    model=model,
                    task=task,
                    video_id=video_id,
                    duration_ms=dur_ms,
                    status="error",
                    error_message=f"HTTP {resp.status_code}: {err_msg}"
                )
                log_event("WARNING", f"DeepSeek API error {resp.status_code}: {err_msg}")
        except Exception as e:
            dur_ms = int((time.time() - t0) * 1000)
            record_ai_usage(
                provider="DeepSeek",
                model=model,
                task=task,
                video_id=video_id,
                duration_ms=dur_ms,
                status="error",
                error_message=str(e)
            )
            log_event("WARNING", f"DeepSeek ngoại lệ: {e}")

        return None

    def _call_gemini(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        task: str,
        video_id: str
    ) -> Optional[str]:
        models_to_try = [model]
        if model != "gemini-2.5-flash":
            models_to_try.append("gemini-2.5-flash")
        if "gemini-1.5-flash" not in models_to_try:
            models_to_try.append("gemini-1.5-flash")

        for m in models_to_try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": f"SYSTEM INSTRUCTION: {system_prompt}\n\nUSER REQUEST: {user_prompt}"}]
                    }
                ],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1500,
                    "responseMimeType": "application/json"
                }
            }

            t0 = time.time()
            try:
                resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
                dur_ms = int((time.time() - t0) * 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        usage = data.get("usageMetadata", {})
                        p_tokens = usage.get("promptTokenCount", 0)
                        c_tokens = usage.get("candidatesTokenCount", 0)
                        cost = estimate_cost(m, p_tokens, c_tokens)

                        record_ai_usage(
                            provider="Gemini",
                            model=m,
                            task=task,
                            video_id=video_id,
                            prompt_tokens=p_tokens,
                            completion_tokens=c_tokens,
                            estimated_cost=cost,
                            duration_ms=dur_ms,
                            status="success"
                        )

                        parts = candidates[0].get("content", {}).get("parts", [])
                        if parts:
                            return parts[0].get("text", "")
                else:
                    err_msg = resp.text[:200]
                    record_ai_usage(
                        provider="Gemini",
                        model=m,
                        task=task,
                        video_id=video_id,
                        duration_ms=dur_ms,
                        status="error",
                        error_message=f"HTTP {resp.status_code}: {err_msg}"
                    )
            except Exception as e:
                dur_ms = int((time.time() - t0) * 1000)
                record_ai_usage(
                    provider="Gemini",
                    model=m,
                    task=task,
                    video_id=video_id,
                    duration_ms=dur_ms,
                    status="error",
                    error_message=str(e)
                )
                continue

        return None

    def _call_openai(
        self,
        api_key: str,
        model: str,
        system_prompt: str,
        user_prompt: str,
        task: str,
        video_id: str
    ) -> Optional[str]:
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 1500,
            "response_format": {"type": "json_object"}
        }

        t0 = time.time()
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            dur_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 200:
                data = resp.json()
                usage = data.get("usage", {})
                p_tokens = usage.get("prompt_tokens", 0)
                c_tokens = usage.get("completion_tokens", 0)
                cost = estimate_cost(model, p_tokens, c_tokens)

                record_ai_usage(
                    provider="OpenAI",
                    model=model,
                    task=task,
                    video_id=video_id,
                    prompt_tokens=p_tokens,
                    completion_tokens=c_tokens,
                    estimated_cost=cost,
                    duration_ms=dur_ms,
                    status="success"
                )
                return data["choices"][0]["message"]["content"]
            else:
                err_msg = resp.text[:200]
                record_ai_usage(
                    provider="OpenAI",
                    model=model,
                    task=task,
                    video_id=video_id,
                    duration_ms=dur_ms,
                    status="error",
                    error_message=f"HTTP {resp.status_code}: {err_msg}"
                )
        except Exception as e:
            dur_ms = int((time.time() - t0) * 1000)
            record_ai_usage(
                provider="OpenAI",
                model=model,
                task=task,
                video_id=video_id,
                duration_ms=dur_ms,
                status="error",
                error_message=str(e)
            )

        return None

    def query_llm(
        self,
        system_prompt: str,
        user_prompt: str,
        task: str = "general_ai",
        video_id: str = "",
        custom_provider: Optional[str] = None,
        custom_model: Optional[str] = None
    ) -> Optional[str]:
        cfg = self._get_active_config()
        primary = (custom_provider or cfg.get("provider", "deepseek")).lower()

        # Thứ tự gọi provider
        providers_order = [primary]
        for p in ["deepseek", "gemini", "openai"]:
            if p not in providers_order:
                providers_order.append(p)

        for provider in providers_order:
            key = cfg.get(f"{provider}_key")
            if not key:
                continue

            model = custom_model if custom_model and provider == primary else cfg.get(f"{provider}_model")

            try:
                if provider == "deepseek":
                    res = self._call_deepseek(key, model or "deepseek-chat", system_prompt, user_prompt, task, video_id)
                elif provider == "gemini":
                    res = self._call_gemini(key, model or "gemini-2.5-flash", system_prompt, user_prompt, task, video_id)
                elif provider == "openai":
                    res = self._call_openai(key, model or "gpt-4o-mini", system_prompt, user_prompt, task, video_id)
                else:
                    res = None

                if res:
                    return res
            except Exception as e:
                log_event("WARNING", f"Thử gọi LLM {provider} ({model}) thất bại: {e}")
                continue

        return None

    def curate_viral_segment(
        self,
        transcript_segments: List[Dict[str, Any]],
        total_duration: float,
        target_duration: int = 65,
        video_title: str = "",
        video_id: str = "",
        custom_provider: Optional[str] = None,
        custom_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Phân tích transcript toàn bộ video để tìm phân đoạn kịch tính/hài hước nhất
        (Virality Score cao nhất) kéo dài 61s - 85s (chuẩn TikTok Creator Rewards > 1 phút).
        Tự động nhận diện ngôn ngữ (Tiếng Anh / Tiếng Việt) để sinh Hook, Title, Hashtag chuẩn ngách.
        """
        condensed_transcript = []
        for s in transcript_segments:
            st = s.get("start", 0)
            en = s.get("end", 0)
            txt = s.get("text", "").strip()
            if txt:
                condensed_transcript.append(f"[{st:.1f}s - {en:.1f}s] {txt}")

        # Cho phép LLM duyệt qua toàn bộ transcript (tối đa 1200 câu ~ 20-30 phút video)
        transcript_text = "\n".join(condensed_transcript[:1200])

        # Phát hiện ngôn ngữ chủ đạo từ tiêu đề và transcript
        sample_text = (video_title + " " + " ".join(condensed_transcript[:20])).lower()
        is_vietnamese = any(c in sample_text for c in "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")
        lang_instruction = "VIETNAMESE (Tiếng Việt)" if is_vietnamese else "ENGLISH (Tiếng Anh - match the source video language)"

        system_prompt = (
            "You are an elite viral video editor and content strategist for top TikTok/Reels/Shorts clipping agencies (OpusClip/Munch level).\n"
            f"TARGET LANGUAGE: {lang_instruction}. All output text (hook_3s, viral_title, description, hashtags) MUST match this target language.\n\n"
            "Your task is to analyze the entire timestamped transcript and select the SINGLE MOST VIRAL segment of length 61 to 85 seconds "
            "(strictly required for TikTok Creator Rewards Beta > 60s).\n\n"
            "VIRALITY RULES:\n"
            "1. THE HOOK (First 0-3s): Must start immediately on an explosive, shocking, or hilarious reaction/line. Cut out all boring intros or dead silence.\n"
            "2. THE CLIMAX & PAYOFF: Must capture the peak emotional peak (screaming, funniest punchline, shocking reveal, intense debate) and end on a natural punchline or suspenseful cliffhanger. NEVER cut mid-sentence!\n"
            "3. COMPILATION & MULTI-CLIP TITLES: If the source video or segment is a compilation of multiple funny moments (e.g. funny moments, clips that made famous, try not to laugh), DO NOT title it after just one minor passing moment or side character. Use proven high-CTR viral compilation titles such as 'iShowSpeed's Funniest Moments That Broke The Internet 😭', 'Try Not To Laugh: iShowSpeed Edition 💀', or 'The Clips That Made iShowSpeed Famous 😂'. The Hook banner should be punchy and overarching: 'TRY NOT TO LAUGH: ISHOWSPEED' or 'SPEED'S FUNNIEST MOMENTS'.\n"
            "4. NICHE HASHTAGS: Only use hashtags directly related to the video niche, topic, and creators (e.g., #ishowspeed #speed #funny #streamer #gaming #fyp). NEVER use irrelevant tags like #learnontiktok or #suthat for gaming/comedy!\n"
            "5. Return strictly valid JSON with no markdown formatting outside JSON."
        )

        user_prompt = (
            f"Video Title: {video_title}\n"
            f"Total Duration: {total_duration:.1f}s\n"
            f"Target Duration: {target_duration}s - 85s (must be >= 61.0s and <= 85.0s)\n\n"
            f"Transcript:\n{transcript_text}\n\n"
            "Output JSON with this exact schema:\n"
            "{\n"
            '  "start_time": <float: start timestamp in seconds>,\n'
            '  "end_time": <float: end timestamp in seconds, strictly end_time - start_time >= 61.0>,\n'
            '  "hook_3s": "<3-6 words in UPPERCASE without emojis, e.g. ISHOWSPEED FUNNIEST MOMENTS or TRY NOT TO LAUGH: SPEED>",\n'
            '  "viral_title": "<Compelling, high-CTR viral title with 1-2 emojis, matching compilation theme if multi-clip>",\n'
            '  "description": "<1-2 engaging sentences summarizing the moment and driving comments>",\n'
            '  "hashtags": "<5-8 highly relevant hashtags matching the creator, topic, and platform>",\n'
            '  "virality_score": <int 1-100>,\n'
            '  "explanation": "<Why this moment will blow up on TikTok>"\n'
            "}"
        )

        raw_json = self.query_llm(
            system_prompt,
            user_prompt,
            task="curate_viral_segment",
            video_id=video_id,
            custom_provider=custom_provider,
            custom_model=custom_model
        )
        if raw_json:
            try:
                cleaned = re.sub(r"^```json\s*", "", raw_json.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                data = json.loads(cleaned)
                start = float(data.get("start_time", 0))
                end = float(data.get("end_time", start + target_duration))

                # Đảm bảo độ dài tối thiểu 61s cho TikTok Beta
                if end - start < 61:
                    end = min(total_duration, start + max(61.0, float(target_duration)))

                hook = data.get("hook_3s", "").strip()
                title = data.get("viral_title", video_title).strip()
                desc = data.get("description", "").strip()
                tags = data.get("hashtags", "").strip()

                if not tags:
                    tags = "#ishowspeed #speed #speedclips #funny #viral #fyp" if not is_vietnamese else "#xuhuong #fyp #viral"

                return {
                    "start_time": max(0.0, start),
                    "end_time": min(total_duration, end),
                    "duration": round(end - start, 1),
                    "hook_3s": hook,
                    "viral_title": title,
                    "description": desc,
                    "hashtags": tags,
                    "virality_score": data.get("virality_score", 90),
                    "source": "cloud_llm"
                }
            except Exception as e:
                log_event("WARNING", f"Lỗi parse JSON từ LLM: {e}")

        # Heuristic fallback an toàn
        return self.fallback_heuristic_segment(total_duration, target_duration, video_title, video_id=video_id, is_vietnamese=is_vietnamese)

    def generate_hook_and_copy(self, raw_title: str, video_id: str = "") -> Dict[str, str]:
        """
        Sinh Hook 3s, Tiêu đề viral, Caption và Hashtag từ tiêu đề gốc chuẩn ngôn ngữ và nội dung
        """
        clean_title = raw_title.replace("#", "").strip()
        is_vietnamese = any(c in clean_title.lower() for c in "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ")
        lang = "VIETNAMESE" if is_vietnamese else "ENGLISH"

        system_prompt = (
            f"You are a master TikTok copywriter. Language MUST be {lang}.\n"
            "Create high-CTR, niche-accurate metadata for this video.\n"
            "Requirements:\n"
            "- hook_3s: 3-6 bold words in UPPERCASE teasing the biggest moment.\n"
            "- viral_title: Curiosity-inducing title with 1-2 emojis, 100% relevant to the subject.\n"
            "- description: 1 short sentence driving viewer comments.\n"
            "- hashtags: 5-7 niche-specific hashtags matching the subject. DO NOT use generic #learnontiktok on entertainment!\n"
            "Output JSON with keys: hook_3s, viral_title, description, hashtags."
        )

        user_prompt = f"Video title: {clean_title}"

        raw_json = self.query_llm(system_prompt, user_prompt, task="generate_hook_copy", video_id=video_id)
        if raw_json:
            try:
                cleaned = re.sub(r"^```json\s*", "", raw_json.strip())
                cleaned = re.sub(r"\s*```$", "", cleaned)
                data = json.loads(cleaned)
                return {
                    "hook": data.get("hook_3s", clean_title[:40].upper()),
                    "viral_title": data.get("viral_title", f"{clean_title} 😱"),
                    "description": data.get("description", "Drop your thoughts below! Follow for more."),
                    "tags": data.get("hashtags", "#viral #fyp #trending")
                }
            except Exception:
                pass

        # Heuristic fallback chuẩn ngôn ngữ
        if is_vietnamese:
            return {
                "hook": f"CHI TIẾT BẤT NGỜ: {clean_title[:30]}".upper(),
                "viral_title": f"{clean_title} 😱 Xem ngay!",
                "description": "Nhớ thả tim và follow kênh để không bỏ lỡ phần tiếp theo!",
                "tags": "#xuhuong #fyp #viral #trending"
            }
        else:
            return {
                "hook": f"WAIT TILL THE END: {clean_title[:30]}".upper(),
                "viral_title": f"{clean_title} 😭",
                "description": "What was your reaction? Follow for more viral clips!",
                "tags": "#ishowspeed #speed #viral #fyp #trending"
            }

    def fallback_heuristic_segment(
        self,
        total_duration: float,
        target_duration: int,
        video_title: str,
        video_id: str = "",
        is_vietnamese: bool = False
    ) -> Dict[str, Any]:
        """Dự phòng thuật toán khi chưa có LLM phản hồi"""
        start = 0.0
        if total_duration > 150:
            start = 15.0

        dur = min(float(target_duration), total_duration - start)
        dur = max(61.0, dur) if total_duration >= 61 else total_duration
        end = min(total_duration, start + dur)

        copy_data = self.generate_hook_and_copy(video_title, video_id=video_id)
        return {
            "start_time": start,
            "end_time": end,
            "duration": end - start,
            "hook_3s": copy_data["hook"],
            "viral_title": copy_data["viral_title"],
            "description": copy_data["description"],
            "hashtags": copy_data["tags"],
            "virality_score": 75,
            "source": "heuristic_fallback"
        }

llm_curator = LLMCurator()
