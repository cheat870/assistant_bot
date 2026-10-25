import os
import asyncio
from typing import Optional
from config import GEMINI_API_KEY, OPENAI_API_KEY

async def query_ai(prompt: str) -> str:
    """Query Gemini or ChatGPT based on available credentials."""
    # Try Gemini first
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = await asyncio.to_thread(
                client.models.generate_content,
                model="gemini-2.5-flash",
                contents=prompt
            )
            return f"✨ *Gemini ឆ្លើយតប៖*\n\n{response.text}"
        except Exception as e:
            return f"❌ Gemini Error: {str(e)[:120]}"
            
    # Try OpenAI if Gemini not set
    if OPENAI_API_KEY and OPENAI_API_KEY != "your_openai_api_key_here":
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=OPENAI_API_KEY)
            response = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}]
            )
            return f"🤖 *ChatGPT ឆ្លើយតប៖*\n\n{response.choices[0].message.content}"
        except Exception as e:
            return f"❌ ChatGPT Error: {str(e)[:120]}"
            
    return (
        "💡 *មុខងារ AI ពុំទាន់បានកំណត់ Key នៅឡើយទេ!*\n\n"
        "ដើម្បីអាចសួរនាំជាមួយ Gemini ឬ ChatGPT សូមដាក់ `GEMINI_API_KEY` ឬ `OPENAI_API_KEY` ទៅក្នុង file `.env` នៃ Bot។"
    )
