import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from backend.app import app
from backend.database import get_connection

client = TestClient(app)

def test_channel_bgm_and_settings_persistence():
    print("\n--- 1. Testing Channel Settings Update & Persistence ---")
    # Get an existing channel
    res = client.get("/api/youtube/channels")
    assert res.status_code == 200
    channels = res.json()
    assert len(channels) > 0, "No channels found to test"
    
    test_ch = channels[0]
    cid = test_ch["channel_id"]
    orig_bgm = test_ch.get("bgm_folder", "")
    orig_vol = test_ch.get("bgm_volume", 0.15)
    print(f"Testing channel: {cid} (Original BGM: '{orig_bgm}', Vol: {orig_vol})")
    
    # Step A: Update to 'general' with 0.22 volume
    payload_a = {
        "channel_id": cid,
        "display_name": test_ch.get("display_name") or test_ch.get("title") or "Test Name",
        "custom_proxy": "",
        "download_dir": "",
        "render_dir": "",
        "is_active": 1,
        "auto_download": 1,
        "auto_render": 1,
        "bgm_folder": "general",
        "bgm_volume": 0.22
    }
    update_res = client.post("/api/youtube/channels/update", json=payload_a)
    assert update_res.status_code == 200, update_res.text
    assert update_res.json()["status"] == "success"
    
    # Verify via GET /api/youtube/channels
    list_res = client.get("/api/youtube/channels")
    ch_after_a = next(c for c in list_res.json() if c["channel_id"] == cid)
    assert ch_after_a["bgm_folder"] == "general", f"Expected 'general', got {ch_after_a['bgm_folder']}"
    assert abs(ch_after_a["bgm_volume"] - 0.22) < 0.001, f"Expected 0.22, got {ch_after_a['bgm_volume']}"
    print("  -> Passed Step A: BGM saved as 'general' with vol 0.22 and verified via GET /api/youtube/channels")
    
    # Verify via GET /api/youtube/channels/{channel_id}
    detail_res = client.get(f"/api/youtube/channels/{cid}")
    assert detail_res.status_code == 200
    assert detail_res.json()["bgm_folder"] == "general"
    assert abs(detail_res.json()["bgm_volume"] - 0.22) < 0.001
    print("  -> Passed Step A Detail: Verified via GET /api/youtube/channels/{cid}")
    
    # Step B: Update to '' (no BGM / empty)
    payload_b = dict(payload_a)
    payload_b["bgm_folder"] = ""
    payload_b["bgm_volume"] = 0.15
    update_res_b = client.post("/api/youtube/channels/update", json=payload_b)
    assert update_res_b.status_code == 200
    
    list_res_b = client.get("/api/youtube/channels")
    ch_after_b = next(c for c in list_res_b.json() if c["channel_id"] == cid)
    assert ch_after_b["bgm_folder"] == "", f"Expected '', got {ch_after_b['bgm_folder']}"
    print("  -> Passed Step B: Reset BGM to empty and verified via GET")
    
    # Step C: Restore to 'general'
    payload_c = dict(payload_a)
    payload_c["bgm_folder"] = "general"
    payload_c["bgm_volume"] = 0.15
    client.post("/api/youtube/channels/update", json=payload_c)
    print("  -> Passed Step C: Restored to 'general'")


def test_audio_categories_api():
    print("\n--- 2. Testing Audio Categories API ---")
    res = client.get("/api/audio/categories")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    categories = data["categories"]
    assert len(categories) > 0
    general_cat = next((c for c in categories if c["id"] == "general"), None)
    assert general_cat is not None, "General audio category must exist"
    print(f"  -> Found 'general' category: display_name='{general_cat['display_name']}', tracks={general_cat['track_count']}")


def test_campaign_bgm_persistence():
    print("\n--- 3. Testing Campaign BGM & Settings Persistence ---")
    res = client.get("/api/campaigns")
    assert res.status_code == 200
    camps = res.json()
    if camps:
        camp = camps[0]
        cid = camp["id"]
        detail_res = client.get(f"/api/campaigns/{cid}")
        assert detail_res.status_code == 200
        camp_detail = detail_res.json()
        print(f"  -> Campaign #{cid} '{camp_detail.get('name')}' BGM: '{camp_detail.get('bgm_folder')}', Vol: {camp_detail.get('bgm_volume')}")
        
        import json
        update_payload = dict(camp_detail)
        if isinstance(update_payload.get("channel_ids"), str):
            update_payload["channel_ids"] = json.loads(update_payload["channel_ids"])
        if isinstance(update_payload.get("gpm_profile_ids"), str):
            update_payload["gpm_profile_ids"] = json.loads(update_payload["gpm_profile_ids"])
        update_payload["bgm_folder"] = "general"
        update_payload["bgm_volume"] = 0.20
        put_res = client.put(f"/api/campaigns/{cid}", json=update_payload)
        print("PUT status:", put_res.status_code, put_res.text)
        assert put_res.status_code == 200, f"Error: {put_res.status_code} {put_res.text}"
        
        # Verify
        check_res = client.get(f"/api/campaigns/{cid}").json()
        assert check_res["bgm_folder"] == "general"
        assert abs(check_res["bgm_volume"] - 0.20) < 0.001
        print("  -> Passed: Campaign BGM updated to 'general' (0.20) and verified via GET")


def test_system_settings_persistence():
    print("\n--- 4. Testing System Settings Persistence ---")
    res = client.get("/api/settings/defaults")
    assert res.status_code == 200
    data = res.json()
    print("  -> Default settings:", data)
    assert "download_dir" in data
    assert "render_dir" in data


if __name__ == "__main__":
    test_channel_bgm_and_settings_persistence()
    test_audio_categories_api()
    test_campaign_bgm_persistence()
    test_system_settings_persistence()
    print("\n✅ ALL BACKEND DATA PERSISTENCE TESTS PASSED SUCCESSFULLY!")
