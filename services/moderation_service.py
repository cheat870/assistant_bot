import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Casino, betting, spam and phishing patterns commonly targeting Telegram groups in Cambodia
SPAM_PATTERNS = [
    # Gambling & Betting (Khmer & English)
    (r"(?:កាស៊ីណូ|បាការ៉ាត់|ស្លុត|បាញ់ត្រី|ភ្នាល់|ល្បែង|មាន់ជល់)", "ល្បែងស៊ីសង / កាស៊ីណូ (Gambling)"),
    (r"\b(?:casino|baccarat|slot\s*machine|cockfight|bet(?:ting)?|jackpot|poker)\b", "ល្បែងស៊ីសង / Casino"),
    (r"(?:ដាក់ប្រាក់|ដកប្រាក់|ប្រាក់រង្វាន់\s*[0-9]+%|ថែមជូន\s*[0-9]+%|free\s*credit)", "ការផ្សាយពាណិជ្ជកម្មល្បែង (Casino Bonus)"),
    (r"\b(?:18\+|porn|sexy\s*video|ហ្គេមបាញ់ត្រី)\b", "ខ្លឹមសារមិនសមរម្យ (Inappropriate/18+)"),
    # Scams & Malicious Links
    (r"(?:earn\s*\$?\s*[0-9]+|invest\s*\$?\s*[0-9]+|crypto\s*doubler|make\s*money\s*fast)", "ការបោកប្រាស់ហិរញ្ញវត្ថុ (Financial Scam)"),
    (r"t\.me\/(?:joinchat|\+[a-zA-Z0-9_\-]+)", "Link អញ្ជើញចូល Group មិនច្បាស់លាស់ (Invite Link)"),
]

def check_spam(text: str) -> Tuple[bool, str]:
    """
    Check if a message text matches spam, scam or casino advertising patterns.
    Returns (is_spam, reason).
    """
    if not text:
        return False, ""

    text_lower = text.lower()
    for pattern, reason in SPAM_PATTERNS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            logger.info(f"Spam detected: '{reason}' in text: {text[:50]}...")
            return True, reason

    return False, ""
