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

# Diamond cost per account
DIAMOND_COST = 10

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

            # ---------- REFERRAL LOGIC (No Auto-Claim) ----------
            if len(message.command) > 1:
                ref_param = message.command[1]
                if ref_param.startswith("ref_"):
                    ref_code = ref_param[4:]
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            diamonds = await get_diamonds(referrer['user_id'])
                            # Notify referrer – only +1 diamond, no auto-claim
                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **New Referral!**\n\n"
                                f"👤 User `{user_id}` just joined using your link.\n"
                                f"💎 You received **1 diamond**!\n"
                                f"📊 Total diamonds: **{diamonds}**\n"
                                f"🎯 Need `{DIAMOND_COST - (diamonds % DIAMOND_COST)}` more for next account.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                            # If diamonds >= 10, the button will appear automatically in main menu
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
            diamonds = await get_diamonds(user_id)
            keyboard = [
                [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                [InlineKeyboardButton("❓ Help & Info", callback_data="help")]
            ]
            # Show Claim button only if diamonds >= 10 (manual claim)
            if diamonds >= DIAMOND_COST:
                keyboard.insert(0, [InlineKeyboardButton("💎 Claim Account (10 💎)", callback_data="claim_reward")])
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
            if Config.SUPPORT_ID:
                keyboard.append([InlineKeyboardButton("🆘 Support", url=f"tg://user?id={Config.SUPPORT_ID}")])

            await message.reply(
                "✨ **Diamond Referral Bot**\n\n"
                f"💎 **Your Diamonds:** `{diamonds}`\n"
                f"🎯 **Earn diamonds** by inviting friends!\n"
                f"💎 **{DIAMOND_COST} diamonds = 1 account**\n\n"
                "👇 Use the buttons below.",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            # ---------- CLAIM REWARD (Manual) ----------
            if data == "claim_reward":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer(f"❌ You need {DIAMOND_COST - diamonds} more diamonds.", show_alert=True)
                    return

                # Deduct diamonds
                success = await deduct_diamonds(user_id, DIAMOND_COST)
                if not success:
                    await callback.answer("❌ Error deducting diamonds.", show_alert=True)
                    return

                # Claim account
                available = await get_available_accounts()
                if not available:
                    # Refund diamonds
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ No accounts available. Try later.", show_alert=True)
                    return

                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await callback.message.edit_text(
                        f"💎 **Account Claimed!**\n\n"
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
                    # Refund
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ Claim failed. Contact admin.", show_alert=True)
                return

            # ---------- OTP RESTART ----------
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
                    "🔁 **OTP listener restarted.**\n\n"
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
                    diamonds = await get_diamonds(user_id)
                    keyboard = [
                        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                        [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                        [InlineKeyboardButton("❓ Help", callback_data="help")]
                    ]
                    if diamonds >= DIAMOND_COST:
                        keyboard.insert(0, [InlineKeyboardButton("💎 Claim Account (10 💎)", callback_data="claim_reward")])
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                    if Config.SUPPORT_ID:
                        keyboard.append([InlineKeyboardButton("🆘 Support", url=f"tg://user?id={Config.SUPPORT_ID}")])
                    await callback.message.edit_text(
                        "✅ **Verification Successful!**\n\n"
                        "✨ **Diamond Referral Bot**\n\n"
                        f"💎 **Your Diamonds:** `{diamonds}`\n"
                        f"🎯 **Earn diamonds** by inviting friends!\n"
                        f"💎 **{DIAMOND_COST} diamonds = 1 account**\n\n"
                        "👇 Use the buttons below.",
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer("❌ Please join both channel & group first.", show_alert=True)
                return

            if data == "stats":
                diamonds = await get_diamonds(user_id)
                count = await get_referral_count(user_id)
                earned = await get_earned_accounts(user_id)
                await callback.message.edit_text(
                    f"📊 **Your Stats**\n\n"
                    f"💎 **Diamonds:** `{diamonds}`\n"
                    f"👥 **Referrals:** `{count}`\n"
                    f"📱 **Accounts Earned:** `{len(earned)}`\n"
                    f"🎯 **Next account in:** `{DIAMOND_COST - (diamonds % DIAMOND_COST)}` diamond(s)\n\n"
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
                    f"📤 When friends start the bot, you get **+1 diamond**.\n"
                    f"💎 **{DIAMOND_COST} diamonds = 1 account**\n\n"
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
                        f"Earn **{DIAMOND_COST} diamonds** to claim your first one!",
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
                    f"3️⃣ **Earn diamonds** – each referral gives **1 diamond**.\n"
                    f"4️⃣ **Claim accounts** – use **{DIAMOND_COST} diamonds** to get **1 Telegram account**.\n"
                    f"5️⃣ **Login** – use the phone number. OTP is forwarded automatically.\n\n"
                    "🔒 **Privacy:** Accounts are unique & never reused.\n"
                    "⏳ OTP forwarding active **permanently** (no timeout).\n\n"
                    f"🆘 **Support:** {Config.SUPPORT_ID if Config.SUPPORT_ID else 'Contact admin'}",
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
                    "• `/broadcast <message>` – Send message to all users\n"
                    "• `/ping` – Check bot alive\n\n"
                    "⚠️ All commands are admin-only.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "back_main":
                is_admin = (user_id == Config.ADMIN_ID)
                diamonds = await get_diamonds(user_id)
                keyboard = [
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                    [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                    [InlineKeyboardButton("❓ Help", callback_data="help")]
                ]
                if diamonds >= DIAMOND_COST:
                    keyboard.insert(0, [InlineKeyboardButton("💎 Claim Account (10 💎)", callback_data="claim_reward")])
                if is_admin:
                    keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                if Config.SUPPORT_ID:
                    keyboard.append([InlineKeyboardButton("🆘 Support", url=f"tg://user?id={Config.SUPPORT_ID}")])
                await callback.message.edit_text(
                    "✨ **Diamond Referral Bot**\n\n"
                    f"💎 **Your Diamonds:** `{diamonds}`\n"
                    f"🎯 **Earn diamonds** by inviting friends!\n"
                    f"💎 **{DIAMOND_COST} diamonds = 1 account**\n\n"
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
                "• `/available` – Count available accounts\n"
                "• `/broadcast <message>` – Send message to all users",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- BROADCAST COMMAND ----------
        @app.on_message(filters.command("broadcast") & filters.user(Config.ADMIN_ID))
        async def broadcast_cmd(client, message):
            # Check if replying to a message
            if message.reply_to_message:
                text = message.reply_to_message.text or message.reply_to_message.caption
                if not text:
                    await message.reply("❌ The replied message has no text or caption.", parse_mode=ParseMode.MARKDOWN)
                    return
            else:
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    await message.reply(
                        "📌 **Usage:** `/broadcast <message>`\n"
                        "Or reply to a message with `/broadcast` to forward it.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                text = parts[1]

            # Fetch all users
            users = await get_all_users()
            total = len(users)
            if total == 0:
                await message.reply("⚠️ No users found in database.", parse_mode=ParseMode.MARKDOWN)
                return

            status_msg = await message.reply(
                f"📢 **Broadcasting to {total} users...**\n"
                f"📤 Sent: `0`\n📭 Failed: `0`\n📊 Progress: `0/{total}`",
                parse_mode=ParseMode.MARKDOWN
            )

            sent = 0
            failed = 0

            for i, user_id in enumerate(users):
                try:
                    await client.send_message(user_id, text)
                    sent += 1
                except Exception:
                    failed += 1

                # Update progress every 5 users
                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await status_msg.edit_text(
                        f"📢 **Broadcasting...**\n"
                        f"📤 Sent: `{sent}`\n📭 Failed: `{failed}`\n📊 Progress: `{i+1}/{total}`",
                        parse_mode=ParseMode.MARKDOWN
                    )

                await asyncio.sleep(0.2)  # Avoid flood wait

            # Final status
            await status_msg.edit_text(
                f"✅ **Broadcast Complete!**\n\n"
                f"📤 **Sent:** `{sent}`\n"
                f"📭 **Failed:** `{failed}`\n"
                f"👥 **Total users:** `{total}`",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- SESSION GENERATION ----------
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
            diamonds = await get_diamonds(uid)
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(
                f"📊 **User Stats**\n\n"
                f"👤 User ID: `{uid}`\n"
                f"💎 Diamonds: `{diamonds}`\n"
                f"👥 Referrals: `{count}`\n"
                f"📱 Accounts Earned: `{len(accounts)}`",
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


# ---------- PERMANENT OTP FORWARDER (NO TIMEOUT) ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(
            buyer_id,
            "❌ **Invalid session string.**\nPlease contact admin.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    logger.info(f"Telethon OTP listener starting for account {account_id} -> buyer {buyer_id} (permanent)")

    await _bot_instance.send_message(
        buyer_id,
        "🔁 **OTP listener is active (no timeout).**\n\n"
        "📱 Open Telegram app, enter the phone number, and press **'Next'**.\n"
        "🔑 The OTP will appear here automatically.",
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

        # 🔥 Infinite wait – no timeout
        try:
            await asyncio.Event().wait()
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
