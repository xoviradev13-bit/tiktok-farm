import sys
import sqlite3

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('data/tiktok_tool.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute('''
    SELECT v.id, v.yt_video_id, v.channel_id, v.title, v.download_path, v.rendered_path,
           c.title as ch_title, c.display_name as ch_disp,
           COALESCE(c.display_name, c.title, 'Dán trực tiếp') as resolved_channel_name
    FROM videos v
    LEFT JOIN channels c ON v.channel_id = c.channel_id
''')
for r in c.fetchall():
    print(dict(r))
