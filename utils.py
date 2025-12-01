"""
Utility module for Amul Product Alert Bot.
Contains logging setup, decorators, and helper functions.
"""

import time
import logging
import requests
from functools import wraps
from typing import Callable, Any

from telegram import Update
from telegram.ext import ContextTypes

from config import Config


# --- Global Variables ---
telegram_session = requests.Session()
app_logger = logging.getLogger("amul_bot")
user_activity_logger = logging.getLogger("user_activity")
user_activity_logger.propagate = False


# --- Custom Telegram Log Handler ---
class TelegramLogHandler(logging.Handler):
    """Custom logging handler that sends logs to a Telegram chat."""
    
    def __init__(self, token: str, chat_id: str):
        super().__init__()
        self.token = token
        self.chat_id = chat_id

    def emit(self, record: logging.LogRecord) -> None:
        log_entry = self.format(record)
        if record.levelno >= logging.INFO:
            api_url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = {
                "chat_id": self.chat_id, 
                "text": f"<pre>{log_entry}</pre>", 
                "parse_mode": "HTML"
            }
            try:
                telegram_session.post(api_url, data=payload, timeout=10)
            except Exception:
                pass  # Silently fail to avoid recursion


def setup_logging() -> None:
    """Configure logging for the application."""
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    formatter = logging.Formatter(log_format)
    
    # Application logger
    app_logger.setLevel(logging.INFO)
    if app_logger.hasHandlers():
        app_logger.handlers.clear()
    
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    app_logger.addHandler(stream_handler)
    
    # User activity logger (sends to Telegram)
    user_activity_logger.setLevel(logging.INFO)
    if Config.LOG_GROUP_ID:
        if user_activity_logger.hasHandlers():
            user_activity_logger.handlers.clear()
        
        telegram_handler = TelegramLogHandler(Config.BOT_TOKEN, Config.LOG_GROUP_ID)
        telegram_handler.setFormatter(formatter)
        user_activity_logger.addHandler(telegram_handler)


# --- Admin Check ---
async def is_admin(chat_id: int, bot) -> bool:
    """Check if a user is an admin of the admin group."""
    try:
        admins = await bot.get_chat_administrators(Config.ADMIN_GROUP_ID)
        return any(admin.user.id == chat_id for admin in admins)
    except Exception as e:
        app_logger.error(f"Could not check admin status for {chat_id}: {e}")
        return False


# --- Decorators ---
def admin_only(func: Callable) -> Callable:
    """Decorator to restrict command to admin group admins only."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
        # Only allow in admin group
        if str(update.message.chat_id) != Config.ADMIN_GROUP_ID:
            return
        
        # Check if user is admin
        if not await is_admin(update.message.from_user.id, context.bot):
            await update.message.reply_text("This command can only be used by group admins.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapped


def rate_limit(limit_seconds: int = 5) -> Callable:
    """Decorator to rate-limit command usage per user."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs) -> Any:
            last_called = context.user_data.get(func.__name__, 0)
            
            if time.time() - last_called < limit_seconds:
                app_logger.info(f"Spam attempt by {update.effective_user.id} for command /{func.__name__}")
                return
            
            context.user_data[func.__name__] = time.time()
            return await func(update, context, *args, **kwargs)
        return wrapped
    return decorator


# --- Telegram Helpers ---
def send_telegram_message(chat_id: str, text: str, parse_mode: str = "Markdown") -> bool:
    """Send a message via Telegram API directly (without async context)."""
    api_url = f"https://api.telegram.org/bot{Config.BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id, 
        "text": text, 
        "parse_mode": parse_mode
    }
    try:
        response = telegram_session.post(api_url, data=payload, timeout=10)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        app_logger.error(f"Failed to send message to {chat_id}: {e}")
        return False


def send_consolidated_alert(
    chat_id: str, 
    pincode: str, 
    in_stock_products: list, 
    sold_out_products: list
) -> None:
    """Send a consolidated stock alert to a user."""
    message_parts = [f"*Stock Update for {pincode}*"]
    
    if in_stock_products:
        product_links = [f"• [{title}]({url})" for title, url in in_stock_products]
        message_parts.append("\n✅ *Now IN STOCK*\n" + "\n".join(product_links))
    
    if sold_out_products:
        product_links = [f"• [{title}]({url})" for title, url in sold_out_products]
        message_parts.append("\n❌ *Now SOLD OUT*\n" + "\n".join(product_links))
    
    message = "\n".join(message_parts)
    
    if send_telegram_message(chat_id, message):
        app_logger.info(f"Consolidated alert sent to {chat_id} for {pincode}")
    else:
        app_logger.error(f"Failed to send consolidated alert for {pincode}")
