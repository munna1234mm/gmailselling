
import aiosqlite
import asyncio
import os

DB_NAME = "bot_data.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance REAL DEFAULT 0.0,
                hold_balance REAL DEFAULT 0.0,
                payment_info TEXT DEFAULT '{}',
                referred_by INTEGER,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE,
                password TEXT,
                status TEXT DEFAULT 'available', -- available, pending, sold
                assigned_to INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        # Set default price if not exists
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('price_per_account', '0.20')")


        # Check if accounts table has name columns
        try:
            await db.execute("ALTER TABLE accounts ADD COLUMN first_name TEXT")
            await db.execute("ALTER TABLE accounts ADD COLUMN last_name TEXT")
        except Exception:
            pass # Ignore if exists

        # Check if users table has referred_by column (migration hack)
        try:
            await db.execute("ALTER TABLE users ADD COLUMN referred_by INTEGER")
        except Exception:
             pass 
            
        try:
            await db.execute("ALTER TABLE users ADD COLUMN hold_balance REAL DEFAULT 0.0")
        except Exception as e:
            import logging
            logging.error(f"Migration error (hold_balance): {e}")
            
        try:
            await db.execute("ALTER TABLE users ADD COLUMN payment_info TEXT DEFAULT '{}'")
        except Exception as e:
            import logging
            logging.error(f"Migration error (payment_info): {e}")
            
        # Check if withdrawals table exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount REAL,
                method TEXT,
                details TEXT,
                status TEXT DEFAULT 'pending', -- pending, paid, rejected
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Default referral bonus
        await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('referral_bonus', '0.05')")
        
         # Check if admins table exists
        await db.execute("""
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY
            )
        """)
            
        await db.commit()

async def get_db_connection():
    return await aiosqlite.connect(DB_NAME)

# Admin Management
async def add_admin(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (user_id,))
        await db.commit()

async def get_admins():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM admins") as cursor:
            return [row[0] for row in await cursor.fetchall()]

async def get_all_users():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor:
            return [row[0] for row in await cursor.fetchall()]

# User Operations
async def add_user(user_id, username, referrer_id=None):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            # Check if user exists
            async with db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)) as cursor:
                if await cursor.fetchone():
                    return False # Already exists
            
            await db.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by, hold_balance, payment_info) VALUES (?, ?, ?, 0.0, '{}')", (user_id, username, referrer_id))
            await db.commit()
            return True # New user
    except Exception as e:
        import logging
        logging.error(f"Error in add_user: {e}", exc_info=True)
        return False

async def get_user_balance(user_id):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT balance, hold_balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
                row = await cursor.fetchone()
                return (row[0], row[1]) if row else (0.0, 0.0)
    except Exception as e:
        import logging
        logging.error(f"Error in get_user_balance: {e}", exc_info=True)
        return (0.0, 0.0)

async def add_balance(user_id, amount):
    # This adds to MAIN balance
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        
async def add_hold_balance(user_id, amount):
    # This adds to HOLD balance
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE users SET hold_balance = hold_balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def update_payment_info(user_id, info_dict):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        # Merge with existing
        async with db.execute("SELECT payment_info FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            current = json.loads(row[0]) if row and row[0] else {}
            
        current.update(info_dict)
        await db.execute("UPDATE users SET payment_info = ? WHERE user_id = ?", (json.dumps(current), user_id))
        await db.commit()

async def get_payment_info(user_id):
    import json
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT payment_info FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row and row[0] else {}

# History & Referrals
async def get_user_history_list(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        # Show sold OR submitted
        async with db.execute("SELECT email, password, created_at, status FROM accounts WHERE assigned_to = ? AND status IN ('sold', 'submitted') ORDER BY created_at DESC LIMIT 10", (user_id,)) as cursor:
            return await cursor.fetchall()

async def get_referral_stats(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users WHERE referred_by = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

# Account Operations
async def add_account(email, password, first_name="Any", last_name="Any"):
    try:
        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute("INSERT INTO accounts (email, password, first_name, last_name) VALUES (?, ?, ?, ?)", (email, password, first_name, last_name))
            await db.commit()
        return True
    except aiosqlite.IntegrityError:
        return False

async def get_available_account(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        # Check if user already has a pending account
        async with db.execute("SELECT id, email, password, first_name, last_name FROM accounts WHERE assigned_to = ? AND status = 'pending'", (user_id,)) as cursor:
            existing = await cursor.fetchone()
            if existing:
                return existing

        # Get a new available account
        async with db.execute("SELECT id, email, password, first_name, last_name FROM accounts WHERE status = 'available' LIMIT 1") as cursor:
            row = await cursor.fetchone()
            if row:
                account_id, email, password, first, last = row
                await db.execute("UPDATE accounts SET status = 'pending', assigned_to = ? WHERE id = ?", (user_id, account_id))
                await db.commit()
                return (account_id, email, password, first, last)
            return None

async def cancel_registration(user_id):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE accounts SET status = 'available', assigned_to = NULL WHERE assigned_to = ? AND status = 'pending'", (user_id,))
        await db.commit()

async def mark_account_submitted(user_id):
    # Changed from 'done' to 'submitted'
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, email, password, first_name, last_name FROM accounts WHERE assigned_to = ? AND status = 'pending'", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return False, "No pending registration found. Please try registering again.", None
            
            account_id, email, password, first, last = row
            
            # Get current price
            async with db.execute("SELECT value FROM settings WHERE key = 'price_per_account'") as cursor:
                price_row = await cursor.fetchone()
                price = float(price_row[0]) if price_row else 0.0

            # Update to submitted
            await db.execute("UPDATE accounts SET status = 'submitted' WHERE id = ?", (account_id,))
            
            cursor2 = await db.execute("UPDATE users SET hold_balance = hold_balance + ? WHERE user_id = ?", (price, user_id))
            if cursor2.rowcount == 0:
                 # User might not exist (add_user failed previously?)
                 import logging
                 logging.warning(f"User {user_id} not found when crediting balance. Attempting self-repair.")
                 # Attempt to add user
                 await db.execute("INSERT OR IGNORE INTO users (user_id, username, referred_by, hold_balance, payment_info) VALUES (?, 'Unknown', NULL, 0.0, '{}')", (user_id,))
                 # Retry update
                 await db.execute("UPDATE users SET hold_balance = hold_balance + ? WHERE user_id = ?", (price, user_id))
                 
            await db.commit()
            return True, price, (account_id, email, password, first, last)

async def get_pending_approvals():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, email, password, assigned_to FROM accounts WHERE status = 'submitted'") as cursor:
            return await cursor.fetchall()

async def approve_account(account_id):
    async with aiosqlite.connect(DB_NAME) as db:
        # Get account info
        async with db.execute("SELECT assigned_to FROM accounts WHERE id = ?", (account_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return False
            user_id = row[0]
            
        # Get price
        async with db.execute("SELECT value FROM settings WHERE key = 'price_per_account'") as cursor:
             price_row = await cursor.fetchone()
             price = float(price_row[0]) if price_row else 0.0

        await db.execute("UPDATE accounts SET status = 'sold' WHERE id = ?", (account_id,))
        await db.execute("UPDATE users SET hold_balance = hold_balance - ?, balance = balance + ? WHERE user_id = ?", (price, price, user_id))
        
        # Credit Referral Bonus
        async with db.execute("SELECT referred_by FROM users WHERE user_id = ?", (user_id,)) as cursor:
            ref_row = await cursor.fetchone()
            if ref_row and ref_row[0]:
                referrer_id = ref_row[0]
                async with db.execute("SELECT value FROM settings WHERE key = 'referral_bonus'") as r_cursor:
                    bonus_row = await r_cursor.fetchone()
                    bonus = float(bonus_row[0]) if bonus_row else 0.0
                
                if bonus > 0:
                    await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (bonus, referrer_id))

        await db.commit()
        return True, user_id

async def reject_account(account_id):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT assigned_to FROM accounts WHERE id = ?", (account_id,)) as cursor:
            row = await cursor.fetchone()
            if not row: return False
            user_id = row[0]
            
        async with db.execute("SELECT value FROM settings WHERE key = 'price_per_account'") as cursor:
             price_row = await cursor.fetchone()
             price = float(price_row[0]) if price_row else 0.0

        # Deduct from Hold (revert the credit)
        # Note: If price changed, this might deduc more/less. 
        # Ideally store price at submission time, but simpler logic here assumes constant price.
        await db.execute("UPDATE users SET hold_balance = hold_balance - ? WHERE user_id = ?", (price, user_id))
        
        await db.execute("UPDATE accounts SET status = 'rejected' WHERE id = ?", (account_id,))
        await db.commit()
        return True, user_id

# Withdrawals
async def create_withdrawal(user_id, amount, method, details):
    async with aiosqlite.connect(DB_NAME) as db:
        # Check balance
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] < amount:
                balance = row[0] if row else 0.0
                return False, f"Insufficient balance. You have ${balance:.2f}, but requested ${amount:.2f}."
        
        # Deduct balance
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        
        # Create record
        await db.execute("INSERT INTO withdrawals (user_id, amount, method, details) VALUES (?, ?, ?, ?)", (user_id, amount, method, details))
        await db.commit()
        return True, "Withdrawal requested."

async def get_pending_withdrawals():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, user_id, amount, method, details, created_at FROM withdrawals WHERE status = 'pending'") as cursor:
            return await cursor.fetchall()

async def mark_withdrawal(withdrawal_id, status):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id, amount FROM withdrawals WHERE id = ?", (withdrawal_id,)) as cursor:
             row = await cursor.fetchone()
             if not row: return False, None
             user_id, amount = row
             
        if status == 'rejected':
            # Refund
            await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
            
        await db.execute("UPDATE withdrawals SET status = ? WHERE id = ?", (status, withdrawal_id))
        await db.commit()
        return True, user_id

# Settings Operations
async def set_price(price):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('price_per_account', ?)", (str(price),))
        await db.commit()

async def get_price():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'price_per_account'") as cursor:
            row = await cursor.fetchone()
            return float(row[0]) if row else 0.0

async def set_referral_bonus(amount):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('referral_bonus', ?)", (str(amount),))
        await db.commit()

async def get_referral_bonus():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'referral_bonus'") as cursor:
             row = await cursor.fetchone()
             return float(row[0]) if row else 0.0

async def set_recovery_email(email):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('recovery_email', ?)", (str(email),))
        await db.commit()

async def get_recovery_email():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'recovery_email'") as cursor:
            row = await cursor.fetchone()
            return str(row[0]) if row else "None"

async def set_names(first, last):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('first_name', ?)", (str(first),))
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('last_name', ?)", (str(last),))
        await db.commit()

async def get_names():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key = 'first_name'") as c1:
            r1 = await c1.fetchone()
        async with db.execute("SELECT value FROM settings WHERE key = 'last_name'") as c2:
            r2 = await c2.fetchone()
            
        first = str(r1[0]) if r1 else "Any"
        last = str(r2[0]) if r2 else "Any"
        return first, last

async def get_stats():
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE status = 'available'") as c1:
            available = (await c1.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM accounts WHERE status = 'sold'") as c2:
            sold = (await c2.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM users") as c3:
            users = (await c3.fetchone())[0]
        return available, sold, users
