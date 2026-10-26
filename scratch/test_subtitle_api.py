import os
import sys
sys.path.insert(0, os.path.abspath('.'))

from fastapi.testclient import TestClient
from backend.app import app
from backend.database import init_db, get_connection

init_db()
client = TestClient(app)

# 1. Test Channel Subtitle update
conn = get_connection()
cursor = conn.cursor()
cursor.execute("INSERT OR REPLACE INTO channels (channel_id, title, url, is_active) VALUES ('TEST_SUB_CH', 'Sub Test Ch', 'https://yt.com', 1)")
conn.commit()
conn.close()

res = client.post('/api/youtube/channels/update', json={
    'channel_id': 'TEST_SUB_CH',
    'subtitle_enabled': 1,
    'subtitle_style': 'tiktok_gradient',
    'subtitle_position': 'bottom',
    'disable_subtitle_for_shorts': 1
})
assert res.status_code == 200, res.text

# Verify DB
conn = get_connection()
cursor = conn.cursor()
cursor.execute('SELECT subtitle_enabled, subtitle_style, subtitle_position, disable_subtitle_for_shorts FROM channels WHERE channel_id = ?', ('TEST_SUB_CH',))
row = cursor.fetchone()
print('Channel DB Row:', dict(row))
assert row['subtitle_enabled'] == 1
assert row['subtitle_style'] == 'tiktok_gradient'
assert row['subtitle_position'] == 'bottom'
assert row['disable_subtitle_for_shorts'] == 1

# 2. Test Campaign Create with inherit_channel
camp_res = client.post('/api/campaigns', json={
    'name': 'Test Sub Campaign',
    'channel_ids': ['TEST_SUB_CH'],
    'gpm_profile_ids': [1],
    'subtitle_enabled': 1,
    'subtitle_style': 'inherit_channel',
    'subtitle_position': 'inherit_channel',
    'disable_subtitle_for_shorts': 1
})
assert camp_res.status_code == 200, camp_res.text
camp_id = camp_res.json()['id']

cursor.execute('SELECT subtitle_enabled, subtitle_style, subtitle_position, disable_subtitle_for_shorts FROM campaigns WHERE id = ?', (camp_id,))
camp_row = cursor.fetchone()
print('Campaign DB Row:', dict(camp_row))
assert camp_row['subtitle_style'] == 'inherit_channel'
assert camp_row['subtitle_position'] == 'inherit_channel'

# Cleanup
cursor.execute('DELETE FROM channels WHERE channel_id = ?', ('TEST_SUB_CH',))
cursor.execute('DELETE FROM campaigns WHERE id = ?', (camp_id,))
conn.commit()
conn.close()

print('✅ API Endpoints Test Passed!')
