# AniToon_1Bot 🎬

AniToon_1Bot is a Telegram media utility bot focused on **fast file renaming, format conversion and advanced media processing**.

It is built with **Python, Pyrogram, MongoDB/Motor and FFmpeg** and is designed for deployment on services such as Render, Railway, Koyeb, Docker or a Linux VPS.

## ✨ Main Features

- 📂 Accepts Telegram documents, videos and audio files
- ✏️ Custom Rename
- 🤖 Auto Rename with an anime-friendly filename detector
- 🛠 Advanced Rename
  - File name changes
  - Audio track names
  - Subtitle track names
- 🔄 Media conversion
  - MP4
  - MKV
  - WEBM
  - MOV
  - MP3
  - M4A
- 🖼 Custom thumbnails
- 📝 Custom captions through Settings
- 🏷 Audio/subtitle metadata controls through Settings
- 📊 Download and upload progress
- ⏳ Per-user job protection and processing queue
- 📦 Large-file splitting support
- 💎 Free, Pro, Premium and Ultra plans
- ⭐ Telegram Stars payments
- 🤖 Create your own AniToon clone bot
- 👑 Owner administration panel
- 🔐 Force Subscribe support
- 📢 Optional private log-channel backup
- 🌐 Hindi and English language resources

## 🧭 Start Page

The `/start` page is intentionally compact and uses an inline dashboard instead of a long list of commands.

### Main buttons

- 🛠 **Help** — bot usage and available features
- ⚙️ **Settings** — caption, thumbnail, metadata and plan settings
- ✏️ **Rename** — start the rename workflow by sending a file
- 🔄 **Convert** — start the conversion workflow by sending a file
- 🤖 **Create Your Own Clone Bot** — available on the main bot when cloning is enabled

The start page does **not** display instructions for `/setcaption` or `/metadata`.

## 📁 File Workflow

1. Send a video, document or audio file.
2. AniToon downloads and inspects the file.
3. Choose one of the available actions:
   - Custom Rename
   - Auto Rename
   - Convert
   - Advanced Rename
4. Complete the selected operation.
5. AniToon uploads the processed result back to the user.
6. If a log channel is configured, the processed file can also be copied there.

### Auto Rename

AniToon detects common filename information such as season, episode, resolution, audio type and codec, then presents the detected filename for confirmation before processing.

### Advanced Rename

Advanced Rename can change the output filename and, where supported by the media, rename audio and subtitle track titles before the final upload.

## 🔄 Conversion

Supported output formats exposed by the bot UI:

| Type | Formats |
|---|---|
| Video | MP4, MKV, WEBM, MOV |
| Audio | MP3, M4A |

The exact conversion behavior depends on the source media and FFmpeg support available on the deployment environment.

## 💎 Plans

| Plan | Price | Daily Limit |
|---|---:|---:|
| 🆓 Free | 0 ⭐ | 10 GB |
| ⚡ Pro | 10 ⭐ | 20 GB |
| 💎 Premium | 20 ⭐ | 40 GB |
| 👑 Ultra | 30 ⭐ | 60 GB |
| 👑 Owner | 0 ⭐ | Unlimited |

Paid plans are configured for 30 days.

The bot owner receives an internal unlimited plan automatically when `OWNER_ID` matches the Telegram numeric ID of the owner.

## ⭐ Telegram Stars

Premium upgrades use Telegram Stars. Payment processing and subscription activation are handled by the bot's premium module.

> Never put bot tokens, API hashes or database credentials in the repository.

## 🤖 Clone Bots

The main bot can create and manage clone instances when cloning is enabled.

Clone functionality uses the configured Bot API token and stores the required clone information in MongoDB.

Set:

```text
IS_CLONE_ALLOWED=true
```

to enable clone creation.

## 👑 Owner Panel

Set the owner's Telegram numeric ID in the deployment environment:

```text
OWNER_ID=YOUR_TELEGRAM_ID
```

The owner panel is available through the owner-only `/owner` handler and provides administration functions such as user management, plan management, broadcasting, bans, restart and clone management.

The owner also receives unlimited processing quota through the owner access module.

## 🔐 Force Subscribe

The current Force Subscribe configuration uses the public channels configured by the bot. A user must satisfy the configured public-channel membership checks before using the main bot.

The retired private Channel 4 is no longer part of the required Force Subscribe flow.

## ⚙️ Environment Variables

Required:

```text
API_ID=
API_HASH=
BOT_TOKEN=
DATABASE_URL=
```

Common optional settings:

```text
MAIN_BOT_USERNAME=
LOG_CHANNEL=0
FORCE_SUB=
FORCE_SUB_LINKS=
IS_CLONE_ALLOWED=true
ADMIN=
OWNER_ID=0
START_PIC=
```

`DATABASE_URL` may use the MongoDB connection string previously supplied through `MONGO_URI` as a fallback.

## 🚀 Deployment

### Render

Use a Python 3.11 environment and install dependencies from `requirements.txt`.

A health endpoint is available at:

```text
/health
```

### Local / VPS

Install FFmpeg and Python dependencies, configure the environment variables, then run:

```bash
python bot.py
```

## 🧱 Project Structure

```text
AniToon_1Bot/
├── bot.py
├── config.py
├── app.py
├── requirements.txt
├── runtime.txt
├── Procfile
├── Dockerfile
├── README.md
│
├── helper/
│   ├── database.py
│   ├── ffmpeg.py
│   ├── plans.py
│   ├── splitter.py
│   ├── utils.py
│   ├── job_state.py
│   └── clone_manager.py
│
└── plugins/
    ├── start.py
    ├── start_priority.py
    ├── start_ui.py
    ├── ui.py
    ├── rename.py
    ├── premium.py
    ├── admin.py
    ├── owner_access.py
    ├── metadata.py
    ├── caption.py
    └── thumb.py
```

## 🛡️ Design Principles

- Preserve existing processing logic when changing the UI.
- Prefer inline buttons over exposing a large command list.
- Validate user plans and quotas before processing.
- Keep owner-only administration separate from normal user controls.
- Use safe filenames and FFmpeg-backed media operations.
- Keep secrets in environment variables rather than source files.

## 📌 Public Commands

The Telegram command menu intentionally exposes only:

```text
/start — Open AniToon
/help  — Show help
```

Normal users should use the inline buttons for the rest of the bot functionality.
