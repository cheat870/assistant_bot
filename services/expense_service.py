import re
from typing import Optional, Dict, Any
from database import add_transaction, get_expense_summary, get_recent_transactions, clear_user_expenses

CATEGORY_KEYWORDS = {
    "អាហារ និងភេសជ្ជៈ 🍜": [
        "បាយ", "ម្ហូប", "កាហ្វេ", "ភេសជ្ជៈ", "នំ", "ញ៉ាំ", "ទឹកដោះគោ", "គុយទាវ", "មី",
        "សាច់", "បន្លែ", "ស្រាបៀរ", "coffee", "food", "drink", "lunch", "dinner", "breakfast", "cafe"
    ],
    "ការធ្វើដំណើរ 🚗": [
        "សាំង", "ម៉ូតូ", "ឡាន", "កង់", "passapp", "grab", "តាក់ស៊ី", "រថយន្ត",
        "fuel", "gas", "ride", "taxi", "bus", "parking", "ផ្ញើម៉ូតូ"
    ],
    "ទិញទំនិញ 🛍️": [
        "ខោ", "អាវ", "ស្បែកជើង", "ទំនិញ", "shopping", "clothes", "phone", "សម្ភារៈ", "ទិញ", "អីវ៉ាន់"
    ],
    "វិក្កយបត្រ & ផ្ទះ 🧾": [
        "ផ្ទះ", "ថ្លៃបន្ទប់", "ថ្លៃទឹក", "ថ្លៃភ្លើង", "wifi", "internet", "bill", "rent", "បង់ថ្លៃ"
    ],
    "សុខភាព & ថែទាំ 💊": [
        "ថ្នាំ", "ពេទ្យ", "ពិនិត្យ", "medicine", "hospital", "clinic", "ហាត់ប្រាណ", "gym"
    ],
    "កម្សាន្ត & ដំណើរកម្សាន្ត 🎬": [
        "កុន", "ភាពយន្ត", "ហ្គេម", "cinema", "game", "party", "ដើរលេង", "ទេសចរណ៍", "hotel"
    ],
    "ប្រាក់បៀវត្សរ៍ & ចំណូល 💰": [
        "ប្រាក់ខែ", "ប្រាក់បៀវត្សរ៍", "salary", "bonus", "ចំណេញ", "profit", "លក់", "បានលុយ"
    ],
}

def detect_category(text: str, default_type: str = "expense") -> str:
    """Classify transaction category based on note text."""
    lower_text = text.lower()
    for cat_name, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower_text for kw in keywords):
            return cat_name
    return "ចំណូលទូទៅ 💵" if default_type == "income" else "ចំណាយទូទៅ 📦"

def parse_expense_text(text: str, force_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Parse spending or income from text.
    Handles:
      - /spend 5$ coffee
      - /spend 20000r ញ៉ាំបាយ
      - /income 500$ salary
      - Natural: ចាយ 20,000៛ ញ៉ាំបាយ
      - Natural: ចំណាយ 15$ សាំងឡាន
      - Natural: រកបាន 50$ លក់ទំនិញ
    """
    raw = text.strip()
    # Strip command prefix if present
    if raw.startswith("/spend"):
        force_type = "expense"
        raw = raw[len("/spend"):].strip()
    elif raw.startswith("/income"):
        force_type = "income"
        raw = raw[len("/income"):].strip()

    # Determine type from natural language keywords
    tx_type = force_type or "expense"
    if not force_type:
        income_match = re.search(r"^(?:ចំណូល|រកបាន|បានប្រាក់|ប្រាក់ខែ|ទទួល)(?:\s+|:)", raw, re.IGNORECASE)
        expense_match = re.search(r"^(?:ចាយ|ចំណាយ|ទិញ|បង់ថ្លៃ)(?:\s+|:)", raw, re.IGNORECASE)
        if income_match:
            tx_type = "income"
            raw = raw[income_match.end():].strip()
        elif expense_match:
            tx_type = "expense"
            raw = raw[expense_match.end():].strip()
        else:
            return None

    # Regex patterns for amounts:
    # Matches: "$5.50 coffee", "5$ coffee", "20,000៛ បាយ", "20000 r lunch", "10 usd snacks"
    pattern = re.compile(
        r"""(?x)
        (?:
            (?P<pre_sym>[\$៛])\s*(?P<amt1>[0-9]+(?:[,.][0-9]+)*)\s*(?P<post_curr1>[a-zA-Z៛]*)
            |
            (?P<amt2>[0-9]+(?:[,.][0-9]+)*)\s*(?P<post_curr2>[\$៛]|usd|khr|r|riel)?
        )
        (?:\s+(?P<note>.*))?$
        """,
        re.IGNORECASE
    )

    m = pattern.search(raw)
    if not m:
        return None

    gd = m.groupdict()
    amt_str = gd.get("amt1") or gd.get("amt2")
    if not amt_str:
        return None

    # Normalize amount
    amt_clean = amt_str.replace(",", "")
    try:
        amount = float(amt_clean)
    except ValueError:
        return None

    if amount <= 0:
        return None

    # Detect currency
    currency = "USD"
    curr_indicators = (
        (gd.get("pre_sym") or "") +
        (gd.get("post_curr1") or "") +
        (gd.get("post_curr2") or "")
    ).lower()

    if "៛" in curr_indicators or "khr" in curr_indicators or "riel" in curr_indicators or curr_indicators == "r":
        currency = "KHR"
    elif "$" in curr_indicators or "usd" in curr_indicators:
        currency = "USD"
    else:
        # Default heuristic in Cambodia: >= 500 without indicator is likely KHR (e.g. 20000), else USD
        if amount >= 500:
            currency = "KHR"
        else:
            currency = "USD"

    note = (gd.get("note") or "").strip()
    if not note:
        note = "មិនបានបញ្ជាក់ចំណាំ"

    category = detect_category(note, default_type=tx_type)

    return {
        "type": tx_type,
        "amount": amount,
        "currency": currency,
        "category": category,
        "note": note
    }

def record_transaction(chat_id: int, tx_data: Dict[str, Any]) -> int:
    """Save transaction to database."""
    return add_transaction(
        chat_id=chat_id,
        tx_type=tx_data["type"],
        amount=tx_data["amount"],
        currency=tx_data["currency"],
        category=tx_data["category"],
        note=tx_data["note"]
    )

def format_record_success(tx_data: Dict[str, Any]) -> str:
    """Format success message after recording a transaction."""
    tx_type = tx_data["type"]
    amt = tx_data["amount"]
    curr = tx_data["currency"]
    cat = tx_data["category"]
    note = tx_data["note"]

    if curr == "KHR":
        formatted_amt = f"{amt:,.0f} ៛"
    else:
        formatted_amt = f"{amt:,.2f} $"

    if tx_type == "income":
        header = "✅ *បានកត់ត្រាចំណូលជោគជ័យ!* 🟢"
        type_str = "ចំណូល (Income)"
    else:
        header = "✅ *បានកត់ត្រាចំណាយជោគជ័យ!* 🔴"
        type_str = "ចំណាយ (Expense)"

    return (
        f"{header}\n\n"
        f"💵 *ចំនួនទឹកប្រាក់:* `{formatted_amt}`\n"
        f"🏷️ *ប្រភេទ:* {type_str}\n"
        f"📂 *ជំពូក:* {cat}\n"
        f"📝 *ចំណាំ:* {note}\n\n"
        f"💡 _វាយ_ `/budget` _ដើម្បីមើលរបាយការណ៍សរុប ឬ_ `/spend` / `/income` _ដើម្បីកត់ត្រាបន្ត។_"
    )

def format_budget_report(chat_id: int, days: int = 30) -> str:
    """Format comprehensive budget report for a user."""
    summary = get_expense_summary(chat_id, days=days)
    recents = get_recent_transactions(chat_id, limit=5)

    exp_usd = summary["expense_usd"]
    exp_khr = summary["expense_khr"]
    inc_usd = summary["income_usd"]
    inc_khr = summary["income_khr"]

    net_usd = inc_usd - exp_usd
    net_khr = inc_khr - exp_khr

    msg = f"📊 *របាយការណ៍ចំណូល-ចំណាយ ({days} ថ្ងៃចុងក្រោយ)*\n"
    msg += f"━━━━━━━━━━━━━━━━━━━━━━\n\n"

    # USD Section
    if inc_usd > 0 or exp_usd > 0:
        msg += f"💵 *គណនីប្រាក់ដុល្លារ (USD):*\n"
        msg += f"  • 🟢 ចំណូលសរុប: `+{inc_usd:,.2f} $`\n"
        msg += f"  • 🔴 ចំណាយសរុប: `-{exp_usd:,.2f} $`\n"
        balance_sign = "+" if net_usd >= 0 else ""
        msg += f"  • ⚖️ សមតុល្យសល់: `*{balance_sign}{net_usd:,.2f} $*`\n\n"

    # KHR Section
    if inc_khr > 0 or exp_khr > 0:
        msg += f"🇰🇭 *គណនីប្រាក់រៀល (KHR):*\n"
        msg += f"  • 🟢 ចំណូលសរុប: `+{inc_khr:,.0f} ៛`\n"
        msg += f"  • 🔴 ចំណាយសរុប: `-{exp_khr:,.0f} ៛`\n"
        balance_sign = "+" if net_khr >= 0 else ""
        msg += f"  • ⚖️ សមតុល្យសល់: `*{balance_sign}{net_khr:,.0f} ៛*`\n\n"

    if inc_usd == 0 and exp_usd == 0 and inc_khr == 0 and exp_khr == 0:
        msg += "📭 _អ្នកពុំទាន់មានកំណត់ត្រាចំណូលចំណាយនៅឡើយទេ។_\n\n"
        msg += "💡 *របៀបចាប់ផ្តើម៖*\n"
        msg += "• `/spend 5$ coffee` ឬ `ចាយ 20,000៛ ញ៉ាំបាយ`\n"
        msg += "• `/income 500$ salary` ឬ `ចំណូល 200$ លក់ទំនិញ`\n"
        return msg

    # Breakdown by category
    cats_usd = summary["categories_usd"]
    cats_khr = summary["categories_khr"]
    if cats_usd or cats_khr:
        msg += f"📑 *ការបែងចែកចំណាយតាមជំពូក (Categories):*\n"
        for cat, amt in cats_usd.items():
            pct = (amt / exp_usd * 100) if exp_usd > 0 else 0
            msg += f"  • {cat}: `{amt:,.2f} $` ({pct:.0f}%)\n"
        for cat, amt in cats_khr.items():
            pct = (amt / exp_khr * 100) if exp_khr > 0 else 0
            msg += f"  • {cat}: `{amt:,.0f} ៛` ({pct:.0f}%)\n"
        msg += "\n"

    # Recent 5 transactions
    if recents:
        msg += f"🕒 *ប្រតិបត្តិការចុងក្រោយ ៥ លើក:*\n"
        for r in recents:
            icon = "🟢 +" if r["type"] == "income" else "🔴 -"
            amt_fmt = f"{r['amount']:,.0f} ៛" if r["currency"] == "KHR" else f"{r['amount']:,.2f} $"
            msg += f"  {icon} `{amt_fmt}` ({r['category']}) - _{r['note']}_\n"
        msg += "\n"

    msg += "━━━━━━━━━━━━━━━━━━━━━━\n"
    msg += "🗑️ _លុបប្រវត្តិទាំងអស់:_ `/clear_expenses`"
    return msg
