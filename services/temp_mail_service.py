import re
import logging
from typing import Dict, Any, List, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

# In-memory mapping of chat_id -> {"email": "...", "login": "...", "domain": "..."}
_USER_MAILBOXES: Dict[int, Dict[str, str]] = {}

def extract_otp_code(text: str) -> Optional[str]:
    """Extract 4 to 8 digit verification code/OTP from subject or message body."""
    if not text:
        return None

    # Priority 1: explicitly following keywords like code, otp, pin, verify
    match = re.search(r'(?:code|otp|pin|verify|verification|លេខកូដ)\D*(\b\d{4,8}\b)', text, re.IGNORECASE)
    if match:
        return match.group(1)

    # Priority 2: standalone 4 to 8 digit number
    matches = re.findall(r'\b\d{4,8}\b', text)
    if matches:
        return matches[0]

    return None

async def generate_temp_email(chat_id: int) -> str:
    """Generate a new free disposable temporary email address using 1secmail API."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get("https://www.1secmail.com/api/v1/?action=genRandomMailbox&count=1")
            if resp.status_code == 200:
                emails = resp.json()
                if emails and isinstance(emails, list):
                    email = emails[0]
                    login, domain = email.split("@")
                    _USER_MAILBOXES[chat_id] = {
                        "email": email,
                        "login": login,
                        "domain": domain
                    }
                    return email
    except Exception as e:
        logger.error(f"Error generating temp email: {e}")

    # Fallback random generator
    import uuid
    rand_id = uuid.uuid4().hex[:8]
    email = f"user_{rand_id}@1secmail.com"
    _USER_MAILBOXES[chat_id] = {
        "email": email,
        "login": f"user_{rand_id}",
        "domain": "1secmail.com"
    }
    return email

def get_current_email(chat_id: int) -> Optional[str]:
    """Retrieve currently active email for user."""
    box = _USER_MAILBOXES.get(chat_id)
    return box.get("email") if box else None

async def check_inbox(chat_id: int) -> Tuple[bool, str, List[Dict[str, Any]]]:
    """Check inbox messages for user's active temporary email."""
    box = _USER_MAILBOXES.get(chat_id)
    if not box:
        email = await generate_temp_email(chat_id)
        box = _USER_MAILBOXES[chat_id]

    login = box["login"]
    domain = box["domain"]
    email = box["email"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url = f"https://www.1secmail.com/api/v1/?action=getMessages&login={login}&domain={domain}"
            resp = await client.get(url)
            if resp.status_code == 200:
                messages = resp.json()
                if isinstance(messages, list):
                    return True, email, messages
    except Exception as e:
        logger.error(f"Error checking inbox for {email}: {e}")

    return False, email, []

async def fetch_message_content(chat_id: int, message_id: int) -> Tuple[bool, Dict[str, Any]]:
    """Read a specific email's content and extract OTP."""
    box = _USER_MAILBOXES.get(chat_id)
    if not box:
        return False, {}

    login = box["login"]
    domain = box["domain"]

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            url = f"https://www.1secmail.com/api/v1/?action=readMessage&login={login}&domain={domain}&id={message_id}"
            resp = await client.get(url)
            if resp.status_code == 200:
                msg_data = resp.json()
                body = msg_data.get("textBody") or msg_data.get("body") or ""
                subject = msg_data.get("subject", "")
                otp = extract_otp_code(f"{subject} {body}")
                msg_data["extracted_otp"] = otp
                return True, msg_data
    except Exception as e:
        logger.error(f"Error fetching message {message_id}: {e}")

    return False, {}
