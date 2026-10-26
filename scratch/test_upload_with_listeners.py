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
    
    # Listen to console messages and page errors
    page.on("console", lambda msg: print(f"[CONSOLE {msg.type}] {msg.text}"))
    page.on("pageerror", lambda err: print(f"[PAGE ERROR] {err}"))
    page.on("requestfailed", lambda req: print(f"[REQ FAILED] {req.url}"))
    
    print("Testing page.locator('input[type=\"file\"]').set_input_files...")
    fi = page.locator('input[type="file"]').first
    fi.set_input_files(ASCII_VIDEO)
    
    time.sleep(5)
    
    st = page.evaluate("""() => {
        const inp = document.querySelector('input[type="file"]');
        return inp ? { filesLen: inp.files.length, val: inp.value } : 'no inp';
    }""")
    print("Input state:", st)
