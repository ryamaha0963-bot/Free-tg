from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from pyrogram.enums import ChatMemberStatus, ParseMode
import logging, asyncio, aiosqlite, traceback, time, re
from database import *
from config import Config

# Telethon imports
from telethon import TelegramClient, events
from telethon.sessions import StringSession

logger = logging.getLogger(__name__)
_bot_instance = None

# Referral threshold
REFERRAL_THRESHOLD = 6

class BotHandlers:
    def __init__(self, app: Client):
        global _bot_instance
        _bot_instance = app
        self.app = app
        self.pending_sessions = {}
        self.otp_tasks = {}

        # ---------- PUBLIC COMMANDS ----------
        @app.on_message(filters.command("ping"))
        async def ping_cmd(client, message):
            await message.reply("🏓 **Pong!** Bot is alive and kicking.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("available"))
        async def available_cmd(client, message):
            try:
                available = await get_available_accounts()
                count = len(available)
                await message.reply(f"📦 **Available Accounts:** `{count}`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ **Error:** `{e}`", parse_mode=ParseMode.MARKDOWN)

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
                            # Notify referrer
                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **New Referral!**\n\n"
                                f"👤 User `{user_id}` just joined using your link.\n"
                                f"📊 You now have **{count}** referral(s).\n"
                                f"🎯 **Next account** in `{REFERRAL_THRESHOLD - (count % REFERRAL_THRESHOLD)}` more referral(s).",
                                parse_mode=ParseMode.MARKDOWN
                            )

                            # Check if user has unclaimed rewards
                            earned_accounts = await get_earned_accounts(referrer['user_id'])
                            earned_count = len(earned_accounts)
                            if earned_count < count // REFERRAL_THRESHOLD:
                                await client.send_message(
                                    referrer['user_id'],
                                    f"🎯 **Congratulations!** You've reached **{REFERRAL_THRESHOLD}** referrals!\n"
                                    "You have **1 account** ready to claim.\n\n"
                                    "👇 Click the button below to claim your reward.",
                                    reply_markup=InlineKeyboardMarkup([
                                        [InlineKeyboardButton("🎁 Claim Reward", callback_data=f"claim_reward_{referrer['user_id']}")]
                                    ]),
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
            count = await get_referral_count(user_id)
            earned_accounts = await get_earned_accounts(user_id)
            earned_count = len(earned_accounts)
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                [InlineKeyboardButton("❓ Help & Info", callback_data="help")]
            ]
            if earned_count < count // REFERRAL_THRESHOLD:
                keyboard.insert(0, [InlineKeyboardButton("🎁 Claim Reward", callback_data=f"claim_reward_{user_id}")])
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])

            await message.reply(
                "✨ **Referral Bot**\n\n"
                f"🎯 **Earn Telegram accounts** by inviting friends!\n"
                f"💎 **{REFERRAL_THRESHOLD} referrals = 1 account**\n\n"
                "👇 Use the buttons below.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            # ---------- CLAIM REWARD ----------
            if data.startswith("claim_reward_"):
                claim_user_id = int(data.split("_")[2])
                if claim_user_id != user_id:
                    await callback.answer("❌ This reward is not for you.", show_alert=True)
                    return

                count = await get_referral_count(user_id)
                earned_accounts = await get_earned_accounts(user_id)
                earned_count = len(earned_accounts)
                if earned_count >= count // REFERRAL_THRESHOLD:
                    await callback.answer("❌ You have already claimed all available rewards.", show_alert=True)
                    return

                available = await get_available_accounts()
                if not available:
                    await callback.answer("❌ No accounts available. Please wait.", show_alert=True)
                    return

                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await callback.message.edit_text(
                        f"🎁 **Account Claimed!**\n\n"
                        f"📱 **Phone Number:** `{phone}`\n\n"
                        "Use this number to login.\n"
                        "OTP will be forwarded here automatically when you request it.\n"
                        "Enjoy! 🚀",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    if account.get('session_string'):
                        task = asyncio.create_task(forward_telegram_otp_telethon(
                            account['id'], user_id, account['session_string']
                        ))
                        self.otp_tasks[account['id']] = task
                    await callback.answer("✅ Account claimed!")
                else:
                    await callback.answer("❌ Claim failed. Contact admin.", show_alert=True)
                return

            # ---------- OTHER CALLBACKS ----------
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

                if account_id in self.otp_tasks:
                    self.otp_tasks[account_id].cancel()
                    try:
                        await self.otp_tasks[account_id]
                    except asyncio.CancelledError:
                        pass
                    await asyncio.sleep(0.5)
                    del self.otp_tasks[account_id]

                await callback.answer("🔄 Restarting listener...")
                await callback.message.reply(
                    "🔁 **OTP listener restarted** (15 min).\n\n"
                    "📱 Open Telegram app, enter the phone number, and press **'Next'**.\n"
                    "🔑 The OTP will appear here automatically.",
                    parse_mode=ParseMode.MARKDOWN
                )
                task = asyncio.create_task(forward_telegram_otp_telethon(account_id, user_id, session_string))
                self.otp_tasks[account_id] = task
                return

            if data == "force_check":
                if await self._is_verified(client, user_id):
                    is_admin = (user_id == Config.ADMIN_ID)
                    count = await get_referral_count(user_id)
                    earned_accounts = await get_earned_accounts(user_id)
                    earned_count = len(earned_accounts)
                    keyboard = [
                        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                        [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                        [InlineKeyboardButton("❓ Help", callback_data="help")]
                    ]
                    if earned_count < count // REFERRAL_THRESHOLD:
                        keyboard.insert(0, [InlineKeyboardButton("🎁 Claim Reward", callback_data=f"claim_reward_{user_id}")])
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                    await callback.message.edit_text(
                        "✅ **Verification Successful!**\n\n"
                        "✨ **Referral Bot**\n\n"
                        f"🎯 **Earn Telegram accounts** by inviting friends!\n"
                        f"💎 **{REFERRAL_THRESHOLD} referrals = 1 account**\n\n"
                        "👇 Use the buttons below.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer("❌ Please join both channel & group first.", show_alert=True)
                return

            if data == "stats":
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                earned_count = len(earned)
                unclaimed = (count // REFERRAL_THRESHOLD) - earned_count
                progress = count % REFERRAL_THRESHOLD
                progress_bar = "▰" * progress + "▱" * (REFERRAL_THRESHOLD - progress)
                await callback.message.edit_text(
                    f"📊 **Your Stats**\n\n"
                    f"👥 **Referrals:** `{count}`\n"
                    f"📱 **Accounts Earned:** `{earned_count}`\n"
                    f"🎁 **Unclaimed Rewards:** `{unclaimed}`\n"
                    f"📈 **Progress:** `{progress_bar}`\n\n"
                    f"🎯 **Next account in:** `{REFERRAL_THRESHOLD - progress}` referral(s)\n\n"
                    f"💪 Keep sharing your link to earn more!",
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
                    f"🔗 **Your Referral Link**\n\n"
                    f"📎 **Share this link:**\n`{link}`\n\n"
                    f"📤 When friends start the bot, you get **+1 referral**.\n"
                    f"🎯 **{REFERRAL_THRESHOLD} referrals = 1 account**\n\n"
                    f"📋 **Copy** and start inviting!",
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
                        f"Refer **{REFERRAL_THRESHOLD} friends** to get your first one!",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                    )
                else:
                    text = "📱 **Your Earned Accounts**\n\n"
                    for acc in accounts:
                        phone = acc.get('phone', 'N/A')
                        masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
                        text += (
                            f"🔹 **ID:** `{acc['id']}` | {masked}\n"
                            f"   📅 **Claimed:** `{acc['claimed_at']}`\n\n"
                        )
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                    )
                await callback.answer()

            elif data == "help":
                await callback.message.edit_text(
                    f"❓ **How It Works**\n\n"
                    f"1️⃣ **Get your referral link** – click the button.\n"
                    f"2️⃣ **Share** with friends & groups.\n"
                    f"3️⃣ **Earn referrals** – when someone starts the bot, you get +1.\n"
                    f"4️⃣ **Claim rewards** – every **{REFERRAL_THRESHOLD} referrals** gives you **1 Telegram account**.\n"
                    f"5️⃣ **Claim** – click the 'Claim Reward' button to get your number.\n"
                    f"6️⃣ **Login** – use the phone number. OTP is forwarded automatically.\n\n"
                    "🔒 **Privacy:** Accounts are unique & never reused.\n"
                    "⏳ OTP forwarding active for **15 minutes**.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ No access.", show_alert=True)
                    return
                await callback.message.edit_text(
                    "🔧 **Admin Panel**\n\n"
                    "**Commands (use in private DM):**\n"
                    "• `/gensession +91...` – Send OTP for session\n"
                    "• `/otp +91... 12345` – Complete OTP → session string\n"
                    "• `/addaccount +91... pass otp session \"desc\"` – Add account\n"
                    "• `/listaccounts` – View all accounts\n"
                    "• `/refstats <user_id>` – Check user stats\n"
                    "• `/available` – Count available accounts\n"
                    "• `/ping` – Check bot alive\n\n"
                    "⚠️ All commands are admin-only.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "back_main":
                is_admin = (user_id == Config.ADMIN_ID)
                count = await get_referral_count(user_id)
                earned_accounts = await get_earned_accounts(user_id)
                earned_count = len(earned_accounts)
                keyboard = [
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                    [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                    [InlineKeyboardButton("❓ Help", callback_data="help")]
                ]
                if earned_count < count // REFERRAL_THRESHOLD:
                    keyboard.insert(0, [InlineKeyboardButton("🎁 Claim Reward", callback_data=f"claim_reward_{user_id}")])
                if is_admin:
                    keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                await callback.message.edit_text(
                    "✨ **Referral Bot**\n\n"
                    f"🎯 **Earn Telegram accounts** by inviting friends!\n"
                    f"💎 **{REFERRAL_THRESHOLD} referrals = 1 account**\n\n"
                    "👇 Use the buttons below.",
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
                "🔧 **Admin Commands**\n\n"
                "• `/gensession +91...` – Send OTP for session\n"
                "• `/otp +91... 12345` – Complete OTP → session string\n"
                "• `/addaccount +91... pass otp session \"desc\"` – Add account\n"
                "• `/listaccounts` – View all accounts\n"
                "• `/refstats <user_id>` – Check user stats\n"
                "• `/available` – Count available accounts",
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 **Usage:** `/gensession +911234567890`", parse_mode=ParseMode.MARKDOWN)
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply("⏳ Already generating. Complete first.", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"📲 Sending OTP to `{phone}`...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {"client": temp_client, "phone": phone, "phone_code_hash": sent_code.phone_code_hash}
                await message.reply(f"✅ OTP sent!\nNow use `/otp {phone} <code>`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ Failed: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("📌 **Usage:** `/otp +911234567890 12345`", parse_mode=ParseMode.MARKDOWN)
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
                await message.reply("📌 **Usage:** `/updateotp <account_id> <new_otp>`", parse_mode=ParseMode.MARKDOWN)
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"✅ OTP for account #{acc_id} updated.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("📭 No accounts in database.", parse_mode=ParseMode.MARKDOWN)
                    return
                text = "📋 **All Accounts**\n\n"
                for r in rows:
                    status = "✅ Sold" if r['is_sold'] else "⬜ Available"
                    text += f"#{r['id']} | {r['phone']} | {status}\n"
                await message.reply(text, parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 **Usage:** `/refstats <user_id>`", parse_mode=ParseMode.MARKDOWN)
                return
            uid = int(parts[1])
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(
                f"📊 **User Stats**\n\n"
                f"👤 User ID: `{uid}`\n"
                f"👥 Referrals: `{count}`\n"
                f"📱 Accounts Earned: `{len(accounts)}`\n"
                f"🎁 Unclaimed: `{count // REFERRAL_THRESHOLD - len(accounts)}`",
                parse_mode=ParseMode.MARKDOWN
            )

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
        text = (
            "🔐 **Verification Required**\n\n"
            "To use this bot, you must join our **Channel** & **Group** below:\n\n"
            "After joining, click the **'I have joined'** button."
        )
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- OTP FORWARDER USING TELETHON ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(
            buyer_id,
            "❌ **Invalid session string.**\nPlease contact admin.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    logger.info(f"Telethon OTP listener starting for account {account_id} -> buyer {buyer_id}")

    await _bot_instance.send_message(
        buyer_id,
        "🔁 **OTP listener is active.**\n\n"
        "📱 Open Telegram app, enter the phone number, and press **'Next'**.\n"
        "🔑 The OTP will appear here automatically.\n\n"
        "⏳ This listener will stay active for **15 minutes**.",
        parse_mode=ParseMode.MARKDOWN
    )

    client = TelegramClient(
        StringSession(session_string),
        Config.API_ID,
        Config.API_HASH,
        connection_retries=3,
        retry_delay=1
    )

    try:
        await client.connect()
        if not await client.is_user_authorized():
            await _bot_instance.send_message(
                buyer_id,
                "❌ **Session invalid or expired.**\nPlease contact admin.",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        logger.info(f"Telethon connected for account {account_id}")

        @client.on(events.MessageEdited(chats=777000))
        @client.on(events.NewMessage(chats=777000))
        async def otp_handler(event):
            if event.message.text and ("login code" in event.message.text.lower() or "code" in event.message.text.lower()):
                await _bot_instance.send_message(
                    buyer_id,
                    f"🔑 **OTP Received:**\n\n`{event.message.text}`\n\n"
                    f"Please enter this code in the Telegram app.",
                    parse_mode=ParseMode.MARKDOWN
                )

        await client.start()

        try:
            await asyncio.sleep(900)  # 15 minutes
            await _bot_instance.send_message(
                buyer_id,
                "⏰ **OTP listener expired.**\n"
                "If you still need OTP, click the **'Get OTP'** button again.",
                parse_mode=ParseMode.MARKDOWN
            )
        except asyncio.CancelledError:
            logger.info(f"Telethon listener cancelled for account {account_id}")
            raise

    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(f"Telethon OTP error: {traceback.format_exc()}")
        await _bot_instance.send_message(
            buyer_id,
            f"❌ **OTP listener crashed.**\n"
            f"Error: `{str(e)[:100]}`\n"
            "Please click **'Get OTP'** button to restart.",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        try:
            await client.disconnect()
        except:
            pass
