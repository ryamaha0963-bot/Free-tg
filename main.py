import asyncio, logging
from pyrogram import Client
from pyrogram.types import BotCommand
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

    # 🔥 Sirf "start" command dikhega menu button mein (ya kuch nahi)
    # Agar bilkul nahi chahiye toh [] bhejo
    await app.set_bot_commands([BotCommand("start", "🚀 Start the bot")])

    print("🤖 Bot is running! (Press Ctrl+C to stop)")
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
