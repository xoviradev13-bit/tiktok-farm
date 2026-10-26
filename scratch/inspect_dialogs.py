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
    
    # Get all text from body
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    print("=== PAGE INNER TEXT ===")
    print(text)
    
    # Check console logs or errors
    # Let's inspect all elements with class containing 'toast', 'error', 'alert', 'modal'
    dialogs = page.evaluate("""() => {
        const els = document.querySelectorAll('[role="dialog"], [role="alert"], .toast, .modal, .TUXModal');
        return Array.from(els).map(e => ({ tag: e.tagName, text: e.innerText, class: e.className }));
    }""")
    print("=== DIALOGS / ALERTS ===")
    print(dialogs)
