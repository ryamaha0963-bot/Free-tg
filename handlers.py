from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatMemberStatus
import logging, asyncio, aiosqlite
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

        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id

            # Force join check
            if not await self._is_verified(client, user_id):
                await self._send_force_join_message(client, message)
                return

            # Referral logic
            if len(message.command) > 1:
                ref_code = message.command[1]
                if ref_code.startswith("ref_"):
                    ref_code = ref_code[4:]
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            try:
                                await client.send_message(
                                    referrer['user_id'],
                                    f"🎉 New referral! User {user_id} used your link.\nTotal: {await get_referral_count(referrer['user_id'])}"
                                )
                            except: pass
                            count = await get_referral_count(referrer['user_id'])
                            if count % 5 == 0:
                                account = await claim_account_for_user(referrer['user_id'])
                                if account:
                                    creds = (
                                        f"🎁 New Account!\n\n📱 Phone: `{account['phone']}`\n"
                                        f"🔑 Password: `{account['password'] or 'N/A'}`\n"
                                        f"🔐 OTP: `{account['otp'] or 'N/A'}`\n"
                                        f"📌 Session: `{account['session_string'] or 'N/A'}`"
                                    )
                                    await client.send_message(referrer['user_id'], creds)
                                    if account['session_string']:
                                        asyncio.create_task(forward_telegram_otp(
                                            account['id'], referrer['user_id'], account['session_string']
                                        ))
                            else:
                                await client.send_message(
                                    referrer['user_id'],
                                    f"📊 Referrals: {count}. {5 - (count % 5)} more for next account."
                                )

            await get_or_create_user(user_id)

            # Main menu
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
                "👋 **Welcome to Referral Account Bot!**\n\n5 referrals = 1 account",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

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
            text = "🔐 **Verification Required**\n\nJoin our Channel & Group to use this bot."
            buttons = []
            if Config.FORCE_CHANNEL:
                buttons.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
            if Config.FORCE_GROUP:
                buttons.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
            buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
            await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    # Show main menu
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
                        "✅ Verified! Welcome.",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                else:
                    await callback.answer("❌ You haven't joined both yet.", show_alert=True)
                return

            # Rest of callbacks...
            if data == "stats":
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                await callback.message.edit_text(
                    f"📊 **Your Stats**\n\n👥 Referrals: {count}\n📱 Accounts Earned: {len(earned)}\nNext: {5 - (count % 5)} more",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                )
                await callback.answer()
            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                link = f"https://t.me/{client.me.username}?start=ref_{user['referral_code']}"
                await callback.message.edit_text(
                    f"🔗 **Your Referral Link**\n\n`{link}`",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Copy", callback_data="copy_link")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ])
                )
                await callback.answer()
            elif data == "copy_link":
                await callback.answer("Copy manually from above.", show_alert=True)
            elif data == "my_accounts":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text("No accounts yet.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
                else:
                    text = "📱 **Your Accounts**\n\n"
                    for acc in accounts:
                        text += f"🔹 {acc['phone']} | Pass: {acc['password'] or 'N/A'}\n"
                    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
                await callback.answer()
            elif data == "help":
                await callback.message.edit_text(
                    "❓ **How it works**\n\n1. Invite friends\n2. 5 referrals = 1 account\n3. Auto-delivery",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                )
                await callback.answer()
            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ Unauthorized", show_alert=True)
                    return
                text = "🔧 **Admin Commands**\n/gensession +91XXXX\n/otp +91XXXX <code>\n/addaccount ..."
                await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]))
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
                await callback.message.edit_text("Main Menu", reply_markup=InlineKeyboardMarkup(keyboard))
                await callback.answer()

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("Usage: /gensession +911234567890")
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply("Already generating. Complete first.")
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"📲 Sending OTP to {phone}...")
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {
                    "client": temp_client,
                    "phone": phone,
                    "phone_code_hash": sent_code.phone_code_hash
                }
                await message.reply(f"OTP sent. Use /otp {phone} <code>")
            except Exception as e:
                await message.reply(f"❌ Failed: {e}")
                if temp_client.is_connected:
                    await temp_client.disconnect()

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: /otp +91XXXX 12345")
                return
            phone, otp_code = parts[1], parts[2]
            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("No pending session. Use /gensession first.")
                return
            if session_data["phone"] != phone:
                await message.reply(f"Phone mismatch. Expected {session_data['phone']}")
                return
            temp_client = session_data["client"]
            try:
                await temp_client.sign_in(phone, otp_code, session_data["phone_code_hash"])
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]
                await message.reply(f"✅ **Session String:**\n`{session_string}`")
            except Exception as e:
                await message.reply(f"❌ Failed: {e}")

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply("Usage: /addaccount <phone> <password> <otp> <session_string> <description>")
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)
            await message.reply(f"✅ Account #{acc_id} added.")

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("No accounts.")
                    return
                text = "📋 All Accounts\n"
                for r in rows:
                    text += f"#{r['id']} | {r['phone']} | {'Sold' if r['is_sold'] else 'Available'}\n"
                await message.reply(text)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("Usage: /refstats <user_id>")
                return
            uid = int(parts[1])
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(f"User {uid}: {count} referrals, {len(accounts)} accounts.")

# ---------- OTP FORWARDER ----------
async def forward_telegram_otp(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        return
    logger.info(f"OTP listener started for account {account_id} -> buyer {buyer_id}")
    try:
        async with Client(f"otp_{account_id}", api_id=Config.API_ID, api_hash=Config.API_HASH, session_string=session_string, in_memory=True) as user_app:
            @user_app.on_message(filters.user(777000) & filters.text)
            async def otp_handler(client, message):
                if "login code" in (message.text or "").lower():
                    await _bot_instance.send_message(buyer_id, f"🔑 **OTP:**\n`{message.text}`")
                    await client.stop()
            await user_app.start()
            await asyncio.sleep(600)
            await _bot_instance.send_message(buyer_id, "⏰ Timeout. Login attempt not detected.")
    except Exception as e:
        logger.error(f"OTP listener error: {e}")
