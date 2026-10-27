"""
YouTube niche-channel scanner (hardened version, extended data model).

Design goals
------------
1. Survive YouTube changes: every fragile step has a fallback, and parsing
   walks the JSON generically instead of following one hard-coded path.
2. Fail loudly: every failure is logged, and a health check warns when
   results look broken (0 channels, mostly-failed RSS, ...).
3. Stay cheap: the official API is used only for channels.list
   (1 unit per 50 channels, even with snippet+statistics+brandingSettings+
   topicDetails). Discovery, upload dates and cadence cost 0 quota.

Discovery fallback chain
    A. HTML scrape of ytInitialData (+ continuation paging)
         A1. parse channelRenderer nodes anywhere in the JSON
         A2. if that finds nothing, regex raw UC... channel IDs
    B. yt-dlp video search, grouped by channel
    C. Official API search.list (only if YOUTUBE_API_KEY is set; 100 units/page)

Stats fallback chain
    API channels.list  ->  scraped sub text  ->  yt-dlp

Stored per channel (table `channels`)
    Identity     channel_id, url, handle, title, description, country,
                 created_at, thumbnail_url
    Size         subscriber_count, hidden_subs, video_count, total_view_count
    Activity     last_upload_date, upload_cadence_days, is_active
    Performance  avg_views_recent, median_views_recent, top_recent_video_views,
                 views_per_sub_ratio, avg_views_lifetime, videos_per_month_lifetime
    Niche        recent_video_titles (JSON), keywords (JSON),
                 topic_categories (JSON), default_language
    Tracking     first_seen, last_checked, found_via_keyword, stats_source

Growth history (table `channel_history`): one snapshot per channel per day.
Use YouTubeScanner.get_channel_growth() to read growth over a time window.

Optional: set the environment variable YOUTUBE_API_KEY for exact
subscriber / video counts and the API-only fields (handle, description,
country, created_at, keywords, topics, language, total views).
"""

import concurrent.futures
import json
import os
import random
import re
import shlex
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

import yt_dlp

from backend.config import YOUTUBE_API_KEY as _CONFIG_YT_KEY
from backend.database import get_connection, log_event

# --------------------------------------------------------------------------- #
# Config & Multi-Key Pool Manager
# --------------------------------------------------------------------------- #
class YouTubeKeyPool:
    """
    Quản lý danh sách các khóa YouTube Data API v3 (Pool).
    Hỗ trợ xoay vòng (Round-Robin), tự động chuyển key (Auto-Failover) khi một key
    chạm giới hạn Quota (10k units/ngày) hoặc gặp lỗi 403/429.
    """
    def __init__(self, raw_keys: Optional[str] = None):
        self._keys: List[str] = []
        self._disabled_until: Dict[str, float] = {}
        self._current_idx: int = 0
        if raw_keys:
            self.set_keys(raw_keys)

    def set_keys(self, raw: str):
        if not raw:
            self._keys = []
            return
        parts = [k.strip() for k in re.split(r"[,;\n\s]+", raw) if k.strip()]
        seen = set()
        new_keys = []
        for k in parts:
            if k not in seen:
                seen.add(k)
                new_keys.append(k)
        self._keys = new_keys
        if self._current_idx >= len(self._keys):
            self._current_idx = 0

    @property
    def total_keys(self) -> int:
        return len(self._keys)

    @property
    def keys(self) -> List[str]:
        return list(self._keys)

    def get_keys_status(self) -> List[Dict[str, Any]]:
        now = time.time()
        res = []
        for idx, k in enumerate(self._keys):
            cooldown = self._disabled_until.get(k, 0.0)
            is_active = cooldown <= now
            masked = k[:6] + "..." + k[-4:] if len(k) > 10 else k
            res.append({
                "index": idx,
                "key_masked": masked,
                "full_key": k,
                "is_active": is_active,
                "cooldown_remaining_sec": max(0, int(cooldown - now)),
                "is_current": (idx == self._current_idx),
            })
        return res

    def get_active_key(self) -> Optional[str]:
        if not self._keys:
            return None
        now = time.time()
        for i in range(len(self._keys)):
            idx = (self._current_idx + i) % len(self._keys)
            key = self._keys[idx]
            if self._disabled_until.get(key, 0.0) <= now:
                self._current_idx = idx
                return key
        return None

    def mark_key_exhausted(self, key: str, reason: str = "quotaExceeded", cooldown_hours: float = 12.0) -> Optional[str]:
        now = time.time()
        self._disabled_until[key] = now + (cooldown_hours * 3600)
        masked = key[:6] + "..." + key[-4:] if len(key) > 10 else "KEY"
        log_event("WARNING", f"YouTube API Key ({masked}) bị lỗi/hết quota: '{reason}'. Tạm dừng {cooldown_hours}h.")
        
        # Advance index to next key
        if len(self._keys) > 1:
            self._current_idx = (self._current_idx + 1) % len(self._keys)
        next_key = self.get_active_key()
        if next_key and next_key != key:
            next_masked = next_key[:6] + "..." + next_key[-4:] if len(next_key) > 10 else "KEY"
            log_event("INFO", f"🔄 Đã tự động xoay sang YouTube API Key dự phòng: {next_masked}")
        elif not next_key:
            log_event("WARNING", "⚠️ Toàn bộ danh sách YouTube API Key đều đã hết quota. Hệ thống chuyển sang cào dữ liệu miễn phí (Scrape/yt-dlp).")
        return next_key


YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", _CONFIG_YT_KEY).strip()
RSS_WORKERS = 10             # keep low to avoid rate limits
CACHE_TTL_HOURS = 12         # skip re-analysing channels checked recently
MAX_CONTINUATION_PAGES = 20
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
CHANNEL_ID_RE = re.compile(r"^UC[\w-]{22}$")

# Columns added to the existing `channels` table (idempotent migration).
EXTRA_COLUMNS: Dict[str, str] = {
    # identity
    "handle": "TEXT",
    "description": "TEXT",
    "country": "TEXT",
    "created_at": "TEXT",
    "thumbnail_url": "TEXT",
    # size
    "total_view_count": "INTEGER",
    "hidden_subs": "INTEGER",
    # performance
    "avg_views_recent": "INTEGER",
    "median_views_recent": "INTEGER",
    "top_recent_video_views": "INTEGER",
    "views_per_sub_ratio": "REAL",
    "avg_views_lifetime": "INTEGER",
    "videos_per_month_lifetime": "REAL",
    # niche signals
    "recent_video_titles": "TEXT",   # JSON list
    "keywords": "TEXT",              # JSON list
    "topic_categories": "TEXT",      # JSON list
    "default_language": "TEXT",
    # tracking
    "first_seen": "TEXT",
    "last_checked": "TEXT",
    "found_via_keyword": "TEXT",
    "stats_source": "TEXT",
}

HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS channel_history (
    channel_id        TEXT NOT NULL,
    snapshot_date     TEXT NOT NULL,   -- YYYY-MM-DD (UTC), one row per day
    recorded_at       TEXT NOT NULL,
    subscriber_count  INTEGER,
    total_view_count  INTEGER,
    video_count       INTEGER,
    avg_views_recent  INTEGER,
    PRIMARY KEY (channel_id, snapshot_date)
)
"""

# Fields stored as JSON text in SQLite but kept as Python lists in memory.
JSON_FIELDS = ("recent_video_titles", "keywords", "topic_categories")

# Upsert policy for each column when a channel already exists:
_UPSERT_OVERWRITE = ("title", "url", "upload_cadence_days", "last_upload_date", "is_active")
# Columns that only come from the RSS feed. If RSS failed this run, an existing
# row must keep its old values instead of being reset to "N/A" / inactive.
_RSS_FIELDS = ("upload_cadence_days", "last_upload_date", "is_active")
# Unknown (0/None) never overwrites a good stored value:
_UPSERT_KEEP_IF_POSITIVE = (
    "subscriber_count", "video_count", "avg_views", "total_view_count",
    "avg_views_recent", "median_views_recent", "top_recent_video_views",
    "avg_views_lifetime", "videos_per_month_lifetime",
)
# Empty/NULL never overwrites a good stored value:
_UPSERT_KEEP_IF_PRESENT = (
    "handle", "description", "country", "created_at", "thumbnail_url",
    "recent_video_titles", "keywords", "topic_categories", "default_language",
    "views_per_sub_ratio", "hidden_subs", "stats_source", "last_checked",
)
_REQUIRED_INT_COLUMNS = ("subscriber_count", "video_count", "avg_views")


# --------------------------------------------------------------------------- #
# Generic helpers
# --------------------------------------------------------------------------- #
def _http_request(
    url: str,
    data: Optional[bytes] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: float = 8,
    retries: int = 2,
) -> Tuple[int, bytes]:
    """
    GET/POST with retry + exponential backoff on 429/5xx/network errors.
    Returns (status_code, body). status_code == 0 means a network failure.
    """
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept-Language": "en-US,en;q=0.9",
        # Best-effort bypass of the EU consent interstitial
        "Cookie": "CONSENT=YES+1; SOCS=CAI",
    }
    if headers:
        hdrs.update(headers)

    status, body = 0, b""
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=data, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = e.read()
            except Exception:
                body = b""
            if status in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep((2 ** attempt) + random.random())
                continue
            return status, body
        except Exception as e:
            status = 0
            if attempt < retries:
                time.sleep((2 ** attempt) + random.random())
                continue
            log_event("WARNING", f"HTTP lỗi mạng ({url[:80]}...): {e}")
    return status, body


def _walk_key(obj: Any, key: str) -> Generator[Any, None, None]:
    """Yield every value stored under `key`, at any depth, in document order."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == key:
                yield v
            if isinstance(v, (dict, list)):
                yield from _walk_key(v, key)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_key(item, key)


def _text(node: Any) -> str:
    """Read YouTube's {simpleText} / {runs:[{text}]} text objects."""
    if isinstance(node, str):
        return node
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return node["simpleText"] or ""
    if "runs" in node:
        return "".join(r.get("text", "") for r in node["runs"] if isinstance(r, dict))
    if "content" in node:  # newer view-model style
        return node["content"] or ""
    return ""


def _extract_initial_data(html: str) -> Optional[Dict[str, Any]]:
    """
    Pull the ytInitialData JSON out of the page without relying on what
    follows it (the old regex needed an exact ';</script>' ending).
    """
    decoder = json.JSONDecoder()
    start = 0
    while True:
        pos = html.find("ytInitialData", start)
        if pos == -1:
            return None
        brace = html.find("{", pos)
        if brace == -1:
            return None
        try:
            obj, _ = decoder.raw_decode(html, brace)
            if isinstance(obj, dict):
                return obj
        except ValueError:
            pass
        start = pos + len("ytInitialData")


def _parse_sub_count(text: str) -> int:
    """'62.6M subscribers' / '504K subscribers' -> int."""
    if not text:
        return 0
    text = text.upper().replace(",", "").strip()
    m = re.search(r"(\d+(?:\.\d+)?)\s*([KMB]?)", text)
    if not m:
        return 0
    try:
        num = float(m.group(1))
    except ValueError:
        return 0
    num *= {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(m.group(2), 1)
    return int(num)


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp (with 'Z' or offset) into an aware datetime."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_keywords(raw: str) -> List[str]:
    """brandingSettings keywords: space-separated, multi-word tags in quotes."""
    if not raw:
        return []
    try:
        return [k for k in shlex.split(raw) if k]
    except ValueError:  # unbalanced quotes
        return [k for k in raw.replace('"', " ").split() if k]


def _parse_topic_categories(urls: Any) -> List[str]:
    """['https://en.wikipedia.org/wiki/Video_game'] -> ['Video game']"""
    out: List[str] = []
    if not isinstance(urls, list):
        return out
    for u in urls:
        if not isinstance(u, str):
            continue
        name = urllib.parse.unquote(u.rstrip("/").rsplit("/", 1)[-1]).replace("_", " ").strip()
        if name and name not in out:
            out.append(name)
    return out


def _parse_api_channel(it: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten one channels.list item (snippet+statistics+branding+topics)."""
    sn = it.get("snippet") or {}
    st = it.get("statistics") or {}
    br = (it.get("brandingSettings") or {}).get("channel") or {}
    tp = it.get("topicDetails") or {}

    hidden = bool(st.get("hiddenSubscriberCount"))
    thumbs = sn.get("thumbnails") or {}
    thumb = ""
    for size in ("medium", "high", "default"):
        thumb = (thumbs.get(size) or {}).get("url", "")
        if thumb:
            break

    return {
        "subscriber_count": 0 if hidden else int(st.get("subscriberCount", 0) or 0),
        "video_count": int(st.get("videoCount", 0) or 0),
        "total_view_count": int(st.get("viewCount", 0) or 0),
        "hidden_subs": hidden,
        "handle": sn.get("customUrl", "") or "",
        "description": sn.get("description", "") or "",
        "country": sn.get("country", "") or br.get("country", "") or "",
        "created_at": sn.get("publishedAt", "") or "",
        "thumbnail_url": thumb,
        "default_language": sn.get("defaultLanguage", "") or br.get("defaultLanguage", "") or "",
        "keywords": _parse_keywords(br.get("keywords", "")),
        "topic_categories": _parse_topic_categories(tp.get("topicCategories")),
        "api_title": sn.get("title", "") or "",
    }


def _parse_channel_renderer(ch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Convert one channelRenderer into our channel dict. The subscriber count and
    the @handle swap between videoCountText / subscriberCountText depending on
    the layout, so we classify by content instead of by field name.
    """
    channel_id = ch.get("channelId", "")
    if not CHANNEL_ID_RE.match(channel_id or ""):
        return None

    sub_text = ""
    for field in ("subscriberCountText", "videoCountText"):
        t = _text(ch.get(field))
        if re.search(r"subscriber", t, re.IGNORECASE):
            sub_text = t
            break

    return {
        "channel_id": channel_id,
        "title": _text(ch.get("title")) or "",
        # /channel/<id> never changes, unlike handles
        "url": f"https://www.youtube.com/channel/{channel_id}",
        "sample_view_count": 0,
        "subscriber_count_scraped": _parse_sub_count(sub_text),
        "hit_count": 1,
    }


def _cadence_description(cadence_days: float, video_count: int) -> str:
    if cadence_days < 0:
        if video_count == 1:
            return "Mới có 1 video"
        if video_count == 0:
            return "Chưa có video"
        return "Chưa đủ dữ liệu chu kỳ"
    if cadence_days < 0.05:
        hours = max(0.1, round(cadence_days * 24.0, 1))
        return f"~{hours}h / video (Siêu dày)"
    if cadence_days < 0.85:
        hours = round(cadence_days * 24.0, 1)
        v_per_day = max(1, int(round(24.0 / max(0.1, hours))))
        return f"{v_per_day} vid/ngày (~{hours}h/vid)"
    if cadence_days <= 1.25:
        return "1 ngày / video (Hàng ngày)"
    return f"Khoảng {round(cadence_days, 1)} ngày / video"


def _db_value(ch: Dict[str, Any], col: str) -> Any:
    """Prepare one channel field for SQLite (lists -> JSON, required ints -> 0)."""
    v = ch.get(col)
    if col in JSON_FIELDS:
        return json.dumps(v, ensure_ascii=False) if isinstance(v, (list, tuple)) and v else None
    if col in _REQUIRED_INT_COLUMNS:
        return v or 0
    if isinstance(v, bool):
        return int(v)
    return v


# --------------------------------------------------------------------------- #
# Scanner
# --------------------------------------------------------------------------- #
class YouTubeScanner:
    def __init__(self):
        self.ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "skip_download": True,
        }
        self.key_pool = YouTubeKeyPool(os.getenv("YOUTUBE_API_KEYS", os.getenv("YOUTUBE_API_KEY", _CONFIG_YT_KEY)))
        self._schema_checked = False

    def reload_keys(self, raw_keys: Optional[str] = None):
        """Nạp lại danh sách key sau khi cập nhật từ UI/file .env"""
        if raw_keys is None:
            raw_keys = os.getenv("YOUTUBE_API_KEYS", os.getenv("YOUTUBE_API_KEY", ""))
        self.key_pool.set_keys(raw_keys)
        log_event("INFO", f"Key Pool đã nạp lại: {self.key_pool.total_keys} YouTube API Key")

    def test_key(self, key: str) -> Dict[str, Any]:
        """Kiểm tra tính hợp lệ và quota khả dụng của một YouTube API Key"""
        if not key or not key.strip():
            return {"valid": False, "message": "Key không được để trống"}
        k = key.strip()
        params = {
            "part": "snippet",
            "id": "UC_x5XG1OV2P6uZZ5FSM9Ttw",
            "key": k,
        }
        status, body = _http_request(
            "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode(params),
            retries=0, timeout=6,
        )
        if status == 200:
            return {"valid": True, "message": "Kết nối thành công! API Key hợp lệ và còn quota."}
        reason = "Lỗi kết nối"
        try:
            reason = json.loads(body)["error"]["errors"][0]["reason"]
        except Exception:
            pass
        return {"valid": False, "message": f"HTTP {status}: {reason}"}

    # ------------------------------------------------------------------ #
    # Discovery
    # ------------------------------------------------------------------ #
    def _collect_channels(self, data: Any, found: Dict[str, Dict[str, Any]], max_results: int):
        """Collect every channelRenderer anywhere in a JSON blob."""
        for ch in _walk_key(data, "channelRenderer"):
            if not isinstance(ch, dict):
                continue
            parsed = _parse_channel_renderer(ch)
            if parsed and parsed["channel_id"] not in found:
                parsed["rank"] = len(found)
                found[parsed["channel_id"]] = parsed
                if len(found) >= max_results:
                    return

    def _collect_ids_fallback(self, data: Any, found: Dict[str, Dict[str, Any]], max_results: int):
        """
        Last-resort parser, used if YouTube renames channelRenderer: grab every
        browseId that looks like a channel ID. Title/subs get filled in later
        from RSS and the API.
        """
        for bid in _walk_key(data, "browseId"):
            if isinstance(bid, str) and CHANNEL_ID_RE.match(bid) and bid not in found:
                found[bid] = {
                    "channel_id": bid,
                    "title": "",
                    "url": f"https://www.youtube.com/channel/{bid}",
                    "sample_view_count": 0,
                    "subscriber_count_scraped": 0,
                    "hit_count": 1,
                    "rank": len(found),
                }
                if len(found) >= max_results:
                    return

    @staticmethod
    def _find_continuation_token(data: Any) -> Optional[str]:
        for cmd in _walk_key(data, "continuationCommand"):
            if isinstance(cmd, dict) and cmd.get("token"):
                return cmd["token"]
        return None

    def _discover_via_html(self, keyword: str, max_results: int) -> Dict[str, Dict[str, Any]]:
        found: Dict[str, Dict[str, Any]] = {}
        url = (
            "https://www.youtube.com/results"
            f"?search_query={urllib.parse.quote(keyword)}&sp=EgIQAg%3D%3D&hl=en&gl=US"
        )
        status, raw = _http_request(url, timeout=10)
        if status != 200 or not raw:
            log_event("WARNING", f"[A] Trang search trả về HTTP {status}")
            return found

        html = raw.decode("utf-8", errors="ignore")
        if "consent.youtube.com" in html[:5000]:
            log_event("WARNING", "[A] Bị chuyển sang trang consent của YouTube")

        data = _extract_initial_data(html)
        if not data:
            log_event("WARNING", "[A] Không tìm thấy ytInitialData – cấu trúc trang có thể đã đổi")
            return found

        self._collect_channels(data, found, max_results)
        if not found:
            log_event("WARNING", "[A1] Không thấy channelRenderer, thử parse channel ID thô (A2)")
            self._collect_ids_fallback(data, found, max_results)

        # Continuation paging, using values read from the page itself so
        # nothing is hard-coded to an old client version.
        key_m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
        ver_m = re.search(r'"INNERTUBE_CONTEXT_CLIENT_VERSION"\s*:\s*"([^"]+)"', html) or \
            re.search(r'"clientVersion"\s*:\s*"([^"]+)"', html)
        api_key = key_m.group(1) if key_m else ""
        client_version = ver_m.group(1) if ver_m else "2.20240101.00.00"

        token = self._find_continuation_token(data)
        pages = 0
        while token and api_key and len(found) < max_results and pages < MAX_CONTINUATION_PAGES:
            payload = json.dumps({
                "context": {"client": {
                    "clientName": "WEB", "clientVersion": client_version,
                    "hl": "en", "gl": "US",
                }},
                "continuation": token,
            }).encode()
            status, body = _http_request(
                f"https://www.youtube.com/youtubei/v1/search?key={api_key}",
                data=payload,
                headers={"Content-Type": "application/json"},
                timeout=10,
            )
            if status != 200:
                log_event("WARNING", f"[A] Continuation HTTP {status}, dừng phân trang")
                break
            try:
                page = json.loads(body)
            except ValueError:
                log_event("WARNING", "[A] Continuation trả về JSON không hợp lệ")
                break
            before = len(found)
            self._collect_channels(page, found, max_results)
            if len(found) == before:
                self._collect_ids_fallback(page, found, max_results)
            token = self._find_continuation_token(page)
            pages += 1
            time.sleep(random.uniform(0.1, 0.4))

        return found

    def _discover_via_ytdlp(self, keyword: str, max_results: int) -> Dict[str, Dict[str, Any]]:
        found: Dict[str, Dict[str, Any]] = {}
        hits: Dict[str, int] = {}
        opts = {**self.ydl_opts, "extract_flat": "in_playlist"}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                result = ydl.extract_info(f"ytsearch{max_results * 4}:{keyword}", download=False)
            for item in (result.get("entries", []) if result else []):
                if not item:
                    continue
                cid = item.get("channel_id") or item.get("uploader_id")
                if not cid or not CHANNEL_ID_RE.match(cid):
                    continue
                hits[cid] = hits.get(cid, 0) + 1
                if cid not in found:
                    found[cid] = {
                        "channel_id": cid,
                        "title": item.get("channel") or item.get("uploader") or "",
                        "url": f"https://www.youtube.com/channel/{cid}",
                        "sample_view_count": item.get("view_count") or 0,
                        "subscriber_count_scraped": 0,
                        "hit_count": 0,
                    }
        except Exception as e:
            log_event("ERROR", f"[B] yt-dlp search thất bại: {e}")
            return {}

        top = sorted(found, key=lambda c: hits.get(c, 0), reverse=True)[:max_results]
        out = {}
        for rank, cid in enumerate(top):
            found[cid]["hit_count"] = hits.get(cid, 0)
            found[cid]["rank"] = rank
            out[cid] = found[cid]
        return out

    def _discover_via_api(self, keyword: str, max_results: int) -> Dict[str, Dict[str, Any]]:
        """Official search.list (100 units / page). Last resort only."""
        found: Dict[str, Dict[str, Any]] = {}
        key = self.key_pool.get_active_key()
        if not key:
            return found
        page_token = ""
        for _ in range(min(4, (max_results + 49) // 50)):
            key = self.key_pool.get_active_key()
            if not key:
                break
            params = {
                "part": "snippet", "type": "channel", "q": keyword,
                "maxResults": 50, "key": key,
            }
            if page_token:
                params["pageToken"] = page_token
            status, body = _http_request(
                "https://www.googleapis.com/youtube/v3/search?" + urllib.parse.urlencode(params),
                retries=1,
            )
            if status != 200:
                next_key = self._handle_api_error_pool(status, body, "search.list", key)
                if not next_key:
                    break
                continue  # retry with next key
            try:
                res = json.loads(body)
            except ValueError:
                break
            for it in res.get("items", []):
                cid = (it.get("id") or {}).get("channelId") or (it.get("snippet") or {}).get("channelId")
                if cid and cid not in found:
                    found[cid] = {
                        "channel_id": cid,
                        "title": (it.get("snippet") or {}).get("title", ""),
                        "url": f"https://www.youtube.com/channel/{cid}",
                        "sample_view_count": 0,
                        "subscriber_count_scraped": 0,
                        "hit_count": 1,
                        "rank": len(found),
                    }
                    if len(found) >= max_results:
                        return found
            page_token = res.get("nextPageToken", "")
            if not page_token:
                break
        return found

    def _discover(self, keyword: str, max_results: int) -> Dict[str, Dict[str, Any]]:
        for name, fn in (
            ("A: HTML scrape", self._discover_via_html),
            ("B: yt-dlp search", self._discover_via_ytdlp),
            ("C: official API", self._discover_via_api),
        ):
            try:
                found = fn(keyword, max_results)
            except Exception as e:
                log_event("ERROR", f"Chiến lược {name} lỗi: {e}")
                found = {}
            if found:
                log_event("INFO", f"Discovery '{keyword}': {len(found)} kênh qua chiến lược {name}")
                return found
            log_event("WARNING", f"Chiến lược {name} không trả về kênh nào, thử phương án tiếp theo")
        return {}

    # ------------------------------------------------------------------ #
    # Stats via official API (cheap: 1 unit per 50 channels)
    # ------------------------------------------------------------------ #
    def _handle_api_error_pool(self, status: int, body: bytes, where: str, current_key: str) -> Optional[str]:
        """Xử lý lỗi API với key_pool: mark key lỗi và trả về key tiếp theo (hoặc None nếu hết pool)."""
        reason = ""
        try:
            reason = json.loads(body)["error"]["errors"][0]["reason"]
        except Exception:
            pass
        quota_errors = ("quotaExceeded", "keyInvalid", "accessNotConfigured", "dailyLimitExceeded", "forbidden")
        if status in (400, 403, 429) and reason in quota_errors:
            return self.key_pool.mark_key_exhausted(current_key, reason, cooldown_hours=12.0)
        else:
            log_event("WARNING", f"API {where} HTTP {status} {reason}")
            return None

    def _fetch_stats_api(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        One channels.list call per 50 channels (1 quota unit) returning
        snippet + statistics + brandingSettings + topicDetails.
        Auto-rotates API keys on quota exhaustion.
        """
        out: Dict[str, Dict[str, Any]] = {}
        if not channel_ids:
            return out
        key = self.key_pool.get_active_key()
        if not key:
            return out
        i = 0
        while i < len(channel_ids):
            key = self.key_pool.get_active_key()
            if not key:
                log_event("WARNING", "_fetch_stats_api: Toàn bộ API key đã hết quota, dừng batch.")
                break
            batch = channel_ids[i:i + 50]
            params = {
                "part": "snippet,statistics,brandingSettings,topicDetails",
                "id": ",".join(batch),
                "key": key,
            }
            status, body = _http_request(
                "https://www.googleapis.com/youtube/v3/channels?" + urllib.parse.urlencode(params),
                retries=1,
            )
            if status != 200:
                next_key = self._handle_api_error_pool(status, body, "channels.list", key)
                if not next_key:
                    break
                continue  # retry same batch with new key
            try:
                items = json.loads(body).get("items", [])
            except ValueError:
                i += 50
                continue
            for it in items:
                try:
                    out[it["id"]] = _parse_api_channel(it)
                except Exception as e:
                    log_event("WARNING", f"API channels.list: lỗi parse {it.get('id')}: {e}")
            i += 50
        return out

    # ------------------------------------------------------------------ #
    # RSS (free, no quota): last upload, cadence, recent performance, titles
    # ------------------------------------------------------------------ #
    def _get_rss_cadence(self, channel_id: str) -> Optional[Dict[str, Any]]:
        if not channel_id:
            return None
        time.sleep(random.uniform(0.0, 0.2))  # de-synchronise worker threads
        status, xml_data = _http_request(
            f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}",
            timeout=6, retries=2,
        )
        if status != 200 or not xml_data:
            log_event("WARNING", f"RSS {channel_id}: HTTP {status}")
            return None
        try:
            root = ET.fromstring(xml_data)
        except ET.ParseError as e:
            log_event("WARNING", f"RSS {channel_id}: XML lỗi ({e})")
            return None

        atom = "{http://www.w3.org/2005/Atom}"
        mrss = "{http://search.yahoo.com/mrss/}"
        dates: List[datetime] = []
        views: List[int] = []
        titles: List[Tuple[datetime, str]] = []
        for entry in root.findall(f"{atom}entry"):
            dt = _parse_iso(entry.findtext(f"{atom}published"))
            if dt:
                dates.append(dt)
                vt = (entry.findtext(f"{atom}title") or "").strip()
                if vt:
                    titles.append((dt, vt))
            stat = entry.find(f".//{mrss}statistics")
            if stat is not None and "views" in stat.attrib:
                try:
                    views.append(int(stat.attrib["views"]))
                except ValueError:
                    pass

        title_node = root.find(f"{atom}title")
        feed_title = (title_node.text or "").strip() if title_node is not None else ""

        if not dates:
            return {"feed_title": feed_title, "empty": True}

        dates.sort(reverse=True)
        titles.sort(key=lambda t: t[0], reverse=True)
        last_date = dates[0]
        days_since = max(0, (datetime.now(timezone.utc) - last_date).days)

        gaps = [(dates[i] - dates[i + 1]).total_seconds() / 86400.0 for i in range(len(dates) - 1)]
        cadence = round(sum(gaps) / len(gaps), 2) if gaps else -1.0

        return {
            "feed_title": feed_title,
            "empty": False,
            "last_upload_date": last_date.strftime("%Y-%m-%d"),
            "days_since_last_upload": days_since,
            "upload_cadence_days": cadence,
            "is_active": 1 if days_since <= 30 else 0,
            "avg_views": int(sum(views) / len(views)) if views else 0,
            "median_views": int(statistics.median(views)) if views else 0,
            "top_views": max(views) if views else 0,
            "recent_titles": [t for _, t in titles],
            "recent_video_count": len(dates),
        }

    # ------------------------------------------------------------------ #
    # Per-channel analysis
    # ------------------------------------------------------------------ #
    def _ytdlp_channel_stats(self, channel_url: str) -> Tuple[int, int]:
        """Slow fallback: (subscribers, video_count). Returns zeros on failure."""
        try:
            url = channel_url.rstrip("/")
            if not url.endswith("/videos"):
                url += "/videos"
            opts = {**self.ydl_opts, "playlistend": 1}
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            if info:
                subs = info.get("channel_follower_count") or info.get("subscriber_count") or 0
                vids = info.get("playlist_count") or 0
                return int(subs), int(vids)
        except Exception as e:
            log_event("WARNING", f"yt-dlp stats lỗi cho {channel_url}: {e}")
        return 0, 0

    def analyze_channel_cadence(self, channel_url: str, basic_info: Dict[str, Any]) -> Dict[str, Any]:
        channel_id = basic_info.get("channel_id", "")
        title = basic_info.get("title", "")
        api = basic_info.get("api_stats") or {}

        subscribers = api.get("subscriber_count") or basic_info.get("subscriber_count_scraped", 0)
        video_count = api.get("video_count", 0)
        total_views = api.get("total_view_count", 0)
        avg_views = basic_info.get("sample_view_count", 0)
        stats_source = "api" if api else ("scrape" if subscribers else "none")

        if not title and api.get("api_title"):
            title = api["api_title"]

        last_upload_date = "N/A"
        days_since = 999
        cadence = -1.0
        is_active = 0
        rss_ok = False
        rss_video_count = 0
        avg_views_recent = 0
        median_views_recent = 0
        top_recent_views = 0
        recent_titles: List[str] = []

        rss = self._get_rss_cadence(channel_id)
        if rss:
            rss_ok = True
            if not title and rss.get("feed_title"):
                title = rss["feed_title"]
            if not rss.get("empty"):
                last_upload_date = rss["last_upload_date"]
                days_since = rss["days_since_last_upload"]
                cadence = rss["upload_cadence_days"]
                is_active = rss["is_active"]
                rss_video_count = rss["recent_video_count"]
                avg_views_recent = rss["avg_views"]
                median_views_recent = rss["median_views"]
                top_recent_views = rss["top_views"]
                recent_titles = rss["recent_titles"]
                if rss["avg_views"] > 0:
                    avg_views = rss["avg_views"]

        # Slow fallback only when we still have no subscriber number
        if subscribers == 0 and not api.get("hidden_subs"):
            yt_subs, yt_vids = self._ytdlp_channel_stats(channel_url)
            if yt_subs:
                subscribers, stats_source = yt_subs, "yt-dlp"
            if yt_vids and not video_count:
                video_count = yt_vids

        # ---- Derived metrics (None = unknown, never stored as a fake 0) ----
        views_per_sub = (
            round(avg_views_recent / subscribers, 4)
            if subscribers > 0 and avg_views_recent > 0 else None
        )
        avg_views_lifetime = (
            int(total_views / video_count) if total_views > 0 and video_count > 0 else 0
        )
        videos_per_month = 0.0
        created = _parse_iso(api.get("created_at"))
        if created and video_count > 0:
            age_days = (datetime.now(timezone.utc) - created).total_seconds() / 86400.0
            if age_days > 0:
                # floor the age at one month so brand-new channels don't explode the ratio
                videos_per_month = round(video_count / (max(age_days, 30.0) / 30.4375), 2)

        hidden = api.get("hidden_subs")
        return {
            # identity
            "channel_id": channel_id,
            "title": title or f"Channel {channel_id}",
            "url": channel_url,
            "handle": api.get("handle", ""),
            "description": api.get("description", ""),
            "country": api.get("country", ""),
            "created_at": api.get("created_at", ""),
            "thumbnail_url": api.get("thumbnail_url", ""),
            # size
            "subscriber_count": subscribers,
            "hidden_subs": None if hidden is None else int(bool(hidden)),
            "video_count": video_count,  # 0 = unknown (never the RSS count)
            "total_view_count": total_views,
            # activity
            "upload_cadence_days": cadence,
            "last_upload_date": last_upload_date,
            "days_since_last_upload": days_since,
            "is_active": is_active,
            "cadence_description": _cadence_description(cadence, video_count or rss_video_count),
            # performance
            "avg_views": avg_views,
            "avg_views_recent": avg_views_recent,
            "median_views_recent": median_views_recent,
            "top_recent_video_views": top_recent_views,
            "views_per_sub_ratio": views_per_sub,
            "avg_views_lifetime": avg_views_lifetime,
            "videos_per_month_lifetime": videos_per_month,
            # niche signals
            "recent_video_titles": recent_titles,
            "keywords": api.get("keywords", []),
            "topic_categories": api.get("topic_categories", []),
            "default_language": api.get("default_language", ""),
            # ranking / tracking
            "hit_count": basic_info.get("hit_count", 1),
            "rank": basic_info.get("rank", 0),
            "stats_source": stats_source,
            "rss_ok": rss_ok,
        }

    # ------------------------------------------------------------------ #
    # DB: schema, cache, save, growth
    # ------------------------------------------------------------------ #
    def _ensure_schema(self, conn):
        """Add missing columns to `channels` and create `channel_history` (idempotent)."""
        if self._schema_checked:
            return
        try:
            conn.execute(HISTORY_TABLE_SQL)
            cols = {r[1] for r in conn.execute("PRAGMA table_info(channels)").fetchall()}
            if cols:
                added = []
                for name, col_type in EXTRA_COLUMNS.items():
                    if name not in cols:
                        conn.execute(f"ALTER TABLE channels ADD COLUMN {name} {col_type}")
                        added.append(name)
                if "first_seen" in added:
                    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
                    conn.execute(
                        "UPDATE channels SET first_seen = COALESCE(last_checked, ?) "
                        "WHERE first_seen IS NULL",
                        (now,),
                    )
                if added:
                    log_event("INFO", f"Đã thêm {len(added)} cột mới vào bảng channels: {', '.join(added)}")
            conn.commit()
            self._schema_checked = bool(cols)
        except Exception as e:
            log_event("WARNING", f"Không kiểm tra được schema: {e}")

    def _load_cached(self, channel_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not channel_ids:
            return out
        try:
            conn = get_connection()
            try:
                self._ensure_schema(conn)
                ph = ",".join("?" * len(channel_ids))
                cur = conn.execute(
                    f"SELECT * FROM channels WHERE channel_id IN ({ph})", channel_ids
                )
                names = [d[0] for d in cur.description]
                rows = [dict(zip(names, tuple(r))) for r in cur.fetchall()]
            finally:
                conn.close()
        except Exception as e:
            log_event("WARNING", f"Không đọc được cache: {e}")
            return out

        now = datetime.now(timezone.utc)
        for r in rows:
            checked = _parse_iso(r.get("last_checked"))
            if not checked or (now - checked).total_seconds() > CACHE_TTL_HOURS * 3600:
                continue  # never checked / stale / bad value -> re-analyse

            days_since = 999
            try:
                d = datetime.strptime(r.get("last_upload_date") or "", "%Y-%m-%d").replace(tzinfo=timezone.utc)
                days_since = max(0, (now - d).days)
            except Exception:
                pass

            cadence = r.get("upload_cadence_days")
            cadence = cadence if cadence is not None else -1.0
            row = dict(r)
            for f in JSON_FIELDS:  # JSON text -> list
                try:
                    row[f] = json.loads(r.get(f) or "[]")
                except ValueError:
                    row[f] = []
            for f in ("subscriber_count", "video_count", "avg_views", "total_view_count",
                      "avg_views_recent", "median_views_recent", "top_recent_video_views",
                      "avg_views_lifetime"):
                row[f] = r.get(f) or 0
            row["videos_per_month_lifetime"] = r.get("videos_per_month_lifetime") or 0.0
            row.update({
                "upload_cadence_days": cadence,
                "last_upload_date": r.get("last_upload_date") or "N/A",
                "days_since_last_upload": days_since,
                "is_active": 1 if days_since <= 30 else 0,
                "cadence_description": _cadence_description(cadence, row["video_count"]),
                "stats_source": "cache",
                "rss_ok": True,
            })
            out[r["channel_id"]] = row
        return out

    def save_channels_to_db(self, channels: List[Dict[str, Any]]):
        """
        Upsert channels + write one growth snapshot per channel per day.
        Unknown (0/empty) values never overwrite good stored values;
        first_seen and found_via_keyword are only set the first time.
        """
        insert_cols = (
            ["channel_id"] + list(_UPSERT_OVERWRITE) + list(_UPSERT_KEEP_IF_POSITIVE)
            + list(_UPSERT_KEEP_IF_PRESENT) + ["found_via_keyword", "first_seen"]
        )
        update_parts = [f"{c} = excluded.{c}" for c in _UPSERT_OVERWRITE]
        update_parts += [
            f"{c} = CASE WHEN excluded.{c} > 0 THEN excluded.{c} ELSE channels.{c} END"
            for c in _UPSERT_KEEP_IF_POSITIVE
        ]
        update_parts += [
            f"{c} = COALESCE(NULLIF(excluded.{c}, ''), channels.{c})"
            for c in _UPSERT_KEEP_IF_PRESENT
        ]
        update_parts.append("found_via_keyword = COALESCE(channels.found_via_keyword, excluded.found_via_keyword)")
        # first_seen is intentionally NOT updated on conflict

        sql = (
            f"INSERT INTO channels ({', '.join(insert_cols)}) "
            f"VALUES ({', '.join('?' * len(insert_cols))}) "
            f"ON CONFLICT(channel_id) DO UPDATE SET {', '.join(update_parts)}"
        )
        # Variant used when RSS failed: same upsert, but the RSS columns are left
        # alone on existing rows (brand-new rows still get the placeholder values).
        rss_prefixes = tuple(f"{c} = " for c in _RSS_FIELDS)
        update_no_rss = [p for p in update_parts if not p.startswith(rss_prefixes)]
        sql_no_rss = (
            f"INSERT INTO channels ({', '.join(insert_cols)}) "
            f"VALUES ({', '.join('?' * len(insert_cols))}) "
            f"ON CONFLICT(channel_id) DO UPDATE SET {', '.join(update_no_rss)}"
        )

        conn = get_connection()
        try:
            self._ensure_schema(conn)
            cursor = conn.cursor()
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat(timespec="seconds")
            today = now_dt.strftime("%Y-%m-%d")
            saved = snapshots = rss_kept = 0
            for ch in channels:
                is_cached = ch.get("stats_source") == "cache"
                row = dict(ch)
                # Cached rows weren't re-checked this run: keep old timestamp/source
                row["last_checked"] = None if is_cached else now
                row["stats_source"] = None if is_cached else ch.get("stats_source")
                row["first_seen"] = now

                values = [_db_value(row, c) for c in insert_cols]
                # rss_ok is False only for freshly analysed channels whose RSS request failed
                if ch.get("rss_ok") is False:
                    cursor.execute(sql_no_rss, values)
                    rss_kept += 1
                else:
                    cursor.execute(sql, values)
                saved += 1

                # Growth snapshot (fresh data only, and only if we have real numbers)
                subs = ch.get("subscriber_count") or None
                total_views = ch.get("total_view_count") or None
                if not is_cached and (subs or total_views):
                    cursor.execute(
                        "INSERT OR REPLACE INTO channel_history "
                        "(channel_id, snapshot_date, recorded_at, subscriber_count, "
                        " total_view_count, video_count, avg_views_recent) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (
                            ch["channel_id"], today, now, subs, total_views,
                            ch.get("video_count") or None,
                            ch.get("avg_views_recent") or None,
                        ),
                    )
                    snapshots += 1
            conn.commit()
        finally:
            conn.close()
        log_event("INFO", f"Đã lưu/cập nhật {saved} kênh YouTube ({snapshots} snapshot lịch sử) vào cơ sở dữ liệu")
        if rss_kept:
            log_event("WARNING", f"{rss_kept} kênh lỗi RSS: giữ nguyên dữ liệu hoạt động/chu kỳ đã lưu")

    def get_channel_growth(self, channel_id: str, days: int = 30) -> Optional[Dict[str, Any]]:
        """
        Growth between the oldest and newest snapshot within the last `days` days.
        Returns None when fewer than 2 snapshots exist.
        """
        conn = get_connection()
        try:
            self._ensure_schema(conn)
            rows = [tuple(r) for r in conn.execute(
                "SELECT snapshot_date, subscriber_count, total_view_count "
                "FROM channel_history WHERE channel_id = ? "
                "AND snapshot_date >= date('now', ?) ORDER BY snapshot_date",
                (channel_id, f"-{int(days)} days"),
            ).fetchall()]
        except Exception as e:
            log_event("WARNING", f"Không đọc được lịch sử {channel_id}: {e}")
            return None
        finally:
            conn.close()

        if len(rows) < 2:
            return None
        (d0, s0, v0), (d1, s1, v1) = rows[0], rows[-1]
        span = max(1, (datetime.strptime(d1, "%Y-%m-%d") - datetime.strptime(d0, "%Y-%m-%d")).days)
        result: Dict[str, Any] = {
            "channel_id": channel_id, "from": d0, "to": d1, "span_days": span,
            "snapshots": len(rows),
        }
        if s0 and s1:
            result.update({
                "sub_delta": s1 - s0,
                "sub_growth_pct": round((s1 - s0) / s0 * 100, 2),
                "subs_per_day": round((s1 - s0) / span, 1),
            })
        if v0 and v1:
            result.update({
                "view_delta": v1 - v0,
                "views_per_day": round((v1 - v0) / span, 1),
            })
        return result

    # ------------------------------------------------------------------ #
    # Main entry point
    # ------------------------------------------------------------------ #
    def search_channels_by_keyword(
        self, keyword: str, max_results: int = 50, use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        log_event("INFO", f"Bắt đầu quét kênh YouTube cho từ khóa: '{keyword}' (Tối đa {max_results} kênh)")

        # 1. Discover
        found = self._discover(keyword, max_results)
        if not found:
            log_event(
                "ERROR",
                f"TẤT CẢ chiến lược discovery thất bại cho '{keyword}'. "
                "Nhiều khả năng YouTube đã đổi cấu trúc hoặc IP đang bị chặn.",
            )
            return []

        # 2. Split into cached vs. needs-analysis
        cached = self._load_cached(list(found)) if use_cache else {}
        to_analyze = {cid: d for cid, d in found.items() if cid not in cached}
        if cached:
            log_event("INFO", f"Dùng cache cho {len(cached)} kênh, phân tích mới {len(to_analyze)} kênh")

        # 3. Batch stats from the official API (≈ 1 unit per 50 channels)
        api_stats = self._fetch_stats_api(list(to_analyze))
        for cid, st in api_stats.items():
            if cid in to_analyze:
                to_analyze[cid]["api_stats"] = st

        # 4. RSS + fallbacks in parallel
        results: List[Dict[str, Any]] = []
        for cid, row in cached.items():
            row["hit_count"] = found[cid].get("hit_count", 1)
            row["rank"] = found[cid].get("rank", 0)
            results.append(row)

        rss_failed = 0
        if to_analyze:
            workers = min(RSS_WORKERS, len(to_analyze))
            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
                futures = {
                    ex.submit(self.analyze_channel_cadence, d["url"], d): cid
                    for cid, d in to_analyze.items()
                }
                for fut in concurrent.futures.as_completed(futures):
                    cid = futures[fut]
                    try:
                        res = fut.result()
                    except Exception as e:
                        log_event("WARNING", f"Lỗi phân tích kênh {cid}: {e}")
                        continue
                    if res:
                        if not res.get("rss_ok"):
                            rss_failed += 1
                        results.append(res)

        for r in results:
            r["found_via_keyword"] = keyword

        # 5. Health checks
        analyzed = len(to_analyze)
        if analyzed >= 5 and rss_failed / analyzed > 0.5:
            log_event(
                "WARNING",
                f"{rss_failed}/{analyzed} RSS request thất bại – có thể đang bị rate-limit. "
                "Giảm RSS_WORKERS hoặc chờ rồi thử lại.",
            )
        if len(results) < len(found):
            log_event("WARNING", f"Chỉ phân tích được {len(results)}/{len(found)} kênh tìm thấy")
        if analyzed and not api_stats and YOUTUBE_API_KEY:
            log_event("WARNING", "Có YOUTUBE_API_KEY nhưng không lấy được stats từ API – đang dùng fallback")

        # 6. Sort: hit_count -> title match -> active -> subscribers -> original search rank
        kw = keyword.lower()
        kw_words = [w for w in kw.split() if w]

        def _sort_key(x: Dict[str, Any]):
            t = (x.get("title") or "").lower()
            title_score = 2 if kw in t else (1 if any(w in t for w in kw_words) else 0)
            return (
                x.get("hit_count", 0), title_score, x.get("is_active", 0),
                x.get("subscriber_count", 0), -x.get("rank", 0),
            )

        results.sort(key=_sort_key, reverse=True)
        log_event("INFO", f"Hoàn thành phân tích {len(results)} kênh cho từ khóa '{keyword}'")
        return results

    def refresh_channel_stats(self, channel_id: str) -> Optional[Dict[str, Any]]:
        """
        Làm mới toàn bộ chỉ số (subscribers, views, upload cadence, tags, videos gần đây)
        của 1 kênh YouTube và cập nhật vào CSDL.
        """
        cid = (channel_id or "").strip()
        if not cid:
            return None

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM channels WHERE channel_id = ?", (cid,))
        row = cursor.fetchone()
        conn.close()

        existing = dict(row) if row else {}
        ch_url = existing.get("url") or f"https://www.youtube.com/channel/{cid}"

        basic_info: Dict[str, Any] = {
            "channel_id": cid,
            "title": existing.get("title", ""),
            "url": ch_url,
            "sample_view_count": existing.get("avg_views", 0),
            "subscriber_count_scraped": existing.get("subscriber_count", 0),
            "hit_count": 1,
            "rank": 0,
        }

        # 1. Lấy stats chính thức qua YouTube Data API v3 (nếu có key trong pool)
        try:
            api_stats = self._fetch_stats_api([cid])
            if cid in api_stats:
                basic_info["api_stats"] = api_stats[cid]
        except Exception as e:
            log_event("WARNING", f"Lỗi fetch API stats cho {cid}: {e}")

        # 2. Phân tích cadence qua RSS & fallback
        analyzed = self.analyze_channel_cadence(ch_url, basic_info)
        if not analyzed:
            return None

        # Giữ nguyên cấu hình mà người dùng đã thiết lập cho kênh
        if existing:
            for keep_col in (
                "is_active", "auto_download", "display_name", "custom_proxy",
                "download_dir", "render_dir", "auto_render", "bgm_folder",
                "bgm_volume", "min_video_duration", "max_video_duration",
                "include_shorts", "include_longform", "disable_subtitle_for_shorts",
                "subtitle_enabled", "subtitle_style", "subtitle_position"
            ):
                if existing.get(keep_col) is not None:
                    analyzed[keep_col] = existing[keep_col]

        # 3. Lưu dữ liệu đã cập nhật vào SQLite + lưu channel_history
        self.save_channels_to_db([analyzed])

        # 4. Trả về channel dictionary đã đồng bộ từ database
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            SELECT c.*, 
                (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id) as downloaded_count,
                (SELECT COUNT(*) FROM videos v WHERE v.channel_id = c.channel_id AND v.status = 'rendered') as rendered_count
            FROM channels c 
            WHERE c.channel_id = ?
        ''', (cid,))
        updated_row = cursor.fetchone()
        conn.close()

        if updated_row:
            ch_res = dict(updated_row)
            for field in ["keywords", "topic_categories", "recent_video_titles"]:
                if isinstance(ch_res.get(field), str):
                    try:
                        ch_res[field] = json.loads(ch_res[field])
                    except Exception:
                        ch_res[field] = []
            ch_res["is_saved"] = True
            log_event("INFO", f"Đã làm mới chỉ số kênh '{ch_res.get('title', cid)}' thành công.")
            return ch_res

        return analyzed


yt_scanner = YouTubeScanner()