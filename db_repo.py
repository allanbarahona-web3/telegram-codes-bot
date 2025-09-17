# db_repo.py — capa de datos conmutada por env (sqlite/postgres)
import os
from typing import Optional

DB_BACKEND = (os.getenv("DB_BACKEND") or "sqlite").strip().lower()

# =========================
# Backend: SQLite (aiosqlite)
# =========================
if DB_BACKEND == "sqlite":
    async def get_default_method(user_id: int):
        db = await _sqlite_conn()
        try:
            async with db.execute("SELECT * FROM payout_methods WHERE user_id=? AND is_default=1 LIMIT 1", (user_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None
        finally:
            await db.close()

    async def create_withdraw_request(user_id: int, amount_cents: int, method_id: int):
        db = await _sqlite_conn()
        try:
            await db.execute(
                "INSERT INTO payments (user_id, amount_cents, status, method_id, requested_at) VALUES (?, ?, 'REQUESTED', ?, datetime('now'))",
                (user_id, amount_cents, method_id)
            )
            await db.commit()
            async with db.execute("SELECT MAX(id) FROM payments WHERE user_id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0])
        finally:
            await db.close()
    async def get_code_by_phone(phone_e164: str):
        db = await _sqlite_conn()
        try:
            async with db.execute("SELECT id, code FROM users WHERE phone=?", (phone_e164,)) as cur:
                row = await cur.fetchone()
                return (row["id"], row["code"]) if row else None
        finally:
            await db.close()
    async def get_user_points(user_id: int) -> int:
        db = await _sqlite_conn()
        try:
            async with db.execute("SELECT COALESCE(total_points, 0) FROM users WHERE id=?", (user_id,)) as cur:
                row = await cur.fetchone()
                return int(row[0]) if row else 0
        finally:
            await db.close()

    async def compute_balances(user_id: int):
        db = await _sqlite_conn()
        try:
            # Approved referrals
            async with db.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=? AND status='APPROVED'", (user_id,)) as cur:
                approved = (await cur.fetchone())[0]
            # Gross earned
            gross = approved * 100  # You may want to use COMMISSION_PER_APPROVED_CENTS from env
            # Paid out
            async with db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=? AND status='PAID'", (user_id,)) as cur:
                paid = (await cur.fetchone())[0]
            # Pending withdrawals
            async with db.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=? AND status IN ('REQUESTED','APPROVED')", (user_id,)) as cur:
                pending = (await cur.fetchone())[0]
            return approved, gross, paid, pending
        finally:
            await db.close()
    import aiosqlite

    DB_PATH = os.getenv("DB_PATH") or "./data/codes.db"

    async def _sqlite_conn():
        os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
        conn = await aiosqlite.connect(DB_PATH)
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = aiosqlite.Row
        return conn

    async def init_db():
        db = await _sqlite_conn()
        try:
            await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                phone TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            );
            """)
            await db.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                campaign_id TEXT NOT NULL,
                referrer_id INTEGER NOT NULL,
                referee_id INTEGER NOT NULL,
                ref_code TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (campaign_id, referee_id),
                CHECK (referrer_id <> referee_id)
            );
            """)
            await db.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals (campaign_id, referrer_id);")
            await db.execute("CREATE INDEX IF NOT EXISTS idx_users_code ON users (code);")
            await db.commit()
        finally:
            await db.close()

    async def upsert_user(user_id: int, code: str, phone: Optional[str]):
        db = await _sqlite_conn()
        try:
            await db.execute("""
            INSERT INTO users (id, code, phone) VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET code=excluded.code, phone=excluded.phone;
            """, (user_id, code, phone))
            await db.commit()
        finally:
            await db.close()

    async def get_existing_code_by_user(user_id: int) -> Optional[str]:
        db = await _sqlite_conn()
        try:
            async with db.execute("SELECT code FROM users WHERE id = ?;", (user_id,)) as cur:
                row = await cur.fetchone()
                return row["code"] if row else None
        finally:
            await db.close()

    async def find_user_by_code(code: str) -> Optional[int]:
        db = await _sqlite_conn()
        try:
            async with db.execute("SELECT id FROM users WHERE code = ?;", (code,)) as cur:
                row = await cur.fetchone()
                return int(row["id"]) if row else None
        finally:
            await db.close()

    async def referee_already_referred(campaign_id: str, referee_id: int) -> bool:
        db = await _sqlite_conn()
        try:
            async with db.execute("""
            SELECT 1 FROM referrals WHERE campaign_id = ? AND referee_id = ?;
            """, (campaign_id, referee_id)) as cur:
                return (await cur.fetchone()) is not None
        finally:
            await db.close()

    async def is_reciprocal_referral(campaign_id: str, referee_id: int, referrer_id: int) -> bool:
        db = await _sqlite_conn()
        try:
            async with db.execute("""
            SELECT 1 FROM referrals
            WHERE campaign_id = ? AND referrer_id = ? AND referee_id = ?;
            """, (campaign_id, referee_id, referrer_id)) as cur:
                return (await cur.fetchone()) is not None
        finally:
            await db.close()

    async def insert_referral(campaign_id: str, referrer_id: int, referee_id: int, ref_code: str):
        db = await _sqlite_conn()
        try:
            await db.execute("""
            INSERT INTO referrals (campaign_id, referrer_id, referee_id, ref_code)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(campaign_id, referee_id) DO NOTHING;
            """, (campaign_id, referrer_id, referee_id, ref_code))
            await db.commit()
        finally:
            await db.close()

# ==============================
# Backend: PostgreSQL (psycopg3)
# ==============================
else:
    async def get_default_method(user_id: int):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("SELECT * FROM payout_methods WHERE user_id=%s AND is_default=1 LIMIT 1", (user_id,))
            row = await cur.fetchone()
            if row:
                columns = [desc[0] for desc in cur.description]
                return dict(zip(columns, row))
            return None

    async def create_withdraw_request(user_id: int, amount_cents: int, method_id: int):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO payments (user_id, amount_cents, status, method_id, requested_at) VALUES (%s, %s, 'REQUESTED', %s, now()) RETURNING id",
                (user_id, amount_cents, method_id)
            )
            row = await cur.fetchone()
            await conn.commit()
            return int(row[0])
    async def get_code_by_phone(phone_e164: str):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("SELECT id, code FROM users WHERE phone=%s", (phone_e164,))
            row = await cur.fetchone()
            return (row[0], row[1]) if row else None
    async def get_user_points(user_id: int) -> int:
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("SELECT COALESCE(total_points, 0) FROM users WHERE id=%s", (user_id,))
            row = await cur.fetchone()
            return int(row[0]) if row else 0

    async def compute_balances(user_id: int):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            # Approved referrals
            await cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=%s AND status='APPROVED'", (user_id,))
            approved = (await cur.fetchone())[0]
            # Gross earned
            gross = approved * 100  # You may want to use COMMISSION_PER_APPROVED_CENTS from env
            # Paid out
            await cur.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=%s AND status='PAID'", (user_id,))
            paid = (await cur.fetchone())[0]
            # Pending withdrawals
            await cur.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=%s AND status IN ('REQUESTED','APPROVED')", (user_id,))
            pending = (await cur.fetchone())[0]
            return approved, gross, paid, pending
    import psycopg
    from psycopg.rows import tuple_row

    DATABASE_URL = os.getenv("DATABASE_URL")

    async def _pg_conn():
        if not DATABASE_URL:
            raise RuntimeError("Missing DATABASE_URL for postgres backend")
        return await psycopg.AsyncConnection.connect(DATABASE_URL, row_factory=tuple_row)

    async def init_db():
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                phone TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            );
            """)
            await cur.execute("""
            CREATE TABLE IF NOT EXISTS referrals (
                campaign_id TEXT NOT NULL,
                referrer_id BIGINT NOT NULL,
                referee_id BIGINT NOT NULL,
                ref_code TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now(),
                CONSTRAINT referrals_pk PRIMARY KEY (campaign_id, referee_id),
                CONSTRAINT no_self_referral CHECK (referrer_id <> referee_id)
            );
            """)
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals (campaign_id, referrer_id);")
            await cur.execute("CREATE INDEX IF NOT EXISTS idx_users_code ON users (code);")
            await conn.commit()

    async def upsert_user(user_id: int, code: str, phone: Optional[str]):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("""
            INSERT INTO users (id, code, phone) VALUES (%s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET code = EXCLUDED.code, phone = EXCLUDED.phone;
            """, (user_id, code, phone))
            await conn.commit()

    async def get_existing_code_by_user(user_id: int) -> Optional[str]:
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("SELECT code FROM users WHERE id = %s;", (user_id,))
            row = await cur.fetchone()
            return row[0] if row else None

    async def find_user_by_code(code: str) -> Optional[int]:
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("SELECT id FROM users WHERE code = %s;", (code,))
            row = await cur.fetchone()
            return int(row[0]) if row else None

    async def referee_already_referred(campaign_id: str, referee_id: int) -> bool:
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("""
            SELECT 1 FROM referrals WHERE campaign_id = %s AND referee_id = %s;
            """, (campaign_id, referee_id))
            return (await cur.fetchone()) is not None

    async def is_reciprocal_referral(campaign_id: str, referee_id: int, referrer_id: int) -> bool:
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("""
            SELECT 1 FROM referrals
            WHERE campaign_id = %s AND referrer_id = %s AND referee_id = %s;
            """, (campaign_id, referee_id, referrer_id))
            return (await cur.fetchone()) is not None

    async def insert_referral(campaign_id: str, referrer_id: int, referee_id: int, ref_code: str):
        async with await _pg_conn() as conn, conn.cursor() as cur:
            await cur.execute("""
            INSERT INTO referrals (campaign_id, referrer_id, referee_id, ref_code)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (campaign_id, referee_id) DO NOTHING;
            """, (campaign_id, referrer_id, referee_id, ref_code))
            await conn.commit()
