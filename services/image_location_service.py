import io
import logging
import asyncio
from typing import Optional, Tuple, Dict, Any
from PIL import Image, ExifTags
from services.weather_service import get_detailed_cambodia_location, fetch_weather
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

VISION_LOCATION_PROMPT = (
    "You are an expert geographical investigator and location identifier specialized in Cambodia and Southeast Asia. "
    "Carefully analyze this image or video to identify where it was taken. "
    "Look for: universities and school campuses (e.g., IFL - Institute of Foreign Languages, RUPP - Royal University of Phnom Penh, "
    "ITC - Institute of Technology of Cambodia, NUM, RULE, Norton, with elevated walkways/bridges, circular driveway, iconic Vann Molyvann architecture), "
    "landmarks, monuments, temple/pagoda architecture, ministries, government buildings, street signs (in Khmer or English), "
    "shop names, phone numbers (with Cambodian area codes like 012, 098, 088, 097), vehicle license plates, "
    "or distinctive natural terrain. "
    "\n\nProvide an informative report in Khmer:\n"
    "📍 **ការវិភាគទីតាំងពីរូបភាព/វីដេអូ (AI Geolocation)**\n"
    "• ឈ្មោះទីតាំង/សំណង់៖ (Identified landmark, university campus, pagoda, building, or road)\n"
    "• ស្រុក/ខណ្ឌ & ខេត្ត/រាជធានី៖ (District/Khan and Province/Capital in Cambodia)\n"
    "• ការពិពណ៌នា & សញ្ញាសម្គាល់៖ (Details of signs, architectural clues, bridge/walkway, or visual clues spotted)\n"
    "• កូអរដោនេប៉ាន់ស្មាន (បើអាច): (Estimated coordinates like 11.5684, 104.8912 or Google Maps search keyword)\n\n"
    "If the media does not have clear recognizable landmarks, describe what is visible "
    "and provide the most likely estimated area or campus."
)

def _to_float(val: Any) -> float:
    """Convert various EXIF rational representations to float."""
    if isinstance(val, (int, float)):
        return float(val)
    if hasattr(val, "numerator") and hasattr(val, "denominator"):
        return float(val.numerator) / float(val.denominator) if val.denominator != 0 else 0.0
    if isinstance(val, (tuple, list)) and len(val) == 2:
        return float(val[0]) / float(val[1]) if val[1] != 0 else 0.0
    try:
        return float(val)
    except Exception:
        return 0.0

def extract_gps_from_image_bytes(image_bytes: bytes) -> Optional[Tuple[float, float]]:
    """
    Extract exact decimal (latitude, longitude) from EXIF GPSInfo metadata in photo bytes.
    Returns None if the image has no EXIF GPS data (e.g. stripped by compression).
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Try modern getexif()
        exif = img.getexif()
        gps = None
        if exif:
            gps = exif.get_ifd(ExifTags.IFD.GPSInfo)
            
        # Fallback to legacy _getexif()
        if not gps:
            raw_exif = getattr(img, "_getexif", lambda: None)()
            if raw_exif and 34853 in raw_exif:
                gps = raw_exif[34853]
                
        if not gps:
            return None

        # GPSLatitudeRef (tag 1), GPSLatitude (tag 2), GPSLongitudeRef (tag 3), GPSLongitude (tag 4)
        lat_ref = gps.get(1, "N")
        lat_raw = gps.get(2)
        lon_ref = gps.get(3, "E")
        lon_raw = gps.get(4)

        if not lat_raw or not lon_raw or len(lat_raw) < 3 or len(lon_raw) < 3:
            return None

        d_lat = _to_float(lat_raw[0])
        m_lat = _to_float(lat_raw[1])
        s_lat = _to_float(lat_raw[2])
        lat = d_lat + (m_lat / 60.0) + (s_lat / 3600.0)
        if str(lat_ref).strip().upper() == "S":
            lat = -lat

        d_lon = _to_float(lon_raw[0])
        m_lon = _to_float(lon_raw[1])
        s_lon = _to_float(lon_raw[2])
        lon = d_lon + (m_lon / 60.0) + (s_lon / 3600.0)
        if str(lon_ref).strip().upper() == "W":
            lon = -lon

        if abs(lat) > 90.0 or abs(lon) > 180.0:
            return None

        return round(lat, 6), round(lon, 6)
    except Exception as e:
        logger.warning(f"Error extracting GPS from image EXIF: {e}")
        return None

def format_photo_gps_message(loc: Dict[str, Any], temp_str: Optional[str] = None) -> str:
    """Format full Cambodian administrative hierarchy for GPS extracted from photo."""
    lat = loc.get("lat")
    lon = loc.get("lon")
    maps_url = f"https://www.google.com/maps?q={lat},{lon}"

    msg = (
        "📍 *បានរកឃើញទីតាំង GPS ពីរូបភាព (Photo Location Metadata)* 🛰️\n\n"
        f"🏡 *ភូមិ / ផ្លូវ:* `{loc.get('village', 'ក្បែរទីតាំងនេះ')}`\n"
        f"🏘️ *សង្កាត់ / ឃុំ:* `{loc.get('commune', 'មិនបានបញ្ជាក់')}`\n"
        f"🏢 *ខណ្ឌ / ស្រុក / ក្រុង:* `{loc.get('district', 'មិនបានបញ្ជាក់')}`\n"
        f"🏛️ *រាជធានី / ខេត្ត:* *{loc.get('province', 'រាជធានីភ្នំពេញ')}*\n\n"
        f"🌐 *កូអរដោនេ GPS:* `{lat}, {lon}`\n"
        f"🗺️ *Google Maps:* [ចុចបើកផែនទីមើលទីតាំង]({maps_url})\n"
    )

    if temp_str:
        msg += f"\n🌤️ *អាកាសធាតុនៅទីតាំងនេះ:* {temp_str}\n"

    msg += (
        "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _ទីតាំងនេះត្រូវបានទាញយកដោយស្វ័យប្រវត្តិចេញពី EXIF GPS Metadata នៃកាមេរ៉ាទូរស័ព្ទដៃរបស់អ្នក!_"
    )
    return msg

async def identify_location_via_vision(image_bytes: bytes, caption: str = "", mime_type: str = "image/jpeg") -> str:
    """Analyze photo or video with Gemini Vision AI to identify landmark/location visually."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "📍 *ការស្វែងរកទីតាំងពីរូបភាព/វីដេអូ៖*\n\n"
            "⚠️ មេឌៀនេះមិនមានទិន្នន័យ EXIF GPS (ដោយសារ Telegram បង្ហាប់ទំហំ)។\n\n"
            "💡 *គន្លឹះដើម្បីទាញយក GPS សុក្រឹត ១០០%៖*\n"
            "សូមផ្ញើរូបភាពដោយជ្រើសរើស **File / Document (Uncompressed)** មកកាន់ Bot ណា៎!"
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    media_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

    instruction = (
        f"{VISION_LOCATION_PROMPT}\n\n"
        f"User caption if any: '{caption}'"
    )

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, [media_part, instruction])
        reply = resp.text
        reply += (
            "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *គន្លឹះ:* ប្រសិនបើចង់ឱ្យ Bot ទាញយកកូអរដោនេ GPS សុក្រឹត ១០០% ពីទូរស័ព្ទដៃ "
            "សូមផ្ញើរូបភាពជាទម្រង់ **File / Document (Uncompressed)** ណា៎!"
        )
        return reply
    except Exception as e:
        logger.error(f"Vision location identification failed: {e}")
        return format_gemini_error(e)

def extract_maps_url_from_vision_text(text: str) -> Optional[str]:
    """Extract a Google Maps coordinate or search URL from Vision AI analysis text."""
    if not text:
        return None
        
    import re
    import urllib.parse

    invalid_words = [
        "មិនច្បាស់", "មិនអាចកំណត់", "មិនស្គាល់", "មិនទាន់", "ពុំទាន់", "ពុំអាច",
        "មិនទាន់អាច", "unknown", "n/a", "none", "unclear", "cannot determine",
        "not clear", "មិនមាន", "គ្មាន"
    ]
    
    # 1. Look for lat, lon coordinates (e.g., 11.5564, 104.9282)
    coords_match = re.search(r"(\d{1,2}\.\d{3,8})[,\s]+(\d{2,3}\.\d{3,8})", text)
    if coords_match:
        lat, lon = coords_match.group(1), coords_match.group(2)
        try:
            f_lat, f_lon = float(lat), float(lon)
            if -90 <= f_lat <= 90 and -180 <= f_lon <= 180:
                return f"https://www.google.com/maps?q={f_lat},{f_lon}"
        except Exception:
            pass

    # 2. Look for identified landmark or building line
    landmark_match = re.search(r"ឈ្មោះទីតាំង(?:/សំណង់)?[\s:៖]+([^\n]+)", text)
    if landmark_match:
        landmark = landmark_match.group(1).strip()
        landmark = re.sub(r"[\*\(\)\[\]]", "", landmark).strip()
        if 3 < len(landmark) < 80 and not any(w in landmark.lower() for w in invalid_words):
            return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(landmark)}"

    # 3. Look for district/province line if specific
    province_match = re.search(r"ខេត្ត/រាជធានី[\s:៖]+([^\n]+)", text)
    if province_match:
        prov = province_match.group(1).strip()
        prov = re.sub(r"[\*\(\)\[\]]", "", prov).strip()
        if 3 < len(prov) < 80 and not any(w in prov.lower() for w in invalid_words):
            return f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(prov)}"

    return None

