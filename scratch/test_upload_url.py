import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client

remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    url = "https://www.tiktok.com/upload?lang=vi-VN"
    print("Navigating to:", url)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    time.sleep(5)
    print("Final URL:", page.url)
    page.screenshot(path="data/screenshots/tiktok_upload_page.png")
    print("Screenshot saved to data/screenshots/tiktok_upload_page.png")
    
    # Inspect inputs
    inputs = page.locator("input[type='file']").all()
    print("File inputs found:", len(inputs))
    for f in page.frames:
        finps = f.locator("input[type='file']").all()
        if finps:
            print(f"  Frame {f.url}: {len(finps)} file inputs")
