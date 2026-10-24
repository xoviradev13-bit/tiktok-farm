"""
session_reader.py
-----------------
Compatibility bridge: delegates to gpm_profile_reader.py
Reads TikTok cookies and stats directly from GPMLogin's profile storage on disk.
"""

from typing import Dict, Any, List, Optional
from backend.modules.gpm_profile_reader import (
    fetch_account_info_from_gpm,
    is_gpm_reader_available,
    get_gpm_storage_path,
    list_gpm_profiles_status,
    load_gpm_profile_cookies
)

session_reader_available = is_gpm_reader_available()
SESSIONS_DIR = get_gpm_storage_path() or ""

def fetch_account_info_from_session(gpm_id: str) -> Dict[str, Any]:
    """Compatibility wrapper calling gpm_profile_reader"""
    return fetch_account_info_from_gpm(gpm_id)

def list_available_sessions() -> List[Dict[str, Any]]:
    """Compatibility wrapper listing GPM profiles status"""
    status = list_gpm_profiles_status()
    out = []
    for p in status.get("profiles", []):
        out.append({
            "gpm_id": p["profile_id"],
            "has_session_file": p["has_cookie_file"],
            "has_auth_cookie": p["has_sessionid"],
            "is_valid": p["has_sessionid"],
            "last_updated": p.get("last_updated"),
            "session_file": f"{status.get('storage_path')}\\{p['profile_id']}\\Default\\GPMSoft\\Exporter\\ExportCookies.json"
        })
    return out

def is_session_reader_available() -> bool:
    return is_gpm_reader_available()
