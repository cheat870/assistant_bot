import re
import urllib.parse
import logging
from typing import Optional, Tuple
import httpx

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

async def translate_and_expand_prompt(prompt: str) -> str:
    """Use Gemini AI or free Google Translate fallback to enhance and translate Khmer prompts into rich English visual prompts."""
    is_khmer = bool(re.search(r"[\u1780-\u17FF]", prompt))
    
    if GEMINI_API_KEY:
        try:
            from google import genai
            client = genai.Client(api_key=GEMINI_API_KEY)
            sys_instruction = (
                "You are an expert AI image prompt engineer. "
                "Convert the user's idea or description into a rich, vivid, professional text-to-image prompt in English. "
                "If the user input is in Khmer, translate the core concept accurately into English first. "
                "Include artistic style details, lighting, resolution, and aesthetic touches. "
                "Output ONLY the prompt text in English, no quotes, no markdown, no intro/outro."
            )
            response = await client.aio.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"system_instruction": sys_instruction, "temperature": 0.7}
            )
            expanded = response.text.strip() if response and response.text else ""
            if expanded:
                expanded = re.sub(r"[*_`#]", "", expanded)
                return expanded
        except Exception as e:
            logger.warning(f"Failed to expand prompt with Gemini: {e}")

    # Fallback for Khmer text via free Google Translate API
    if is_khmer:
        try:
            url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=en&dt=t&q={urllib.parse.quote(prompt)}"
            async with httpx.AsyncClient(timeout=10.0) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    translated = r.json()[0][0][0]
                    if translated:
                        return f"{translated}, highly detailed, cinematic lighting, 8k resolution, masterpiece"
        except Exception as e_tr:
            logger.warning(f"Free Google translate fallback failed: {e_tr}")

    return prompt

async def generate_ai_image(prompt: str) -> Tuple[Optional[bytes], str, str]:
    """
    Generate high-resolution image using Pollinations AI (FLUX / Turbo / Sana models).
    Returns (image_bytes, original_prompt, expanded_prompt).
    """
    cleaned_prompt = prompt.strip()
    if not cleaned_prompt:
        return None, "", "សូមបញ្ជាក់ព័ត៌មានលម្អិតនៃរូបភាព (Prompt)"

    # Translate and expand visual prompt
    expanded_prompt = await translate_and_expand_prompt(cleaned_prompt)
    logger.info(f"Generating image with prompt: {expanded_prompt[:60]}...")

    # Encode prompt for URL
    encoded = urllib.parse.quote(expanded_prompt[:350])
    import random
    seed = random.randint(1000, 999999)

    candidates = [
        f"https://image.pollinations.ai/prompt/{encoded}?width=1024&height=1024&model=flux&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&model=turbo&seed={seed}&nologo=true",
        f"https://image.pollinations.ai/prompt/{encoded}?width=768&height=768&nologo=true",
    ]

    async with httpx.AsyncClient(timeout=45.0) as client:
        for url in candidates:
            try:
                resp = await client.get(url, follow_redirects=True)
                if resp.status_code == 200 and len(resp.content) > 1000:
                    return resp.content, cleaned_prompt, expanded_prompt
                else:
                    logger.warning(f"Pollinations URL {url[:60]} returned {resp.status_code}")
            except Exception as e:
                logger.warning(f"Pollinations attempt error: {e}")

    return None, cleaned_prompt, expanded_prompt
