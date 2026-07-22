import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    API_ID = int(os.getenv("API_ID"))
    API_HASH = os.getenv("API_HASH")
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    ADMIN_ID = int(os.getenv("ADMIN_ID"))
    SUPPORT_ID = int(os.getenv("SUPPORT_ID", 0))  # optional support user ID
    FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")
    FORCE_GROUP = os.getenv("FORCE_GROUP", "")
    DB_PATH = os.getenv("DB_PATH", "accounts.db")
