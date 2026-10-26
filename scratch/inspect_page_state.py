import sys
import os
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

with sync_playwright() as p:
    # Connect to the running GPM browser
    # Let's find the port or query GPM
    from backend.modules.gpm_client import gpm_client
    # Let's see active profiles
    remote_address = gpm_client.start_profile("30dabc91-9f51-49e9-9b6b-007d4c086b3b")
    print("Remote address:", remote_address)
    browser = p.chromium.connect_over_cdp(f"http://{remote_address}")
    context = browser.contexts[0]
    for i, page in enumerate(context.pages):
        print(f"Page {i}: {page.url}")
        if "tiktok.com" in page.url or "upload" in page.url:
            ss_path = "data/screenshots/current_upload_state.png"
            os.makedirs("data/screenshots", exist_ok=True)
            page.screenshot(path=ss_path)
            print(f"Saved screenshot to {ss_path}")
            
            # Print all buttons on page
            buttons = page.locator("button").all()
            print(f"Total buttons: {len(buttons)}")
            for b in buttons:
                try:
                    txt = b.inner_text().strip()
                    if txt:
                        cls = b.get_attribute("class") or ""
                        e2e = b.get_attribute("data-e2e") or ""
                        print(f"  Button: '{txt}' | data-e2e: '{e2e}' | class: '{cls[:40]}'")
                except Exception:
                    pass
            
            # Check frames
            print(f"Frames: {len(page.frames)}")
            for f in page.frames:
                print(f"  Frame: {f.url}")
                fb = f.locator("button").all()
                for b in fb:
                    try:
                        txt = b.inner_text().strip()
                        if txt:
                            print(f"    Frame Button: '{txt}' | data-e2e: '{b.get_attribute('data-e2e')}'")
                    except Exception:
                        pass
