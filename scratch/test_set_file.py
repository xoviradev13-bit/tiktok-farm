import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client

TEST_VIDEO = os.path.abspath(r"data\rendered\Sự_Thật_Gây_Sốc_Về_Điều_j41_hP1dbNA_Part1.mp4")
remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    print("Setting input files with:", TEST_VIDEO)
    fi = page.locator('input[type="file"]').first
    fi.set_input_files(TEST_VIDEO)
    print("File set. Waiting 10 seconds for TikTok Studio to react...")
    time.sleep(10)
    
    page.screenshot(path="data/screenshots/after_file_set.png")
    print("Saved screenshot to data/screenshots/after_file_set.png")
    
    print("Checking buttons on page now:")
    for b in page.locator("button").all():
        try:
            txt = b.inner_text().strip()
            if txt:
                print(f"  Button: '{txt}' | e2e: '{b.get_attribute('data-e2e')}' | class: '{b.get_attribute('class')[:35]}'")
        except Exception:
            pass

    print("Checking inputs / editors:")
    for div in page.locator('div[contenteditable="true"]').all():
        print("  Contenteditable div found!")
