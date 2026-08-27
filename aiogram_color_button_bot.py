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


async def init_db():
    """MongoDB se connect karo aur pehle se saved channels memory me load karo."""
    global channels_collection
    if not MONGO_URI:
        print("⚠️ MONGO_URI nahi diya gaya - channels sirf memory me rahenge "
              "(restart hone par dobara /addchannel karna padega).")
        return

    try:
        client = AsyncIOMotorClient(MONGO_URI)
        db = client["telegram_bot"]
        channels_collection = db["channels"]

        count = 0
        async for doc in channels_collection.find():
            CONNECTED_CHANNELS.setdefault(doc["user_id"], [])
            CONNECTED_CHANNELS[doc["user_id"]].append({"id": doc["channel_id"], "title": doc["title"]})
            count += 1

        print(f"✅ MongoDB connect ho gaya. {count} saved channel(s) load ho gaye.")
    except Exception as e:
        print(f"❌ MongoDB se connect nahi ho paya: {e}")
        print("   Channels sirf memory me rahenge (restart pe reset honge).")


# ---------------------------------------------------------
# /start -- demo message with colored buttons
# ---------------------------------------------------------
@dp.message(CommandStart())
async def start(message: Message):
    keyboard = [
        [InlineKeyboardButton(text=text, url=url, style=style) for text, url, style in row]
        for row in BUTTONS
    ]
    await message.answer(MESSAGE_TEXT, reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))


# ---------------------------------------------------------
# /addchannel -- channel connect karo
# ---------------------------------------------------------
@dp.message(Command("addchannel"))
async def addchannel_cmd(message: Message):
    user_states[message.from_user.id] = {"step": "add_channel"}
    await message.answer(
        "📢 Channel connect karne ke steps:\n\n"
        "1) Bot ko us channel me ADMIN banao (post karne ki permission ke saath)\n\n"
        "2a) Agar channel PUBLIC hai: yaha uska username bhejo (jaise @mychannel)\n\n"
        "2b) Agar channel PRIVATE hai: us channel me jaakar koi bhi ek message "
        "yaha is chat me FORWARD kardo"
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
    user_states[message.from_user.id] = {"step": "text", "buttons": []}
    await message.answer(
        "📝 Apna post banana shuru karte hain.\n\n"
        "Pehle wo TEXT bhejo jo buttons ke UPAR dikhega:"
    )


# ---------------------------------------------------------
# Saara text/forwarded input yahi handle karta hai (jo commands nahi hain)
# ---------------------------------------------------------
@dp.message(F.text | F.forward_origin)
async def collect_input(message: Message):
    uid = message.from_user.id
    if uid not in user_states:
        return  # koi active flow nahi hai, ignore karo

    state = user_states[uid]
    step = state["step"]

    if step == "add_channel":
        try:
            chat = None
            # Private channel -> forward se seedha chat info milta hai
            if message.forward_origin and message.forward_origin.type == "channel":
                chat = message.forward_origin.chat
            else:
                chat_ref = message.text.strip()
                chat = await bot.get_chat(chat_ref)

            member = await bot.get_chat_member(chat.id, bot.id)
            if member.status not in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR):
                await message.answer(
                    "⚠️ Bot is channel me ADMIN nahi hai. Pehle admin banao "
                    "(post karne ki permission ke saath), phir /addchannel se dobara try karo."
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
        # Poora text by-default BOLD rakha ja raha hai.
        state["text"] = f"<b>{message.html_text}</b>"
        state["step"] = "button_name"
        await message.answer("🔘 Ab pehle button ka NAAM bhejo (jaise: Website):")

    elif step == "button_name":
        state["current_name"] = message.text
        state["step"] = "button_url"
        await message.answer("🔗 Ab is button ka URL bhejo (https:// se shuru hona chahiye):")

    elif step == "button_url":
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

    keyboard = [
        [InlineKeyboardButton(text=name, url=url, style=style)]
        for name, url, style in state["buttons"]
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
        await bot.send_message(uid, state["text"], reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard), parse_mode="HTML")
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
            await bot.send_message(uid, state["text"], reply_markup=markup, parse_mode="HTML")
            await callback.message.edit_text("✅ Post aapko DM me bhej diya gaya.")
        else:
            chat_id = int(target)
            await bot.send_message(chat_id, state["text"], reply_markup=markup, parse_mode="HTML")
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
