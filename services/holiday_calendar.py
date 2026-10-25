from datetime import date, datetime
from typing import List, Dict, Optional
import pytz
from config import BOT_TIMEZONE

# Cambodian Public Holidays Dataset
CAMBODIA_HOLIDAYS = [
    # 2025
    {"date": "2025-01-01", "name_km": "ទិវាចូលឆ្នាំសកល", "name_en": "International New Year's Day", "wishes": "រីករាយទិវាចូលឆ្នាំសកល ឆ្នាំ២០២៥! 🎉"},
    {"date": "2025-01-07", "name_km": "ទិវាជ័យជម្នះលើរបបប្រល័យពូជសាសន៍", "name_en": "Victory Over Genocide Day", "wishes": "រំលឹកទិវាជ័យជម្នះ ៧ មករា 🕊️"},
    {"date": "2025-03-08", "name_km": "ទិវាអន្តរជាតិនារី", "name_en": "International Women's Day", "wishes": "រីករាយទិវាអន្តរជាតិនារី ៨ មីនា! 💐"},
    {"date": "2025-04-14", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី១)", "name_en": "Khmer New Year (Day 1)", "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! សូមទេវតាឆ្នាំថ្មីតាមជួយថែរក្សា! 🌸"},
    {"date": "2025-04-15", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី២)", "name_en": "Khmer New Year (Day 2)", "wishes": "រីករាយថ្ងៃទី២ នៃពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🎊"},
    {"date": "2025-04-16", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី៣)", "name_en": "Khmer New Year (Day 3)", "wishes": "រីករាយថ្ងៃឡើងស័ក នៃពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! ✨"},
    {"date": "2025-05-01", "name_km": "ទិវាពលកម្មអន្តរជាតិ", "name_en": "International Labour Day", "wishes": "រីករាយទិវាពលកម្មអន្តរជាតិ ១ ឧសភា! 🛠️"},
    {"date": "2025-05-11", "name_km": "ពិធីបុណ្យវិសាខបូជា", "name_en": "Visak Bochea Day", "wishes": "រីករាយពិធីបុណ្យវិសាខបូជា! សូមបានសេចក្តីស្ងប់ក្នុងចិត្ត 🪷"},
    {"date": "2025-05-14", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម ព្រះមហាក្សត្រ", "name_en": "King Norodom Sihamoni's Birthday", "wishes": "សូមថ្វាយព្រះពរ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះបរមនាថ នរោត្តម សីហមុនី 👑"},
    {"date": "2025-05-15", "name_km": "ព្រះរាជពិធីច្រត់ព្រះនង្គ័ល", "name_en": "Royal Ploughing Ceremony", "wishes": "រីករាយព្រះរាជពិធីច្រត់ព្រះនង្គ័ល 🌾"},
    {"date": "2025-06-18", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម សម្ដេចព្រះមហាក្សត្រី", "name_en": "Queen Mother's Birthday", "wishes": "សូមថ្វាយព្រះពរ សម្ដេចព្រះមហាក្សត្រី ព្រះវររាជមាតាជាតិខ្មែរ 👑"},
    {"date": "2025-09-21", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃទី១)", "name_en": "Pchum Ben Day 1", "wishes": "រីករាយពិធីបុណ្យភ្ជុំបិណ្ឌ! សូមបានបុណ្យកុសលគ្រប់ៗគ្នា 🙏"},
    {"date": "2025-09-22", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃទី២)", "name_en": "Pchum Ben Day 2", "wishes": "រីករាយពិធីបុណ្យភ្ជុំបិណ្ឌ! សូមបានបុណ្យកុសល និងសេចក្តីសុខ 🙏"},
    {"date": "2025-09-23", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃភ្ជុំធំ)", "name_en": "Pchum Ben Day 3", "wishes": "រីករាយថ្ងៃភ្ជុំធំ! សូមធ្វើដំណើរទៅស្រុកកំណើតប្រកបដោយសុវត្ថិភាព 🙏"},
    {"date": "2025-09-24", "name_km": "ទិវាប្រកាសរដ្ឋធម្មនុញ្ញ", "name_en": "Constitutional Day", "wishes": "រំលឹកទិវាប្រកាសរដ្ឋធម្មនុញ្ញ 🇰🇭"},
    {"date": "2025-10-15", "name_km": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះបរមរតនកោដ្ឋ", "name_en": "Commemoration Day of the King Father", "wishes": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះនរោត្តម សីហនុ 🕊️"},
    {"date": "2025-10-29", "name_km": "ព្រះរាជពិធីគ្រងព្រះបរមរាជសម្បត្តិ ព្រះមហាក្សត្រ", "name_en": "Coronation Day of the King", "wishes": "អបអរសាទរខួបនៃការឡើងគ្រងរាជសម្បត្តិ ព្រះករុណា ព្រះមហាក្សត្រ 👑"},
    {"date": "2025-11-04", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី១)", "name_en": "Water Festival (Day 1)", "wishes": "រីករាយព្រះរាជពិធីបុណ្យអុំទូក បណ្ដែតប្រទីប! 🚣‍♂️🎆"},
    {"date": "2025-11-05", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី២ - សំពះព្រះខែ អកអំបុក)", "name_en": "Water Festival (Day 2)", "wishes": "រីករាយពិធីសំពះព្រះខែ និងអកអំបុក! 🌕✨"},
    {"date": "2025-11-06", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី៣)", "name_en": "Water Festival (Day 3)", "wishes": "រីករាយថ្ងៃបញ្ចប់នៃព្រះរាជពិធីបុណ្យអុំទូក! 🚣‍♂️🎉"},
    {"date": "2025-11-09", "name_km": "ពិធីបុណ្យឯករាជ្យជាតិ", "name_en": "National Independence Day", "wishes": "អបអរសាទរទិវាបុណ្យឯករាជ្យជាតិ ៩ វិច្ឆិកា 🇰🇭"},

    # 2026
    {"date": "2026-01-01", "name_km": "ទិវាចូលឆ្នាំសកល", "name_en": "International New Year's Day", "wishes": "រីករាយទិវាចូលឆ្នាំសកល ឆ្នាំ២០២៦! 🎉"},
    {"date": "2026-01-07", "name_km": "ទិវាជ័យជម្នះលើរបបប្រល័យពូជសាសន៍", "name_en": "Victory Over Genocide Day", "wishes": "រំលឹកទិវាជ័យជម្នះ ៧ មករា 🕊️"},
    {"date": "2026-03-08", "name_km": "ទិវាអន្តរជាតិនារី", "name_en": "International Women's Day", "wishes": "រីករាយទិវាអន្តរជាតិនារី ៨ មីនា! 💐"},
    {"date": "2026-04-14", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី១)", "name_en": "Khmer New Year (Day 1)", "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ ឆ្នាំ២០២៦! 🌸"},
    {"date": "2026-04-15", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី២)", "name_en": "Khmer New Year (Day 2)", "wishes": "រីករាយថ្ងៃទី២ នៃពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🎊"},
    {"date": "2026-04-16", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី៣)", "name_en": "Khmer New Year (Day 3)", "wishes": "រីករាយថ្ងៃឡើងស័ក ពិធីបុណ្យចូលឆ្នាំថ្មី! សូមជួបតែសំណាងល្អ! ✨"},
    {"date": "2026-05-01", "name_km": "ទិវាពលកម្មអន្តរជាតិ", "name_en": "International Labour Day", "wishes": "រីករាយទិវាពលកម្មអន្តរជាតិ ១ ឧសភា! 🛠️"},
    {"date": "2026-05-02", "name_km": "ពិធីបុណ្យវិសាខបូជា", "name_en": "Visak Bochea Day", "wishes": "រីករាយពិធីបុណ្យវិសាខបូជា! 🪷"},
    {"date": "2026-05-06", "name_km": "ព្រះរាជពិធីច្រត់ព្រះនង្គ័ល", "name_en": "Royal Ploughing Ceremony", "wishes": "រីករាយព្រះរាជពិធីច្រត់ព្រះនង្គ័ល 🌾"},
    {"date": "2026-05-14", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម ព្រះមហាក្សត្រ", "name_en": "King Norodom Sihamoni's Birthday", "wishes": "សូមថ្វាយព្រះពរ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះបរមនាថ នរោត្តម សីហមុនី 👑"},
    {"date": "2026-06-18", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម សម្ដេចព្រះមហាក្សត្រី", "name_en": "Queen Mother's Birthday", "wishes": "សូមថ្វាយព្រះពរ សម្ដេចព្រះមហាក្សត្រី ព្រះវររាជមាតាជាតិខ្មែរ 👑"},
    {"date": "2026-09-24", "name_km": "ទិវាប្រកាសរដ្ឋធម្មនុញ្ញ", "name_en": "Constitutional Day", "wishes": "រំលឹកទិវាប្រកាសរដ្ឋធម្មនុញ្ញ 🇰🇭"},
    {"date": "2026-10-10", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃទី១)", "name_en": "Pchum Ben Day 1", "wishes": "រីករាយពិធីបុណ្យភ្ជុំបិណ្ឌ! សូមបានបុណ្យកុសលគ្រប់ៗគ្នា 🙏"},
    {"date": "2026-10-11", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃទី២)", "name_en": "Pchum Ben Day 2", "wishes": "រីករាយពិធីបុណ្យភ្ជុំបិណ្ឌ! សូមបានបុណ្យកុសលគ្រប់ៗគ្នា 🙏"},
    {"date": "2026-10-12", "name_km": "ពិធីបុណ្យភ្ជុំបិណ្ឌ (ថ្ងៃភ្ជុំធំ)", "name_en": "Pchum Ben Day 3", "wishes": "រីករាយថ្ងៃភ្ជុំធំ! សូមធ្វើដំណើរប្រកបដោយសុវត្ថិភាព និងក្តីសុខ 🙏"},
    {"date": "2026-10-15", "name_km": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះបរមរតនកោដ្ឋ", "name_en": "Commemoration Day of the King Father", "wishes": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះនរោត្តម សីហនុ 🕊️"},
    {"date": "2026-10-29", "name_km": "ព្រះរាជពិធីគ្រងព្រះបរមរាជសម្បត្តិ ព្រះមហាក្សត្រ", "name_en": "Coronation Day of the King", "wishes": "អបអរសាទរខួបនៃការឡើងគ្រងរាជសម្បត្តិ ព្រះករុណា ព្រះមហាក្សត្រ 👑"},
    {"date": "2026-11-09", "name_km": "ពិធីបុណ្យឯករាជ្យជាតិ", "name_en": "National Independence Day", "wishes": "អបអរសាទរទិវាបុណ្យឯករាជ្យជាតិ ៩ វិច្ឆិកា 🇰🇭"},
    {"date": "2026-11-23", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី១)", "name_en": "Water Festival (Day 1)", "wishes": "រីករាយព្រះរាជពិធីបុណ្យអុំទូក បណ្ដែតប្រទីប! 🚣‍♂️🎆"},
    {"date": "2026-11-24", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី២ - សំពះព្រះខែ អកអំបុក)", "name_en": "Water Festival (Day 2)", "wishes": "រីករាយពិធីសំពះព្រះខែ និងអកអំបុក! 🌕✨"},
    {"date": "2026-11-25", "name_km": "ព្រះរាជពិធីបុណ្យអុំទូក (ថ្ងៃទី៣)", "name_en": "Water Festival (Day 3)", "wishes": "រីករាយថ្ងៃបញ្ចប់នៃព្រះរាជពិធីបុណ្យអុំទូក! 🚣‍♂️🎉"},

    # 2027
    {"date": "2027-01-01", "name_km": "ទិវាចូលឆ្នាំសកល", "name_en": "International New Year's Day", "wishes": "រីករាយទិវាចូលឆ្នាំសកល ឆ្នាំ២០២៧! 🎉"},
    {"date": "2027-01-07", "name_km": "ទិវាជ័យជម្នះលើរបបប្រល័យពូជសាសន៍", "name_en": "Victory Over Genocide Day", "wishes": "រំលឹកទិវាជ័យជម្នះ ៧ មករា 🕊️"},
    {"date": "2027-03-08", "name_km": "ទិវាអន្តរជាតិនារី", "name_en": "International Women's Day", "wishes": "រីករាយទិវាអន្តរជាតិនារី ៨ មីនា! 💐"},
    {"date": "2027-04-14", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី១)", "name_en": "Khmer New Year (Day 1)", "wishes": "សួស្តីឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ ឆ្នាំ២០២៧! 🌸"},
    {"date": "2027-04-15", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី២)", "name_en": "Khmer New Year (Day 2)", "wishes": "រីករាយថ្ងៃទី២ នៃពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិខ្មែរ! 🎊"},
    {"date": "2027-04-16", "name_km": "ពិធីបុណ្យចូលឆ្នាំថ្មីប្រពៃណីជាតិ (ថ្ងៃទី៣)", "name_en": "Khmer New Year (Day 3)", "wishes": "រីករាយថ្ងៃឡើងស័ក ពិធីបុណ្យចូលឆ្នាំថ្មី! ✨"},
    {"date": "2027-05-01", "name_km": "ទិវាពលកម្មអន្តរជាតិ", "name_en": "International Labour Day", "wishes": "រីករាយទិវាពលកម្មអន្តរជាតិ ១ ឧសភា! 🛠️"},
    {"date": "2027-05-14", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម ព្រះមហាក្សត្រ", "name_en": "King Norodom Sihamoni's Birthday", "wishes": "សូមថ្វាយព្រះពរ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះបរមនាថ នរោត្តម សីហមុនី 👑"},
    {"date": "2027-06-18", "name_km": "ព្រះរាជពិធីបុណ្យចម្រើនព្រះជន្ម សម្ដេចព្រះមហាក្សត្រី", "name_en": "Queen Mother's Birthday", "wishes": "សូមថ្វាយព្រះពរ សម្ដេចព្រះមហាក្សត្រី ព្រះវររាជមាតាជាតិខ្មែរ 👑"},
    {"date": "2027-09-24", "name_km": "ទិវាប្រកាសរដ្ឋធម្មនុញ្ញ", "name_en": "Constitutional Day", "wishes": "រំលឹកទិវាប្រកាសរដ្ឋធម្មនុញ្ញ 🇰🇭"},
    {"date": "2027-10-15", "name_km": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះបរមរតនកោដ្ឋ", "name_en": "Commemoration Day of the King Father", "wishes": "ទិវាគោរពព្រះវិញ្ញាណក្ខន្ធ ព្រះករុណា ព្រះបាទសម្ដេច ព្រះនរោត្តម សីហនុ 🕊️"},
    {"date": "2027-10-29", "name_km": "ព្រះរាជពិធីគ្រងព្រះបរមរាជសម្បត្តិ ព្រះមហាក្សត្រ", "name_en": "Coronation Day of the King", "wishes": "អបអរសាទរខួបនៃការឡើងគ្រងរាជសម្បត្តិ ព្រះករុណា ព្រះមហាក្សត្រ 👑"},
    {"date": "2027-11-09", "name_km": "ពិធីបុណ្យឯករាជ្យជាតិ", "name_en": "National Independence Day", "wishes": "អបអរសាទរទិវាបុណ្យឯករាជ្យជាតិ ៩ វិច្ឆិកា 🇰🇭"},
]

def get_current_cambodia_date() -> date:
    """Return today's date in Cambodia timezone (UTC+7)."""
    return datetime.now(BOT_TIMEZONE).date()

def get_holiday_by_date(check_date: date) -> Optional[Dict]:
    """Check if a specific date is a Cambodian public holiday."""
    date_str = check_date.strftime("%Y-%m-%d")
    for holiday in CAMBODIA_HOLIDAYS:
        if holiday["date"] == date_str:
            return holiday
    return None

def get_today_holiday() -> Optional[Dict]:
    """Check if today is a public holiday in Cambodia."""
    today = get_current_cambodia_date()
    return get_holiday_by_date(today)

def get_upcoming_holidays(limit: int = 5) -> List[Dict]:
    """Get the next upcoming public holidays from today."""
    today = get_current_cambodia_date()
    upcoming = []
    
    for holiday in sorted(CAMBODIA_HOLIDAYS, key=lambda x: x["date"]):
        h_date = datetime.strptime(holiday["date"], "%Y-%m-%d").date()
        if h_date >= today:
            days_left = (h_date - today).days
            item = holiday.copy()
            item["days_left"] = days_left
            upcoming.append(item)
            if len(upcoming) >= limit:
                break
                
    return upcoming

def get_holidays_by_year(year: int) -> List[Dict]:
    """Retrieve all holidays for a given year."""
    year_prefix = f"{year}-"
    return [h for h in CAMBODIA_HOLIDAYS if h["date"].startswith(year_prefix)]

def format_upcoming_message() -> str:
    """Format upcoming holidays with countdown."""
    upcoming = get_upcoming_holidays(limit=6)
    if not upcoming:
        return "📅 មិនមានទិន្នន័យថ្ងៃឈប់សម្រាកបន្ទាប់ទៀតទេ!"
    
    msg_lines = ["🗓️ *បញ្ជីថ្ងៃឈប់សម្រាកបន្ទាប់ (Upcoming Holidays):*\n"]
    for idx, item in enumerate(upcoming, 1):
        days_left = item["days_left"]
        if days_left == 0:
            countdown_text = "🔥 *[ថ្ងៃនេះ! Today]*"
        elif days_left == 1:
            countdown_text = "⏳ *(ថ្ងៃស្អែក Tomorrow)*"
        else:
            countdown_text = f"⏳ *(នៅសល់ {days_left} ថ្ងៃទៀត)*"
            
        msg_lines.append(
            f"{idx}. 🇰🇭 *{item['name_km']}*\n"
            f"   📅 កាលបរិច្ឆេទ: `{item['date']}` {countdown_text}\n"
            f"   🇬🇧 {item['name_en']}\n"
        )
    return "\n".join(msg_lines)

def format_calendar_message(year: int) -> str:
    """Format full calendar of holidays for a specific year."""
    holidays = get_holidays_by_year(year)
    if not holidays:
        return f"📅 មិនមានទិន្នន័យសម្រាប់ឆ្នាំ {year} ឡើយ។"
        
    msg_lines = [f"🇰🇭 *ប្រតិទិនថ្ងៃឈប់សម្រាកបុណ្យជាតិ ឆ្នាំ {year}* 📅\n"]
    for idx, item in enumerate(holidays, 1):
        msg_lines.append(f"{idx:02d}. `{item['date']}`: *{item['name_km']}*")
    
    msg_lines.append(f"\n✨ សរុបថ្ងៃឈប់សម្រាកផ្លូវការ: *{len(holidays)} ថ្ងៃ*")
    return "\n".join(msg_lines)

def format_alert_message(holiday: Dict) -> str:
    """Create early morning 4:00 AM alert announcement message."""
    return (
        "🔔 *[ដំណឹងថ្ងៃឈប់សម្រាកបុណ្យជាតិ!] 🔔*\n\n"
        "🌅 *អរុណសួស្តីនាពេលទៀបភ្លឺ (៤:០០ ព្រឹក)!*\n\n"
        f"ថ្ងៃនេះគឺជាថ្ងៃឈប់សម្រាកផ្លូវការ៖\n"
        f"🇰🇭 *{holiday['name_km']}*\n"
        f"🇬🇧 _{holiday['name_en']}_\n"
        f"📅 កាលបរិច្ឆេទ: `{holiday['date']}`\n\n"
        f"💬 *ពាក្យជូនពរ:* {holiday.get('wishes', 'សូមទទួលបាននូវសេចក្តីសុខ និងសំណាងល្អ!')}\n\n"
        "✨ សូមរីករាយជាមួយថ្ងៃឈប់សម្រាក និងធ្វើដំណើរប្រកបដោយសុវត្ថិភាព! 🌸"
    )
