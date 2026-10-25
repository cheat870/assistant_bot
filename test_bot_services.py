import sys
import io
from pathlib import Path

# Ensure UTF-8 output on Windows console
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services.holiday_calendar import (
    get_upcoming_holidays,
    get_today_holiday,
    get_holidays_by_year,
    format_upcoming_message,
    format_calendar_message,
    format_alert_message,
)
from database import init_db, add_subscriber, is_subscribed, remove_subscriber, get_active_subscribers
from services.video_downloader import extract_video_url

def test_holiday_calendar():
    print("[1] Testing Holiday Calendar Service...")
    upcoming = get_upcoming_holidays(limit=3)
    assert len(upcoming) > 0, "Should return upcoming holidays"
    print(f"  - Upcoming holidays count: {len(upcoming)}")
    print(f"  - Next holiday: {upcoming[0]['name_km']} on {upcoming[0]['date']} ({upcoming[0]['days_left']} days left)")
    
    holidays_2026 = get_holidays_by_year(2026)
    assert len(holidays_2026) >= 15, "Should have full list of 2026 holidays"
    print(f"  - 2026 holidays count: {len(holidays_2026)}")
    
    msg = format_upcoming_message()
    assert "Upcoming Holidays" in msg
    
    alert_msg = format_alert_message(upcoming[0])
    assert "៤:០០ ព្រឹក" in alert_msg
    print("  [OK] Holiday Calendar Service verified!")

def test_database():
    print("\n[2] Testing Database Service...")
    init_db()
    test_chat_id = 999888777
    add_subscriber(test_chat_id, "test_user", "private")
    assert is_subscribed(test_chat_id) is True
    assert test_chat_id in get_active_subscribers()
    
    remove_subscriber(test_chat_id)
    assert is_subscribed(test_chat_id) is False
    assert test_chat_id not in get_active_subscribers()
    print("  [OK] Database functions verified!")

def test_video_url_extractor():
    print("\n[3] Testing Video URL Extractor...")
    test_urls = [
        ("https://www.tiktok.com/@user/video/1234567890", "TikTok"),
        ("https://vt.tiktok.com/ZS2xyz123/", "TikTok Short"),
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "YouTube"),
        ("https://youtu.be/dQw4w9WgXcQ", "YouTube Short"),
        ("https://www.facebook.com/watch/?v=123456789", "Facebook"),
        ("https://fb.watch/xyz123abc/", "Facebook Watch"),
        ("https://www.instagram.com/reel/C3xyz123abc/", "Instagram Reel"),
        ("https://x.com/user/status/123456789", "X / Twitter"),
    ]
    for url, site_name in test_urls:
        extracted = extract_video_url(f"Check this out {url} cool video")
        assert extracted == url, f"Failed for {site_name}: expected {url}, got {extracted}"
        print(f"  - Matched {site_name}: {url[:40]}...")
    print("  [OK] Video URL extractor verified!")

if __name__ == "__main__":
    test_holiday_calendar()
    test_database()
    test_video_url_extractor()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY! ✅")
