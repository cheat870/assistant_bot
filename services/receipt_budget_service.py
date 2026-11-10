import io
import re
import json
import math
import zipfile
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, List, Tuple
from PIL import Image, ImageDraw, ImageFont

from database import add_transaction, get_expense_summary, DB_PATH
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

RECEIPT_PARSER_PROMPT = (
    "You are an expert Cambodian financial auditor and receipt scanner. "
    "Analyze this image of a receipt, restaurant bill, supermarket invoice (AEON, Lucky, Chip Mong, etc.), "
    "or mobile banking payment slip (ABA Pay, Bakong, Wing, ACLEDA, TrueMoney, etc.). "
    "\n\nExtract the financial transaction details and output ONLY a valid JSON object matching this schema:\n"
    "{\n"
    '  "is_receipt": true,\n'
    '  "merchant": "Shop or Merchant Name in Khmer or English",\n'
    '  "amount": 12.50,\n'
    '  "currency": "USD",\n'
    '  "category": "អាហារ និងភេសជ្ជៈ 🍜",\n'
    '  "date": "2026-11-10",\n'
    '  "items": ["Item 1", "Item 2"],\n'
    '  "summary_km": "Brief 1-line description in Khmer"\n'
    "}\n\n"
    "Rules:\n"
    "1. amount must be a clean numeric float (e.g. 12.50 or 50000.0). If both USD and KHR appear, prefer the paid total.\n"
    "2. currency must be either 'USD' or 'KHR'. (If symbol is $ or USD -> 'USD'; if ៛, R, or KHR -> 'KHR').\n"
    "3. category must be one of: 'អាហារ និងភេសជ្ជៈ 🍜', 'ការធ្វើដំណើរ 🚗', 'ទិញទំនិញ 🛍️', 'វិក្កយបត្រ & ផ្ទះ 🧾', 'សុខភាព & ថែទាំ 💊', 'កម្សាន្ត & ដំណើរកម្សាន្ត 🎬', 'ចំណាយទូទៅ 📦'.\n"
    "4. If the image is clearly NOT a receipt or payment slip, set is_receipt to false.\n"
    "Do not include markdown code block ticks ```json or extra prose outside the JSON."
)

async def scan_receipt_image(image_bytes: bytes, caption: str = "") -> Dict[str, Any]:
    """Scan receipt/bill/slip using Gemini Vision AI and extract structured transaction data."""
    fallback = {
        "is_receipt": False,
        "merchant": "មិនស្គាល់",
        "amount": 0.0,
        "currency": "USD",
        "category": "ចំណាយទូទៅ 📦",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "items": [],
        "summary_km": "មិនអាចស្កេនវិក្កយបត្របានទេ"
    }

    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return fallback

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    img_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    instruction = f"{RECEIPT_PARSER_PROMPT}\nUser note: '{caption}'"

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, [img_part, instruction])
        raw_text = resp.text.strip()
        
        # Clean potential markdown fences
        if "```" in raw_text:
            match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.DOTALL)
            if match:
                raw_text = match.group(1).strip()
            else:
                raw_text = re.sub(r"^```[a-z]*\n|```$", "", raw_text, flags=re.MULTILINE).strip()

        data = json.loads(raw_text)
        # Validate required fields
        data["amount"] = float(data.get("amount", 0.0))
        data["currency"] = "KHR" if str(data.get("currency", "")).upper() in ["KHR", "៛", "RIEL", "RIELS"] else "USD"
        data["is_receipt"] = bool(data.get("is_receipt", True))
        return data
    except Exception as e:
        logger.warning(f"Receipt parsing error: {e}")
        # Try regex fallback if AI returned non-JSON
        try:
            amt_match = re.search(r"(\$|៛)?\s*([0-9]+(?:\.[0-9]{1,2})?)\s*(\$|USD|KHR|៛)?", caption or "")
            if amt_match:
                val = float(amt_match.group(2))
                is_khr = "៛" in (caption or "") or "khr" in (caption or "").lower()
                return {
                    "is_receipt": True,
                    "merchant": "វិក្កយបត្រទូទៅ",
                    "amount": val,
                    "currency": "KHR" if is_khr else "USD",
                    "category": "ចំណាយទូទៅ 📦",
                    "date": datetime.now().strftime("%Y-%m-%d"),
                    "items": [],
                    "summary_km": "វិក្កយបត្រស្កេន"
                }
        except Exception:
            pass
        return fallback

def record_receipt_transaction(chat_id: int, receipt: Dict[str, Any]) -> str:
    """Record parsed receipt into database expenses and return formatted confirmation message."""
    amt = receipt.get("amount", 0.0)
    curr = receipt.get("currency", "USD")
    cat = receipt.get("category", "ចំណាយទូទៅ 📦")
    merchant = receipt.get("merchant", "វិក្កយបត្រ")
    items = receipt.get("items", [])

    note = f"វិក្កយបត្រ: {merchant}"
    if items:
        note += f" ({', '.join(items[:3])})"

    # Record into database
    add_transaction(chat_id, "expense", amt, curr, cat, note)

    curr_sym = "$" if curr == "USD" else "៛"
    amt_str = f"{amt:,.2f} {curr_sym}" if curr == "USD" else f"{int(amt):,} {curr_sym}"

    msg = (
        "🧾 *បានស្កេន និងកត់ត្រាវិក្កយបត្រដោយជោគជ័យ!* ✨\n\n"
        f"🏪 *ហាង / ស្ថាប័ន:* *{merchant}*\n"
        f"💵 *ចំនួនទឹកប្រាក់:* *{amt_str}*\n"
        f"🏷️ *ប្រភេទចំណាយ:* `{cat}`\n"
        f"📅 *កាលបរិច្ឆេទ:* `{receipt.get('date', datetime.now().strftime('%Y-%m-%d'))}`\n"
    )

    if items:
        msg += f"\n🛒 *មុខទំនិញដែលបានទិញ៖*\n"
        for item in items[:5]:
            msg += f"  • {item}\n"

    msg += (
        "\n━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 _ទិន្នន័យនេះត្រូវបានកត់ចូលប្រព័ន្ធចំណូល-ចំណាយ (`/budget`) របស់អ្នកដោយស្វ័យប្រវត្តិ!_"
    )
    return msg

# Distinct aesthetic color palette for donut chart
CHART_PALETTE = [
    (255, 99, 132),   # Pink Coral
    (54, 162, 235),   # Bright Sky Blue
    (255, 206, 86),   # Sun Yellow
    (75, 192, 192),   # Teal Mint
    (153, 102, 255),  # Violet Purple
    (255, 159, 64),   # Bright Orange
    (46, 204, 113),   # Emerald Green
    (149, 165, 166),  # Muted Gray
]

def generate_budget_pie_chart(chat_id: int, days: int = 30) -> Optional[bytes]:
    """Generate high-resolution, modern Donut/Pie Chart image of user expenses with Pillow."""
    summary = get_expense_summary(chat_id, days=days)
    cats_usd = summary.get("categories_usd", {})
    cats_khr = summary.get("categories_khr", {})

    # Combine expenses normalized to USD for chart (approx rate: 4100 KHR = 1 USD)
    combined: Dict[str, float] = {}
    for cat, val in cats_usd.items():
        combined[cat] = combined.get(cat, 0.0) + val
    for cat, val in cats_khr.items():
        combined[cat] = combined.get(cat, 0.0) + (val / 4100.0)

    # Filter out zeros
    slices = [(cat, amt) for cat, amt in combined.items() if amt > 0]
    if not slices:
        return None

    # Sort descending
    slices.sort(key=lambda x: x[1], reverse=True)
    total_val = sum(s[1] for s in slices)
    if total_val <= 0:
        return None

    # Image dimensions
    W, H = 840, 500
    img = Image.new("RGBA", (W, H), (24, 28, 40, 255))
    draw = ImageDraw.Draw(img)

    # Header Bar
    draw.rectangle([(0, 0), (W, 70)], fill=(32, 38, 56, 255))
    title_text = "📊 របាយការណ៍ចំណាយតាមប្រភេទ (Expense Breakdown - 30 ថ្ងៃ)"
    draw.text((25, 22), title_text, fill=(255, 255, 255), font=None)

    # Donut Chart Coordinates
    cx, cy = 240, 285
    r_outer = 160
    r_inner = 85

    start_deg = -90.0
    for idx, (cat, amt) in enumerate(slices):
        pct = amt / total_val
        sweep = pct * 360.0
        color = CHART_PALETTE[idx % len(CHART_PALETTE)]

        # Draw outer slice
        draw.pieslice(
            [(cx - r_outer, cy - r_outer), (cx + r_outer, cy + r_outer)],
            start=start_deg,
            end=start_deg + sweep,
            fill=color,
            outline=(24, 28, 40, 255),
            width=2
        )
        start_deg += sweep

    # Draw inner cutout circle (Donut hole)
    draw.ellipse(
        [(cx - r_inner, cy - r_inner), (cx + r_inner, cy + r_inner)],
        fill=(24, 28, 40, 255),
        outline=(38, 46, 68, 255),
        width=3
    )

    # Center Text in Donut
    draw.text((cx - 30, cy - 25), "សរុប (Total)", fill=(160, 175, 200), font=None)
    tot_str = f"${total_val:,.1f}"
    draw.text((cx - 28, cy - 5), tot_str, fill=(255, 255, 255), font=None)

    # Legend on Right Side
    lx, ly = 460, 110
    row_height = 45

    for idx, (cat, amt) in enumerate(slices[:8]):
        pct = (amt / total_val) * 100.0
        color = CHART_PALETTE[idx % len(CHART_PALETTE)]
        y_pos = ly + idx * row_height

        # Color square
        draw.rectangle([(lx, y_pos), (lx + 20, y_pos + 20)], fill=color)

        # Label & Amount
        cat_short = cat[:25]
        label = f"{cat_short}"
        val_str = f"${amt:,.2f} ({pct:.1f}%)"
        draw.text((lx + 32, y_pos), label, fill=(240, 240, 245), font=None)
        draw.text((lx + 32, y_pos + 18), val_str, fill=(160, 175, 200), font=None)

    # Watermark Footer
    draw.text((25, H - 30), "⚡ បង្កើតដោយ Telegram Assistant Bot | Smart Personal Accountant", fill=(100, 115, 140), font=None)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

def generate_budget_excel(chat_id: int) -> bytes:
    """
    Generate an authentic, complete OpenXML Excel spreadsheet (.xlsx) of user transaction history.
    Implemented in pure Python using zipfile for maximum reliability.
    """
    import sqlite3
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, type, amount, currency, category, note, created_at
        FROM expenses
        WHERE chat_id = ?
        ORDER BY id ASC
    """, (chat_id,))
    rows = cursor.fetchall()
    conn.close()

    # XML sheet building
    sheet_rows_xml = []
    
    # Header Row (Row 1)
    headers = ["ID", "Type (ប្រភេទ)", "Amount (ទឹកប្រាក់)", "Currency (រូបិយប័ណ្ណ)", "Category (ចំណាត់ថ្នាក់)", "Note (ការកត់ចំណាំ)", "Date & Time (កាលបរិច្ឆេទ)"]
    hdr_cells = []
    for col_idx, h in enumerate(headers, 1):
        col_letter = chr(64 + col_idx)
        cell = f'<c r="{col_letter}1" t="inlineStr"><is><t>{h}</t></is></c>'
        hdr_cells.append(cell)
    sheet_rows_xml.append(f'<row r="1" spans="1:7">{"".join(hdr_cells)}</row>')

    # Data Rows
    row_num = 2
    for r in rows:
        r_id, r_type, r_amt, r_curr, r_cat, r_note, r_date = r
        type_km = "ចំណាយ (Expense)" if r_type == "expense" else "ចំណូល (Income)"
        amt_num = float(r_amt or 0.0)
        curr_str = str(r_curr or "USD")
        cat_str = str(r_cat or "ទូទៅ")
        note_str = str(r_note or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        date_str = str(r_date or "")

        cells = [
            f'<c r="A{row_num}"><v>{r_id}</v></c>',
            f'<c r="B{row_num}" t="inlineStr"><is><t>{type_km}</t></is></c>',
            f'<c r="C{row_num}"><v>{amt_num}</v></c>',
            f'<c r="D{row_num}" t="inlineStr"><is><t>{curr_str}</t></is></c>',
            f'<c r="E{row_num}" t="inlineStr"><is><t>{cat_str}</t></is></c>',
            f'<c r="F{row_num}" t="inlineStr"><is><t>{note_str}</t></is></c>',
            f'<c r="G{row_num}" t="inlineStr"><is><t>{date_str}</t></is></c>',
        ]
        sheet_rows_xml.append(f'<row r="{row_num}" spans="1:7">{"".join(cells)}</row>')
        row_num += 1

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">\n'
        '  <cols>\n'
        '    <col min="1" max="1" width="8" customWidth="1"/>\n'
        '    <col min="2" max="2" width="20" customWidth="1"/>\n'
        '    <col min="3" max="3" width="16" customWidth="1"/>\n'
        '    <col min="4" max="4" width="14" customWidth="1"/>\n'
        '    <col min="5" max="5" width="25" customWidth="1"/>\n'
        '    <col min="6" max="6" width="35" customWidth="1"/>\n'
        '    <col min="7" max="7" width="24" customWidth="1"/>\n'
        '  </cols>\n'
        '  <sheetData>\n'
        + "\n".join(sheet_rows_xml) +
        '\n  </sheetData>\n'
        '</worksheet>'
    )

    content_types_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
        '  <Default Extension="xml" ContentType="application/xml"/>\n'
        '  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>\n'
        '  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n'
        '</Types>'
    )

    rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>\n'
        '</Relationships>'
    )

    wb_rels_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
        '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>\n'
        '</Relationships>'
    )

    wb_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">\n'
        '  <sheets>\n'
        '    <sheet name="Transaction History" sheetId="1" r:id="rId1"/>\n'
        '  </sheets>\n'
        '</workbook>'
    )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types_xml)
        z.writestr("_rels/.rels", rels_xml)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels_xml)
        z.writestr("xl/workbook.xml", wb_xml)
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)

    return buf.getvalue()
