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
from services.expense_service import parse_expense_text, record_transaction, format_budget_report
from services.tts_service import generate_tts_audio
from services.moderation_service import check_spam
from services.news_service import fetch_morning_headlines
from database import is_antispam_enabled, set_antispam_enabled, clear_user_expenses

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

def test_expense_tracker():
    print("\n[5] Testing Expense & Income Tracker...")
    init_db()
    test_chat = 777666555
    clear_user_expenses(test_chat)

    # 1. Parse various test cases
    p1 = parse_expense_text("/spend 5$ coffee", force_type="expense")
    assert p1["type"] == "expense" and p1["amount"] == 5.0 and p1["currency"] == "USD"
    record_transaction(test_chat, p1)

    p2 = parse_expense_text("ចាយ 20,000៛ ញ៉ាំបាយ")
    assert p2["type"] == "expense" and p2["amount"] == 20000.0 and p2["currency"] == "KHR"
    record_transaction(test_chat, p2)

    p3 = parse_expense_text("/income 500$ monthly salary", force_type="income")
    assert p3["type"] == "income" and p3["amount"] == 500.0 and p3["currency"] == "USD"
    record_transaction(test_chat, p3)

    rep = format_budget_report(test_chat, days=30)
    assert "500.00 $" in rep
    assert "5.00 $" in rep
    assert "20,000 ៛" in rep
    print("  - Budget report generated with USD and KHR balances!")
    print("  [OK] Expense & Income Tracker verified!")

def test_tts_service():
    print("\n[6] Testing Text-to-Speech (TTS)...")
    km_fp = generate_tts_audio("សួស្តីកម្ពុជា")
    assert len(km_fp.getvalue()) > 5000, "Should generate valid audio bytes"
    en_fp = generate_tts_audio("Hello from Telegram Bot")
    assert len(en_fp.getvalue()) > 5000, "Should generate valid audio bytes"
    print(f"  - Khmer speech bytes: {len(km_fp.getvalue())}, English: {len(en_fp.getvalue())}")
    print("  [OK] TTS Service verified!")

def test_moderation_service():
    print("\n[7] Testing Anti-Spam & Moderation...")
    spam1, _ = check_spam("កាស៊ីណូអនឡាញ ឈ្នះ 100% ចុះឈ្មោះឥឡូវនេះ")
    assert spam1 is True, "Should detect Khmer casino spam"
    
    clean1, _ = check_spam("សួស្តីបងប្អូន ស្អែកមានប្រជុំម៉ោង 10")
    assert clean1 is False, "Should pass normal conversation"

    test_chat = 123456789
    set_antispam_enabled(test_chat, True)
    assert is_antispam_enabled(test_chat) is True
    set_antispam_enabled(test_chat, False)
    assert is_antispam_enabled(test_chat) is False
    print("  [OK] Anti-Spam & Moderation verified!")

async def test_news_service_async():
    print("\n[8] Testing News RSS Service...")
    headlines = await fetch_morning_headlines()
    assert len(headlines["cambodia"]) > 0 or len(headlines["tech"]) > 0
    print(f"  - Cambodia headlines: {len(headlines['cambodia'])}, Tech headlines: {len(headlines['tech'])}")
    print("  [OK] News Service verified!")

if __name__ == "__main__":
    test_holiday_calendar()
    test_database()
    test_video_url_extractor()
    asyncio.run(test_weather_service_async())
    test_expense_tracker()
    test_tts_service()
    test_moderation_service()
    asyncio.run(test_news_service_async())
    print("\n🎉 ALL 8 TEST SUITES PASSED SUCCESSFULLY! ✅")
