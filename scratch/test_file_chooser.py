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
    
    print("Testing file chooser on button[data-e2e='select_video_button']...")
    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            page.locator('button[data-e2e="select_video_button"]').click()
        file_chooser = fc_info.value
        print("File chooser intercepted successfully! Setting files...")
        file_chooser.set_files(TEST_VIDEO)
        print("File chooser set_files done!")
    except Exception as e:
        print("expect_file_chooser failed:", e)
        # Fallback: test set_input_files directly with dispatchEvent
        print("Trying set_input_files with dispatchEvent...")
        fi = page.locator('input[type="file"]').first
        fi.set_input_files(TEST_VIDEO)
        page.evaluate("""() => {
            const fi = document.querySelector('input[type="file"]');
            if (fi) {
                fi.dispatchEvent(new Event('change', { bubbles: true }));
                fi.dispatchEvent(new Event('input', { bubbles: true }));
            }
        }""")

    print("Waiting 10s...")
    time.sleep(10)
    page.screenshot(path="data/screenshots/after_file_chooser.png")
    print("Screenshot saved to data/screenshots/after_file_chooser.png")
    
    buttons = [b.inner_text().strip() for b in page.locator("button").all() if b.inner_text().strip()]
    print("Buttons on page:", buttons)
