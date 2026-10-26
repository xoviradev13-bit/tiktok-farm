import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.app import get_channel_videos

res = get_channel_videos("UCnxGkOGNMqQEUMvroOWps6Q")
print(f"Total videos for JRE Clips: {len(res.get('videos', []))}")
for v in res.get('videos', []):
    print(f"  ID={v['id']} | title={v['title'][:35]} | parts={len(v.get('rendered_parts', []))} | dl={bool(v.get('download_path'))}")
