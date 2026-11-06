import logging
from typing import Dict, Any, Optional
from services.ai_service import _call_gemini_api
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

SPELLCHECK_PROMPT = (
    "You are an expert Khmer linguist specializing in Khmer orthography and grammar according to "
    "the Samdech Sangharaja Chuon Nath Dictionary (វចនានុក្រមខ្មែរ សម្តេចព្រះសង្ឃរាជ ជួន ណាត) "
    "and modern National Committee for Khmer Language rules.\n\n"
    "When given a text in Khmer:\n"
    "1. Identify every spelling mistake or inaccurate word.\n"
    "2. For each mistake, show: ❌ Wrong word ➔ ✅ Correct word (with a brief Chuon Nath explanation).\n"
    "3. Provide the full corrected and polished text (អត្ថបទកែលម្អរួច).\n"
    "4. Format the response clearly with emojis and sections in Khmer.\n"
    "If the text has no errors, praise the user and provide tips or elegant synonym alternatives."
)

TRANSLATE_PROMPT = (
    "You are an expert bilingual Khmer <-> English professional translator and linguist.\n"
    "When given text:\n"
    "1. Detect the source language (Khmer or English).\n"
    "2. If English ➔ Translate into natural, elegant, and grammatically accurate Khmer.\n"
    "3. If Khmer ➔ Translate into natural, native, and clear English.\n"
    "4. Provide phonetic/pronunciation tips for key difficult words.\n"
    "5. Explain key vocabulary terms used in the translation.\n"
    "6. Format nicely with emojis."
)

async def check_khmer_spelling(text: str) -> str:
    """Analyze Khmer text for spelling and grammar errors using Chuon Nath rules."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "💡 *មុខងារពិនិត្យអក្ខរាវិរុទ្ធតម្រូវឱ្យមាន API Key!*\n\n"
            "សូមកំណត់ `GEMINI_API_KEY` នៅក្នុង Environment Variables។"
        )
    
    import asyncio
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"សូមជួយពិនិត្យអក្ខរាវិរុទ្ធ និងវេយ្យាករណ៍ខ្មែរលើអត្ថបទខាងក្រោម៖\n\n「 {text} 」"
    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, prompt, SPELLCHECK_PROMPT)
        return resp.text
    except Exception as e:
        logger.error(f"Khmer spellcheck error: {e}")
        from services.ai_service import format_gemini_error
        return format_gemini_error(e)

async def translate_pro(text: str) -> str:
    """Translate text between English and Khmer with linguistic details."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "💡 *មុខងារបកប្រែ Pro តម្រូវឱ្យមាន API Key!*\n\n"
            "សូមកំណត់ `GEMINI_API_KEY` នៅក្នុង Environment Variables។"
        )

    import asyncio
    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"សូមបកប្រែអត្ថបទខាងក្រោម (English ⬄ Khmer)៖\n\n「 {text} 」"
    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, prompt, TRANSLATE_PROMPT)
        return resp.text
    except Exception as e:
        logger.error(f"Translation error: {e}")
        from services.ai_service import format_gemini_error
        return format_gemini_error(e)
