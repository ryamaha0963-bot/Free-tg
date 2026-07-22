import asyncio
import logging
from pyrogram import Client
from config import Config
from database import init_db
from handlers import BotHandlers

logging.basicConfig(level=logging.INFO)

async def main():
    await init_db()
    app_bot = Client(
        "account_bot",
        api_id=Config.API_ID,
        api_hash=Config.API_HASH,
        bot_token=Config.BOT_TOKEN
    )
    BotHandlers(app_bot)
    print("🤖 Bot is running... Referral system active.")
    await app_bot.start()
    await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
