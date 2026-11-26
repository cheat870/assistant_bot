import io
import re
import logging
import asyncio
from typing import Dict, Any, Optional
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

CHORD_PROMPT = (
    "You are an expert Cambodian musician, guitar teacher, and music theorist. "
    "A musician is asking for the chords, lyrics, and guitar/piano guide for this song: '{song_name}'. "
    "\n\nProvide an authoritative, beautifully structured music sheet in Khmer formatted in clean Markdown:\n"
    "🎸 **បន្ទះ Chord & ទំនុកច្រៀង (Guitar & Piano Chords)**\n"
    "• បទចម្រៀង៖ (Song title & original artist)\n"
    "• Key មូលដ្ឋាន៖ (e.g., Key C, G, Am, Dm, etc.)\n"
    "• ចង្វាក់ & ល្បឿន (Tempo & Rhythm)៖ (e.g., 4/4 Slow Rock, Ballad, Romvong, Saravan)\n"
    "• ចង្វាក់កេះហ្គីតា (Strumming Pattern)៖ (e.g., ↓ ↓↑ ↑↓↑)\n"
    "• កន្លែងគាប Capo (បើមាន)៖ (e.g., Capo 2nd Fret)\n"
    "• បន្ទះ Chord សំខាន់ៗ៖ [Chord 1] [Chord 2] [Chord 3] [Chord 4]\n\n"
    "📝 **ទំនុកច្រៀងអមជាមួយបន្ទះ Chord (Lyrics with Chords):**\n"
    "Place the chord in brackets [Chord] right above or directly next to the Khmer lyrics syllables, like:\n"
    "```text\n"
    "[C]                  [Em]\n"
    "  អត្ថបទចម្រៀងឃ្លាទី១... \n"
    "[F]                  [G]\n"
    "  អត្ថបទចម្រៀងឃ្លាទី២... \n"
    "```\n\n"
    "🎹 **កំណត់ត្រា Key ព្យាណូ ឬ Hook Intro:** (Notes for intro, e.g. C - E - G - A)\n"
    "💡 **គន្លឹះលេង៖** (One tip on vocal key or feeling for this song)\n"
)

AUDIO_SHAZAM_PROMPT = (
    "You are an expert audio music identifier and Shazam-like acoustic AI. "
    "Listen to this audio recording (which may be recorded from a cafe, radio, or humming) "
    "and identify the song being played. "
    "\n\nProvide the song identification report in Khmer:\n"
    "🎧 **លទ្ធផលសម្គាល់បទចម្រៀង (Song Identification)**\n"
    "• ឈ្មោះបទចម្រៀង៖ (Song Title in Khmer/English)\n"
    "• អ្នកចម្រៀង / តារា៖ (Singer / Artist)\n"
    "• អាល់ប៊ុម / ឆ្នាំចេញផ្សាយ៖ (Album or Year)\n"
    "• ប្រភេទតន្ត្រី៖ (Genre, e.g. R&B, Pop, Ballad, Hip-Hop, Classical)\n"
    "• ឃ្លាទំនុកច្រៀងល្បីក្នុងបទ៖ (Sample lyrics quote)\n\n"
    "If the audio is too short, noisy, or cannot be identified with high confidence, state clearly what "
    "type of melody or rhythm was heard and ask the user to record 5-10 seconds closer to the speaker."
)

async def find_song_chords(song_query: str) -> str:
    """Generate guitar chords, rhythm strumming pattern, and lyrics sheet for any song."""
    song_clean = song_query.strip()
    if not song_clean:
        return "🎸 សូមវាយឈ្មោះបទចម្រៀងដែលចង់រក Chord ណា៎! (ឧ. `/chord ចិត្តអើយ` ឬ `/chord នឹកអូន`)"

    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            f"🎸 *បន្ទះ Chord បទ៖ {song_clean}*\n\n"
            "Key មូលដ្ឋាន៖ Key C Major\n"
            "Chord សំខាន់ៗ៖ [C] [Am] [F] [G]\n"
            "ចង្វាក់៖ 4/4 Ballad (↓ ↓↑ ↑↓↑)\n\n"
            "💡 _សូមកំណត់ GEMINI_API_KEY ដើម្បីទាញយកទំនុកច្រៀង និង Chord ពេញលេញ!_"
        )

    from google import genai
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = CHORD_PROMPT.format(song_name=song_clean)

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, prompt)
        return resp.text
    except Exception as e:
        logger.error(f"Error fetching song chords: {e}")
        return (
            f"🎸 *បន្ទះ Chord បទ៖ {song_clean}*\n\n"
            "Key មូលដ្ឋាន៖ Key C Major (Standard Chord Progression)\n"
            "Chord សំខាន់ៗ៖ [C] [Am] [F] [G] [Em] [Dm]\n"
            "ចង្វាក់ (Rhythm): 4/4 Ballad / Pop (↓ ↓↑ ↑↓↑)\n\n"
            "• Intro: [C] - [Am] - [F] - [G]\n"
            "• Verse: [C] ... [Am] ... [F] ... [G]\n"
            "• Chorus: [F] ... [G] ... [Em] ... [Am]\n\n"
            "💡 _(ទិន្នន័យក្រៅបណ្ដាញ Offline Standard Chord Sheet)_"
        )

async def identify_song_from_audio(audio_bytes: bytes, mime_type: str = "audio/ogg") -> str:
    """Identify playing music from voice note or audio recording using Gemini Multimodal Audio."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "🎧 *ការស្គាល់បទចម្រៀង (Shazam Audio):*\n\n"
            "⚠️ មុខងារស្គាល់បទចម្រៀងត្រូវការកំណត់ GEMINI_API_KEY ជាមុនសិន។"
        )

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, [audio_part, AUDIO_SHAZAM_PROMPT])
        return resp.text
    except Exception as e:
        logger.error(f"Song identification error: {e}")
        return format_gemini_error(e)
