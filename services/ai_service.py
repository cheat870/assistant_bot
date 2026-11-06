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

async def query_ai(prompt: str) -> str:
    """Query Gemini or ChatGPT for a single question."""
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT
                )
            )
            return f"✨ *Gemini ឆ្លើយតប៖*\n\n{response.text}"
        except Exception as e:
            logger.error(f"Gemini error: {e}")
            return f"❌ Gemini Error: {str(e)[:150]}"
            
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
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            )
        )
        
        reply_text = response.text or "សូមអភ័យទោស ខ្ញុំមិនអាចឆ្លើយតបបានទេនៅពេលនេះ។"
        
        # Save to chat history memory
        save_chat_message(chat_id, "user", user_prompt)
        save_chat_message(chat_id, "model", reply_text)
        
        return reply_text
        
    except Exception as e:
        logger.error(f"Continuous AI error: {e}")
        return f"❌ AI Error: {str(e)[:150]}"

async def process_voice_ai(voice_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Understand and respond to Telegram voice message using Gemini 2.5 Flash."""
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
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[audio_part, instruction],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            )
        )
        
        reply_text = response.text or "ខ្ញុំបានស្តាប់សារជាសំឡេងរបស់អ្នកហើយ ប៉ុន្តែពុំមានចម្លើយជាក់លាក់ទេ។"
        return f"🎙️ *Gemini Voice AI ឆ្លើយតប៖*\n\n{reply_text}"
        
    except Exception as e:
        logger.error(f"Voice AI error: {e}")
        return f"❌ Voice AI Error: {str(e)[:150]}"

async def process_vision_ai(image_bytes: bytes, mime_type: str = "image/jpeg", caption: str = "") -> str:
    """Analyze image / OCR / translate / homework solve using Gemini 2.5 Flash."""
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
        
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[image_part, instruction],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT
            )
        )
        
        reply_text = response.text or "មិនអាចវិភាគរូបភាពបានទេ។"
        return f"📷 *Gemini Vision AI (OCR & វិភាគរូបភាព)៖*\n\n{reply_text}"
        
    except Exception as e:
        logger.error(f"Vision AI error: {e}")
        return f"❌ Vision AI Error: {str(e)[:150]}"
