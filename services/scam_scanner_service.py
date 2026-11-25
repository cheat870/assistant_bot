import re
import json
import logging
import asyncio
import urllib.parse
from typing import Dict, Any, List, Optional

import httpx
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

OFFICIAL_CAMBODIAN_DOMAINS = [
    "ababank.com",
    "wingbank.com.kh",
    "acledabank.com.kh",
    "canadiabank.com.kh",
    "princebank.com.kh",
    "sathapana.com.kh",
    "bakong.nbc.gov.kh",
    "bakong.nbc.org.kh",
    "nbc.gov.kh",
    "telegram.org",
    "t.me",
    "google.com",
    "facebook.com",
    "youtube.com",
    "tiktok.com",
]

SUSPICIOUS_TLDS = {
    ".xyz", ".top", ".club", ".buzz", ".click", ".vip", ".work",
    ".tk", ".ml", ".ga", ".cf", ".gq", ".live", ".space", ".monster"
}

DANGEROUS_EXTENSIONS = {
    ".apk", ".exe", ".scr", ".bat", ".cmd", ".vbs", ".msi", ".jar", ".iso"
}

def extract_urls(text: str) -> List[str]:
    """Extract all web URLs from text or message."""
    url_pattern = r'https?://[^\s<>"]+|www\.[^\s<>"]+'
    matches = re.findall(url_pattern, text)
    cleaned = []
    for m in matches:
        if not m.startswith("http"):
            m = "http://" + m
        cleaned.append(m.rstrip(".,;:!?)'\""))
    return cleaned

async def _check_urlhaus_api(url: str) -> Optional[Dict[str, Any]]:
    """Query free public URLhaus malware threat database."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                "https://urlhaus-api.abuse.ch/v1/url/",
                data={"url": url}
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("query_status") == "ok":
                    return {
                        "is_malware": True,
                        "threat": data.get("threat", "Malware"),
                        "status": data.get("url_status", "online")
                    }
    except Exception as e:
        logger.debug(f"URLhaus check skipped: {e}")
    return None

async def scan_link_or_text(content: str) -> Dict[str, Any]:
    """
    Scan a URL or forwarded text for phishing, banking scams, fake giveaways, and malware.
    Returns structured security evaluation card.
    """
    urls = extract_urls(content)
    primary_url = urls[0] if urls else ""

    reasons: List[str] = []
    risk_score = 0  # 0 to 100

    parsed_domain = ""
    if primary_url:
        try:
            parsed = urllib.parse.urlparse(primary_url)
            parsed_domain = parsed.netloc.lower()
            if ":" in parsed_domain:
                parsed_domain = parsed_domain.split(":")[0]
        except Exception:
            parsed_domain = primary_url

    # Check 1: Direct IP address in URL
    if re.search(r'https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', primary_url):
        risk_score += 40
        reasons.append("🚨 ប្រើប្រាស់លេខ IP ផ្ទាល់ ដោយគ្មានឈ្មោះ Domain ច្បាស់លាស់ (សញ្ញាក្លែងបន្លំ)")

    # Check 2: Cambodian Banking Phishing & Brand Impersonation
    bank_keywords = ["aba", "wing", "acleda", "canadia", "bakong", "truemoney", "prince"]
    for kw in bank_keywords:
        if kw in parsed_domain:
            is_official = any(parsed_domain == off or parsed_domain.endswith("." + off) for off in OFFICIAL_CAMBODIAN_DOMAINS)
            if not is_official:
                risk_score += 80
                reasons.append(f"🚨 ក្លែងបន្លំឈ្មោះធនាគារ {kw.upper()} លើ Domain ក្លែងក្លាយ (`{parsed_domain}`)!")

    # Check 3: Telegram Account Stealing Scams
    lower_text = content.lower()
    telegram_scam_words = [
        "free telegram premium", "telegram gift", "vote for my niece", "vote for my daughter",
        "បោះឆ្នោតឱ្យក្មួយ", "ទទួល telegram premium ឥតគិតថ្លៃ", "login your telegram", "telegram security alert"
    ]
    for scam_w in telegram_scam_words:
        if scam_w in lower_text:
            risk_score += 70
            reasons.append(f"⚠️ មានពាក្យគន្លឹះឆបោកលួចគណនី Telegram: \"{scam_w}\"")

    # Check 4: Dangerous File Download (.APK, .EXE)
    for ext in DANGEROUS_EXTENSIONS:
        if ext in primary_url.lower():
            risk_score += 65
            reasons.append(f"🚨 មានផ្ទុក File ដំឡើងប្រព័ន្ធគ្រោះថ្នាក់ (`{ext}`) ដែលអាចជាមេរោគលួចទិន្នន័យ")

    # Check 5: Suspicious TLD
    for tld in SUSPICIOUS_TLDS:
        if parsed_domain.endswith(tld):
            risk_score += 25
            reasons.append(f"⚠️ ប្រើប្រាស់កន្ទុយ Domain មិនគួរឱ្យទុកចិត្ត (`{tld}`)")

    # Check 6: Check URLhaus Threat Database
    if primary_url:
        urlhaus_res = await _check_urlhaus_api(primary_url)
        if urlhaus_res and urlhaus_res.get("is_malware"):
            risk_score += 90
            reasons.append(f"🚨 ជាប់ឈ្មោះក្នុងបញ្ជីខ្មៅមេរោគអន្តរជាតិ (URLhaus Threat: {urlhaus_res.get('threat')})")

    # Check 7: Gemini AI Security Evaluation
    ai_verdict = ""
    try:
        from google import genai
        from google.genai import types
        from services.ai_service import _call_gemini_api

        client = genai.Client(api_key=GEMINI_API_KEY)
        ai_prompt = (
            "You are a cybersecurity expert analyzing potential phishing scams, fake giveaways, and fraud.\n"
            f"Content to analyze:\n{content[:1000]}\n\n"
            "Task: Evaluate if this message/link is a phishing scam, fraud, virus, or safe.\n"
            "Return JSON strictly in this format:\n"
            "{\n"
            '  "threat_level": "SAFE" or "SUSPICIOUS" or "DANGEROUS",\n'
            '  "score_modifier": -20 to +50,\n'
            '  "explanation": "Clear explanation in Khmer language",\n'
            '  "safety_tip": "Specific actionable advice in Khmer"\n'
            "}"
        )

        response = await asyncio.to_thread(
            _call_gemini_api,
            client,
            ai_prompt,
            "Evaluate scam risk strictly as JSON."
        )

        res_text = response.text.strip() if response and response.text else "{}"
        if res_text.startswith("```"):
            res_text = re.sub(r"^```[a-zA-Z]*\n?", "", res_text)
            res_text = re.sub(r"\n?```$", "", res_text).strip()

        ai_data = json.loads(res_text)
        risk_score += int(ai_data.get("score_modifier", 0))
        ai_verdict = ai_data.get("explanation", "").strip()
        ai_tip = ai_data.get("safety_tip", "កុំចុចលើ Link ឬបញ្ចូលព័ត៌មានសម្ងាត់ឱ្យសោះ!").strip()
    except Exception as e:
        logger.warning(f"Gemini scan analysis failed: {e}")
        ai_verdict = "ប្រព័ន្ធបានវិភាគផ្អែកលើក្បួនពិនិត្យសុវត្ថិភាពបច្ចេកវិទ្យា។"
        ai_tip = "កុំចុចបើក ឬផ្ញើលេខកូដ OTP ទៅកាន់អ្នកដទៃជាដាច់ខាត!"

    # Clamp risk score
    risk_score = max(0, min(100, risk_score))

    # Determine Verdict Card
    if risk_score >= 60:
        status_label = "🔴 គ្រោះថ្នាក់ខ្លាំង - គេហទំព័របោកប្រាស់ (PHISHING / SCAM)"
        verdict_color = "red"
        advice = "⛔ **ហាមចុចបើកជាដាច់ខាត!** គេហទំព័រនេះជាអន្ទាក់ឆបោកដើម្បីលួចគណនី Telegram លួចលុយពីធនាគារ ឬចម្លងមេរោគចូលទូរស័ព្ទ។"
    elif risk_score >= 25:
        status_label = "🟡 គួរឱ្យសង្ស័យ - សូមប្រុងប្រយ័ត្ន (SUSPICIOUS)"
        verdict_color = "yellow"
        advice = "⚠️ **សូមកុំបញ្ចូលលេខសម្ងាត់ ឬ OTP!** គេហទំព័រនេះមានសញ្ញាមិនប្រក្រតីមួយចំនួន សូមផ្ទៀងផ្ទាត់ឱ្យច្បាស់មុននឹងបន្ត។"
    else:
        status_label = "🟢 មានសុវត្ថិភាពខ្ពស់ (LOW RISK / SAFE)"
        verdict_color = "green"
        advice = "✅ មិនមានសញ្ញាឆបោក ឬមេរោគត្រូវបានរកឃើញឡើយ។ គេហទំព័រនេះមានសុវត្ថិភាពធម្មតា។"

    return {
        "url": primary_url or "អត្ថបទសារ (Message Text)",
        "domain": parsed_domain or "គ្មាន Domain",
        "risk_score": risk_score,
        "status_label": status_label,
        "verdict_color": verdict_color,
        "reasons": reasons,
        "ai_verdict": ai_verdict,
        "safety_tip": ai_tip,
        "advice": advice
    }
