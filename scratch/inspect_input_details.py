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
    
    info = page.evaluate("""() => {
        const inp = document.querySelector('input[type="file"]');
        if (!inp) return "No file input";
        return {
            outerHTML: inp.outerHTML,
            parentClass: inp.parentElement ? inp.parentElement.className : null,
            parentHTML: inp.parentElement ? inp.parentElement.outerHTML.slice(0, 500) : null,
            visible: inp.offsetWidth > 0 && inp.offsetHeight > 0,
            style: inp.getAttribute('style')
        };
    }""")
    print("Input file info:", info)
