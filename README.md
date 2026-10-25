# 🇰🇭 Telegram Assistant Bot (Video Downloader & Cambodia Public Holiday Alert)

Telegram Bot ជំនួយការឆ្លាតវៃដែលរួមបញ្ចូលមុខងារសំខាន់ៗចំនួន ២៖
1. **📥 All Video Downloader**: ទាញយកវីដេអូពីគ្រប់បណ្ដាញសង្គម (**TikTok, YouTube, Facebook, Instagram, Twitter/X...**) ដោយស្វ័យប្រវត្តិតាមរយៈ Link។
2. **🗓️ Cambodia Public Holiday Calendar & 4:00 AM Alert**:
   - ប្រតិទិនថ្ងៃឈប់សម្រាកបុណ្យជាតិផ្លូវការនៅកម្ពុជា (២០២៥, ២០២៦, ២០២៧)។
   - គណនាថ្ងៃដែលនៅសល់ (Countdown to upcoming holidays)។
   - **ប្រព័ន្ធដាស់តឿនស្វ័យប្រវត្តិនាពេលទៀបភ្លឺ (៤:០០ ព្រឹក)** ក្នុងរាល់ថ្ងៃបុណ្យឈប់សម្រាក (ម៉ោងនៅកម្ពុជា `Asia/Phnom_Penh`)។

---

## 📁 រចនាសម្ព័ន្ធគម្រោង (Project Structure)

```text
telegram_assistant_bot/
├── config.py                 # ការកំណត់ទូទៅ (Timezone, Alert Time, Limits)
├── database.py               # SQLite Database សម្រាប់គ្រប់គ្រង Subscribers
├── main.py                   # កូដមេសម្រាប់ដំណើរការ Telegram Bot
├── requirements.txt          # បញ្ជីបណ្ណាល័យដែលត្រូវការ
├── .env                      # File រក្សាទុក Telegram Bot Token
├── .env.example              # គំរូ Environment Variables
├── services/
│   ├── holiday_calendar.py   # ប្រតិទិនបុណ្យជាតិ និងមុខងារគណនាថ្ងៃឈប់សម្រាក
│   ├── scheduler.py          # ប្រព័ន្ធ JobQueue ដាស់តឿនម៉ោង ៤:០០ ព្រឹក
│   └── video_downloader.py   # ម៉ាស៊ីនទាញយកវីដេអូ (yt-dlp)
├── handlers/
│   ├── command_handlers.py   # /start, /calendar, /upcoming, /subscribe...
│   └── video_handlers.py     # ចាប់យក Link និងផ្ញើវីដេអូត្រឡប់ទៅវិញ
└── test_bot_services.py      # Test suite ផ្ទៀងផ្ទាត់មុខងារទាំងអស់
```

---

## 🚀 របៀបដំឡើង និងដំណើរការ (Quickstart)

### ជំហានទី ១: យក Telegram Bot Token
1. បើកកម្មវិធី **Telegram** រួចស្វែងរក `@BotFather`
2. វាយបញ្ជា `/newbot` រួចដាក់ឈ្មោះ និង username ឱ្យ bot របស់អ្នក
3. ចម្លងយក **HTTP API Token** (ឧ. `7123456789:AAH...`)

### ជំហានទី ២: កំណត់ Token ក្នុង `.env`
បើក file `.env` រួចបិទភ្ជាប់ Token របស់អ្នក៖
```ini
TELEGRAM_BOT_TOKEN="ដាក់_TOKEN_របស់អ្នកនៅទីនេះ"
BOT_TIMEZONE="Asia/Phnom_Penh"
ALERT_HOUR=4
ALERT_MINUTE=0
MAX_FILE_SIZE_MB=50
```

### ជំហានទី ៣: ដំណើរការ Bot
ដំណើរការតាម command ខាងក្រោម៖
```bash
python main.py
```

---

## 🎮 បញ្ជីពាក្យបញ្ជា (Bot Commands)

| Command | ការពិពណ៌នា (Description) |
|---|---|
| `/start` | បង្ហាញ Menu មេ និងចុះឈ្មោះទទួលការដាស់តឿនដោយស្វ័យប្រវត្តិ |
| `/upcoming` | មើលថ្ងៃបុណ្យឈប់សម្រាកបន្ទាប់ និងចំនួនថ្ងៃដែលនៅសល់ |
| `/calendar` | បង្ហាញប្រតិទិនថ្ងៃឈប់សម្រាកផ្លូវការប្រចាំឆ្នាំ (២០២៥, ២០២៦, ២០២៧) |
| `/subscribe` | បើកការដាស់តឿនបុណ្យជាតិនាពេលទៀបភ្លឺ ៤:០០ ព្រឹក |
| `/unsubscribe`| បិទការដាស់តឿន |
| `/status` | ពិនិត្យស្ថានភាព Subscriber និងថ្ងៃឈប់សម្រាកថ្ងៃនេះ |
| `/test_alert` | សាកល្បងផ្ញើសារដាស់តឿន ៤:០០ ព្រឹកភ្លាមៗ (Test Preview) |
| `/help` | មើលការណែនាំអំពីរបៀបប្រើប្រាស់ |

---

## 💡 របៀបទាញយកវីដេអូ (Video Download Guide)

គ្រាន់តែ copy link វីដេអូពី៖
- **TikTok** (គាំទ្រទាំង link វែង និង link កាត់ `vt.tiktok.com`)
- **YouTube** (គាំទ្រ Shorts និងវីដេអូធម្មតា)
- **Facebook** (គាំទ្រ Reels, Watch និង Videos)
- **Instagram** (គាំទ្រ Reels និង Post)
- **X / Twitter**

រួច **Paste & Send** ចូលក្នុង Bot ជាការស្រេច! Bot នឹងឆ្លើយតប status និងផ្ញើ file វីដេអូ `.mp4` មកវិញភ្លាមៗ។
