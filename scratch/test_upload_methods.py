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

    # Test 1: FileChooser with ASCII path
    print("--- TEST 1: FileChooser with ASCII path ---")
    try:
        with page.expect_file_chooser(timeout=4000) as fc_info:
            page.locator('button[data-e2e="select_video_button"]').click()
        fc = fc_info.value
        fc.set_files(ASCII_VIDEO)
        print("FileChooser set_files done!")
    except Exception as e:
        print("FileChooser error:", e)

    time.sleep(5)
    page.screenshot(path="data/screenshots/test1_fc.png")
    
    # Check if stage changed
    if page.locator('div[contenteditable="true"]').count() > 0 or page.locator('button[data-e2e="select_video_button"]').count() == 0:
        print("Test 1 SUCCESS: Stage changed!")
    else:
        print("Test 1 DID NOT CHANGE STAGE.")
        
        # Test 2: Drag and drop via DataTransfer JS
        print("--- TEST 2: Drag & drop simulation via CDP / JS ---")
        # In Playwright, we can use set_input_files on the input element AND trigger change via React setter
        res = page.evaluate("""() => {
            const input = document.querySelector('input[type="file"]');
            if (!input) return "No input found";
            // Check properties
            return {
                id: input.id,
                name: input.name,
                accept: input.accept,
                filesLength: input.files ? input.files.length : 0
            };
        }""")
        print("Input state:", res)
