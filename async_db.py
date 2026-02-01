"""
Async database wrappers for non-blocking database operations.
All database operations are run in thread pool to avoid blocking event loop.
"""

import asyncio
from datetime import date
from typing import Optional, Dict, List, Tuple, Any

# Import all sync functions from database module
from database import (
    # Connection management
    validate_connection_pool as _validate_connection_pool,
    # User operations
    upsert_user as _upsert_user,
    get_user_subscription_status as _get_user_subscription_status,
    update_user_pincode as _update_user_pincode,
    activate_user_subscription as _activate_user_subscription,
    get_user_subscription_details as _get_user_subscription_details,
    pause_user_subscription as _pause_user_subscription,
    resume_user_subscription as _resume_user_subscription,
    is_user_paused as _is_user_paused,
    get_pause_until_date as _get_pause_until_date,
    get_paused_users as _get_paused_users,
    block_user as _block_user,
    is_user_blocked as _is_user_blocked,
    unblock_user as _unblock_user,
    # Preferences
    get_user_preferences as _get_user_preferences,
    set_user_preference as _set_user_preference,
    toggle_user_preference as _toggle_user_preference,
    get_all_products as _get_all_products,
    # Alert settings
    get_alert_frequency as _get_alert_frequency,
    set_alert_frequency as _set_alert_frequency,
    get_quiet_hours as _get_quiet_hours,
    set_quiet_hours as _set_quiet_hours,
    # Alerts
    get_pending_alerts as _get_pending_alerts,
    mark_alerts_sent as _mark_alerts_sent,
    store_pending_alerts as _store_pending_alerts,
    clear_pending_alerts as _clear_pending_alerts,
    get_users_by_alert_frequency as _get_users_by_alert_frequency,
    # Admin
    get_setting as _get_setting,
    set_setting as _set_setting,
    get_user_stats as _get_user_stats,
    get_active_user_ids as _get_active_user_ids,
    extend_user_subscription as _extend_user_subscription,
    # Expiry
    expire_subscriptions as _expire_subscriptions,
    # Cache & Scraper
    get_product_status as _get_product_status,
    set_product_status as _set_product_status,
    clear_old_product_cache as _clear_old_product_cache,
    get_pincode_data as _get_pincode_data,
    has_cached_products_for_pincode as _has_cached_products_for_pincode,
)


async def run_in_executor(func, *args):
    """Helper to run blocking function in thread pool."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, func, *args)


# --- User Operations (Async) ---

async def upsert_user(chat_id: int, username: Optional[str] = None) -> None:
    """Async: Register or update user in database."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _upsert_user, chat_id, username)


async def get_user_subscription_status(chat_id: int) -> Optional[str]:
    """Async: Get user subscription status."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_user_subscription_status, chat_id)


async def update_user_pincode(chat_id: int, pincode: str) -> None:
    """Async: Update user's pincode."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _update_user_pincode, chat_id, pincode)


async def activate_user_subscription(chat_id: int, subscription_days: int = 30) -> Tuple:
    """Async: Activate user subscription. Returns (start_date, end_date)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _activate_user_subscription, chat_id, subscription_days)


async def get_user_subscription_details(chat_id: int) -> Optional[Tuple]:
    """Async: Get user's subscription details."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_user_subscription_details, chat_id)


async def pause_user_subscription(chat_id: int, days: int) -> Optional[date]:
    """Async: Pause user subscription. Returns resume date."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _pause_user_subscription, chat_id, days)


async def resume_user_subscription(chat_id: int) -> bool:
    """Async: Resume user subscription."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _resume_user_subscription, chat_id)


async def is_user_paused(chat_id: int) -> bool:
    """Async: Check if user is paused."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _is_user_paused, chat_id)

async def get_pause_until_date(chat_id: int) -> Optional[date]:
    """Async: Get pause expiry date."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_pause_until_date, chat_id)


async def get_paused_users() -> List[int]:
    """Async: Get all paused users."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_paused_users)


async def block_user(chat_id: int) -> bool:
    """Async: Block user."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _block_user, chat_id)


async def is_user_blocked(chat_id: int) -> bool:
    """Async: Check if user is blocked."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _is_user_blocked, chat_id)


async def unblock_user(chat_id: int) -> bool:
    """Async: Unblock user."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _unblock_user, chat_id)


# --- Preferences (Async) ---

async def get_user_preferences(chat_id: int) -> List[str]:
    """Async: Get user's product preferences."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_user_preferences, chat_id)


async def set_user_preference(chat_id: int, product_name: str, value: bool) -> bool:
    """Async: Set user preference for a product."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_user_preference, chat_id, product_name, value)


async def toggle_user_preference(chat_id: int, product_name: str) -> bool:
    """Async: Toggle user preference for a product."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _toggle_user_preference, chat_id, product_name)


async def get_all_products() -> List[str]:
    """Async: Get all available products."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_all_products)


# --- Alert Settings (Async) ---

async def get_alert_frequency(chat_id: int) -> Optional[str]:
    """Async: Get user's alert frequency."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_alert_frequency, chat_id)


async def set_alert_frequency(chat_id: int, frequency: str) -> bool:
    """Async: Set user's alert frequency."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_alert_frequency, chat_id, frequency)


async def get_quiet_hours(chat_id: int) -> Tuple[Optional[str], Optional[str]]:
    """Async: Get user's quiet hours."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_quiet_hours, chat_id)


async def set_quiet_hours(chat_id: int, start_time: Optional[str], end_time: Optional[str]) -> bool:
    """Async: Set user's quiet hours. Pass time strings like '22:00:00' or None to clear."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_quiet_hours, chat_id, start_time, end_time)


# --- Alerts (Async) ---

async def get_pending_alerts(chat_id: int) -> List[Tuple[str, str, str]]:
    """Async: Get pending alerts for a user."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_pending_alerts, chat_id)


async def mark_alerts_sent(chat_id: int) -> int:
    """Async: Mark alerts as sent."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _mark_alerts_sent, chat_id)


async def store_pending_alerts(chat_id: int, pincode: str, in_stock_products: List[Tuple[str, str]], sold_out_products: List[Tuple[str, str]]) -> None:
    """Async: Store pending alerts."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _store_pending_alerts, chat_id, pincode, in_stock_products, sold_out_products)


async def clear_pending_alerts(chat_id: int) -> int:
    """Async: Clear all pending alerts for a user."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _clear_pending_alerts, chat_id)


async def get_users_by_alert_frequency(frequency: str) -> List[int]:
    """Async: Get users by alert frequency."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_users_by_alert_frequency, frequency)


# --- Settings (Async) ---

async def get_setting(setting_name: str) -> Optional[str]:
    """Async: Get a bot setting."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_setting, setting_name)


async def set_setting(setting_name: str, value: str) -> bool:
    """Async: Set a bot setting."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _set_setting, setting_name, value)


# --- Admin Operations (Async) ---

async def get_user_stats() -> Dict[str, int]:
    """Async: Get user statistics."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_user_stats)


async def get_active_user_ids() -> List[int]:
    """Async: Get all active user IDs."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_active_user_ids)


async def extend_user_subscription(chat_id: int, additional_days: int) -> Optional[date]:
    """Async: Extend user subscription. Returns new end_date or None."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _extend_user_subscription, chat_id, additional_days)


# --- Expiry (Async) ---

async def expire_subscriptions() -> int:
    """Async: Expire old subscriptions. Returns count of expired subscriptions."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _expire_subscriptions)


# --- Cache & Scraper (Async) ---

async def get_product_status(product_url: str, pincode: str) -> Optional[str]:
    """Async: Get cached product status."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_product_status, product_url, pincode)


async def set_product_status(product_url: str, pincode: str, status: str) -> None:
    """Async: Set product status in cache."""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _set_product_status, product_url, pincode, status)


async def get_pincode_data() -> Dict[str, List[int]]:
    """Async: Get mapping of pincodes to chat_ids."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_pincode_data)

async def get_products_for_pincode(pincode: str) -> List[str]:
    """Async: Get list of available products for a pincode from cache."""
    from database import get_db_cursor
    
    def _get_products():
        try:
            with get_db_cursor() as cur:
                cur.execute("""
                    SELECT product_url 
                    FROM product_status_cache 
                    WHERE pincode = %s AND status = 'stock'
                    ORDER BY last_updated DESC
                    LIMIT 20;
                """, (pincode,))
                results = cur.fetchall()
                return [row[0] for row in results] if results else []
        except Exception:
            return []
    
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _get_products)


async def has_cached_products_for_pincode(pincode: str) -> bool:
    """Async: Check if we have cached products for this pincode (indicates first-time scraping)."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _has_cached_products_for_pincode, pincode)


async def validate_connection_pool() -> bool:
    """Async: Validate database connection pool health. Reinitializes if needed."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _validate_connection_pool)


async def clear_old_product_cache(days: int = 14) -> int:
    """Async: Clear product cache older than specified days. Returns count deleted."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _clear_old_product_cache, days)