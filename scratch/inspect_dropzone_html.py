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
    
    html = page.evaluate("""() => {
        const btn = document.querySelector('button[data-e2e="select_video_button"]');
        if (!btn) return "Button not found";
        let parent = btn;
        for (let i = 0; i < 4; i++) {
            if (parent.parentElement) parent = parent.parentElement;
        }
        return parent.outerHTML;
    }""")
    print("Dropzone HTML snippet:")
    print(html[:2000])
