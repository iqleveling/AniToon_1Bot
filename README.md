# AniToon_1Bot

AniToon_1Bot is a Telegram file processing and renaming bot built with Python, Pyrogram, MongoDB and FFmpeg.

## Features

- Automatic file detection
- File renaming
- Video, audio and document support
- Custom thumbnails
- Custom captions
- Internal audio/subtitle metadata processing
- Progress display
- Daily usage limits
- Free, Pro, Premium and Ultra plans
- Telegram Stars payments
- File splitting for large files
- Private log-channel backups
- Force Subscribe
- Hindi and English language support
- Bot cloning
- Main-owner administration dashboard

## Plans

| Plan | Stars | Daily Limit |
|------|------:|------------:|
| 🆓 Free | 0 ⭐ | 10 GB |
| ⚡ Pro | 10 ⭐ | 20 GB |
| 💎 Premium | 20 ⭐ | 40 GB |
| 👑 Ultra | 30 ⭐ | 60 GB |

Paid plans are valid for 30 days.

Large files are automatically split into smaller parts when necessary.

## Architecture

```text
AniToon_1Bot
│
├── bot.py
├── config.py
├── requirements.txt
├── app.py
├── Procfile
├── runtime.txt
├── Dockerfile
├── README.md
├── .gitignore
│
├── helper/
│   ├── utils.py
│   ├── database.py
│   ├── ffmpeg.py
│   ├── splitter.py
│   ├── plans.py
│   └── clone_manager.py
│
├── plugins/
│   ├── start.py
│   ├── thumb.py
│   ├── caption.py
│   ├── rename.py
│   ├── admin.py
│   ├── cb_data.py
│   ├── metadata.py
│   └── premium.py
│
└── language/
    ├── en.json
    └── hi.json
