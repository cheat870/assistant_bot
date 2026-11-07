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
from services.weather_service import (
    fetch_weather,
    format_weather_message,
    reverse_geocode_async,
    get_detailed_cambodia_location,
    format_detailed_location_message,
)
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

    detailed = await get_detailed_cambodia_location(11.5564, 104.9282)
    assert "province" in detailed
    assert "district" in detailed
    assert "commune" in detailed
    assert "village" in detailed
    print(f"  - Detailed Location Hierarchy:")
    print(f"    * 🏡 ភូមិ/ផ្លូវ: {detailed['village']}")
    print(f"    * 🏘️ សង្កាត់/ឃុំ: {detailed['commune']}")
    print(f"    * 🏢 ខណ្ឌ/ស្រុក: {detailed['district']}")
    print(f"    * 🏛️ រាជធានី/ខេត្ត: {detailed['province']}")
    print("  [OK] Weather Service & Detailed Location verified!")

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

def test_pdf_service():
    print("\n[9] Testing PDF Extraction & Session Service...")
    import pypdf
    from services.pdf_service import extract_pdf_info_and_text
    from database import save_pdf_session, get_pdf_session, clear_pdf_session
    
    # Create test in-memory PDF
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=300, height=300)
    buf = io.BytesIO()
    writer.write(buf)
    pdf_bytes = buf.getvalue()
    
    info = extract_pdf_info_and_text(pdf_bytes)
    assert info["success"] is True
    assert info["total_pages"] == 1
    print(f"  - In-memory PDF created and extracted: {info['total_pages']} page(s)")
    
    # Test session storage
    test_chat = 99887766
    save_pdf_session(test_chat, "test_contract.pdf", "Summary of contract", "Page 1 content", 1)
    sess = get_pdf_session(test_chat)
    assert sess is not None
    assert sess["filename"] == "test_contract.pdf"
    clear_pdf_session(test_chat)
    assert get_pdf_session(test_chat) is None
    print("  [OK] PDF Service and session storage verified!")

def test_image_enhancer():
    print("\n[10] Testing Image Enhancer & Super-Resolution...")
    import numpy as np
    import cv2
    from services.image_enhancer_service import enhance_image
    
    # Create dummy 120x120 test image
    dummy = np.zeros((120, 120, 3), dtype=np.uint8)
    dummy[:60, :] = [220, 100, 50]
    dummy[60:, :] = [50, 150, 220]
    cv2.putText(dummy, "HD", (30, 70), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 255, 255), 2)
    _, buf = cv2.imencode(".jpg", dummy)
    raw_bytes = buf.tobytes()
    
    enhanced_bytes, metrics = enhance_image(raw_bytes, target_scale=2)
    assert len(enhanced_bytes) > 0
    assert metrics["new_width"] > metrics["orig_width"]
    print(f"  - Enhanced: {metrics['orig_width']}x{metrics['orig_height']} -> {metrics['new_width']}x{metrics['new_height']} (Scale: {metrics['scale']}x, Time: {metrics['elapsed_seconds']}s)")
    print("  [OK] Image Enhancer verified!")

def test_watermark_service():
    print("\n[11] Testing Watermark Service...")
    from PIL import Image
    from services.watermark_service import apply_watermark
    
    img = Image.new("RGB", (400, 300), color=(80, 120, 160))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    raw_bytes = buf.getvalue()
    
    wm_bytes = apply_watermark(raw_bytes, text="Angkor Store 012 345 678", position="bottom_right")
    assert len(wm_bytes) > 0
    print(f"  - Watermarked badge image size: {len(wm_bytes)} bytes")
    
    diag_bytes = apply_watermark(raw_bytes, text="CONFIDENTIAL", position="diagonal")
    assert len(diag_bytes) > 0
    print(f"  - Diagonal watermark image size: {len(diag_bytes)} bytes")
    print("  [OK] Watermark Service verified!")

def test_welcome_banner_service():
    print("\n[12] Testing Custom Welcome Banner Service...")
    from services.welcome_banner_service import generate_welcome_banner
    from database import is_welcome_enabled, set_welcome_enabled
    
    banner_bytes = generate_welcome_banner(
        user_name="Socheat Sopheap",
        group_title="Cambodia Developers Hub",
        avatar_bytes=None,
        member_count=1250
    )
    assert len(banner_bytes) > 10000
    print(f"  - Generated welcome banner size: {len(banner_bytes)} bytes")
    
    test_group = 88776655
    set_welcome_enabled(test_group, True)
    assert is_welcome_enabled(test_group) is True
    set_welcome_enabled(test_group, False)
    assert is_welcome_enabled(test_group) is False
    print("  [OK] Welcome Banner & Group Settings verified!")

def test_image_location_service():
    print("\n[13] Testing Image Location Extraction (EXIF GPS)...")
    from PIL import Image, ExifTags
    from services.image_location_service import extract_gps_from_image_bytes, format_photo_gps_message
    
    # Create an in-memory JPEG with EXIF GPS (Phnom Penh)
    img = Image.new("RGB", (100, 100), color="blue")
    exif = img.getexif()
    gps_ifd = exif.get_ifd(ExifTags.IFD.GPSInfo)
    gps_ifd[1] = "N"
    gps_ifd[2] = (11.0, 33.0, 23.0)
    gps_ifd[3] = "E"
    gps_ifd[4] = (104.0, 55.0, 41.0)
    
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    jpeg_bytes = buf.getvalue()
    
    coords = extract_gps_from_image_bytes(jpeg_bytes)
    assert coords is not None
    assert abs(coords[0] - 11.556389) < 0.001
    assert abs(coords[1] - 104.928056) < 0.001
    print(f"  - Extracted GPS coordinates: {coords[0]}, {coords[1]}")
    
    loc_dummy = {
        "village": "វិមានឯករាជ្យ",
        "commune": "សង្កាត់បឹងកេងកងទី ១",
        "district": "ខណ្ឌដូនពេញ",
        "province": "រាជធានីភ្នំពេញ",
        "lat": coords[0],
        "lon": coords[1]
    }
    msg = format_photo_gps_message(loc_dummy, "28°C")
    assert "រាជធានីភ្នំពេញ" in msg
    assert "Google Maps" in msg
    print("  [OK] Image Location Extraction Service verified!")

def test_clean_chat_and_auto_cleanup():
    print("\n[14] Testing Chat Cleaner & Auto-Cleanup Keyboards...")
    from handlers.command_handlers import get_main_menu_keyboard, get_persistent_bottom_keyboard, clean_chat_command
    
    # Verify bottom persistent keyboard has clean chat button
    bottom_kb = get_persistent_bottom_keyboard()
    bottom_buttons = [btn.text for row in bottom_kb.keyboard for btn in row]
    assert any("សម្អាតសារ" in b for b in bottom_buttons), "Bottom keyboard must contain clean chat button"
    print("  - Persistent bottom keyboard contains '🧹 សម្អាតសារ' button: OK")

    # Verify inline main menu keyboard has clean chat callback
    main_kb = get_main_menu_keyboard(chat_id=12345)
    inline_callbacks = [btn.callback_data for row in main_kb.inline_keyboard for btn in row if btn.callback_data]
    assert "btn_clean_chat" in inline_callbacks, "Main menu keyboard must contain btn_clean_chat"
    print("  - Main menu keyboard contains 'btn_clean_chat' callback: OK")
    print("  [OK] Chat Cleaner & Auto-Cleanup verified!")

if __name__ == "__main__":
    test_holiday_calendar()
    test_database()
    test_video_url_extractor()
    asyncio.run(test_weather_service_async())
    test_expense_tracker()
    test_tts_service()
    test_moderation_service()
    asyncio.run(test_news_service_async())
    test_pdf_service()
    test_image_enhancer()
    test_watermark_service()
    test_welcome_banner_service()
    test_image_location_service()
    test_clean_chat_and_auto_cleanup()
    print("\n🎉 ALL 14 TEST SUITES PASSED SUCCESSFULLY! ✅")
