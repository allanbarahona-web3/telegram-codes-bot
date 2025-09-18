# Eliminar usuario por id (para tests)
async def delete_user(user_id: int):
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		# Borra puntos primero para evitar violación de FK
		await cur.execute("DELETE FROM points_history WHERE user_id = %s;", (user_id,))
		await cur.execute("DELETE FROM users WHERE id = %s;", (user_id,))
		await conn.commit()
# --- Database Service Layer (migrated from db_repo.py) ---
import os
from typing import Optional
import psycopg_pool
import logging

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
	raise RuntimeError("Missing DATABASE_URL for postgres backend")


# Pool global: None hasta que se inicialice
_pool = None

def get_pool():
	global _pool
	if _pool is None:
		raise RuntimeError("Pool not initialized. Call open_pool() first.")
	return _pool

# Inicializar pool de forma asíncrona
async def open_pool():
	global _pool
	_pool = psycopg_pool.AsyncConnectionPool(DATABASE_URL, min_size=2, max_size=10)
	await _pool.open()
logger = logging.getLogger(__name__)

async def get_active_campaign_for_user(user_id: int):
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("""
			SELECT c.* FROM campaigns c
			JOIN users u ON u.id = %s
			WHERE c.client_id = u.client_id AND c.status = 'ACTIVE'
			ORDER BY c.created_at DESC LIMIT 1;
		""", (user_id,))
		row = await cur.fetchone()
		if row:
			columns = [desc[0] for desc in cur.description]
			return dict(zip(columns, row))
		return None

async def get_default_method(user_id: int, campaign_id: int = None):
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("SELECT * FROM payout_methods WHERE user_id=%s AND is_default=1 LIMIT 1", (user_id,))
		row = await cur.fetchone()
		if row:
			columns = [desc[0] for desc in cur.description]
			return dict(zip(columns, row))
		return None

async def create_withdraw_request(user_id: int, amount_cents: int, method_id: int, campaign_id: int = None):
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			await cur.execute(
				"INSERT INTO payments (user_id, amount_cents, status, method_id, requested_at) VALUES (%s, %s, 'REQUESTED', %s, now()) RETURNING id",
				(user_id, amount_cents, method_id)
			)
			row = await cur.fetchone()
			await conn.commit()
			logger.info(f"Withdraw request created for user {user_id} amount {amount_cents}")
			return int(row[0])
	except Exception as e:
		logger.error(f"Error creating withdraw request for user {user_id}: {e}")
		raise

async def get_code_by_phone(phone_e164: str):
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			await cur.execute("SELECT id, code FROM users WHERE phone=%s", (phone_e164,))
			row = await cur.fetchone()
			return (row[0], row[1]) if row else None
	except Exception as e:
		logger.error(f"Error getting code by phone {phone_e164}: {e}")
		return None

async def get_user_points(user_id: int, campaign_id: int = None) -> int:
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			await cur.execute("SELECT COALESCE(total_points, 0) FROM users WHERE id=%s", (user_id,))
			row = await cur.fetchone()
			return int(row[0]) if row else 0
	except Exception as e:
		logger.error(f"Error getting points for user {user_id}: {e}")
		return 0

async def compute_balances(user_id: int, campaign_id: int, commission_per_approved_cents: int):
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			await cur.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id=%s AND campaign_id=%s AND status='APPROVED'", (user_id, campaign_id))
			approved = (await cur.fetchone())[0]
			gross = approved * commission_per_approved_cents
			await cur.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=%s AND status='PAID'", (user_id,))
			paid = (await cur.fetchone())[0]
			await cur.execute("SELECT COALESCE(SUM(amount_cents),0) FROM payments WHERE user_id=%s AND status IN ('REQUESTED','APPROVED')", (user_id,))
			pending = (await cur.fetchone())[0]
			return approved, gross, paid, pending
	except Exception as e:
		logger.error(f"Error computing balances for user {user_id}: {e}")
		return 0, 0, 0, 0

async def init_db():
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		   # Crear tabla clients (mínima)
		   await cur.execute("""
		   CREATE TABLE IF NOT EXISTS clients (
			   id SERIAL PRIMARY KEY,
			   name TEXT NOT NULL,
			   contact_email TEXT,
			   created_at TIMESTAMPTZ NOT NULL DEFAULT now()
		   );
		   """)
		   # Crear tabla campaigns (mínima)
		   await cur.execute("""
		   CREATE TABLE IF NOT EXISTS campaigns (
			   id TEXT PRIMARY KEY,
			   client_id INTEGER REFERENCES clients(id),
			   name TEXT,
			   status TEXT,
			   created_at TIMESTAMPTZ DEFAULT now()
		   );
		   """)
		   await cur.execute("""
		   CREATE TABLE IF NOT EXISTS users (
			   id BIGINT PRIMARY KEY,
			   code TEXT UNIQUE NOT NULL,
			   phone TEXT,
			   email TEXT,
			   total_points INTEGER NOT NULL DEFAULT 0,
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
		   await cur.execute("""
		   CREATE TABLE IF NOT EXISTS points_history (
			   id SERIAL PRIMARY KEY,
			   user_id BIGINT NOT NULL,
			   campaign_id TEXT,
			   points INTEGER NOT NULL,
			   reason TEXT,
			   created_at TIMESTAMPTZ DEFAULT now()
		   );
		   """)
		   await conn.commit()

async def add_points(user_id: int, points: int, reason: str, campaign_id: str = None):
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			await cur.execute(
				"UPDATE users SET total_points = COALESCE(total_points, 0) + %s WHERE id = %s;",
				(points, user_id)
			)
			await cur.execute(
				"INSERT INTO points_history (user_id, campaign_id, points, reason) VALUES (%s, %s, %s, %s);",
				(user_id, campaign_id, points, reason)
			)
			await conn.commit()
			logger.info(f"Added {points} points to user {user_id} for {reason} (campaign={campaign_id})")
	except Exception as e:
		logger.error(f"Error adding points to user {user_id}: {e}")
		raise

async def upsert_user(user_id: int, code: str = None, phone: Optional[str] = None, email: Optional[str] = None):
	pool = get_pool()
	try:
		async with pool.connection() as conn, conn.cursor() as cur:
			fields = ["id"]
			values = [user_id]
			updates = []
			if code is not None:
				fields.append("code")
				values.append(code)
				updates.append("code = EXCLUDED.code")
			if phone is not None:
				fields.append("phone")
				values.append(phone)
				updates.append("phone = EXCLUDED.phone")
			if email is not None:
				fields.append("email")
				values.append(email)
				updates.append("email = EXCLUDED.email")
			sql = f"INSERT INTO users ({', '.join(fields)}) VALUES ({', '.join(['%s']*len(fields))}) "
			if updates:
				sql += f"ON CONFLICT (id) DO UPDATE SET {', '.join(updates)};"
			else:
				sql += "ON CONFLICT (id) DO NOTHING;"
			await cur.execute(sql, tuple(values))
			await conn.commit()
			logger.info(f"Upserted user {user_id}")
	except Exception as e:
		logger.error(f"Error upserting user {user_id}: {e}")
		raise

async def get_existing_code_by_user(user_id: int) -> Optional[str]:
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("SELECT code FROM users WHERE id = %s;", (user_id,))
		row = await cur.fetchone()
		return row[0] if row else None

async def find_user_by_code(code: str) -> Optional[int]:
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("SELECT id FROM users WHERE code = %s;", (code,))
		row = await cur.fetchone()
		return int(row[0]) if row else None

async def referee_already_referred(campaign_id: str, referee_id: int) -> bool:
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("""
		SELECT 1 FROM referrals WHERE campaign_id = %s AND referee_id = %s;
		""", (campaign_id, referee_id))
		return (await cur.fetchone()) is not None

async def is_reciprocal_referral(campaign_id: str, referee_id: int, referrer_id: int) -> bool:
	pool = get_pool()
	async with pool.connection() as conn, conn.cursor() as cur:
		await cur.execute("""
		SELECT 1 FROM referrals
		WHERE campaign_id = %s AND referrer_id = %s AND referee_id = %s;
		""", (campaign_id, referrer_id, referee_id))
		return (await cur.fetchone()) is not None

async def insert_referral(campaign_id: str, referrer_id: int, referee_id: int, ref_code: str) -> bool:
	import traceback
	pool = get_pool()
	try:
		async with pool.connection() as conn:
			async with conn.transaction():
				async with conn.cursor() as cur:
					# Validar que la campaña esté activa
					await cur.execute("SELECT status FROM campaigns WHERE id = %s;", (campaign_id,))
					row = await cur.fetchone()
					if not row or row[0] != 'ACTIVE':
						logger.info(f"Referral blocked: campaign inactive or not found (campaign_id={campaign_id})")
						return False
					# Bloqueo de referidos recíprocos
					await cur.execute("""
						SELECT 1 FROM referrals
						WHERE campaign_id = %s AND referrer_id = %s AND referee_id = %s
					""", (campaign_id, referee_id, referrer_id))
					if await cur.fetchone():
						logger.info(f"Reciprocal referral blocked: campaign={campaign_id}, referrer={referrer_id}, referee={referee_id}")
						return False
					await cur.execute("""
						INSERT INTO referrals (campaign_id, referrer_id, referee_id, ref_code)
						VALUES (%s, %s, %s, %s)
						ON CONFLICT (campaign_id, referee_id) DO NOTHING RETURNING campaign_id;
					""", (campaign_id, referrer_id, referee_id, ref_code))
					row = await cur.fetchone()
					logger.info(f"Referral inserted: campaign={campaign_id}, referrer={referrer_id}, referee={referee_id}, inserted={bool(row)}")
					return bool(row)
	except Exception as e:
		tb = traceback.format_exc()
		logger.error(f"Error inserting referral: campaign={campaign_id}, referrer={referrer_id}, referee={referee_id}, error={e}\nTraceback:\n{tb}")
		raise
# This module will contain all database access and repository logic for the SaaS bot.
# Move all DB-related functions from db_repo.py here, and import them as needed.
