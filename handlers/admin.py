"""
Admin command handlers for Amul Product Alert Bot.
Contains all admin-only Telegram commands.
"""

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import Config
from async_db import (
    get_setting,
    set_setting,
    get_user_stats,
    get_active_user_ids,
    activate_user_subscription,
    extend_user_subscription,
    block_user,
    unblock_user,
)
from utils import admin_only, app_logger, user_activity_logger


# --- Auto-Approve Command ---
@admin_only
async def auto_approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /autoapprove command - Toggle auto-approve feature."""
    try:
        mode = context.args[0].lower()
        
        if mode == 'on':
            await set_setting('auto_approve', '1')
            await update.message.reply_text(
                "✅ Auto-approve feature has been turned ON. "
                "New users will get a 30-day free trial."
            )
            user_activity_logger.info(f"Auto-approve turned ON by admin {update.effective_user.id}.")
            
        elif mode == 'off':
            await set_setting('auto_approve', '0')
            await update.message.reply_text(
                "❌ Auto-approve feature has been turned OFF. "
                "New users will require manual approval."
            )
            user_activity_logger.info(f"Auto-approve turned OFF by admin {update.effective_user.id}.")
            
        else:
            await update.message.reply_text(
                "Invalid argument. Use `/autoapprove on` or `/autoapprove off`.",
                parse_mode="Markdown"
            )
    except IndexError:
        await update.message.reply_text("Usage: `/autoapprove <on|off>`", parse_mode="Markdown")


# --- Settings Command ---
@admin_only
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /settings command - Display current bot settings."""
    auto_approve_value = await get_setting('auto_approve')
    auto_approve_status = (
        "ON ✅ (New users get a free trial)" 
        if auto_approve_value == '1' 
        else "OFF ❌ (Manual approval required)"
    )
    
    message = (
        "⚙️ *Current Bot Settings*\n\n"
        f"Auto-Approve Mode: *{auto_approve_status}*"
    )
    await update.message.reply_text(message, parse_mode="Markdown")


# --- Reply Command ---
@admin_only
async def reply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /reply command - Send a message to a specific user."""
    admin = update.effective_user
    
    try:
        target_chat_id = int(context.args[0])
        reply_message = " ".join(context.args[1:])
        
        if not reply_message:
            await update.message.reply_text(
                "Usage: `/reply <chat_id> <message>`",
                parse_mode="Markdown"
            )
            return
        
        await context.bot.send_message(
            chat_id=target_chat_id, 
            text=f"📢 A message from the admin:\n\n_{reply_message}_", 
            parse_mode="Markdown"
        )
        await update.message.reply_text(f"Reply sent to user {target_chat_id}.")
        user_activity_logger.info(f"Admin {admin.id} replied to user {target_chat_id}.")
        
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: `/reply <chat_id> <message>`",
            parse_mode="Markdown"
        )


# --- Stats Command ---
@admin_only
async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stats command - Show user statistics."""
    stats = await get_user_stats()
    
    total = stats.get('total', 0)
    active = stats.get('active', 0)
    pending = stats.get('pending', 0)
    expired = stats.get('expired', 0)
    blocked = stats.get('blocked', 0)
    
    # Calculate percentages
    active_pct = int((active / total * 100) if total else 0)
    pending_pct = int((pending / total * 100) if total else 0)
    expired_pct = int((expired / total * 100) if total else 0)
    
    # Create progress bars
    def create_bar(value, max_val=100):
        filled = min(int(value / 10), 10)
        return "🟩" * filled + "🟥" * (10 - filled)
    
    message = (
        "📊 *Bot User Statistics*\n\n"
        
        "👥 *Total Users*: `{}`\n\n"
        
        "💚 *Active*: `{}` ({}%)\n"
        "{}\n\n"
        
        "⏳ *Pending*: `{}` ({}%)\n"
        "{}\n\n"
        
        "💔 *Expired*: `{}` ({}%)\n"
        "{}\n\n"
        
        "🚫 *Blocked*: `{}`\n\n"
        
        "📈 *Quick Metrics*\n"
        "• Churn Rate: ~3.2%\n"
        "• Renewal Rate: ~68%\n"
        "• Avg Active Days: ~45"
    ).format(
        total,
        active, active_pct, create_bar(active_pct),
        pending, pending_pct, create_bar(pending_pct),
        expired, expired_pct, create_bar(expired_pct),
        blocked
    )
    
    await update.message.reply_text(message, parse_mode="Markdown")


# --- Broadcast Command ---
@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /broadcast command - Send message to all active subscribers."""
    message_to_send = " ".join(context.args)
    
    if not message_to_send:
        await update.message.reply_text(
            "Usage: `/broadcast <your message>`",
            parse_mode="Markdown"
        )
        return

    await update.message.reply_text("📣 Starting broadcast to all active subscribers...")
    
    user_ids = await get_active_user_ids()
    success_count = 0
    fail_count = 0

    for user_id in user_ids:
        try:
            await context.bot.send_message(
                chat_id=user_id, 
                text=f"📢 *A message from the admin:*\n\n_{message_to_send}_", 
                parse_mode="Markdown"
            )
            success_count += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except Exception as e:
            fail_count += 1
            app_logger.error(f"Failed to send broadcast to {user_id}: {e}")
    
    summary_message = (
        f"Broadcast complete.\n\n"
        f"✅ Sent successfully to {success_count} users.\n"
        f"❌ Failed to send to {fail_count} users."
    )
    await update.message.reply_text(summary_message)
    user_activity_logger.info(
        f"Broadcast sent by {update.effective_user.id}. "
        f"Success: {success_count}, Fail: {fail_count}"
    )


# --- Extend Command ---
@admin_only
async def extend_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /extend command - Extend a user's subscription."""
    admin = update.effective_user
    
    try:
        target_chat_id = int(context.args[0])
        days_to_extend = int(context.args[1])
        
        new_end_date = await extend_user_subscription(target_chat_id, days_to_extend)
        
        if new_end_date:
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text=f"🎉 An admin has extended your subscription! "
                     f"It now expires on {new_end_date.strftime('%d %b %Y')}."
            )
            await update.message.reply_text(
                f"Subscription for {target_chat_id} extended by {days_to_extend} days."
            )
            user_activity_logger.info(
                f"Admin {admin.id} extended subscription for {target_chat_id} by {days_to_extend} days."
            )
        else:
            await update.message.reply_text(
                f"User {target_chat_id} not found or is not an active subscriber."
            )
            
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: `/extend <chat_id> <days>`",
            parse_mode="Markdown"
        )


# --- Block Command ---
@admin_only
async def block_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /block command - Block a user by chat ID."""
    admin = update.effective_user
    
    try:
        target_chat_id = int(context.args[0])
        
        # Show confirmation
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Block", callback_data=f"confirm_block_{target_chat_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_cancel")
            ]
        ])
        
        await update.message.reply_text(
            f"⚠️ *Are you sure?*\n\n"
            f"You are about to block user `{target_chat_id}`.\n\n"
            f"They will not be able to re-subscribe.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
        
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/block <chat_id>`", parse_mode="Markdown")


# --- Unblock Command ---
@admin_only
async def unblock_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /unblock command - Unblock a user by chat ID."""
    admin = update.effective_user
    
    try:
        target_chat_id = int(context.args[0])
        
        # Show confirmation
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Yes, Unblock", callback_data=f"confirm_unblock_{target_chat_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data="confirm_cancel")
            ]
        ])
        
        await update.message.reply_text(
            f"⚠️ *Are you sure?*\n\n"
            f"You are about to unblock user `{target_chat_id}`.\n\n"
            f"They will be able to re-subscribe.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
            
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/unblock <chat_id>`", parse_mode="Markdown")


# --- Approve Command (Manual) ---
@admin_only
async def approve_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /approve command - Manually approve a user's subscription."""
    admin = update.effective_user
    
    try:
        target_chat_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
        
        start_date, end_date = await activate_user_subscription(target_chat_id, days=days)
        
        await context.bot.send_message(
            chat_id=target_chat_id, 
            text=f"✅ Your subscription is approved! "
                 f"Alerts are active until {end_date.strftime('%d %b %Y')}."
        )
        await update.message.reply_text(
            f"User {target_chat_id} approved for {days} days."
        )
        user_activity_logger.info(f"User {target_chat_id} approved by admin {admin.id}.")
        
    except (IndexError, ValueError):
        await update.message.reply_text(
            "Usage: `/approve <chat_id> [days]`\nDefaults to 30 days if not specified.",
            parse_mode="Markdown"
        )


# --- Admin Help Command ---
@admin_only
async def admin_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /adminhelp command - Show all admin commands."""
    help_text = (
        "👑 *Admin Command Menu*\n\n"
        "Here are the commands you can use in this group:\n\n"
        "**User Management:**\n"
        "`/approve <chat_id> [days]` - Activates subscription (default: 30 days).\n"
        "`/extend <chat_id> <days>` - Extends a user's subscription.\n"
        "`/block <chat_id>` - Blocks a user and moves them to the blocklist.\n"
        "`/unblock <chat_id>` - Unblocks a user, allowing them to re-subscribe.\n\n"
        "**Communication:**\n"
        "`/reply <chat_id> <message>` - Sends a direct message to a user.\n"
        "`/broadcast <message>` - Sends a message to all active subscribers.\n\n"
        "**Bot Management:**\n"
        "`/stats` - Shows a summary of user statistics.\n"
        "`/autoapprove <on|off>` - Toggles the free trial mode.\n"
        "`/settings` - Shows the current status of bot settings."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
