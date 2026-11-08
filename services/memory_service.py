"""
Long-Term Vector & Semantic Memory Service for Smart Assistant Bot.
Learns and remembers user preferences (music, spending habits, birthdays, schedules)
and provides contextual personalization to Gemini AI without asking repeatedly.
"""

import re
import logging
from typing import List, Dict, Any, Optional
from database import (
    save_user_memory,
    get_user_memories,
    delete_user_memory,
    clear_user_memories,
)
from services.cache_service import cache_get, cache_set, cache_delete

logger = logging.getLogger(__name__)

# Category Emojis for Display
CATEGORY_EMOJIS = {
    "music": "🎵",
    "budget": "💰",
    "schedule": "📅",
    "personal": "👤",
    "general": "💡",
}

def format_memories_for_ai(chat_id: int) -> str:
    """Format user's active memories into a contextual prompt block for Gemini/GPT."""
    cache_key = f"mem_prompt_{chat_id}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    memories = get_user_memories(chat_id)
    if not memories:
        return ""

    lines = ["\n[User Profile & Long-Term Memories]:"]
    for m in memories[:10]:
        cat = m.get("category", "general")
        emoji = CATEGORY_EMOJIS.get(cat, "•")
        lines.append(f"- {emoji} {cat.capitalize()}: {m.get('content')}")
    lines.append("Use these known user preferences to provide deeply personalized and context-aware responses naturally without repeating them verbatim.")
    prompt_block = "\n".join(lines) + "\n"
    cache_set(cache_key, prompt_block, ttl_seconds=300)
    return prompt_block

def format_user_memory_display(chat_id: int) -> str:
    """Format all stored user memories into an elegant Khmer markdown summary."""
    memories = get_user_memories(chat_id)
    if not memories:
        return (
            "🧠 *ប្រព័ន្ធចងចាំ Long-Term Memory (កម្រិត Master)* ✨\n\n"
            "📭 _មិនទាន់មានទិន្នន័យចងចាំនៅឡើយទេ!_\n\n"
            "💡 *របៀបឱ្យ Bot ចងចាំស្វ័យប្រវត្តិ៖*\n"
            "លោកអ្នកគ្រាន់តែប្រាប់ Bot ក្នុងការជជែកដូចជា៖\n"
            "• `ខ្ញុំចូលចិត្តស្តាប់ចម្រៀង វណ្ណដា`\n"
            "• `ថ្ងៃកំណើតរបស់ខ្ញុំគឺ ថ្ងៃទី ១៥ ខែកក្កដា`\n"
            "• `ខ្ញុំតែងតែផឹកកាហ្វេពេលព្រឹក`\n"
            "• `ខ្ញុំរស់នៅរាជធានីភ្នំពេញ`\n\n"
            "Bot នឹងចងចាំទម្លាប់ទាំងនេះជាស្វ័យប្រវត្ត ដើម្បីផ្តល់ចម្លើយ និងបទចម្រៀងដែលត្រូវចិត្តលោកអ្នកជានិច្ច!"
        )

    text = "🧠 *ប្រព័ន្ធចងចាំ Long-Term Memory របស់អ្នក* ✨\n\n"
    text += f"រកឃើញការចងចាំសរុប៖ *{len(memories)} ចំណុច*\n\n"
    
    by_category = {}
    for m in memories:
        cat = m.get("category", "general")
        by_category.setdefault(cat, []).append(m)

    category_names = {
        "music": "ចំណូលចិត្តតន្ត្រី & ចម្រៀង (Music)",
        "budget": "ទម្លាប់ចំណាយ & ហិរញ្ញវត្ថុ (Budget)",
        "schedule": "កាលបរិច្ឆេទ & ថ្ងៃកំណើត (Schedule)",
        "personal": "ព័ត៌មានផ្ទាល់ខ្លួន (Personal)",
        "general": "ការចងចាំទូទៅ (General)",
    }

    for cat, items in by_category.items():
        cat_title = category_names.get(cat, cat.capitalize())
        emoji = CATEGORY_EMOJIS.get(cat, "•")
        text += f"{emoji} *{cat_title}:*\n"
        for item in items:
            text += f"  • {item['content']}\n"
        text += "\n"

    text += "👉 _វាយ `/forget` ដើម្បីលុបការចងចាំទាំងអស់ឡើងវិញ។_"
    return text

def auto_extract_and_save_facts(chat_id: int, text: str) -> Optional[str]:
    """
    Intelligently mine personal facts, music tastes, and habits from user chat.
    Automatically saves to long-term memory.
    """
    if not text or len(text.strip()) < 5:
        return None

    cleaned = text.strip()
    extracted = None

    # 1. Music preferences
    # Matches: ខ្ញុំចូលចិត្តស្តាប់ចម្រៀង... / ខ្ញុំចូលចិត្តបទ... / តារាចម្រៀងដែលខ្ញុំចូលចិត្ត...
    m = re.search(r"(?:ខ្ញុំ)?(?:ចូលចិត្ត|ស្រឡាញ់)(?:ស្តាប់)?(?:ចម្រៀង|បទ|តន្ត្រី|តារាចម្រៀង)?\s*[:៖]?\s*(.+)", cleaned, re.IGNORECASE)
    if m and not any(k in cleaned.lower() for k in ["/song", "/music", "/play", "តើ", "ស្វែងរក"]):
        val = m.group(1).strip()
        if len(val) > 2 and len(val) < 80:
            content = f"ចូលចិត្តស្តាប់៖ {val}"
            save_user_memory(chat_id, category="music", memory_key="favorite_music", content=content)
            cache_delete(f"mem_prompt_{chat_id}")
            extracted = f"🎵 *បានចងចាំចំណូលចិត្តតន្ត្រី:* {val}"

    # 2. Birthday / Key Date
    # Matches: ថ្ងៃកំណើត(ខ្ញុំ|របស់ខ្ញុំ) គឺ...
    b = re.search(r"(?:ថ្ងៃកំណើត|ថ្ងៃខួបកំណើត)(?:ខ្ញុំ|របស់ខ្ញុំ)?\s*(?:គឺ|នៅ|ធ្លាក់លើ)?\s*[:៖]?\s*(.+)", cleaned, re.IGNORECASE)
    if b:
        val = b.group(1).strip()
        if len(val) > 2 and len(val) < 60:
            content = f"ថ្ងៃកំណើត៖ {val}"
            save_user_memory(chat_id, category="schedule", memory_key="birthday", content=content)
            cache_delete(f"mem_prompt_{chat_id}")
            extracted = f"🎂 *បានចងចាំថ្ងៃកំណើតរបស់អ្នក:* {val}"

    # 3. Budget / Spending Habit
    # Matches: ខ្ញុំតែងតែផឹក/ទិញ/ញ៉ាំ...
    h = re.search(r"(?:ខ្ញុំ)?(?:តែងតែ|ចូលចិត្ត)(?:ផឹក|ញ៉ាំ|ទិញ|ចំណាយលើ)\s*[:៖]?\s*(.+)", cleaned, re.IGNORECASE)
    if h and not extracted:
        val = h.group(1).strip()
        if len(val) > 2 and len(val) < 80:
            content = f"ទម្លាប់ចំណាយ/ការរស់នៅ៖ {val}"
            save_user_memory(chat_id, category="budget", memory_key="spending_habit", content=content)
            cache_delete(f"mem_prompt_{chat_id}")
            extracted = f"☕ *បានចងចាំទម្លាប់របស់អ្នក:* {val}"

    # 4. Personal Info (Name, Location, Job)
    loc = re.search(r"ខ្ញុំ(?:រស់នៅ|ស្នាក់នៅ|នៅ)\s*(?:ឯ|ក្បែរ|ក្នុង)?\s*(.+)", cleaned, re.IGNORECASE)
    if loc and not extracted and not any(k in cleaned.lower() for k in ["/loc", "gps", "ផែនទី"]):
        val = loc.group(1).strip()
        if len(val) > 2 and len(val) < 80:
            content = f"ទីកន្លែងរស់នៅ៖ {val}"
            save_user_memory(chat_id, category="personal", memory_key="living_location", content=content)
            cache_delete(f"mem_prompt_{chat_id}")
            extracted = f"🏡 *បានចងចាំទីតាំងរបស់អ្នក:* {val}"

    return extracted
