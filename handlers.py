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
            await message.reply(
                "⚡ **SYSTEM STATUS** ⚡\n\n"
                "┌─────────────────────┐\n"
                "│ 🟢 Bot is **ONLINE**  │\n"
                "│ ⏱️ Latency: **0 ms**  │\n"
                "│ 💎 All systems go.   │\n"
                "└─────────────────────┘",
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_message(filters.command("available"))
        async def available_cmd(client, message):
            try:
                available = await get_available_accounts()
                count = len(available)
                await message.reply(
                    f"📦 **INVENTORY STATUS**\n\n"
                    f"┌─────────────────────┐\n"
                    f"│ 📱 Available: **{count}** │\n"
                    f"│ 💎 Ready for claim.  │\n"
                    f"└─────────────────────┘",
                    parse_mode=ParseMode.MARKDOWN
                )
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
                            diamonds = await get_diamonds(referrer['user_id'])
                            await client.send_message(
                                referrer['user_id'],
                                f"🎉 **NEW REFERRAL**\n\n"
                                f"┌─────────────────────┐\n"
                                f"│ 👤 User **{user_id}**  │\n"
                                f"│ joined using your    │\n"
                                f"│ referral link!       │\n"
                                f"│ 💎 +1 Diamond added! │\n"
                                f"│ 💰 Balance: {diamonds} 💎 │\n"
                                f"│ 🎯 Need {DIAMOND_COST - (diamonds % DIAMOND_COST)} more for next │\n"
                                f"└─────────────────────┘",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await client.send_message(
                                referrer['user_id'],
                                "❌ **Already Referred**\n\nThis user has already been referred by someone else.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 **Self-Referral Not Allowed**", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ **Invalid Referral Link**", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)

            # ---------- MAIN DASHBOARD ----------
            is_admin = (user_id == Config.ADMIN_ID)
            diamonds = await get_diamonds(user_id)
            referrals = await get_referral_count(user_id)
            purchased = len(await get_earned_accounts(user_id))
            progress = diamonds % DIAMOND_COST
            progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
            
            dashboard = (
                f"╔════════════════════════════════╗\n"
                f"          💎 **DIAMOND HUB**\n"
                f"      PREMIUM COMMUNITY\n"
                f"╚════════════════════════════════╝\n\n"
                f"👤 **USER**\n"
                f"├ 🆔 ID: `{user_id}`\n"
                f"├ 💎 Wallet: `{diamonds}`\n"
                f"├ 👥 Referrals: `{referrals}`\n"
                f"├ 📦 Accounts: `{purchased}`\n"
                f"└ 🏆 Rank: `{self._get_rank(referrals)}`\n\n"
                f"⚡ **REFERRAL PROGRESS**\n"
                f"┌─────────────────────┐\n"
                f"│ {progress_bar} {progress}/{DIAMOND_COST} │\n"
                f"└─────────────────────┘\n\n"
                f"🔥 **FEATURES**\n"
                f"✔ Instant Delivery\n"
                f"✔ Auto OTP System\n"
                f"✔ Premium Accounts\n"
                f"✔ Lifetime History\n"
                f"✔ Secure & Safe\n\n"
                f"💠 **SELECT OPTION**"
            )

            keyboard = [
                [InlineKeyboardButton("👤 Profile", callback_data="profile"),
                 InlineKeyboardButton("💎 Wallet", callback_data="wallet")],
                [InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account"),
                 InlineKeyboardButton("📦 My Accounts", callback_data="purchase_history")],
                [InlineKeyboardButton("👥 Referrals", callback_data="referral_link"),
                 InlineKeyboardButton("📊 Dashboard", callback_data="back_main")],
                [InlineKeyboardButton("🆘 Support", callback_data="help")]
            ]
            if is_admin:
                keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
            if Config.SUPPORT_ID:
                keyboard.append([InlineKeyboardButton("📩 Contact Admin", url=f"tg://user?id={Config.SUPPORT_ID}")])

            await message.reply(
                dashboard,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- CALLBACKS ----------
        @app.on_callback_query()
        async def callback_handler(client, callback: CallbackQuery):
            data = callback.data
            user_id = callback.from_user.id

            # ---------- BUY ACCOUNT ----------
            if data == "buy_account":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer(f"❌ Insufficient balance! Need {DIAMOND_COST - diamonds} more.", show_alert=True)
                    return

                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          🛒 **PURCHASE**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"💎 **Product:** Telegram Account\n"
                    f"💰 **Price:** `{DIAMOND_COST}` 💎\n"
                    f"📊 **Your Balance:** `{diamonds}` 💎\n"
                    f"⚡ **After Purchase:** `{diamonds - DIAMOND_COST}` 💎\n\n"
                    f"⚠️ This action is **irreversible**.\n"
                    f"Confirm to proceed.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ Confirm", callback_data="confirm_buy"),
                         InlineKeyboardButton("❌ Cancel", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
                return

            if data == "confirm_buy":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer("❌ Insufficient balance!", show_alert=True)
                    return

                success = await deduct_diamonds(user_id, DIAMOND_COST)
                if not success:
                    await callback.answer("❌ Error deducting diamonds.", show_alert=True)
                    return

                available = await get_available_accounts()
                if not available:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ No accounts available. Try later.", show_alert=True)
                    return

                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await callback.message.edit_text(
                        f"╔════════════════════════════════╗\n"
                        f"          ✅ **SUCCESS**\n"
                        f"╚════════════════════════════════╝\n\n"
                        f"🎉 **Account Purchased!**\n\n"
                        f"📱 **Phone:** `{phone}`\n"
                        f"💎 **Spent:** `{DIAMOND_COST}` 💎\n"
                        f"🔑 **OTP will be forwarded here automatically.**\n\n"
                        f"Enjoy your premium account 🚀",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    if account.get('session_string'):
                        task = asyncio.create_task(forward_telegram_otp_telethon(
                            account['id'], user_id, account['session_string']
                        ))
                        self.otp_tasks[account['id']] = task
                    await callback.answer("✅ Account purchased!")
                else:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ Purchase failed. Contact admin.", show_alert=True)
                return

            # ---------- PROFILE ----------
            if data == "profile":
                diamonds = await get_diamonds(user_id)
                referrals = await get_referral_count(user_id)
                purchased = len(await get_earned_accounts(user_id))
                rank = self._get_rank(referrals)
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          👤 **PROFILE**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"🆔 **User ID:** `{user_id}`\n"
                    f"🏆 **Rank:** {rank}\n"
                    f"💎 **Wallet:** `{diamonds}` 💎\n"
                    f"👥 **Referrals:** `{referrals}`\n"
                    f"📦 **Accounts Purchased:** `{purchased}`\n\n"
                    f"🔥 Keep sharing your referral link\nto earn more diamonds!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- WALLET ----------
            elif data == "wallet":
                diamonds = await get_diamonds(user_id)
                referrals = await get_referral_count(user_id)
                progress = diamonds % DIAMOND_COST
                progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
                total_earned = diamonds  # assuming all earned from referrals
                total_spent = (await get_earned_accounts(user_id)) * DIAMOND_COST if purchased else 0
                purchased = len(await get_earned_accounts(user_id))
                
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          💎 **WALLET**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"💰 **TOTAL BALANCE**\n"
                    f"   `{diamonds}` 💎\n\n"
                    f"📊 **STATISTICS**\n"
                    f"├ Total Earned: `{total_earned}` 💎\n"
                    f"├ Total Spent: `{total_spent}` 💎\n"
                    f"└ Accounts Purchased: `{purchased}`\n\n"
                    f"⚡ **NEXT REWARD**\n"
                    f"┌─────────────────────┐\n"
                    f"│ {progress_bar} {progress}/{DIAMOND_COST} │\n"
                    f"└─────────────────────┘\n\n"
                    f"🎯 Need `{DIAMOND_COST - progress}` more diamonds for next account.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- PURCHASE HISTORY (My Accounts) ----------
            elif data == "purchase_history":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text(
                        f"╔════════════════════════════════╗\n"
                        f"          📦 **MY ACCOUNTS**\n"
                        f"╚════════════════════════════════╝\n\n"
                        "📭 **No accounts purchased yet.**\n\n"
                        "💎 Earn **10 diamonds** to buy your first one!\n"
                        "🔥 Share your referral link now.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                    )
                else:
                    text = f"╔════════════════════════════════╗\n          📦 **MY ACCOUNTS**\n╚════════════════════════════════╝\n\n"
                    for acc in accounts:
                        phone = acc.get('phone', 'N/A')
                        masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
                        text += (
                            f"┌─────────────────────────────┐\n"
                            f"│ 📱 **{masked}**\n"
                            f"│ 💎 Spent: `{acc.get('diamonds_spent', 10)}`\n"
                            f"│ 📅 {acc['claimed_at']}\n"
                            f"│ 🟢 Status: **Delivered**\n"
                            f"└─────────────────────────────┘\n\n"
                        )
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])
                    )
                await callback.answer()

            # ---------- REFERRAL LINK ----------
            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                bot_username = client.me.username
                if not bot_username:
                    await callback.answer("Set bot username first.", show_alert=True)
                    return
                link = f"https://t.me/{bot_username}?start=ref_{user['referral_code']}"
                referrals = await get_referral_count(user_id)
                diamonds = await get_diamonds(user_id)
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          👥 **REFERRALS**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"🔗 **Your Referral Link**\n`{link}`\n\n"
                    f"📊 **Your Stats**\n"
                    f"├ Total Referrals: `{referrals}`\n"
                    f"└ Diamonds Earned: `{diamonds}` 💎\n\n"
                    f"💎 **1 referral = 1 diamond**\n"
                    f"🔥 Share the link and earn rewards!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 Referral Stats", callback_data="referral_stats")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- REFERRAL STATS ----------
            elif data == "referral_stats":
                count = await get_referral_count(user_id)
                diamonds = await get_diamonds(user_id)
                progress = diamonds % DIAMOND_COST
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          📊 **REFERRAL STATS**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"👥 **Total Referrals:** `{count}`\n"
                    f"💰 **Diamonds Earned:** `{diamonds}`\n"
                    f"💎 **Per Referral:** `1`\n"
                    f"🛒 **Accounts Purchased:** `{len(await get_earned_accounts(user_id))}`\n\n"
                    f"🎯 **Next account in:** `{DIAMOND_COST - progress}` diamonds\n\n"
                    f"📈 **Referral Progress**\n"
                    f"┌─────────────────────┐\n"
                    f"│ {self._progress_bar(count, 10)} {count}/10 │\n"
                    f"└─────────────────────┘",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- HELP & SUPPORT ----------
            elif data == "help":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          🆘 **SUPPORT**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"❓ **How can we help you?**\n\n"
                    f"📌 **How to Earn Diamonds**\n"
                    f"   Share your referral link. Each new user gives 1 💎.\n\n"
                    f"📌 **How to Buy Account**\n"
                    f"   Collect {DIAMOND_COST} 💎 and click 'Buy Account'.\n\n"
                    f"📌 **FAQ & Common Issues**\n"
                    f"   • OTP forwarding is automatic.\n"
                    f"   • Accounts are unique & never reused.\n"
                    f"   • Support is available 24/7.\n\n"
                    f"📩 **Contact Admin**\n"
                    f"   {Config.SUPPORT_ID if Config.SUPPORT_ID else 'Not set'}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📩 Contact Admin", url=f"tg://user?id={Config.SUPPORT_ID}") if Config.SUPPORT_ID else InlineKeyboardButton("🔙 Back", callback_data="back_main")],
                        [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- BACK TO MAIN ----------
            elif data == "back_main":
                is_admin = (user_id == Config.ADMIN_ID)
                diamonds = await get_diamonds(user_id)
                referrals = await get_referral_count(user_id)
                purchased = len(await get_earned_accounts(user_id))
                progress = diamonds % DIAMOND_COST
                progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
                
                dashboard = (
                    f"╔════════════════════════════════╗\n"
                    f"          💎 **DIAMOND HUB**\n"
                    f"      PREMIUM COMMUNITY\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"👤 **USER**\n"
                    f"├ 🆔 ID: `{user_id}`\n"
                    f"├ 💎 Wallet: `{diamonds}`\n"
                    f"├ 👥 Referrals: `{referrals}`\n"
                    f"├ 📦 Accounts: `{purchased}`\n"
                    f"└ 🏆 Rank: `{self._get_rank(referrals)}`\n\n"
                    f"⚡ **REFERRAL PROGRESS**\n"
                    f"┌─────────────────────┐\n"
                    f"│ {progress_bar} {progress}/{DIAMOND_COST} │\n"
                    f"└─────────────────────┘\n\n"
                    f"🔥 **FEATURES**\n"
                    f"✔ Instant Delivery\n✔ Auto OTP System\n"
                    f"✔ Premium Accounts\n✔ Lifetime History\n"
                    f"✔ Secure & Safe\n\n"
                    f"💠 **SELECT OPTION**"
                )
                keyboard = [
                    [InlineKeyboardButton("👤 Profile", callback_data="profile"),
                     InlineKeyboardButton("💎 Wallet", callback_data="wallet")],
                    [InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account"),
                     InlineKeyboardButton("📦 My Accounts", callback_data="purchase_history")],
                    [InlineKeyboardButton("👥 Referrals", callback_data="referral_link"),
                     InlineKeyboardButton("📊 Dashboard", callback_data="back_main")],
                    [InlineKeyboardButton("🆘 Support", callback_data="help")]
                ]
                if is_admin:
                    keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                if Config.SUPPORT_ID:
                    keyboard.append([InlineKeyboardButton("📩 Contact Admin", url=f"tg://user?id={Config.SUPPORT_ID}")])
                await callback.message.edit_text(
                    dashboard,
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- FORCE CHECK ----------
            elif data == "force_check":
                if await self._is_verified(client, user_id):
                    is_admin = (user_id == Config.ADMIN_ID)
                    diamonds = await get_diamonds(user_id)
                    referrals = await get_referral_count(user_id)
                    purchased = len(await get_earned_accounts(user_id))
                    progress = diamonds % DIAMOND_COST
                    progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
                    
                    dashboard = (
                        f"╔════════════════════════════════╗\n"
                        f"          💎 **DIAMOND HUB**\n"
                        f"      PREMIUM COMMUNITY\n"
                        f"╚════════════════════════════════╝\n\n"
                        f"✅ **Verification Successful!**\n\n"
                        f"👤 **USER**\n"
                        f"├ 🆔 ID: `{user_id}`\n"
                        f"├ 💎 Wallet: `{diamonds}`\n"
                        f"├ 👥 Referrals: `{referrals}`\n"
                        f"├ 📦 Accounts: `{purchased}`\n"
                        f"└ 🏆 Rank: `{self._get_rank(referrals)}`\n\n"
                        f"⚡ **REFERRAL PROGRESS**\n"
                        f"┌─────────────────────┐\n"
                        f"│ {progress_bar} {progress}/{DIAMOND_COST} │\n"
                        f"└─────────────────────┘\n\n"
                        f"🔥 **FEATURES**\n"
                        f"✔ Instant Delivery\n✔ Auto OTP System\n"
                        f"✔ Premium Accounts\n✔ Lifetime History\n"
                        f"✔ Secure & Safe\n\n"
                        f"💠 **SELECT OPTION**"
                    )
                    keyboard = [
                        [InlineKeyboardButton("👤 Profile", callback_data="profile"),
                         InlineKeyboardButton("💎 Wallet", callback_data="wallet")],
                        [InlineKeyboardButton("🛒 Buy Account", callback_data="buy_account"),
                         InlineKeyboardButton("📦 My Accounts", callback_data="purchase_history")],
                        [InlineKeyboardButton("👥 Referrals", callback_data="referral_link"),
                         InlineKeyboardButton("📊 Dashboard", callback_data="back_main")],
                        [InlineKeyboardButton("🆘 Support", callback_data="help")]
                    ]
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
                    if Config.SUPPORT_ID:
                        keyboard.append([InlineKeyboardButton("📩 Contact Admin", url=f"tg://user?id={Config.SUPPORT_ID}")])
                    await callback.message.edit_text(
                        dashboard,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer("❌ Please join both channel & group first.", show_alert=True)
                return

            # ---------- ADMIN PANEL (Premium) ----------
            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ No access.", show_alert=True)
                    return
                admin_keyboard = [
                    [InlineKeyboardButton("🔑 Generate Session", callback_data="admin_gensession")],
                    [InlineKeyboardButton("📲 Complete OTP", callback_data="admin_otp")],
                    [InlineKeyboardButton("➕ Add Account", callback_data="admin_addaccount")],
                    [InlineKeyboardButton("📋 List Accounts", callback_data="admin_listaccounts")],
                    [InlineKeyboardButton("📊 User Stats", callback_data="admin_refstats")],
                    [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back_main")]
                ]
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          🔧 **ADMIN PANEL**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"🛡️ **Bot Status:** 🟢 Online\n"
                    f"💾 **Database:** 🟢 Connected\n"
                    f"👥 **Total Users:** `{len(await get_all_users())}`\n\n"
                    f"⚡ **Quick Actions**\n"
                    f"Click a button below.",
                    reply_markup=InlineKeyboardMarkup(admin_keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- ADMIN INLINE BUTTON HANDLERS ----------
            elif data == "admin_gensession":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          🔑 **GENERATE SESSION**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"📌 **Command:**\n"
                    f"`/gensession +911234567890`\n\n"
                    f"Replace with the actual phone number.\n"
                    f"You will receive OTP instructions.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_otp":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          📲 **COMPLETE OTP**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"📌 **Command:**\n"
                    f"`/otp +911234567890 12345`\n\n"
                    f"Replace with phone and OTP code.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_addaccount":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          ➕ **ADD ACCOUNT**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"📌 **Command:**\n"
                    f"`/addaccount +911234567890 MyPass123 456789 session_string \"Description\"`\n\n"
                    f"Replace all fields accordingly.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_listaccounts":
                await callback.message.reply("/listaccounts")
                await callback.answer()

            elif data == "admin_refstats":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          📊 **USER STATS**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"📌 **Command:**\n"
                    f"`/refstats <user_id>`\n\n"
                    f"Example: `/refstats 123456789`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_broadcast":
                await callback.message.edit_text(
                    f"╔════════════════════════════════╗\n"
                    f"          📢 **BROADCAST**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"📌 **Command:**\n"
                    f"`/broadcast Your message here`\n\n"
                    f"Or reply to a message with `/broadcast`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Admin", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            else:
                await callback.answer("Unknown action.")

        # ---------- ADMIN COMMANDS (unchanged) ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                f"╔════════════════════════════════╗\n"
                f"          🔧 **ADMIN CMDS**\n"
                f"╚════════════════════════════════╝\n\n"
                f"• `/gensession +91...` – Send OTP\n"
                f"• `/otp +91... 12345` – Complete OTP\n"
                f"• `/addaccount ...` – Add account\n"
                f"• `/listaccounts` – View all\n"
                f"• `/refstats <user_id>` – User stats\n"
                f"• `/available` – Count available\n"
                f"• `/broadcast <msg>` – Broadcast",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- BROADCAST COMMAND ----------
        @app.on_message(filters.command("broadcast") & filters.user(Config.ADMIN_ID))
        async def broadcast_cmd(client, message):
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

                if (i + 1) % 5 == 0 or (i + 1) == total:
                    await status_msg.edit_text(
                        f"📢 **Broadcasting...**\n"
                        f"📤 Sent: `{sent}`\n📭 Failed: `{failed}`\n📊 Progress: `{i+1}/{total}`",
                        parse_mode=ParseMode.MARKDOWN
                    )

                await asyncio.sleep(0.2)

            await status_msg.edit_text(
                f"✅ **Broadcast Complete!**\n\n"
                f"📤 **Sent:** `{sent}`\n"
                f"📭 **Failed:** `{failed}`\n"
                f"👥 **Total users:** `{total}`",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- SESSION GENERATION (unchanged) ----------
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
                text = "╔════════════════════════════════╗\n          📋 **ALL ACCOUNTS**\n╚════════════════════════════════╝\n\n"
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
                f"╔════════════════════════════════╗\n"
                f"          📊 **USER STATS**\n"
                f"╚════════════════════════════════╝\n\n"
                f"👤 User ID: `{uid}`\n"
                f"💰 Wallet: `{diamonds}` 💎\n"
                f"👥 Referrals: `{count}`\n"
                f"📱 Accounts: `{len(accounts)}`",
                parse_mode=ParseMode.MARKDOWN
            )

    # ---------- HELPERS ----------
    def _get_rank(self, referrals):
        if referrals >= 50:
            return "👑 **Diamond King**"
        elif referrals >= 25:
            return "⭐ **Elite Referrer**"
        elif referrals >= 10:
            return "💎 **Gold Referrer**"
        elif referrals >= 5:
            return "🥈 **Silver Referrer**"
        else:
            return "🥉 **Bronze Referrer**"

    def _progress_bar(self, current, total, length=10):
        filled = int(round((current / total) * length)) if total > 0 else 0
        bar = "█" * filled + "░" * (length - filled)
        return bar

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
            f"╔════════════════════════════════╗\n"
            f"          🔐 **VERIFICATION**\n"
            f"╚════════════════════════════════╝\n\n"
            "⚠️ **Access Restricted**\n\n"
            "You must join our **Channel** & **Group**\n"
            "to use this premium bot.\n\n"
            "After joining, click the button below."
        )
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 Join Channel", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 Join Group", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ I have joined", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- PERMANENT OTP FORWARDER ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(
            buyer_id,
            f"╔════════════════════════════════╗\n"
            f"          ❌ **ERROR**\n"
            f"╚════════════════════════════════╝\n\n"
            "Invalid session string. Please contact admin.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    logger.info(f"Telethon OTP listener starting for account {account_id} -> buyer {buyer_id} (permanent)")

    await _bot_instance.send_message(
        buyer_id,
        f"╔════════════════════════════════╗\n"
        f"          🔁 **OTP LISTENER**\n"
        f"╚════════════════════════════════╝\n\n"
        "🟢 **Active (No Timeout)**\n\n"
        "📱 Open Telegram app, enter the phone number,\n"
        "and press **'Next'**.\n\n"
        "🔑 Your OTP will appear here automatically.",
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
                f"╔════════════════════════════════╗\n"
                f"          ❌ **SESSION EXPIRED**\n"
                f"╚════════════════════════════════╝\n\n"
                "The session is invalid. Contact admin.",
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
                    f"╔════════════════════════════════╗\n"
                    f"          🔑 **OTP RECEIVED**\n"
                    f"╚════════════════════════════════╝\n\n"
                    f"`{event.message.text}`\n\n"
                    f"Please enter this code in the Telegram app.",
                    parse_mode=ParseMode.MARKDOWN
                )

        await client.start()

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
            f"╔════════════════════════════════╗\n"
            f"          ❌ **OTP CRASH**\n"
            f"╚════════════════════════════════╝\n\n"
            f"Error: `{str(e)[:100]}`\n"
            "Please click **'Get OTP'** button to restart.",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        try:
            await client.disconnect()
        except:
            pass
