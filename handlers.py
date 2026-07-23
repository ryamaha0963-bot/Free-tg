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
                "⚡ 𝗦𝗬𝗦𝗧𝗘𝗠 𝗦𝗧𝗔𝗧𝗨𝗦\n\n"
                "🟢 𝗕𝗼𝘁 𝗶𝘀 𝗼𝗻𝗹𝗶𝗻𝗲\n"
                "⏱️ 𝗟𝗮𝘁𝗲𝗻𝗰𝘆: 𝟬 𝗺𝘀\n"
                "💎 𝗔𝗹𝗹 𝘀𝘆𝘀𝘁𝗲𝗺𝘀 𝗼𝗽𝗲𝗿𝗮𝘁𝗶𝗼𝗻𝗮𝗹",
                parse_mode=ParseMode.MARKDOWN
            )

        @app.on_message(filters.command("available"))
        async def available_cmd(client, message):
            try:
                available = await get_available_accounts()
                count = len(available)
                await message.reply(
                    f"📦 𝗜𝗡𝗩𝗘𝗡𝗧𝗢𝗥𝗬 𝗦𝗧𝗔𝗧𝗨𝗦\n\n"
                    f"📱 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲: **{count}**\n"
                    f"💎 𝗥𝗲𝗮𝗱𝘆 𝗳𝗼𝗿 𝗰𝗹𝗮𝗶𝗺",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply(f"❌ 𝗘𝗿𝗿𝗼𝗿: `{e}`", parse_mode=ParseMode.MARKDOWN)

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
                                f"🎉 𝗡𝗘𝗪 𝗥𝗘𝗙𝗘𝗥𝗥𝗔𝗟\n\n"
                                f"👤 𝗨𝘀𝗲𝗿 **{user_id}** 𝗷𝗼𝗶𝗻𝗲𝗱 𝘃𝗶𝗮 𝘆𝗼𝘂𝗿 𝗹𝗶𝗻𝗸.\n"
                                f"💎 +𝟭 𝗖𝗿𝗲𝗱𝗶𝘁 𝗮𝗱𝗱𝗲𝗱.\n"
                                f"💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: **{diamonds}** 💎\n"
                                f"🎯 𝗡𝗲𝗲𝗱 {DIAMOND_COST - (diamonds % DIAMOND_COST)} 𝗺𝗼𝗿𝗲 𝗳𝗼𝗿 𝗻𝗲𝘅𝘁 𝗮𝗰𝗰𝗼𝘂𝗻𝘁.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                        else:
                            await client.send_message(
                                referrer['user_id'],
                                "❌ 𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗥𝗲𝗳𝗲𝗿𝗿𝗲𝗱\n\n"
                                "𝗧𝗵𝗶𝘀 𝘂𝘀𝗲𝗿 𝗵𝗮𝘀 𝗮𝗹𝗿𝗲𝗮𝗱𝘆 𝗯𝗲𝗲𝗻 𝗿𝗲𝗳𝗲𝗿𝗿𝗲𝗱 𝗯𝘆 𝘀𝗼𝗺𝗲𝗼𝗻𝗲 𝗲𝗹𝘀𝗲.",
                                parse_mode=ParseMode.MARKDOWN
                            )
                    else:
                        if referrer and referrer['user_id'] == user_id:
                            await message.reply("😄 𝗦𝗲𝗹𝗳-𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗶𝘀 𝗻𝗼𝘁 𝗮𝗹𝗹𝗼𝘄𝗲𝗱.", parse_mode=ParseMode.MARKDOWN)
                        else:
                            await message.reply("❌ 𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗹𝗶𝗻𝗸.", parse_mode=ParseMode.MARKDOWN)

            await get_or_create_user(user_id)

            # ---------- MAIN DASHBOARD ----------
            is_admin = (user_id == Config.ADMIN_ID)
            diamonds = await get_diamonds(user_id)
            referrals = await get_referral_count(user_id)
            purchased = len(await get_earned_accounts(user_id))
            progress = diamonds % DIAMOND_COST
            progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
            
            dashboard = (
                f"🚀 𝗪𝗘𝗟𝗖𝗢𝗠𝗘\n\n"
                f"𝗦𝘂𝗰𝗰𝗲𝘀𝘀 𝗶𝘀𝗻'𝘁 𝗴𝗶𝘃𝗲𝗻.\n"
                f"𝗜𝘁'𝘀 𝗲𝗮𝗿𝗻𝗲𝗱.\n\n"
                f"─── • ───\n\n"
                f"👤 𝗨𝘀𝗲𝗿 𝗜𝗗: `{user_id}`\n"
                f"💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀: `{diamonds}`\n"
                f"👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{referrals}`\n"
                f"📦 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: `{purchased}`\n"
                f"🏆 𝗥𝗮𝗻𝗸: {self._get_rank(referrals)}\n\n"
                f"─── • ───\n\n"
                f"⚡ 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀\n"
                f"{progress_bar} {progress}/{DIAMOND_COST}\n\n"
                f"─── • ───\n\n"
                f"🔥 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀\n"
                f"• 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆\n"
                f"• 𝗔𝘂𝘁𝗼 𝗢𝗧𝗣 𝗦𝘆𝘀𝘁𝗲𝗺\n"
                f"• 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀\n"
                f"• 𝗟𝗶𝗳𝗲𝘁𝗶𝗺𝗲 𝗛𝗶𝘀𝘁𝗼𝗿𝘆\n"
                f"• 𝗦𝗲𝗰𝘂𝗿𝗲 & 𝗦𝗮𝗳𝗲\n\n"
                f"─── • ───\n\n"
                f"💠 𝗦𝗘𝗟𝗘𝗖𝗧 𝗢𝗣𝗧𝗜𝗢𝗡"
            )

            keyboard = [
                [InlineKeyboardButton("👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲", callback_data="profile"),
                 InlineKeyboardButton("💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀", callback_data="wallet")],
                [InlineKeyboardButton("🎁 𝗚𝗲𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", callback_data="buy_account"),
                 InlineKeyboardButton("📦 𝗠𝘆 𝗥𝗲𝘄𝗮𝗿𝗱𝘀", callback_data="purchase_history")],
                [InlineKeyboardButton("👥 𝗜𝗻𝘃𝗶𝘁𝗲", callback_data="referral_link"),
                 InlineKeyboardButton("📊 𝗗𝗮𝘀𝗵𝗯𝗼𝗮𝗿𝗱", callback_data="back_main")],
                [InlineKeyboardButton("🆘 𝗦𝘂𝗽𝗽𝗼𝗿𝘁", callback_data="help")]
            ]
            if is_admin:
                keyboard.append([InlineKeyboardButton("⚙️ 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")])
            if Config.SUPPORT_ID:
                keyboard.append([InlineKeyboardButton("📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗔𝗱𝗺𝗶𝗻", url=f"tg://user?id={Config.SUPPORT_ID}")])

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
                    await callback.answer(f"❌ 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗯𝗮𝗹𝗮𝗻𝗰𝗲! 𝗡𝗲𝗲𝗱 {DIAMOND_COST - diamonds} 𝗺𝗼𝗿𝗲.", show_alert=True)
                    return

                await callback.message.edit_text(
                    f"🛒 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘\n\n"
                    f"💎 𝗣𝗿𝗼𝗱𝘂𝗰𝘁: 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗔𝗰𝗰𝗼𝘂𝗻𝘁\n"
                    f"💰 𝗣𝗿𝗶𝗰𝗲: **{DIAMOND_COST}** 💎\n"
                    f"📊 𝗬𝗼𝘂𝗿 𝗯𝗮𝗹𝗮𝗻𝗰𝗲: **{diamonds}** 💎\n"
                    f"⚡ 𝗔𝗳𝘁𝗲𝗿 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲: **{diamonds - DIAMOND_COST}** 💎\n\n"
                    f"─── • ───\n\n"
                    f"⚠️ 𝗧𝗵𝗶𝘀 𝗮𝗰𝘁𝗶𝗼𝗻 𝗶𝘀 𝗶𝗿𝗿𝗲𝘃𝗲𝗿𝘀𝗶𝗯𝗹𝗲.\n"
                    f"𝗖𝗼𝗻𝗳𝗶𝗿𝗺 𝘁𝗼 𝗽𝗿𝗼𝗰𝗲𝗲𝗱.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("✅ 𝗖𝗼𝗻𝗳𝗶𝗿𝗺", callback_data="confirm_buy"),
                         InlineKeyboardButton("❌ 𝗖𝗮𝗻𝗰𝗲𝗹", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()
                return

            if data == "confirm_buy":
                diamonds = await get_diamonds(user_id)
                if diamonds < DIAMOND_COST:
                    await callback.answer("❌ 𝗜𝗻𝘀𝘂𝗳𝗳𝗶𝗰𝗶𝗲𝗻𝘁 𝗯𝗮𝗹𝗮𝗻𝗰𝗲!", show_alert=True)
                    return

                success = await deduct_diamonds(user_id, DIAMOND_COST)
                if not success:
                    await callback.answer("❌ 𝗘𝗿𝗿𝗼𝗿 𝗱𝗲𝗱𝘂𝗰𝘁𝗶𝗻𝗴 𝗰𝗿𝗲𝗱𝗶𝘁𝘀.", show_alert=True)
                    return

                available = await get_available_accounts()
                if not available:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ 𝗡𝗼 𝗮𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲. 𝗣𝗹𝗲𝗮𝘀𝗲 𝘁𝗿𝘆 𝗹𝗮𝘁𝗲𝗿.", show_alert=True)
                    return

                account = await claim_account_for_user(user_id)
                if account:
                    phone = account.get('phone', 'N/A')
                    await callback.message.edit_text(
                        f"✅ 𝗣𝗨𝗥𝗖𝗛𝗔𝗦𝗘 𝗦𝗨𝗖𝗖𝗘𝗦𝗦\n\n"
                        f"🎉 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗮𝗰𝗾𝘂𝗶𝗿𝗲𝗱!\n\n"
                        f"📱 𝗣𝗵𝗼𝗻𝗲: `{phone}`\n"
                        f"💎 𝗦𝗽𝗲𝗻𝘁: **{DIAMOND_COST}** 💎\n"
                        f"🔑 𝗢𝗧𝗣 𝘄𝗶𝗹𝗹 𝗯𝗲 𝗳𝗼𝗿𝘄𝗮𝗿𝗱𝗲𝗱 𝗮𝘂𝘁𝗼𝗺𝗮𝘁𝗶𝗰𝗮𝗹𝗹𝘆.\n\n"
                        f"─── • ───\n\n"
                        f"𝗘𝗻𝗷𝗼𝘆 𝘆𝗼𝘂𝗿 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗮𝗰𝗰𝗼𝘂𝗻𝘁 🚀",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    if account.get('session_string'):
                        task = asyncio.create_task(forward_telegram_otp_telethon(
                            account['id'], user_id, account['session_string']
                        ))
                        self.otp_tasks[account['id']] = task
                    await callback.answer("✅ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱!")
                else:
                    await deduct_diamonds(user_id, -DIAMOND_COST)
                    await callback.answer("❌ 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲 𝗳𝗮𝗶𝗹𝗲𝗱. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗰𝗼𝗻𝘁𝗮𝗰𝘁 𝗮𝗱𝗺𝗶𝗻.", show_alert=True)
                return

            # ---------- PROFILE ----------
            if data == "profile":
                diamonds = await get_diamonds(user_id)
                referrals = await get_referral_count(user_id)
                purchased = len(await get_earned_accounts(user_id))
                rank = self._get_rank(referrals)
                await callback.message.edit_text(
                    f"👤 𝗣𝗥𝗢𝗙𝗜𝗟𝗘\n\n"
                    f"🆔 𝗨𝘀𝗲𝗿 𝗜𝗗: `{user_id}`\n"
                    f"🏆 𝗥𝗮𝗻𝗸: {rank}\n"
                    f"💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀: `{diamonds}` 💎\n"
                    f"👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{referrals}`\n"
                    f"📦 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: `{purchased}`\n\n"
                    f"─── • ───\n\n"
                    f"🔥 𝗦𝗵𝗮𝗿𝗲 𝘆𝗼𝘂𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗹𝗶𝗻𝗸 𝘁𝗼 𝗲𝗮𝗿𝗻 𝗺𝗼𝗿𝗲 𝗰𝗿𝗲𝗱𝗶𝘁𝘀.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- WALLET (CREDITS) ----------
            elif data == "wallet":
                diamonds = await get_diamonds(user_id)
                referrals = await get_referral_count(user_id)
                progress = diamonds % DIAMOND_COST
                progress_bar = "█" * progress + "░" * (DIAMOND_COST - progress) if progress > 0 else "░░░░░░░░░░"
                total_earned = diamonds  # assuming all earned from referrals
                purchased = len(await get_earned_accounts(user_id))
                total_spent = purchased * DIAMOND_COST if purchased else 0
                
                await callback.message.edit_text(
                    f"💠 𝗖𝗥𝗘𝗗𝗜𝗧𝗦\n\n"
                    f"💰 𝗕𝗮𝗹𝗮𝗻𝗰𝗲: **{diamonds}** 💎\n\n"
                    f"─── • ───\n\n"
                    f"📊 𝗦𝘁𝗮𝘁𝗶𝘀𝘁𝗶𝗰𝘀\n"
                    f"• 𝗧𝗼𝘁𝗮𝗹 𝗲𝗮𝗿𝗻𝗲𝗱: **{total_earned}** 💎\n"
                    f"• 𝗧𝗼𝘁𝗮𝗹 𝘀𝗽𝗲𝗻𝘁: **{total_spent}** 💎\n"
                    f"• 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: **{purchased}**\n\n"
                    f"─── • ───\n\n"
                    f"⚡ 𝗡𝗲𝘅𝘁 𝗿𝗲𝘄𝗮𝗿𝗱\n"
                    f"{progress_bar} {progress}/{DIAMOND_COST}\n\n"
                    f"🎯 𝗡𝗲𝗲𝗱 **{DIAMOND_COST - progress}** 𝗺𝗼𝗿𝗲 𝗰𝗿𝗲𝗱𝗶𝘁𝘀 𝗳𝗼𝗿 𝘁𝗵𝗲 𝗻𝗲𝘅𝘁 𝗮𝗰𝗰𝗼𝘂𝗻𝘁.",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🎁 𝗚𝗲𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", callback_data="buy_account")],
                        [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]
                    ]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- PURCHASE HISTORY (My Rewards) ----------
            elif data == "purchase_history":
                accounts = await get_earned_accounts(user_id)
                if not accounts:
                    await callback.message.edit_text(
                        f"📦 𝗠𝗬 𝗥𝗘𝗪𝗔𝗥𝗗𝗦\n\n"
                        "📭 𝗡𝗼 𝗮𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱 𝘆𝗲𝘁.\n\n"
                        "💎 𝗘𝗮𝗿𝗻 **10** 𝗰𝗿𝗲𝗱𝗶𝘁𝘀 𝘁𝗼 𝗮𝗰𝗾𝘂𝗶𝗿𝗲 𝘆𝗼𝘂𝗿 𝗳𝗶𝗿𝘀𝘁 𝗼𝗻𝗲.\n"
                        "🔥 𝗦𝗵𝗮𝗿𝗲 𝘆𝗼𝘂𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗹𝗶𝗻𝗸 𝗻𝗼𝘄.",
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]])
                    )
                else:
                    text = f"📦 𝗠𝗬 𝗥𝗘𝗪𝗔𝗥𝗗𝗦\n\n"
                    for acc in accounts:
                        phone = acc.get('phone', 'N/A')
                        masked = phone[:4] + "****" + phone[-4:] if len(phone) > 8 else phone
                        text += (
                            f"📱 **{masked}**\n"
                            f"💎 𝗦𝗽𝗲𝗻𝘁: `{acc.get('diamonds_spent', 10)}`\n"
                            f"📅 {acc['claimed_at']}\n"
                            f"🟢 𝗦𝘁𝗮𝘁𝘂𝘀: 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝗲𝗱\n\n"
                        )
                    await callback.message.edit_text(
                        text,
                        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]])
                    )
                await callback.answer()

            # ---------- REFERRAL LINK (Invite) ----------
            elif data == "referral_link":
                user = await get_or_create_user(user_id)
                bot_username = client.me.username
                if not bot_username:
                    await callback.answer("𝗦𝗲𝘁 𝗯𝗼𝘁 𝘂𝘀𝗲𝗿𝗻𝗮𝗺𝗲 𝗳𝗶𝗿𝘀𝘁.", show_alert=True)
                    return
                link = f"https://t.me/{bot_username}?start=ref_{user['referral_code']}"
                referrals = await get_referral_count(user_id)
                diamonds = await get_diamonds(user_id)
                await callback.message.edit_text(
                    f"👥 𝗜𝗡𝗩𝗜𝗧𝗘\n\n"
                    f"🔗 𝗬𝗼𝘂𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗹𝗶𝗻𝗸:\n`{link}`\n\n"
                    f"─── • ───\n\n"
                    f"📊 𝗬𝗼𝘂𝗿 𝘀𝘁𝗮𝘁𝘀\n"
                    f"• 𝗧𝗼𝘁𝗮𝗹 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{referrals}`\n"
                    f"• 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗲𝗮𝗿𝗻𝗲𝗱: `{diamonds}` 💎\n\n"
                    f"💎 𝟭 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 = 𝟭 𝗰𝗿𝗲𝗱𝗶𝘁\n"
                    f"🔥 𝗦𝗵𝗮𝗿𝗲 𝘁𝗵𝗲 𝗹𝗶𝗻𝗸 𝗮𝗻𝗱 𝘀𝘁𝗮𝗿𝘁 𝗲𝗮𝗿𝗻𝗶𝗻𝗴!",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📊 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗦𝘁𝗮𝘁𝘀", callback_data="referral_stats")],
                        [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]
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
                    f"📊 𝗥𝗘𝗙𝗘𝗥𝗥𝗔𝗟 𝗦𝗧𝗔𝗧𝗦\n\n"
                    f"👥 𝗧𝗼𝘁𝗮𝗹 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: **{count}**\n"
                    f"💰 𝗖𝗿𝗲𝗱𝗶𝘁𝘀 𝗲𝗮𝗿𝗻𝗲𝗱: **{diamonds}** 💎\n"
                    f"💎 𝗣𝗲𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹: 𝟭\n"
                    f"🛒 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗽𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: **{len(await get_earned_accounts(user_id))}**\n\n"
                    f"─── • ───\n\n"
                    f"🎯 𝗡𝗲𝘅𝘁 𝗮𝗰𝗰𝗼𝘂𝗻𝘁 𝗶𝗻: **{DIAMOND_COST - progress}** 𝗰𝗿𝗲𝗱𝗶𝘁𝘀\n\n"
                    f"📈 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗽𝗿𝗼𝗴𝗿𝗲𝘀𝘀\n"
                    f"{self._progress_bar(count, 10)} {count}/10",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- HELP & SUPPORT ----------
            elif data == "help":
                await callback.message.edit_text(
                    f"🆘 𝗦𝗨𝗣𝗣𝗢𝗥𝗧\n\n"
                    f"❓ 𝗛𝗼𝘄 𝗰𝗮𝗻 𝘄𝗲 𝗮𝘀𝘀𝗶𝘀𝘁 𝘆𝗼𝘂?\n\n"
                    f"─── • ───\n\n"
                    f"📌 𝗛𝗼𝘄 𝘁𝗼 𝗲𝗮𝗿𝗻 𝗰𝗿𝗲𝗱𝗶𝘁𝘀\n"
                    f"   𝗦𝗵𝗮𝗿𝗲 𝘆𝗼𝘂𝗿 𝗿𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗹𝗶𝗻𝗸. 𝗘𝗮𝗰𝗵 𝗻𝗲𝘄 𝘂𝘀𝗲𝗿 𝗴𝗶𝘃𝗲𝘀 𝟭 💎.\n\n"
                    f"📌 𝗛𝗼𝘄 𝘁𝗼 𝗯𝘂𝘆 𝗮𝗻 𝗮𝗰𝗰𝗼𝘂𝗻𝘁\n"
                    f"   𝗖𝗼𝗹𝗹𝗲𝗰𝘁 {DIAMOND_COST} 💎 𝗮𝗻𝗱 𝗰𝗹𝗶𝗰𝗸 '𝗚𝗲𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁'.\n\n"
                    f"📌 𝗙𝗔𝗤\n"
                    f"   • 𝗢𝗧𝗣 𝗳𝗼𝗿𝘄𝗮𝗿𝗱𝗶𝗻𝗴 𝗶𝘀 𝗮𝘂𝘁𝗼𝗺𝗮𝘁𝗶𝗰.\n"
                    f"   • 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗮𝗿𝗲 𝘂𝗻𝗶𝗾𝘂𝗲 𝗮𝗻𝗱 𝗻𝗲𝘃𝗲𝗿 𝗿𝗲𝘂𝘀𝗲𝗱.\n"
                    f"   • 𝗦𝘂𝗽𝗽𝗼𝗿𝘁 𝗶𝘀 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲 𝟮𝟰/𝟳.\n\n"
                    f"─── • ───\n\n"
                    f"📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗔𝗱𝗺𝗶𝗻\n"
                    f"   {Config.SUPPORT_ID if Config.SUPPORT_ID else '𝗡𝗼𝘁 𝘀𝗲𝘁'}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗔𝗱𝗺𝗶𝗻", url=f"tg://user?id={Config.SUPPORT_ID}") if Config.SUPPORT_ID else InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")],
                        [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]
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
                    f"🚀 𝗪𝗘𝗟𝗖𝗢𝗠𝗘\n\n"
                    f"𝗦𝘂𝗰𝗰𝗲𝘀𝘀 𝗶𝘀𝗻'𝘁 𝗴𝗶𝘃𝗲𝗻.\n"
                    f"𝗜𝘁'𝘀 𝗲𝗮𝗿𝗻𝗲𝗱.\n\n"
                    f"─── • ───\n\n"
                    f"👤 𝗨𝘀𝗲𝗿 𝗜𝗗: `{user_id}`\n"
                    f"💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀: `{diamonds}`\n"
                    f"👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{referrals}`\n"
                    f"📦 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: `{purchased}`\n"
                    f"🏆 𝗥𝗮𝗻𝗸: {self._get_rank(referrals)}\n\n"
                    f"─── • ───\n\n"
                    f"⚡ 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀\n"
                    f"{progress_bar} {progress}/{DIAMOND_COST}\n\n"
                    f"─── • ───\n\n"
                    f"🔥 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀\n"
                    f"• 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆\n"
                    f"• 𝗔𝘂𝘁𝗼 𝗢𝗧𝗣 𝗦𝘆𝘀𝘁𝗲𝗺\n"
                    f"• 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀\n"
                    f"• 𝗟𝗶𝗳𝗲𝘁𝗶𝗺𝗲 𝗛𝗶𝘀𝘁𝗼𝗿𝘆\n"
                    f"• 𝗦𝗲𝗰𝘂𝗿𝗲 & 𝗦𝗮𝗳𝗲\n\n"
                    f"─── • ───\n\n"
                    f"💠 𝗦𝗘𝗟𝗘𝗖𝗧 𝗢𝗣𝗧𝗜𝗢𝗡"
                )
                keyboard = [
                    [InlineKeyboardButton("👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲", callback_data="profile"),
                     InlineKeyboardButton("💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀", callback_data="wallet")],
                    [InlineKeyboardButton("🎁 𝗚𝗲𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", callback_data="buy_account"),
                     InlineKeyboardButton("📦 𝗠𝘆 𝗥𝗲𝘄𝗮𝗿𝗱𝘀", callback_data="purchase_history")],
                    [InlineKeyboardButton("👥 𝗜𝗻𝘃𝗶𝘁𝗲", callback_data="referral_link"),
                     InlineKeyboardButton("📊 𝗗𝗮𝘀𝗵𝗯𝗼𝗮𝗿𝗱", callback_data="back_main")],
                    [InlineKeyboardButton("🆘 𝗦𝘂𝗽𝗽𝗼𝗿𝘁", callback_data="help")]
                ]
                if is_admin:
                    keyboard.append([InlineKeyboardButton("⚙️ 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")])
                if Config.SUPPORT_ID:
                    keyboard.append([InlineKeyboardButton("📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗔𝗱𝗺𝗶𝗻", url=f"tg://user?id={Config.SUPPORT_ID}")])
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
                        f"🚀 𝗪𝗘𝗟𝗖𝗢𝗠𝗘\n\n"
                        f"✅ 𝗩𝗲𝗿𝗶𝗳𝗶𝗰𝗮𝘁𝗶𝗼𝗻 𝘀𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹!\n\n"
                        f"─── • ───\n\n"
                        f"👤 𝗨𝘀𝗲𝗿 𝗜𝗗: `{user_id}`\n"
                        f"💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀: `{diamonds}`\n"
                        f"👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{referrals}`\n"
                        f"📦 𝗣𝘂𝗿𝗰𝗵𝗮𝘀𝗲𝗱: `{purchased}`\n"
                        f"🏆 𝗥𝗮𝗻𝗸: {self._get_rank(referrals)}\n\n"
                        f"─── • ───\n\n"
                        f"⚡ 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀\n"
                        f"{progress_bar} {progress}/{DIAMOND_COST}\n\n"
                        f"─── • ───\n\n"
                        f"🔥 𝗙𝗲𝗮𝘁𝘂𝗿𝗲𝘀\n"
                        f"• 𝗜𝗻𝘀𝘁𝗮𝗻𝘁 𝗗𝗲𝗹𝗶𝘃𝗲𝗿𝘆\n"
                        f"• 𝗔𝘂𝘁𝗼 𝗢𝗧𝗣 𝗦𝘆𝘀𝘁𝗲𝗺\n"
                        f"• 𝗣𝗿𝗲𝗺𝗶𝘂𝗺 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀\n"
                        f"• 𝗟𝗶𝗳𝗲𝘁𝗶𝗺𝗲 𝗛𝗶𝘀𝘁𝗼𝗿𝘆\n"
                        f"• 𝗦𝗲𝗰𝘂𝗿𝗲 & 𝗦𝗮𝗳𝗲\n\n"
                        f"─── • ───\n\n"
                        f"💠 𝗦𝗘𝗟𝗘𝗖𝗧 𝗢𝗣𝗧𝗜𝗢𝗡"
                    )
                    keyboard = [
                        [InlineKeyboardButton("👤 𝗣𝗿𝗼𝗳𝗶𝗹𝗲", callback_data="profile"),
                         InlineKeyboardButton("💠 𝗖𝗿𝗲𝗱𝗶𝘁𝘀", callback_data="wallet")],
                        [InlineKeyboardButton("🎁 𝗚𝗲𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", callback_data="buy_account"),
                         InlineKeyboardButton("📦 𝗠𝘆 𝗥𝗲𝘄𝗮𝗿𝗱𝘀", callback_data="purchase_history")],
                        [InlineKeyboardButton("👥 𝗜𝗻𝘃𝗶𝘁𝗲", callback_data="referral_link"),
                         InlineKeyboardButton("📊 𝗗𝗮𝘀𝗵𝗯𝗼𝗮𝗿𝗱", callback_data="back_main")],
                        [InlineKeyboardButton("🆘 𝗦𝘂𝗽𝗽𝗼𝗿𝘁", callback_data="help")]
                    ]
                    if is_admin:
                        keyboard.append([InlineKeyboardButton("⚙️ 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")])
                    if Config.SUPPORT_ID:
                        keyboard.append([InlineKeyboardButton("📩 𝗖𝗼𝗻𝘁𝗮𝗰𝘁 𝗔𝗱𝗺𝗶𝗻", url=f"tg://user?id={Config.SUPPORT_ID}")])
                    await callback.message.edit_text(
                        dashboard,
                        reply_markup=InlineKeyboardMarkup(keyboard),
                        parse_mode=ParseMode.MARKDOWN
                    )
                else:
                    await callback.answer("❌ 𝗣𝗹𝗲𝗮𝘀𝗲 𝗷𝗼𝗶𝗻 𝗯𝗼𝘁𝗵 𝗰𝗵𝗮𝗻𝗻𝗲𝗹 𝗮𝗻𝗱 𝗴𝗿𝗼𝘂𝗽 𝗳𝗶𝗿𝘀𝘁.", show_alert=True)
                return

            # ---------- ADMIN PANEL ----------
            elif data == "admin_panel":
                if user_id != Config.ADMIN_ID:
                    await callback.answer("❌ 𝗡𝗼 𝗮𝗰𝗰𝗲𝘀𝘀.", show_alert=True)
                    return
                admin_keyboard = [
                    [InlineKeyboardButton("🔑 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲 𝗦𝗲𝘀𝘀𝗶𝗼𝗻", callback_data="admin_gensession")],
                    [InlineKeyboardButton("📲 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲 𝗢𝗧𝗣", callback_data="admin_otp")],
                    [InlineKeyboardButton("➕ 𝗔𝗱𝗱 𝗔𝗰𝗰𝗼𝘂𝗻𝘁", callback_data="admin_addaccount")],
                    [InlineKeyboardButton("📋 𝗟𝗶𝘀𝘁 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀", callback_data="admin_listaccounts")],
                    [InlineKeyboardButton("📊 𝗨𝘀𝗲𝗿 𝗦𝘁𝗮𝘁𝘀", callback_data="admin_refstats")],
                    [InlineKeyboardButton("📢 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸", callback_data="back_main")]
                ]
                await callback.message.edit_text(
                    f"⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗣𝗔𝗡𝗘𝗟\n\n"
                    f"🛡️ 𝗕𝗼𝘁 𝘀𝘁𝗮𝘁𝘂𝘀: 🟢 𝗢𝗻𝗹𝗶𝗻𝗲\n"
                    f"💾 𝗗𝗮𝘁𝗮𝗯𝗮𝘀𝗲: 🟢 𝗖𝗼𝗻𝗻𝗲𝗰𝘁𝗲𝗱\n"
                    f"👥 𝗧𝗼𝘁𝗮𝗹 𝘂𝘀𝗲𝗿𝘀: **{len(await get_all_users())}**\n\n"
                    f"─── • ───\n\n"
                    f"⚡ 𝗤𝘂𝗶𝗰𝗸 𝗮𝗰𝘁𝗶𝗼𝗻𝘀",
                    reply_markup=InlineKeyboardMarkup(admin_keyboard),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            # ---------- ADMIN INLINE BUTTON HANDLERS ----------
            elif data == "admin_gensession":
                await callback.message.edit_text(
                    f"🔑 𝗚𝗘𝗡𝗘𝗥𝗔𝗧𝗘 𝗦𝗘𝗦𝗦𝗜𝗢𝗡\n\n"
                    f"📌 𝗨𝘀𝗮𝗴𝗲:\n`/gensession +911234567890`\n\n"
                    f"𝗥𝗲𝗽𝗹𝗮𝗰𝗲 𝘄𝗶𝘁𝗵 𝘁𝗵𝗲 𝗮𝗰𝘁𝘂𝗮𝗹 𝗽𝗵𝗼𝗻𝗲 𝗻𝘂𝗺𝗯𝗲𝗿.\n"
                    f"𝗬𝗼𝘂 𝘄𝗶𝗹𝗹 𝗿𝗲𝗰𝗲𝗶𝘃𝗲 𝗢𝗧𝗣 𝗶𝗻𝘀𝘁𝗿𝘂𝗰𝘁𝗶𝗼𝗻𝘀.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_otp":
                await callback.message.edit_text(
                    f"📲 𝗖𝗢𝗠𝗣𝗟𝗘𝗧𝗘 𝗢𝗧𝗣\n\n"
                    f"📌 𝗨𝘀𝗮𝗴𝗲:\n`/otp +911234567890 12345`\n\n"
                    f"𝗥𝗲𝗽𝗹𝗮𝗰𝗲 𝘄𝗶𝘁𝗵 𝗽𝗵𝗼𝗻𝗲 𝗮𝗻𝗱 𝗢𝗧𝗣 𝗰𝗼𝗱𝗲.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_addaccount":
                await callback.message.edit_text(
                    f"➕ 𝗔𝗗𝗗 𝗔𝗖𝗖𝗢𝗨𝗡𝗧\n\n"
                    f"📌 𝗨𝘀𝗮𝗴𝗲:\n`/addaccount +911234567890 MyPass123 456789 session_string \"Description\"`\n\n"
                    f"𝗥𝗲𝗽𝗹𝗮𝗰𝗲 𝗮𝗹𝗹 𝗳𝗶𝗲𝗹𝗱𝘀 𝗮𝗰𝗰𝗼𝗿𝗱𝗶𝗻𝗴𝗹𝘆.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_listaccounts":
                await callback.message.reply("/listaccounts")
                await callback.answer()

            elif data == "admin_refstats":
                await callback.message.edit_text(
                    f"📊 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦\n\n"
                    f"📌 𝗨𝘀𝗮𝗴𝗲:\n`/refstats <user_id>`\n\n"
                    f"𝗘𝘅𝗮𝗺𝗽𝗹𝗲: `/refstats 123456789`",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            elif data == "admin_broadcast":
                await callback.message.edit_text(
                    f"📢 𝗕𝗥𝗢𝗔𝗗𝗖𝗔𝗦𝗧\n\n"
                    f"📌 𝗨𝘀𝗮𝗴𝗲:\n`/broadcast 𝗬𝗼𝘂𝗿 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗵𝗲𝗿𝗲`\n\n"
                    f"𝗢𝗿 𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘄𝗶𝘁𝗵 `/broadcast`.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 𝗕𝗮𝗰𝗸 𝘁𝗼 𝗔𝗱𝗺𝗶𝗻", callback_data="admin_panel")]]),
                    parse_mode=ParseMode.MARKDOWN
                )
                await callback.answer()

            else:
                await callback.answer("𝗨𝗻𝗸𝗻𝗼𝘄𝗻 𝗮𝗰𝘁𝗶𝗼𝗻.")

        # ---------- ADMIN COMMANDS ----------
        @app.on_message(filters.command("admin") & filters.user(Config.ADMIN_ID))
        async def admin_cmd(client, message):
            await message.reply(
                f"⚙️ 𝗔𝗗𝗠𝗜𝗡 𝗖𝗢𝗠𝗠𝗔𝗡𝗗𝗦\n\n"
                f"• `/gensession +91...` – 𝗦𝗲𝗻𝗱 𝗢𝗧𝗣\n"
                f"• `/otp +91... 12345` – 𝗖𝗼𝗺𝗽𝗹𝗲𝘁𝗲 𝗢𝗧𝗣\n"
                f"• `/addaccount ...` – 𝗔𝗱𝗱 𝗮𝗰𝗰𝗼𝘂𝗻𝘁\n"
                f"• `/listaccounts` – 𝗩𝗶𝗲𝘄 𝗮𝗹𝗹\n"
                f"• `/refstats <user_id>` – 𝗨𝘀𝗲𝗿 𝘀𝘁𝗮𝘁𝘀\n"
                f"• `/available` – 𝗖𝗼𝘂𝗻𝘁 𝗮𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲\n"
                f"• `/broadcast <msg>` – 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- BROADCAST COMMAND ----------
        @app.on_message(filters.command("broadcast") & filters.user(Config.ADMIN_ID))
        async def broadcast_cmd(client, message):
            if message.reply_to_message:
                text = message.reply_to_message.text or message.reply_to_message.caption
                if not text:
                    await message.reply("❌ 𝗧𝗵𝗲 𝗿𝗲𝗽𝗹𝗶𝗲𝗱 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝗵𝗮𝘀 𝗻𝗼 𝘁𝗲𝘅𝘁 𝗼𝗿 𝗰𝗮𝗽𝘁𝗶𝗼𝗻.", parse_mode=ParseMode.MARKDOWN)
                    return
            else:
                parts = message.text.split(maxsplit=1)
                if len(parts) < 2:
                    await message.reply(
                        "📌 𝗨𝘀𝗮𝗴𝗲: `/broadcast <𝗺𝗲𝘀𝘀𝗮𝗴𝗲>`\n"
                        "𝗢𝗿 𝗿𝗲𝗽𝗹𝘆 𝘁𝗼 𝗮 𝗺𝗲𝘀𝘀𝗮𝗴𝗲 𝘄𝗶𝘁𝗵 `/broadcast` 𝘁𝗼 𝗳𝗼𝗿𝘄𝗮𝗿𝗱 𝗶𝘁.",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    return
                text = parts[1]

            users = await get_all_users()
            total = len(users)
            if total == 0:
                await message.reply("⚠️ 𝗡𝗼 𝘂𝘀𝗲𝗿𝘀 𝗳𝗼𝘂𝗻𝗱 𝗶𝗻 𝗱𝗮𝘁𝗮𝗯𝗮𝘀𝗲.", parse_mode=ParseMode.MARKDOWN)
                return

            status_msg = await message.reply(
                f"📢 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁𝗶𝗻𝗴 𝘁𝗼 {total} 𝘂𝘀𝗲𝗿𝘀...\n"
                f"📤 𝗦𝗲𝗻𝘁: `0`\n📭 𝗙𝗮𝗶𝗹𝗲𝗱: `0`\n📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: `0/{total}`",
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
                        f"📢 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁𝗶𝗻𝗴...\n"
                        f"📤 𝗦𝗲𝗻𝘁: `{sent}`\n📭 𝗙𝗮𝗶𝗹𝗲𝗱: `{failed}`\n📊 𝗣𝗿𝗼𝗴𝗿𝗲𝘀𝘀: `{i+1}/{total}`",
                        parse_mode=ParseMode.MARKDOWN
                    )

                await asyncio.sleep(0.2)

            await status_msg.edit_text(
                f"✅ 𝗕𝗿𝗼𝗮𝗱𝗰𝗮𝘀𝘁 𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲!\n\n"
                f"📤 𝗦𝗲𝗻𝘁: `{sent}`\n"
                f"📭 𝗙𝗮𝗶𝗹𝗲𝗱: `{failed}`\n"
                f"👥 𝗧𝗼𝘁𝗮𝗹 𝘂𝘀𝗲𝗿𝘀: `{total}`",
                parse_mode=ParseMode.MARKDOWN
            )

        # ---------- SESSION GENERATION ----------
        @app.on_message(filters.command("gensession") & filters.user(Config.ADMIN_ID))
        async def gen_session_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 𝗨𝘀𝗮𝗴𝗲: `/gensession +911234567890`", parse_mode=ParseMode.MARKDOWN)
                return
            phone = parts[1]
            if message.from_user.id in self.pending_sessions:
                await message.reply("⏳ 𝗔𝗹𝗿𝗲𝗮𝗱𝘆 𝗴𝗲𝗻𝗲𝗿𝗮𝘁𝗶𝗻𝗴. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗰𝗼𝗺𝗽𝗹𝗲𝘁𝗲 𝗳𝗶𝗿𝘀𝘁.", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = Client(f"temp_{message.from_user.id}", api_id=Config.API_ID, api_hash=Config.API_HASH, in_memory=True)
            await message.reply(f"📲 𝗦𝗲𝗻𝗱𝗶𝗻𝗴 𝗢𝗧𝗣 𝘁𝗼 `{phone}`...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.connect()
                sent_code = await temp_client.send_code(phone)
                self.pending_sessions[message.from_user.id] = {"client": temp_client, "phone": phone, "phone_code_hash": sent_code.phone_code_hash}
                await message.reply(f"✅ 𝗢𝗧𝗣 𝘀𝗲𝗻𝘁!\n𝗡𝗼𝘄 𝘂𝘀𝗲 `/otp {phone} <𝗰𝗼𝗱𝗲>`", parse_mode=ParseMode.MARKDOWN)
            except Exception as e:
                await message.reply(f"❌ 𝗙𝗮𝗶𝗹𝗲𝗱: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("otp") & filters.user(Config.ADMIN_ID))
        async def complete_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("📌 𝗨𝘀𝗮𝗴𝗲: `/otp +911234567890 12345`", parse_mode=ParseMode.MARKDOWN)
                return
            phone, otp_code = parts[1], parts[2]
            session_data = self.pending_sessions.get(message.from_user.id)
            if not session_data:
                await message.reply("❌ 𝗡𝗼 𝗽𝗲𝗻𝗱𝗶𝗻𝗴 𝘀𝗲𝘀𝘀𝗶𝗼𝗻.", parse_mode=ParseMode.MARKDOWN)
                return
            if session_data["phone"] != phone:
                await message.reply(f"❌ 𝗣𝗵𝗼𝗻𝗲 𝗺𝗶𝘀𝗺𝗮𝘁𝗰𝗵. 𝗘𝘅𝗽𝗲𝗰𝘁𝗲𝗱 `{session_data['phone']}`", parse_mode=ParseMode.MARKDOWN)
                return
            temp_client = session_data["client"]
            await message.reply("⏳ 𝗦𝗶𝗴𝗻𝗶𝗻𝗴 𝗶𝗻...", parse_mode=ParseMode.MARKDOWN)
            try:
                await temp_client.sign_in(phone, otp_code, session_data["phone_code_hash"])
                session_string = await temp_client.export_session_string()
                await temp_client.disconnect()
                del self.pending_sessions[message.from_user.id]
                await message.reply(
                    f"✅ 𝗦𝗲𝘀𝘀𝗶𝗼𝗻 𝗚𝗲𝗻𝗲𝗿𝗮𝘁𝗲𝗱!\n\n📱 𝗣𝗵𝗼𝗻𝗲: `{phone}`\n🔑 𝗦𝗲𝘀𝘀𝗶𝗼𝗻:\n`{session_string}`",
                    parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await message.reply(f"❌ 𝗙𝗮𝗶𝗹𝗲𝗱: `{e}`", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("addaccount") & filters.user(Config.ADMIN_ID))
        async def add_account_cmd(client, message):
            parts = message.text.split(maxsplit=5)
            if len(parts) < 6:
                await message.reply(
                    "📌 𝗨𝘀𝗮𝗴𝗲: `/addaccount <𝗽𝗵𝗼𝗻𝗲> <𝗽𝗮𝘀𝘀𝘄𝗼𝗿𝗱> <𝗼𝘁𝗽> <𝘀𝗲𝘀𝘀𝗶𝗼𝗻_𝘀𝘁𝗿𝗶𝗻𝗴> <𝗱𝗲𝘀𝗰𝗿𝗶𝗽𝘁𝗶𝗼𝗻>`\n\n"
                    "𝗘𝘅𝗮𝗺𝗽𝗹𝗲:\n"
                    "`/addaccount +911234567890 MyPass123 456789 session_here \"Premium\"`",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
            phone, password, otp, session_str, desc = parts[1], parts[2], parts[3], parts[4], parts[5]
            acc_id = await add_account(phone, password, otp, session_str, 0, desc)
            await message.reply(f"✅ 𝗔𝗰𝗰𝗼𝘂𝗻𝘁 #{acc_id} 𝗮𝗱𝗱𝗲𝗱!", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("updateotp") & filters.user(Config.ADMIN_ID))
        async def update_otp_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 3:
                await message.reply("📌 𝗨𝘀𝗮𝗴𝗲: `/updateotp <𝗮𝗰𝗰𝗼𝘂𝗻𝘁_𝗶𝗱> <𝗻𝗲𝘄_𝗼𝘁𝗽>`", parse_mode=ParseMode.MARKDOWN)
                return
            acc_id, new_otp = int(parts[1]), parts[2]
            await update_account_otp(acc_id, new_otp)
            await message.reply(f"✅ 𝗢𝗧𝗣 𝗳𝗼𝗿 𝗮𝗰𝗰𝗼𝘂𝗻𝘁 #{acc_id} 𝘂𝗽𝗱𝗮𝘁𝗲𝗱.", parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("listaccounts") & filters.user(Config.ADMIN_ID))
        async def list_accounts_cmd(client, message):
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute("SELECT * FROM accounts ORDER BY id")
                rows = await cursor.fetchall()
                if not rows:
                    await message.reply("📭 𝗡𝗼 𝗮𝗰𝗰𝗼𝘂𝗻𝘁𝘀 𝗶𝗻 𝗱𝗮𝘁𝗮𝗯𝗮𝘀𝗲.", parse_mode=ParseMode.MARKDOWN)
                    return
                text = "📋 𝗔𝗟𝗟 𝗔𝗖𝗖𝗢𝗨𝗡𝗧𝗦\n\n"
                for r in rows:
                    status = "✅ 𝗦𝗼𝗹𝗱" if r['is_sold'] else "⬜ 𝗔𝘃𝗮𝗶𝗹𝗮𝗯𝗹𝗲"
                    text += f"#{r['id']} | {r['phone']} | {status}\n"
                await message.reply(text, parse_mode=ParseMode.MARKDOWN)

        @app.on_message(filters.command("refstats") & filters.user(Config.ADMIN_ID))
        async def ref_stats_cmd(client, message):
            parts = message.text.split()
            if len(parts) != 2:
                await message.reply("📌 𝗨𝘀𝗮𝗴𝗲: `/refstats <𝘂𝘀𝗲𝗿_𝗶𝗱>`", parse_mode=ParseMode.MARKDOWN)
                return
            uid = int(parts[1])
            diamonds = await get_diamonds(uid)
            count = await get_referral_count(uid)
            accounts = await get_earned_accounts(uid)
            await message.reply(
                f"📊 𝗨𝗦𝗘𝗥 𝗦𝗧𝗔𝗧𝗦\n\n"
                f"👤 𝗨𝘀𝗲𝗿 𝗜𝗗: `{uid}`\n"
                f"💰 𝗪𝗮𝗹𝗹𝗲𝘁: `{diamonds}` 💎\n"
                f"👥 𝗥𝗲𝗳𝗲𝗿𝗿𝗮𝗹𝘀: `{count}`\n"
                f"📱 𝗔𝗰𝗰𝗼𝘂𝗻𝘁𝘀: `{len(accounts)}`",
                parse_mode=ParseMode.MARKDOWN
            )

    # ---------- HELPERS ----------
    def _get_rank(self, referrals):
        if referrals >= 50:
            return "👑 𝗗𝗶𝗮𝗺𝗼𝗻𝗱 𝗞𝗶𝗻𝗴"
        elif referrals >= 25:
            return "⭐ 𝗘𝗹𝗶𝘁𝗲 𝗥𝗲𝗳𝗲𝗿𝗿𝗲𝗿"
        elif referrals >= 10:
            return "💎 𝗚𝗼𝗹𝗱 𝗥𝗲𝗳𝗲𝗿𝗿𝗲𝗿"
        elif referrals >= 5:
            return "🥈 𝗦𝗶𝗹𝘃𝗲𝗿 𝗥𝗲𝗳𝗲𝗿𝗿𝗲𝗿"
        else:
            return "🥉 𝗕𝗿𝗼𝗻𝘇𝗲 𝗥𝗲𝗳𝗲𝗿𝗿𝗲𝗿"

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
            f"🔐 𝗩𝗘𝗥𝗜𝗙𝗜𝗖𝗔𝗧𝗜𝗢𝗡 𝗥𝗘𝗤𝗨𝗜𝗥𝗘𝗗\n\n"
            "⚠️ 𝗔𝗰𝗰𝗲𝘀𝘀 𝗿𝗲𝘀𝘁𝗿𝗶𝗰𝘁𝗲𝗱\n\n"
            "𝗧𝗼 𝘂𝘀𝗲 𝘁𝗵𝗶𝘀 𝗽𝗿𝗲𝗺𝗶𝘂𝗺 𝗯𝗼𝘁, 𝘆𝗼𝘂 𝗺𝘂𝘀𝘁 𝗷𝗼𝗶𝗻 𝗼𝘂𝗿\n"
            "𝗖𝗵𝗮𝗻𝗻𝗲𝗹 𝗮𝗻𝗱 𝗚𝗿𝗼𝘂𝗽.\n\n"
            "─── • ───\n\n"
            "𝗔𝗳𝘁𝗲𝗿 𝗷𝗼𝗶𝗻𝗶𝗻𝗴, 𝗰𝗹𝗶𝗰𝗸 𝘁𝗵𝗲 𝗯𝘂𝘁𝘁𝗼𝗻 𝗯𝗲𝗹𝗼𝘄 𝘁𝗼 𝗰𝗼𝗻𝘁𝗶𝗻𝘂𝗲."
        )
        buttons = []
        if Config.FORCE_CHANNEL:
            buttons.append([InlineKeyboardButton("📢 𝗝𝗼𝗶𝗻 𝗖𝗵𝗮𝗻𝗻𝗲𝗹", url=f"https://t.me/{Config.FORCE_CHANNEL}")])
        if Config.FORCE_GROUP:
            buttons.append([InlineKeyboardButton("👥 𝗝𝗼𝗶𝗻 𝗚𝗿𝗼𝘂𝗽", url=f"https://t.me/{Config.FORCE_GROUP}")])
        buttons.append([InlineKeyboardButton("✅ 𝗜'𝘃𝗲 𝗷𝗼𝗶𝗻𝗲𝗱", callback_data="force_check")])
        await message.reply(text, reply_markup=InlineKeyboardMarkup(buttons), parse_mode=ParseMode.MARKDOWN)


# ---------- PERMANENT OTP FORWARDER ----------
async def forward_telegram_otp_telethon(account_id: int, buyer_id: int, session_string: str):
    if not session_string or len(session_string) < 10:
        await _bot_instance.send_message(
            buyer_id,
            f"❌ 𝗢𝗧𝗣 𝗘𝗥𝗥𝗢𝗥\n\n"
            "𝗜𝗻𝘃𝗮𝗹𝗶𝗱 𝘀𝗲𝘀𝘀𝗶𝗼𝗻 𝘀𝘁𝗿𝗶𝗻𝗴. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗰𝗼𝗻𝘁𝗮𝗰𝘁 𝗮𝗱𝗺𝗶𝗻.",
            parse_mode=ParseMode.MARKDOWN
        )
        return

    logger.info(f"Telethon OTP listener starting for account {account_id} -> buyer {buyer_id} (permanent)")

    await _bot_instance.send_message(
        buyer_id,
        f"🔁 𝗢𝗧𝗣 𝗟𝗜𝗦𝗧𝗘𝗡𝗘𝗥 𝗔𝗖𝗧𝗜𝗩𝗘\n\n"
        "🟢 𝗡𝗼 𝘁𝗶𝗺𝗲𝗼𝘂𝘁 — 𝘄𝗲'𝗹𝗹 𝗰𝗮𝗽𝘁𝘂𝗿𝗲 𝘆𝗼𝘂𝗿 𝗰𝗼𝗱𝗲.\n\n"
        "📱 𝗢𝗽𝗲𝗻 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺, 𝗲𝗻𝘁𝗲𝗿 𝘁𝗵𝗲 𝗽𝗵𝗼𝗻𝗲 𝗻𝘂𝗺𝗯𝗲𝗿,\n"
        "𝗮𝗻𝗱 𝗽𝗿𝗲𝘀𝘀 '𝗡𝗲𝘅𝘁'.\n\n"
        "─── • ───\n\n"
        "🔑 𝗧𝗵𝗲 𝗢𝗧𝗣 𝘄𝗶𝗹𝗹 𝗮𝗽𝗽𝗲𝗮𝗿 𝗵𝗲𝗿𝗲 𝗮𝘂𝘁𝗼𝗺𝗮𝘁𝗶𝗰𝗮𝗹𝗹𝘆.",
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
                f"❌ 𝗦𝗘𝗦𝗦𝗜𝗢𝗡 𝗘𝗫𝗣𝗜𝗥𝗘𝗗\n\n"
                "𝗧𝗵𝗲 𝘀𝗲𝘀𝘀𝗶𝗼𝗻 𝗶𝘀 𝗶𝗻𝘃𝗮𝗹𝗶𝗱. 𝗣𝗹𝗲𝗮𝘀𝗲 𝗰𝗼𝗻𝘁𝗮𝗰𝘁 𝗮𝗱𝗺𝗶𝗻.",
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
                    f"🔑 𝗢𝗧𝗣 𝗥𝗘𝗖𝗘𝗜𝗩𝗘𝗗\n\n"
                    f"`{event.message.text}`\n\n"
                    f"𝗣𝗹𝗲𝗮𝘀𝗲 𝗲𝗻𝘁𝗲𝗿 𝘁𝗵𝗶𝘀 𝗰𝗼𝗱𝗲 𝗶𝗻 𝘁𝗵𝗲 𝗧𝗲𝗹𝗲𝗴𝗿𝗮𝗺 𝗮𝗽𝗽.",
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
            f"❌ 𝗢𝗧𝗣 𝗖𝗥𝗔𝗦𝗛\n\n"
            f"𝗘𝗿𝗿𝗼𝗿: `{str(e)[:100]}`\n"
            "𝗣𝗹𝗲𝗮𝘀𝗲 𝗰𝗹𝗶𝗰𝗸 '𝗚𝗲𝘁 𝗢𝗧𝗣' 𝘁𝗼 𝗿𝗲𝘀𝘁𝗮𝗿𝘁.",
            parse_mode=ParseMode.MARKDOWN
        )
    finally:
        try:
            await client.disconnect()
        except:
            pass
