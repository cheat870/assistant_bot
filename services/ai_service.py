import os
import asyncio
import logging
from typing import Optional, List, Dict
from config import GEMINI_API_KEY, OPENAI_API_KEY
from database import get_chat_history, save_chat_message

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a friendly, highly capable, and intelligent AI Assistant for Cambodian users. "
    "You speak fluent, polite, and natural Khmer (and English when appropriate). "
    "Keep answers concise, helpful, and formatted with emojis."
)

# In-memory cache for the confirmed working model
_cached_working_model: Optional[str] = None

# Free-tier stable models in priority order (1.5-flash has generous free quota)
DEFAULT_CANDIDATES = [
    "gemini-1.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-pro",
]

def _call_gemini_api(client, contents, system_prompt: str = SYSTEM_PROMPT):
    """Synchronous worker that calls Gemini with automatic dynamic model discovery and fallback."""
    from google.genai import types
    global _cached_working_model

    # Try cached working model first for maximum speed
    if _cached_working_model:
        try:
            return client.models.generate_content(
                model=_cached_working_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt
                )
            )
        except Exception as e:
            err_msg = str(e).lower()
            if any(k in err_msg for k in ["404", "not found", "not available", "429", "quota", "resource_exhausted"]):
                logger.warning(f"Cached model {_cached_working_model} failed, resetting cache...")
                _cached_working_model = None
            else:
                raise e

    candidates = list(DEFAULT_CANDIDATES)

    # Check available models for this specific API key
    try:
        listed = []
        for m in client.models.list():
            name = (m.name or "").replace("models/", "")
            if "flash" in name.lower() and "embed" not in name.lower():
                listed.append(name)
        # Prioritize 1.5-flash if available in listed
        if "gemini-1.5-flash" in listed:
            listed.remove("gemini-1.5-flash")
            listed.insert(0, "gemini-1.5-flash")
        for m in reversed(listed):
            if m not in candidates:
                candidates.append(m)
    except Exception as e:
        logger.warning(f"Could not list models: {e}")

    last_err = None
    for model_name in candidates:
        try:
            logger.info(f"Attempting Gemini generation with model: {model_name}")
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt
                )
            )
            # Successfully generated; cache this working model
            _cached_working_model = model_name
            logger.info(f"Successfully connected to Gemini model: {model_name}")
            return resp
        except Exception as e:
            err_msg = str(e).lower()
            is_skippable = any(k in err_msg for k in [
                "404", "not found", "not available", "not supported",
                "429", "quota", "resource_exhausted", "exceeded your current quota"
            ])
            if is_skippable:
                logger.warning(f"Gemini model {model_name} skipped ({e}), trying next candidate...")
                last_err = e
                continue
            raise e

    if last_err:
        raise last_err

async def query_ai(prompt: str) -> str:
    """Query Gemini or ChatGPT for a single question."""
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            response = await asyncio.to_thread(_call_gemini_api, client, prompt)
            return f"✨ *Gemini ឆ្លើយតប៖*\n\n{response.text}"
        except Exception as e:
            err_str = str(e)
            logger.error(f"Gemini error: {err_str}")
            if any(k in err_str.lower() for k in ["429", "quota", "resource_exhausted", "exceeded your current quota"]):
                return (
                    "⚠️ *Google Gemini Quota ពេញបណ្ដោះអាសន្ន (Rate Limit 429)*\n\n"
                    "គណនី Free Tier អនុញ្ញាតឱ្យសួរ ១៥ ដងក្នុង ១ នាទី។\n"
                    "👉 **សូមរង់ចាំប្រហែល ១ នាទី** រួចសាកល្បងសួរម្តងទៀតណា៎! (កម្រិតកំណត់នឹង Reset ដោយស្វ័យប្រវត្តិ)។"
                )
            return f"❌ Gemini Error: {err_str[:150]}"
            
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ]
            )
            return f"🤖 *ChatGPT ឆ្លើយតប៖*\n\n{response.choices[0].message.content}"
        except Exception as e:
            logger.error(f"ChatGPT error: {e}")
            return f"❌ ChatGPT Error: {str(e)[:150]}"
            
    return (
        "💡 *មុខងារ AI ពុំទាន់បានកំណត់ API Key នៅឡើយទេ!*\n\n"
        "ដើម្បីអាចសួរនាំជាមួយ Gemini ឬ ChatGPT សូមដាក់ `GEMINI_API_KEY` ឬ `OPENAI_API_KEY` ទៅក្នុង Render Environment Variables នៃ Bot។"
    )

async def query_continuous_ai(chat_id: int, user_prompt: str) -> str:
    """Continuous conversation mode with memory of recent messages."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return await query_ai(user_prompt)

    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Load recent context history (up to last 8 messages)
        history = get_chat_history(chat_id, limit=8)
        
        contents: List[types.Content] = []
        for h in history:
            role = "user" if h["role"] == "user" else "model"
            contents.append(
                types.Content(
                    role=role,
                    parts=[types.Part.from_text(text=h["content"])]
                )
            )
            
        # Append latest user message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=user_prompt)]
            )
        )
        
        response = await asyncio.to_thread(_call_gemini_api, client, contents)
        reply_text = response.text or "សូមអភ័យទោស ខ្ញុំមិនអាចឆ្លើយតបបានទេនៅពេលនេះ។"
        
        # Save to chat history memory
        save_chat_message(chat_id, "user", user_prompt)
        save_chat_message(chat_id, "model", reply_text)
        
        return reply_text
        
    except Exception as e:
        err_str = str(e)
        logger.error(f"Continuous AI error: {err_str}")
        if any(k in err_str.lower() for k in ["429", "quota", "resource_exhausted"]):
            return (
                "⚠️ *Google Gemini Quota ពេញបណ្ដោះអាសន្ន (Rate Limit 429)*\n\n"
                "👉 សូមរង់ចាំប្រហែល ១ នាទី រួចផ្ញើសារម្តងទៀតណា៎!"
            )
        return f"❌ AI Error: {err_str[:150]}"

async def process_voice_ai(voice_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Understand and respond to Telegram voice message using Gemini."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "🎙️ *បានទទួលសារជាសំឡេង (Voice Message)!*\n\n"
            "💡 ដើម្បីឱ្យ Bot អាចស្តាប់យល់ និងឆ្លើយតបជាភាសាខ្មែរ សូមបន្ថែម `GEMINI_API_KEY` ទៅក្នុង Render Environment Variables នៃ Bot។"
        )
        
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        audio_part = types.Part.from_bytes(data=voice_bytes, mime_type=mime_type)
        instruction = (
            "Listen to this voice message very carefully. "
            "It may be in Khmer or English. "
            "Understand what the user is saying or asking, and reply directly with a helpful, natural, and friendly response in Khmer."
        )
        
        response = await asyncio.to_thread(_call_gemini_api, client, [audio_part, instruction])
        reply_text = response.text or "ខ្ញុំបានស្តាប់សារជាសំឡេងរបស់អ្នកហើយ ប៉ុន្តែពុំមានចម្លើយជាក់លាក់ទេ។"
        return f"🎙️ *Gemini Voice AI ឆ្លើយតប៖*\n\n{reply_text}"
        
    except Exception as e:
        err_str = str(e)
        logger.error(f"Voice AI error: {err_str}")
        if any(k in err_str.lower() for k in ["429", "quota", "resource_exhausted"]):
            return "⚠️ *Google Gemini Quota ពេញបណ្ដោះអាសន្ន* សូមរង់ចាំ ១ នាទី រួចផ្ញើសារសំឡេងម្តងទៀតណា៎!"
        return f"❌ Voice AI Error: {err_str[:150]}"

async def process_vision_ai(image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = "") -> str:
    """Analyze image / OCR / translate / homework solve using Gemini."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "📷 *បានទទួលរូបភាព (Vision AI)!*\n\n"
            "💡 ដើម្បីឱ្យ Bot ជួយអានអក្សរ OCR បកប្រែ ឬដោះស្រាយលំហាត់ សូមបន្ថែម `GEMINI_API_KEY` ទៅក្នុង Render Environment Variables នៃ Bot។"
        )
        
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        user_prompt = caption.strip() if caption else "Analyze this image and describe what you see."
        instruction = (
            f"User note/question: '{user_prompt}'. "
            "Carefully examine this image. "
            "1. If it contains documents, receipts, bills, invoices, or handwritten text, perform OCR to extract key text and summarize/translate it clearly. "
            "2. If it is a math problem, homework question, or test, solve it step-by-step with clear explanations. "
            "3. If it is an object, scene, or diagram, explain what is shown. "
            "Always respond in polite, clear Khmer."
        )
        
        response = await asyncio.to_thread(_call_gemini_api, client, [image_part, instruction])
        reply_text = response.text or "មិនអាចវិភាគរូបភាពបានទេ។"
        return f"📷 *Gemini Vision AI (OCR & វិភាគរូបភាព)៖*\n\n{reply_text}"
        
    except Exception as e:
        err_str = str(e)
        logger.error(f"Vision AI error: {err_str}")
        if any(k in err_str.lower() for k in ["429", "quota", "resource_exhausted"]):
            return "⚠️ *Google Gemini Quota ពេញបណ្ដោះអាសន្ន* សូមរង់ចាំ ១ នាទី រួចផ្ញើរូបភាពម្តងទៀតណា៎!"
        return f"❌ Vision AI Error: {err_str[:150]}"
