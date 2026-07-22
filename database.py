import aiosqlite
from datetime import datetime
from config import Config

DB_PATH = Config.DB_PATH

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Accounts
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
        # Users
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                referral_code TEXT UNIQUE NOT NULL,
                diamonds INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Referrals
        await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                referrer_id INTEGER NOT NULL,
                referred_id INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (referrer_id) REFERENCES users(user_id),
                FOREIGN KEY (referred_id) REFERENCES users(user_id),
                UNIQUE(referred_id)
            )
        """)
        # Orders
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
        # Add columns if missing (for backward compatibility)
        try:
            await db.execute("ALTER TABLE accounts ADD COLUMN session_string TEXT;")
        except:
            pass
        try:
            await db.execute("ALTER TABLE users ADD COLUMN diamonds INTEGER DEFAULT 0;")
        except:
            pass
        await db.commit()

# ---------- USER FUNCTIONS ----------
async def get_or_create_user(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if row:
            return dict(row)
        import random, string
        code = f"{user_id}{''.join(random.choices(string.ascii_lowercase + string.digits, k=6))}"
        existing = await db.execute("SELECT 1 FROM users WHERE referral_code = ?", (code,))
        if await existing.fetchone():
            code = f"{user_id}{''.join(random.choices(string.ascii_lowercase + string.digits, k=8))}"
        await db.execute(
            "INSERT INTO users (user_id, referral_code, diamonds) VALUES (?, ?, 0)",
            (user_id, code)
        )
        await db.commit()
        return {"user_id": user_id, "referral_code": code, "diamonds": 0, "created_at": None}

async def get_user_by_referral_code(code: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM users WHERE referral_code = ?", (code,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def get_referral_count(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def add_referral(referrer_id: int, referred_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT 1 FROM referrals WHERE referred_id = ?", (referred_id,))
        if await cursor.fetchone():
            return False
        await db.execute(
            "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
            (referrer_id, referred_id)
        )
        # Add 1 diamond to referrer
        await db.execute(
            "UPDATE users SET diamonds = diamonds + 1 WHERE user_id = ?",
            (referrer_id,)
        )
        await db.commit()
        return True

async def get_diamonds(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

async def deduct_diamonds(user_id: int, amount: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT diamonds FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        if not row or row[0] < amount:
            return False
        await db.execute(
            "UPDATE users SET diamonds = diamonds - ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()
        return True

async def get_earned_accounts(user_id: int) -> list:
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
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM accounts WHERE is_sold = 0 ORDER BY id LIMIT 1"
        )
        row = await cursor.fetchone()
        if not row:
            return None
        account = dict(row)
        await db.execute(
            "UPDATE accounts SET is_sold = 1, sold_to = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id, account['id'])
        )
        cursor = await db.execute(
            "INSERT INTO orders (user_id, account_id, status) VALUES (?, ?, 'claimed')",
            (user_id, account['id'])
        )
        await db.commit()
        order_id = cursor.lastrowid
        account['order_id'] = order_id
        return account

# ---------- ACCOUNT FUNCTIONS ----------
async def get_available_accounts() -> list:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE is_sold = 0 ORDER BY id")
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

async def get_account_by_id(account_id: int) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None

async def add_account(phone, password, otp, session_string, price, description):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "INSERT INTO accounts (phone, password, otp, session_string, price, description) VALUES (?, ?, ?, ?, ?, ?)",
            (phone, password, otp, session_string, price, description)
        )
        await db.commit()
        return cursor.lastrowid

async def update_account_otp(account_id: int, new_otp: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE accounts SET otp = ? WHERE id = ?", (new_otp, account_id))
        await db.commit()

async def mark_account_sold(account_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE accounts SET is_sold = 1, sold_to = ?, sold_at = CURRENT_TIMESTAMP WHERE id = ?",
            (user_id, account_id)
        )
        await db.commit()

# ---------- BROADCAST FUNCTION ----------
async def get_all_users() -> list:
    """Fetch all user IDs from the database for broadcasting."""
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("SELECT user_id FROM users")
        rows = await cursor.fetchall()
        return [row[0] for row in rows]
