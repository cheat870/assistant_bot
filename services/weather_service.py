import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

# Default coordinates: Phnom Penh, Cambodia
DEFAULT_LAT = 11.5564
DEFAULT_LON = 104.9282
DEFAULT_LOCATION_NAME = "រាជធានីភ្នំពេញ"

# WMO Weather interpretation codes
WMO_CODES = {
    0: ("មេឃស្រឡះល្អ", "☀️"),
    1: ("ផ្ទៃមេឃស្រឡះភាគច្រើន", "🌤️"),
    2: ("មានពពកតិចតួច", "⛅"),
    3: ("មានពពកច្រើន", "☁️"),
    45: ("មានអ័ព្ទធ្លាក់", "🌫️"),
    48: ("មានអ័ព្ទកក", "🌫️"),
    51: ("មានភ្លៀងរលឹមស្រិចៗតិចតួច", "🌦️"),
    53: ("មានភ្លៀងរលឹមស្រិចៗមធ្យម", "🌦️"),
    55: ("មានភ្លៀងរលឹមស្រិចៗខ្លាំង", "🌧️"),
    61: ("មានភ្លៀងធ្លាក់តិចៗ", "🌧️"),
    63: ("មានភ្លៀងធ្លាក់មធ្យម", "🌧️"),
    65: ("មានភ្លៀងធ្លាក់ខ្លាំង", "🌧️🌧️"),
    80: ("មានភ្លៀងកន្ត្រាក់តិចតួច", "🌦️"),
    81: ("មានភ្លៀងកន្ត្រាក់មធ្យម", "🌧️"),
    82: ("មានភ្លៀងកន្ត្រាក់ខ្លាំង", "⛈️"),
    95: ("មានផ្គររន្ទះ និងភ្លៀង", "⛈️"),
    96: ("មានផ្គររន្ទះ និងព្រិលធ្លាក់តិច", "⛈️"),
    99: ("មានផ្គររន្ទះ និងខ្យល់ព្យុះខ្លាំង", "⛈️🌪️"),
}

HTTP_HEADERS = {
    "User-Agent": "TelegramAssistantBot/1.0 (https://github.com/cheat870/assistant_bot)",
    "Accept": "application/json"
}

async def reverse_geocode_async(lat: float, lon: float) -> str:
    """Reverse geocode coordinates to location name in Khmer."""
    try:
        url = f"https://api.bigdatacloud.net/data/reverse-geocode-client?latitude={lat}&longitude={lon}&localityLanguage=km"
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                locality = data.get("locality") or ""
                city = data.get("city") or data.get("principalSubdivision") or ""
                country = data.get("countryName") or ""
                
                parts = [p for p in [locality, city] if p]
                if parts:
                    return ", ".join(parts)
                elif country:
                    return f"{country} ({lat:.2f}, {lon:.2f})"
    except Exception as e:
        logger.warning(f"Reverse geocode failed: {e}")
        
    return f"កូអរដោនេ ({lat:.2f}, {lon:.2f})"

async def fetch_weather(lat: float = DEFAULT_LAT, lon: float = DEFAULT_LON) -> Optional[Dict[str, Any]]:
    """Fetch real-time weather and today's forecast from Open-Meteo."""
    url = (
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Asia%2FBangkok"
    )
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=10.0, headers=HTTP_HEADERS) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.json()
                logger.warning(f"Open-Meteo attempt {attempt + 1} returned status {resp.status_code}")
        except Exception as e:
            logger.warning(f"Open-Meteo attempt {attempt + 1} failed: {e}")
            
    return None

def format_weather_message(
    weather_data: Dict[str, Any],
    location_name: str,
    is_daily_alert: bool = False
) -> str:
    """Format comprehensive Khmer weather report with emojis and tips."""
    current = weather_data.get("current", {})
    daily = weather_data.get("daily", {})
    
    temp = current.get("temperature_2m", 0.0)
    feels_like = current.get("apparent_temperature", temp)
    humidity = current.get("relative_humidity_2m", 0)
    wind = current.get("wind_speed_10m", 0.0)
    weather_code = current.get("weather_code", 0)
    
    max_temp = daily.get("temperature_2m_max", [temp])[0]
    min_temp = daily.get("temperature_2m_min", [temp])[0]
    rain_prob = daily.get("precipitation_probability_max", [0])[0]
    
    cond_text, cond_emoji = WMO_CODES.get(weather_code, ("មេឃស្រឡះ", "🌤️"))
    
    # Context-aware daily advice
    if rain_prob >= 60 or weather_code in [61, 63, 65, 80, 81, 82, 95]:
        advice = "⚠️ *ថ្ងៃនេះមានឱកាសភ្លៀងធ្លាក់ខ្ពស់!* សូមកុំភ្លេចយកឆ័ត្រ ឬអាវភ្លៀងតាមខ្លួនពេលចេញទៅក្រៅ។ 🌧️"
    elif max_temp >= 35:
        advice = "☀️ *ថ្ងៃនេះអាកាសធាតុក្តៅខ្លាំង!* សូមពិសាទឹកឱ្យបានច្រើន និងចៀសវាងត្រូវកម្ដៅថ្ងៃយូរ។ 💧"
    elif rain_prob >= 30:
        advice = "⛅ *អាចមានភ្លៀងរលឹមតិចតួចនៅតំបន់ខ្លះ!* សូមត្រៀមខ្លួនជាមុន។"
    else:
        advice = "✨ *អាកាសធាតុអំណោយផលល្អ!* សូមឱ្យថ្ងៃថ្មីនេះពោរពេញដោយថាមពល និងភាពជោគជ័យ! 🌸"
        
    title = (
        "🌅 *[ដំណឹងអាកាសធាតុពេលព្រឹកព្រលឹម - ៥:០០ ព្រឹក]*\n\n"
        "អរុណសួស្តី! នេះជារបាយការណ៍អាកាសធាតុប្រចាំថ្ងៃនៅទីតាំងរបស់អ្នក៖\n"
        if is_daily_alert else
        "🌤️ *[របាយការណ៍អាកាសធាតុបច្ចុប្បន្ន]*\n\n"
    )
    
    msg = (
        f"{title}"
        f"📍 *ទីតាំង:* `{location_name}`\n"
        f"{cond_emoji} *ស្ថានភាពទូទៅ:* *{cond_text}*\n\n"
        f"🌡️ *សីតុណ្ហភាពបច្ចុប្បន្ន:* *{temp:.1f}°C* _(មានអារម្មណ៍ដូច {feels_like:.1f}°C)_\n"
        f"📈 *សីតុណ្ហភាពខ្ពស់បំផុត:* *{max_temp:.1f}°C* | *ទាបបំផុត:* *{min_temp:.1f}°C*\n"
        f"🌧️ *ឱកាសមានភ្លៀង:* *{rain_prob}%*\n"
        f"💧 *កម្រិតសំណើម:* *{humidity}%* | 💨 *ល្បឿនខ្យល់:* *{wind:.1f} km/h*\n\n"
        f"💡 *ដំបូន្មានប្រចាំថ្ងៃ:* {advice}"
    )
    return msg
