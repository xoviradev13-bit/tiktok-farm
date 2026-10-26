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
    cdp = page.context.new_cdp_session(page)
    
    # Evaluate JS to get references and test click
    res = page.evaluate("""() => {
        const inp = document.querySelector('input[type="file"]');
        const btn = document.querySelector('button[data-e2e="select_video_button"]');
        const roleBtn = document.querySelector('div[role="button"]');
        
        // Track whether click on btn triggers inp.click
        let inpClickTriggered = false;
        const origClick = inp.click;
        inp.click = function() {
            inpClickTriggered = true;
            return origClick.apply(this, arguments);
        };
        
        btn.click();
        inp.click = origClick;
        return { inpClickTriggered };
    }""")
    print("Test click result:", res)
