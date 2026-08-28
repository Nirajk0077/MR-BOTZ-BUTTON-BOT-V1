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
import threading
import random
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from motor.motor_asyncio import AsyncIOMotorClient

# =========================================================
# CONFIG -- yaha apni values daalo
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")   # @BotFather se
MONGO_URI = os.environ.get("MONGO_URI", "")   # MongoDB connection string (optional par recommended)

# Apna khud ka text yaha likho (emoji bhi daal sakte ho)
MESSAGE_TEXT = (
    "👋 Namaste!\n\n"
    "Latest updates, movies aur exclusive content ke liye "
    "neeche diye buttons se hamare Channel aur Group se judo 👇"
)

# Har button: (button_text, url, style)
# style options: "success" (green), "primary" (blue), "danger" (red), None (default)
BUTTONS = [
    [("📢 Channel", "https://t.me/Deendayal_dhakadd", "success")],
    [("👥 Group", "https://t.me/Deendayal_dhakadd", "success")],
]

# /start message ke saath image dikhani hai to PICS environment variable me
# URLs daalo (space se separate karke), jaise:
#   https://example.com/1.jpg https://example.com/2.jpg
# Har baar /start hone par inme se RANDOM ek image choose hogi.
START_IMAGES = os.environ.get(
    'PICS',
    'https://i.ibb.co/ccWd1db5/photo-2026-01-04-09-51-53-7591442205638656024.jpg '
    'https://i.ibb.co/38fQNmF/photo-2026-01-04-09-52-40-7591442536351137808.jpg '
    'https://i.ibb.co/TBLBcL8j/photo-2026-01-04-09-52-16-7591442102559440916.jpg '
    'https://i.ibb.co/1J0BK84k/photo-2026-01-04-09-52-26-7591442712444796944.jpg'
).split()

# /start ke neeche jo custom menu button dikhega, uska naam yaha se change karo
MENU_BUTTON_TEXT = "⚙️ Settings"
# =========================================================

if not BOT_TOKEN:
    print("\n❌ BOT_TOKEN missing hai. Isse environment variable ki tarah set karo,")
    print("   ya seedha script ke CONFIG section me daalo.\n")
    sys.exit(1)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# User ke chat state track karne ke liye (memory me, restart hone par reset ho jayega)
user_states = {}

# User ne jo channels connect kiye hain (memory me cache, MongoDB se load hota hai)
# Structure: { user_id: [ {"id": -1001234, "title": "My Channel"}, ... ] }
CONNECTED_CHANNELS = {}

channels_collection = None  # MongoDB connect hone ke baad set hoga
settings_collection = None  # MongoDB connect hone ke baad set hoga (Caption Format + Image Spoiler)

# User ne apna caption format kya choose kiya hai (Quote/Mono/Spoiler/None)
# Structure: { user_id: "quote" | "mono" | "spoiler" | None }
USER_FORMAT = {}

# User ne image spoiler (hide) chuna hai ya default
# Structure: { user_id: True (spoiler) | False (default) }
USER_IMAGE_SPOILER = {}

# User ek line me kitne buttons chahta hai (1-4), None = default (1 per line)
# Structure: { user_id: 1 | 2 | 3 | 4 | None }
USER_BUTTONS_PER_ROW = {}


def chunk_buttons(buttons, per_row):
    """Buttons ki flat list ko per_row size ke rows me todta hai."""
    per_row = per_row or 1
    return [buttons[i:i + per_row] for i in range(0, len(buttons), per_row)]


async def edit_smart(message, text, markup=None):
    """Message photo wala hai to caption edit karo, warna normal text edit karo.
    (Zaroori hai kyunki /start ab image ke saath bhi ho sakta hai.)"""
    if message.photo:
        await message.edit_caption(caption=text, reply_markup=markup)
    else:
        await message.edit_text(text, reply_markup=markup)


async def init_db():
    """MongoDB se connect karo aur pehle se saved channels + settings memory me load karo."""
    global channels_collection, settings_collection
    if not MONGO_URI:
        print("⚠️ MONGO_URI nahi diya gaya - channels/settings sirf memory me rahenge "
              "(restart hone par dobara set karna padega).")
        return

    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client["telegram_bot"]
        channels_collection = db["channels"]
        settings_collection = db["user_settings"]

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

        print(f"✅ MongoDB connect ho gaya. {count} saved channel(s), {settings_count} user setting(s) load ho gaye.")
    except Exception as e:
        print(f"❌ MongoDB se connect nahi ho paya: {e}")
        print("   Channels/settings sirf memory me rahenge (restart pe reset honge).")


# ---------------------------------------------------------
# /start -- demo message with colored buttons
# ---------------------------------------------------------
@dp.message(CommandStart())
async def start(message: Message):
    keyboard = [
        [InlineKeyboardButton(text=text, url=url, style=style) for text, url, style in row]
        for row in BUTTONS
    ]
    keyboard.append([InlineKeyboardButton(text=MENU_BUTTON_TEXT, callback_data="main_menu")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    if START_IMAGES:
        image = random.choice(START_IMAGES)
        await message.answer_photo(photo=image, caption=MESSAGE_TEXT, reply_markup=markup)
    else:
        await message.answer(MESSAGE_TEXT, reply_markup=markup)


# ---------------------------------------------------------
# Settings menu -- Connect Channel + Caption Format
# ---------------------------------------------------------
@dp.callback_query(F.data == "main_menu")
async def main_menu(callback: CallbackQuery):
    kb = [
        [InlineKeyboardButton(text="🔗 Connect Channel/Group", callback_data="menu_channels")],
        [InlineKeyboardButton(text="📝 Caption Format", callback_data="menu_format")],
        [InlineKeyboardButton(text="🖼️ Image Settings", callback_data="menu_image")],
        [InlineKeyboardButton(text="🔲 Buttons Per Line", callback_data="menu_perrow")],
        [InlineKeyboardButton(text="⬅️ Back", callback_data="back_to_start")],
    ]
    await edit_smart(callback.message, "⚙️ Settings Menu", InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "back_to_start")
async def back_to_start(callback: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton(text=text, url=url, style=style) for text, url, style in row]
        for row in BUTTONS
    ]
    keyboard.append([InlineKeyboardButton(text=MENU_BUTTON_TEXT, callback_data="main_menu")])
    await edit_smart(callback.message, MESSAGE_TEXT, InlineKeyboardMarkup(inline_keyboard=keyboard))
    await callback.answer()


@dp.callback_query(F.data == "menu_channels")
async def menu_channels(callback: CallbackQuery):
    uid = callback.from_user.id
    channels = CONNECTED_CHANNELS.get(uid, [])
    kb = [
        [InlineKeyboardButton(text=f"📢 {c['title']}", callback_data=f"manage_channel_{c['id']}")]
        for c in channels
    ]
    kb.append([InlineKeyboardButton(text="➕ Connect New Channel/Group", callback_data="menu_addchannel")])
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")])
    text = "🔗 Aapke connected channels/groups:" if channels else "Abhi koi channel/group connect nahi hai."
    await edit_smart(callback.message, text, InlineKeyboardMarkup(inline_keyboard=kb))
    await callback.answer()


@dp.callback_query(F.data == "menu_addchannel")
async def menu_addchannel(callback: CallbackQuery):
    user_states[callback.from_user.id] = {"step": "add_channel"}
    await edit_smart(
        callback.message,
        "📢 Channel ya Group connect karne ke steps:\n\n"
        "1) Bot ko add karo:\n"
        "   • Channel me: bot ko ADMIN banao (post permission ke saath)\n"
        "   • Group me: bot ko bas MEMBER ki tarah add karo, admin zaroori nahi\n\n"
        "2) Yaha bhejo:\n"
        "   • PUBLIC ho to uska username (jaise @mychannel)\n"
        "   • PRIVATE ho to uski numeric ID (-100 se shuru hoti hai), "
        "ya wahan se koi message yaha FORWARD kardo"
    )
    await callback.answer()


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
        [InlineKeyboardButton(text=("✅ " if current == "quote" else "") + "❝ Quote", callback_data="format_quote")],
        [InlineKeyboardButton(text=("✅ " if current == "mono" else "") + "🔤 Mono", callback_data="format_mono")],
        [InlineKeyboardButton(text=("✅ " if current == "spoiler" else "") + "🙈 Spoiler", callback_data="format_spoiler")],
        [InlineKeyboardButton(text=("✅ " if current is None else "") + "⚪ Default (bold only)", callback_data="format_none")],
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
    kb = []
    for n in (1, 2, 3, 4):
        tick = "✅ " if current == n else ""
        kb.append([InlineKeyboardButton(text=f"{tick}{n} button{'s' if n > 1 else ''} per line", callback_data=f"perrow_{n}")])
    kb.append([InlineKeyboardButton(text=("✅ " if current is None else "") + "⚪ Default (1 per line)", callback_data="perrow_default")])
    kb.append([InlineKeyboardButton(text="⬅️ Back", callback_data="main_menu")])
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
    user_states[message.from_user.id] = {"step": "add_channel"}
    await message.answer(
        "📢 Channel ya Group connect karne ke steps:\n\n"
        "1) Bot ko add karo:\n"
        "   • Channel me: bot ko ADMIN banao (post permission ke saath)\n"
        "   • Group me: bot ko bas MEMBER ki tarah add karo, admin zaroori nahi\n\n"
        "2) Yaha bhejo:\n"
        "   • PUBLIC ho to uska username (jaise @mychannel)\n"
        "   • PRIVATE ho to uski numeric ID (-100 se shuru hoti hai), "
        "ya wahan se koi message yaha FORWARD kardo"
    )


@dp.message(Command("mychannels"))
async def mychannels_cmd(message: Message):
    channels = CONNECTED_CHANNELS.get(message.from_user.id, [])
    if not channels:
        await message.answer("Abhi koi channel connect nahi hai. /addchannel use karo.")
        return
    text = "📋 Aapke connected channels:\n\n" + "\n".join(f"• {c['title']}" for c in channels)
    await message.answer(text)


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

            await message.answer(f"✅ Channel '{chat.title}' connect ho gaya!")
        except Exception as e:
            await message.answer(
                f"❌ Channel connect nahi ho paya.\n"
                f"Public ho to @username check karo. Private ho to message forward karo.\n\n"
                f"(Error: {e})"
            )
        del user_states[uid]
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
    await callback.message.edit_text(
        f"✅ Button '{state['current_name']}' add ho gaya.\n\nAur button add karna hai?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="➕ Haan, aur button", callback_data="more_yes"),
            InlineKeyboardButton(text="✅ Nahi, post banao", callback_data="more_no"),
        ]])
    )
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
# Render/Koyeb FREE Web Service ke liye dummy port
# ---------------------------------------------------------
def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")

        def do_HEAD(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()

        def log_message(self, format, *args):
            pass

    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()


async def main():
    await init_db()
    print("✅ Bot start ho raha hai...")
    print("   Telegram par apne bot ko /start bhejo.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    threading.Thread(target=run_dummy_server, daemon=True).start()
    asyncio.run(main())
