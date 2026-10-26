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
    
    cdp = page.context.new_cdp_session(page)
    # Get document
    doc = cdp.send("DOM.getDocument")
    root_id = doc["root"]["nodeId"]
    # Query selector for input[type="file"]
    node = cdp.send("DOM.querySelector", {"nodeId": root_id, "selector": 'input[type="file"]'})
    print("CDP querySelector node:", node)
    node_id = node.get("nodeId")
    if node_id:
        print(f"Setting file input via CDP DOM.setFileInputFiles on nodeId {node_id}...")
        cdp.send("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [ASCII_VIDEO]
        })
        print("CDP DOM.setFileInputFiles sent!")
        
        # Now trigger change and input events via JS
        page.evaluate("""() => {
            const inp = document.querySelector('input[type="file"]');
            if (inp) {
                inp.dispatchEvent(new Event('input', { bubbles: true }));
                inp.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }""")
        
        print("Checking files length after 3s...")
        time.sleep(3)
        st = page.evaluate("""() => {
            const inp = document.querySelector('input[type="file"]');
            return {
                filesLength: inp ? inp.files.length : -1,
                fileName: inp && inp.files[0] ? inp.files[0].name : null,
                fileSize: inp && inp.files[0] ? inp.files[0].size : null
            };
        }""")
        print("Input file state after CDP:", st)
        
        time.sleep(5)
        page.screenshot(path="data/screenshots/after_cdp_set.png")
        print("Screenshot saved to data/screenshots/after_cdp_set.png")
