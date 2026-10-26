import sqlite3

conn = sqlite3.connect('data/tiktok_tool.db')
c = conn.cursor()
c.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in c.fetchall()]

for t in tables:
    c.execute(f"PRAGMA table_info({t})")
    cols = [col[1] for col in c.fetchall()]
    path_cols = [col for col in cols if any(k in col.lower() for k in ['path', 'file', 'dir', 'url'])]
    if path_cols:
        print(f"Table '{t}': {path_cols}")
        for pcol in path_cols:
            if 'url' not in pcol.lower() or 'path' in pcol.lower():
                try:
                    c.execute(f"SELECT COUNT(*) FROM {t} WHERE {pcol} IS NOT NULL AND {pcol} != ''")
                    cnt = c.fetchone()[0]
                    if cnt > 0:
                        print(f"   {pcol} has {cnt} rows")
                        c.execute(f"SELECT id, {pcol} FROM {t} WHERE {pcol} IS NOT NULL AND {pcol} != '' LIMIT 5")
                        for row in c.fetchall():
                            print(f"      {row}")
                except Exception as e:
                    pass
