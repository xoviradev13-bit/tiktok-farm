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
    
    res = page.evaluate("""() => {
        const btn = document.querySelector('button[data-e2e="select_video_button"]');
        const inp = document.querySelector('input[type="file"]');
        const container = document.querySelector('div[data-e2e="select_video_container"]');
        return {
            btnExists: !!btn,
            inpExists: !!inp,
            inpAccept: inp ? inp.accept : null,
            containerExists: !!container,
            containerRole: container ? container.getAttribute('role') : null,
            parentRole: inp && inp.parentElement ? inp.parentElement.getAttribute('role') : null
        };
    }""")
    print("DOM info:", res)
