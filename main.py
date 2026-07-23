import asyncio, logging
from pyrogram import Client
from pyrogram.types import BotCommand, BotCommandScopeChat  # 🔥 BotCommandScopeChat import karna zaroori hai
from config import Config
from database import init_db
from handlers import BotHandlers

logging.basicConfig(level=logging.INFO)

async def main():
    print("🚀 Initializing database...")
    await init_db()
    print("🚀 Starting bot...")
    
    app = Client("account_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
    BotHandlers(app)
    await app.start()

    # ---------- 🎯 COMMAND MENU FIX (YAHI SE HOGAAAAAAAA) ----------
    
    # 1. YE COMMANDS SABHI USERS KO DIKHENGI (Default Global Menu)
    user_commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("ping", "🏓 Check bot status"),
        BotCommand("available", "📦 Check available accounts"),
    ]

    # 2. YE COMMANDS SIRF ADMIN KO DIKHENGI (User commands + Admin commands)
    admin_commands = user_commands + [
        BotCommand("broadcast", "📢 Send broadcast (Admin)"),
        BotCommand("admin", "🔧 Admin commands list"),
        BotCommand("gensession", "🔑 Generate session (Admin)"),
        BotCommand("otp", "📲 Complete OTP (Admin)"),
        BotCommand("addaccount", "➕ Add account (Admin)"),
        BotCommand("listaccounts", "📋 List accounts (Admin)"),
        BotCommand("refstats", "📊 User stats (Admin)"),
    ]

    # 🔥 Global menu set kar (Sirf user commands, taaki normal users ko admin commands na dikhe)
    await app.set_bot_commands(user_commands)

    # 🔥 Admin ke liye alag se scope set kar (Isse admin ke menu mein saari commands aa jayengi)
    await app.set_bot_commands(
        commands=admin_commands,
        scope=BotCommandScopeChat(chat_id=Config.ADMIN_ID)  # Tere config mein ADMIN_ID already hai
    )

    # ---------- 🎯 FIX KHATAM ----------

    print("🤖 Bot is running! (Press Ctrl+C to stop)")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
