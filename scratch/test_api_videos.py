import sys
import os

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import list_videos

print("Calling list_videos(sync=False)...")
videos = list_videos(sync=False)
print(f"Total videos returned: {len(videos)}")

for v in videos:
    print(f"\nID={v['id']} | title={v['title'][:35]} | channel_name={v.get('channel_name')}")
    print(f"  has_raw={v.get('has_raw')} | download_path={v.get('download_path')}")
    print(f"  has_rendered={v.get('has_rendered')} | rendered_path={v.get('rendered_path')}")
    print(f"  rendered_parts ({len(v.get('rendered_parts', []))} parts):")
    for rp in v.get('rendered_parts', []):
        print(f"     Part {rp['part']}: {rp['filename']} (exists={os.path.exists(rp['path'])})")
