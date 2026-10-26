import sqlite3

conn = sqlite3.connect('data/tiktok_tool.db')
c = conn.cursor()
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_min_duration', '180')")
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_max_duration', '3600')")
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_include_shorts', '1')")
c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('download_include_longform', '1')")
conn.commit()
conn.close()
print("Successfully set download_min_duration to 180s in database!")
