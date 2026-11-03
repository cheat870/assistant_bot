import sys
import io
import asyncio
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
from database import (
    init_db,
    add_subscriber,
    is_subscribed,
    remove_subscriber,
    get_active_subscribers,
    set_user_location,
    get_user_weather_settings,
    set_weather_alert_active,
    get_active_weather_subscribers,
)
from services.video_downloader import extract_video_url
from services.weather_service import fetch_weather, format_weather_message, reverse_geocode_async

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

    # Weather settings tests
    set_user_location(test_chat_id, 13.3671, 103.8448, "ខេត្តសៀមរាប")
    settings = get_user_weather_settings(test_chat_id)
    assert settings["location_name"] == "ខេត្តសៀមរាប"
    assert settings["latitude"] == 13.3671
    assert settings["is_active"] is True
    print("  - Saved location verified: ខេត្តសៀមរាប")

    set_weather_alert_active(test_chat_id, False)
    assert get_user_weather_settings(test_chat_id)["is_active"] is False

    set_weather_alert_active(test_chat_id, True)
    active_subs = get_active_weather_subscribers()
    assert any(s["chat_id"] == test_chat_id for s in active_subs)
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

async def test_weather_service_async():
    print("\n[4] Testing Weather Service & Reverse Geocoding...")
    w_data = await fetch_weather(11.5564, 104.9282)
    assert w_data is not None, "Should fetch weather data from Open-Meteo"
    assert "current" in w_data
    assert "temperature_2m" in w_data["current"]
    print(f"  - Current Temp: {w_data['current']['temperature_2m']}°C")
    
    msg = format_weather_message(w_data, "រាជធានីភ្នំពេញ", is_daily_alert=True)
    assert "៥:០០ ព្រឹក" in msg
    assert "រាជធានីភ្នំពេញ" in msg
    print("  - Daily 5:00 AM Alert Message formatted successfully!")

    loc_name = await reverse_geocode_async(11.5564, 104.9282)
    print(f"  - Reverse geocoded: {loc_name}")
    assert loc_name is not None
    print("  [OK] Weather Service verified!")

if __name__ == "__main__":
    test_holiday_calendar()
    test_database()
    test_video_url_extractor()
    asyncio.run(test_weather_service_async())
    print("\n🎉 ALL TESTS (HOLIDAY + VIDEO + WEATHER 5AM) PASSED SUCCESSFULLY! ✅")
