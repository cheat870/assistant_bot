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

# Initial default working model (fastest responding verified candidate)
_cached_working_model: Optional[str] = "gemini-flash-lite-latest"

# Primary candidates in priority order (fastest & most stable first)
DEFAULT_CANDIDATES = [
    "gemini-flash-lite-latest",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.8-flash",
    "gemini-flash-latest",
]

DISALLOWED_SUBSTRINGS = ["live", "realtime", "streaming", "embed", "imagen", "veo", "tts", "aqa"]

def is_valid_generation_model(name: str) -> bool:
    """Check if model name is valid for standard generate_content (excludes streaming/live/embed)."""
    name_lower = name.lower()
    return not any(dis in name_lower for dis in DISALLOWED_SUBSTRINGS)

def is_skippable_gemini_error(err: Exception) -> bool:
    """Check if error is transient, quota-related, obsolete model, or network failure that can be retried on next model."""
    err_msg = str(err).lower()
    return any(k in err_msg for k in [
        "404", "not found", "not available", "not supported", "no longer available",
        "429", "quota", "resource_exhausted", "exceeded your current quota",
        "503", "500", "502", "504", "unavailable", "high demand",
        "400", "invalid_argument", "streaming", "bidirectional", "live-preview", "live",
        "timeout", "timed out", "10060", "10053", "10054", "connection", "aborted", "reset", "socket", "network"
    ])

def _call_gemini_api(client, contents, system_prompt: str = SYSTEM_PROMPT, enable_search: bool = False):
    """Synchronous worker that calls Gemini with automatic dynamic model discovery, optional Google Search Grounding, and fallback."""
    from google.genai import types
    global _cached_working_model

    tools = [types.Tool(google_search=types.GoogleSearch())] if enable_search else None

    # Try cached working model first for maximum speed
    if _cached_working_model:
        try:
            return client.models.generate_content(
                model=_cached_working_model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools
                )
            )
        except Exception as e:
            if is_skippable_gemini_error(e):
                logger.warning(f"Cached model {_cached_working_model} failed ({e}), resetting cache...")
                _cached_working_model = None
            elif enable_search:
                # Fallback without search tools if tools failed
                logger.warning(f"Search grounding failed on {_cached_working_model} ({e}), retrying standard...")
                enable_search = False
                tools = None
            else:
                raise e

    candidates = [m for m in DEFAULT_CANDIDATES if is_valid_generation_model(m)]

    # Discover and append valid models from the user's API key
    try:
        listed = []
        for m in client.models.list():
            name = (m.name or "").replace("models/", "")
            if is_valid_generation_model(name) and "flash" in name.lower():
                listed.append(name)
        # Append any new discovered flash models
        for m in listed:
            if m not in candidates:
                candidates.append(m)
    except Exception as e:
        logger.warning(f"Could not list models: {e}")

    last_err = None
    for model_name in candidates:
        try:
            logger.info(f"Attempting Gemini generation with model: {model_name} (search={enable_search})")
            resp = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools
                )
            )
            # Successfully generated; cache this working model
            _cached_working_model = model_name
            logger.info(f"Successfully connected to Gemini model: {model_name}")
            return resp
        except Exception as e:
            if enable_search:
                # Retry same model without search tool in case tool is disallowed
                try:
                    resp = client.models.generate_content(
                        model=model_name,
                        contents=contents,
                        config=types.GenerateContentConfig(
                            system_instruction=system_prompt
                        )
                    )
                    _cached_working_model = model_name
                    return resp
                except Exception:
                    pass
            if is_skippable_gemini_error(e):
                logger.warning(f"Gemini model {model_name} skipped ({e}), trying next candidate...")
                last_err = e
                continue
            raise e

    if last_err:
        raise last_err

def format_gemini_error(err: Exception) -> str:
    """Format Gemini error into a helpful Khmer user message."""
    err_str = str(err)
    err_lower = err_str.lower()
    if any(k in err_lower for k in ["401", "unauthenticated", "api key not valid", "invalid api key"]):
        return (
            "⚠️ *Google Gemini API Key មិនត្រឹមត្រូវ (401 Unauthenticated)*\n\n"
            "👉 *មូលហេតុ៖* API Key បច្ចុប្បន្នមិនមែនជា Key របស់ Google AI Studio ទេ (Key ត្រឹមត្រូវតែងតែចាប់ផ្តើមដោយ `AIzaSy...`)។\n\n"
            "💡 *ដំណោះស្រាយងាយៗ (ឥតគិតថ្លៃ ១០០%):*\n"
            "1. ចូលទៅកាន់គេហទំព័រ [aistudio.google.com/apikey](https://aistudio.google.com/apikey)\n"
            "2. ចុចយក **'Create API key'** (បង្កើតដោយឥតគិតថ្លៃក្នុងរយៈពេល ១០ វិនាទី)\n"
            "3. ចម្លង (Copy) Key ដែលចាប់ផ្តើមដោយ `AIzaSy...`\n"
            "4. ចូលទៅកាន់ **Render Dashboard** ➔ **Settings** ➔ **Environment Variables** ➔ ប្តូរតម្លៃ `GEMINI_API_KEY` រួច Save!"
        )
    if any(k in err_lower for k in ["429", "quota", "resource_exhausted", "exceeded your current quota"]):
        return (
            "⚠️ *Google Gemini បានកំណត់កម្រិតសំណួរ (Rate Limit 429 / Quota)*\n\n"
            "👉 *មូលហេតុ៖* API Key នេះត្រូវបានបង្កើតនៅក្នុង Project ដែលអស់ Quota ឬសួរលើសពី ១៥ ដងក្នុង ១ នាទី។\n\n"
            "💡 *ដំណោះស្រាយងាយៗ៖*\n"
            "1. **រង់ចាំប្រហែល ១ នាទី** រួចសួរម្តងទៀត (Rate limit នឹង Reset ដោយស្វ័យប្រវត្តិ)។\n"
            "2. ឬចូលទៅ [aistudio.google.com](https://aistudio.google.com) ➔ ចុច **Get API key** ➔ **Create API key in NEW project** (កុំជ្រើសរើស existing project) ➔ យក Key ថ្មីនោះទៅប្តូរក្នុង Render!"
        )
    return f"❌ Gemini Error: {err_str[:160]}"

async def query_ai(prompt: str, chat_id: Optional[int] = None, enable_search: bool = False) -> str:
    """Query Gemini or ChatGPT with optional Google Search Grounding & Long-Term Memory context."""
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            system_prompt = SYSTEM_PROMPT
            if chat_id:
                from services.memory_service import format_memories_for_ai
                mem_block = format_memories_for_ai(chat_id)
                if mem_block:
                    system_prompt += "\n" + mem_block
            
            response = await asyncio.to_thread(_call_gemini_api, client, prompt, system_prompt, enable_search)
            header = "🌐 *Gemini Real-Time Web Search៖*\n\n" if enable_search else "✨ *Gemini ឆ្លើយតប៖*\n\n"
            return f"{header}{response.text}"
        except Exception as e:
            logger.error(f"Gemini query error: {e}")
            return format_gemini_error(e)
            
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
    """Continuous conversation mode with Long-Term Memory and optional Real-Time Search Grounding."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return await query_ai(user_prompt, chat_id=chat_id)

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

        # Inject long-term profile memories into system instruction
        from services.memory_service import format_memories_for_ai
        system_instruction = SYSTEM_PROMPT
        mem_block = format_memories_for_ai(chat_id)
        if mem_block:
            system_instruction += "\n" + mem_block

        # Auto-detect if query asks for real-time / current facts
        realtime_keywords = [
            "who won", "today", "news", "price", "vs", "scores", "weather", "current",
            "gold", "fuel", "exchange", "rate", "breaking",
            "ថ្ងៃនេះ", "ឥឡូវ", "ហាងឆេង", "បាល់ទាត់", "ព័ត៌មាន", "អត្រាប្តូរប្រាក់", "ប្រេង", "មាស", "ប៉ុន្មាន"
        ]
        prompt_lower = user_prompt.lower()
        should_search = any(k in prompt_lower for k in realtime_keywords)
        
        response = await asyncio.to_thread(_call_gemini_api, client, contents, system_instruction, should_search)
        reply_text = response.text or "សូមអភ័យទោស ខ្ញុំមិនអាចឆ្លើយតបបានទេនៅពេលនេះ។"
        
        # Save to chat history memory
        save_chat_message(chat_id, "user", user_prompt)
        save_chat_message(chat_id, "model", reply_text)
        
        return reply_text
        
    except Exception as e:
        logger.error(f"Continuous AI error: {e}")
        return format_gemini_error(e)

async def query_gemini_live_search(user_query: str, chat_id: Optional[int] = None) -> str:
    """Execute live Google Search Grounding with Gemini for real-time web facts."""
    return await query_ai(user_query, chat_id=chat_id, enable_search=True)

async def process_voice_ai(voice_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Understand and respond to Telegram voice message using Gemini."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here") or GEMINI_API_KEY.startswith("AQ."):
        return (
            "🎙️ *បានទទួលសារជាសំឡេង (Voice Message)!*\n\n"
            "⚠️ *Google Gemini API Key មិនទាន់ត្រឹមត្រូវ (401)*\n"
            "💡 ដើម្បីឱ្យ Bot អាចស្តាប់យល់ និងឆ្លើយតបជាភាសាខ្មែរ សូមចូលយក Key ឥតគិតថ្លៃពី [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (Key ចាប់ផ្តើមដោយ `AIzaSy...`) រួចដាក់ក្នុង Render Environment Variables (`GEMINI_API_KEY`)។"
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
        logger.error(f"Voice AI error: {e}")
        return format_gemini_error(e)

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
        logger.error(f"Vision AI error: {e}")
        return format_gemini_error(e)
