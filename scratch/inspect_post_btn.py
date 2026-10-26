import sys
import os
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client
from backend.modules.tiktok_uploader import dismiss_tiktok_modals

remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    # Dismiss modals first
    print("Dismissing modals...")
    for _ in range(5):
        dismiss_tiktok_modals(page)
    
    # Screenshot after dismissing
    page.screenshot(path="data/screenshots/after_dismiss_modals.png")
    print("Saved after_dismiss_modals.png")
    
    # Find all buttons with text 'Đăng' or 'Post'
    post_btns = page.locator('button:has-text("Đăng"), button:has-text("Post")').all()
    print(f"Total post buttons: {len(post_btns)}")
    for i, btn in enumerate(post_btns):
        try:
            print(f"  Btn #{i}: text='{btn.inner_text().strip()}', class='{btn.get_attribute('class')}', data-e2e='{btn.get_attribute('data-e2e')}', visible={btn.is_visible()}")
        except Exception as e:
            print(f"  Btn #{i} err:", e)
            
    # Also inspect caption input
    caption_divs = page.locator('div[contenteditable="true"]').all()
    print(f"Total contenteditable divs: {len(caption_divs)}")
    for i, div in enumerate(caption_divs):
        try:
            print(f"  Div #{i}: class='{div.get_attribute('class')}', visible={div.is_visible()}, text='{div.inner_text().strip()[:50]}'")
        except Exception as e:
            print(f"  Div #{i} err:", e)
