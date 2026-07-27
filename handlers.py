from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, MessageEntity
from pyrogram.enums import ChatMemberStatus, ParseMode
import logging, asyncio, aiosqlite, traceback, re, io
from database import *
from config import Config

# Telethon imports for OTP listener
from telethon import TelegramClient, events
from telethon.sessions import StringSession

# PIL for dynamic image generation
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)
_bot_instance = None

DIAMOND_COST = 10

# ========== IMAGE MAPPING (Static images for other screens) ==========
MEDIA_MAPPING = {
    "welcome": "AgACAgUAAxkBAAICPWpiIWYRTlYmoNtf5YAMo4moOmHrAAIYE2sbpi4QV3bwmESz182zAAgBAAMCAAN5AAceBA",
    "profile": None,  # Ab static nahi, dynamic generate karenge
    "invite": "AgACAgUAAxkBAAICQ2piIurs4zuoexABkKldhri2QX7IAAIcE2sbpi4QV6pQ9mA2CAugAAgBAAMCAAN5AAceBA",
    "rewards": "AgACAgUAAxkBAAICRmpiI3NqRzzURxr0z-kN31yRfRl0AAIdE2sbpi4QV0zq454LY2_PAAgBAAMCAAN5AAceBA",
    "my_rewards": "AgACAgUAAxkBAAICRmpiI3NqRzzURxr0z-kN31yRfRl0AAIdE2sbpi4QV0zq454LY2_PAAgBAAMCAAN5AAceBA",
    "progress": "AgACAgUAAxkBAAICS2piI_FLgEAGxcCJwxDxOgQXiOVZAAIeE2sbpi4QVxY6hrl6jS5pAAgBAAMCAAN5AAceBA",
    "support": "AgACAgUAAxkBAAICT2piJGMMLPKdjUI9n2N2KqwAAVWZKwACIRNrG6YuEFfJP48Z1gPnlgAIAQADAgADeQAHHgQ",
    "admin": "AgACAgUAAxkBAAICUmpiJLi1RXiYSQWJj2Eg5rcJTBpvAAIjE2sbpi4QV3VpkdHjPokXAAgBAAMCAAN5AAceBA",
    "admin_broadcast": "AgACAgUAAxkBAAICVWpiJQpZB3c0xVHgOpdhbiliInPoAAIkE2sbpi4QVyqn1zaowZUBAAgBAAMCAAN5AAceBA",
}

AUTO_SWITCH_STATE = {}

# ========== DYNAMIC PROFILE CARD GENERATOR ==========
def generate_profile_card(user_id, username, diamonds, referrals, earned):
    """Generate a sexy profile card image with user data."""
    # Image size
    width, height = 1280, 720
    # Dark premium background
    img = Image.new('RGB', (width, height), color=(18, 18, 40))
    draw = ImageDraw.Draw(img)

    # Draw a premium gradient-like header box
    draw.rectangle([(0, 0), (width, 120)], fill=(40, 40, 80))
    draw.rectangle([(0, 110), (width, 120)], fill=(80, 50, 150))

    # Load fonts (fallback to default if arial not found)
    try:
        font_title = ImageFont.truetype("arial.ttf", 50)
        font_big = ImageFont.truetype("arial.ttf", 40)
        font_medium = ImageFont.truetype("arial.ttf", 30)
    except:
        font_title = ImageFont.load_default()
        font_big = font_title
        font_medium = font_title

    # Title
    draw.text((50, 35), "👤✨ YOUR PROFILE ✨👤", font=font_title, fill=(255, 255, 255))

    # User Info
    y = 160
    display_name = username if username else str(user_id)
    draw.text((50, y), f"👤 Name: {display_name}", font=font_big, fill=(200, 200, 255))
    y += 60
    draw.text((50, y), f"🆔 User ID: {user_id}", font=font_medium, fill=(180, 180, 220))
    y += 60

    # Stats boxes (premium card style)
    box_y_start = y + 20
    box_width = 280
    box_height = 140
    gap = 30
    colors = [(50, 50, 120), (120, 50, 80), (40, 100, 90), (80, 40, 100)]
    labels = ["💎 DIAMONDS", "👥 REFERRALS", "📱 EARNED", "🎯 NEXT TARGET"]
    values = [str(diamonds), str(referrals), str(len(earned)), f"{DIAMOND_COST - (diamonds % DIAMOND_COST)}"]

    for i in range(4):
        x = 50 + i * (box_width + gap)
        draw.rectangle([(x, box_y_start), (x + box_width, box_y_start + box_height)], fill=colors[i], outline=(255, 255, 255, 50), width=2)
        # Label
        draw.text((x + 20, box_y_start + 20), labels[i], font=font_medium, fill=(200, 200, 200))
        # Value
        draw.text((x + 20, box_y_start + 80), values[i], font=font_title, fill=(255, 255, 255))

    # Rank / Level (Bottom)
    y = box_y_start + box_height + 60
    rank = "💎 Bronze"
    if diamonds >= 50: rank = "💎 Gold"
    elif diamonds >= 30: rank = "💎 Silver"
    draw.text((50, y), f"🏅 Rank: {rank}", font=font_big, fill=(255, 215, 0))
    y += 60

    # Footer
    draw.text((50, height - 50), "✨ ASCEND - Premium Referral Bot ✨", font=font_medium, fill=(100, 100, 150))

    # Save to BytesIO
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    img_bytes.seek(0)
    return img_bytes

class BotHandlers:
    def __init__(self, app: Client):
        global _bot_instance
        _bot_instance = app
        self.app = app
        self.pending_sessions = {}
        self.otp_tasks = {}

        # ---------- GET FILE ID ----------
        @app.on_message(filters.command("getfileid") & filters.user(Config.ADMIN_ID))
        async def get_file_id(client, message):
            if message.reply_to_message and message.reply_to_message.photo:
                file_id = message.reply_to_message.photo.file_id
                await message.reply(f"📸✨ **File ID:**\n`{file_id}`", parse_mode=ParseMode.MARKDOWN)
            else:
                await message.reply("❌ Reply to a photo with `/getfileid`", parse_mode=ParseMode.MARKDOWN)

        # ---------- GET EMOJI ID ----------
        @app.on_message(filters.command("getemojioid") & filters.user(Config.ADMIN_ID))
        async def get_emoji_id(client, message):
            if message.reply_to_message:
                msg = message.reply_to_message
                if msg.entities:
                    for entity in msg.entities:
                        if hasattr(entity, 'custom_emoji_id') and entity.custom_emoji_id:
                            await message.reply(f"✅✨ **Custom Emoji ID:**\n`{entity.custom_emoji_id}`", parse_mode=ParseMode.MARKDOWN)
                            return
                if msg.caption_entities:
                    for entity in msg.caption_entities:
                        if hasattr(entity, 'custom_emoji_id') and entity.custom_emoji_id:
                            await message.reply(f"✅✨ **Custom Emoji ID:**\n`{entity.custom_emoji_id}`", parse_mode=ParseMode.MARKDOWN)
                            return
                await message.reply("❌ No custom emoji found.", parse_mode=ParseMode.MARKDOWN)
            else:
                await message.reply("📌 Reply to a Premium emoji with `/getemojioid`", parse_mode=ParseMode.MARKDOWN)

        # ---------- START ----------
        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id
            if not await self._is_verified(client, user_id):
                await self._send_force_join_message(client, message)
                return

            if len(message.command) > 1:
                ref_param = message.command[1]
                if ref_param.startswith("ref_"):
                    ref_code = ref_param[4:]
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            diamonds = await get_diamonds(referrer['user_id'])
                            await client.send_message(referrer['user_id'], f"✨🎉 **New Referral!**\n\n👤 User `{user_id}` joined.\n💎 +1 diamond! Total: **{diamonds}**", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await client.send_message(referrer['user_id'], "❌ Already referred.", parse_mode=ParseMode.MARKDOWN)
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 Can't refer self!", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ Invalid link.", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)
            if user_id not in AUTO_SWITCH_STATE:
                AUTO_SWITCH_STATE[user_id] = False

            await self._show_screen(client, message, "welcome", user_id, is_edit=False)

        # ---------- CALLBACK ----------
        @app.on_callback_query()
        async def callback_handler(client, callback):
            data = callback.data
            user_id = callback.from_user.id
            current_msg = callback.message

            if data == "claim_reward":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer(f"💎 Need {DIAMOND_COST - diamonds} more.", show_alert=True)
                    return
                success = await deduct_diamonds(user_id, DIAMOND_COST)
                if not success:
                    await callback.answer("❌ Error.", show_alert=True)
                    return
                available = await get_available_accounts()
                if not available:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("📦 No accounts.", show_alert=True)
                    return
                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await current_msg.delete()
                    await callback.message.reply(f"🎁💎 **Account Claimed!**\n\n📱 Phone: `{phone}`\n\nEnjoy! 🚀✨", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙✨ Home", callback_data="welcome")]]), parse_mode=ParseMode.MARKDOWN)
                    if account.get('session_string'):
                        asyncio.create_task(forward_telegram_otp_telethon(account['id'], user_id, account['session_string']))
                    await callback.answer("✅ Claimed!")
                else:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ Claim failed.", show_alert=True)
                return

            if data == "auto_switch":
                current = AUTO_SWITCH_STATE.get(user_id, False)
                AUTO_SWITCH_STATE[user_id] = not current
                await callback.answer(f"🔄 Auto-Switch {'ON' if AUTO_SWITCH_STATE[user_id] else 'OFF'}")
                await self._show_screen(client, current_msg, "welcome", user_id, is_edit=True)
                return

            if data == "copy_link":
                await callback.answer("📋 Copy manually.", show_alert=True)
                return

            screen_map = {
                "welcome": "welcome", "profile": "profile", "invite": "invite",
                "rewards": "rewards", "my_rewards": "my_rewards", "progress": "progress",
                "support": "support", "admin": "admin", "admin_broadcast": "admin_broadcast",
            }
            if data in screen_map:
                await self._show_screen(client, current_msg, screen_map[data], user_id, is_edit=True)
                await callback.answer()
                return

            if data in ["admin_users", "admin_stats", "admin_settings"]:
                await current_msg.delete()
                await callback.message.reply("🔧✨ Under development.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙✨ Back", callback_data="admin")]]), parse_mode=ParseMode.MARKDOWN)
                await callback.answer()
                return

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    await self._show_screen(client, current_msg, "welcome", user_id, is_edit=True)
                else:
                    await callback.answer("❌ Join channel & group first.", show_alert=True)
                return

            await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply("🔧✨ **Admin Commands**\n\n• `/gensession +91...` – 🔑 Generate session\n• `/otp +91... 12345` – 📲 Complete OTP\n• `/addaccount ...` – ➕ Add account\n• `/listaccounts` – 📋 List accounts\n• `/refstats <id>` – 📊 User stats\n• `/available` – 📦 Available accounts\n• `/broadcast <msg>` – 📢 Send broadcast\n• `/getfileid` – 🖼️ Get file ID\n• `/getemojioid` – 🎨 Get premium emoji ID", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 Usage: `/gensession +911234567890`", parse_mode=ParseMode.MARKDOWN)
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply("⏳ Already generating.", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"📲 Sending OTP to `{phone}`...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {"client": temp_client, "phone": phone, "phone_code_hash": sent_code.phone_code_hash}
                await message.reply(f"✅ OTP sent! Use `/otp {phone} <code>`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("📌 Usage: `/otp +911234567890 12345`", parse_mode=ParseMode.MARKDOWN)
                return
            phone, otp_code = parts[1], parts[2]
            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("❌ No pending session.", parse_mode=ParseMode.MARKDOWN)
                return
            if session_data["phone"] != phone:
                await message.reply(f"❌ Mismatch. Expected `{session_data['phone']}`", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = session_data["client"]
            await message.reply("⏳ Signing in...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.sign_in(phone, otp_code, session_data["phone_code_hash"])
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]
                await message.reply(f"✅✨ **Session Generated!**\n\n📱 Phone: `{phone}`\n🔑 Session:\n`{session_string}`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply("📌 Usage: `/addaccount <phone> <pass> <otp> <session> <desc>`\nExample: `/addaccount +911234567890 MyPass123 456789 session_here \"Premium\"`", parse_mode=ParseMode.MARKDOWN)
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)
            await message.reply(f"✅ **Account #{acc_id} added!**", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("updateotp") & filters.user(Config.ADMIN_ID))
        async def update_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("📌 Usage: `/updateotp <account_id> <new_otp>`", parse_mode=ParseMode.MARKDOWN)
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"✅ OTP for #{acc_id} updated.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("📭 No accounts.", parse_mode=ParseMode.MARKDOWN)
                    return
                text = "📋✨ **All Accounts**\n\n"
                for r in rows:
                    status = "✅ Sold" if r['is_sold'] else "⬜ Available"
                    text += f"#{r['id']} | {r['phone']} | {status}\n"
                await message.reply(text, parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 Usage: `/refstats <user_id>`", parse_mode=ParseMode.MARKDOWN)
                return
            uid = int(parts[1])
            diamonds = await get_diamonds(uid)
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(f"📊✨ **User {uid}**\n💎 Diamonds: {diamonds}\n👥 Referrals: {count}\n📱 Accounts: {len(accounts)}", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("available") & filters.user(Config.ADMIN_ID))
        async def available_cmd(client, message):
            available = await get_available_accounts()
            await message.reply(f"📦✨ **Available Accounts:** `{len(available)}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("broadcast") & filters.user(Config.ADMIN_ID))
        async def broadcast_cmd(client, message):
            if message.reply_to_message:
                text = message.reply_to_message.text or message.reply_to_message.caption
                if not text:
                    await message.reply("❌ No text.", parse_mode=ParseMode.MARKDOWN)
                    return
            else:
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    await message.reply("📌 Usage: `/broadcast <message>`", parse_mode=ParseMode.MARKDOWN)
                    return
                text = parts[1]

            users = await get_all_users()
            total = len(users)
            if total == 0:
                await message.reply("📭 No users.", parse_mode=ParseMode.MARKDOWN)
                return

            status_msg = await message.reply(f"📢✨ Broadcasting to {total} users...", parse_mode=ParseMode.MARKDOWN)
            sent = 0
            failed = 0
            for i, user_id in enumerate(users):
                try:
                    await client.send_message(user_id, text)
                    sent += 1
                except:
                    failed += 1
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await status_msg.edit_text(f"📢 Progress: {i+1}/{total}\n✅ Sent: {sent}\n❌ Failed: {failed}", parse_mode=ParseMode.MARKDOWN)
                await asyncio.sleep(0.2)
            await status_msg.edit_text(f"✅✨ Broadcast Done!\n✅ Sent: {sent}\n❌ Failed: {failed}", parse_mode=ParseMode.MARKDOWN)

    # ==================== HELPER METHODS ====================

    async def _show_screen(self, client, target, screen, user_id, is_edit=False):
        if is_edit:
            try:
                await target.delete()
            except:
                pass

        diamonds = await get_diamonds(user_id)
        is_admin = (user_id == Config.ADMIN_ID)
        count = await get_referral_count(user_id)
        earned = await get_earned_accounts(user_id)

        # ===== CAPTIONS =====
        captions = {
            "welcome": (
                "🌟💎 **Welcome to ASCEND** 💎🌟\n\n"
                "✨ Earn **Telegram Accounts** by inviting friends!\n"
                "🔥 **1 Referral = 1 Diamond**\n"
                f"🎁 **{DIAMOND_COST} Diamonds = 1 Account**\n"
                "💯 **100% Trusted & Secure**\n\n"
                f"💎 **Your Diamonds:** `{diamonds}`\n"
                f"🎯 **Next account in:** `{DIAMOND_COST - (diamonds % DIAMOND_COST)}` diamond(s)"
            ),
            "profile": "",  # Caption not used for dynamic image, but fallback if image fails
            "invite": (
                "🔗✨ **Your Invite Link** ✨🔗\n\n"
                "📤 Share this link with your friends:\n"
                "`https://t.me/{}?start=ref_{}`\n\n"
                "💎 Each referral gives you **1 diamond**."
            ),
            "rewards": (
                "🎁✨ **Rewards** ✨🎁\n\n"
                "Complete tasks and invite more to unlock exclusive rewards.\n"
                "💎 **More invites = More rewards!**"
            ),
            "my_rewards": (
                "📱✨ **My Rewards** ✨📱\n\n"
                "Here are your claimed accounts:\n\n"
                f"{self._format_earned_accounts(earned)}"
            ),
            "progress": (
                "📊✨ **Your Progress** ✨📊\n\n"
                f"💎 **Diamonds:** `{diamonds}`\n"
                f"🎯 **Target:** `{DIAMOND_COST}` diamonds for 1 account\n"
                f"📈 **Progress:** `{diamonds}/{DIAMOND_COST}`\n"
                f"📊 **Referrals:** `{count}`\n\n"
                "💪 Keep going! You're doing great!"
            ),
            "support": (
                "🆘✨ **Support** ✨🆘\n\n"
                "Facing any issue? We are here to help you.\n"
                "Click the button below to contact support."
            ),
            "admin": (
                "🔧✨ **Admin Panel** ✨🔧\n\n"
                "Select an option below."
            ),
            "admin_broadcast": (
                "📢✨ **Broadcast** ✨📢\n\n"
                "Send a message to all users.\n"
                "Use: `/broadcast <message>`\n"
                "Or reply to a message with `/broadcast`."
            ),
        }

        # ===== BUTTONS =====
        keyboard = []
        if screen == "welcome":
            keyboard = [
                [InlineKeyboardButton("👤✨ Profile", callback_data="profile")],
                [InlineKeyboardButton("🔗✨ Invite", callback_data="invite")],
                [InlineKeyboardButton("🎁✨ Rewards", callback_data="rewards")],
                [InlineKeyboardButton("📊✨ Progress", callback_data="progress")],
                [InlineKeyboardButton("🆘✨ Support", callback_data="support")]
            ]
            if diamonds >= DIAMOND_COST:
                keyboard.insert(0, [InlineKeyboardButton("💎🎁 Claim Account", callback_data="claim_reward")])
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧✨ Admin Panel", callback_data="admin")])
            state = "ON" if AUTO_SWITCH_STATE.get(user_id, False) else "OFF"
            keyboard.append([InlineKeyboardButton(f"🔄 Auto-Switch {state}", callback_data="auto_switch")])

        elif screen == "profile":
            keyboard = [[InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]]

        elif screen == "invite":
            user = await get_or_create_user(user_id)
            bot_username = (await client.get_me()).username
            captions["invite"] = captions["invite"].format(bot_username, user['referral_code'])
            keyboard = [
                [InlineKeyboardButton("📋✨ Copy Link", callback_data="copy_link")],
                [InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]
            ]

        elif screen == "rewards":
            keyboard = [
                [InlineKeyboardButton("📱✨ My Rewards", callback_data="my_rewards")],
                [InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]
            ]

        elif screen == "my_rewards":
            keyboard = [[InlineKeyboardButton("🔙✨ Back", callback_data="rewards")]]

        elif screen == "progress":
            keyboard = [[InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]]

        elif screen == "support":
            support_btn = []
            if Config.SUPPORT_ID:
                support_btn = [InlineKeyboardButton("📩✨ Contact Support", url=f"tg://user?id={Config.SUPPORT_ID}")]
            keyboard = [support_btn, [InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]] if support_btn else [[InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]]

        elif screen == "admin":
            keyboard = [
                [InlineKeyboardButton("👥✨ Users", callback_data="admin_users")],
                [InlineKeyboardButton("📢✨ Broadcast", callback_data="admin_broadcast")],
                [InlineKeyboardButton("📊✨ Statistics", callback_data="admin_stats")],
                [InlineKeyboardButton("⚙️✨ Settings", callback_data="admin_settings")],
                [InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]
            ]

        elif screen == "admin_broadcast":
            keyboard = [[InlineKeyboardButton("🔙✨ Back", callback_data="admin")]]

        else:
            keyboard = [[InlineKeyboardButton("🔙✨ Back to Home", callback_data="welcome")]]

        # ===== SEND LOGIC =====
        chat_id = target.chat.id if hasattr(target, 'chat') else target.chat.id
        caption = captions.get(screen, "")

        # SPECIAL CASE: PROFILE SCREEN -> DYNAMIC IMAGE
        if screen == "profile":
            try:
                # Get username if available
                try:
                    user_obj = await client.get_users(user_id)
                    username = f"@{user_obj.username}" if user_obj.username else str(user_id)
                except:
                    username = str(user_id)

                img_bytes = generate_profile_card(user_id, username, diamonds, count, earned)
                await client.send_photo(
                    chat_id=chat_id,
                    photo=img_bytes,
                    caption="👤✨ **Your Dynamic Profile**",  # Optional small caption
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                return  # Skip normal send
            except Exception as e:
                logger.error(f"Dynamic profile failed: {e}. Falling back to static/text.")
                # If dynamic fails, fallback to sending text
                await client.send_message(
                    chat_id=chat_id,
                    text=f"👤✨ **Your Profile**\n\n💎 Diamonds: {diamonds}\n👥 Referrals: {count}\n📱 Accounts Earned: {len(earned)}\n🎯 Next Account: {DIAMOND_COST - (diamonds % DIAMOND_COST)} diamonds",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                return

        # NORMAL SCREENS (Static images)
        image_id = MEDIA_MAPPING.get(screen)
        try:
            if image_id:
                await client.send_photo(
                    chat_id=chat_id,
                    photo=image_id,
                    caption=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            else:
                # If no image ID (should not happen for non-profile), send text
                await client.send_message(
                    chat_id=chat_id,
                    text=caption,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
        except Exception as e:
            logger.error(f"Send failed for {screen}: {e}")
            await client.send_message(
                chat_id=chat_id,
                text=caption + f"\n\n⚠️ Image could not be loaded.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

    def _format_earned_accounts(self, accounts):
        if not accounts:
            return "You haven't claimed any account yet."
        lines = []
        for acc in accounts:
            phone = acc.get('phone', 'N/A')
            masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
            lines.append(f"🔹 ID: `{acc['id']}` | {masked}")
        return "\n".join(lines)

    async def _is_verified(self, client, user_id):
        try:
            if Config.FORCE_CHANNEL:
                try:
                    member = await client.get_chat_member(f"@{Config.FORCE_CHANNEL}", user_id)
                    if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                        return False
                except:
                    return False
            if Config.FORCE_GROUP:
                try:
                    member = await client.get_chat_member(f"@{Config.FORCE_GROUP}", user_id)
                    if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                        return False
                except:
                    return False
            return True
        except:
            return False

    async def _send_force_join_message(self, client, message):
        text = "🔐✨ **Verification Required** ✨🔐\n\nJoin our Channel & Group below:\n\nAfter joining, click **'I have joined'**."
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢✨ Join Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥✨ Join Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅✨ I have joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- OTP FORWARDER (PERMANENT) ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(buyer_id, "❌ Invalid session string.", parse_mode=ParseMode.MARKDOWN)
        return
    logger.info(f"OTP listener started for account {account_id}")
    await _bot_instance.send_message(
        buyer_id,
        "🔁✨ **OTP listener active (no timeout).**\n\n📱 Open Telegram app, enter phone, press 'Next'.\n🔑 OTP will appear here.",
        parse_mode=ParseMode.MARKDOWN
    )
    client = TelegramClient(StringSession(session_string), Config.API_ID, Config.API_HASH, connection_retries=3, retry_delay=1)
    try:
        await client.connect()
        if not await client.is_user_authorized():
            await _bot_instance.send_message(buyer_id, "❌ Session invalid.", parse_mode=ParseMode.MARKDOWN)
            return
        @client.on(events.MessageEdited(chats=777000))
        @client.on(events.NewMessage(chats=777000))
        async def otp_handler(event):
            if event.message.text and ("login code" in event.message.text.lower() or "code" in event.message.text.lower()):
                await _bot_instance.send_message(buyer_id, f"🔑✨ **OTP Received:**\n\n`{event.message.text}`", parse_mode=ParseMode.MARKDOWN)
        await client.start()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info(f"Listener cancelled for account {account_id}")
            raise
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"OTP error: {traceback.format_exc()}")
        await _bot_instance.send_message(buyer_id, f"❌ OTP listener crashed. Click 'Get OTP' to restart.", parse_mode=ParseMode.MARKDOWN)
    finally:
        try:
            await client.disconnect()
        except:
            pass
