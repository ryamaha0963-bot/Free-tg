from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
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

        # ---------- START COMMAND ----------
        @app.on_message(filters.command("start"))
        async def start_cmd(client, message):
            user_id = message.from_user.id

            # Check if start param (referral)
            if len(message.command) > 1:
                ref_code = message.command[1]
                if ref_code.startswith("ref_"):
                    ref_code = ref_code[4:]  # remove prefix
                    referrer = await get_user_by_referral_code(ref_code)
                    if referrer and referrer['user_id'] != user_id:
                        # Record referral
                        success = await add_referral(referrer['user_id'], user_id)
                        if success:
                            # Notify referrer
                            try:
                                await client.send_message(
                                    referrer['user_id'],
                                    f"🎉 **New referral!**\nUser {user_id} used your link.\n"
                                    f"Total referrals: {await get_referral_count(referrer['user_id'])}"
                                )
                            except:
                                pass
                            # Check if referrer reached a multiple of 5
                            count = await get_referral_count(referrer['user_id'])
                            if count % 5 == 0:
                                # Award an account
                                account = await claim_account_for_user(referrer['user_id'])
                                if account:
                                    # Send account details
                                    creds = (
                                        f"🎁 **Congratulations!** You earned a new account!\n\n"
                                        f"📱 Phone: `{account['phone']}`\n"
                                        f"🔑 Password: `{account['password'] or 'N/A'}`\n"
                                        f"🔐 OTP Backup: `{account['otp'] or 'N/A'}`\n"
                                        f"📌 Session String: `{account['session_string'] or 'N/A'}`\n\n"
                                        "⚠️ Change credentials immediately.\n"
                                        "🔁 OTP forwarding is active for 10 minutes when you try to login."
                                    )
                                    await client.send_message(referrer['user_id'], creds)
                                    # Start OTP forwarder
                                    if account['session_string']:
                                        asyncio.create_task(forward_telegram_otp(
                                            account['id'],
                                            referrer['user_id'],
                                            account['session_string']
                                        ))
                            else:
                                # Notify progress
                                await client.send_message(
                                    referrer['user_id'],
                                    f"📊 You now have **{count}** referrals. "
                                    f"{5 - (count % 5)} more to get your next account!"
                                )

            # Ensure user exists in DB
            await get_or_create_user(user_id)

            # Show main menu
            await message.reply(
                "👋 **Welcome to the Referral Account Bot!**\n\n"
                "Earn Telegram accounts by inviting your friends.\n"
                "🎯 **5 referrals = 1 account**\n\n"
                "Use the buttons below to get started.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                    [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                    [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                    [InlineKeyboardButton("❓ Help", callback_data="help")]
                ])
            )

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

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
                # We cannot copy directly, so we just show again with copy hint
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

            elif data == "back_main":
                await callback.message.edit_text(
                    "👋 **Main Menu**\n\nChoose an option:",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 My Stats", callback_data="stats")],
                        [InlineKeyboardButton("🔗 My Referral Link", callback_data="referral_link")],
                        [InlineKeyboardButton("📱 My Earned Accounts", callback_data="my_accounts")],
                        [InlineKeyboardButton("❓ Help", callback_data="help")]
                    ])
                )
                await callback.answer()

            else:
                await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                "🔧 **Admin Panel**\n\n"
                "/addaccount <phone> <password> <otp> <session_string> <description>\n"
                "/updateotp <account_id> <new_otp>\n"
                "/listaccounts - Show all accounts (sold/unsold)\n"
                "/refstats <user_id> - Show referral count for a user"
            )

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply("Usage: /addaccount <phone> <password> <otp> <session_string> <description>")
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)  # price=0
            await message.reply(f"✅ Account #{acc_id} added.")

        @app.on_message(filters.command("updateotp") & filters.user(Config.ADMIN_ID))
        async def update_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("Usage: /updateotp <account_id> <new_otp>")
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"✅ OTP for account #{acc_id} updated.")

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
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

        # ---------- OTP FORWARDER (unchanged) ----------
        # (copy from previous handlers.py)
        # We'll keep the same forward_telegram_otp function

# ---------- OTP FORWARDER (standalone) ----------
async def forward_telegram_otp(account_id: int, buyer_id: int, session_string: str):
    """Same as before, but uses _bot_instance to send OTPs"""
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
                "⏰ **Timeout:** No login attempt detected in 10 minutes. Contact admin if needed."
            )
    except Exception as e:
        logger.error(f"OTP listener crashed: {e}")
        try:
            await _bot_instance.send_message(buyer_id, f"❌ OTP error: {str(e)}")
        except:
            pass
