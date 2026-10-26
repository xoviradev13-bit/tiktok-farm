import sys
import sqlite3
import os
import json
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

base = Path('data')
print('=== DOWNLOADS DIR ===')
for root, dirs, files in os.walk(base / 'downloads'):
    print(f"Dir: {root}")
    for f in files:
        print(f"  File: {f}")

print('\n=== RENDERED DIR ===')
for root, dirs, files in os.walk(base / 'rendered'):
    print(f"Dir: {root}")
    for f in files:
        print(f"  File: {f}")

print('\n=== CHANNELS TABLE SCHEMA ===')
conn = sqlite3.connect('data/tiktok_tool.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute('PRAGMA table_info(channels)')
for col in c.fetchall():
    print(dict(col))

print('\n=== CHANNELS IN DB ===')
c.execute('SELECT * FROM channels')
for r in c.fetchall():
    print(dict(r))

print('\n=== VIDEOS TABLE SCHEMA ===')
c.execute('PRAGMA table_info(videos)')
for col in c.fetchall():
    print(dict(col))

print('\n=== DB VIDEOS ===')
c.execute('SELECT * FROM videos')
for r in c.fetchall():
    d = dict(r)
    print(f"ID={d.get('id')} | yt_id={d.get('yt_video_id')} | ch_id={d.get('channel_id')} | title={d.get('title')}")
    print(f"   download_path: {d.get('download_path')}")
    print(f"   rendered_path: {d.get('rendered_path')}")
    print(f"   status: {d.get('status')}")


