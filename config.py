import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    # Telegram API Credentials
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))

    # 🔥 Force Join – Channel & Group (bina @ ke username)
    FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")  # Example: "my_updates"
    FORCE_GROUP = os.getenv("FORCE_GROUP", "")      # Example: "my_discussion"

    # Database Path (optional, default: accounts.db)
    DB_PATH = os.getenv("DB_PATH", "accounts.db")
