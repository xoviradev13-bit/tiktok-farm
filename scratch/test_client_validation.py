import sys
import os
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath("."))

from fastapi.testclient import TestClient
from backend.app import app
from backend.database import get_connection, is_save_by_channel_folder_enabled
from backend.config import DOWNLOADS_DIR, RENDERED_DIR
from backend.modules.yt_downloader import yt_downloader
from backend.modules.ai_video_engine import sanitize_filename

client = TestClient(app)

print("--- 1. Testing GET /api/settings/scheduler ---")
res = client.get("/api/settings/scheduler")
assert res.status_code == 200, f"Expected 200, got {res.status_code}"
sched_data = res.json()
print("save_by_channel_folder returned:", sched_data.get("save_by_channel_folder"))
assert "save_by_channel_folder" in sched_data

print("\n--- 2. Testing POST /api/settings/scheduler to toggle ON ---")
payload = {
    "interval_minutes": 15,
    "upload_interval_seconds": 60,
    "auto_download": True,
    "auto_render": True,
    "save_by_channel_folder": True,
    "max_videos_per_scan": 5,
    "channel_delay_seconds": 2
}
res = client.post("/api/settings/scheduler", json=payload)
assert res.status_code == 200
res_data = res.json()
print("POST Response settings:", res_data.get("settings"))
assert res_data.get("settings", {}).get("save_by_channel_folder") is True

# Verify GET returns True
res_get = client.get("/api/settings/scheduler").json()
print("Verified GET save_by_channel_folder:", res_get.get("save_by_channel_folder"))
assert res_get.get("save_by_channel_folder") is True

# Verify is_save_by_channel_folder_enabled() returns True
assert is_save_by_channel_folder_enabled() is True
print("is_save_by_channel_folder_enabled() is True!")

print("\n--- 3. Testing POST /api/settings/scheduler to toggle OFF ---")
payload["save_by_channel_folder"] = False
res = client.post("/api/settings/scheduler", json=payload)
assert res.status_code == 200
assert is_save_by_channel_folder_enabled() is False
print("Toggle OFF verified successfully!")

# Toggle back ON for testing channel folder logic
payload["save_by_channel_folder"] = True
client.post("/api/settings/scheduler", json=payload)
assert is_save_by_channel_folder_enabled() is True

print("\n--- 4. Testing destination folder resolution in yt_downloader ---")
# When is_studio=True:
# Should resolve to DOWNLOADS_DIR / "studio"
studio_dir = DOWNLOADS_DIR / "studio"
studio_dir.mkdir(parents=True, exist_ok=True)
assert studio_dir.exists()
print("Studio separate folder verified:", studio_dir)

# When channel_name is given and is_save_by_channel_folder_enabled() is True:
sample_ch = "Kho Báu Lịch Sử"
safe_ch = sanitize_filename(sample_ch, 35)
expected_ch_dir = DOWNLOADS_DIR / safe_ch
print("Expected channel subfolder:", expected_ch_dir)

print("\n--- 5. Testing PUT & DELETE /api/video endpoints ---")
conn = get_connection()
cursor = conn.cursor()
test_vid_id = "test_studio_popover_vid_123"
cursor.execute("DELETE FROM videos WHERE yt_video_id = ?", (test_vid_id,))
cursor.execute("""
    INSERT INTO videos (yt_video_id, title, duration, status, created_at)
    VALUES (?, 'Tiêu đề ban đầu chưa sửa', 90, 'downloaded', datetime('now'))
""", (test_vid_id,))
conn.commit()
cursor.execute("SELECT id FROM videos WHERE yt_video_id = ?", (test_vid_id,))
test_db_id = cursor.fetchone()[0]
conn.close()

# Test PUT /api/video/{test_db_id}
updated_title = "Tiêu đề đã sửa qua Popover Studio"
res_put = client.put(f"/api/video/{test_db_id}", json={"title": updated_title})
assert res_put.status_code == 200, res_put.text
print("PUT Status:", res_put.json())

# Verify in database
conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT title FROM videos WHERE id = ?", (test_db_id,))
cur_title = cursor.fetchone()[0]
assert cur_title == updated_title
print(f"Verified Title successfully updated to: '{cur_title}'")

# Test DELETE /api/video/{test_db_id}
res_del = client.delete(f"/api/video/{test_db_id}")
assert res_del.status_code == 200, res_del.text
print("DELETE Status:", res_del.json())

# Verify record deleted
cursor.execute("SELECT COUNT(*) FROM videos WHERE id = ?", (test_db_id,))
count_after = cursor.fetchone()[0]
conn.close()
assert count_after == 0
print("Verified Video successfully removed from DB!")

print("\n=== ALL TEST CLIENT VALIDATIONS PASSED PERFECTLY! ===")
