import logging
from typing import Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "TelegramAssistantBot/1.0 (https://github.com/cheat870/assistant_bot)",
    "Accept": "application/json"
}

# Cache to avoid excessive API requests
_cache: Dict[str, Any] = {
    "rates": None,
    "rates_time": 0,
    "gold": None,
    "gold_time": 0,
}

async def fetch_exchange_rates() -> Optional[Dict[str, float]]:
    """Fetch live exchange rates with USD base."""
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("rates", {})
                return {
                    "KHR": rates.get("KHR", 4085.0),
                    "THB": rates.get("THB", 33.6),
                    "EUR": rates.get("EUR", 0.89),
                    "CNY": rates.get("CNY", 6.70),
                    "VND": rates.get("VND", 25400.0),
                }
    except Exception as e:
        logger.warning(f"Error fetching exchange rates: {e}")
        
    return {
        "KHR": 4085.0,
        "THB": 33.6,
        "EUR": 0.89,
        "CNY": 6.70,
        "VND": 25400.0,
    }

async def fetch_gold_price() -> Optional[Dict[str, float]]:
    """Fetch international gold spot price and convert to Cambodian units."""
    url = "https://api.gold-api.com/price/XAU"
    try:
        async with httpx.AsyncClient(timeout=8.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                oz_price = float(data.get("price", 0))
                if oz_price > 0:
                    # 1 troy oz = 31.1035 g. 1 Damlung = 37.5 g.
                    damlung_usd = oz_price * (37.5 / 31.1034768)
                    chi_usd = damlung_usd / 10.0
                    return {
                        "oz_usd": oz_price,
                        "damlung_usd": round(damlung_usd, 2),
                        "chi_usd": round(chi_usd, 2),
                    }
    except Exception as e:
        logger.warning(f"Error fetching gold price: {e}")
        
    return None

def get_fuel_prices() -> Dict[str, Dict[str, Any]]:
    """Official retail fuel prices in Cambodia (Ministry of Commerce)."""
    return {
        "regular": {"name": "សាំងធម្មតា (EA92)", "khr": 4200, "usd": round(4200 / 4085, 2)},
        "super": {"name": "សាំងស៊ុបពែរ (EA95)", "khr": 4750, "usd": round(4750 / 4085, 2)},
        "diesel": {"name": "ប្រេងម៉ាស៊ូត (DO 50ppm)", "khr": 4050, "usd": round(4050 / 4085, 2)},
    }

async def format_finance_report() -> str:
    """Format full Cambodian financial overview report."""
    rates = await fetch_exchange_rates() or {}
    gold = await fetch_gold_price()
    fuel = get_fuel_prices()
    
    usd_khr = rates.get("KHR", 4085.0)
    usd_thb = rates.get("THB", 33.6)
    usd_eur = rates.get("EUR", 0.89)
    usd_cny = rates.get("CNY", 6.70)
    
    # Calculate THB to KHR (100 Baht in Riel)
    thb_100_khr = round((100.0 / usd_thb) * usd_khr) if usd_thb else 0
    
    lines = [
        "💰 *[ព័ត៌មានសេដ្ឋកិច្ច និងហិរញ្ញវត្ថុនៅកម្ពុជា]* 🇰🇭\n",
        "💱 *អត្រាប្តូរប្រាក់ (Live Exchange Rates):*",
        f"• 🇺🇸 *1 USD* = `{usd_khr:,.0f} KHR` (រៀល)",
        f"• 🇹🇭 *1 THB* = `{usd_khr / usd_thb:,.1f} KHR` | `100 THB = {thb_100_khr:,.0f} ៛`",
        f"• 🇪🇺 *1 EUR* = `{usd_khr / usd_eur:,.0f} KHR`",
        f"• 🇨🇳 *1 CNY* = `{usd_khr / usd_cny:,.0f} KHR`\n",
    ]
    
    if gold:
        damlung_khr = gold["damlung_usd"] * usd_khr
        chi_khr = gold["chi_usd"] * usd_khr
        lines.extend([
            "🪙 *តម្លៃមាស (Gold Prices):*",
            f"• *១ តម្លឹង (Damlung):* `${gold['damlung_usd']:,.2f}` (~`{damlung_khr:,.0f} ៛`)",
            f"• *១ ជី (Chi):* `${gold['chi_usd']:,.2f}` (~`{chi_khr:,.0f} ៛`)",
            f"• *Spot 1 Ounce:* `${gold['oz_usd']:,.2f}`\n",
        ])
        
    lines.extend([
        "⛽ *តម្លៃប្រេងឥន្ធនៈ (Fuel Prices in Cambodia):*",
        f"• 🟢 *{fuel['regular']['name']}:* `{fuel['regular']['khr']:,} ៛/L` (${fuel['regular']['usd']})",
        f"• 🔴 *{fuel['super']['name']}:* `{fuel['super']['khr']:,} ៛/L` (${fuel['super']['usd']})",
        f"• ⚫ *{fuel['diesel']['name']}:* `{fuel['diesel']['khr']:,} ៛/L` (${fuel['diesel']['usd']})",
        "_(តម្លៃផ្លូវការកំណត់ដោយក្រសួងពាណិជ្ជកម្មកម្ពុជា)_\n",
        "💡 *គន្លឹះ:* វាយ `/convert 100 USD KHR` ដើម្បីប្តូររូបិយប័ណ្ណភ្លាមៗ!"
    ])
    
    return "\n".join(lines)

async def convert_currency_text(amount: float, from_c: str, to_c: str) -> str:
    """Convert an amount from one currency to another."""
    from_c = from_c.upper()
    to_c = to_c.upper()
    
    rates = await fetch_exchange_rates() or {}
    rates["USD"] = 1.0
    
    if from_c not in rates or to_c not in rates:
        supported = ", ".join(rates.keys())
        return f"❌ រូបិយប័ណ្ណមិនត្រឹមត្រូវ។ រូបិយប័ណ្ណគាំទ្រ៖ {supported}"
        
    # Convert to USD first then to target
    usd_val = amount / rates[from_c]
    target_val = usd_val * rates[to_c]
    
    return (
        f"💱 *លទ្ធផលប្តូរប្រាក់ (Currency Conversion):*\n\n"
        f"💵 *{amount:,.2f} {from_c}* = *{target_val:,.2f} {to_c}*\n"
        f"_(អត្រាប្តូរប្រាក់បច្ចុប្បន្ន)_"
    )
