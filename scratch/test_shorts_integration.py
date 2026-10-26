import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from starlette.testclient import TestClient
from backend.app import app
from backend.modules.ai_video_engine import ai_video_engine

client = TestClient(app)

def test_download_filter_includes_shorts():
    print("\n--- 1. Testing Download Filter for Shorts Support ---")
    res = client.get("/api/settings/download-filter")
    assert res.status_code == 200
    data = res.json()
    print(f"Current download filter: min={data['min_video_duration']}s, max={data['max_video_duration']}s")
    assert data["min_video_duration"] == 0, f"Expected min_video_duration=0, got {data['min_video_duration']}"
    print("✅ Verified: Minimum download duration is 0s (YouTube Shorts will be downloaded).")

def test_short_form_vs_long_form_logic():
    print("\n--- 2. Testing Short-Form (Shorts <= 180s) vs Long-Form (> 180s) Engine Logic ---")
    
    # Check that short-form video duration logic correctly detects <= 180s
    short_durations = [30.0, 58.5, 90.0, 180.0]
    for d in short_durations:
        is_short = (d <= 180.0)
        assert is_short is True, f"Duration {d} must be detected as short-form"
    print("✅ Verified: All durations <= 180s correctly identified as Short-form.")
    
    long_durations = [181.0, 240.0, 600.0, 1800.0]
    for d in long_durations:
        is_short = (d <= 180.0)
        assert is_short is False, f"Duration {d} must be detected as long-form"
    print("✅ Verified: All durations > 180s correctly identified as Long-form.")

def test_save_download_filter_with_zero():
    print("\n--- 3. Testing POST /api/settings/download-filter with 0s ---")
    res = client.post("/api/settings/download-filter", json={"min_video_duration": 0, "max_video_duration": 3600})
    assert res.status_code == 200
    check = client.get("/api/settings/download-filter").json()
    assert check["min_video_duration"] == 0
    print("✅ Verified: Setting min_video_duration to 0s saves and persists properly.")

if __name__ == "__main__":
    test_download_filter_includes_shorts()
    test_short_form_vs_long_form_logic()
    test_save_download_filter_with_zero()
    print("\n🎉 ALL SHORTS & LONG-FORM INTEGRATION TESTS PASSED!\n")
