import re
import logging
from typing import Dict, Any, Optional
from services.ai_service import query_ai, process_vision_ai

logger = logging.getLogger(__name__)

CONTENT_STYLES = {
    "sales": "បែបលក់ដាច់ & វិជ្ជាជីវៈ (High-Converting Sales Pitch)",
    "engaging": "បែបកំប្លែងទាក់ទាញ & ស៊ីអារម្មណ៍ (Fun & Viral Hook)",
    "short": "បែបខ្លីរហ័ស (Compact & Minimalist)"
}

PROMPT_TEMPLATE = """
អ្នកគឺជាអ្នកជំនាញខាង Social Media Marketing, Copywriting និង TikTok Script Creator ឈានមុខគេនៅកម្ពុជា។
សូមសរសេរមាតិកាផ្សព្វផ្សាយលក់ (Content Marketing) សម្រាប់ប្រធានបទ ឬផលិតផលខាងក្រោមជាភាសាខ្មែរ ដោយបែងចែកជា ៣ ផ្នែកច្បាស់លាស់៖

【ព័ត៌មាន/ប្រធានបទផលិតផល】៖ {topic}
【រចនាប័ទ្ម (Style)】៖ {style_desc}

សូមរៀបចំចម្លើយតាមទម្រង់ម៉ឺងម៉ាត់ដូចខាងក្រោម៖

---FACEBOOK_POST---
[សរសេរសារ Post លក់នៅលើ Facebook / Telegram Channel ដែលមាន៖
- ចំណងជើងទាក់ទាញខ្លាំង (Attention Grabber) ជាមួយ Emoji
- គុណសម្បត្តិពិសេស ៣ ចំណុចធំៗ
- ការផ្តល់ជូនពិសេស ឬបញ្ចុះតម្លៃ
- ព័ត៌មានទំនាក់ទំនង និង Call-to-Action (ឆាតកុម្ម៉ង់ ឬតេ)]

---TIKTOK_SCRIPT---
[សរសេរ Script វីដេអូខ្លី TikTok / Reels រយៈពេល ១៥-២០ វិនាទី៖
- វិនាទី 0-3 (Hook): សម្ដី ឬសកម្មភាពទាក់ចិត្តអ្នកមើលកុំឱ្យ Scroll រំលង
- វិនាទី 4-12 (Demo/Story): បង្ហាញពីរបៀបប្រើ ឬចំណុចលេចធ្លោ
- វិនាទី 13-18 (Call to Action): ណែនាំឱ្យចុច Link ក្នុង Bio ឬឆាតមក]

---HASHTAGS---
[បញ្ជី Hashtag ល្បីៗ ១០-១៥ ទាំងខ្មែរ និងអង់គ្លេស ដូចជា #Cambodia #fyp #khmer #onlinebusiness ...]
"""

def generate_fallback_content(topic: str, style: str = "sales") -> Dict[str, Any]:
    """Generate high-quality structured Khmer content template as fallback."""
    clean_topic = topic.strip() or "ផលិតផលគុណភាពខ្ពស់"
    fb_post = (
        f"🔥 *[ប្រូម៉ូសិនពិសេសប្រចាំខែ - {clean_topic}!]* ✨\n\n"
        f"កំពុងស្វែងរកដំណោះស្រាយល្អបំផុតមែនទេ? ឈប់បារម្ភទៀតទៅ! "
        f"ជាមួយ **{clean_topic}** នឹងជួយសម្រួលដល់ការរស់នៅ និងបំពេញតម្រូវការរបស់អ្នកយ៉ាងល្អឥតខ្ចោះ។\n\n"
        f"🌟 *ចំណុចពិសេសដែលមិនគួររំលង៖*\n"
        f"• ✅ គុណភាពខ្ពស់ ស្តង់ដារត្រឹមត្រូវ ១០០%\n"
        f"• ✅ ងាយស្រួលប្រើប្រាស់ និងសន្សំសំចៃពេលវេលា\n"
        f"• ✅ តម្លៃសមរម្យ ធានាការពេញចិត្តលើសពីការរំពឹងទុក!\n\n"
        f"🎁 *ការផ្តល់ជូនពិសេស៖* បញ្ជាទិញថ្ងៃនេះមានការបញ្ចុះតម្លៃពិសេស និងដឹកជញ្ជូនរហ័សទូទាំង ២៥ ខេត្ត-ក្រុង! 🚚\n\n"
        f"👉 *ទំនាក់ទំនងកុម្ម៉ង់ភ្លាមៗ៖*\n"
        f"• 💬 Inbox មកកាន់ Page ឬទាក់ទងតាម Telegram\n"
        f"• 📞 លេខទូរស័ព្ទ៖ 012 xxx xxx / 098 xxx xxx"
    )

    tiktok_script = (
        f"🎬 *[TikTok & Reels Video Script (15s) - {clean_topic}]*\n\n"
        f"• ⏱️ **0s - 3s (The Hook):**\n"
        f"   (កាន់ {clean_topic} បង្ហាញកាមេរ៉ាជិតៗ)\n"
        f"   🗣️ _«ឈប់សិន! បើអ្នកកំពុងជួបបញ្ហានេះ វីដេអូនេះសម្រាប់អ្នកហើយ!»_\n\n"
        f"• ⏱️ **4s - 10s (Problem & Solution):**\n"
        f"   (បង្ហាញរបៀបប្រើជាក់ស្តែង និងអារម្មណ៍ពេញចិត្ត)\n"
        f"   🗣️ _«តាំងពីបានប្រើ {clean_topic} មក ជីវិតស្រួលជាងមុន មិនបាច់ឈឺក្បាលទៀតទេ!»_\n\n"
        f"• ⏱️ **11s - 15s (Call to Action):**\n"
        f"   (ចង្អុលដៃទៅកាន់ Bio ឬប្រអប់ Comment)\n"
        f"   🗣️ _«ចង់បានតម្លៃប្រូម៉ូសិនមែនទេ? ចុច Link ក្នុង Bio ឬឆាតមកឥឡូវនេះ!»_"
    )

    hashtags = f"#Cambodia #Khmer #fyp #khmertiktok #{clean_topic.replace(' ', '')} #OnlineShopCambodia #Promotion #TrendingKhmer #គុណភាពល្អ"

    return {
        "topic": clean_topic,
        "style": style,
        "fb_post": fb_post,
        "tiktok_script": tiktok_script,
        "hashtags": hashtags
    }

async def generate_social_content(
    topic: str,
    image_bytes: Optional[bytes] = None,
    style: str = "sales"
) -> Dict[str, Any]:
    """
    Generate professional social media sales posts, TikTok scripts, and hashtags.
    Works from text topic or by analyzing product image via Gemini Vision.
    """
    style_desc = CONTENT_STYLES.get(style, CONTENT_STYLES["sales"])
    prompt = PROMPT_TEMPLATE.format(topic=topic or "ផលិតផលក្នុងរូបភាព", style_desc=style_desc)

    raw_response = ""
    try:
        if image_bytes and len(image_bytes) > 200:
            raw_response = await process_vision_ai(image_bytes, caption=prompt)
        else:
            raw_response = await query_ai(prompt)
    except Exception as e:
        logger.warning(f"Error querying AI for social content: {e}")

    if not raw_response or len(raw_response) < 80:
        return generate_fallback_content(topic, style)

    # Parse delimited sections
    fb_part = ""
    tt_part = ""
    tag_part = ""

    if "---FACEBOOK_POST---" in raw_response and "---TIKTOK_SCRIPT---" in raw_response:
        parts = raw_response.split("---FACEBOOK_POST---")[1]
        fb_and_rest = parts.split("---TIKTOK_SCRIPT---")
        fb_part = fb_and_rest[0].strip()

        if "---HASHTAGS---" in fb_and_rest[1]:
            tt_and_tags = fb_and_rest[1].split("---HASHTAGS---")
            tt_part = tt_and_tags[0].strip()
            tag_part = tt_and_tags[1].strip()
        else:
            tt_part = fb_and_rest[1].strip()
    else:
        # Fallback if delimiter was omitted by model
        fb_part = raw_response.strip()
        tt_part = f"🎬 *[TikTok Video Hook]*\n\n🗣️ «តោះមកមើលពី {topic}! ចុច Link ក្នុង Bio ដើម្បីកុម្ម៉ង់ឥឡូវនេះ!»"
        tag_part = "#Cambodia #Khmer #fyp #khmertiktok #OnlineShop"

    if not tag_part:
        tag_part = f"#Cambodia #Khmer #fyp #khmertiktok #{topic.replace(' ', '')} #Promotion"

    return {
        "topic": topic,
        "style": style,
        "fb_post": fb_part or generate_fallback_content(topic, style)["fb_post"],
        "tiktok_script": tt_part or generate_fallback_content(topic, style)["tiktok_script"],
        "hashtags": tag_part
    }

def format_content_card(content_data: Dict[str, Any], view_mode: str = "all") -> str:
    """Format handsome Markdown report card for Telegram display."""
    topic = content_data.get("topic", "ផលិតផល")
    fb_post = content_data.get("fb_post", "")
    tt_script = content_data.get("tiktok_script", "")
    hashtags = content_data.get("hashtags", "")

    if view_mode == "fb":
        return (
            f"🛍️ *[Facebook & Telegram Sales Post]* 📢\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{fb_post}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Hashtags:* {hashtags}\n\n"
            f"💡 _អ្នកអាច Copy អត្ថបទនេះទៅផុសនៅលើ Facebook Page ឬ Telegram បានភ្លាមៗ!_"
        )

    if view_mode == "tiktok":
        return (
            f"🎬 *[TikTok & Reels Video Script (15s)]* 📱\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
            f"{tt_script}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷️ *Hashtags:* {hashtags}\n\n"
            f"💡 _Script នេះរៀបចំឡើងយ៉ាងពិសេសដើម្បីទាក់ទាញអ្នកមើលក្នុងរយៈពេល ៣ វិនាទីដំបូង!_"
        )

    # Combined overview (all)
    return (
        f"🎬 *[AI Content Creator Studio - {topic}]* ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🛍️ *១. គំរូផុសលក់ (Facebook & Telegram Post)៖*\n\n"
        f"{fb_post}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🎬 *២. Script វីដេអូខ្លី (TikTok / Reels 15s)៖*\n\n"
        f"{tt_script}\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🏷️ *Trending Hashtags៖*\n"
        f"`{hashtags}`\n\n"
        f"💡 _ជ្រើសរើសប៊ូតុងខាងក្រោមដើម្បីមើលតែមួយមុខ ឬប្តូររចនាប័ទ្ម ⬇️_"
    )
