"""
aiogram Bot with Colored URL Buttons (Green / Blue / Red) + Multi-Channel Posting
------------------------------------------------------------------------------------
Kurigram (MTProto) is naye button 'style' (color) feature ko support nahi karta,
isliye ab 'aiogram' use kar rahe hain jo seedha Telegram Bot API (HTTP) se baat
karta hai aur ye feature fully support karta hai.

FEATURES:
  /start       -> Demo message with colored buttons
  /newpost     -> Apna text + buttons (naam, URL, COLOR) khud bana kar post karo
  /addchannel  -> Apna channel connect karo (post karne ke liye)
  /mychannels  -> Connected channels ki list dekho

SETUP:
  1) pip install aiogram --upgrade
  2) @BotFather se BOT_TOKEN lo
  3) Neeche BOT_TOKEN daalo (ya environment variable set karo)
  4) Run karo: python aiogram_color_button_bot.py

Agar BOT_TOKEN missing hoga, bot clear error dega, crash nahi karega.
"""

import os
import sys
import asyncio
import random
import json
import time
import hmac
import hashlib
import base64
import urllib.parse
from aiohttp import web

from aiogram import Bot, Dispatcher, F, BaseMiddleware
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    TelegramObject, WebAppInfo, BufferedInputFile,
)
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from motor.motor_asyncio import AsyncIOMotorClient

# =========================================================
# CONFIG -- yaha apni values daalo
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")   # @BotFather se
MONGO_URI = os.environ.get("MONGO_URI", "")   # MongoDB connection string (optional par recommended)

# Jis channel me bot ki activity logs (new user, deploy/restart) bhejni hain.
# Bot us channel me ADMIN hona chahiye. ID -100 se shuru hoti hai. Khaali chhodo to logs off.
LOG_CHANNEL_ID = os.environ.get("LOG_CHANNEL_ID", "").strip()

# Sirf inn Telegram user IDs ko /broadcast aur /stats jaise admin-only commands
# use karne dena hai (comma se separate karke, jaise "123456789,987654321").
# Apni ID pata karne ke liye @userinfobot ko /start karo.
ADMIN_IDS = {int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().lstrip("-").isdigit()}

# Mini App (Telegram WebApp) kaha hosted hai. Render deploy karne par ye apne aap
# mil jata hai (RENDER_EXTERNAL_URL). Khud host kar rahe ho to yaha manually daal do.
WEBAPP_BASE_URL = os.environ.get("RENDER_EXTERNAL_URL", os.environ.get("WEBAPP_BASE_URL", "")).rstrip("/")

import html

# Saara customizable TEXT script.py se aata hai.
# Text change karne ke liye bot.py nahi, script.py edit karo.
from script import MESSAGE_TEXT, MENU_BUTTON_TEXT, ABOUT_TEXT

# Har button: (button_text, url, style)
# style options: "success" (green), "primary" (blue), "danger" (red), None (default)
BUTTONS = [
    [("📢 Channel", "https://t.me/Deendayal_dhakadd", "success"),
     ("👥 Group", "https://t.me/Deendayal_dhakadd", "success")],
]

# /start message ke saath image dikhani hai to PICS environment variable me
# URL daalo. Multiple URLs (space se separate) doge to har baar random ek choose hogi;
# ek hi URL doge to hamesha wahi image dikhegi.
START_IMAGES = os.environ.get(
    'PICS',
    'https://i.ibb.co/wNcw3tMY/photo-2026-08-29-04-38-12-7679308298687873056.jpg'
).split()
# =========================================================

if not BOT_TOKEN:
    print("\n❌ BOT_TOKEN missing hai. Isse environment variable ki tarah set karo,")
    print("   ya seedha script ke CONFIG section me daalo.\n")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

BOT_USERNAME = ""  # startup par init_db se pehle fetch hoga
START_TIME = time.time()  # bot kab start hua (uptime calculate karne ke liye)

# User ke chat state track karne ke liye (memory me, restart hone par reset ho jayega)
user_states = {}

# User ne jo channels connect kiye hain (memory me cache, MongoDB se load hota hai)
# Structure: { user_id: [ {"id": -1001234, "title": "My Channel"}, ... ] }
CONNECTED_CHANNELS = {}

channels_collection = None  # MongoDB connect hone ke baad set hoga
settings_collection = None  # MongoDB connect hone ke baad set hoga (Caption Format + Image Spoiler)
users_collection = None     # MongoDB connect hone ke baad set hoga (broadcast/stats ke liye)

# Bot ko ab tak jitne users ne /start kiya hai (memory cache, MongoDB se load hota hai)
ALL_USERS = set()


async def send_log(text):
    """LOG_CHANNEL_ID set hai to wahan message bhejta hai (fail ho to silently ignore)."""
    if not LOG_CHANNEL_ID:
        return
    try:
        await bot.send_message(int(LOG_CHANNEL_ID), text, parse_mode="HTML")
    except Exception as e:
        print(f"⚠️ Log channel me message nahi bhej paya: {e}")


async def track_user(user):
    """Naya user hai to save karo aur log channel me bata do."""
    if user.id in ALL_USERS:
        return
    ALL_USERS.add(user.id)
    if users_collection is not None:
        try:
            await users_collection.update_one(
                {"user_id": user.id},
                {"$set": {"user_id": user.id, "name": user.full_name, "username": user.username}},
                upsert=True
            )
        except Exception as e:
            print(f"⚠️ User DB me save nahi ho paya: {e}")

    mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    username_line = f"@{user.username}" if user.username else "N/A"
    await send_log(
        f"🆕 <b>New User Started Bot</b>\n"
        f"👤 Name: {mention}\n"
        f"🔗 Username: {username_line}\n"
        f"🆔 ID: <code>{user.id}</code>\n"
        f"📊 Total Users: {len(ALL_USERS)}"
    )


async def track_user_dict(user: dict):
    """Mini App (Telegram WebApp initData) se aaya plain JSON user object handle karta hai."""
    uid = user.get("id")
    if uid is None or uid in ALL_USERS:
        return
    ALL_USERS.add(uid)
    full_name = " ".join(filter(None, [user.get("first_name"), user.get("last_name")])) or "Unknown"
    username = user.get("username")
    if users_collection is not None:
        try:
            await users_collection.update_one(
                {"user_id": uid},
                {"$set": {"user_id": uid, "name": full_name, "username": username}},
                upsert=True
            )
        except Exception as e:
            print(f"⚠️ User DB me save nahi ho paya: {e}")

    mention = f'<a href="tg://user?id={uid}">{html.escape(full_name)}</a>'
    username_line = f"@{username}" if username else "N/A"
    await send_log(
        f"🆕 <b>New User Started Bot (Mini App)</b>\n"
        f"👤 Name: {mention}\n"
        f"🔗 Username: {username_line}\n"
        f"🆔 ID: <code>{uid}</code>\n"
        f"📊 Total Users: {len(ALL_USERS)}"
    )

# User ne apna caption format kya choose kiya hai (Quote/Mono/Spoiler/None)
# Structure: { user_id: "quote" | "mono" | "spoiler" | None }
USER_FORMAT = {}

# User ne image spoiler (hide) chuna hai ya default
# Structure: { user_id: True (spoiler) | False (default) }
USER_IMAGE_SPOILER = {}

# User ek line me kitne buttons chahta hai (1-4), None = default (1 per line)
# Structure: { user_id: 1 | 2 | 3 | 4 | None }
USER_BUTTONS_PER_ROW = {}


def is_admin(user_id):
    return bool(ADMIN_IDS) and user_id in ADMIN_IDS


async def get_chat_link(chat_id):
    """Public ho to @username link, private ho to invite link banane ki koshish karta hai."""
    try:
        chat = await bot.get_chat(chat_id)
        if chat.username:
            return f"https://t.me/{chat.username}"
        link = await bot.create_chat_invite_link(chat_id)
        return link.invite_link
    except Exception:
        return None


def chunk_buttons(buttons, per_row):
    """Buttons ki flat list ko per_row size ke rows me todta hai."""
    per_row = per_row or 1
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


async def edit_smart(message, text, markup=None, parse_mode=None):
    """Message photo wala hai to caption edit karo, warna normal text edit karo.
    (Zaroori hai kyunki /start ab image ke saath bhi ho sakta hai.)"""
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=markup, parse_mode=parse_mode)
    else:
        await message.edit_text(text, reply_markup=markup, parse_mode=parse_mode)


def build_channel_list(uid):
    """Connected channels ki list + Add/Back buttons banata hai. (text, markup) return karta hai."""
    channels = CONNECTED_CHANNELS.get(uid, [])
    kb = [[InlineKeyboardButton(text="➕ Connect New Channel/Group", callback_data="menu_addchannel")]]
    kb += [
        [InlineKeyboardButton(text=f"📢 {c['title']}", callback_data=f"manage_channel_{c['id']}")]
        for c in channels
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_start")])
    text = "🔗 Aapke connected channels/groups:" if channels else "Abhi koi channel/group connect nahi hai."
    return text, InlineKeyboardMarkup(inline_keyboard=kb)


async def send_start_view(chat_id, prefix="", user=None):
    """/start jaisa screen bhejta hai (image + text + buttons), aage ek chhota
    confirmation note bhi jod sakte ho (jaise 'Channel connect ho gaya!').
    'user' diya ho to uska clickable naam {user} ki jagah dikhega."""
    keyboard = [
        [InlineKeyboardButton(text="🔗 Connect Channel/Group", callback_data="menu_channels")],
    ]

    if WEBAPP_BASE_URL:
        keyboard.append([InlineKeyboardButton(
            text="🚀 Open Mini App",
            web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}/app")
        )])

    keyboard += [
        [InlineKeyboardButton(text=text, url=url, style=style) for text, url, style in row]
        for row in BUTTONS
    ]
    keyboard.append([
        InlineKeyboardButton(text=MENU_BUTTON_TEXT, callback_data="main_menu"),
        InlineKeyboardButton(text="ℹ️ About", callback_data="show_about"),
    ])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if user is not None:
        mention = f'<a href="tg://user?id={user.id}">{html.escape(user.full_name)}</a>'
    else:
        mention = ""
    body = MESSAGE_TEXT.format(user=mention)

    safe_prefix = html.escape(prefix) if prefix else ""
    caption = f"{safe_prefix}\n\n{body}" if safe_prefix else body

    if START_IMAGES:
        image = random.choice(START_IMAGES)
        await bot.send_photo(chat_id, photo=image, caption=caption, reply_markup=markup, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, caption, reply_markup=markup, parse_mode="HTML")


async def init_db():
    """MongoDB se connect karo aur pehle se saved channels + settings + users memory me load karo."""
    global channels_collection, settings_collection, users_collection
    if not MONGO_URI:
        print("⚠️ MONGO_URI nahi diya gaya - channels/settings/users sirf memory me rahenge "
              "(restart hone par dobara set karna padega).")
        return

    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client["telegram_bot"]
        channels_collection = db["channels"]
        settings_collection = db["user_settings"]
        users_collection = db["users"]

        count = 0
        async for doc in channels_collection.find():
            CONNECTED_CHANNELS.setdefault(doc["user_id"], [])
            CONNECTED_CHANNELS[doc["user_id"]].append({"id": doc["channel_id"], "title": doc["title"]})
            count += 1

        settings_count = 0
        async for doc in settings_collection.find():
            USER_FORMAT[doc["user_id"]] = doc.get("format")
            USER_IMAGE_SPOILER[doc["user_id"]] = doc.get("image_spoiler", False)
            USER_BUTTONS_PER_ROW[doc["user_id"]] = doc.get("buttons_per_row")
            settings_count += 1

        user_count = 0
        async for doc in users_collection.find():
            ALL_USERS.add(doc["user_id"])
            user_count += 1

        print(f"✅ MongoDB connect ho gaya. {count} channel(s), {settings_count} setting(s), {user_count} user(s) load ho gaye.")
    except Exception as e:
        print(f"❌ MongoDB se connect nahi ho paya: {e}")
        print("   Channels/settings/users sirf memory me rahenge (restart pe reset honge).")


# ---------------------------------------------------------
# /start -- demo message with colored buttons
# ---------------------------------------------------------
@dp.message(CommandStart())
async def start(message: Message):
    await track_user(message.from_user)
    await send_start_view(message.chat.id, user=message.from_user)


# ---------------------------------------------------------
# Settings menu -- Connect Channel + Caption Format
# ---------------------------------------------------------
@dp.callback_query(F.data == "show_about")
async def show_about(callback: CallbackQuery):
    kb = [[InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_start")]]
    await edit_smart(callback.message, ABOUT_TEXT, InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="📝 Caption Format", callback_data="menu_format"),
         InlineKeyboardButton(text="🖼️ Image Settings", callback_data="menu_image")],
        [InlineKeyboardButton(text="🔲 Buttons Per Line", callback_data="menu_perrow")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_start")],
    ]
    await edit_smart(callback.message, "⚙️ Settings Menu", InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text="🔗 Connect Channel/Group", callback_data="menu_channels")],
    ]
    if WEBAPP_BASE_URL:
        keyboard.append([InlineKeyboardButton(
            text="🚀 Open Mini App",
            web_app=WebAppInfo(url=f"{WEBAPP_BASE_URL}/app")
        )])
    keyboard += [
        [InlineKeyboardButton(text=text, url=url, style=style) for text, url, style in row]
        for row in BUTTONS
    ]
    keyboard.append([
        InlineKeyboardButton(text=MENU_BUTTON_TEXT, callback_data="main_menu"),
        InlineKeyboardButton(text="ℹ️ About", callback_data="show_about"),
    ])
    mention = f'<a href="tg://user?id={callback.from_user.id}">{html.escape(callback.from_user.full_name)}</a>'
    body = MESSAGE_TEXT.format(user=mention)
    await edit_smart(callback.message, body, InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data == "menu_channels")
async def menu_channels(callback: CallbackQuery):
    text, markup = build_channel_list(callback.from_user.id)
    await edit_smart(callback.message, text, markup)
    await callback.answer()


@dp.callback_query(F.data == "menu_addchannel")
async def menu_addchannel(callback: CallbackQuery):
    user_states[callback.from_user.id] = {
        "step": "add_channel",
        "steps_chat_id": callback.message.chat.id,
        "steps_msg_id": callback.message.message_id,
    }
    await edit_smart(
        callback.message,
        "📢 Channel ya Group connect karne ke steps:\n\n"
        "1) Bot ko add karo:\n"
        "   • Channel me: bot ko ADMIN banao (post permission ke saath)\n"
        "   • Group me: bot ko bas MEMBER ki tarah add karo, admin zaroori nahi\n\n"
        "2) Yaha bhejo:\n"
        "   • PUBLIC ho to uska username (jaise @mychannel)\n"
        "   • PRIVATE ho to uski numeric ID (-100 se shuru hoti hai), "
        "ya wahan se koi message yaha FORWARD kardo",
        InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Back", callback_data="cancel_addchannel")]])
    )
    await callback.answer()


@dp.callback_query(F.data == "cancel_addchannel")
async def cancel_addchannel(callback: CallbackQuery):
    user_states.pop(callback.from_user.id, None)
    await menu_channels(callback)


@dp.callback_query(F.data.startswith("manage_channel_"))
async def manage_channel(callback: CallbackQuery):
    chat_id = int(callback.data.split("_", 2)[2])
    uid = callback.from_user.id
    channel = next((c for c in CONNECTED_CHANNELS.get(uid, []) if c["id"] == chat_id), None)
    if not channel:
        await callback.answer("Channel nahi mila.", show_alert=True)
        return
    kb = [
        [InlineKeyboardButton(text="❌ Remove", callback_data=f"remove_channel_{chat_id}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="menu_channels")],
    ]
    await edit_smart(callback.message, f"📢 {channel['title']}", InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("remove_channel_"))
async def remove_channel(callback: CallbackQuery):
    chat_id = int(callback.data.split("_", 2)[2])
    uid = callback.from_user.id
    CONNECTED_CHANNELS[uid] = [c for c in CONNECTED_CHANNELS.get(uid, []) if c["id"] != chat_id]
    if channels_collection is not None:
        await channels_collection.delete_one({"user_id": uid, "channel_id": chat_id})
    await callback.answer("✅ Channel remove ho gaya.", show_alert=True)
    await menu_channels(callback)  # list dobara dikhao, updated


@dp.callback_query(F.data == "menu_format")
async def menu_format(callback: CallbackQuery):
    current = USER_FORMAT.get(callback.from_user.id)
    kb = [
        [InlineKeyboardButton(text=("✅ " if current is None else "") + "⚪ Default (bold only)", callback_data="format_none")],
        [InlineKeyboardButton(text=("✅ " if current == "quote" else "") + "❝ Quote", callback_data="format_quote"),
         InlineKeyboardButton(text=("✅ " if current == "mono" else "") + "🔤 Mono", callback_data="format_mono")],
        [InlineKeyboardButton(text=("✅ " if current == "spoiler" else "") + "🙈 Spoiler", callback_data="format_spoiler")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
    ]
    await edit_smart(
        callback.message,
        "📝 /newpost me jo text bhejoge, wo is format me wrap hoga:",
        InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("format_"))
async def set_format(callback: CallbackQuery):
    uid = callback.from_user.id
    choice = callback.data.split("_", 1)[1]  # quote / mono / spoiler / none
    USER_FORMAT[uid] = None if choice == "none" else choice

    if settings_collection is not None:
        await settings_collection.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "format": USER_FORMAT[uid]}},
            upsert=True
        )

    await callback.answer("✅ Format set ho gaya!")
    await menu_format(callback)  # updated tick mark ke saath dobara dikhao


@dp.callback_query(F.data == "menu_image")
async def menu_image(callback: CallbackQuery):
    is_spoiler = USER_IMAGE_SPOILER.get(callback.from_user.id, False)
    kb = [
        [InlineKeyboardButton(text=("✅ " if is_spoiler else "") + "🙈 Hide with Spoiler", callback_data="image_spoiler")],
        [InlineKeyboardButton(text=("✅ " if not is_spoiler else "") + "🖼️ Default (visible)", callback_data="image_default")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
    ]
    await edit_smart(
        callback.message,
        "🖼️ /newpost me jo PHOTO bhejoge, wo is setting ke hisaab se post hogi:",
        InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(F.data.in_({"image_spoiler", "image_default"}))
async def set_image_setting(callback: CallbackQuery):
    uid = callback.from_user.id
    USER_IMAGE_SPOILER[uid] = (callback.data == "image_spoiler")

    if settings_collection is not None:
        await settings_collection.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "image_spoiler": USER_IMAGE_SPOILER[uid]}},
            upsert=True
        )

    await callback.answer("✅ Setting save ho gayi!")
    await menu_image(callback)  # updated tick mark ke saath dobara dikhao


@dp.callback_query(F.data == "menu_perrow")
async def menu_perrow(callback: CallbackQuery):
    current = USER_BUTTONS_PER_ROW.get(callback.from_user.id)

    def opt(n):
        tick = "✅ " if current == n else ""
        return InlineKeyboardButton(text=f"{tick}{n} button{'s' if n > 1 else ''} per line", callback_data=f"perrow_{n}")

    kb = [
        [InlineKeyboardButton(text=("✅ " if current is None else "") + "⚪ Default (1 per line)", callback_data="perrow_default")],
        [opt(1), opt(2)],
        [opt(3), opt(4)],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")],
    ]
    await edit_smart(
        callback.message,
        "🔲 /newpost me buttons ek line me kitne dikhein?",
        InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("perrow_"))
async def set_perrow(callback: CallbackQuery):
    uid = callback.from_user.id
    value = callback.data.split("_", 1)[1]  # "1"/"2"/"3"/"4"/"default"
    per_row = None if value == "default" else int(value)
    USER_BUTTONS_PER_ROW[uid] = per_row

    if settings_collection is not None:
        await settings_collection.update_one(
            {"user_id": uid},
            {"$set": {"user_id": uid, "buttons_per_row": per_row}},
            upsert=True
        )

    await callback.answer("✅ Setting save ho gayi!")
    await menu_perrow(callback)  # updated tick mark ke saath dobara dikhao


# ---------------------------------------------------------
# /addchannel -- channel connect karo
# ---------------------------------------------------------
@dp.message(Command("addchannel"))
async def addchannel_cmd(message: Message):
    sent = await message.answer(
        "📢 Channel ya Group connect karne ke steps:\n\n"
        "1) Bot ko add karo:\n"
        "   • Channel me: bot ko ADMIN banao (post permission ke saath)\n"
        "   • Group me: bot ko bas MEMBER ki tarah add karo, admin zaroori nahi\n\n"
        "2) Yaha bhejo:\n"
        "   • PUBLIC ho to uska username (jaise @mychannel)\n"
        "   • PRIVATE ho to uski numeric ID (-100 se shuru hoti hai), "
        "ya wahan se koi message yaha FORWARD kardo"
    )
    user_states[message.from_user.id] = {
        "step": "add_channel",
        "steps_chat_id": sent.chat.id,
        "steps_msg_id": sent.message_id,
    }


@dp.message(Command("mychannels"))
async def mychannels_cmd(message: Message):
    channels = CONNECTED_CHANNELS.get(message.from_user.id, [])
    if not channels:
        await message.answer("Abhi koi channel connect nahi hai. /addchannel use karo.")
        return
    text = "📋 Aapke connected channels:\n\n" + "\n".join(f"• {c['title']}" for c in channels)
    await message.answer(text)


@dp.message(Command("stats"))
async def stats_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Ye command sirf admin use kar sakte hain.")
        return

    status_msg = await message.answer("⏳ Stats collect kar raha hoon...")

    # Saare users ke connected channels/groups ko dedupe karke ek list banao
    all_chats = {}
    for uid, chats in CONNECTED_CHANNELS.items():
        for c in chats:
            all_chats[c["id"]] = c["title"]

    lines = [
        "📊 <b>Bot Stats</b>\n",
        f"👥 Total Users: <b>{len(ALL_USERS)}</b>",
        f"📢 Total Connected Channels/Groups: <b>{len(all_chats)}</b>\n",
    ]

    for chat_id, title in all_chats.items():
        link = await get_chat_link(chat_id)
        if link:
            lines.append(f"• <a href=\"{link}\">{html.escape(title)}</a>")
        else:
            lines.append(f"• {html.escape(title)} (ID: <code>{chat_id}</code>)")

    await status_msg.edit_text("\n".join(lines), parse_mode="HTML", disable_web_page_preview=True)


@dp.message(Command("broadcast"))
async def broadcast_cmd(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("🚫 Ye command sirf admin use kar sakte hain.")
        return
    user_states[message.from_user.id] = {"step": "broadcast_wait"}
    await message.answer("📢 Jo bhi message broadcast karna hai wo bhejo (text, photo — jo bhi):")


@dp.callback_query(F.data == "bcast_yes")
async def broadcast_send(callback: CallbackQuery):
    uid = callback.from_user.id
    state = user_states.get(uid)
    if not state or "broadcast_msg_id" not in state:
        await callback.answer("Session expire ho gaya.", show_alert=True)
        return

    await callback.message.edit_text("⏳ Broadcast bhej raha hoon...")
    success, failed = 0, 0
    for target_id in list(ALL_USERS):
        try:
            await bot.copy_message(target_id, from_chat_id=state["broadcast_chat_id"], message_id=state["broadcast_msg_id"])
            success += 1
        except Exception:
            failed += 1
        await asyncio.sleep(0.05)  # Telegram flood limits se bachne ke liye

    await callback.message.edit_text(
        f"✅ <b>Broadcast Complete</b>\n\n"
        f"👥 Total: {len(ALL_USERS)}\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}",
        parse_mode="HTML"
    )
    del user_states[uid]
    await callback.answer()


@dp.callback_query(F.data == "bcast_no")
async def broadcast_cancel(callback: CallbackQuery):
    user_states.pop(callback.from_user.id, None)
    await callback.message.edit_text("❌ Broadcast cancel kar diya gaya.")
    await callback.answer()


# ---------------------------------------------------------
# /newpost -- apna post banao
# ---------------------------------------------------------
@dp.message(Command("newpost"))
async def newpost(message: Message):
    user_states[message.from_user.id] = {"step": "text", "buttons": [], "photo": None}
    await message.answer(
        "📝 Apna post banana shuru karte hain.\n\n"
        "TEXT bhejo (ya PHOTO bhejo caption ke saath) jo buttons ke UPAR dikhega:"
    )


# ---------------------------------------------------------
# Saara text/forwarded input yahi handle karta hai (jo commands nahi hain)
# ---------------------------------------------------------
@dp.message(F.text | F.forward_origin | F.photo)
async def collect_input(message: Message):
    uid = message.from_user.id
    if uid not in user_states:
        return  # koi active flow nahi hai, ignore karo

    state = user_states[uid]
    step = state["step"]

    if step == "broadcast_wait":
        state["broadcast_chat_id"] = message.chat.id
        state["broadcast_msg_id"] = message.message_id
        await message.answer(
            f"👀 Preview upar hai. Ye {len(ALL_USERS)} users ko bhej du?",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(text="✅ Haan, bhejo", callback_data="bcast_yes"),
                InlineKeyboardButton(text="❌ Cancel", callback_data="bcast_no"),
            ]])
        )
        return

    if step == "add_channel":
        if not (message.text or message.forward_origin):
            await message.answer("⚠️ Channel username bhejo ya us channel se message forward karo.")
            return
        try:
            chat = None
            # Forward se seedha chat info milta hai (channel ya group dono ke liye)
            if message.forward_origin:
                origin = message.forward_origin
                if origin.type == "channel":
                    chat = origin.chat
                elif origin.type == "chat":
                    chat = origin.sender_chat

            if chat is None:
                if not message.text:
                    await message.answer(
                        "⚠️ Is forward se channel/group pata nahi chal paya (privacy ki wajah se). "
                        "Username ya numeric ID TEXT me bhejo."
                    )
                    return
                chat_ref = message.text.strip()
                chat = await bot.get_chat(chat_ref)

            member = await bot.get_chat_member(chat.id, bot.id)

            if chat.type == "channel":
                # Channel me post karne ke liye bot ka ADMIN hona zaroori hai
                if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                    await message.answer(
                        "⚠️ Bot is Channel me ADMIN nahi hai. Pehle admin banao "
                        "(post karne ki permission ke saath), phir dobara try karo."
                    )
                    return
            else:
                # Group/Supergroup me sirf member hona bhi kaafi hai (admin zaroori nahi)
                if member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
                    await message.answer(
                        "⚠️ Bot is Group me add nahi hai. Pehle bot ko group me add karo, "
                        "phir dobara try karo."
                    )
                    return

            # Connect karne wala USER khud us channel/group me ADMIN hona chahiye
            # (warna koi bhi random user kisi bhi channel/group connect kar sakta tha)
            user_member = await bot.get_chat_member(chat.id, uid)
            if user_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                await message.answer(
                    "⚠️ Aap is Channel/Group me ADMIN nahi hain. Sirf admin hi apna "
                    "channel/group is bot se connect kar sakte hain."
                )
                return

            CONNECTED_CHANNELS.setdefault(uid, [])
            if not any(c["id"] == chat.id for c in CONNECTED_CHANNELS[uid]):
                CONNECTED_CHANNELS[uid].append({"id": chat.id, "title": chat.title})

            # MongoDB me bhi save karo taaki restart ke baad bhi yaad rahe
            if channels_collection is not None:
                await channels_collection.update_one(
                    {"user_id": uid, "channel_id": chat.id},
                    {"$set": {"user_id": uid, "channel_id": chat.id, "title": chat.title}},
                    upsert=True
                )

            # Purana "steps" wala message hata do taaki clutter na ho
            try:
                await bot.delete_message(state.get("steps_chat_id", uid), state.get("steps_msg_id"))
            except Exception:
                pass

            # Saaf start-view dikhao, upar ek chhota confirmation note ke saath
            await send_start_view(uid, prefix=f"✅ '{chat.title}' connect ho gaya!", user=message.from_user)
        except Exception as e:
            await message.answer(
                f"❌ Channel connect nahi ho paya.\n"
                f"Public ho to @username check karo. Private ho to message forward karo.\n\n"
                f"(Error: {e})"
            )
        del user_states[uid]
        return

    if step == "editing_name":
        if not message.text:
            await message.answer("⚠️ Naya naam TEXT me bhejo:")
            return
        i = state["editing_index"]
        _, url, style = state["buttons"][i]
        state["buttons"][i] = (message.text, url, style)
        state["step"] = "ask_more"
        text, markup = preview_view(state)
        await message.answer("✅ Naam update ho gaya!")
        await message.answer(text, reply_markup=markup)
        return

    if step == "editing_url":
        if not message.text or not message.text.strip().startswith("http"):
            await message.answer("⚠️ URL http:// ya https:// se shuru honi chahiye. Dobara bhejo:")
            return
        i = state["editing_index"]
        name, _, style = state["buttons"][i]
        state["buttons"][i] = (name, message.text.strip(), style)
        state["step"] = "ask_more"
        text, markup = preview_view(state)
        await message.answer("✅ URL update ho gaya!")
        await message.answer(text, reply_markup=markup)
        return

    if step == "text":
        # message.html_text formatting preserve karta hai jo user ne apply ki ho
        # (bold, italic, spoiler, quote, code/copy-able block, wagera).
        # Upar se, Settings me jo format (Quote/Mono/Spoiler) choose kiya hai wo bhi
        # wrap hoga, aur poora text by-default BOLD rahega.
        def apply_format(raw_html: str) -> str:
            fmt = USER_FORMAT.get(uid)
            if fmt == "quote":
                raw_html = f"<blockquote>{raw_html}</blockquote>"
            elif fmt == "mono":
                raw_html = f"<code>{raw_html}</code>"
            elif fmt == "spoiler":
                raw_html = f"<tg-spoiler>{raw_html}</tg-spoiler>"
            return f"<b>{raw_html}</b>"

        if message.photo:
            state["photo"] = message.photo[-1].file_id  # sabse badi resolution wali photo
            caption = message.html_text or ""
            state["text"] = apply_format(caption) if caption else ""
        elif message.text:
            state["photo"] = None
            state["text"] = apply_format(message.html_text)
        else:
            await message.answer("⚠️ TEXT ya PHOTO (caption ke saath) bhejo:")
            return
        state["step"] = "button_name"
        await message.answer("🔘 Ab pehle button ka NAAM bhejo (jaise: Website):")

    elif step == "button_name":
        if not message.text:
            await message.answer("⚠️ Button ka naam TEXT me bhejo:")
            return
        state["current_name"] = message.text
        state["step"] = "button_url"
        await message.answer("🔗 Ab is button ka URL bhejo (https:// se shuru hona chahiye):")

    elif step == "button_url":
        if not message.text:
            await message.answer("⚠️ URL TEXT me bhejo:")
            return
        url = message.text.strip()
        if not url.startswith("http"):
            await message.answer("⚠️ URL http:// ya https:// se shuru honi chahiye. Dobara bhejo:")
            return
        state["current_url"] = url
        state["step"] = "choose_color"
        await message.answer(
            "🎨 Is button ka COLOR choose karo:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🟢 Green", callback_data="color_success")],
                [InlineKeyboardButton(text="🔵 Blue", callback_data="color_primary")],
                [InlineKeyboardButton(text="🔴 Red", callback_data="color_danger")],
                [InlineKeyboardButton(text="⚪ Default", callback_data="color_none")],
            ])
        )


# ---------------------------------------------------------
# Color choose karne ke baad
# ---------------------------------------------------------
@dp.callback_query(F.data.startswith("color_"))
async def handle_color(callback: CallbackQuery):
    uid = callback.from_user.id
    state = user_states.get(uid)
    if not state or "current_url" not in state:
        await callback.answer("Session expire ho gaya, /newpost dobara bhejo.", show_alert=True)
        return

    style_map = {"color_success": "success", "color_primary": "primary",
                 "color_danger": "danger", "color_none": None}
    style = style_map[callback.data]

    state["buttons"].append((state["current_name"], state["current_url"], style))
    state["step"] = "ask_more"
    text, markup = ask_more_view(state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


async def send_final_post(chat_id, state, markup, uid=None):
    """State me photo hai to photo+caption bhejo, warna sirf text bhejo.
    uid diya ho to uski spoiler-setting ke hisaab se photo hide/visible hogi."""
    if state.get("photo"):
        spoiler = USER_IMAGE_SPOILER.get(uid, False) if uid is not None else False
        await bot.send_photo(chat_id, photo=state["photo"], caption=state["text"],
                              reply_markup=markup, parse_mode="HTML", has_spoiler=spoiler)
    else:
        await bot.send_message(chat_id, state["text"], reply_markup=markup, parse_mode="HTML")


def ask_more_view(state):
    """'Aur button add karna hai?' screen. Preview/Edit option tabhi dikhta hai
    jab kam se kam ek button add ho chuka ho."""
    count = len(state["buttons"])
    kb = [[
        InlineKeyboardButton(text="➕ Haan, aur button", callback_data="more_yes"),
        InlineKeyboardButton(text="✅ Nahi, post banao", callback_data="more_no"),
    ]]
    if count:
        kb.append([InlineKeyboardButton(text="📋 Preview/Edit Buttons", callback_data="preview_buttons")])
    text = f"✅ Ab tak {count} button add ho chuke hain.\n\nAur button add karna hai?"
    return text, InlineKeyboardMarkup(inline_keyboard=kb)


COLOR_EMOJI = {"success": "🟢", "primary": "🔵", "danger": "🔴", None: "⚪"}


def preview_view(state):
    """Ab tak ke saare buttons ki list, edit karne ke liye tap kiya ja sakta hai."""
    kb = [
        [InlineKeyboardButton(text=f"{COLOR_EMOJI.get(style, '⚪')} {name}", callback_data=f"editbtn_{i}")]
        for i, (name, url, style) in enumerate(state["buttons"])
    ]
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_ask_more")])
    return "📋 Ab tak ke buttons (edit karne ke liye tap karo):", InlineKeyboardMarkup(inline_keyboard=kb)


# ---------------------------------------------------------
# Preview + Edit buttons
# ---------------------------------------------------------
@dp.callback_query(F.data == "preview_buttons")
async def preview_buttons(callback: CallbackQuery):
    state = user_states.get(callback.from_user.id)
    if not state:
        await callback.answer("Session expire ho gaya, /newpost dobara bhejo.", show_alert=True)
        return
    text, markup = preview_view(state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@dp.callback_query(F.data == "back_to_ask_more")
async def back_to_ask_more(callback: CallbackQuery):
    state = user_states.get(callback.from_user.id)
    if not state:
        await callback.answer("Session expire ho gaya, /newpost dobara bhejo.", show_alert=True)
        return
    state["step"] = "ask_more"
    text, markup = ask_more_view(state)
    await callback.message.edit_text(text, reply_markup=markup)
    await callback.answer()


@dp.callback_query(F.data.startswith("editbtn_"))
async def edit_button_menu(callback: CallbackQuery):
    state = user_states.get(callback.from_user.id)
    i = int(callback.data.split("_", 1)[1])
    if not state or i >= len(state["buttons"]):
        await callback.answer("Button nahi mila.", show_alert=True)
        return
    name, url, style = state["buttons"][i]
    kb = [
        [InlineKeyboardButton(text="✏️ Naam Edit", callback_data=f"editname_{i}")],
        [InlineKeyboardButton(text="🔗 URL Edit", callback_data=f"editurl_{i}")],
        [InlineKeyboardButton(text="🎨 Color Edit", callback_data=f"editcolor_{i}")],
        [InlineKeyboardButton(text="❌ Remove", callback_data=f"removebtn_{i}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="preview_buttons")],
    ]
    await callback.message.edit_text(
        f"Naam: {name}\nURL: {url}\nColor: {COLOR_EMOJI.get(style, '⚪')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("editname_"))
async def editname_start(callback: CallbackQuery):
    uid = callback.from_user.id
    i = int(callback.data.split("_", 1)[1])
    state = user_states.get(uid)
    if not state or i >= len(state["buttons"]):
        await callback.answer("Button nahi mila.", show_alert=True)
        return
    state["step"] = "editing_name"
    state["editing_index"] = i
    await callback.message.edit_text("✏️ Naya NAAM bhejo is button ke liye:")
    await callback.answer()


@dp.callback_query(F.data.startswith("editurl_"))
async def editurl_start(callback: CallbackQuery):
    uid = callback.from_user.id
    i = int(callback.data.split("_", 1)[1])
    state = user_states.get(uid)
    if not state or i >= len(state["buttons"]):
        await callback.answer("Button nahi mila.", show_alert=True)
        return
    state["step"] = "editing_url"
    state["editing_index"] = i
    await callback.message.edit_text("🔗 Naya URL bhejo (https:// se shuru hona chahiye):")
    await callback.answer()


@dp.callback_query(F.data.startswith("editcolor_"))
async def editcolor_menu(callback: CallbackQuery):
    i = int(callback.data.split("_", 1)[1])
    kb = [
        [InlineKeyboardButton(text="🟢 Green", callback_data=f"applycolor_{i}_success")],
        [InlineKeyboardButton(text="🔵 Blue", callback_data=f"applycolor_{i}_primary")],
        [InlineKeyboardButton(text="🔴 Red", callback_data=f"applycolor_{i}_danger")],
        [InlineKeyboardButton(text="⚪ Default", callback_data=f"applycolor_{i}_none")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data=f"editbtn_{i}")],
    ]
    await callback.message.edit_text("🎨 Naya COLOR choose karo:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data.startswith("applycolor_"))
async def apply_color_edit(callback: CallbackQuery):
    state = user_states.get(callback.from_user.id)
    _, i, color = callback.data.split("_", 2)
    i = int(i)
    if not state or i >= len(state["buttons"]):
        await callback.answer("Button nahi mila.", show_alert=True)
        return
    style = None if color == "none" else color
    name, url, _ = state["buttons"][i]
    state["buttons"][i] = (name, url, style)
    await callback.answer("✅ Color update ho gaya!")
    # wapas edit-menu dikhao, updated color ke saath
    await edit_button_menu_render(callback, state, i)


async def edit_button_menu_render(callback, state, i):
    name, url, style = state["buttons"][i]
    kb = [
        [InlineKeyboardButton(text="✏️ Naam Edit", callback_data=f"editname_{i}")],
        [InlineKeyboardButton(text="🔗 URL Edit", callback_data=f"editurl_{i}")],
        [InlineKeyboardButton(text="🎨 Color Edit", callback_data=f"editcolor_{i}")],
        [InlineKeyboardButton(text="❌ Remove", callback_data=f"removebtn_{i}")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="preview_buttons")],
    ]
    await callback.message.edit_text(
        f"Naam: {name}\nURL: {url}\nColor: {COLOR_EMOJI.get(style, '⚪')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
    )


@dp.callback_query(F.data.startswith("removebtn_"))
async def remove_button(callback: CallbackQuery):
    state = user_states.get(callback.from_user.id)
    i = int(callback.data.split("_", 1)[1])
    if not state or i >= len(state["buttons"]):
        await callback.answer("Button nahi mila.", show_alert=True)
        return
    state["buttons"].pop(i)
    await callback.answer("✅ Button remove ho gaya!")
    text, markup = preview_view(state)
    await callback.message.edit_text(text, reply_markup=markup)


# ---------------------------------------------------------
# Aur button add karna hai ya post finalize karna hai
# ---------------------------------------------------------
@dp.callback_query(F.data.startswith("more_"))
async def handle_more(callback: CallbackQuery):
    uid = callback.from_user.id
    state = user_states.get(uid)
    if not state:
        await callback.answer("Session expire ho gaya, /newpost dobara bhejo.", show_alert=True)
        return

    if callback.data == "more_yes":
        state["step"] = "button_name"
        await callback.message.edit_text("🔘 Agle button ka NAAM bhejo:")
        await callback.answer()
        return

    per_row = USER_BUTTONS_PER_ROW.get(uid)
    keyboard = [
        [InlineKeyboardButton(text=name, url=url, style=style) for name, url, style in row]
        for row in chunk_buttons(state["buttons"], per_row)
    ]
    state["final_keyboard"] = keyboard
    channels = CONNECTED_CHANNELS.get(uid, [])

    if channels:
        chan_buttons = [
            [InlineKeyboardButton(text=f"📢 {c['title']}", callback_data=f"postto_{c['id']}")]
            for c in channels
        ]
        chan_buttons.append([InlineKeyboardButton(text="📩 Mujhe DM me bhejo", callback_data="postto_dm")])
        await callback.message.edit_text(
            "📍 Ye post KIS channel me karna hai? Neeche se choose karo:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=chan_buttons)
        )
    else:
        await callback.message.delete()
        await send_final_post(uid, state, InlineKeyboardMarkup(inline_keyboard=keyboard), uid=uid)
        await bot.send_message(
            uid,
            "👆 Aapka post ready hai! Seedha channel me post karwane ke liye "
            "/addchannel se apna channel connect karo."
        )
        del user_states[uid]

    await callback.answer()


# ---------------------------------------------------------
# Konse channel me post karna hai (ya DM me)
# ---------------------------------------------------------
@dp.callback_query(F.data.startswith("postto_"))
async def handle_postto(callback: CallbackQuery):
    uid = callback.from_user.id
    state = user_states.get(uid)
    if not state or "final_keyboard" not in state:
        await callback.answer("Session expire ho gaya, /newpost dobara bhejo.", show_alert=True)
        return

    target = callback.data.split("_", 1)[1]
    markup = InlineKeyboardMarkup(inline_keyboard=state["final_keyboard"])

    try:
        if target == "dm":
            await send_final_post(uid, state, markup, uid=uid)
            await callback.message.edit_text("✅ Post aapko DM me bhej diya gaya.")
        else:
            chat_id = int(target)
            await send_final_post(chat_id, state, markup, uid=uid)
            await callback.message.edit_text("✅ Post channel me successfully daal diya gaya!")
    except TelegramBadRequest as e:
        await callback.message.edit_text(
            f"❌ Post nahi ho paya. Check karo bot admin hai ya nahi.\n(Error: {e})"
        )

    del user_states[uid]
    await callback.answer()


# ---------------------------------------------------------
# Mini App Backend -- Telegram WebApp ke liye REST API
# ---------------------------------------------------------
def verify_init_data(init_data: str):
    """Telegram WebApp 'initData' ko verify karta hai (HMAC signature check).
    Valid hone par us user ka dict return karta hai, warna None."""
    try:
        parsed = dict(urllib.parse.parse_qsl(init_data, strict_parsing=True))
        received_hash = parsed.pop("hash", None)
        if not received_hash:
            return None
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
        secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
        computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(computed_hash, received_hash):
            return None
        user_json = parsed.get("user")
        return json.loads(user_json) if user_json else None
    except Exception:
        return None


def _authed_user(body: dict):
    return verify_init_data(body.get("initData", ""))


async def handle_health(request):
    return web.Response(text="Bot is running")


async def handle_webapp_page(request):
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "webapp.html")
        with open(path, "r", encoding="utf-8") as f:
            return web.Response(text=f.read(), content_type="text/html")
    except FileNotFoundError:
        return web.Response(text="webapp.html not found next to bot.py", status=404)


async def handle_api_me(request):
    body = await request.json()
    user = _authed_user(body)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    uid = user["id"]
    await track_user_dict(user)

    # Bot-wide stats (sabhi users ke liye same) — global dedup chat count
    all_chat_ids = {c["id"] for chats in CONNECTED_CHANNELS.values() for c in chats}

    return web.json_response({
        "user": user,
        "channels": CONNECTED_CHANNELS.get(uid, []),
        "settings": {
            "format": USER_FORMAT.get(uid),
            "image_spoiler": USER_IMAGE_SPOILER.get(uid, False),
            "buttons_per_row": USER_BUTTONS_PER_ROW.get(uid),
        },
        "bot_stats": {
            "total_users": len(ALL_USERS),
            "total_chats": len(all_chat_ids),
            "uptime_seconds": time.time() - START_TIME,
        },
    })


async def handle_api_connect(request):
    body = await request.json()
    user = _authed_user(body)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    uid = user["id"]
    chat_ref = str(body.get("chat_ref", "")).strip()
    if not chat_ref:
        return web.json_response({"error": "Channel/Group username ya ID do."}, status=400)

    try:
        chat = await bot.get_chat(chat_ref)
        bot_member = await bot.get_chat_member(chat.id, bot.id)

        if chat.type == "channel":
            if bot_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                return web.json_response({"error": "Bot is Channel me ADMIN nahi hai."}, status=400)
        elif bot_member.status in (ChatMemberStatus.LEFT, ChatMemberStatus.KICKED):
            return web.json_response({"error": "Bot is Group me add nahi hai."}, status=400)

        user_member = await bot.get_chat_member(chat.id, uid)
        if user_member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
            return web.json_response({"error": "Aap is Channel/Group me ADMIN nahi hain."}, status=403)

        CONNECTED_CHANNELS.setdefault(uid, [])
        if not any(c["id"] == chat.id for c in CONNECTED_CHANNELS[uid]):
            CONNECTED_CHANNELS[uid].append({"id": chat.id, "title": chat.title})
        if channels_collection is not None:
            await channels_collection.update_one(
                {"user_id": uid, "channel_id": chat.id},
                {"$set": {"user_id": uid, "channel_id": chat.id, "title": chat.title}},
                upsert=True,
            )
        return web.json_response({"ok": True, "channels": CONNECTED_CHANNELS[uid]})
    except Exception as e:
        return web.json_response({"error": f"Connect nahi ho paya: {e}"}, status=400)


async def handle_api_remove(request):
    body = await request.json()
    user = _authed_user(body)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    uid = user["id"]
    chat_id = body.get("chat_id")
    CONNECTED_CHANNELS[uid] = [c for c in CONNECTED_CHANNELS.get(uid, []) if c["id"] != chat_id]
    if channels_collection is not None:
        await channels_collection.delete_one({"user_id": uid, "channel_id": chat_id})
    return web.json_response({"ok": True, "channels": CONNECTED_CHANNELS.get(uid, [])})


async def handle_api_settings(request):
    body = await request.json()
    user = _authed_user(body)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    uid = user["id"]
    if "format" in body:
        USER_FORMAT[uid] = body["format"]
    if "image_spoiler" in body:
        USER_IMAGE_SPOILER[uid] = bool(body["image_spoiler"])
    if "buttons_per_row" in body:
        USER_BUTTONS_PER_ROW[uid] = body["buttons_per_row"]
    if settings_collection is not None:
        await settings_collection.update_one(
            {"user_id": uid},
            {"$set": {
                "user_id": uid,
                "format": USER_FORMAT.get(uid),
                "image_spoiler": USER_IMAGE_SPOILER.get(uid, False),
                "buttons_per_row": USER_BUTTONS_PER_ROW.get(uid),
            }},
            upsert=True,
        )
    return web.json_response({"ok": True})


async def handle_api_publish(request):
    body = await request.json()
    user = _authed_user(body)
    if not user:
        return web.json_response({"error": "unauthorized"}, status=401)
    uid = user["id"]

    text = body.get("text", "")
    buttons = body.get("buttons", [])  # [{name, url, style}]
    per_row = body.get("buttons_per_row")
    target = body.get("target_chat_id")  # "me" ya numeric chat id
    photo_base64 = body.get("photo_base64")
    spoiler = bool(body.get("spoiler", False))

    if not target:
        return web.json_response({"error": "Kis channel/group me post karna hai, wo batao."}, status=400)

    button_tuples = [(b["name"], b["url"], b.get("style")) for b in buttons]
    keyboard = [
        [InlineKeyboardButton(text=n, url=u, style=s) for n, u, s in row]
        for row in chunk_buttons(button_tuples, per_row)
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard) if keyboard else None
    chat_id = uid if target == "me" else int(target)

    try:
        if photo_base64:
            photo_bytes = base64.b64decode(photo_base64.split(",")[-1])
            file = BufferedInputFile(photo_bytes, filename="post.jpg")
            await bot.send_photo(chat_id, photo=file, caption=text, reply_markup=markup,
                                  parse_mode="HTML", has_spoiler=spoiler)
        else:
            await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="HTML")
        return web.json_response({"ok": True})
    except Exception as e:
        return web.json_response({"error": f"Post nahi ho paya: {e}"}, status=400)


def build_web_app():
    app = web.Application(client_max_size=15 * 1024 * 1024)  # photo uploads ke liye
    app.router.add_get("/", handle_health)
    app.router.add_get("/app", handle_webapp_page)
    app.router.add_post("/api/me", handle_api_me)
    app.router.add_post("/api/connect", handle_api_connect)
    app.router.add_post("/api/remove", handle_api_remove)
    app.router.add_post("/api/settings", handle_api_settings)
    app.router.add_post("/api/publish", handle_api_publish)
    return app


async def start_web_server():
    runner = web.AppRunner(build_web_app())
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"🌐 Web server + Mini App backend chal raha hai port {port} par")


async def main():
    global BOT_USERNAME
    me = await bot.get_me()
    BOT_USERNAME = me.username
    await init_db()
    await start_web_server()
    print(f"✅ Bot start ho raha hai... (@{BOT_USERNAME})")
    if WEBAPP_BASE_URL:
        print(f"🚀 Mini App: {WEBAPP_BASE_URL}/app")
    else:
        print("⚠️ WEBAPP_BASE_URL set nahi hai — Mini App button nahi dikhega.")
    print("   Telegram par apne bot ko /start bhejo.")
    await send_log(
        f"🚀 <b>Bot Deployed/Restarted</b>\n"
        f"🤖 @{BOT_USERNAME}\n"
        f"👥 Total Users: {len(ALL_USERS)}"
    )
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
