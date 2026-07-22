import os
from dotenv import load_dotenv
load_dotenv()

class Config:
    # ---------- REQUIRED (MUST BE SET) ----------
    API_ID = os.getenv("API_ID")
    if API_ID is None:
        raise ValueError("❌ API_ID not set in environment variables")
    API_ID = int(API_ID)

    API_HASH = os.getenv("API_HASH")
    if API_HASH is None:
        raise ValueError("❌ API_HASH not set")
    
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if BOT_TOKEN is None:
        raise ValueError("❌ BOT_TOKEN not set")
    
    ADMIN_ID = os.getenv("ADMIN_ID")
    if ADMIN_ID is None:
        raise ValueError("❌ ADMIN_ID not set")
    ADMIN_ID = int(ADMIN_ID)

    # ---------- OPTIONAL (Default values) ----------
    FORCE_CHANNEL = os.getenv("FORCE_CHANNEL", "")   # leave empty to disable
    FORCE_GROUP = os.getenv("FORCE_GROUP", "")       # leave empty to disable
    DB_PATH = os.getenv("DB_PATH", "accounts.db")
