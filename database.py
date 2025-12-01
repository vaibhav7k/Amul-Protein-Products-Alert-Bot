"""
Database module for Amul Product Alert Bot.
Handles all PostgreSQL database operations with connection pooling.
"""

import psycopg2
from psycopg2 import pool
from contextlib import contextmanager
from urllib.parse import urlparse
from datetime import date, timedelta
from typing import Optional, Dict, List, Tuple, Any

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
    """Initialize database tables if they don't exist."""
    with get_db_cursor(commit=True) as cur:
        # Users table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                username VARCHAR(255),
                pincode VARCHAR(6),
                subscription_status VARCHAR(50) DEFAULT 'none',
                start_date DATE,
                end_date DATE
            );
        """)
        
        # Blocklist table
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
        
        # Set default settings
        cur.execute("""
            INSERT INTO settings (key, value) 
            VALUES ('auto_approve', '0') 
            ON CONFLICT (key) DO NOTHING;
        """)


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
    
    pincode_to_chat_ids: Dict[str, List[str]] = {}
    for chat_id, pincode in rows:
        if pincode not in pincode_to_chat_ids:
            pincode_to_chat_ids[pincode] = []
        pincode_to_chat_ids[pincode].append(str(chat_id))
    
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
            WHERE subscription_status = 'active' AND end_date < %s;
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
