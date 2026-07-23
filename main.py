import asyncio, logging
from pyrogram import Client
from pyrogram.types import BotCommand
from config import Config
from database import init_db
from handlers import BotHandlers

logging.basicConfig(level=logging.INFO)

async def set_commands(app):
    commands = [
        BotCommand("start", "🚀 Start the bot"),
        BotCommand("ping", "🏓 Check bot status"),
        BotCommand("available", "📦 Check available accounts"),
        BotCommand("broadcast", "📢 Send broadcast (Admin)"),
        BotCommand("admin", "🔧 Admin commands list"),
        BotCommand("gensession", "🔑 Generate session (Admin)"),
        BotCommand("otp", "📲 Complete OTP (Admin)"),
        BotCommand("addaccount", "➕ Add account (Admin)"),
        BotCommand("listaccounts", "📋 List accounts (Admin)"),
        BotCommand("refstats", "📊 User stats (Admin)"),
    ]
    await app.set_bot_commands(commands)

async def main():
    print("🚀 Initializing database...")
    await init_db()
    print("🚀 Starting bot...")
    app = Client("account_bot", api_id=Config.API_ID, api_hash=Config.API_HASH, bot_token=Config.BOT_TOKEN)
    BotHandlers(app)
    await app.start()
    await set_commands(app)
    print("🤖 Bot is running! (Press Ctrl+C to stop)")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
