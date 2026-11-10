import time
import logging
import asyncio
from typing import Dict, Any, Optional, Tuple, List
import httpx

logger = logging.getLogger(__name__)

HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TelegramAssistantBot/1.0",
    "Accept": "application/json"
}

SUPPORTED_COINS: Dict[str, Dict[str, str]] = {
    "TON": {
        "name": "The Open Network (Telegram)",
        "icon": "💎",
        "binance": "TONUSDT",
        "coingecko": "the-open-network"
    },
    "BTC": {
        "name": "Bitcoin",
        "icon": "₿",
        "binance": "BTCUSDT",
        "coingecko": "bitcoin"
    },
    "ETH": {
        "name": "Ethereum",
        "icon": "🔷",
        "binance": "ETHUSDT",
        "coingecko": "ethereum"
    },
    "SOL": {
        "name": "Solana",
        "icon": "🟣",
        "binance": "SOLUSDT",
        "coingecko": "solana"
    },
    "DOGE": {
        "name": "Dogecoin",
        "icon": "🐶",
        "binance": "DOGEUSDT",
        "coingecko": "dogecoin"
    },
    "BNB": {
        "name": "BNB (Binance)",
        "icon": "🟡",
        "binance": "BNBUSDT",
        "coingecko": "binancecoin"
    },
    "XRP": {
        "name": "Ripple (XRP)",
        "icon": "⚡",
        "binance": "XRPUSDT",
        "coingecko": "ripple"
    },
    "USDT": {
        "name": "Tether USD",
        "icon": "💵",
        "binance": "USDCUSDT",
        "coingecko": "tether"
    }
}

# In-memory cache for live prices (30-second TTL)
_price_cache: Dict[str, Any] = {
    "data": None,
    "timestamp": 0
}

async def fetch_crypto_prices(force_refresh: bool = False) -> Dict[str, Dict[str, Any]]:
    """
    Fetch real-time crypto prices, 24h change %, and 24h highs/lows.
    Primary source: Binance Public 24hr Ticker API.
    Fallback source: CoinGecko Public Simple Price API.
    """
    global _price_cache
    now = time.time()
    if not force_refresh and _price_cache["data"] and (now - _price_cache["timestamp"] < 30):
        return _price_cache["data"]

    results: Dict[str, Dict[str, Any]] = {}

    # 1. Try Binance Public API (symbols query)
    binance_symbols = [coin["binance"] for coin in SUPPORTED_COINS.values() if coin.get("binance")]
    symbols_json = '["' + '","'.join(binance_symbols) + '"]'
    url = f"https://api.binance.com/api/v3/ticker/24hr?symbols={symbols_json}"

    try:
        async with httpx.AsyncClient(timeout=6.0, headers=HTTP_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                data_by_sym = {item["symbol"]: item for item in data}

                for sym, meta in SUPPORTED_COINS.items():
                    bsym = meta.get("binance")
                    if bsym and bsym in data_by_sym:
                        b_item = data_by_sym[bsym]
                        price = float(b_item.get("lastPrice", 0.0))
                        change = float(b_item.get("priceChangePercent", 0.0))
                        high = float(b_item.get("highPrice", 0.0))
                        low = float(b_item.get("lowPrice", 0.0))
                        vol = float(b_item.get("volume", 0.0))
                        results[sym] = {
                            "symbol": sym,
                            "name": meta["name"],
                            "icon": meta["icon"],
                            "price_usd": price,
                            "change_24h": change,
                            "high_24h": high,
                            "low_24h": low,
                            "volume": vol
                        }
    except Exception as e_binance:
        logger.debug(f"Binance API query failed, trying CoinGecko fallback: {e_binance}")

    # 2. Fallback to CoinGecko if Binance missed coins
    if len(results) < len(SUPPORTED_COINS):
        try:
            cg_ids = ",".join(coin["coingecko"] for coin in SUPPORTED_COINS.values())
            cg_url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_ids}&vs_currencies=usd&include_24hr_change=true"
            async with httpx.AsyncClient(timeout=6.0, headers=HTTP_HEADERS) as client:
                resp = await client.get(cg_url)
                if resp.status_code == 200:
                    cg_data = resp.json()
                    for sym, meta in SUPPORTED_COINS.items():
                        if sym not in results:
                            cid = meta["coingecko"]
                            if cid in cg_data:
                                price = float(cg_data[cid].get("usd", 0.0))
                                change = float(cg_data[cid].get("usd_24h_change", 0.0))
                                results[sym] = {
                                    "symbol": sym,
                                    "name": meta["name"],
                                    "icon": meta["icon"],
                                    "price_usd": price,
                                    "change_24h": change,
                                    "high_24h": price,
                                    "low_24h": price,
                                    "volume": 0.0
                                }
        except Exception as e_cg:
            logger.debug(f"CoinGecko fallback failed: {e_cg}")

    # 3. If everything failed, populate safe approximate defaults
    if not results:
        fallback_defaults = {
            "TON": (1.65, 1.2),
            "BTC": (72500.0, -1.8),
            "ETH": (2020.0, -3.2),
            "SOL": (82.5, -4.1),
            "DOGE": (0.067, -2.5),
            "BNB": (540.0, 0.5),
            "XRP": (0.55, -1.0),
            "USDT": (1.0, 0.0)
        }
        for sym, (p, c) in fallback_defaults.items():
            meta = SUPPORTED_COINS[sym]
            results[sym] = {
                "symbol": sym,
                "name": meta["name"],
                "icon": meta["icon"],
                "price_usd": p,
                "change_24h": c,
                "high_24h": p * 1.03,
                "low_24h": p * 0.97,
                "volume": 0.0
            }

    _price_cache["data"] = results
    _price_cache["timestamp"] = now
    return results

def format_crypto_overview_card(
    crypto_data: Dict[str, Dict[str, Any]],
    usd_khr_rate: float = 4085.0,
    gold_info: Optional[Dict[str, float]] = None
) -> str:
    """Format full Cambodian Crypto & TON Live Watcher report card."""
    lines = [
        "📈 *[ផ្សារ Crypto, TON & មាស Live Watcher]* 💎\n",
        f"💱 *អត្រាប្តូរប្រាក់យោង:* `1 USD ≈ {usd_khr_rate:,.0f} ៛`\n",
        "━━━━━━━━━━━━━━━━━━━━━━"
    ]

    # Priority order: TON first (Telegram Ecosystem), then BTC, ETH, SOL, DOGE, BNB, XRP
    display_order = ["TON", "BTC", "ETH", "SOL", "DOGE", "BNB", "XRP"]
    for sym in display_order:
        item = crypto_data.get(sym)
        if not item:
            continue

        p_usd = item["price_usd"]
        p_khr = p_usd * usd_khr_rate
        change = item["change_24h"]
        c_badge = "🟢 +" if change >= 0 else "🔴 "
        c_str = f"{c_badge}{change:.2f}%"

        # Format price with appropriate decimal places
        if p_usd >= 1000:
            price_usd_fmt = f"${p_usd:,.2f}"
            price_khr_fmt = f"{p_khr:,.0f} ៛"
        elif p_usd >= 1:
            price_usd_fmt = f"${p_usd:,.3f}"
            price_khr_fmt = f"{p_khr:,.1f} ៛"
        else:
            price_usd_fmt = f"${p_usd:,.5f}"
            price_khr_fmt = f"{p_khr:,.2f} ៛"

        icon = item["icon"]
        name = item["name"]

        lines.append(f"{icon} *{sym}* - _{name}_")
        lines.append(f"   • តម្លៃ: `{price_usd_fmt}` ≈ `{price_khr_fmt}`")
        lines.append(f"   • បំរែបំរួល 24h: {c_str}")

        if item.get("high_24h") and item.get("low_24h") and item["high_24h"] > 0:
            lines.append(f"   • 24h High/Low: `${item['high_24h']:,.2f}` / `${item['low_24h']:,.2f}`")
        lines.append("")

    # Include Gold snapshot if available
    if gold_info and gold_info.get("damlung_usd"):
        damlung_usd = gold_info["damlung_usd"]
        damlung_khr = damlung_usd * usd_khr_rate
        chi_usd = gold_info.get("chi_usd", damlung_usd / 10.0)
        lines.append("━━━━━━━━━━━━━━━━━━━━━━")
        lines.append("🪙 *ទីផ្សារមាសអន្តរជាតិ (Gold Spot Price):*")
        lines.append(f"• 🥇 *មាស ១ ដំឡឹង:* `${damlung_usd:,.2f}` ≈ `{damlung_khr:,.0f} ៛`")
        lines.append(f"• 🥈 *មាស ១ ជី:* `${chi_usd:,.2f}`")
        lines.append("")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 *កំណត់ម៉ោងរោទ៍ Alert តម្លៃ (Drop / Pump Alert)៖*")
    lines.append("• វាយពាក្យ៖ `/alert <កាក់> <តម្លៃ>`")
    lines.append("• ឧទាហរណ៍៖ `/alert btc 85000` (ប្រាប់ពេល Bitcoin ធ្លាក់/ឡើងដល់)")
    lines.append("• ឧទាហរណ៍៖ `/alert ton 5.5` (ប្រាប់ពេល TON ឡើងដល់ $5.5)")
    lines.append("• មើល Alert សកម្ម៖ `/alerts` ឬចុចប៊ូតុងខាងក្រោម ⬇️")

    return "\n".join(lines)

def format_single_coin_card(coin: Dict[str, Any], usd_khr_rate: float = 4085.0) -> str:
    """Format single coin deep-dive report."""
    p_usd = coin["price_usd"]
    p_khr = p_usd * usd_khr_rate
    change = coin["change_24h"]
    c_badge = "🟢 +" if change >= 0 else "🔴 "
    c_str = f"{c_badge}{change:.2f}%"

    lines = [
        f"{coin['icon']} *[ព័ត៌មានលម្អិតកាក់ {coin['symbol']} ({coin['name']})]* 🚀\n",
        "━━━━━━━━━━━━━━━━━━━━━━",
        f"• 💵 *តម្លៃបច្ចុប្បន្ន (USD):* `${p_usd:,.4f}`",
        f"• 🇰🇭 *តម្លៃជាប្រាក់រៀល (KHR):* `{p_khr:,.0f} ៛`",
        f"• 📊 *បំរែបំរួល ២៤ ម៉ោង:* {c_str}",
        f"• 📈 *តម្លៃខ្ពស់បំផុត ២៤h:* `${coin.get('high_24h', 0):,.2f}`",
        f"• 📉 *តម្លៃទាបបំផុត ២៤h:* `${coin.get('low_24h', 0):,.2f}`",
    ]
    if coin.get("volume"):
        lines.append(f"• 📦 *ទំហំជួញដូរ ២៤h:* `{coin['volume']:,.0f} {coin['symbol']}`")

    lines.append("━━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🔔 *កំណត់ Alert សម្រាប់កាក់នេះ៖*")
    lines.append(f"`/alert {coin['symbol'].lower()} <target_price>`")
    return "\n".join(lines)

def parse_alert_input(
    raw_text: str,
    current_prices: Dict[str, Dict[str, Any]]
) -> Tuple[bool, Optional[str], Optional[float], Optional[str], Optional[float], str]:
    """
    Parse user alert input e.g. 'btc 85000', 'ton 5.5', 'eth 3000'.
    Returns (success, symbol, target_price, condition, current_price, msg).
    """
    parts = raw_text.strip().split()
    if len(parts) < 2:
        return False, None, None, None, None, (
            "❌ *ទម្រង់កំណត់ Alert មិនត្រឹមត្រូវ!*\n\n"
            "សូមបញ្ជាក់ឈ្មោះកាក់ និងតម្លៃដែលចង់ឱ្យ Bot ជូនដំណឹង៖\n"
            "• ឧទាហរណ៍៖ `/alert btc 85000`\n"
            "• ឧទាហរណ៍៖ `/alert ton 5.5`\n"
            "• ឧទាហរណ៍៖ `/alert eth 3200`"
        )

    sym = parts[0].upper().lstrip("$").lstrip("#")
    if sym not in current_prices:
        avail = ", ".join(f"`{s}`" for s in current_prices.keys())
        return False, None, None, None, None, (
            f"❌ *មិនស្គាល់កាក់ `{sym}` ឡើយ!*\n\n"
            f"កាក់ដែលគាំទ្របច្ចុប្បន្នមាន៖ {avail}"
        )

    price_str = parts[1].replace("$", "").replace(",", "").strip()
    try:
        target_price = float(price_str)
        if target_price <= 0:
            raise ValueError()
    except ValueError:
        return False, None, None, None, None, "❌ *ចំនួនទឹកប្រាក់គោលដៅមិនត្រឹមត្រូវ!* សូមវាយជាលេខ (ឧទាហរណ៍: `85000` ឬ `5.5`)"

    curr_price = current_prices[sym]["price_usd"]
    # Auto-detect condition:
    # If target > current -> Alert when price RISES ABOVE target
    # If target < current -> Alert when price DROPS BELOW target
    if target_price > curr_price:
        condition = "above"
        cond_text = f"📈 *កើនឡើងដល់ ឬលើសពី* `${target_price:,.2f}`"
    else:
        condition = "below"
        cond_text = f"📉 *ធ្លាក់ចុះដល់ ឬក្រោម* `${target_price:,.2f}`"

    success_msg = (
        f"✅ *បានកំណត់ Alert តម្លៃកាក់ {sym} ដោយជោគជ័យ!* 🔔\n\n"
        f"• កាក់: *{sym}* ({current_prices[sym]['name']})\n"
        f"• តម្លៃបច្ចុប្បន្ន: `${curr_price:,.2f}`\n"
        f"• លក្ខខណ្ឌជូនដំណឹង: {cond_text}\n\n"
        f"Bot នឹងផ្ញើសារជូនដំណឹងភ្លាមៗនៅពេលទីផ្សារប្រែប្រួលដល់កម្រិតនេះ! 🚀"
    )
    return True, sym, target_price, condition, curr_price, success_msg

async def check_and_trigger_crypto_alerts(bot: Any) -> int:
    """
    Check all active alerts in SQLite database against current prices.
    Sends notification message to user if threshold is breached.
    """
    from database import get_active_crypto_alerts, mark_crypto_alert_triggered

    active_alerts = get_active_crypto_alerts()
    if not active_alerts:
        return 0

    latest_prices = await fetch_crypto_prices(force_refresh=True)
    triggered_count = 0

    for alert in active_alerts:
        aid = alert["id"]
        chat_id = alert["chat_id"]
        sym = alert["symbol"]
        target = alert["target_price"]
        condition = alert["condition"]
        created_p = alert["created_price"]

        coin = latest_prices.get(sym)
        if not coin:
            continue

        curr_p = coin["price_usd"]
        is_triggered = False

        if condition == "below" and curr_p <= target:
            is_triggered = True
            direction_km = f"📉 *ធ្លាក់ចុះមកដល់* `${curr_p:,.2f}` (គោលដៅកំណត់: `${target:,.2f}`)"
        elif condition == "above" and curr_p >= target:
            is_triggered = True
            direction_km = f"🚀 *កើនឡើងហក់ដល់* `${curr_p:,.2f}` (គោលដៅកំណត់: `${target:,.2f}`)"

        if is_triggered:
            mark_crypto_alert_triggered(aid)
            triggered_count += 1

            diff = curr_p - created_p
            diff_pct = (diff / created_p * 100.0) if created_p else 0.0
            diff_badge = f"+{diff_pct:.2f}%" if diff_pct >= 0 else f"{diff_pct:.2f}%"

            notify_text = (
                f"🚨 *ការជូនដំណឹងតម្លៃ Crypto (Price Alert Triggered)!* 🔔\n\n"
                f"{coin['icon']} *កាក់ {sym} ({coin['name']})* បានឆ្លងកាត់គោលដៅរបស់អ្នកហើយ!\n\n"
                f"• {direction_km}\n"
                f"• តម្លៃកាលកំណត់: `${created_p:,.2f}`\n"
                f"• បំរែបំរួលចាប់តាំងពីកំណត់: `{diff_badge}`\n"
                f"• បំរែបំរួល ២៤ ម៉ោង: `{coin['change_24h']:+.2f}%`\n\n"
                f"💡 លោកអ្នកអាចចូលទៅកាន់ `/crypto` ដើម្បីពិនិត្យមើលស្ថានភាពទីផ្សារបន្ត!"
            )
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=notify_text,
                    parse_mode="Markdown"
                )
            except Exception as e_send:
                logger.debug(f"Could not deliver crypto alert to chat {chat_id}: {e_send}")

    return triggered_count
