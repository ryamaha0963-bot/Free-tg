import aiosqlite
from datetime import datetime

DB_PATH = "accounts.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Accounts (unchanged)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phone TEXT NOT NULL,
                password TEXT,
                otp TEXT,
                session_string TEXT,
                price INTEGER DEFAULT 0,
                description TEXT,
                is_sold BOOLEAN DEFAULT 0,
                sold_to INTEGER,
                sold_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Users (telegram users)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                referral_code TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Referrals tracker
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id),
                UNIQUE(referred_id)  -- each user can be referred only once
            )
        """)

        # Orders (for claimed accounts, similar to before)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                account_id INTEGER NOT NULL,
                status TEXT DEFAULT 'claimed',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                confirmed_at TIMESTAMP
            )
        """)

        # Add session_string column if missing (safety)
        try:
            await db.execute("ALTER TABLE accounts ADD COLUMN session_string TEXT;")
        except:
            pass

        await db.commit()


# ---------- USER FUNCTIONS ----------
async def get_or_create_user(user_id: int) -> dict:
    """Get user, create if not exists with a unique referral code."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)

        # Generate a unique referral code (simple: user_id + random suffix)
        import random, string
        code = f"{user_id}{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
        # ensure unique (loop if needed, but rare)
        existing = await db.execute("SELECT 1 FROM users WHERE referral_code = ?", (code,))
        if await existing.fetchone():
            code = f"{user_id}{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"

        await db.execute(
            "INSERT INTO users (user_id, referral_code) VALUES (?, ?)",
            (user_id, code)
        )
        await db.commit()
        return {"user_id": user_id, "referral_code": code, "created_at": None}


async def get_user_by_referral_code(code: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def get_referral_count(user_id: int) -> int:
    """Count how many distinct users this user has referred."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0


async def add_referral(referrer_id: int, referred_id: int) -> bool:
    """Record a referral if not already referred."""
    # Check if referred_id already has a referrer
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,))
        if await cursor.fetchone():
            return False  # already referred
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, referred_id)
        )
        await db.commit()
        return True


async def get_earned_accounts(user_id: int) -> list:
    """Get all accounts claimed by this user via referral."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("""
            SELECT a.*, o.id as order_id, o.created_at as claimed_at
            FROM orders o
            JOIN accounts a ON o.account_id = a.id
            WHERE o.user_id = ? AND o.status = 'claimed'
            ORDER BY o.created_at DESC
        """, (user_id,))
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def claim_account_for_user(user_id: int) -> dict | None:
    """Assign the next available unsold account to the user."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Find one unsold account
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE is_sold = 0 ORDER BY id LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        account = dict(row)

        # Mark sold
        await db.execute(
            "UPDATE accounts SET is_sold = 1, sold_to = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id, account['id'])
        )
        # Create order
        cursor = await db.execute(
            "INSERT INTO orders (user_id, account_id, status) VALUES (?, ?, 'claimed')",
            (user_id, account['id'])
        )
        await db.commit()
        order_id = cursor.lastrowid
        account['order_id'] = order_id
        return account

# ---------- Keep existing account functions (get_account_by_id, etc.) ----------
# (Copy from previous database.py, but we already have them; we'll include them)
