"""
script.py -- Sirf yahi file edit karo apna text/buttons/content change karne ke liye
------------------------------------------------------------------------------
Bot ka asli code (bot.py) isse import karta hai. Yaha kuch bhi change karoge,
bot restart hote hi wo dikhega. Coding ki zaroorat nahi, bas text/URLs edit karo.
"""

# ---------------------------------------------------------
# /start message ka text
# ---------------------------------------------------------
# HTML tags support hain: <b>bold</b>, <i>italic</i>, <blockquote>quote</blockquote>
# {user} ki jagah automatically us insaan ka naam (clickable mention) aa jayega
# jo /start kar raha hai.
MESSAGE_TEXT = (
    "👋 <b>Namaste {user}!</b>\n\n"
    "🔘 Custom colored buttons wale posts banao\n"
    "📢 Multiple Channels/Groups me seedha post karo\n"
    "🖼️ Photo ke saath spoiler ya normal post karo\n"
    "📝 Quote, Mono, Spoiler jaisi caption formatting\n"
    "⚡ Fast aur reliable\n\n"
    "Apna post banane ke liye ye command bhejo:\n"
    "<blockquote>/newpost</blockquote>"
)

# ---------------------------------------------------------
# /start message ke buttons
# ---------------------------------------------------------
# Har button: (button_text, url, style)
# style options: "success" (green), "primary" (blue), "danger" (red), None (default)
# Ek row (list ke andar list) me jitne pairs doge, wo saath ek line me dikhenge.
BUTTONS = [
    [("📢 Channel", "https://t.me/Deendayal_dhakadd", "success"),
     ("👥 Group", "https://t.me/Deendayal_dhakadd", "success")],
]

# ---------------------------------------------------------
# /start message ke saath dikhne wali image(s)
# ---------------------------------------------------------
# Ye Render ke PICS environment variable se bhi override ho sakti hai.
# Multiple URLs (space se separate) doge to har baar random ek choose hogi.
DEFAULT_PICS = "https://i.ibb.co/wNcw3tMY/photo-2026-08-29-04-38-12-7679308298687873056.jpg"

# ---------------------------------------------------------
# Settings menu button ka naam
# ---------------------------------------------------------
MENU_BUTTON_TEXT = "⚙️ Settings"

# ---------------------------------------------------------
# "About" button dabane par ye details dikhengi
# ---------------------------------------------------------
ABOUT_TEXT = (
    "━━━[ <b>MY DETAILS</b> ]━━━\n"
    "★ <b>My Name</b> : Deendayal Button Bot\n"
    "★ <b>Developer</b> : Deendayal\n"
    "★ <b>Library</b> : aiogram\n"
    "★ <b>Language</b> : Python 3\n"
    "★ <b>Database</b> : MongoDB\n"
    "★ <b>Bot Server</b> : Render\n"
    "★ <b>Build Status</b> : Stable\n"
    "━━━━━━━━━━━━━━━━"
)
