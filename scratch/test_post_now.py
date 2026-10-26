import sys
import os
import time
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from backend.modules.gpm_client import gpm_client
from backend.modules.tiktok_uploader import dismiss_tiktok_modals

remote = gpm_client.start_profile('30dabc91-9f51-49e9-9b6b-007d4c086b3b')
with sync_playwright() as p:
    b = p.chromium.connect_over_cdp(f'http://{remote}')
    page = b.contexts[0].pages[0]
    
    # 1. Dismiss modals
    for _ in range(3):
        dismiss_tiktok_modals(page)
        time.sleep(1)

    # 2. Type caption
    title = "Sự Thật Gây Sốc #Shorts #Viral #Trending #KhamPha"
    print(f"Typing caption: {title}")
    
    editor = page.locator('div[contenteditable="true"]').first
    editor.scroll_into_view_if_needed()
    editor.click()
    page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(title, delay=35)
    time.sleep(2)
    dismiss_tiktok_modals(page)
    
    # 3. Click Post button
    post_btn = page.locator('button[data-e2e="post_video_button"]').first
    if not post_btn.is_visible():
        post_btn = page.locator('button.Button__root--type-primary:has-text("Đăng"), button:text-is("Đăng")').first

    print("Post button visible:", post_btn.is_visible())
    print("Clicking post button...")
    post_btn.scroll_into_view_if_needed()
    try:
        post_btn.evaluate("el => el.click()")
    except Exception:
        post_btn.click()

    print("Post clicked. Waiting 8s...")
    time.sleep(8)
    
    page.screenshot(path="data/screenshots/after_post_clicked.png")
    print("Saved screenshot to data/screenshots/after_post_clicked.png")
    print("Current URL:", page.url)
    
    # Check text on page
    body_text = page.evaluate("() => document.body ? document.body.innerText.slice(0, 1000) : ''")
    print("Body text snippet:")
    print(body_text)
