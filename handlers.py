from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatMemberStatus
import logging
import asyncio
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

        # ---------- START COMMAND (WITH FORCE JOIN) ----------
        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id

            # 🔥 FORCE JOIN VERIFICATION
            if not await self._is_verified(client, user_id):
                await self._send_force_join_message(client, message)
                return

            # ---------- REFERRAL LOGIC (Remains Same) ----------
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

            # ---------- MAIN MENU ----------
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
                "👋 **Welcome to the Referral Account Bot!**\n\n"
                "Earn Telegram accounts by inviting your friends.\n"
                "🎯 **5 referrals = 1 account**\n\n"
                "Use the buttons below to get started.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )

        # ---------- FORCE JOIN MESSAGE & BUTTONS ----------
        async def _send_force_join_message(self, client, message):
            text = "🔐 **Verification Required**\n\n"
            text += "Please join our **Channel** and **Group** to use this bot.\n\n"
            
            buttons = []
            channel = Config.FORCE_CHANNEL
            group = Config.FORCE_GROUP
            
            if channel:
                buttons.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{channel}")])
            if group:
                buttons.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{group}")])
            
            buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
            
            await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons))

        async def _is_verified(self, client, user_id):
            """Check if user has joined channel AND group"""
            try:
                # Check Channel
                if Config.FORCE_CHANNEL:
                    try:
                        member = await client.get_chat_member(f"@{Config.FORCE_CHANNEL}", user_id)
                        if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                            return False
                    except Exception as e:
                        logger.warning(f"Channel check failed: {e}")
                        return False
                
                # Check Group
                if Config.FORCE_GROUP:
                    try:
                        member = await client.get_chat_member(f"@{Config.FORCE_GROUP}", user_id)
                        if member.status not in [ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]:
                            return False
                    except Exception as e:
                        logger.warning(f"Group check failed: {e}")
                        return False
                
                return True
            except Exception as e:
                logger.error(f"Verification error: {e}")
                return False

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            # 🔥 FORCE JOIN CALLBACK (Re-verify)
            if data == "force_check":
                if await self._is_verified(client, user_id):
                    # Verified – Show Main Menu
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
                        "✅ **Verification Successful!**\n\n"
                        "👋 **Welcome to the Referral Account Bot!**\n\n"
                        "Earn Telegram accounts by inviting your friends.\n"
                        "🎯 **5 referrals = 1 account**",
                        reply_markup=InlineKeyboardMarkup(keyboard)
                    )
                    await callback.answer("✅ Verified! Welcome.")
                else:
                    await callback.answer("❌ You haven't joined both yet. Please join and try again.", show_alert=True)
                return

            # ---------- REST OF CALLBACKS (stats, referral_link, etc.) ----------
            # (Pehle jaise hi rahenge, but ensure they also check verification? 
            # Actually, once they pass start, they are verified. But if they click a button later, no need to recheck unless they leave. 
            # We can add a check here too, but skipping for performance, assuming they are verified.)

            if data == "stats":
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                await callback.message.edit_text(
                    f"📊 **Your Stats**\n\n"
                    f"👥 Referrals: **{count}**\n"
                    f"📱 Accounts Earned: **{len(earned)}**\n"
                    f"Next account at: **{5 - (count % 5)}** more referrals",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ])
                )
                await callback.answer()

            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                link = f"https://t.me/{client.me.username}?start=ref_{user['referral_code']}"
                await callback.message.edit_text(
                    f"🔗 **Your Referral Link**\n\n"
                    f"`{link}`\n\n"
                    "Share this link with your friends.\n"
                    "When they start the bot, you get a referral!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Copy", callback_data="copy_link")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ])
                )
                await callback.answer()

            elif data == "copy_link":
                await callback.answer("Copy the link manually from the message above.", show_alert=True)

            elif data == "my_accounts":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text(
                        "📱 You haven't earned any accounts yet.\n"
                        "Refer 5 friends to get your first one!",
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                        ])
                    )
                else:
                    text = "📱 **Your Earned Accounts**\n\n"
                    for acc in accounts:
                        phone = acc['phone']
                        masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
                        text += f"🔹 ID: {acc['id']} | {masked}\n"
                        text += f"   Password: `{acc['password'] or 'N/A'}`\n"
                        text += f"   OTP Backup: `{acc['otp'] or 'N/A'}`\n"
                        text += f"   Claimed: {acc['claimed_at']}\n\n"
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([
                            [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                        ])
                    )
                await callback.answer()

            elif data == "help":
                await callback.message.edit_text(
                    "❓ **How it works**\n\n"
                    "1. Invite friends using your referral link.\n"
                    "2. When they start the bot, you get +1 referral.\n"
                    "3. Every **5 referrals** earns you 1 Telegram account.\n"
                    "4. The account details will be sent to you automatically.\n"
                    "5. When you log in, OTPs will be forwarded here by the bot.\n\n"
                    "🔒 **Privacy:** All accounts are unique and never reused.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ])
                )
                await callback.answer()

            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ Unauthorized!", show_alert=True)
                    return
                text = (
                    "🔧 **Admin Commands**\n\n"
                    "1️⃣ `/gensession +91XXXXX` – Send OTP to generate session\n"
                    "2️⃣ `/otp +91XXXXX <code>` – Verify OTP & get session string\n"
                    "3️⃣ `/addaccount <phone> <password> <otp> <session_string> <desc>` – Add new account\n"
                    "4️⃣ `/updateotp <account_id> <new_otp>` – Update OTP\n"
                    "5️⃣ `/listaccounts` – View all accounts\n"
                    "6️⃣ `/refstats <user_id>` – Check user referrals\n"
                    "7️⃣ `/admin` – Old admin help\n\n"
                    "⚠️ These commands work only in **Private DM**."
                )
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")]
                    ])
                )
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
                await callback.message.edit_text(
                    "👋 **Main Menu**\n\nChoose an option:",
                    reply_markup=InlineKeyboardMarkup(keyboard)
                )
                await callback.answer()

            else:
                await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                "🔧 **Admin Panel**\n\n"
                "/gensession <phone> – Generate session\n"
                "/otp <phone> <code> – Complete session\n"
                "/addaccount <phone> <password> <otp> <session_string> <description> – Add account\n"
                "/updateotp <account_id> <new_otp> – Update OTP\n"
                "/listaccounts – Show all accounts\n"
                "/refstats <user_id> – Referral stats of a user"
            )

        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("Usage: `/gensession +911234567890`")
                return
            phone = parts[1]

            if message.from_user.id in self.pending_sessions:
                await message.reply("⏳ Already generating a session. Complete or wait.")
                return

            temp_client = Client(
                f"temp_{message.from_user.id}",
                api_id=Config.API_ID,
                api_hash=Config.API_HASH,
                in_memory=True
            )
            await message.reply(f"📲 Sending OTP to `{phone}`...")
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {
                    "client": temp_client,
                    "phone": phone,
                    "phone_code_hash": sent_code.phone_code_hash,
                    "step": "awaiting_otp"
                }
                await message.reply(
                    f"✅ OTP sent to `{phone}`!\n\n"
                    "Send OTP using:\n"
                    f"`/otp {phone} <code>`"
                )
            except Exception as e:
                await message.reply(f"❌ Failed to send OTP: `{str(e)}`")
                if temp_client.is_connected:
                    await temp_client.disconnect()

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: `/otp +911234567890 12345`")
                return
            phone, otp_code = parts[1], parts[2]

            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("❌ No pending session. Use `/gensession` first.")
                return
            if session_data["phone"] != phone:
                await message.reply(f"❌ Phone mismatch. Expected `{session_data['phone']}`")
                return

            temp_client = session_data["client"]
            await message.reply("⏳ Signing in...")
            try:
                await temp_client.sign_in(
                    phone_number=phone,
                    code=otp_code,
                    phone_code_hash=session_data["phone_code_hash"]
                )
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]

                await message.reply(
                    f"✅ **Session Generated!**\n\n"
                    f"📱 Phone: `{phone}`\n"
                    f"🔑 Session String:\n`{session_string}`\n\n"
                    f"Use this in `/addaccount` command."
                )
            except Exception as e:
                await message.reply(f"❌ Failed: `{str(e)}`")
                try:
                    await temp_client.disconnect()
                except:
                    pass
                if message.from_user.id in self.pending_sessions:
                    del self.pending_sessions[message.from_user.id]

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply("Usage: /addaccount <phone> <password> <otp> <session_string> <description>")
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)
            await message.reply(f"✅ Account #{acc_id} added successfully!")

        @app.on_message(filters.command("updateotp") & filters.user(Config.ADMIN_ID))
        async def update_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: /updateotp <account_id> <new_otp>")
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"✅ OTP for account #{acc_id} updated to `{new_otp}`")

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("No accounts in database.")
                    return
                text = "📋 **All Accounts**\n\n"
                for r in rows:
                    sold = "✅ Sold" if r['is_sold'] else "⬜ Available"
                    text += f"#{r['id']} | {r['phone']} | {sold}\n"
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
            await message.reply(f"User {uid}: {count} referrals, {len(accounts)} accounts earned.")


# ---------- OTP FORWARDER (Standalone) ----------
async def forward_telegram_otp(account_id: int, buyer_id: int, session_string: str):
    if not session_string or session_string == "N/A" or len(session_string) < 10:
        return
    logger.info(f"Starting OTP listener for account {account_id} -> Buyer {buyer_id}")
    try:
        async with Client(
            f"otp_listener_{account_id}",
            api_id=Config.API_ID,
            api_hash=Config.API_HASH,
            session_string=session_string,
            in_memory=True
        ) as user_app:
            @user_app.on_message(filters.text & filters.user(777000))
            async def otp_handler(client, message):
                text = message.text or ""
                if "login code" in text.lower() or "code" in text.lower():
                    logger.info(f"OTP received for account {account_id}. Forwarding to buyer {buyer_id}")
                    try:
                        await _bot_instance.send_message(
                            buyer_id,
                            f"🔑 **Login Code Received!**\n\n`{text}`\n\nPlease enter this code in the Telegram app."
                        )
                    except Exception as e:
                        logger.error(f"Failed to forward OTP: {e}")
                    await client.stop()
            await user_app.start()
            await asyncio.sleep(600)
            await _bot_instance.send_message(
                buyer_id,
                "⏰ **Timeout:** No login attempt detected in the last 10 minutes. "
                "If you tried to login, contact support."
            )
    except Exception as e:
        logger.error(f"OTP listener crashed: {e}")
        try:
            await _bot_instance.send_message(
                buyer_id,
                f"❌ OTP forwarding error: `{str(e)}`\nPlease use the session string to login via Pyrogram/Telethon."
            )
        except:
            pass
