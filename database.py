"""
Database module for Amul Product Alert Bot.
Handles all PostgreSQL database operations with connection pooling.
"""

import asyncio
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from urllib.parse import urlparse
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple, Any, Callable

from config import Config


# --- Connection Pool ---
_connection_pool: Optional[pool.SimpleConnectionPool] = None


def init_connection_pool(min_connections: int = 1, max_connections: int = 10) -> None:
    """Initialize the database connection pool."""
    global _connection_pool
    
    result = urlparse(Config.DATABASE_URL)
    _connection_pool = pool.SimpleConnectionPool(
        min_connections,
        max_connections,
        dbname=result.path[1:],
        user=result.username,
        password=result.password,
        host=result.hostname,
        port=result.port
    )


def close_connection_pool() -> None:
    """Close all connections in the pool."""
    global _connection_pool
    if _connection_pool:
        _connection_pool.closeall()
        _connection_pool = None


def validate_connection_pool() -> bool:
    """
    Validate that connection pool is healthy.
    If not, reinitialize it.
    
    Returns:
        bool: True if pool is healthy, False if reinit was needed
    """
    global _connection_pool
    
    try:
        # Try to get and test a connection
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.close()
        
        # Pool is healthy
        return True
    
    except Exception as e:
        from utils import app_logger
        app_logger.warning(f"⚠️ Connection pool unhealthy: {e}. Reinitializing...")
        
        # Close existing pool
        close_connection_pool()
        
        # Reinitialize
        try:
            init_connection_pool()
            app_logger.info("✅ Connection pool reinitialized successfully")
            return False
        except Exception as reinit_error:
            app_logger.error(f"❌ Failed to reinitialize connection pool: {reinit_error}")
            return False


# --- Async Helpers ---
async def run_async_db_operation(func: Callable, *args, **kwargs):
    """
    Run a blocking database operation in a thread pool to avoid blocking event loop.
    
    Usage:
        result = await run_async_db_operation(get_user_preferences, user_id)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, func, *args)


async def run_async_db_operation_kwargs(func: Callable, **kwargs):
    """
    Run a blocking database operation with keyword arguments in a thread pool.
    
    Usage:
        result = await run_async_db_operation_kwargs(some_func, arg1=val1, arg2=val2)
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(**kwargs))


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Automatically returns connection to pool when done.
    
    Usage:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(...)
            conn.commit()
    """
    global _connection_pool
    
    if _connection_pool is None:
        init_connection_pool()
    
    conn = _connection_pool.getconn()
    try:
        yield conn
    finally:
        _connection_pool.putconn(conn)


@contextmanager
def get_db_cursor(commit: bool = False):
    """
    Context manager for database cursor.
    Optionally commits after operations.
    
    Usage:
        with get_db_cursor(commit=True) as cur:
            cur.execute(...)
    """
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            yield cur
            if commit:
                conn.commit()
        finally:
            cur.close()


# --- Database Initialization ---
def init_db() -> None:
    """Initialize database tables if they don't exist and validate connection."""
    from utils import app_logger
    
    try:
        # Test connection first
        app_logger.info("Testing database connection...")
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.close()
        app_logger.info("✅ Database connection successful")
    except Exception as e:
        app_logger.error(f"❌ Database connection FAILED: {type(e).__name__}: {e}")
        raise
    
    try:
        with get_db_cursor(commit=True) as cur:
            # 1. Create users table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    chat_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    pincode VARCHAR(6),
                    subscription_status VARCHAR(50) DEFAULT 'none'
                );
            """)
            
            # 2. Migration: Add missing columns to 'users' table
            columns_to_add = [
                ("start_date", "DATE"),
                ("end_date", "DATE"),
                ("is_paused", "BOOLEAN DEFAULT FALSE"),
                ("pause_until", "DATE"),
                ("alert_frequency", "VARCHAR(20) DEFAULT 'instant'"),
                ("quiet_hours_start", "TIME"),
                ("quiet_hours_end", "TIME")
            ]
                
            for col_name, col_type in columns_to_add:
                cur.execute(f"""
                    DO $$ 
                    BEGIN 
                        IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                    WHERE table_name='users' AND column_name='{col_name}') THEN
                            ALTER TABLE users ADD COLUMN {col_name} {col_type};
                        END IF;
                    END $$;
                """)
        
        # 3. Create blocklist table
        with get_db_cursor(commit=True) as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS blocklist (
                    chat_id BIGINT PRIMARY KEY,
                    username VARCHAR(255),
                    block_date DATE,
                    reason TEXT
                );
            """)
            
            # Settings table
            cur.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key VARCHAR(50) PRIMARY KEY,
                    value VARCHAR(50)
                );
            """)
            
            # Product status cache table (for state persistence)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS product_status_cache (
                    product_url VARCHAR(512),
                    pincode VARCHAR(6),
                    status VARCHAR(20),
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (product_url, pincode)
                );
            """)
            
            # User preferences table (for product filtering)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS user_preferences (
                    chat_id BIGINT,
                    product_name VARCHAR(255),
                    active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (chat_id, product_name),
                    FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE
                );
            """)
            
            # Pending alerts table (for digest mode)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS pending_alerts (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT,
                    pincode VARCHAR(6),
                    product_title VARCHAR(255),
                    product_url VARCHAR(512),
                    status VARCHAR(20),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    sent BOOLEAN DEFAULT FALSE,
                    FOREIGN KEY (chat_id) REFERENCES users(chat_id) ON DELETE CASCADE,
                    UNIQUE(chat_id, product_url, status, pincode)
                );
            """)
            
            # Migration: Add pincode column to pending_alerts if it doesn't exist
            cur.execute("""
                DO $$ 
                BEGIN 
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                WHERE table_name='pending_alerts' AND column_name='pincode') THEN
                        ALTER TABLE pending_alerts ADD COLUMN pincode VARCHAR(6);
                    END IF;
                END $$;
            """)
            
            # Set default settings
            cur.execute("""
                INSERT INTO settings (key, value) 
                VALUES ('auto_approve', '0') 
                ON CONFLICT (key) DO NOTHING;
            """)
        
        app_logger.info("✅ Database tables initialized")
    except Exception as e:
        app_logger.error(f"❌ Database initialization FAILED: {e}")
        raise


# --- Settings Operations ---
def get_setting(key: str) -> str:
    """Fetch a setting value from the database."""
    with get_db_cursor() as cur:
        cur.execute("SELECT value FROM settings WHERE key = %s;", (key,))
        result = cur.fetchone()
        return result[0] if result else '0'


def set_setting(key: str, value: str) -> None:
    """Update a setting value in the database."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO settings (key, value) 
            VALUES (%s, %s) 
            ON CONFLICT (key) DO UPDATE SET value = %s;
        """, (key, value, value))


# --- User Operations ---
def upsert_user(chat_id: int, username: Optional[str]) -> None:
    """Insert or update a user in the database."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO users (chat_id, username, subscription_status) 
            VALUES (%s, %s, 'none') 
            ON CONFLICT (chat_id) DO UPDATE SET username = %s;
        """, (chat_id, username, username))


def get_user(chat_id: int) -> Optional[Tuple]:
    """Get user data by chat_id."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT chat_id, username, pincode, subscription_status, start_date, end_date 
            FROM users WHERE chat_id = %s;
        """, (chat_id,))
        return cur.fetchone()


def get_user_subscription_status(chat_id: int) -> Optional[str]:
    """Get user's subscription status."""
    with get_db_cursor() as cur:
        cur.execute("SELECT subscription_status FROM users WHERE chat_id = %s;", (chat_id,))
        result = cur.fetchone()
        return result[0] if result else None


def update_user_pincode(chat_id: int, pincode: str) -> None:
    """Update user's pincode."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("UPDATE users SET pincode = %s WHERE chat_id = %s;", (pincode, chat_id))


def activate_user_subscription(chat_id: int, days: int = 30) -> Tuple[date, date]:
    """Activate a user's subscription for specified number of days."""
    start_date = date.today()
    end_date = start_date + timedelta(days=days)
    
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users 
            SET subscription_status = 'active', start_date = %s, end_date = %s 
            WHERE chat_id = %s;
        """, (start_date, end_date, chat_id))
    
    return start_date, end_date


def extend_user_subscription(chat_id: int, days: int) -> Optional[date]:
    """Extend an active user's subscription by specified days."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            SELECT end_date FROM users 
            WHERE chat_id = %s AND subscription_status = 'active';
        """, (chat_id,))
        result = cur.fetchone()
        
        if result:
            current_end_date = result[0]
            base_date = max(date.today(), current_end_date)
            new_end_date = base_date + timedelta(days=days)
            
            cur.execute("UPDATE users SET end_date = %s WHERE chat_id = %s;", (new_end_date, chat_id))
            return new_end_date
        return None


# --- Pause/Resume Functions ---
def pause_user_subscription(chat_id: int, days: int = 30) -> Optional[date]:
    """Pause a user's subscription. Returns the resume date."""
    resume_date = date.today() + timedelta(days=days)
    
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users 
            SET is_paused = TRUE, pause_until = %s 
            WHERE chat_id = %s AND subscription_status = 'active';
        """, (resume_date, chat_id))
    
    return resume_date


def resume_user_subscription(chat_id: int) -> bool:
    """Resume a paused user's subscription."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users 
            SET is_paused = FALSE, pause_until = NULL 
            WHERE chat_id = %s;
        """, (chat_id,))
        return cur.rowcount > 0


def get_paused_users() -> List[int]:
    """Get list of paused users whose pause period has ended."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT chat_id FROM users 
            WHERE is_paused = TRUE AND pause_until <= %s;
        """, (date.today(),))
        return [row[0] for row in cur.fetchall()]


def is_user_paused(chat_id: int) -> bool:
    """Check if user is currently paused."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT is_paused FROM users WHERE chat_id = %s;
        """, (chat_id,))
        result = cur.fetchone()
        return result[0] if result else False


def get_pause_until_date(chat_id: int) -> Optional[date]:
    """Get the pause until date for a paused user."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT pause_until FROM users WHERE chat_id = %s;
        """, (chat_id,))
        result = cur.fetchone()
        return result[0] if result else None


def get_user_subscription_details(chat_id: int) -> Optional[Tuple[str, str, date]]:
    """Get user's pincode, status, and end_date."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT pincode, subscription_status, end_date 
            FROM users WHERE chat_id = %s;
        """, (chat_id,))
        return cur.fetchone()


# --- Subscription Management ---
def get_pincode_data() -> Dict[str, List[str]]:
    """Get mapping of pincodes to chat_ids for active subscribers."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT chat_id, pincode FROM users 
            WHERE subscription_status = 'active' AND pincode IS NOT NULL;
        """)
        rows = cur.fetchall()
    
    pincode_to_chat_ids: Dict[str, List[int]] = {}
    for chat_id, pincode in rows:
        if pincode not in pincode_to_chat_ids:
            pincode_to_chat_ids[pincode] = []
        # keep chat_id as integer for downstream callers
        try:
            pincode_to_chat_ids[pincode].append(int(chat_id))
        except Exception:
            # fallback: append as-is
            pincode_to_chat_ids[pincode].append(chat_id)
    
    return pincode_to_chat_ids


def get_active_user_ids() -> List[int]:
    """Get list of all active subscriber chat_ids."""
    with get_db_cursor() as cur:
        cur.execute("SELECT chat_id FROM users WHERE subscription_status = 'active';")
        return [row[0] for row in cur.fetchall()]


def get_user_stats() -> Dict[str, int]:
    """Get user statistics by subscription status."""
    stats: Dict[str, int] = {}
    
    with get_db_cursor() as cur:
        cur.execute("SELECT subscription_status, COUNT(*) FROM users GROUP BY subscription_status;")
        for status, count in cur.fetchall():
            stats[status] = count
        
        cur.execute("SELECT COUNT(*) FROM users;")
        stats['total'] = cur.fetchone()[0]
    
    return stats


def expire_subscriptions() -> int:
    """Mark expired subscriptions. Returns count of expired subscriptions."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users 
            SET subscription_status = 'expired' 
            WHERE subscription_status = 'active' AND end_date IS NOT NULL AND end_date < %s;
        """, (date.today(),))
        return cur.rowcount


# --- Block/Unblock Operations ---
def block_user(chat_id: int) -> bool:
    """Block a user and move them to blocklist. Returns True if successful."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT chat_id, username FROM users WHERE chat_id = %s;", (chat_id,))
            user = cur.fetchone()
            
            if user:
                cur.execute("""
                    INSERT INTO blocklist (chat_id, username, block_date) 
                    VALUES (%s, %s, %s) 
                    ON CONFLICT (chat_id) DO NOTHING;
                """, (user[0], user[1], date.today()))
                
                cur.execute("DELETE FROM users WHERE chat_id = %s;", (chat_id,))
                conn.commit()
                return True
            return False
        finally:
            cur.close()


def unblock_user(chat_id: int) -> bool:
    """Unblock a user and restore them to users table. Returns True if successful."""
    with get_db_connection() as conn:
        cur = conn.cursor()
        try:
            cur.execute("SELECT chat_id, username FROM blocklist WHERE chat_id = %s;", (chat_id,))
            user = cur.fetchone()
            
            if user:
                cur.execute("""
                    INSERT INTO users (chat_id, username, subscription_status) 
                    VALUES (%s, %s, 'expired') 
                    ON CONFLICT (chat_id) DO NOTHING;
                """, (user[0], user[1]))
                
                cur.execute("DELETE FROM blocklist WHERE chat_id = %s;", (chat_id,))
                conn.commit()
                return True
            return False
        finally:
            cur.close()


def is_user_blocked(chat_id: int) -> bool:
    """Check if a user is in the blocklist."""
    with get_db_cursor() as cur:
        cur.execute("SELECT 1 FROM blocklist WHERE chat_id = %s;", (chat_id,))
        return cur.fetchone() is not None

# --- Product Status Cache (State Persistence) ---
def get_product_status(product_url: str, pincode: str) -> Optional[str]:
    """Get cached product status ('stock', 'sold', or None if not cached)."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT status FROM product_status_cache WHERE product_url = %s AND pincode = %s;",
            (product_url, pincode)
        )
        result = cur.fetchone()
        return result[0] if result else None


def set_product_status(product_url: str, pincode: str, status: str) -> None:
    """Update or insert product status in cache."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO product_status_cache (product_url, pincode, status)
            VALUES (%s, %s, %s)
            ON CONFLICT (product_url, pincode) 
            DO UPDATE SET status = %s, last_updated = CURRENT_TIMESTAMP;
        """, (product_url, pincode, status, status))


def clear_old_product_cache(days: int = 30) -> int:
    """Clear product status cache older than specified days. Returns count deleted."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            DELETE FROM product_status_cache
            WHERE last_updated < CURRENT_TIMESTAMP - INTERVAL '%s days';
        """, (days,))
        return cur.rowcount


def has_cached_products_for_pincode(pincode: str) -> bool:
    """Check if we have any cached product statuses for this pincode."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM product_status_cache WHERE pincode = %s LIMIT 1;",
            (pincode,)
        )
        result = cur.fetchone()
        return result[0] > 0 if result else False


# --- User Preferences (Product Filtering) ---
def get_user_preferences(chat_id: int) -> List[str]:
    """Get list of products user is tracking."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT product_name FROM user_preferences WHERE chat_id = %s AND active = TRUE;",
            (chat_id,)
        )
        return [row[0] for row in cur.fetchall()]


def set_user_preference(chat_id: int, product_name: str, active: bool = True) -> None:
    """Add or update a product preference."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO user_preferences (chat_id, product_name, active)
            VALUES (%s, %s, %s)
            ON CONFLICT (chat_id, product_name) 
            DO UPDATE SET active = %s;
        """, (chat_id, product_name, active, active))


def toggle_user_preference(chat_id: int, product_name: str) -> bool:
    """Toggle a product preference on/off. Returns new state."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "SELECT active FROM user_preferences WHERE chat_id = %s AND product_name = %s;",
            (chat_id, product_name)
        )
        result = cur.fetchone()
        new_active = not result[0] if result else True
        
        set_user_preference(chat_id, product_name, new_active)
        return new_active


def get_all_products() -> List[str]:
    """Get list of all available products from cache."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT DISTINCT product_url FROM product_status_cache 
            ORDER BY product_url;
        """)
        return [row[0] for row in cur.fetchall()]


def clear_user_preferences(chat_id: int) -> None:
    """Clear all preferences for a user."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM user_preferences WHERE chat_id = %s;", (chat_id,))


# --- Alert Frequency Settings ---
def set_alert_frequency(chat_id: int, frequency: str) -> None:
    """Set user's alert frequency (instant, hourly, daily)."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE users SET alert_frequency = %s WHERE chat_id = %s;",
            (frequency, chat_id)
        )


def get_alert_frequency(chat_id: int) -> str:
    """Get user's alert frequency (default: instant)."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT alert_frequency FROM users WHERE chat_id = %s;",
            (chat_id,)
        )
        result = cur.fetchone()
        return result[0] if result else "instant"

def set_quiet_hours(chat_id: int, start_time: Optional[str], end_time: Optional[str]) -> None:
    """Set user's quiet hours (time strings 'HH:MM:SS') or clear with None.

    Pass `start_time` and `end_time` as strings (e.g. '22:00:00'). To clear quiet hours,
    pass None for both values.
    """
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            UPDATE users 
            SET quiet_hours_start = %s::TIME, quiet_hours_end = %s::TIME 
            WHERE chat_id = %s;
        """, (start_time, end_time, chat_id))


def get_quiet_hours(chat_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Get user's quiet hours. Returns (start_time_str, end_time_str) or (None, None)."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT quiet_hours_start, quiet_hours_end FROM users WHERE chat_id = %s;",
            (chat_id,)
        )
        result = cur.fetchone()
        if not result:
            return (None, None)
        
        start, end = result
        # Convert time objects to strings if needed
        start_str = start.strftime("%H:%M:%S") if start else None
        end_str = end.strftime("%H:%M:%S") if end else None
        return (start_str, end_str)


# --- Pending Alerts (for digest mode) ---
def add_pending_alert(chat_id: int, product_title: str, product_url: str, status: str) -> None:
    """Add an alert to the pending queue."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("""
            INSERT INTO pending_alerts (chat_id, product_title, product_url, status)
            VALUES (%s, %s, %s, %s);
        """, (chat_id, product_title, product_url, status))


def get_pending_alerts(chat_id: int, limit: int = 10) -> List[Tuple[str, str, str]]:
    """Get pending unsent alerts for a user."""
    with get_db_cursor() as cur:
        cur.execute("""
            SELECT product_title, product_url, status FROM pending_alerts
            WHERE chat_id = %s AND sent = FALSE
            ORDER BY created_at
            LIMIT %s;
        """, (chat_id, limit))
        return cur.fetchall()


def mark_alerts_sent(chat_id: int) -> int:
    """Mark all pending alerts as sent. Returns count."""
    with get_db_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE pending_alerts SET sent = TRUE WHERE chat_id = %s AND sent = FALSE;",
            (chat_id,)
        )
        return cur.rowcount


def clear_pending_alerts(chat_id: int) -> int:
    """Clear pending alerts for a user. Returns count deleted."""
    with get_db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM pending_alerts WHERE chat_id = %s;", (chat_id,))
        return cur.rowcount


def get_users_by_alert_frequency(frequency: str) -> List[int]:
    """Get all chat IDs with a specific alert frequency."""
    with get_db_cursor() as cur:
        cur.execute(
            "SELECT chat_id FROM users WHERE alert_frequency = %s AND subscription_status = 'active';",
            (frequency,)
        )
        return [row[0] for row in cur.fetchall()]


def store_pending_alerts(chat_id: int, pincode: str, in_stock_products: List[Tuple[str, str]], sold_out_products: List[Tuple[str, str]]) -> None:
    """Store pending alerts for later delivery (digest mode or quiet hours)."""
    with get_db_cursor(commit=True) as cur:
        for title, url in in_stock_products:
            cur.execute(
                """INSERT INTO pending_alerts (chat_id, pincode, product_title, product_url, status)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (chat_id, product_url, status, pincode) DO NOTHING;""",
                (chat_id, pincode, title, url, "stock")
            )
        
        for title, url in sold_out_products:
            cur.execute(
                """INSERT INTO pending_alerts (chat_id, pincode, product_title, product_url, status)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (chat_id, product_url, status, pincode) DO NOTHING;""",
                (chat_id, pincode, title, url, "sold")
            )