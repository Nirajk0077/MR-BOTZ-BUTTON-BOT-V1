"""
script.py -- Sirf yahi file edit karo apna TEXT change karne ke liye
------------------------------------------------------------------------------
Bot ka asli code (bot.py) isse import karta hai. Yaha kuch bhi change karoge,
bot restart hote hi wo dikhega. Coding ki zaroorat nahi, bas text edit karo.
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

