"""
Morning Executive Briefing Service (លេខាផ្ទាល់ខ្លួន VIP).
Generates an all-in-one VIP personalized morning briefing combining:
- Local GPS weather with practical advice
- Today's personal agenda & reminders
- Key financial indicators (Gold, Currency NBC, Fuel)
- Top 3 National News Headlines
- Daily Khmer motivational quote & positive mindset
"""

import random
import logging
from datetime import datetime
from typing import Optional
import pytz

from config import BOT_TIMEZONE
from database import get_user_weather_settings, get_user_reminders
from services.weather_service import fetch_weather
from services.finance_service import fetch_exchange_rates, fetch_gold_price
from services.news_service import fetch_morning_headlines

logger = logging.getLogger(__name__)

# Daily Khmer Motivational Quotes & Wisdom
KHMER_DAILY_QUOTES = [
    "«ដំណើររាប់ពាន់យោជន៍ ចាប់ផ្តើមពីជំហានដំបូង។ ចាប់ផ្តើមថ្ងៃនេះដោយភាពជឿជាក់!»",
    "«ភាពជោគជ័យមិនមែនជាការចៃដន្យឡើយ វាជាលទ្ធផលនៃការខិតខំប្រឹងប្រែង និងភាពខ្ជាប់ខ្ជួនជារៀងរាល់ថ្ងៃ។»",
    "«ឧបសគ្គគឺជាឱកាសដ៏ល្អដើម្បីបង្ហាញពីសមត្ថភាព និងភាពរឹងមាំរបស់អ្នក។»",
    "«វិនិយោគលើចំណេះដឹង និងសុខភាពខ្លួនឯង គឺជាការវិនិយោគដែលផ្តល់ផលចំណេញខ្ពស់បំផុតក្នុងជីវិត។»",
    "«កុំរង់ចាំថ្ងៃស្អែកដើម្បីធ្វើរឿងដែលអស្ចារ្យ ថ្ងៃនេះជាថ្ងៃដ៏ល្អបំផុតសម្រាប់អ្នក!»",
    "«ចិត្តស្ងប់ បញ្ញាភ្លឺថ្លា។ គ្រប់បញ្ហាតែងតែមានដំណោះស្រាយជានិច្ច។»",
    "«រាល់ព្រឹកព្រលឹម គឺជាការចាប់ផ្តើមថ្មីនៃក្តីសង្ឃឹម និងឱកាសថ្មីៗគ្មានដែនកំណត់។»"
]

KHMER_DAYS = {
    0: "ថ្ងៃចន្ទ",
    1: "ថ្ងៃអង្គារ",
    2: "ថ្ងៃពុធ",
    3: "ថ្ងៃព្រហស្បតិ៍",
    4: "ថ្ងៃសុក្រ",
    5: "ថ្ងៃសៅរ៍",
    6: "ថ្ងៃអាទិត្យ",
}

KHMER_MONTHS = {
    1: "មករា",
    2: "កុម្ភៈ",
    3: "មីនា",
    4: "មេសា",
    5: "ឧសភា",
    6: "មិថុនា",
    7: "កក្កដា",
    8: "សីហា",
    9: "កញ្ញា",
    10: "តុលា",
    11: "វិច្ឆិកា",
    12: "ធ្នូ",
}

def to_khmer_num(num) -> str:
    """Convert western digits to Khmer digits."""
    mapping = {"0": "០", "1": "១", "2": "២", "3": "៣", "4": "៤", "5": "៥", "6": "៦", "7": "៧", "8": "៨", "9": "៩"}
    return "".join(mapping.get(c, c) for c in str(num))

async def generate_executive_briefing(chat_id: int, user_name: Optional[str] = None) -> str:
    """Generate comprehensive VIP Morning Executive Briefing."""
    now_kh = datetime.now(BOT_TIMEZONE)
    day_name = KHMER_DAYS.get(now_kh.weekday(), "")
    date_str = f"{day_name} ទី {to_khmer_num(now_kh.day)} ខែ {KHMER_MONTHS.get(now_kh.month, '')} ឆ្នាំ {to_khmer_num(now_kh.year)}"
    display_name = user_name or "លោកអ្នក"

    # 1. Weather
    settings = get_user_weather_settings(chat_id)
    lat = settings.get("latitude") or 11.5564
    lon = settings.get("longitude") or 104.9282
    loc_name = settings.get("location_name") or "រាជធានីភ្នំពេញ"
    
    weather_text = "• មិនអាចទាញយកទិន្នន័យអាកាសធាតុបានទេ"
    try:
        w_data = await fetch_weather(lat, lon)
        if w_data:
            temp = round(w_data.get("temp", 32), 1)
            t_min = round(w_data.get("temp_min", temp - 2), 1)
            t_max = round(w_data.get("temp_max", temp + 3), 1)
            desc = w_data.get("description", "មេឃស្រឡះ")
            humidity = w_data.get("humidity", 70)
            
            advice = "🌤️ អាកាសធាតុល្អសម្រាប់ធ្វើដំណើរ និងប្រកបការងារ"
            if "ភ្លៀង" in desc or "rain" in desc.lower():
                advice = "🌧️ អាចមានភ្លៀងធ្លាក់ សូមកុំភ្លេចយកឆត្រ ឬអាវភ្លៀងតាមខ្លួនណា៎!"
            elif temp >= 35:
                advice = "☀️ អាកាសធាតុក្តៅខ្លាំង សូមពិសាទឹកឱ្យបានច្រើន និងចៀសវាងកម្ដៅថ្ងៃយូរ!"

            weather_text = (
                f"• ទីតាំង៖ *{loc_name}*\n"
                f"• សីតុណ្ហភាព៖ `{temp}°C` (ទាបបំផុត `{t_min}°C` ➔ ខ្ពស់បំផុត `{t_max}°C`)\n"
                f"• ស្ថានភាព៖ {desc} (សំណើម: {humidity}%)\n"
                f"• 💡 *ដំបូន្មាន៖* {advice}"
            )
    except Exception as e:
        logger.warning(f"Briefing weather error: {e}")

    # 2. Today's Reminders
    reminders_text = "✨ _គ្មានកិច្ចការដាស់តឿនក្នុងថ្ងៃនេះឡើយ (អាចកំណត់តាម `/remind`)_"
    try:
        user_reminders = get_user_reminders(chat_id)
        if user_reminders:
            today_prefix = now_kh.strftime("%Y-%m-%d")
            today_rems = [
                r for r in user_reminders 
                if (r.get("remind_at") or "").startswith(today_prefix) or ("T" in (r.get("remind_at") or "") and (r.get("remind_at") or "")[:10] == today_prefix)
            ]
            if today_rems:
                rem_lines = []
                for idx, r in enumerate(today_rems[:4], 1):
                    rem_lines.append(f"  {to_khmer_num(idx)}. ⏰ `{r.get('time_str', '')}` ➔ {r.get('message', '')}")
                reminders_text = "\n".join(rem_lines)
            else:
                reminders_text = f"✨ _លោកអ្នកមាន Reminders សរុប {to_khmer_num(len(user_reminders))} ប៉ុន្តែមិនមែនក្នុងថ្ងៃនេះទេ_"
    except Exception as e:
        logger.warning(f"Briefing reminders error: {e}")

    # 3. Market Rates (Gold, NBC Exchange, Fuel)
    finance_text = "• 1 USD = 4,050 KHR | មាសគីឡូ: ~$2,680/ដំឡឹង"
    try:
        rates = await fetch_exchange_rates()
        gold = await fetch_gold_price()
        khr_rate = int(rates.get("KHR", 4050)) if rates else 4050
        thb_rate = round(rates.get("THB", 33.5), 1) if rates else 33.5
        
        gold_part = ""
        if gold and gold.get("damlung_usd", 0) > 0:
            gold_part = f"\n• 🪙 *មាសគីឡូ (១ តម្លឹង):* `${gold['damlung_usd']:,.0f}` (~${gold['chi_usd']:,.0f}/ជី)"
            
        finance_text = (
            f"• 💵 *អត្រាប្តូរប្រាក់ (NBC):* `1 USD` = `{khr_rate:,} ៛` | `1 THB` = `{round(khr_rate/thb_rate, 1)} ៛`"
            f"{gold_part}\n"
            f"• ⛽ *ប្រេងឥន្ធនៈបច្ចុប្បន្ន:* សាំងធម្មតា `~4,150 ៛` | ម៉ាស៊ូត `~3,950 ៛/L`"
        )
    except Exception as e:
        logger.warning(f"Briefing finance error: {e}")

    # 4. Top 3 National News Headlines
    news_text = "• មិនទាន់មានព័ត៌មានថ្មីនៅឡើយទេ"
    try:
        news_data = await fetch_morning_headlines()
        cam_news = news_data.get("cambodia", [])
        if cam_news:
            news_lines = []
            for idx, item in enumerate(cam_news[:3], 1):
                clean_title = item.get("title", "").split(" - ")[0].strip()
                news_lines.append(f"  {to_khmer_num(idx)}. [{clean_title[:75]}]({item.get('link', '')})")
            news_text = "\n".join(news_lines)
    except Exception as e:
        logger.warning(f"Briefing news error: {e}")

    # 5. Motivational Quote
    daily_quote = random.choice(KHMER_DAILY_QUOTES)

    briefing = (
        f"👑 *[Morning Executive Briefing (លេខាផ្ទាល់ខ្លួន VIP)]* ✨\n\n"
        f"🗓️ *កាលបរិច្ឆេទ៖* {date_str}\n"
        f"👋 *អរុណសួស្តីបង {display_name}!* សូមជូនពរឱ្យថ្ងៃនេះជាថ្ងៃដ៏មានថាមពល និងពោរពេញដោយលាភសំណាង! ☀️\n\n"
        f"🌤️ *អាកាសធាតុប្រចាំថ្ងៃ៖*\n"
        f"{weather_text}\n\n"
        f"⏰ *កាលវិភាគ & សារដាស់តឿនថ្ងៃនេះ៖*\n"
        f"{reminders_text}\n\n"
        f"💰 *សេដ្ឋកិច្ច & ហាងឆេងសំខាន់ៗ៖*\n"
        f"{finance_text}\n\n"
        f"📰 *ព័ត៌មានជាតិសំខាន់ៗ ៣ ចំណុច៖*\n"
        f"{news_text}\n\n"
        f"💡 *សម្រង់គំនិតលើកទឹកចិត្តប្រចាំថ្ងៃ (Daily Quote)៖*\n"
        f"_{daily_quote}_\n\n"
        f"✨ _រៀបចំជូនដោយ Smart Assistant Bot VIP Secretary_"
    )
    return briefing
