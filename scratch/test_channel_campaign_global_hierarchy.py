import sys
import os
import sqlite3

# Add backend to sys.path
sys.path.insert(0, os.path.abspath('.'))

from backend.database import init_db, get_connection
from backend.modules.yt_monitor import YouTubeRSSMonitor
from fastapi.testclient import TestClient
from backend.app import app

init_db()
client = TestClient(app)

def test_hierarchy_resolution():
    print("=== Testing Priority: Channel > Campaign > Global ===")
    conn = get_connection()
    c = conn.cursor()

    # 1. Setup Global Settings
    client.post("/api/settings/download-filter", json={
        "min_video_duration": 100,
        "max_video_duration": 1000,
        "include_shorts": True,
        "include_longform": True
    })

    # Create dummy channel
    test_ch_id = "UC_TEST_HIERARCHY_001"
    c.execute("DELETE FROM channels WHERE channel_id = ?", (test_ch_id,))
    c.execute("""
        INSERT INTO channels (channel_id, title, url, is_active, min_video_duration, max_video_duration, include_shorts, include_longform)
        VALUES (?, 'Hierarchy Test Ch', 'https://youtube.com', 1, NULL, NULL, NULL, NULL)
    """, (test_ch_id,))
    conn.commit()

    monitor = YouTubeRSSMonitor()

    # Test Level 3: Global fallback (Channel and Campaign are unset)
    limits = monitor.get_effective_duration_limits(test_ch_id)
    print(f"Fallback to Global: {limits}")
    assert limits[0] == 100 and limits[1] == 1000 and bool(limits[2]) is True and bool(limits[3]) is True, f"Expected global (100, 1000, True, True), got {limits}"

    # Test Level 2: Campaign overrides Global
    camp_res = client.post("/api/campaigns", json={
        "name": "Campaign Hierarchy Test",
        "channel_ids": [test_ch_id],
        "gpm_profile_ids": [1],
        "min_video_duration": 222,
        "max_video_duration": 2222,
        "include_shorts": 0,
        "include_longform": 1
    })
    assert camp_res.status_code == 200, camp_res.text
    camp_id = camp_res.json()["id"]

    limits_camp = monitor.get_effective_duration_limits(test_ch_id, force_campaign_id=camp_id)
    print(f"Override by Campaign: {limits_camp}")
    assert limits_camp == (222, 2222, 0, 1), f"Expected campaign (222, 2222, 0, 1), got {limits_camp}"

    # Test Level 1: Channel overrides Campaign and Global
    ch_up_res = client.post("/api/youtube/channels/update", json={
        "channel_id": test_ch_id,
        "min_video_duration": 333,
        "max_video_duration": 3333,
        "include_shorts": 1,
        "include_longform": 0
    })
    assert ch_up_res.status_code == 200, ch_up_res.text

    limits_channel = monitor.get_effective_duration_limits(test_ch_id, force_campaign_id=camp_id)
    print(f"Override by Channel: {limits_channel}")
    assert limits_channel == (333, 3333, 1, 0), f"Expected channel (333, 3333, 1, 0), got {limits_channel}"

    # Clean up
    c.execute("DELETE FROM channels WHERE channel_id = ?", (test_ch_id,))
    c.execute("DELETE FROM campaigns WHERE id = ?", (camp_id,))
    conn.commit()
    conn.close()
    print("✅ Priority Channel > Campaign > Global test PASSED!")

if __name__ == "__main__":
    test_hierarchy_resolution()
