---
title: Telegram Smart Assistant Bot
emoji: 🇰🇭
colorFrom: blue
colorTo: indigo
sdk: gradio
sdk_version: 4.44.0
app_file: app.py
pinned: false
license: mit
---

# 🇰🇭 Telegram Smart Assistant Bot (Hub 4.0 Pro Ultimate)

Telegram Bot ជំនួយការឆ្លាតវៃពហុមុខងារ (Multi-purpose Smart Assistant Hub) បង្កើតឡើងយ៉ាងពិសេសសម្រាប់អ្នកប្រើប្រាស់នៅប្រទេសកម្ពុជា 🇰🇭។

---

## 🌟 មុខងារសំខាន់ៗ (Key Features)

### 1. 📄 អាន និងសង្ខេបឯកសារ PDF / Chat with PDF (`/pdf`)
- **សង្ខេបឯកសារ PDF ស្វ័យប្រវត្ត:** គ្រាន់តែ Forward ឬផ្ញើ File PDF (កិច្ចសន្យា, សៀវភៅ, មេរៀន, របាយការណ៍) ➔ AI អាន និងសង្ខេបចំណុចសំខាន់ៗជាភាសាខ្មែរភ្លាមៗ។
- **សួរសំណួរលម្អិត (Chat with PDF):** បងអាច Reply លើសារសង្ខេប ឬវាយ `/pdf <សំណួរ>` ដើម្បីសួរព័ត៌មានលម្អិតពីទំព័រណាមួយនៃឯកសារនោះបាន។

### 2. 🔍 បង្កើនគុណភាពរូបភាពឱ្យច្បាស់ HD (AI Image Enhancer & Super-Resolution)
- **កែប្រែរូបភាពចាស់ បែកព្រាល ឱ្យច្បាស់ HD:** ផ្ញើរូបភាពដោយភ្ជាប់ Caption `/enhance` ឬ Reply លើរូបភាពដោយវាយ `/enhance` ឬ `/upscale`
- បច្ចេកវិទ្យា Denoise, Lanczos-4 Super-Resolution (ពង្រីកទំហំ 2x-4x), Unsharp Masking និង CLAHE Lighting Enhancement ធ្វើឱ្យរូបភាពកាន់តែច្បាស់ស្អាតភ្លាមៗ។

### 3. 💧 បន្ថែម Watermark / Logo លើរូបភាពផលិតផល (`/watermark`)
- **បោះត្រាការពាររូបភាពទំនិញ:** វាយ `/watermark <ឈ្មោះហាង លេខទូរស័ព្ទ>` លើ Caption ឬ Reply លើរូបភាពណាមួយ
- Bot នឹងបោះត្រាជាទម្រង់ Glassmorphism Badge ថ្លាស្អាត ឬ Full Diagonal Watermark ការពារគេលួចចម្លងរូបភាពផលិតផល។

### 4. 🖼️ រូបភាពស្វាគមន៍សមាជិកថ្មីស្វ័យប្រវត្ត (Custom Welcome Banner)
- នៅពេលមានសមាជិកថ្មី Join Group ➔ Bot បង្កើតផ្ទាំង Banner 1200x600 ស្អាតៗកម្រិត HD ដោយមានដាក់រូប Profile, ឈ្មោះសមាជិក, និងឈ្មោះ Group ដោយស្វ័យប្រវត្តិ។
- កំណត់បើក/បិទសម្រាប់ Admin: `/welcome on` ឬ `/welcome off`។

### 5. 📊 កត់ត្រាចំណូល-ចំណាយផ្ទាល់ខ្លួន (Personal Expense & Income Tracker)
- **កត់ត្រាយ៉ាងរហ័ស:**
  - តាម Command: `/spend 5$ coffee`, `/spend 20,000៛ ញ៉ាំបាយ`, `/income 500$ monthly salary`
  - ឬវាយជាភាសាខ្មែរធម្មតា: `ចាយ 20,000៛ ញ៉ាំបាយ`, `ចំណាយ 15$ សាំងឡាន`, `ចំណូល 200$ លក់ទំនិញ`
- **របាយការណ៍សរុប (`/budget`):**
  - គណនាសមតុល្យសល់ (Balance) ទាំងប្រាក់ដុល្លារ ($) និងប្រាក់រៀល (៛)
  - បែងចែកតាមជំពូកចំណាយ (Categories: អាហារ, ធ្វើដំណើរ, ទិញទំនិញ, វិក្កយបត្រ, សុខភាព...)
  - បង្ហាញប្រវត្តិប្រតិបត្តិការចុងក្រោយ។

### 6. 🗣️ អានជាសំឡេងនិយាយភាសាខ្មែរ & អង់គ្លេស (Text-to-Speech)
- **បម្លែងអត្ថបទទៅជាសំឡេង:** វាយ `/speak <អត្ថបទ>` ឬ Reply លើសារណាមួយរួចវាយ `/speak`
- Bot នឹងបញ្ចេញសំឡេងនិយាយជាភាសាខ្មែរ ឬអង់គ្លេស (Voice Message) ផ្ញើត្រឡប់មកវិញភ្លាមៗ។

### 7. ✍️ ពិនិត្យអក្ខរាវិរុទ្ធខ្មែរ (Khmer Spellchecker & Chuon Nath Dictionary)
- វាយ `/check <អត្ថបទខ្មែរ>` ឬ Reply លើសារណាមួយដោយវាយ `/check`
- AI ជួយកែពាក្យខុសឱ្យត្រូវតាមក្បួនខ្នាតវចនានុក្រមសម្តេចព្រះសង្ឃរាជ **ជួន ណាត** និងកែលម្អឃ្លាប្រយោគឱ្យកាន់តែពិរោះ។

### 8. 🌐 បកប្រែភាសា Pro (English ⬄ Khmer with Audio)
- វាយ `/translate <អត្ថបទ>` ឬ `/tr <អត្ថបទ>`
- បកប្រែឯកសារ ឬឃ្លាស្មុគស្មាញពីរភាសាទៅវិញទៅមក រួមទាំងការបញ្ចេញសំឡេង និងការពន្យល់ពាក្យគន្លឹះ។

### 9. 🎧 ស្វែងរក និងទាញយកចម្រៀង MP3 320kbps (Music Finder)
- វាយឈ្មោះបទចម្រៀង ឬឈ្មោះតារា: `/song ស្រលាញ់គ្នាម្តងទៀតបានទេ` ឬ `/song shape of you`
- Bot នឹងស្វែងរក និងទាញយក file MP3 កម្រិតច្បាស់ (High Bitrate 320kbps) ព្រមទាំងមានរូប Cover Album និងឈ្មោះតារាចម្រៀងត្រឹមត្រូវ។

### 10. ✂️ កាត់ផ្ទៃខាងក្រោយរូបភាព (AI Background Remover)
- ផ្ញើរូបថតដោយដាក់ Caption ថា `/rembg` ឬ Reply លើរូបថតណាមួយដោយវាយ `/rembg`
- Bot នឹងកាត់ Background ចេញដោយស្វ័យប្រវត្តិក្លាយជា File PNG Transparent ក្នុងរយៈពេលតែ ១-២ វិនាទី។

### 11. 🔍 ស្វែងរកប្រភពបទភ្លេង TikTok (TikTok Sound Identifier)
- វាយ `/sound <Link វីដេអូ TikTok>`
- Bot ស្រង់យកឈ្មោះបទចម្រៀងដើម (Track Title) ឈ្មោះតារាចម្រៀង និង Album ពីក្នុងវីដេអូជូនភ្លាមៗ។

### 12. 🛡️ ប្រព័ន្ធការពារ Spam & Scam ក្នុង Group Telegram
- វាយ `/antispam on` ឬ `/antispam off` (សម្រាប់ Group Admin)
- លុបដោយស្វ័យប្រវត្តិនូវសារផ្សាយពាណិជ្ជកម្មល្បែងស៊ីសង (Casino Ads, Baccarat, Slot), Link មេរោគ និងគណនី Bot ក្លែងក្លាយ។

### 13. 📰 ព្រឹត្តិបត្រព័ត៌មានពេលព្រឹក ៧:០០ AM (Morning News Digest)
- ផ្ញើសេចក្តីសង្ខេបព័ត៌មានជាតិកម្ពុជា និងបច្ចេកវិទ្យាពិភពលោកចំនួន ៥ ដំណឹងជារៀងរាល់ព្រឹកម៉ោង ៧:០០ ព្រឹកស្វ័យប្រវត្តិ
- ឬមើលភ្លាមៗគ្រប់ពេលវេលាតាមរយៈ `/news`។

### 14. 📥 All-in-One Video Downloader (TikTok, YouTube, Facebook, IG, X)
- Copy link វីដេអូផ្ញើចូលទីនេះ ➔ Bot ទាញយកវីដេអូ HD (គ្មាន Watermark)
- មានប៊ូតុងទាញយក MP3 និង Cover HD ដោយស្វ័យប្រវត្តិ។

### 15. 💰 សេដ្ឋកិច្ចកម្ពុជា & ⏰ Reminders & 🌤️ អាកាសធាតុ
- អត្រាប្តូរប្រាក់ផ្លូវការ (NBC/USD/KHR/THB/EUR/CNY), តម្លៃមាស (តម្លឹង/ជី), តម្លៃប្រេងឥន្ធនៈ
- សារដាស់តឿនផ្ទាល់ខ្លួន `/remind 08:30 ជួបភ្ញៀវ`
- អាកាសធាតុ ៥:០០ ព្រឹក (មានឋានានុក្រម ភូមិ/ឃុំ/ស្រុក/ខេត្ត) និងបុណ្យជាតិ ៤:០០ ព្រឹក។

---

## 🎮 បញ្ជីពាក្យបញ្ជា (Bot Commands)

| Command | ការពិពណ៌នា (Description) |
|---|---|
| `/start` | បង្ហាញផ្ទាំង Dashboard មេ និង Menu បញ្ជា |
| `/budget` | មើលរបាយការណ៍សរុបចំណូល-ចំណាយ និងសមតុល្យ |
| `/spend <ចំនួន> <ចំណាំ>` | កត់ត្រាចំណាយ (ឧ. `/spend 5$ coffee` ឬ `ចាយ 20,000៛ បាយ`) |
| `/income <ចំនួន> <ចំណាំ>` | កត់ត្រាចំណូល (ឧ. `/income 500$ salary` ឬ `ចំណូល 200$ លក់ទំនិញ`) |
| `/song <ឈ្មោះបទ>` | ស្វែងរក និងទាញយកចម្រៀង MP3 320kbps |
| `/speak <អត្ថបទ>` | បម្លែងអក្សរទៅជាសំឡេងនិយាយខ្មែរ/អង់គ្លេស (TTS) |
| `/check <អត្ថបទ>` | ពិនិត្យអក្ខរាវិរុទ្ធ និងវេយ្យាករណ៍តាមវចនានុក្រម ជួន ណាត |
| `/translate <អត្ថបទ>` | បកប្រែភាសា Pro (English ⬄ Khmer) ជាមួយសំឡេង |
| `/pdf [សំណួរ]` | Chat with PDF & សង្ខេបឯកសារ PDF (កិច្ចសន្យា/សៀវភៅ/មេរៀន) |
| `/enhance` / `/upscale` | ធ្វើឱ្យរូបភាពចាស់ បែកព្រាល ឡើងច្បាស់ HD (Super-Resolution 2x-4x) |
| `/watermark <អត្ថបទ>` | បោះត្រា Watermark ការពាររូបភាពផលិតផល |
| `/welcome <on/off>` | *(Admin Only)* បើក/បិទ Custom Welcome Banner សម្រាប់សមាជិកថ្មីក្នុង Group |
| `/rembg` | កាត់ Background រូបថតក្លាយជា Transparent PNG |
| `/news` | មើលព្រឹត្តិបត្រសង្ខេបព័ត៌មានជាតិ និងបច្ចេកវិទ្យាពេលព្រឹក |
| `/sound <Link>` | ស្រង់យកឈ្មោះបទចម្រៀងដើមពីក្នុងវីដេអូ TikTok |
| `/antispam <on/off>` | បើក/បិទប្រព័ន្ធការពារ Spam & Casino Ads ក្នុង Group |
| `/finance` | មើលអត្រាប្តូរប្រាក់ តម្លៃមាស និងតម្លៃសាំងនៅកម្ពុជា |
| `/remind <ម៉ោង> <កិច្ចការ>` | កំណត់ម៉ោងដាស់តឿន (ឧ. `/remind 08:30 ជួបភ្ញៀវ`) |
| `/reminders` | មើលបញ្ជីសារដាស់តឿនរបស់អ្នក និងលុបចេញ |
| `/aimode` | បើក/បិទ AI Continuous Chat Mode (មិនបាច់វាយ /ask) |
| `/ask <សំណួរ>` | សួរសំណួរ AI មួយៗ (Google Gemini 3.8 Flash) |
| `/qr <អត្ថបទ/Link>` | បង្កើត QR Code រូបភាពភ្លាមៗ |
| `/weather` | មើលអាកាសធាតុបច្ចុប្បន្ននៅទីតាំងរបស់អ្នក |
| `/location` | កំណត់ទីតាំងសម្រាប់ដំណឹងអាកាសធាតុ ៥:០០ ព្រឹក |
| `/upcoming` | មើលថ្ងៃបុណ្យឈប់សម្រាកបន្ទាប់ និងចំនួនថ្ងៃនៅសល់ |
| `/calendar` | បង្ហាញប្រតិទិនថ្ងៃឈប់សម្រាកផ្លូវការប្រចាំឆ្នាំ |
| `/status` | ពិនិត្យស្ថានភាពគណនី និងការកំណត់ទាំងអស់ |
| `/help` | មើលការណែនាំអំពីរបៀបប្រើប្រាស់ |
| `/broadcast <សារ>` | *(Admin Only)* ផ្ញើដំណឹងទៅកាន់ User ទាំងអស់ |

---

## 🚀 របៀបដំណើរការ (Local Setup)

```bash
# 1. Clone repository
git clone https://github.com/cheat870/assistant_bot.git
cd assistant_bot

# 2. Install requirements
pip install -r requirements.txt

# 3. Setup .env file
# TELEGRAM_BOT_TOKEN="your_bot_token"
# GEMINI_API_KEY="your_gemini_key"

# 4. Run bot
python main.py
```

---

## 🌐 ដំណើរការ ២៤/៧ លើ Cloud (Render.com)
គម្រោងនេះមាន **Health Check HTTP Server** (Port 8080/10000) រួចជាស្រេចសម្រាប់ Cloud Deploy លើ **Render.com** (Web Service Free Tier)។ ភ្ជាប់ជាមួយ [UptimeRobot.com](https://uptimerobot.com) ដោយកំណត់ Check Interval **5 minutes** ដើម្បីកុំឱ្យ Render គេង (Keep-Alive 24/7)។
