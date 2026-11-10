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

    # Test Vision AI Maps URL extraction helper
    from services.image_location_service import extract_maps_url_from_vision_text
    sample_vision_coords = "📍 **ការវិភាគទីតាំងពីរូបភាព**\n• ឈ្មោះទីតាំង៖ ប្រាសាទអង្គរវត្ត\n• កូអរដោនេប៉ាន់ស្មាន: 13.4125, 103.8670"
    url_coords = extract_maps_url_from_vision_text(sample_vision_coords)
    assert url_coords == "https://www.google.com/maps?q=13.4125,103.867"
    print(f"  - Vision coordinate Maps URL: {url_coords}")

    sample_vision_landmark = "📍 **ការវិភាគទីតាំងពីរូបភាព**\n• ឈ្មោះទីតាំង៖ រង្វង់មូលវិមានឯករាជ្យ\n• ខេត្ត/រាជធានី៖ រាជធានីភ្នំពេញ"
    url_landmark = extract_maps_url_from_vision_text(sample_vision_landmark)
    assert url_landmark and "google.com/maps/search" in url_landmark
    print(f"  - Vision landmark Maps URL: {url_landmark}")

    print("  [OK] Image Location Extraction Service verified!")

def test_clean_chat_and_auto_cleanup():
    print("\n[14] Testing Chat Cleaner & Auto-Cleanup Keyboards...")
    from handlers.command_handlers import get_main_menu_keyboard, get_persistent_bottom_keyboard, clean_chat_command
    
    # Verify bottom persistent keyboard has clean chat button
    bottom_kb = get_persistent_bottom_keyboard()
    bottom_buttons = [btn.text for row in bottom_kb.keyboard for btn in row]
    assert any("សម្អាតសារ" in b for b in bottom_buttons), "Bottom keyboard must contain clean chat button"
    print("  - Persistent bottom keyboard contains '🧹 សម្អាតសារ' button: OK")

    # Verify inline main menu keyboard has clean chat and auto-clean toggle callbacks
    main_kb = get_main_menu_keyboard(chat_id=12345)
    inline_callbacks = [btn.callback_data for row in main_kb.inline_keyboard for btn in row if btn.callback_data]
    assert "btn_clean_chat" in inline_callbacks, "Main menu keyboard must contain btn_clean_chat"
    assert "btn_toggle_autoclean" in inline_callbacks, "Main menu keyboard must contain btn_toggle_autoclean"
    
    # Check button text for 3AM & 12PM schedule
    autoclean_btn_text = [btn.text for row in main_kb.inline_keyboard for btn in row if "Auto-Clean" in (btn.text or "")]
    assert any("3AM/12PM" in t for t in autoclean_btn_text), f"Button should mention 3AM/12PM: {autoclean_btn_text}"
    print("  - Main menu keyboard contains 'Auto-Clean (3AM/12PM)' callback: OK")

    # Test auto-clean database logic (3AM & 12PM scheduled auto-clean)
    from database import (
        record_auto_clean_message,
        get_expired_auto_clean_messages,
        delete_auto_clean_message_records,
        is_auto_clean_enabled,
        set_auto_clean_enabled,
        get_all_auto_clean_chats,
        get_auto_clean_messages_for_chat,
        clear_auto_clean_messages_for_chat,
    )
    from datetime import datetime, timezone, timedelta

    test_chat = 999888
    set_auto_clean_enabled(test_chat, True)
    assert is_auto_clean_enabled(test_chat) is True

    record_auto_clean_message(test_chat, 1001)
    record_auto_clean_message(test_chat, 1002)
    
    # Test chat-specific auto-clean query
    chat_msgs = get_auto_clean_messages_for_chat(test_chat)
    assert any(m[1] == 1001 for m in chat_msgs), "Must retrieve recorded message 1001"
    assert any(m[1] == 1002 for m in chat_msgs), "Must retrieve recorded message 1002"
    
    # Check active auto-clean chats
    auto_chats = get_all_auto_clean_chats()
    assert test_chat in auto_chats, "Test chat should be in active auto-clean chats"
    
    # Clear for chat
    clear_auto_clean_messages_for_chat(test_chat)
    chat_msgs_after = get_auto_clean_messages_for_chat(test_chat)
    assert len(chat_msgs_after) == 0, "Chat messages should be cleared"

    # Also test cutoff-based expiry for compatibility
    record_auto_clean_message(test_chat, 2001)
    future_cutoff = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
    expired = get_expired_auto_clean_messages(future_cutoff)
    matching = [e for e in expired if e[1] == test_chat and e[2] == 2001]
    assert len(matching) == 1, "Must find recorded message when past cutoff"
    
    delete_auto_clean_message_records([matching[0][0]])
    expired_after = get_expired_auto_clean_messages(future_cutoff)
    assert not any(e[1] == test_chat and e[2] == 2001 for e in expired_after)
    print("  - Twice-daily (3AM & 12PM) auto-clean database pipeline: OK")
    print("  [OK] Chat Cleaner & Twice-Daily Auto-Clean verified!")

def test_long_term_memory_service():
    print("\n[15] Testing Long-Term Vector & Semantic Memory Service...")
    from services.memory_service import (
        format_memories_for_ai,
        format_user_memory_display,
        auto_extract_and_save_facts,
    )
    from database import (
        save_user_memory,
        get_user_memories,
        clear_user_memories,
    )
    test_user_id = 777111222
    clear_user_memories(test_user_id)
    
    # 1. Manual save
    save_user_memory(test_user_id, "music", "favorite_singer", "ចូលចិត្តស្តាប់ចម្រៀង វណ្ណដា (VannDa)")
    save_user_memory(test_user_id, "budget", "morning_coffee", "ចូលចិត្តផឹកកាហ្វេទឹកដោះគោពេលព្រឹក")
    
    memories = get_user_memories(test_user_id)
    assert len(memories) == 2, "Should have 2 saved memories"
    assert any("វណ្ណដា" in m["content"] for m in memories)
    print("  - Stored user memories verified: 2 items")
    
    # 2. Context formatting for AI
    ai_prompt_context = format_memories_for_ai(test_user_id)
    assert "វណ្ណដា" in ai_prompt_context
    assert "User Profile & Long-Term Memories" in ai_prompt_context
    print("  - AI prompt contextual memory block generated: OK")
    
    # 3. Automatic memory extraction from chat
    fact_result = auto_extract_and_save_facts(test_user_id, "ថ្ងៃកំណើតខ្ញុំគឺ ថ្ងៃទី ១៥ ខែកក្កដា")
    assert fact_result is not None
    assert "ថ្ងៃកំណើត" in fact_result
    
    memories_after = get_user_memories(test_user_id)
    assert len(memories_after) == 3
    print("  - Auto-extracted memory from user text: OK")
    
    display = format_user_memory_display(test_user_id)
    assert "ប្រព័ន្ធចងចាំ Long-Term Memory" in display
    
    clear_user_memories(test_user_id)
    assert len(get_user_memories(test_user_id)) == 0
    print("  [OK] Long-Term Vector & Semantic Memory Service verified!")

async def test_enterprise_architecture():
    print("\n[16] Testing Enterprise Architecture (PostgreSQL Ready, Redis/Memory Cache & Worker)...")
    from database import get_database_info
    from services.cache_service import cache_set, cache_get, cache_delete, get_cache_status
    from services.worker_service import execute_heavy_job, get_worker_status

    # 1. Database Info
    db_info = get_database_info()
    assert "engine" in db_info
    print(f"  - Database Engine: {db_info['engine']} (PostgreSQL ready: {db_info['is_postgres']})")

    # 2. Cache Service
    cache_set("test_rate_usd", 4050, ttl_seconds=60)
    cached_val = cache_get("test_rate_usd")
    assert cached_val == 4050
    cache_delete("test_rate_usd")
    assert cache_get("test_rate_usd") is None
    c_status = get_cache_status()
    print(f"  - Cache Status: {c_status['provider']} (In-memory items: {c_status['in_memory_items']})")

    # 3. Background Worker
    def heavy_math(x, y):
        return x * y + 100
    res = await execute_heavy_job("test_calc", heavy_math, 5, 20)
    assert res == 200
    w_status = get_worker_status()
    print(f"  - Background Worker Pool: {w_status['engine']} (Workers: {w_status['max_workers']})")
    print("  [OK] Enterprise Architecture verified!")

async def test_briefing_service_async():
    print("\n[17] Testing Morning Executive Briefing (VIP Secretary)...")
    from services.briefing_service import generate_executive_briefing
    chat_id = 999888777
    briefing = await generate_executive_briefing(chat_id, user_name="Socheat")
    assert "Morning Executive Briefing" in briefing
    assert "Socheat" in briefing
    assert "អាកាសធាតុប្រចាំថ្ងៃ" in briefing
    assert "កាលវិភាគ" in briefing
    assert "សេដ្ឋកិច្ច" in briefing
    assert "សម្រង់គំនិតលើកទឹកចិត្ត" in briefing
    print("  - Generated VIP Executive Briefing successfully!")
    print("  [OK] Morning Executive Briefing verified!")

def test_file_master_service():
    print("\n[18] Testing Universal File Master (PDF Compression, DOCX, Split & Merge)...")
    import pypdf
    import io
    from PIL import Image
    from services.file_master_service import (
        compress_pdf_bytes,
        compress_image_bytes,
        pdf_to_docx_bytes,
        split_pdf_pages,
        merge_pdf_documents,
    )

    # 1. Create a dummy multi-page PDF in memory
    writer = pypdf.PdfWriter()
    for i in range(3):
        writer.add_blank_page(width=300, height=300)
    pdf_buf = io.BytesIO()
    writer.write(pdf_buf)
    dummy_pdf_bytes = pdf_buf.getvalue()

    # Test PDF Compression
    comp_pdf, c_stats = compress_pdf_bytes(dummy_pdf_bytes)
    assert len(comp_pdf) > 0
    assert c_stats["pages"] == 3
    print(f"  - PDF Compression verified: {c_stats['pages']} pages")

    # Test PDF to DOCX
    docx_bytes, d_stats = pdf_to_docx_bytes(dummy_pdf_bytes, filename="test_doc.pdf")
    assert len(docx_bytes) > 0
    # Verify it is a valid zip archive with word/document.xml
    import zipfile
    with zipfile.ZipFile(io.BytesIO(docx_bytes)) as z:
        assert "word/document.xml" in z.namelist()
        assert "[Content_Types].xml" in z.namelist()
    print(f"  - PDF to Word (.docx) generator verified: {d_stats['pages']} pages, valid OpenXML zip archive")

    # Test PDF Split
    split_bytes, s_stats = split_pdf_pages(dummy_pdf_bytes, 1, 2)
    assert s_stats["extracted_pages"] == 2
    print(f"  - PDF Split verified: extracted {s_stats['extracted_pages']} pages")

    # Test PDF Merge
    merged_bytes, m_stats = merge_pdf_documents([split_bytes, split_bytes])
    assert m_stats["total_pages"] == 4
    print(f"  - PDF Merge verified: combined {m_stats['total_documents']} documents into {m_stats['total_pages']} pages")

    # Test Image Compression
    img = Image.new("RGB", (2000, 1500), color=(100, 150, 200))
    img_buf = io.BytesIO()
    img.save(img_buf, format="JPEG", quality=95)
    raw_img_bytes = img_buf.getvalue()

    comp_img, img_stats = compress_image_bytes(raw_img_bytes, max_dim=800, quality=70)
    assert len(comp_img) < len(raw_img_bytes)
    print(f"  - Image Compression & Resize: {img_stats['original_res']} -> {img_stats['new_res']} (-{img_stats['saved_pct']}%)")
    print("  [OK] Universal File Master verified!")

def test_camroad_trip_planner():
    print("\n[19] Testing CamRoad Trip Planner & Car Diagnostic...")
    from services.camroad_car_service import (
        CAMBODIA_ROUTES,
        match_destination,
        calculate_trip_details,
        format_trip_report,
    )

    # Test destination matching
    dest_sr = match_destination("សៀមរាប")
    assert dest_sr is not None
    assert dest_sr["distance_km"] == 314
    print("  - Matched destination 'សៀមរាប': 314 km, NR6")

    dest_shv = match_destination("sihanoukville")
    assert dest_shv is not None
    assert dest_shv["distance_km"] == 187
    print("  - Matched destination 'sihanoukville': 187 km, Expressway E4")

    # Test trip calculation & fuel cost
    trip = calculate_trip_details(dest_sr, origin="រាជធានីភ្នំពេញ", vehicle_type="suv")
    assert trip["fuel_needed_liters"] > 20
    assert trip["fuel_cost_khr"] > 50000
    assert "google.com/maps/dir" in trip["maps_dir_url"]
    print(f"  - Calculated fuel: ~{trip['fuel_needed_liters']}L, cost: ~{trip['fuel_cost_khr']:,} KHR (~${trip['fuel_cost_usd']})")

    # Test report formatting
    report = format_trip_report(trip)
    assert "ផ្លូវជាតិលេខ ៦" in report
    assert "ក្រឡានកំពង់ធំ" in report
    assert "កន្លែងឈប់សម្រាក" in report
    print("  - Trip report formatted with highway, rest stops and local food!")
    print("  [OK] CamRoad Trip Planner verified!")

def test_code_runner_sandbox():
    print("\n[20] Testing Python Code Runner Sandbox & Debugger...")
    from services.code_runner_service import (
        execute_python_code_sandboxed,
        format_execution_result,
    )

    # 1. Test basic successful execution
    code_ok = "a = 15\nb = 27\nprint('Total:', a + b)"
    res_ok = execute_python_code_sandboxed(code_ok)
    assert res_ok["success"] is True
    assert res_ok["exit_code"] == 0
    assert "Total: 42" in res_ok["stdout"]
    assert res_ok["elapsed"] < 3.0
    print(f"  - Successful execution: {res_ok['stdout']} (in {res_ok['elapsed']}s)")

    # 2. Test error / traceback handling
    code_err = "x = 10 / 0"
    res_err = execute_python_code_sandboxed(code_err)
    assert res_err["success"] is False
    assert "ZeroDivisionError" in res_err["stderr"]
    print("  - ZeroDivisionError caught and handled in stderr!")

    # 3. Test security protection against dangerous patterns
    code_unsafe = "import os\nos.system('dir')"
    res_unsafe = execute_python_code_sandboxed(code_unsafe)
    assert res_unsafe["success"] is False
    assert "សុវត្ថិភាពខ្ពស់" in res_unsafe["stderr"]
    print("  - Blocked dangerous command: 'os.system' blocked successfully!")

    # 4. Test timeout handling
    code_loop = "while True:\n    pass"
    res_loop = execute_python_code_sandboxed(code_loop, timeout_seconds=0.6)
    assert res_loop["success"] is False
    assert "Timeout" in res_loop["stderr"]
    print("  - Infinite loop timeout handled cleanly (<= 0.6s)!")

    # 5. Test output formatter
    formatted = format_execution_result(res_ok, code_ok)
    assert "លទ្ធផលដំណើរការកូដ" in formatted
    assert "Total: 42" in formatted
    print("  - Formatted execution result markdown card: OK")
    print("  [OK] Python Code Runner Sandbox verified!")

def test_receipt_scanner_and_budget_export():
    print("\n[21] Testing AI Receipt Scanner, Pie Chart & Excel (.xlsx) Generator...")
    from services.receipt_budget_service import (
        record_receipt_transaction,
        generate_budget_pie_chart,
        generate_budget_excel,
    )
    import zipfile
    import io

    test_chat = 888777
    sample_receipt = {
        "is_receipt": True,
        "merchant": "Amazon Cafe IFL",
        "amount": 4.50,
        "currency": "USD",
        "category": "អាហារ និងភេសជ្ជៈ 🍜",
        "date": "2026-11-10",
        "items": ["Iced Latte", "Butter Croissant"],
        "summary_km": "ទិញកាហ្វេ និងនំពេលព្រឹក"
    }

    # 1. Test receipt transaction recording
    msg = record_receipt_transaction(test_chat, sample_receipt)
    assert "Amazon Cafe IFL" in msg
    assert "4.50 $" in msg
    assert "Iced Latte" in msg
    print("  - Recorded parsed receipt transaction to DB: OK")

    # 2. Test Donut/Pie Chart image generation
    chart_bytes = generate_budget_pie_chart(test_chat)
    assert chart_bytes is not None
    assert len(chart_bytes) > 2000
    assert chart_bytes[:4] == b"\x89PNG"
    print(f"  - Generated Donut/Pie Chart PNG ({len(chart_bytes):,} bytes): OK")

    # 3. Test authentic OpenXML Excel (.xlsx) generation
    excel_bytes = generate_budget_excel(test_chat)
    assert excel_bytes is not None
    assert len(excel_bytes) > 500
    with zipfile.ZipFile(io.BytesIO(excel_bytes)) as zf:
        names = zf.namelist()
        assert "[Content_Types].xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/workbook.xml" in names
        sheet_content = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        assert "Amazon Cafe IFL" in sheet_content
        assert "4.5" in sheet_content
    print(f"  - Generated pure OpenXML Excel (.xlsx) ({len(excel_bytes):,} bytes): OK")
    print("  [OK] Receipt Scanner, Chart & Excel verified!")

async def test_podcast_service_async():
    print("\n[22] Testing Web Article to Audio Podcast Service...")
    from services.podcast_service import (
        extract_article_content_from_url,
        generate_article_podcast,
        PODCAST_PROMPT,
    )

    assert "===SUMMARY===" in PODCAST_PROMPT
    assert "===SPOKEN===" in PODCAST_PROMPT
    assert "{Title in Khmer}" in PODCAST_PROMPT

    # Test error handling with unreachable URL
    res = await generate_article_podcast("https://invalid-non-existent-domain-123456.com")
    assert "success" in res
    assert res["success"] is False
    assert "មិនអាចទាញយកខ្លឹមសារ" in res["bullet_summary"]
    print("  - Handled invalid/unreachable URL cleanly: OK")
    print("  [OK] Web Article to Podcast verified!")

async def test_chord_music_service_async():
    print("\n[23] Testing Guitar/Piano Chord Finder & Shazam...")
    from services.chord_music_service import (
        find_song_chords,
        identify_song_from_audio,
        CHORD_PROMPT,
        AUDIO_SHAZAM_PROMPT,
    )

    assert "Key" in CHORD_PROMPT
    assert "Strumming Pattern" in CHORD_PROMPT
    assert "Shazam" in AUDIO_SHAZAM_PROMPT

    # 1. Test empty query validation
    empty_res = await find_song_chords("")
    assert "សូមវាយឈ្មោះបទចម្រៀង" in empty_res
    print("  - Empty song query validation: OK")

    # 2. Test chords retrieval
    chords = await find_song_chords("ចិត្តអើយ")
    assert len(chords) > 30
    assert "Key" in chords or "Chord" in chords
    print("  - Generated guitar/piano chord sheet: OK")

    # 3. Test Shazam prompt and structure
    shazam_offline = await identify_song_from_audio(b"dummy_audio_bytes", mime_type="audio/ogg")
    assert len(shazam_offline) > 10
    print("  - Shazam audio identifier pipeline verified: OK")
    print("  [OK] Chord Finder & Shazam verified!")

def test_two_way_voice_assistant():
    print("\n[24] Testing Two-Way Voice Assistant (Khmer Speech Synthesis)...")
    from services.tts_service import generate_tts_audio

    khmer_prompt = "សួស្តី! ខ្ញុំជាជំនួយការឆ្លាតវៃ Telegram របស់អ្នក។ ខ្ញុំអាចជួយលោកអ្នកបានគ្រប់ពេលវេលា!"
    fp = generate_tts_audio(khmer_prompt, lang="km")
    assert fp is not None
    data = fp.read()
    assert len(data) > 1000
    print(f"  - Synthesized Khmer voice audio response ({len(data):,} bytes): OK")
    print("  [OK] Two-Way Voice Assistant verified!")

async def test_telegram_user_resolver_async():
    print("\n[25] Testing Telegram Profile Resolver & 1-Click Link Generator...")
    from services.user_resolver_service import (
        extract_telegram_username,
        validate_username_format,
        resolve_telegram_user,
        format_user_resolver_card,
    )
    from database import init_db, add_subscriber, find_users_in_db
    init_db()

    # 1. Test username extraction from various formats
    assert extract_telegram_username("heamlyheak") == "heamlyheak"
    assert extract_telegram_username("@heamlyheak") == "heamlyheak"
    assert extract_telegram_username("https://t.me/heamlyheak") == "heamlyheak"
    assert extract_telegram_username("t.me/heamlyheak") == "heamlyheak"
    assert extract_telegram_username("tg://resolve?domain=heamlyheak") == "heamlyheak"
    assert extract_telegram_username("") is None
    print("  - Extracted clean usernames from raw text, @mentions, web URLs, and deep links: OK")

    # 2. Test format validation
    is_valid, clean, err = validate_username_format("")
    assert not is_valid and ("របៀបស្វែងរក" in err or "របៀបប្រើប្រាស់" in err)

    is_valid, clean, err = validate_username_format("heamlyheak")
    assert is_valid and clean == "heamlyheak"
    print("  - Username format validation: OK")

    # 3. Test local database search
    add_subscriber(777666, "heamlyheak_test", "private")
    matches = find_users_in_db("heamlyheak_test")
    assert len(matches) > 0
    assert matches[0]["username"] == "heamlyheak_test"
    print(f"  - Searched user in local database: found {len(matches)} match: OK")

    # 4. Test multi-match resolution and card formatting
    res_heam = await resolve_telegram_user(None, "heamlyheak")
    assert res_heam["valid"] is True
    assert len(res_heam["matches"]) >= 1
    # Check that similar match @lyheak was found!
    usernames_found = [m["username"] for m in res_heam["matches"]]
    assert "lyheak" in usernames_found
    card_heam, kb_heam = format_user_resolver_card(res_heam)
    assert "@lyheak" in card_heam
    assert len(kb_heam.inline_keyboard) >= 2
    print(f"  - Found {len(res_heam['matches'])} similar matching profiles for 'heamlyheak' (including @lyheak): OK")

    res_socheat = await resolve_telegram_user(None, "socheat")
    assert res_socheat["valid"] is True
    assert res_socheat["exact_match"] is not None
    assert len(res_socheat["matches"]) >= 3
    card_soc, kb_soc = format_user_resolver_card(res_socheat)
    assert "Exact Match" in card_soc
    assert "@socheat" in card_soc
    print(f"  - Found exact match and {len(res_socheat['matches'])} total matching accounts for 'socheat': OK")
    print("  [OK] Telegram Profile Resolver & Multi-Match verified!")

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
    test_long_term_memory_service()
    asyncio.run(test_enterprise_architecture())
    asyncio.run(test_briefing_service_async())
    test_file_master_service()
    test_camroad_trip_planner()
    test_code_runner_sandbox()
    test_receipt_scanner_and_budget_export()
    asyncio.run(test_podcast_service_async())
    asyncio.run(test_chord_music_service_async())
    test_two_way_voice_assistant()
    asyncio.run(test_telegram_user_resolver_async())
    print("\n🎉 ALL 25 TEST SUITES PASSED SUCCESSFULLY! ✅")
