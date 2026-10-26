import sys
import os

sys.path.insert(0, os.path.abspath('.'))

from backend.database import init_db
from backend.modules.yt_monitor import YouTubeRSSMonitor

init_db()

def test_subtitle_hierarchy():
    print("=== Testing Priority: Channel > Campaign > Global for Subtitles ===")
    monitor = YouTubeRSSMonitor()

    # Case 1: All unset -> Global fallback
    res1 = monitor.get_effective_subtitle_settings(channel_obj={}, camp={})
    print(f"Case 1 (Global fallback): {res1}")
    assert res1["subtitle_style"] == "karaoke_yellow"
    assert res1["subtitle_position"] == "center"
    assert res1["disable_subtitle_for_shorts"] is False
    assert res1["enable_subtitles"] is True

    # Case 2: Campaign overrides Global
    camp2 = {
        "subtitle_enabled": 1,
        "subtitle_style": "classic_white",
        "subtitle_position": "bottom",
        "disable_subtitle_for_shorts": 1
    }
    ch2 = {
        "subtitle_enabled": None,
        "subtitle_style": "inherit",
        "subtitle_position": "inherit",
        "disable_subtitle_for_shorts": 0
    }
    res2 = monitor.get_effective_subtitle_settings(channel_obj=ch2, camp=camp2)
    print(f"Case 2 (Campaign overrides Global): {res2}")
    assert res2["subtitle_style"] == "classic_white"
    assert res2["subtitle_position"] == "bottom"
    assert res2["disable_subtitle_for_shorts"] is True
    assert res2["enable_subtitles"] is True

    # Case 3: Campaign uses inherit_channel -> follows Channel
    camp3 = {
        "subtitle_enabled": 1,
        "subtitle_style": "inherit_channel",
        "subtitle_position": "inherit_channel",
        "disable_subtitle_for_shorts": 0
    }
    ch3 = {
        "subtitle_enabled": 1,
        "subtitle_style": "tiktok_gradient",
        "subtitle_position": "bottom",
        "disable_subtitle_for_shorts": 1
    }
    res3 = monitor.get_effective_subtitle_settings(channel_obj=ch3, camp=camp3)
    print(f"Case 3 (Campaign inherit_channel follows Channel): {res3}")
    assert res3["subtitle_style"] == "tiktok_gradient"
    assert res3["subtitle_position"] == "bottom"
    assert res3["disable_subtitle_for_shorts"] is True

    # Case 4: Channel overrides Campaign (Channel > Campaign > Global)
    camp4 = {
        "subtitle_enabled": 1,
        "subtitle_style": "karaoke_yellow",
        "subtitle_position": "center",
        "disable_subtitle_for_shorts": 0
    }
    ch4 = {
        "subtitle_enabled": 0,  # Channel disabled subtitles
        "subtitle_style": "tiktok_gradient",
        "subtitle_position": "bottom",
        "disable_subtitle_for_shorts": 1
    }
    res4 = monitor.get_effective_subtitle_settings(channel_obj=ch4, camp=camp4)
    print(f"Case 4 (Channel overrides Campaign): {res4}")
    assert res4["enable_subtitles"] is False
    assert res4["subtitle_style"] == "tiktok_gradient"
    assert res4["subtitle_position"] == "bottom"
    assert res4["disable_subtitle_for_shorts"] is True

    print("✅ ALL SUBTITLE HIERARCHY TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    test_subtitle_hierarchy()
