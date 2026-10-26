import sqlite3
import json

conn = sqlite3.connect('data/tiktok_tool.db')
conn.row_factory = sqlite3.Row
c = conn.cursor()
c.execute("SELECT * FROM gpm_profiles WHERE tiktok_username LIKE '%ceowapp%' OR name LIKE '%ceowapp%'")
rows = [dict(r) for r in c.fetchall()]
print(json.dumps(rows, indent=2, ensure_ascii=False))
