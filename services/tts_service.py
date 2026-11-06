import io
import re
import logging
from typing import Optional
from gtts import gTTS

logger = logging.getLogger(__name__)

def is_khmer_text(text: str) -> bool:
    """Check if text contains Khmer Unicode characters."""
    return bool(re.search(r"[\u1780-\u17FF]", text))

def generate_tts_audio(text: str, lang: Optional[str] = None) -> io.BytesIO:
    """
    Generate speech audio (MP3) from text using gTTS.
    Auto-detects Khmer (km) vs English (en) if lang is not specified.
    """
    cleaned_text = text.strip()
    # Strip markdown symbols so TTS doesn't say "asterisk", "hash", etc.
    cleaned_text = re.sub(r"[*_`#~\[\]()>]", "", cleaned_text)
    
    # Limit length to avoid massive audio requests (around 1000 chars)
    if len(cleaned_text) > 1000:
        cleaned_text = cleaned_text[:1000] + "..."

    if not lang:
        lang = "km" if is_khmer_text(cleaned_text) else "en"

    logger.info(f"Generating TTS audio with lang='{lang}' for: {cleaned_text[:40]}...")
    tts = gTTS(text=cleaned_text, lang=lang, slow=False)
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    return audio_fp
