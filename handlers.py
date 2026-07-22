from pyrogram import Client, filters
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

        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id

            if not await self._is_verified(client, user_id):
                await self._send_force_join_message(client, message)
                return

            # ---------- REFERRAL LOGIC ----------
            if len(message.command) > 1:
                ref_param = message.command[1]
                if ref_param.startswith("ref_"):
                    ref_code = ref_param[4:]
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            count = await get_referral_count(referrer['user_id'])
                            logger.info(f"Referrer {referrer['user_id']} now has {count} referrals")

                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **New Referral!**\n\n"
                                f"👤 User `{user_id}` joined using your link.\n"
                                f"📊 Total referrals: **{count}**",
                                parse_mode=ParseMode.MARKDOWN
                            )

                            if count % 2 == 0:
                                logger.info(f"Threshold reached for {referrer['user_id']}")
                                await client.send_message(
                                    referrer['user_id'],
                                    "🎯 **Congratulations! You've reached 2 referrals!**\n"
                                    "⏳ Claiming your account...",
                                    parse_mode=ParseMode.MARKDOWN
                                )

                                available = await get_available_accounts()
                                if not available:
                                    await client.send_message(
                                        referrer['user_id'],
                                        "⚠️ **No accounts available right now.**\n"
                                        "Admin will add more soon. Your referrals are saved.",
                                        parse_mode=ParseMode.MARKDOWN
                                    )
                                    try:
                                        await client.send_message(
                                            Config.ADMIN_ID,
                                            f"⚠️ User {referrer['user_id']} reached {count} referrals but no accounts available."
                                        )
                                    except:
                                        pass
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
                                            f"📌 **Session String:** `{session_str}`\n\n"
                                            "⚠️ **Change credentials immediately.**\n"
                                            "🔁 OTP forwarding is active for **10 minutes** when you login."
                                        )
                                        await client.send_message(referrer['user_id'], creds, parse_mode=ParseMode.MARKDOWN)
                                        if account.get('session_string'):
                                            asyncio.create_task(forward_telegram_otp(
                                                account['id'], referrer['user_id'], account['session_string']
                                            ))
                                    else:
                                        await client.send_message(
                                            referrer['user_id'],
                                            "❌ **Account claim failed.** Admin notified.",
                                            parse_mode=ParseMode.MARKDOWN
                                        )
                                        try:
                                            await client.send_message(
                                                Config.ADMIN_ID,
                                                f"❌ Claim failed for user {referrer['user_id']} with {count} referrals."
                                            )
                                        except:
                                            pass
                            else:
                                remaining = 2 - (count % 2)
                                await client.send_message(
                                    referrer['user_id'],
                                    f"📊 **Referral Progress**\n\n"
                                    f"👥 You have **{count}** referrals.\n"
                                    f"🎯 Need **{remaining}** more to get your next account!",
                                    parse_mode=ParseMode.MARKDOWN
                                )
                        else:
                            await client.send_message(
                                referrer['user_id'],
                                "❌ This user has already been referred by someone else.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 You can't refer yourself!", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ Invalid referral link.", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)

            # ---------- MAIN MENU ----------
            is_admin = (user_id == Config.ADMIN_ID)
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                [InlineKeyboardButton("❓ Help & Info", callback_data="help")]
            ]
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])

            await message.reply(
                "✨ **Referral Account Bot**\n\n"
                "🎯 **Earn Telegram accounts** by inviting your friends.\n"
                "💎 **2 referrals = 1 account**\n\n"
                "👇 Use the buttons below to get started.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- CALLBACK QUERY ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    is_admin = (user_id == Config.ADMIN_ID)
                    keyboard = [
                        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                        [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                        [InlineKeyboardButton("❓ Help & Info", callback_data="help")]
                    ]
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                    await callback.message.edit_text(
                        "✅ **Verification Successful!**\n\n"
                        "✨ **Referral Account Bot**\n\n"
                        "🎯 **Earn Telegram accounts** by inviting your friends.\n"
                        "💎 **2 referrals = 1 account**\n\n"
                        "👇 Use the buttons below to get started.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer(
                        "❌ You haven't joined both yet.\n"
                        "Please join and try again.\n"
                        "If you already joined, contact admin (bot not added to chat).",
                        show_alert=True
                    )
                return

            if data == "stats":
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                remaining = 2 - (count % 2)
                if remaining == 0:
                    remaining = 2
                progress = "▰" * (count % 2) + "▱" * (2 - (count % 2))
                await callback.message.edit_text(
                    f"📊 **Your Stats**\n\n"
                    f"👥 **Referrals:** `{count}`\n"
                    f"📱 **Accounts Earned:** `{len(earned)}`\n"
                    f"🎯 **Next account in:** `{remaining}` referral(s)\n"
                    f"📈 **Progress:** {progress}\n\n"
                    f"💪 Keep sharing your link to earn more!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                if not user or not user.get('referral_code'):
                    await callback.answer("Error generating link. Try again.", show_alert=True)
                    return
                bot_username = client.me.username
                if not bot_username:
                    await callback.answer("Bot has no username. Set a username for your bot first.", show_alert=True)
                    return
                link = f"https://t.me/{bot_username}?start=ref_{user['referral_code']}"
                await callback.message.edit_text(
                    f"🔗 **Your Referral Link**\n\n"
                    f"📎 **Share this link with your friends:**\n"
                    f"`{link}`\n\n"
                    f"📤 When they start the bot, you'll get **+1 referral**.\n"
                    f"🎯 **2 referrals = 1 account**\n\n"
                    f"📋 **Copy it** and start inviting now!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📋 Copy Link", callback_data="copy_link")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "copy_link":
                await callback.answer("📋 Copy the link manually from the message above.", show_alert=True)

            elif data == "my_accounts":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text(
                        "📱 You haven't earned any accounts yet.\n"
                        "Refer **2 friends** to get your first one!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    text = "📱 **Your Earned Accounts**\n\n"
                    for acc in accounts:
                        phone = acc.get('phone', 'N/A')
                        masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
                        text += (
                            f"🔹 **ID:** `{acc['id']}` | {masked}\n"
                            f"   🔑 **Password:** `{acc.get('password', 'N/A')}`\n"
                            f"   🔐 **OTP Backup:** `{acc.get('otp', 'N/A')}`\n"
                            f"   📅 **Claimed:** `{acc['claimed_at']}`\n\n"
                        )
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                        parse_mode=ParseMode.MARKDOWN
                    )
                await callback.answer()

            elif data == "help":
                await callback.message.edit_text(
                    "❓ **How It Works**\n\n"
                    "1️⃣ **Get your referral link** – click the button below.\n"
                    "2️⃣ **Share it** with friends, groups, or social media.\n"
                    "3️⃣ **Earn referrals** – when someone starts the bot, you get +1.\n"
                    "4️⃣ **Claim rewards** – every **2 referrals** gives you **1 Telegram account**.\n"
                    "5️⃣ **Login** – use the account details. OTPs are forwarded automatically.\n\n"
                    "🔒 **Privacy:** Accounts are unique and never reused.\n"
                    "⏳ OTP forwarding active for **10 minutes** after account delivery.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ Unauthorized", show_alert=True)
                    return
                text = (
                    "🔧 **Admin Commands**\n\n"
                    "1️⃣ **Generate Session** (for adding accounts)\n"
                    "   `/gensession +911234567890`\n"
                    "   Then `/otp +911234567890 12345`\n\n"
                    "2️⃣ **Add Account** (after generating session)\n"
                    "   `/addaccount +911234567890 MyPass123 456789 session_string_here \"Premium Account\"`\n\n"
                    "3️⃣ **Update OTP** for an existing account\n"
                    "   `/updateotp 1 987654`\n\n"
                    "4️⃣ **List all accounts**\n"
                    "   `/listaccounts`\n\n"
                    "5️⃣ **View referral stats** of a user\n"
                    "   `/refstats 123456789`\n\n"
                    "6️⃣ **Check available accounts**\n"
                    "   `/available`\n\n"
                    "⚠️ All admin commands work only in **private DM**."
                )
                await callback.message.edit_text(
                    text,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Main", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "back_main":
                is_admin = (user_id == Config.ADMIN_ID)
                keyboard = [
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                    [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                    [InlineKeyboardButton("❓ Help & Info", callback_data="help")]
                ]
                if is_admin:
                    keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                await callback.message.edit_text(
                    "✨ **Referral Account Bot**\n\n"
                    "🎯 **Earn Telegram accounts** by inviting your friends.\n"
                    "💎 **2 referrals = 1 account**\n\n"
                    "👇 Use the buttons below to get started.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            else:
                await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                "🔧 **Admin Commands – With Examples**\n\n"
                "1️⃣ **Generate Session** (for adding accounts)\n"
                "   `/gensession +911234567890`\n"
                "   Then `/otp +911234567890 12345`\n\n"
                "2️⃣ **Add Account** (after generating session)\n"
                "   `/addaccount +911234567890 MyPass123 456789 session_string_here \"Premium Account\"`\n\n"
                "3️⃣ **Update OTP** for an existing account\n"
                "   `/updateotp 1 987654`\n\n"
                "4️⃣ **List all accounts**\n"
                "   `/listaccounts`\n\n"
                "5️⃣ **View referral stats** of a user\n"
                "   `/refstats 123456789`\n\n"
                "6️⃣ **Check available accounts**\n"
                "   `/available`\n\n"
                "⚠️ All admin commands work only in **private DM**.",
                parse_mode=ParseMode.MARKDOWN
            )

        # ✅ /available command – FIXED
        @app.on_message(filters.command("available") & filters.user(Config.ADMIN_ID))
        async def available_cmd(client, message):
            available = await get_available_accounts()
            count = len(available)
            await message.reply(
                f"📦 **Available Accounts:** `{count}`",
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply(
                    "📌 **Usage:** `/gensession +911234567890`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply(
                    "⏳ Already generating. Complete first.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"📲 Sending OTP to `{phone}`...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {
                    "client": temp_client,
                    "phone": phone,
                    "phone_code_hash": sent_code.phone_code_hash
                }
                await message.reply(
                    f"✅ OTP sent!\nNow use `/otp {phone} <code>`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply(f"❌ Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply(
                    "📌 **Usage:** `/otp +911234567890 12345`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            phone, otp_code = parts[1], parts[2]
            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("❌ No pending session.", parse_mode=ParseMode.MARKDOWN)
                return
            if session_data["phone"] != phone:
                await message.reply(f"❌ Phone mismatch. Expected `{session_data['phone']}`", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = session_data["client"]
            await message.reply("⏳ Signing in...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.sign_in(phone, otp_code, session_data["phone_code_hash"])
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]
                await message.reply(
                    f"✅ **Session Generated!**\n\n📱 Phone: `{phone}`\n🔑 Session:\n`{session_string}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply(f"❌ Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply(
                    "📌 **Usage:** `/addaccount <phone> <password> <otp> <session_string> <description>`\n\n"
                    "Example:\n"
                    "`/addaccount +911234567890 MyPass123 456789 session_here \"Premium\"`",
                    parse_mode=ParseMode.MARKDOWN
                )
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
                    await message.reply("No accounts.", parse_mode=ParseMode.MARKDOWN)
                    return
                text = "📋 **All Accounts**\n\n"
                for r in rows:
                    status = "✅ Sold" if r['is_sold'] else "⬜ Available"
                    phone = r['phone'] or 'N/A'
                    text += f"#{r['id']} | {phone} | {status}\n"
                await message.reply(text, parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 Usage: `/refstats <user_id>`", parse_mode=ParseMode.MARKDOWN)
                return
            uid = int(parts[1])
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(f"📊 User {uid}\nReferrals: {count}\nAccounts: {len(accounts)}", parse_mode=ParseMode.MARKDOWN)

    # ---------- HELPERS ----------
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
        text = "🔐 **Verification Required**\n\nJoin our Channel & Group."
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


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
                    await _bot_instance.send_message(
                        buyer_id,
                        f"🔑 **OTP:**\n`{message.text}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    await client.stop()
            await user_app.start()
            await asyncio.sleep(600)
            await _bot_instance.send_message(buyer_id, "⏰ Timeout. No login attempt detected.", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"OTP error: {e}")
