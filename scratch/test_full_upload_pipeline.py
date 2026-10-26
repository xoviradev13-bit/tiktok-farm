import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.tiktok_uploader import tiktok_uploader
from backend.database import get_connection

GPM_PROFILE_ID = "30dabc91-9f51-49e9-9b6b-007d4c086b3b"
TEST_VIDEO = os.path.abspath(r"data\rendered\test_tiktok_ceowapp.mp4")

print(f"=== FULL PIPELINE TEST: TIKTOK UPLOAD FOR CEOWAPP ===")
print(f"Profile: {GPM_PROFILE_ID} (ceowapp)")
print(f"Video: {TEST_VIDEO} (Exists: {os.path.exists(TEST_VIDEO)})")

# Execute upload_via_gpm
result = tiktok_uploader.upload_via_gpm(
    gpm_profile_id=GPM_PROFILE_ID,
    video_path=TEST_VIDEO,
    title="Thử Nghiệm Tự Động Đăng Video TikTok",
    tags="#viral #trending #test",
    auto_post=True,
    close_browser_on_finish=False
)

print("\n=== PIPELINE RESULT ===")
print(result)

# Verify profile status in DB
conn = get_connection()
c = conn.cursor()
c.execute("SELECT id, name, tiktok_username, followers_count, status, status_reason FROM gpm_profiles WHERE gpm_id = ?", (GPM_PROFILE_ID,))
row = dict(c.fetchone() or {})
conn.close()
print("\n=== DB PROFILE ROW ===")
print(row)
