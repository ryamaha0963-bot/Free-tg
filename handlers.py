from pyrogram import Client, filters, errors
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ParseMode
import logging, asyncio, aiosqlite, traceback
from database import *
from config import Config

logger = logging.getLogger(__name__)
_bot_instance = None

class BotHandlers:
    def __init__(self, app: Client):
        global _bot_instance
        _bot_instance = app
        self.app = app
        self.pending_sessions = {}
        self.otp_tasks = {}

        @app.on_message(filters.command("ping"))
        async def ping_cmd(client, message):
            await message.reply("🏓 Pong! Bot is alive.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("available"))
        async def available_cmd(client, message):
            try:
                available = await get_available_accounts()
                count = len(available)
                await message.reply(f"📦 **Available Accounts:** `{count}`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ Error: {e}", parse_mode=ParseMode.MARKDOWN)

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
                            count = await get_referral_count(referrer['user_id'])
                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **New Referral!**\n\n👤 User `{user_id}` joined.\n📊 Total: **{count}**",
                                parse_mode=ParseMode.MARKDOWN
                            )
                            if count % 2 == 0:
                                await client.send_message(
                                    referrer['user_id'],
                                    "🎯 **Congratulations! Claiming account...**",
                                    parse_mode=ParseMode.MARKDOWN
                                )
                                try:
                                    available = await get_available_accounts()
                                    if not available:
                                        await client.send_message(
                                            referrer['user_id'],
                                            "⚠️ No accounts available. Admin will add.",
                                            parse_mode=ParseMode.MARKDOWN
                                        )
                                    else:
                                        account = await claim_account_for_user(referrer['user_id'])
                                        if account:
                                            phone = account.get('phone', 'N/A')
                                            password = account.get('password', 'N/A')
                                            otp = account.get('otp', 'N/A')
                                            session_str = account.get('session_string', 'N/A')
                                            creds = (
                                                f"🎁 **Account Delivered!**\n\n"
                                                f"📱 **Phone:** `{phone}`\n"
                                                f"🔑 **Password:** `{password}`\n"
                                                f"🔐 **OTP Backup:** `{otp}`\n"
                                                f"📌 **Session:** `{session_str}`\n\n"
                                                "⚠️ Change credentials.\n"
                                                "🔁 Click button below to get OTP (valid for 15 min)."
                                            )
                                            await client.send_message(
                                                referrer['user_id'],
                                                creds,
                                                reply_markup=InlineKeyboardMarkup([
                                                    [InlineKeyboardButton("📲 Get OTP", callback_data=f"get_otp_{account['id']}")]
                                                ]),
                                                parse_mode=ParseMode.MARKDOWN
                                            )
                                            if account.get('session_string'):
                                                task = asyncio.create_task(forward_telegram_otp(
                                                    account['id'], referrer['user_id'], account['session_string']
                                                ))
                                                self.otp_tasks[account['id']] = task
                                except Exception as e:
                                    await client.send_message(referrer['user_id'], f"❌ Error: {e}", parse_mode=ParseMode.MARKDOWN)
                            else:
                                remaining = 2 - (count % 2)
                                await client.send_message(
                                    referrer['user_id'],
                                    f"📊 Progress: {count} referrals. Need {remaining} more.",
                                    parse_mode=ParseMode.MARKDOWN
                                )
                        else:
                            await client.send_message(referrer['user_id'], "❌ Already referred.", parse_mode=ParseMode.MARKDOWN)
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 Can't refer self!", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ Invalid link.", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)
            is_admin = (user_id == Config.ADMIN_ID)
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                [InlineKeyboardButton("❓ Help", callback_data="help")]
            ]
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
            await message.reply(
                "✨ **Referral Bot**\n\n2 referrals = 1 account",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            if data.startswith("get_otp_"):
                account_id = int(data.split("_")[2])
                account = await get_account_by_id(account_id)
                if not account:
                    await callback.answer("❌ Not found.", show_alert=True)
                    return
                if account.get('sold_to') != user_id:
                    await callback.answer("❌ Not your account.", show_alert=True)
                    return
                session_string = account.get('session_string')
                if not session_string:
                    await callback.answer("❌ No session.", show_alert=True)
                    return

                # Cancel previous listener
                if account_id in self.otp_tasks:
                    self.otp_tasks[account_id].cancel()
                    try:
                        await self.otp_tasks[account_id]
                    except asyncio.CancelledError:
                        pass
                    del self.otp_tasks[account_id]

                await callback.answer("🔄 Restarting listener...")
                await callback.message.reply(
                    "🔁 **OTP listener restarted (15 min).**\n"
                    "Open Telegram app, enter the phone number, and press **'Next'**.\n"
                    "The OTP will appear here automatically.",
                    parse_mode=ParseMode.MARKDOWN
                )
                task = asyncio.create_task(forward_telegram_otp(account_id, user_id, session_string))
                self.otp_tasks[account_id] = task
                return

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    is_admin = (user_id == Config.ADMIN_ID)
                    keyboard = [
                        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                        [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                        [InlineKeyboardButton("❓ Help", callback_data="help")]
                    ]
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                    await callback.message.edit_text(
                        "✅ **Verified!**\nWelcome to Referral Bot.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer("❌ Join both first.", show_alert=True)
                return

            if data == "stats":
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                remaining = 2 - (count % 2)
                if remaining == 0: remaining = 2
                progress = "▰" * (count % 2) + "▱" * (2 - (count % 2))
                await callback.message.edit_text(
                    f"📊 **Stats**\n👥 Referrals: {count}\n📱 Earned: {len(earned)}\n🎯 Next: {remaining}\n{progress}",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                bot_username = client.me.username
                if not bot_username:
                    await callback.answer("Set bot username first.", show_alert=True)
                    return
                link = f"https://t.me/{bot_username}?start=ref_{user['referral_code']}"
                await callback.message.edit_text(
                    f"🔗 **Link**\n`{link}`\n\nShare this!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Copy", callback_data="copy_link")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
            elif data == "copy_link":
                await callback.answer("Copy manually from message.", show_alert=True)
            elif data == "my_accounts":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text("No accounts yet.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
                else:
                    text = "📱 **Your Accounts**\n"
                    for acc in accounts:
                        text += f"🔹 {acc['phone']} | Pass: {acc['password']}\n"
                    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
                await callback.answer()
            elif data == "help":
                await callback.message.edit_text(
                    "❓ **How to use**\n1. Share link\n2. Get 2 referrals\n3. Get account",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ No.", show_alert=True)
                    return
                text = "🔧 **Admin**\n/gensession +91...\n/otp +91... 12345\n/addaccount ...\n/listaccounts\n/refstats"
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]), parse_mode=ParseMode.MARKDOWN)
                await callback.answer()
            elif data == "back_main":
                is_admin = (user_id == Config.ADMIN_ID)
                keyboard = [
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                    [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                    [InlineKeyboardButton("❓ Help", callback_data="help")]
                ]
                if is_admin:
                    keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                await callback.message.edit_text("Main Menu", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode=ParseMode.MARKDOWN)
                await callback.answer()
            else:
                await callback.answer("Unknown.")

        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply("Commands: /gensession, /otp, /addaccount, /listaccounts, /refstats", parse_mode=ParseMode.MARKDOWN)

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
                text = "📋 **Accounts**\n"
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
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(f"User {uid}: {count} refs, {len(accounts)} accs", parse_mode=ParseMode.MARKDOWN)

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
        text = "🔐 Verify\nJoin Channel & Group."
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ Joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- IMPROVED OTP FORWARDER ----------
async def forward_telegram_otp(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(
            buyer_id,
            "❌ **Invalid session string.**\nPlease contact admin.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    logger.info(f"OTP listener starting for account {account_id} -> buyer {buyer_id}")

    # Notify user that listener is starting
    await _bot_instance.send_message(
        buyer_id,
        "🔁 **OTP listener is active.**\n"
        "Open Telegram app, enter the phone number, and press **'Next'**.\n"
        "The OTP will appear here automatically.\n\n"
        "⏳ This listener will stay active for **15 minutes**.",
        parse_mode=ParseMode.MARKDOWN
    )

    try:
        async with Client(
            f"otp_{account_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=session_string,
            in_memory=True
        ) as user_app:
            # Register a handler for messages from Telegram service (777000)
            @user_app.on_message(filters.user(777000) & filters.text)
            async def otp_handler(client, message):
                # Check if it's a login code message
                if "login code" in (message.text or "").lower() or "code" in (message.text or "").lower():
                    # Extract the code (usually a 5-digit number)
                    import re
                    code_match = re.search(r'\b(\d{5,6})\b', message.text)
                    if code_match:
                        code = code_match.group(1)
                    else:
                        code = message.text.strip()
                    
                    # Send the full message to the user
                    await _bot_instance.send_message(
                        buyer_id,
                        f"🔑 **OTP Received:**\n\n`{message.text}`\n\n"
                        f"Please enter this code in the Telegram app.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    # Keep listener alive – do not stop

            # Start the client
            await user_app.start()
            logger.info(f"OTP listener connected for account {account_id}")

            # Keep listener alive for 15 minutes
            try:
                await asyncio.sleep(900)  # 15 minutes
                await _bot_instance.send_message(
                    buyer_id,
                    "⏰ **OTP listener expired.**\n"
                    "If you still need OTP, click the **'Get OTP'** button again.",
                    parse_mode=ParseMode.MARKDOWN
                )
            except asyncio.CancelledError:
                logger.info(f"OTP listener cancelled for account {account_id}")
                # User clicked "Get OTP" again – we'll raise to exit
                raise
    except asyncio.CancelledError:
        # This is expected when user restarts
        raise
    except errors.exceptions.unauthorized_401.Unauthorized:
        logger.error(f"Unauthorized: invalid session for account {account_id}")
        await _bot_instance.send_message(
            buyer_id,
            "❌ **Session expired or invalid.**\n"
            "Please contact admin to get a new session.",
            parse_mode=ParseMode.MARKDOWN
        )
    except Exception as e:
        logger.error(f"OTP listener error for account {account_id}: {traceback.format_exc()}")
        await _bot_instance.send_message(
            buyer_id,
            f"❌ **OTP listener crashed.**\n"
            f"Error: `{str(e)[:100]}`\n"
            "Please click **'Get OTP'** button to restart.",
            parse_mode=ParseMode.MARKDOWN
        )
