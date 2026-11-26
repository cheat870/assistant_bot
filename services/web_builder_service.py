import os
import re
import uuid
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Tuple, Optional
from pathlib import Path

from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
SITES_DIR = BASE_DIR / "data" / "sites"
SITES_DIR.mkdir(parents=True, exist_ok=True)

# External base URL for live website hosting
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://assistant-bot-9ncu.onrender.com/app")
if RENDER_URL:
    DEFAULT_BASE_URL = RENDER_URL
else:
    # Extract scheme & host from WEBAPP_URL
    DEFAULT_BASE_URL = "/".join(WEBAPP_URL.split("/")[:3]) if "://" in WEBAPP_URL else "https://assistant-bot-9ncu.onrender.com"

# Category-specific curated royalty-free images (Unsplash)
CATEGORY_IMAGES = {
    "photo": [
        "https://images.unsplash.com/photo-1542038784456-1ea8e935640e?w=800&q=80",
        "https://images.unsplash.com/photo-1516035069371-29a1b244cc32?w=800&q=80",
        "https://images.unsplash.com/photo-1554080353-a576cf803bda?w=800&q=80",
        "https://images.unsplash.com/photo-1519741497674-611481863552?w=800&q=80"
    ],
    "cafe": [
        "https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=800&q=80",
        "https://images.unsplash.com/photo-1495474472287-4d71bcdd2085?w=800&q=80",
        "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=800&q=80",
        "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=800&q=80"
    ],
    "shop": [
        "https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?w=800&q=80",
        "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=800&q=80",
        "https://images.unsplash.com/photo-1472851294608-062f824d29cc?w=800&q=80",
        "https://images.unsplash.com/photo-1556742049-0a67c5574f73?w=800&q=80"
    ],
    "dev": [
        "https://images.unsplash.com/photo-1498050108023-c5249f4df085?w=800&q=80",
        "https://images.unsplash.com/photo-1555066931-4365d14bab8c?w=800&q=80",
        "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?w=800&q=80",
        "https://images.unsplash.com/photo-1526374965328-7f61d4dc18c5?w=800&q=80"
    ],
    "business": [
        "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?w=800&q=80",
        "https://images.unsplash.com/photo-1497366216548-37526070297c?w=800&q=80",
        "https://images.unsplash.com/photo-1497215728101-856f4ea42174?w=800&q=80",
        "https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?w=800&q=80"
    ]
}

def detect_category(prompt_text: str) -> str:
    p = prompt_text.lower()
    if any(k in p for k in ["ថតរូប", "photo", "camera", "wedding", "studio", "វីដេអូ"]):
        return "photo"
    if any(k in p for k in ["កាហ្វេ", "cafe", "coffee", "ភេសជ្ជៈ", "ម្ហូប", "restaurant", "food", "ហាងបាយ"]):
        return "cafe"
    if any(k in p for k in ["ឡេ", "លក់", "shop", "store", "ស្បែកជើង", "ខោអាវ", "cosmetic", "online shop", "ផលិតផល"]):
        return "shop"
    if any(k in p for k in ["developer", "code", "programmer", "it", "web", "software", "portfolio", "cv"]):
        return "dev"
    return "business"

def synthesize_landing_html(data: Dict[str, Any], category: str = "business") -> str:
    """Build production-grade, responsive, glassmorphic Tailwind CSS landing page in Khmer & English."""
    title = data.get("title", "ទំព័រផ្ទាល់ខ្លួន").strip()
    tagline = data.get("tagline", "សេវាកម្មប្រកបដោយគុណភាព និងទំនុកចិត្តខ្ពស់").strip()
    about = data.get("about", "យើងខ្ញុំផ្តល់ជូននូវសេវាកម្មល្អបំផុត ជាមួយនឹងបទពិសោធន៍វិជ្ជាជីវៈខ្ពស់។").strip()
    services = data.get("services", [])
    if not services:
        services = [
            {"name": "សេវាកម្មកម្រិត VIP", "desc": "គុណភាពស្តង់ដារ និងល្បឿនលឿន", "price": "$$$"},
            {"name": "ការប្រឹក្សាដោយផ្ទាល់", "desc": "ឆ្លើយតបគ្រប់តម្រូវការ ២៤/៧", "price": "Free"},
            {"name": "ការធានាលើគុណភាព", "desc": "ពេញចិត្ត ១០០% ធានាសុវត្ថិភាព", "price": "100%"}
        ]
    
    contacts = data.get("contacts", {})
    phone = contacts.get("phone", "012 345 678").strip()
    telegram = contacts.get("telegram", "").replace("@", "").strip()
    facebook = contacts.get("facebook", "").strip()
    location = contacts.get("location", "រាជធានីភ្នំពេញ, កម្ពុជា").strip()

    images = CATEGORY_IMAGES.get(category, CATEGORY_IMAGES["business"])
    hero_img = images[0]
    gallery_imgs = images[1:]

    # Services HTML cards
    service_cards = ""
    for s in services:
        s_name = s.get("name", "សេវាកម្ម")
        s_desc = s.get("desc", "")
        s_price = s.get("price", "")
        badge = f'<span class="bg-indigo-500/20 text-indigo-300 text-xs px-2.5 py-1 rounded-full font-semibold">{s_price}</span>' if s_price else ''
        service_cards += f"""
        <div class="bg-slate-800/60 backdrop-blur-md border border-slate-700/60 rounded-2xl p-6 hover:border-indigo-500/50 transition duration-300 shadow-xl group">
            <div class="flex items-center justify-between mb-4">
                <div class="w-12 h-12 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-white text-xl shadow-lg group-hover:scale-110 transition duration-300">
                    ✨
                </div>
                {badge}
            </div>
            <h3 class="text-xl font-bold text-white mb-2">{s_name}</h3>
            <p class="text-slate-400 text-sm leading-relaxed">{s_desc}</p>
        </div>
        """

    # Gallery HTML
    gallery_html = ""
    for idx, img_url in enumerate(gallery_imgs):
        gallery_html += f"""
        <div class="overflow-hidden rounded-2xl border border-slate-700/50 group relative aspect-video shadow-lg">
            <img src="{img_url}" alt="Gallery item" class="w-full h-full object-cover group-hover:scale-105 transition duration-500">
            <div class="absolute inset-0 bg-gradient-to-t from-slate-950/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition duration-300 flex items-end p-4">
                <span class="text-white text-xs font-semibold tracking-wider uppercase">ស្នាដៃ / សកម្មភាព #{idx+1}</span>
            </div>
        </div>
        """

    # Contact Buttons
    tg_btn = ""
    if telegram:
        tg_btn = f"""
        <a href="https://t.me/{telegram}" target="_blank" class="flex items-center justify-center gap-2 bg-sky-500 hover:bg-sky-600 text-white font-semibold py-3 px-6 rounded-xl shadow-lg transition duration-200">
            <svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm4.64 6.8c-.15 1.58-.8 5.42-1.13 7.19-.14.75-.42 1-.68 1.03-.58.05-1.02-.38-1.58-.75-.88-.58-1.38-.94-2.23-1.5-.99-.65-.35-1.01.22-1.59.15-.15 2.71-2.48 2.76-2.69a.2.2 0 00-.05-.18c-.06-.05-.14-.03-.21-.02-.09.02-1.49.95-4.22 2.79-.4.27-.76.41-1.08.4-.36-.01-1.04-.2-1.55-.37-.63-.2-1.12-.31-1.08-.66.02-.18.27-.36.74-.55 2.92-1.27 4.86-2.11 5.83-2.51 2.78-1.16 3.35-1.36 3.73-1.36.08 0 .27.02.39.12.1.08.13.19.14.27-.01.06.01.24 0 .38z"/></svg>
            ឆាត Telegram
        </a>
        """

    phone_clean = re.sub(r'[^0-9+]', '', phone)
    phone_btn = f"""
    <a href="tel:{phone_clean}" class="flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold py-3 px-6 rounded-xl shadow-lg transition duration-200">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg>
        តេភ្លាម: {phone}
    </a>
    """

    html = f"""<!DOCTYPE html>
<html lang="km" class="scroll-smooth">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>{title} | គេហទំព័រផ្លូវការ</title>
    <!-- Google Fonts -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700;800&family=Kantumruy+Pro:wght@300;400;600;700&display=swap" rel="stylesheet">
    <!-- Tailwind CSS CDN -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    fontFamily: {{
                        sans: ['Kantumruy Pro', 'Inter', 'sans-serif'],
                    }},
                    colors: {{
                        brand: {{
                            500: '#6366f1',
                            600: '#4f46e5',
                            700: '#4338ca'
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        body {{
            font-family: 'Kantumruy Pro', 'Inter', sans-serif;
            background-color: #0b0f19;
            color: #f1f5f9;
        }}
        .glass {{
            background: rgba(15, 23, 42, 0.75);
            backdrop-filter: blur(12px);
            -webkit-backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
        }}
    </style>
</head>
<body class="min-h-screen flex flex-col selection:bg-indigo-500 selection:text-white">

    <!-- Top Navigation Bar -->
    <header class="sticky top-0 z-50 glass">
        <div class="max-w-5xl mx-auto px-4 py-3.5 flex items-center justify-between">
            <div class="flex items-center gap-2">
                <div class="w-8 h-8 rounded-lg bg-gradient-to-tr from-indigo-500 to-pink-500 flex items-center justify-center font-bold text-white shadow-md">
                    ★
                </div>
                <span class="font-bold text-lg text-white tracking-wide truncate max-w-[200px] sm:max-w-xs">{title}</span>
            </div>
            <div class="flex items-center gap-2">
                <a href="#contact" class="text-xs sm:text-sm font-semibold bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-lg transition shadow-md">
                    ទំនាក់ទំនង
                </a>
            </div>
        </div>
    </header>

    <!-- Hero Section -->
    <section class="relative pt-12 pb-16 px-4 overflow-hidden">
        <div class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-indigo-600/20 rounded-full blur-3xl pointer-events-none"></div>
        <div class="max-w-5xl mx-auto relative z-10 text-center">
            <span class="inline-flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 text-xs sm:text-sm px-3.5 py-1.5 rounded-full font-medium mb-6">
                ✨ គេហទំព័រផ្លូវការ & សេវាកម្មកម្រិតខ្ពស់
            </span>
            <h1 class="text-3xl sm:text-5xl font-extrabold text-white leading-tight mb-4 tracking-tight">
                {title}
            </h1>
            <p class="text-base sm:text-lg text-slate-300 max-w-2xl mx-auto mb-8 font-light leading-relaxed">
                {tagline}
            </p>
            <div class="flex flex-wrap justify-center gap-3.5 mb-10">
                {tg_btn}
                {phone_btn}
            </div>
            <!-- Hero Featured Banner -->
            <div class="rounded-3xl overflow-hidden shadow-2xl border border-slate-700/60 max-w-4xl mx-auto aspect-video max-h-[380px]">
                <img src="{hero_img}" alt="{title}" class="w-full h-full object-cover">
            </div>
        </div>
    </section>

    <!-- About Section -->
    <section class="py-12 px-4 bg-slate-900/50 border-y border-slate-800/80">
        <div class="max-w-4xl mx-auto">
            <div class="glass p-8 sm:p-10 rounded-3xl shadow-xl">
                <h2 class="text-2xl font-bold text-white mb-4 flex items-center gap-2">
                    <span>📖 អំពីយើងខ្ញុំ (About Us)</span>
                </h2>
                <p class="text-slate-300 text-base leading-relaxed mb-6 font-light">
                    {about}
                </p>
                <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 text-center">
                    <div class="p-3 bg-slate-800/40 rounded-xl border border-slate-700/40">
                        <div class="text-indigo-400 font-extrabold text-2xl">100%</div>
                        <div class="text-xs text-slate-400 mt-1">ការទទួលខុសត្រូវ</div>
                    </div>
                    <div class="p-3 bg-slate-800/40 rounded-xl border border-slate-700/40">
                        <div class="text-emerald-400 font-extrabold text-2xl">24/7</div>
                        <div class="text-xs text-slate-400 mt-1">សេវាបំរើអតិថិជន</div>
                    </div>
                    <div class="p-3 bg-slate-800/40 rounded-xl border border-slate-700/40">
                        <div class="text-amber-400 font-extrabold text-2xl">5.0 ★</div>
                        <div class="text-xs text-slate-400 mt-1">ការពេញចិត្តខ្ពស់</div>
                    </div>
                    <div class="p-3 bg-slate-800/40 rounded-xl border border-slate-700/40">
                        <div class="text-purple-400 font-extrabold text-2xl">Fast</div>
                        <div class="text-xs text-slate-400 mt-1">រហ័សទាន់ចិត្ត</div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Services / Products Section -->
    <section class="py-14 px-4 max-w-5xl mx-auto">
        <div class="text-center mb-10">
            <span class="text-indigo-400 text-xs font-bold uppercase tracking-wider">សេវាកម្ម & ផលិតផល</span>
            <h2 class="text-3xl font-extrabold text-white mt-2">អ្វីដែលយើងខ្ញុំផ្តល់ជូន</h2>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
            {service_cards}
        </div>
    </section>

    <!-- Gallery / Showcase Section -->
    <section class="py-12 px-4 bg-slate-900/40">
        <div class="max-w-5xl mx-auto">
            <div class="text-center mb-10">
                <span class="text-indigo-400 text-xs font-bold uppercase tracking-wider">រូបភាព & សកម្មភាព</span>
                <h2 class="text-2xl sm:text-3xl font-extrabold text-white mt-2">កម្រងរូបភាពស្នាដៃ</h2>
            </div>
            <div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {gallery_html}
            </div>
        </div>
    </section>

    <!-- Customer Reviews -->
    <section class="py-14 px-4 max-w-4xl mx-auto">
        <div class="text-center mb-8">
            <h2 class="text-2xl font-bold text-white">មតិអតិថិជន (Testimonials)</h2>
            <div class="flex justify-center text-amber-400 gap-1 mt-2 text-sm">
                ★★★★★ <span class="text-slate-400 text-xs ml-2">(៤.៩/៥ ផ្កាយ)</span>
            </div>
        </div>
        <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div class="p-5 glass rounded-2xl">
                <p class="text-slate-300 text-sm italic mb-3">"សេវាកម្មរហ័សទាន់ចិត្ត បុគ្គលិកមានភាពរួសរាយរាក់ទាក់ និងមានវិជ្ជាជីវៈច្បាស់លាស់។ ពិតជាពេញចិត្តខ្លាំងណាស់!"</p>
                <div class="text-xs font-bold text-indigo-300">— លោក វីរៈ (អតិថិជនប្រចាំ)</div>
            </div>
            <div class="p-5 glass rounded-2xl">
                <p class="text-slate-300 text-sm italic mb-3">"គុណភាពល្អឥតខ្ចោះ លើសពីការរំពឹងទុក។ នឹងបន្តគាំទ្រ និងណែនាំមិត្តភក្តិឱ្យមកប្រើប្រាស់សេវាកម្មនេះបន្ថែមទៀត!"</p>
                <div class="text-xs font-bold text-indigo-300">— កញ្ញា សុភាព (អតិថិជនភ្នំពេញ)</div>
            </div>
        </div>
    </section>

    <!-- Contact & Map Section -->
    <section id="contact" class="py-14 px-4 bg-gradient-to-b from-slate-900 to-indigo-950/60 border-t border-slate-800">
        <div class="max-w-3xl mx-auto text-center glass p-8 sm:p-12 rounded-3xl shadow-2xl">
            <h2 class="text-3xl font-extrabold text-white mb-3">ទំនាក់ទំនងមកយើងខ្ញុំឥឡូវនេះ</h2>
            <p class="text-slate-400 text-sm sm:text-base mb-8 max-w-lg mx-auto font-light">
                យើងខ្ញុំរង់ចាំស្វាគមន៍ និងផ្តល់ព័ត៌មានលម្អិតជូនលោកអ្នកគ្រប់ពេលវេលា!
            </p>
            <div class="flex flex-col sm:flex-row gap-3 justify-center mb-8">
                {tg_btn}
                {phone_btn}
            </div>
            <div class="text-slate-400 text-xs sm:text-sm space-y-2 border-t border-slate-700/60 pt-6">
                <div>📍 <strong>អាសយដ្ឋាន៖</strong> {location}</div>
                <div>🕒 <strong>ម៉ោងធ្វើការ៖</strong> ចន្ទ - អាទិត្យ (8:00 ព្រឹក - 8:00 យប់)</div>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="py-6 px-4 text-center text-xs text-slate-500 border-t border-slate-800/80">
        <p>© 2026 {title}. រក្សាសិទ្ធិគ្រប់យ៉ាង។</p>
        <p class="mt-1 text-[11px] text-slate-600">បង្កើតឡើងដោយស្វ័យប្រវត្តិតាមរយៈ <span class="text-indigo-400 font-medium">Smart Assistant Bot 🚀</span></p>
    </footer>

</body>
</html>"""
    return html

async def generate_landing_page(user_prompt: str, user_id: int) -> Tuple[bool, str, str, str, str]:
    """
    Generate complete, modern, responsive landing page from user prompt.
    Returns: (success, site_id, site_url, html_content, summary_text)
    """
    category = detect_category(user_prompt)
    site_id = f"site_{uuid.uuid4().hex[:8]}"
    site_filename = f"{site_id}.html"
    site_path = SITES_DIR / site_filename

    # Default extraction
    data = {
        "title": "ទំព័រផ្ទាល់ខ្លួន",
        "tagline": "សេវាកម្មប្រកបដោយគុណភាព និងទំនុកចិត្តខ្ពស់",
        "about": user_prompt,
        "services": [],
        "contacts": {
            "phone": "012 345 678",
            "telegram": "",
            "location": "រាជធានីភ្នំពេញ, កម្ពុជា"
        }
    }

    # Extract details using Gemini if available
    if GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here":
        try:
            from google import genai
            from services.ai_service import _call_gemini_api

            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = (
                "You are an expert web designer and copywriter for Cambodian businesses. "
                "Analyze the user's website request and extract structured details for a modern landing page in Khmer.\n\n"
                "User prompt: " + user_prompt + "\n\n"
                "Extract JSON with these fields:\n"
                "- title: Catchy business or portfolio name in Khmer/English (e.g., 'Sokha Photography Studio', 'ហាងកាហ្វេ ធម្មជាតិ')\n"
                "- tagline: Inspiring, professional 1-sentence tagline in Khmer\n"
                "- about: Professional 2-3 sentence company/personal introduction in Khmer\n"
                "- services: Array of 3 items, each with 'name', 'desc', and 'price' (in Khmer/USD)\n"
                "- contacts: Object with 'phone' (e.g. 012 888 999), 'telegram' (username if mentioned), 'location' (city/area in Cambodia)\n\n"
                "Return STRICT JSON only, no markdown backticks, no text outside JSON."
            )

            response = await asyncio.to_thread(
                _call_gemini_api,
                client,
                prompt,
                "Extract website landing page structure as JSON."
            )

            res_text = response.text.strip() if response and response.text else ""
            if res_text.startswith("```"):
                res_text = re.sub(r"^```[a-zA-Z]*\n?", "", res_text)
                res_text = re.sub(r"\n?```$", "", res_text).strip()

            if res_text:
                parsed = json.loads(res_text)
                if isinstance(parsed, dict):
                    data.update(parsed)
        except Exception as e_ai:
            logger.warning(f"Gemini landing page extraction error, using heuristic fallback: {e_ai}")

    # Fallback heuristic extraction if Gemini was offline
    if data.get("title") == "ទំព័រផ្ទាល់ខ្លួន":
        # Extract title from user text
        clean = re.sub(r'/(web|page|site)', '', user_prompt, flags=re.IGNORECASE).strip()
        # Find phone if any
        phone_match = re.search(r'(0\d{1,2}[-\s]?\d{3}[-\s]?\d{3,4})', clean)
        if phone_match:
            data["contacts"]["phone"] = phone_match.group(1)
        # Find telegram if any
        tg_match = re.search(r'@([A-Za-z0-9_]{4,})', clean)
        if tg_match:
            data["contacts"]["telegram"] = tg_match.group(1)

        # Set title based on category
        cat_titles = {
            "photo": "Sokha Photography & Media Studio",
            "cafe": "Cafe Arom & Bakery",
            "shop": "Online Beauty & Fashion Store",
            "dev": "Professional Software Developer Portfolio",
            "business": "Premier Business Services Cambodia"
        }
        data["title"] = cat_titles.get(category, "គេហទំព័រអាជីវកម្មផ្លូវការ")
        data["tagline"] = clean if len(clean) < 80 else clean[:80] + "..."
        data["about"] = clean

    # Render complete HTML
    html_content = synthesize_landing_html(data, category)

    # Save to disk
    site_path.write_text(html_content, encoding="utf-8")
    logger.info(f"Generated landing page: {site_path}")

    # Build live URL
    site_url = f"{DEFAULT_BASE_URL}/site/{site_id}"
    summary = f"🌐 គេហទំព័រ៖ **{data.get('title')}**\n✨ ប្រភេទ៖ {category.capitalize()}\n🔗 Live Link៖ {site_url}"

    return True, site_id, site_url, html_content, summary
