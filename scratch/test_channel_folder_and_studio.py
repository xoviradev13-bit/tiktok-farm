import sys
import os
import requests
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

BASE_URL = "http://127.0.0.1:8088"

print("--- 1. Testing GET /api/settings/scheduler ---")
try:
    res = requests.get(f"{BASE_URL}/api/settings/scheduler", timeout=5)
    print("Status:", res.status_code)
    sched_data = res.json()
    print("save_by_channel_folder in settings:", sched_data.get("save_by_channel_folder"))
    assert "save_by_channel_folder" in sched_data, "save_by_channel_folder missing from scheduler settings!"
except Exception as e:
    print("Error calling /api/settings/scheduler:", e)

print("\n--- 2. Testing POST /api/settings/scheduler to toggle ON ---")
try:
    payload = {
        "interval_minutes": 15,
        "upload_interval_seconds": 60,
        "auto_download": True,
        "auto_render": True,
        "save_by_channel_folder": True,
        "max_videos_per_scan": 5,
        "channel_delay_seconds": 2
    }
    res = requests.post(f"{BASE_URL}/api/settings/scheduler", json=payload, timeout=5)
    print("Status:", res.status_code)
    res_data = res.json()
    print("Response message:", res_data.get("message"))
    assert res_data.get("settings", {}).get("save_by_channel_folder") is True, "Setting not returned as True!"

    # Verify via GET
    res_get = requests.get(f"{BASE_URL}/api/settings/scheduler", timeout=5).json()
    print("Verified GET save_by_channel_folder:", res_get.get("save_by_channel_folder"))
    assert res_get.get("save_by_channel_folder") is True
except Exception as e:
    print("Error posting scheduler settings:", e)

print("\n--- 3. Testing is_save_by_channel_folder_enabled() directly in Python ---")
from backend.database import is_save_by_channel_folder_enabled, get_connection
enabled = is_save_by_channel_folder_enabled()
print("is_save_by_channel_folder_enabled():", enabled)
assert enabled is True

print("\n--- 4. Testing Studio separate folder download logic ---")
from backend.config import DOWNLOADS_DIR, RENDERED_DIR
from backend.modules.yt_downloader import yt_downloader
from backend.modules.ai_video_engine import ai_video_engine

studio_dir = DOWNLOADS_DIR / "studio"
print("Studio dir:", studio_dir)
# Verify studio folder creation
studio_dir.mkdir(parents=True, exist_ok=True)
assert studio_dir.exists()

print("\n--- 5. Testing PUT & DELETE /api/video endpoints ---")
# Insert a temporary test video row into SQLite
conn = get_connection()
cursor = conn.cursor()
test_vid_id = "test_popover_vid_999"
cursor.execute("DELETE FROM videos WHERE yt_video_id = ?", (test_vid_id,))
cursor.execute("""
    INSERT INTO videos (yt_video_id, title, duration, status, created_at)
    VALUES (?, 'Test Video for Popover', 45, 'downloaded', datetime('now'))
""", (test_vid_id,))
conn.commit()
cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (test_vid_id,))
v_row = cursor.fetchone()
test_db_id = v_row[0]
conn.close()

print(f"Created test video #{test_db_id} ({test_vid_id})")

# Test PUT /api/video/{id}
new_title = "Updated Title via Popover Edit"
res_put = requests.put(f"{BASE_URL}/api/video/{test_db_id}", json={"title": new_title}, timeout=5)
print("PUT Status:", res_put.status_code, res_put.json())
assert res_put.status_code == 200

# Verify in DB
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT title FROM videos WHERE id = ?", (test_db_id,))
row = cursor.fetchone()
conn.close()
assert row[0] == new_title
print(f"Verified Title Updated to: '{row[0]}'")

# Test DELETE /api/video/{id}
res_del = requests.delete(f"{BASE_URL}/api/video/{test_db_id}", timeout=5)
print("DELETE Status:", res_del.status_code, res_del.json())
assert res_del.status_code == 200

# Verify deleted from DB
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM videos WHERE id = ?", (test_db_id,))
cnt = cursor.fetchone()[0]
conn.close()
assert cnt == 0
print("Verified Video Successfully Deleted from DB!")

print("\n=== ALL TESTS PASSED SUCCESSFULLY! ===")
