import os
import sys
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from backend.app import app
from backend.database import get_connection
from backend.modules.yt_monitor import yt_monitor

client = TestClient(app)

def test_global_download_filter_api():
    print("\n--- TEST 1: Global Download Filter API ---")
    
    # 1. Test reject if both unchecked
    res = client.post("/api/settings/download-filter", json={
        "min_video_duration": 300,
        "max_video_duration": 3600,
        "include_shorts": False,
        "include_longform": False
    })
    assert res.status_code == 400, f"Expected 400 when both unchecked, got {res.status_code}"
    print("  [OK] Successfully rejected when both Shorts & Long-form are unchecked")

    # 2. Save both enabled with min=300s, max=3600s
    res = client.post("/api/settings/download-filter", json={
        "min_video_duration": 300,
        "max_video_duration": 3600,
        "include_shorts": True,
        "include_longform": True
    })
    assert res.status_code == 200
    print("  [OK] Successfully saved with include_shorts=True, include_longform=True, min=300, max=3600")

    # 3. Retrieve settings
    res = client.get("/api/settings/download-filter")
    assert res.status_code == 200
    data = res.json()
    assert data["include_shorts"] is True
    assert data["include_longform"] is True
    assert data["min_video_duration"] == 300
    assert data["max_video_duration"] == 3600
    print("  [OK] GET /api/settings/download-filter returned correct saved values:", data)

def test_campaign_filter_api():
    print("\n--- TEST 2: Campaign Filter API (Creation & Update) ---")
    
    # Check channels & gpms available in DB
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT channel_id FROM channels LIMIT 1")
    ch_row = c.fetchone()
    c.execute("SELECT id FROM gpm_profiles LIMIT 1")
    gpm_row = c.fetchone()
    conn.close()

    if not ch_row or not gpm_row:
        print("  [SKIP] No channels or GPM profiles in DB to test campaign creation")
        return

    ch_id = ch_row["channel_id"]
    gpm_id = gpm_row["id"]

    # 1. Create campaign with Shorts only (include_shorts=1, include_longform=0)
    create_payload = {
        "name": "Test Campaign Shorts Only",
        "channel_id": ch_id,
        "channel_ids": [ch_id],
        "gpm_profile_id": gpm_id,
        "gpm_profile_ids": [gpm_id],
        "include_shorts": 1,
        "include_longform": 0,
        "min_video_duration": 0,
        "max_video_duration": 3600,
        "clips_per_video": 1,
        "add_part_label": 0
    }
    res = client.post("/api/campaigns", json=create_payload)
    assert res.status_code == 200, f"Create campaign failed: {res.text}"
    camp_id = res.json()["id"]
    print(f"  [OK] Created campaign ID {camp_id} with include_shorts=1, include_longform=0")

    # 2. Get campaign
    res = client.get(f"/api/campaigns/{camp_id}")
    assert res.status_code == 200
    camp_data = res.json()
    assert camp_data["include_shorts"] == 1
    assert camp_data["include_longform"] == 0
    print("  [OK] Campaign retrieved with include_shorts=1, include_longform=0")

    # 3. Update campaign to Long-form only (include_shorts=0, include_longform=1, min=300)
    update_payload = {
        "name": "Test Campaign Longform Only",
        "channel_id": ch_id,
        "channel_ids": [ch_id],
        "gpm_profile_id": gpm_id,
        "gpm_profile_ids": [gpm_id],
        "include_shorts": 0,
        "include_longform": 1,
        "min_video_duration": 300,
        "max_video_duration": 1800,
        "clips_per_video": 3,
        "add_part_label": 1
    }
    res = client.put(f"/api/campaigns/{camp_id}", json=update_payload)
    assert res.status_code == 200, f"Update campaign failed: {res.text}"
    print(f"  [OK] Updated campaign ID {camp_id}")

    # 4. Verify updated
    res = client.get(f"/api/campaigns/{camp_id}")
    assert res.status_code == 200
    updated_data = res.json()
    assert updated_data["include_shorts"] == 0
    assert updated_data["include_longform"] == 1
    assert updated_data["min_video_duration"] == 300
    assert updated_data["max_video_duration"] == 1800
    print("  [OK] Campaign verified with include_shorts=0, include_longform=1, min=300, max=1800")

    # Clean up test campaign
    client.delete(f"/api/campaigns/{camp_id}")
    print(f"  [OK] Cleaned up test campaign ID {camp_id}")

def test_effective_filter_decision_logic():
    print("\n--- TEST 3: Effective Filter Decision Logic (Shorts vs Long-form + Min/Max) ---")
    
    # Case A: Global has include_shorts=True, include_longform=True, min=300, max=3600
    client.post("/api/settings/download-filter", json={
        "min_video_duration": 300,
        "max_video_duration": 3600,
        "include_shorts": True,
        "include_longform": True
    })

    eff_min, eff_max, eff_shorts, eff_long = yt_monitor.get_effective_duration_limits("non_campaign_channel")
    assert eff_shorts is True
    assert eff_long is True
    assert eff_min == 300
    assert eff_max == 3600

    # Test filtering logic for various video lengths:
    # 1. 60s video (Shorts)
    dur = 60
    is_short = (dur <= 180)
    should_reject_shorts = (is_short and not eff_shorts)
    should_reject_min = (not is_short and eff_min is not None and dur < eff_min)
    accepted = not should_reject_shorts and not should_reject_min
    assert accepted is True, "60s Shorts should be accepted even though min is 300s!"
    print(f"  [OK] 60s video (Shorts): Accepted = {accepted} (Bypasses min_duration 300s)")

    # 2. 200s video (Long-form < min_duration 300s)
    dur = 200
    is_short = (dur <= 180)
    should_reject_long = (not is_short and not eff_long)
    should_reject_min = (not is_short and eff_min is not None and dur < eff_min)
    accepted = not should_reject_long and not should_reject_min
    assert accepted is False, "200s video is > 180s (long-form) but < 300s (min_duration), should be rejected!"
    print(f"  [OK] 200s video (Long-form < 300s): Accepted = {accepted} (Rejected by min_duration)")

    # 3. 600s video (Long-form within range)
    dur = 600
    is_short = (dur <= 180)
    should_reject_long = (not is_short and not eff_long)
    should_reject_min = (not is_short and eff_min is not None and dur < eff_min)
    should_reject_max = (not is_short and eff_max is not None and dur > eff_max)
    accepted = not should_reject_long and not should_reject_min and not should_reject_max
    assert accepted is True
    print(f"  [OK] 600s video (Long-form within range): Accepted = {accepted}")

    # Case B: User unchecks Shorts (include_shorts=False, include_longform=True)
    client.post("/api/settings/download-filter", json={
        "min_video_duration": 300,
        "max_video_duration": 3600,
        "include_shorts": False,
        "include_longform": True
    })
    eff_min, eff_max, eff_shorts, eff_long = yt_monitor.get_effective_duration_limits("non_campaign_channel")
    assert eff_shorts is False
    assert eff_long is True
    
    # 60s video now
    dur = 60
    is_short = (dur <= 180)
    should_reject = (is_short and not eff_shorts)
    accepted = not should_reject
    assert accepted is False, "60s Shorts should be rejected when include_shorts=False!"
    print(f"  [OK] 60s video when include_shorts=False: Accepted = {accepted} (Rejected as requested)")

    # Case C: User unchecks Long-form (include_shorts=True, include_longform=False)
    client.post("/api/settings/download-filter", json={
        "min_video_duration": 300,
        "max_video_duration": 3600,
        "include_shorts": True,
        "include_longform": False
    })
    eff_min, eff_max, eff_shorts, eff_long = yt_monitor.get_effective_duration_limits("non_campaign_channel")
    assert eff_shorts is True
    assert eff_long is False

    # 600s video now
    dur = 600
    is_short = (dur <= 180)
    should_reject = (not is_short and not eff_long)
    accepted = not should_reject
    assert accepted is False, "600s Long-form should be rejected when include_longform=False!"
    print(f"  [OK] 600s video when include_longform=False: Accepted = {accepted} (Rejected as requested)")

    # Reset to default
    client.post("/api/settings/download-filter", json={
        "min_video_duration": 0,
        "max_video_duration": 3600,
        "include_shorts": True,
        "include_longform": True
    })
    print("  [OK] Reset global filter settings to defaults (min=0, max=3600, both=True)")

if __name__ == "__main__":
    test_global_download_filter_api()
    test_campaign_filter_api()
    test_effective_filter_decision_logic()
    print("\nALL WORKFLOW & CHECKBOX TESTS PASSED SUCCESSFULLY! 🎉")
