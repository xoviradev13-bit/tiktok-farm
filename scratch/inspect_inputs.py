import sys
import os
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client

remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    print("Page URL:", page.url)
    inputs = page.locator("input").all()
    print("Total inputs:", len(inputs))
    for i, inp in enumerate(inputs):
        try:
            itype = inp.get_attribute("type")
            iaccept = inp.get_attribute("accept")
            iclass = inp.get_attribute("class")
            print(f"  Input #{i}: type={itype}, accept={iaccept}, class={iclass}")
        except Exception as e:
            print(f"  Input #{i} err:", e)

    # Check iframes
    for f in page.frames:
        print(f"Frame URL: {f.url}")
        finps = f.locator("input").all()
        for i, inp in enumerate(finps):
            try:
                print(f"  Frame input #{i}: type={inp.get_attribute('type')}, accept={inp.get_attribute('accept')}")
            except Exception:
                pass
