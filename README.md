<div align="center">

# 🤖 Deendayal Button Bot

**A powerful, self-serve Telegram bot for creating rich, colored-button posts and broadcasting them across multiple channels & groups — no coding required.**

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![aiogram](https://img.shields.io/badge/aiogram-3.x-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://docs.aiogram.dev/)
[![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-47A248?style=for-the-badge&logo=mongodb&logoColor=white)](https://www.mongodb.com/atlas)
[![Render](https://img.shields.io/badge/Deploy-Render-46E3B7?style=for-the-badge&logo=render&logoColor=white)](https://render.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](#-license)

</div>

---

## 📖 Overview

**Deendayal Button Bot** lets anyone — with zero technical knowledge — build professional Telegram posts with colored inline buttons, rich formatting, and spoiler-protected images, then publish them instantly to any Channel or Group they administer. Every setting is controlled through an in-chat Settings menu, and all data survives redeploys via MongoDB persistence.

---

## ✨ Features

### 📝 Post Creation
- **Interactive post builder** (`/newpost`) — build text/photo posts step-by-step entirely in chat
- **Colored inline buttons** — 🟢 Green, 🔵 Blue, 🔴 Red, or ⚪ Default, per button
- **Live preview & editing** — review every button added so far and edit its name, URL, or color before publishing
- **Rich text formatting** — Bold (default), Italic, Spoiler, Monospace/Code, and Blockquote — all preserved from Telegram's native formatting tools
- **Photo support** — attach an image with caption, with optional spoiler/blur protection
- **Configurable button layout** — choose 1–4 buttons per row

### 📢 Multi-Channel Publishing
- Connect **unlimited Channels & Groups** to your account
- **Ownership verification** — only users who are admins of a channel/group can connect it
- One-tap **Telegram deep-links** for adding the bot as admin
- Publish a finished post to **any connected destination** with a single tap

### ⚙️ Settings & Personalization
- **Caption Format** — auto-wrap post text in Quote, Mono, or Spoiler
- **Image Settings** — default visibility or spoiler-blur for photos
- **Buttons Per Line** — customize your default layout
- All preferences persist per-user via MongoDB

### 📊 Admin & Analytics
- **`/stats`** — total users, total connected channels/groups, with clickable invite links (public or private)
- **`/broadcast`** — send an announcement to every user who has started the bot, with delivery report
- **Activity logging** — a dedicated log channel receives real-time alerts for new users and bot deploys/restarts

### 🛠️ Infrastructure
- Built on **aiogram 3** (async, Bot API–native)
- **MongoDB** persistence — channels, user preferences, and user base survive restarts
- **Render-ready** — includes a lightweight built-in web server so it deploys cleanly on Render's free Web Service tier

---

## 🗂️ Project Structure

```
.
├── bot.py              # Core bot logic (handlers, database, deployment glue)
├── script.py           # All user-facing text content (edit this to rebrand)
├── requirements.txt    # Python dependencies
└── Procfile            # Process definition for Render/Heroku
```

> 💡 **Tip:** To rebrand the bot (welcome message, About text, menu labels), you only need to edit `script.py` — no need to touch `bot.py`.

---

## 🚀 Getting Started

### Prerequisites

| Requirement | Where to get it |
|---|---|
| Telegram Bot Token | [@BotFather](https://t.me/BotFather) |
| MongoDB connection string *(optional but recommended)* | [MongoDB Atlas](https://www.mongodb.com/cloud/atlas) — free tier |
| Your Telegram User ID *(for admin features)* | [@userinfobot](https://t.me/userinfobot) |

### 1. Clone & Install

```bash
git clone <your-repo-url>
cd <your-repo-folder>
pip install -r requirements.txt
```

### 2. Configure Environment Variables

| Variable | Required | Description |
|---|---|---|
| `BOT_TOKEN` | ✅ Yes | Your bot token from BotFather |
| `MONGO_URI` | ⚠️ Recommended | MongoDB connection string — without it, data resets on every restart |
| `PICS` | ❌ Optional | Space-separated image URL(s) shown on `/start`. One URL = fixed image, multiple = random per visit |
| `LOG_CHANNEL_ID` | ❌ Optional | Channel ID (bot must be admin) to receive new-user and deploy alerts |
| `ADMIN_IDS` | ❌ Optional | Comma-separated Telegram user IDs allowed to run `/stats` and `/broadcast` |

### 3. Run Locally

```bash
python bot.py
```

---

## ☁️ Deploying to Render (Free Tier)

1. Push this repository to GitHub.
2. On [Render](https://render.com), create a **New → Web Service** (the built-in dummy web server keeps the free tier alive).
3. Set:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
4. Add your environment variables under the **Environment** tab.
5. Deploy — your bot will go live and post a startup notice to your log channel (if configured).

> ⚠️ **Uptime tip:** Render's free tier sleeps after inactivity. Pair it with a service like [UptimeRobot](https://uptimerobot.com) pinging your Render URL every 5 minutes to keep it awake.

---

## 💬 Commands Reference

| Command | Access | Description |
|---|---|---|
| `/start` | Everyone | Show the welcome screen with Channel/Group links and Settings |
| `/newpost` | Everyone | Launch the interactive post builder |
| `/addchannel` | Everyone | Connect a Channel or Group you administer |
| `/mychannels` | Everyone | List your connected Channels/Groups |
| `/stats` | Admins only | View bot-wide usage statistics |
| `/broadcast` | Admins only | Send a message to every bot user |

---

## 🎨 Customization

All editable content lives in **`script.py`**:

```python
MESSAGE_TEXT      # /start welcome message (supports HTML formatting + {user} mention)
MENU_BUTTON_TEXT  # Label for the Settings button
ABOUT_TEXT        # Content shown on the About screen
```

Button links and images are configured directly in `bot.py`'s `BUTTONS` and `START_IMAGES` sections.

---

## 🔒 Security Notes

- Users can only connect a Channel/Group they are personally an **admin** of — verified live against the Telegram API on every connection attempt.
- Admin-only commands (`/stats`, `/broadcast`) are gated behind `ADMIN_IDS`; if left unset, these commands are disabled for everyone.

---

## 🤝 Contributing

Issues and feature suggestions are welcome. Fork the repo, make your changes, and open a pull request.

---

## 📄 License

This project is licensed under the **MIT License** — free to use, modify, and distribute.

---

<div align="center">

**Built with ❤️ using aiogram, MongoDB, and Render**

</div>
