import sys
import os
import re
import shutil
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path('c:/Users/datng/tiktok-farm')
DATA_DIR = BASE_DIR / 'data'
DOWNLOADS_DIR = DATA_DIR / 'downloads'
RENDERED_DIR = DATA_DIR / 'rendered'
DB_PATH = DATA_DIR / 'tiktok_tool.db'

print("=== STARTING REORGANIZATION DRY RUN ===")

# Connect to DB to get channel mapping
conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get known channels
cursor.execute("SELECT channel_id, title, display_name FROM channels")
channels = {}
for ch in cursor.fetchall():
    ch_id = ch["channel_id"]
    name = ch["display_name"] or ch["title"] or ch_id
    channels[ch_id] = name
print(f"Known monitored channels: {channels}")

# Get all videos
cursor.execute("SELECT id, yt_video_id, channel_id, title, download_path, rendered_path FROM videos")
db_videos = [dict(r) for r in cursor.fetchall()]
print(f"Total videos in DB: {len(db_videos)}")

# Map each video to its folder name
def get_folder_for_video(v):
    ch_id = v.get("channel_id")
    if ch_id and ch_id in channels:
        # Sanitize folder name
        raw_name = channels[ch_id]
        clean_name = re.sub(r'[\\/*?:"<>|]', '', raw_name).strip()
        return clean_name or "Direct Links"
    return "Direct Links"

video_target_folder = {}
for v in db_videos:
    folder = get_folder_for_video(v)
    video_target_folder[v["yt_video_id"]] = folder
    print(f"Video {v['yt_video_id']} ('{v['title'][:35]}') -> Folder: '{folder}'")

# Scan downloads
print("\n--- DOWNLOADS TO MOVE ---")
moves_downloads = []
for f in DOWNLOADS_DIR.iterdir():
    if f.is_file():
        # Check if video ID in filename
        vid_m = re.search(r'\[([a-zA-Z0-9_-]{11})\]', f.name)
        vid_id = vid_m.group(1) if vid_m else None
        
        target_folder = "Direct Links"
        if vid_id and vid_id in video_target_folder:
            target_folder = video_target_folder[vid_id]
        elif "[JRE_Clips]" in f.name:
            target_folder = "JRE Clips"
            
        target_path = DOWNLOADS_DIR / target_folder / f.name
        moves_downloads.append((f, target_path))
        print(f"  {f.name} -> {target_folder}/")

# Scan rendered
print("\n--- RENDERED TO MOVE ---")
moves_rendered = []
for f in RENDERED_DIR.iterdir():
    if f.is_file():
        if f.name == "test_tiktok_ceowapp.mp4":
            continue
        vid_m = re.search(r'([a-zA-Z0-9_-]{11})', f.name)
        vid_id = vid_m.group(1) if vid_m else None
        
        target_folder = "Direct Links"
        if vid_id and vid_id in video_target_folder:
            target_folder = video_target_folder[vid_id]
        elif "[JRE_Clips]" in f.name:
            target_folder = "JRE Clips"
            
        target_path = RENDERED_DIR / target_folder / f.name
        moves_rendered.append((f, target_path))
        print(f"  {f.name} -> {target_folder}/")

print("\n=== EXECUTING REORGANIZATION ===")

# Create destination folders
for folder in ["JRE Clips", "Direct Links"]:
    (DOWNLOADS_DIR / folder).mkdir(parents=True, exist_ok=True)
    (RENDERED_DIR / folder).mkdir(parents=True, exist_ok=True)

# 1. Move downloads
path_replacements = {}
for src, dst in moves_downloads:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"Moving download: {src.name} -> {dst}")
    shutil.move(str(src), str(dst))
    path_replacements[str(src)] = str(dst)
    # Also track with Windows backslashes and relative paths
    path_replacements[str(src).replace('/', '\\')] = str(dst).replace('/', '\\')
    path_replacements[f"data\\downloads\\{src.name}"] = f"data\\downloads\\{dst.parent.name}\\{dst.name}"
    path_replacements[f"data/downloads/{src.name}"] = f"data/downloads/{dst.parent.name}/{dst.name}"

# 2. Move rendered
for src, dst in moves_rendered:
    dst.parent.mkdir(parents=True, exist_ok=True)
    print(f"Moving rendered: {src.name} -> {dst}")
    shutil.move(str(src), str(dst))
    path_replacements[str(src)] = str(dst)
    path_replacements[str(src).replace('/', '\\')] = str(dst).replace('/', '\\')
    path_replacements[f"data\\rendered\\{src.name}"] = f"data\\rendered\\{dst.parent.name}\\{dst.name}"
    path_replacements[f"data/rendered/{src.name}"] = f"data/rendered/{dst.parent.name}/{dst.name}"

# 3. Clean up empty downloads/studio if empty
studio_dir = DOWNLOADS_DIR / "studio"
if studio_dir.exists() and not any(studio_dir.iterdir()):
    try:
        studio_dir.rmdir()
        print("Removed empty data/downloads/studio directory")
    except Exception:
        pass

# 4. Update Database
print("\n--- UPDATING DATABASE PATHS ---")

# Update videos table
cursor.execute("SELECT id, download_path, rendered_path FROM videos")
for row in cursor.fetchall():
    v_id = row["id"]
    old_dl = row["download_path"]
    old_ren = row["rendered_path"]
    
    new_dl = old_dl
    new_ren = old_ren
    
    if old_dl:
        for k, v in path_replacements.items():
            if k.lower() == old_dl.lower() or Path(old_dl).name.lower() == Path(k).name.lower():
                new_dl = v
                break
                
    if old_ren:
        for k, v in path_replacements.items():
            if k.lower() == old_ren.lower() or Path(old_ren).name.lower() == Path(k).name.lower():
                new_ren = v
                break
                
    if new_dl != old_dl or new_ren != old_ren:
        cursor.execute("UPDATE videos SET download_path = ?, rendered_path = ? WHERE id = ?", (new_dl, new_ren, v_id))
        print(f"Updated video ID {v_id}:")
        if new_dl != old_dl:
            print(f"   download_path: {old_dl} -> {new_dl}")
        if new_ren != old_ren:
            print(f"   rendered_path: {old_ren} -> {new_ren}")

# Update upload_tasks table
cursor.execute("SELECT id, video_path FROM upload_tasks")
for row in cursor.fetchall():
    t_id = row["id"]
    old_vp = row["video_path"]
    if old_vp:
        new_vp = old_vp
        for k, v in path_replacements.items():
            if k.lower() == old_vp.lower() or Path(old_vp).name.lower() == Path(k).name.lower():
                new_vp = v
                break
        if new_vp != old_vp:
            cursor.execute("UPDATE upload_tasks SET video_path = ? WHERE id = ?", (new_vp, t_id))
            print(f"Updated upload_task ID {t_id}: {old_vp} -> {new_vp}")

# Enable save_by_channel_folder in settings
cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('save_by_channel_folder', '1')")
print("Set save_by_channel_folder = 1 in settings")

conn.commit()
conn.close()
print("\n=== REORGANIZATION COMPLETED SUCCESSFULLY! ===")
