import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_multi_channel_switching_and_bgm_persistence():
    print("\n========================================================")
    print("TEST: Multi-Channel Switching & BGM Dropdown Consistency")
    print("========================================================")
    
    # 1. Fetch all channels
    res = client.get("/api/youtube/channels")
    channels = res.json()
    assert len(channels) >= 2, "Need at least 2 channels to test switching"
    
    ch1 = channels[0] # e.g. Lex Fridman
    ch2 = channels[1] # e.g. StarTalk or Joe Rogan
    
    print(f"Channel 1: {ch1['channel_id']} ({ch1.get('display_name') or ch1.get('title')}) - BGM: '{ch1.get('bgm_folder')}'")
    print(f"Channel 2: {ch2['channel_id']} ({ch2.get('display_name') or ch2.get('title')}) - BGM: '{ch2.get('bgm_folder')}'")
    
    # Set Channel 1 to 'general'
    payload1 = {
        "channel_id": ch1["channel_id"],
        "display_name": ch1.get("display_name") or ch1.get("title") or "Ch 1",
        "custom_proxy": ch1.get("custom_proxy", ""),
        "download_dir": ch1.get("download_dir", ""),
        "render_dir": ch1.get("render_dir", ""),
        "is_active": 1,
        "auto_download": 1,
        "auto_render": 1,
        "bgm_folder": "general",
        "bgm_volume": 0.25
    }
    r1 = client.post("/api/youtube/channels/update", json=payload1)
    assert r1.status_code == 200
    
    # Set Channel 2 to '' (No BGM)
    payload2 = {
        "channel_id": ch2["channel_id"],
        "display_name": ch2.get("display_name") or ch2.get("title") or "Ch 2",
        "custom_proxy": ch2.get("custom_proxy", ""),
        "download_dir": ch2.get("download_dir", ""),
        "render_dir": ch2.get("render_dir", ""),
        "is_active": 1,
        "auto_download": 1,
        "auto_render": 1,
        "bgm_folder": "",
        "bgm_volume": 0.15
    }
    r2 = client.post("/api/youtube/channels/update", json=payload2)
    assert r2.status_code == 200
    
    # Verify Channel 1 detail
    d1 = client.get(f"/api/youtube/channels/{ch1['channel_id']}").json()
    assert d1["bgm_folder"] == "general", f"Channel 1 must have 'general', got {d1['bgm_folder']}"
    assert abs(d1["bgm_volume"] - 0.25) < 0.001
    print("✅ Channel 1 verified in DB: BGM = 'general', volume = 25%")
    
    # Verify Channel 2 detail
    d2 = client.get(f"/api/youtube/channels/{ch2['channel_id']}").json()
    assert d2["bgm_folder"] == "", f"Channel 2 must have '', got {d2['bgm_folder']}"
    assert abs(d2["bgm_volume"] - 0.15) < 0.001
    print("✅ Channel 2 verified in DB: BGM = '' (No BGM), volume = 15%")
    
    # Switch Channel 2 to 'horror_mystery'
    payload2["bgm_folder"] = "horror_mystery"
    payload2["bgm_volume"] = 0.30
    client.post("/api/youtube/channels/update", json=payload2)
    d2_after = client.get(f"/api/youtube/channels/{ch2['channel_id']}").json()
    assert d2_after["bgm_folder"] == "horror_mystery"
    assert abs(d2_after["bgm_volume"] - 0.30) < 0.001
    print("✅ Channel 2 updated to 'horror_mystery': verified in DB")
    
    # Ensure Channel 1 was NOT affected and remains 'general'
    d1_check = client.get(f"/api/youtube/channels/{ch1['channel_id']}").json()
    assert d1_check["bgm_folder"] == "general"
    print("✅ Channel 1 untouched: still 'general'")

    print("\n🎉 ALL TESTS PASSED: Data saves and displays accurately across all channels!\n")

if __name__ == "__main__":
    test_multi_channel_switching_and_bgm_persistence()
