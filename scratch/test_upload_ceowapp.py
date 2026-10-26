import sys
import os
import time

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client
from backend.modules.tiktok_uploader import tiktok_uploader
from backend.database import get_connection

GPM_PROFILE_ID = "30dabc91-9f51-49e9-9b6b-007d4c086b3b"
TEST_VIDEO = os.path.abspath(r"data\rendered\Sự_Thật_Gây_Sốc_Về_Điều_j41_hP1dbNA_Part1.mp4")

print(f"=== TEST UPLOAD TO TIKTOK FOR CEOWAPP ===")
print(f"GPM Profile ID: {GPM_PROFILE_ID}")
print(f"Video Path: {TEST_VIDEO} (Exists: {os.path.exists(TEST_VIDEO)})")

# 1. Health check GPMLogin
health = gpm_client.check_health()
print(f"1. GPM Health: {health}")
if not health.get("running"):
    print("GPMLogin not running, attempting to start...")
    gpm_client.ensure_gpm_running()

# 2. Test upload
print("\n2. Executing tiktok_uploader.upload_via_gpm...")
start_t = time.time()
res = tiktok_uploader.upload_via_gpm(
    gpm_profile_id=GPM_PROFILE_ID,
    video_path=TEST_VIDEO,
    title="Test Upload Ceowapp Auto TikTok",
    tags="#viral #fyp #test",
    auto_post=True,
    close_browser_on_finish=False
)
elapsed = time.time() - start_t
print(f"\n3. Result after {elapsed:.1f}s:")
print(res)

# 4. Check DB status for this profile
conn = get_connection()
c = conn.cursor()
c.execute("SELECT id, name, tiktok_username, followers_count, status, status_reason, last_checked FROM gpm_profiles WHERE gpm_id = ?", (GPM_PROFILE_ID,))
row = dict(c.fetchone() or {})
conn.close()
print(f"\n4. Profile state in DB:")
print(row)
