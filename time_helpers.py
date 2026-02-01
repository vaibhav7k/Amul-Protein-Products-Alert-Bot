"""
Time helper utilities with timezone awareness.
"""

from datetime import datetime, time, timezone
import pytz
import os

# Get timezone from environment, default to India
BOT_TIMEZONE_STR = os.environ.get("BOT_TIMEZONE", "Asia/Kolkata")
BOT_TIMEZONE = pytz.timezone(BOT_TIMEZONE_STR)


def get_current_time() -> datetime:
    """
    Get current time in bot's configured timezone.
    
    Returns:
        datetime: Current time in bot's timezone, timezone-aware
    """
    return datetime.now(BOT_TIMEZONE)


def get_current_time_utc() -> datetime:
    """
    Get current time in UTC.
    
    Returns:
        datetime: Current time in UTC, timezone-aware
    """
    return datetime.now(timezone.utc)


def get_current_time_only() -> time:
    """
    Get current time portion only (no date) in bot's timezone.
    
    Returns:
        time: Current time portion only (HH:MM:SS)
    """
    return get_current_time().time()


def is_between_times(current: time, start: time, end: time) -> bool:
    """
    Check if current time is between start and end times.
    
    Args:
        current: Current time to check
        start: Start time (e.g., 22:00:00)
        end: End time (e.g., 08:00:00)
    
    Returns:
        bool: True if current is between start and end (handles wrap-around)
    
    Example:
        # Quiet hours 22:00 to 08:00 (10 PM to 8 AM)
        is_between_times(current_time, time(22, 0), time(8, 0))
    """
    if start <= end:
        return start <= current <= end
    else:
        # Handles wrap-around (e.g., 22:00 to 08:00 next day)
        return current >= start or current <= end


def localize_datetime(dt: datetime, tz_str: str = None) -> datetime:
    """
    Convert naive datetime to timezone-aware datetime.
    
    Args:
        dt: Datetime to localize (can be naive or aware)
        tz_str: Timezone string (defaults to bot timezone)
    
    Returns:
        datetime: Timezone-aware datetime
    """
    if tz_str is None:
        tz_str = BOT_TIMEZONE_STR
    
    tz = pytz.timezone(tz_str)
    
    if dt.tzinfo is None:
        # Naive datetime - localize to specified timezone
        return tz.localize(dt)
    else:
        # Already aware - convert to specified timezone
        return dt.astimezone(tz)


def format_datetime_for_display(dt: datetime, format_str: str = "%Y-%m-%d %H:%M:%S %Z") -> str:
    """
    Format datetime for display with timezone info.
    
    Args:
        dt: Datetime to format
        format_str: Format string (default includes timezone)
    
    Returns:
        str: Formatted datetime string
    """
    if dt.tzinfo is None:
        dt = localize_datetime(dt)
    return dt.strftime(format_str)
