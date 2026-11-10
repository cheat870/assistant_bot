import logging
import re
import urllib.parse
from typing import Dict, Any, Optional, Tuple, List
from services.finance_service import get_fuel_prices
from services.ai_service import _call_gemini_api, format_gemini_error
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

# Known Cambodia Routes & Highway Database (Origin: Phnom Penh by default)
CAMBODIA_ROUTES: Dict[str, Dict[str, Any]] = {
    "siemreap": {
        "names": ["សៀមរាប", "siem reap", "angkor", "អង្គរ", "siemreap"],
        "display_name": "🏛️ ខេត្តសៀមរាប (ក្រុងអង្គរ)",
        "distance_km": 314,
        "duration_hours": 5.5,
        "highway": "ផ្លូវជាតិលេខ ៦ (NR6)",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ស្រុកស្គុន (កំពង់ចាម) - សាច់គោអាំង & សត្វល្អិតបំពងល្បីប្រចាំតំបន់",
            "📍 ក្រុងស្ទឹងសែន (កំពង់ធំ) - កន្លែងឈប់សម្រាកបាយថ្ងៃត្រង់ & ក្រឡានក្តៅៗ",
            "📍 ស្ពានប្រវត្តិសាស្ត្រកំពង់ក្តី (ស្រុកជីក្រែង)"
        ],
        "must_eat": "ក្រឡានកំពង់ធំ, ប្រហុកអាំង, នំបញ្ចុកសៀមរាប",
        "destination_coords": (13.3671, 103.8448)
    },
    "sihanoukville": {
        "names": ["ព្រះសីហនុ", "កំពង់សោម", "sihanoukville", "kompong som", "kps", "shv"],
        "display_name": "🏖️ ខេត្តព្រះសីហនុ (ក្រុងកំពង់សោម)",
        "distance_km": 187,
        "duration_hours": 2.0,
        "highway": "ផ្លូវល្បឿនលឿន ភ្នំពេញ-ព្រះសីហនុ (Expressway E4) / ផ្លូវជាតិលេខ ៤",
        "toll_fee_usd": 12.0,
        "rest_stops": [
            "📍 ចំណតសេវាកម្មផ្លូវល្បឿនលឿន (Service Area កំពង់ស្ពឺ / ត្រែងត្រយឹង)",
            "📍 កំពូលភ្នំពេជ្រនិល / អាស្រមយាយម៉ៅ (ចេកអាំង & ដូងក្រអូប បើជិះតាម NR4)",
            "📍 ឆ្នេរអូរឈើទាល & ឆ្នេរអូរត្រេះ"
        ],
        "must_eat": "គ្រឿងសមុទ្រស្រស់ៗ, មឹកបំពងអំបិលម្ទេស, ក្តាមថ្មចំហុយ",
        "destination_coords": (10.6253, 103.5234)
    },
    "kampot": {
        "names": ["កំពត", "kampot"],
        "display_name": "⛰️ ខេត្តកំពត (ក្រុងបូកគោ)",
        "distance_km": 148,
        "duration_hours": 2.75,
        "highway": "ផ្លូវជាតិលេខ ៣ (NR3) ថ្មី / ផ្លូវជាតិលេខ ៣៣",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ផ្សារត្រាំខ្នារ & ស្រុកឈូក",
            "📍 រង្វង់មូលធុរេនកំពត & មាត់ព្រែកកំពត",
            "📍 រមណីយដ្ឋានភ្នំបូកគោ (Bokor National Park)"
        ],
        "must_eat": "ធុរេនកំពត, នំបញ្ចុកទឹកម្ហេចកំពត, ឆាក្តាមម្រេចខ្ចី",
        "destination_coords": (10.5942, 104.1640)
    },
    "kep": {
        "names": ["កែប", "kep"],
        "display_name": "🦀 ខេត្តកែប (តំបន់ឆ្នេរ & ផ្សារក្តាម)",
        "distance_km": 164,
        "duration_hours": 3.0,
        "highway": "ផ្លូវជាតិលេខ ៣ (NR3) + ផ្លូវជាតិលេខ ៣៣A",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ផ្សារក្តាមកែប (Crab Market) - កន្លែងលក់គ្រឿងសមុទ្រស្រស់ស្រង់ពីទឹក",
            "📍 រូបសំណាកស្រីស & ក្តាមសេះយក្ស",
            "📍 ឧទ្យានជាតិកែប (Kep National Park)"
        ],
        "must_eat": "ក្តាមសេះឆាម្រេចខ្ចី, មឹកអាំងអំបិលម្ទេស, បង្គាចំហុយ",
        "destination_coords": (10.4828, 104.2947)
    },
    "battambang": {
        "names": ["បាត់ដំបង", "battambang", "btb"],
        "display_name": "🌾 ខេត្តបាត់ដំបង (ជង្រុកស្រូវកម្ពុជា)",
        "distance_km": 291,
        "duration_hours": 4.75,
        "highway": "ផ្លូវជាតិលេខ ៥ (NR5) ពង្រីក ៤ គន្លងថ្មី",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ក្រុងឧដុង្គ (ទស្សនាភ្នំព្រះរាជទ្រព្យ)",
            "📍 ខេត្តកំពង់ឆ្នាំង (ទិញក្អម ឆ្នាំងដី និងក្រឡាន)",
            "📍 ខេត្តពោធិ៍សាត់ (ក្រូចពោធិ៍សាត់ & សាច់គោអាំងពោធិ៍សាត់)",
            "📍 រូបសំណាកលោកម្ចាស់ដំបងក្រញូង"
        ],
        "must_eat": "មីកូឡា, ក្រូចពោធិ៍សាត់, ណែមត្រីបាត់ដំបង, ទឹកអំពៅបាត់ដំបង",
        "destination_coords": (13.0957, 103.2022)
    },
    "mondulkiri": {
        "names": ["មណ្ឌលគិរី", "mondulkiri", "senmonorom", "សែនមនោរម្យ"],
        "display_name": "🌲 ខេត្តមណ្ឌលគិរី (ក្រុងសែនមនោរម្យ - អាកាសធាតុត្រជាក់)",
        "distance_km": 375,
        "duration_hours": 6.0,
        "highway": "NR6 ➔ NR7 (កំពង់ចាម) ➔ NR76 (ស្នួល ➔ សែនមនោរម្យ)",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ស្ពានគីហ្សូណា (កំពង់ចាម)",
            "📍 រង្វង់មូលព្រាបស (ក្រុងស្នួល ខេត្តក្រចេះ)",
            "📍 ភ្នំដោះក្រមុំ & ទឹកធ្លាក់ប៊ូស្រា",
            "📍 ចម្ការកាហ្វេ & ស្រល់មណ្ឌលគិរី"
        ],
        "must_eat": "កាហ្វេមណ្ឌលគិរី, សាច់គោអាំងលើចង្អេរ, ផ្លែប័រ (Avocado)",
        "destination_coords": (12.4558, 107.1881)
    },
    "ratanakiri": {
        "names": ["រតនគិរី", "ratanakiri", "banlung", "បានលុង"],
        "display_name": "🌋 ខេត្តរតនគិរី (ក្រុងបានលុង - បឹងយក្សឡោម)",
        "distance_km": 588,
        "duration_hours": 8.5,
        "highway": "NR6 ➔ NR7 (ក្រចេះ/ស្ទឹងត្រែង) ➔ NR78 (បានលុង)",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ទីរួមខេត្តក្រចេះ (មើលសត្វផ្សោតទន្លេមេគង្គកាំពី)",
            "📍 ខេត្តស្ទឹងត្រែង (ឆ្លងកាត់ស្ពានទន្លេសេកុង)",
            "📍 បឹងភ្នំភ្លើងយក្សឡោម & ទឹកធ្លាក់ចាអ៊ុង"
        ],
        "must_eat": "ត្រីប៉ាស៊ីអ៊ីនស្ទឹងត្រែង, កាហ្វេតំបន់ខ្ពង់រាប, ដំណាប់ចេក",
        "destination_coords": (13.7394, 106.9873)
    },
    "kohkong": {
        "names": ["កោះកុង", "koh kong", "kohkong"],
        "display_name": "🏞️ ខេត្តកោះកុង (អេកូទេសចរណ៍ & ព្រៃកោងកាង)",
        "distance_km": 280,
        "duration_hours": 4.75,
        "highway": "ផ្លូវជាតិលេខ ៤ ➔ ផ្លូវជាតិលេខ ៤៨ (ស្រែអំបិល ➔ កោះកុង)",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ផ្លូវបំបែកស្រែអំបិល",
            "📍 ស្ពានឆ្លងដៃសមុទ្រកោះកុង",
            "📍 ព្រៃកោងកាងពាមក្រសោប (Mangrove Forest)"
        ],
        "must_eat": "ក្តាមប្រៃកោះកុង, ទឹកត្រីកោះកុង, គ្រឿងសមុទ្រស្រស់",
        "destination_coords": (11.6153, 102.9838)
    },
    "poipet": {
        "names": ["ប៉ោយប៉ែត", "បន្ទាយមានជ័យ", "poipet", "banteay meanchey", "sisophon", "សិរីសោភ័ណ"],
        "display_name": "🚪 ក្រុងប៉ោយប៉ែត / ខេត្តបន្ទាយមានជ័យ (ច្រកព្រំដែន)",
        "distance_km": 398,
        "duration_hours": 6.5,
        "highway": "ផ្លូវជាតិលេខ ៥ (NR5 ឆ្លងកាត់បាត់ដំបង និងសិរីសោភ័ណ)",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ក្រុងបាត់ដំបង",
            "📍 ក្រុងសិរីសោភ័ណ (ភ្នំបន្ទាយនាង)",
            "📍 ច្រកទ្វារព្រំដែនអន្តរជាតិប៉ោយប៉ែត"
        ],
        "must_eat": "ទាខ្វៃប៉ោយប៉ែត, បាញ់ឆែវបន្ទាយមានជ័យ",
        "destination_coords": (13.6561, 102.5630)
    },
    "kampongcham": {
        "names": ["កំពង់ចាម", "kampong cham", "kpc"],
        "display_name": "🌉 ខេត្តកំពង់ចាម (មាត់ទន្លេមេគង្គ)",
        "distance_km": 124,
        "duration_hours": 2.0,
        "highway": "ផ្លូវជាតិលេខ ៦ ➔ ផ្លូវជាតិលេខ ៧",
        "toll_fee_usd": 0.0,
        "rest_stops": [
            "📍 ស្រុកស្គុន",
            "📍 ស្ពានគីហ្សូណា (Kizuna Bridge)",
            "📍 វត្តនគរបាជ័យ & កោះប៉ែន"
        ],
        "must_eat": "សាច់គោអាំងស្គុន, ត្រីដុតមាត់ទន្លេ, ផ្លែដូងកំពង់ចាម",
        "destination_coords": (11.9924, 105.4645)
    }
}

# Vehicle fuel consumption profiles (Liters per 100km)
VEHICLE_PROFILES = {
    "sedan": {"name": "រថយន្តតូច/Sedan (Prius, Corolla, Vios)", "consumption_per_100km": 7.0},
    "suv": {"name": "រថយន្ត SUV/Crossover (RAV4, RX, Highlander)", "consumption_per_100km": 8.8},
    "pickup": {"name": "រថយន្ត Pickup/Diesel (Ford Ranger, Hilux)", "consumption_per_100km": 9.5, "fuel_type": "diesel"},
    "moto": {"name": "ម៉ូតូ (Scoopy, Wave, Click)", "consumption_per_100km": 2.4}
}

def match_destination(query: str) -> Optional[Dict[str, Any]]:
    """Match destination query to known Cambodian routes."""
    q_clean = query.lower().strip()
    # Direct key lookup
    if q_clean in CAMBODIA_ROUTES:
        return CAMBODIA_ROUTES[q_clean]

    for key, data in CAMBODIA_ROUTES.items():
        if any(alias in q_clean for alias in data["names"]):
            return data
    return None

def calculate_trip_details(
    destination_data: Dict[str, Any],
    origin: str = "រាជធានីភ្នំពេញ",
    vehicle_type: str = "suv"
) -> Dict[str, Any]:
    """Calculate distance, duration, fuel usage, and cost based on live retail fuel prices."""
    dist_km = destination_data["distance_km"]
    hours = destination_data["duration_hours"]

    # Vehicle profile
    v_profile = VEHICLE_PROFILES.get(vehicle_type, VEHICLE_PROFILES["suv"])
    rate_100km = v_profile["consumption_per_100km"]
    fuel_needed_liters = round((dist_km / 100.0) * rate_100km, 1)

    # Fetch live fuel price
    fuel_prices = get_fuel_prices()
    fuel_key = v_profile.get("fuel_type", "regular")
    price_info = fuel_prices.get(fuel_key, fuel_prices["regular"])
    price_per_l_khr = price_info["khr"]
    price_per_l_usd = price_info["usd"]

    fuel_cost_khr = round(fuel_needed_liters * price_per_l_khr)
    fuel_cost_usd = round(fuel_needed_liters * price_per_l_usd, 2)

    toll_usd = destination_data.get("toll_fee_usd", 0.0)
    total_cost_usd = round(fuel_cost_usd + toll_usd, 2)

    # Google maps route link
    dest_lat, dest_lon = destination_data.get("destination_coords", (11.5564, 104.9282))
    maps_dir_url = f"https://www.google.com/maps/dir/?api=1&origin={urllib.parse.quote(origin)}&destination={dest_lat},{dest_lon}"

    return {
        "origin": origin,
        "destination": destination_data["display_name"],
        "distance_km": dist_km,
        "duration_hours": hours,
        "highway": destination_data["highway"],
        "vehicle_name": v_profile["name"],
        "fuel_needed_liters": fuel_needed_liters,
        "fuel_name": price_info["name"],
        "price_per_l_khr": price_per_l_khr,
        "fuel_cost_khr": fuel_cost_khr,
        "fuel_cost_usd": fuel_cost_usd,
        "toll_fee_usd": toll_usd,
        "total_cost_usd": total_cost_usd,
        "rest_stops": destination_data["rest_stops"],
        "must_eat": destination_data["must_eat"],
        "maps_dir_url": maps_dir_url
    }

def format_trip_report(trip: Dict[str, Any]) -> str:
    """Format an informative, polished trip plan report in Khmer."""
    h = int(trip["duration_hours"])
    m = int(round((trip["duration_hours"] - h) * 60))
    time_str = f"{h} ម៉ោង {m} នាទី" if m > 0 else f"{h} ម៉ោង"

    rest_stops_formatted = "\n".join(f"  {s}" for s in trip["rest_stops"])

    report = (
        f"🚗 *ផែនការធ្វើដំណើរឆ្លាតវៃ CamRoad (Trip Planner)* 🛣️\n\n"
        f"🚩 *ចេញដំណើរពី:* {trip['origin']}\n"
        f"🏁 *គោលដៅ:* *{trip['destination']}*\n"
        f"🛣️ *ផ្លូវធ្វើដំណើរ:* `{trip['highway']}`\n\n"
        f"📏 *ចម្ងាយផ្លូវ:* `~{trip['distance_km']} គីឡូម៉ែត្រ (km)`\n"
        f"⏱️ *រយៈពេលបើកបរ:* `~{time_str}` (អាស្រ័យលើល្បឿន & ចរាចរណ៍)\n\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n"
        f"⛽ *ការប៉ាន់ស្មានការប្រើប្រាស់ប្រេងឥន្ធនៈ៖*\n"
        f"• ប្រភេទទោចក្រ/រថយន្ត៖ _{trip['vehicle_name']}_\n"
        f"• បរិមាណសាំងត្រូវប្រើ៖ *~{trip['fuel_needed_liters']} លីត្រ* ({trip['fuel_name']})\n"
        f"• តម្លៃសាំងបច្ចុប្បន្ន៖ `{trip['price_per_l_khr']:,} ៛/L`\n"
        f"• ថ្លៃសាំងប៉ាន់ស្មាន៖ *~{trip['fuel_cost_khr']:,} ៛* (~${trip['fuel_cost_usd']})\n"
    )

    if trip["toll_fee_usd"] > 0:
        report += (
            f"• សោហ៊ុយផ្លូវល្បឿនលឿន (Toll)៖ *~${trip['toll_fee_usd']}*\n"
            f"💰 *សរុបការចំណាយធ្វើដំណើរ:* *~${trip['total_cost_usd']}*\n"
        )

    report += (
        f"\n━━━━━━━━━━━━━━━━━━━━━━\n"
        f"🛑 *កន្លែងឈប់សម្រាក & ទេសភាពតាមផ្លូវ៖*\n"
        f"{rest_stops_formatted}\n\n"
        f"🍽️ *ម្ហូប & ចំណីល្បីប្រចាំតំបន់ដែលមិនគួររំលង៖*\n"
        f"• _{trip['must_eat']}_\n"
    )
    return report

CAR_DIAGNOSTIC_PROMPT = (
    "You are a master automotive technician and vehicle diagnostic expert specialized in common cars in Cambodia "
    "(Toyota Prius, Lexus RX, Toyota Highlander, Ford Ranger, Toyota Hilux, Hyundai, Kia, Mazda, etc.). "
    "Carefully inspect this image of a car instrument cluster / dashboard warning light or OBD2 diagnostic code. "
    "\n\nProvide a comprehensive, authoritative diagnostic report in Khmer formatted in clean Markdown:\n"
    "🔧 **ការវិភាគភ្លើងកុងទ័ររថយន្ត (Car Dashboard Diagnostic)**\n"
    "• ឈ្មោះភ្លើងសញ្ញា/កូដ៖ (Name of the warning indicator in Khmer and English, e.g., Check Engine, ABS, Oil Pressure, TPMS, Battery)\n"
    "• កម្រិតគ្រោះថ្នាក់៖ (Choose: 🔴 ធ្ងន់ធ្ងរខ្លាំង - ត្រូវឈប់ឡានភ្លាមៗ | 🟡 មធ្យម - អាចបើកទៅមុខតិចតួចបាន តែត្រូវឆែកជាបន្ទាន់ | 🟢 សញ្ញាដំណឹងធម្មតា)\n"
    "• មូលហេតុដែលអាចកើតមាន៖ (List 2-3 most common causes for cars in Cambodia)\n"
    "• អ្វីដែលអ្នកបើកបរត្រូវធ្វើភ្លាមៗ៖ (Clear step-by-step instructions for the driver)\n"
    "• ផលប៉ះពាល់ និងការជួសជុល៖ (What mechanic will do, estimated impact if ignored)\n\n"
    "If the image does not show a dashboard warning light or car part, state clearly what is seen and advise "
    "the user to photograph the instrument cluster with warning lights illuminated."
)

async def diagnose_car_dashboard(image_bytes: bytes, caption: str = "") -> str:
    """Analyze car dashboard warning lights or engine indicators using Gemini Vision AI."""
    if not (GEMINI_API_KEY and GEMINI_API_KEY != "your_gemini_api_key_here"):
        return (
            "🔧 *ការវិភាគភ្លើងសញ្ញាកុងទ័ររថយន្ត (Car Diagnostic)*\n\n"
            "⚠️ មុខងារ AI Vision មិនទាន់ត្រូវបានកំណត់ GEMINI_API_KEY នៅឡើយទេ។\n\n"
            "💡 *សញ្ញាទូទៅដែលតែងតែលោត៖*\n"
            "• 🟡 **Check Engine:** បញ្ហាប្រព័ន្ធចំហេះ, O2 Sensor, ឬប៊ូហ្ស៊ី\n"
            "• 🔴 **Oil Pressure (កំសៀវប្រេង):** ខ្វះប្រេងម៉ាស៊ីន (ត្រូវឈប់ឡានភ្លាម)\n"
            "• 🔴 **Battery/Alternator:** ដាយណា​ម៉ូមិនសាកភ្លើងចូលអាគុយ\n"
            "• 🟡 **ABS:** ប្រព័ន្ធហ្វ្រាំងជំនួយមានបញ្ហា (ហ្វ្រាំងធម្មតានៅដំណើរការ)"
        )

    import asyncio
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)
    image_part = types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg")

    instruction = (
        f"{CAR_DIAGNOSTIC_PROMPT}\n\n"
        f"User caption or description if any: '{caption}'"
    )

    try:
        resp = await asyncio.to_thread(_call_gemini_api, client, [image_part, instruction])
        reply = resp.text
        reply += (
            "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ _សម្គាល់៖ ការវិភាគនេះជាជំនួយបឋមដោយ AI។ សូមយកយានយន្តទៅយានដ្ឋានជំនាញដើម្បីដោតម៉ាស៊ីន OBD2 ឆែកឱ្យកាន់តែច្បាស់!_"
        )
        return reply
    except Exception as e:
        logger.error(f"Car diagnostic failed: {e}")
        return format_gemini_error(e)
