import sys
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/tiktok_tool.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT id, video_id, gpm_profile_id, video_path, status FROM upload_tasks")
for r in c.fetchall():
    print(dict(r))
