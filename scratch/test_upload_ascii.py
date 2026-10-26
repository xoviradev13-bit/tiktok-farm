import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client

ASCII_VIDEO = os.path.abspath(r"data\rendered\test_tiktok_ceowapp.mp4")
remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    print("Setting input files on 'input[type=file]' with:", ASCII_VIDEO)
    page.set_input_files('input[type="file"]', ASCII_VIDEO)
    
    print("Waiting up to 15 seconds for upload stage to change...")
    for i in range(15):
        time.sleep(1)
        # Check if stage changed
        btn_count = page.locator('button[data-e2e="select_video_button"]').count()
        div_editor = page.locator('div[contenteditable="true"]').count()
        print(f"  Sec {i+1}: select_video_btn count = {btn_count}, editor count = {div_editor}")
        if div_editor > 0 or btn_count == 0:
            print("  Stage changed!")
            break

    page.screenshot(path="data/screenshots/after_ascii_upload.png")
    print("Screenshot saved to data/screenshots/after_ascii_upload.png")
