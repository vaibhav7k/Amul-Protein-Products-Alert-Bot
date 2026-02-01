"""
Amul Product Alert Bot - Main Entry Point

A Telegram bot that monitors Amul product stock and sends alerts to subscribers.
"""

import html
import json
import asyncio
import traceback

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application, 
    CommandHandler, 
    MessageHandler, 
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from config import Config
from database import init_db, close_connection_pool
from async_db import (
    activate_user_subscription,
    block_user,
    get_user_preferences,
    get_all_products,
    toggle_user_preference,
    set_alert_frequency,
    unblock_user,
    upsert_user,
    get_user_subscription_status,
    get_user_subscription_details,
    pause_user_subscription,
)
from utils import setup_logging, app_logger, user_activity_logger, is_admin
from scraper import scheduler

# Import all handlers
from handlers import (
    # User handlers
    start_command,
    add_command,
    proof_command,
    handle_proof_photo,
    subscription_command,
    rules_command,
    dm_command,
    help_command,
    pause_command,
    resume_command,
    preferences_command,
    alert_settings_command,
    quiet_hours_command,
    getalert_command,
    # Admin handlers
    auto_approve_command,
    settings_command,
    reply_command,
    stats_command,
    broadcast_command,
    extend_command,
    block_command,
    unblock_command,
    approve_command,
    admin_help_command,
)


# --- Refactored Button Handler Functions ---

async def handle_user_menu_button(query, update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user menu buttons (user_* callbacks)."""
    action = query.data.split("_", 1)[1]
    
    if action == "set_pincode":
        await query.message.reply_text("To set your pincode, please send:\n`/add <pincode>`", parse_mode="Markdown")
    elif action == "my_subscription":
        await subscription_command(update, context, from_button=True)
    elif action == "rules":
        await rules_command(update, context, from_button=True)
    elif action == "contact_admin":
        await query.message.reply_text("To contact an admin, please send:\n`/dm <your message>`", parse_mode="Markdown")
    elif action == "help":
        await help_command(update, context)
    elif action == "payment_proof":
        await query.message.reply_text("To submit your payment proof, please send:\n`/proof`", parse_mode="Markdown")
    elif action == "proof_info":
        await proof_command(update, context)
    elif action == "start":
        # Handle start button from callback - use edit_message_text instead
        await handle_start_button(query, context)


async def handle_start_button(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle main menu button from callback - shows welcome menu using edit_message_text."""
    user = query.from_user
    chat_id = user.id
    
    # Register/update user in database
    await upsert_user(chat_id, user.username)
    
    # Check user's current status
    status = await get_user_subscription_status(chat_id) or 'none'
    user_data = await get_user_subscription_details(chat_id)
    pincode = user_data[0] if user_data else None
    
    # Build interactive menu based on status
    if status == 'active':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📊 My Subscription", callback_data="user_my_subscription")],
            [InlineKeyboardButton("📝 Change Pincode", callback_data="user_set_pincode")],
            [InlineKeyboardButton("❓ Help", callback_data="user_help")]
        ])
        welcome_message = (
            f"👋 Welcome back, {user.first_name}!\n\n"
            f"✅ Your subscription is active 🎉\n"
            f"📍 Location: {pincode}\n\n"
            f"You're receiving alerts for your area!"
        )
    elif status == 'pending':
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏳ Check Status", callback_data="user_my_subscription")],
            [InlineKeyboardButton("📞 Contact Admin", callback_data="user_contact_admin")]
        ])
        welcome_message = (
            f"👋 Welcome back, {user.first_name}!\n\n"
            f"⏳ Your proof is pending review.\n"
            f"We'll notify you once approved!"
        )
    else:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Set Pincode & Start", callback_data="user_set_pincode")],
            [InlineKeyboardButton("📜 Rules", callback_data="user_rules")],
            [InlineKeyboardButton("❓ How It Works", callback_data="user_help")]
        ])
        welcome_message = (
            f"👋 Welcome, {user.first_name}! 🎉\n\n"
            f"I'm your personal Amul Product Alert Bot 🥛\n\n"
            f"Get instant alerts when Amul products are in stock at your location!\n\n"
            f"Let's get started 👇"
        )
    
    await query.edit_message_text(welcome_message, reply_markup=keyboard)


async def handle_pause_button(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle pause subscription buttons."""
    action = query.data.split("_")[1]
    
    if action == "cancel":
        await query.edit_message_text("❌ Pause cancelled.")
        return
    
    try:
        days = int(action)
        chat_id = query.from_user.id
        resume_date = await pause_user_subscription(chat_id, days)
        user_activity_logger.info(f"User {chat_id} paused subscription for {days} days.")
        
        # Validate resume_date is not None
        if not resume_date:
            await query.answer("❌ Error processing pause request", show_alert=True)
            return
        
        await query.edit_message_text(
            f"⏸️ *Subscription Paused!*\n\n"
            f"Your subscription is paused for {days} days.\n"
            f"📅 Will resume automatically on: {resume_date.strftime('%d %b %Y')}\n\n"
            f"You won't receive alerts during this time.",
            parse_mode="Markdown"
        )
    except ValueError:
        await query.answer("❌ Invalid pause duration", show_alert=True)
    except Exception as e:
        app_logger.error(f"Error in pause button handler: {e}", exc_info=True)
        await query.answer("❌ Error processing pause request", show_alert=True)


async def handle_preference_button(query, update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle product preference buttons."""
    action = query.data.split("_")[1]
    chat_id = query.from_user.id
    
    if action == "done":
        prefs = await get_user_preferences(chat_id)
        if not prefs or len(prefs) == 0:
            await query.answer("❌ Please select at least 1 product before saving!", show_alert=True)
            return
        
        await query.answer("✅ Preferences saved!")
        await query.edit_message_text(
            f"📊 You're tracking {len(prefs)} products.\nUse /alertsettings to change frequency."
        )
        return
    
    # Toggle preference
    try:
        product_idx = int(action)
        all_products = await get_all_products()
        if product_idx < len(all_products):
            product = all_products[product_idx]
            new_state = await toggle_user_preference(chat_id, product)
            user_activity_logger.info(f"User {chat_id} toggled product preference: {product} -> {new_state}")
    except (ValueError, IndexError):
        pass
    
    # Refresh menu
    try:
        await preferences_command(update, context)
    except Exception:
        pass


async def handle_frequency_button(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle alert frequency buttons."""
    frequency = query.data.split("_")[1]
    chat_id = query.from_user.id
    
    await set_alert_frequency(chat_id, frequency)
    user_activity_logger.info(f"User {chat_id} set alert frequency: {frequency}")
    
    emoji_map = {"instant": "⚡", "hourly": "⏰", "daily": "📅"}
    emoji = emoji_map.get(frequency, "🔔")
    
    await query.edit_message_text(
        f"{emoji} *Alert frequency updated to {frequency.upper()}!*\n\nYour preference has been saved.",
        parse_mode="Markdown"
    )


async def handle_confirmation_button(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin confirmation buttons."""
    if not await is_admin(query.from_user.id, context.bot):
        await query.answer("This action can only be performed by a group admin.", show_alert=True)
        return
    
    parts = query.data.split("_")
    action = "_".join(parts[1:-1])
    target_chat_id = int(parts[-1])
    admin_user = query.from_user
    
    if action == "block":
        if await block_user(target_chat_id):
            await query.edit_message_text(f"✅ User {target_chat_id} has been blocked by {admin_user.first_name}.")
            user_activity_logger.info(f"User {target_chat_id} BLOCKED by admin {admin_user.id}.")
        else:
            await query.edit_message_text(f"User {target_chat_id} not found.")
    
    elif action == "unblock":
        if await unblock_user(target_chat_id):
            await query.edit_message_text(f"✅ User {target_chat_id} has been unblocked by {admin_user.first_name}.")
            user_activity_logger.info(f"User {target_chat_id} UNBLOCKED by admin {admin_user.id}.")
        else:
            await query.edit_message_text(f"User {target_chat_id} not found in blocklist.")


async def handle_admin_action_button(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin action buttons (approve, block, request_proof)."""
    if not await is_admin(query.from_user.id, context.bot):
        await query.answer("This action can only be performed by a group admin.", show_alert=True)
        return
    
    try:
        action, target_chat_id_str = query.data.split(":")
        target_chat_id = int(target_chat_id_str)
        admin_user = query.from_user
        
        if action == "approve":
            _, end_date = await activate_user_subscription(target_chat_id, days=30)
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text=f"✅ Your subscription is approved! Alerts are active until {end_date.strftime('%d %b %Y')}."
            )
            await query.edit_message_caption(
                caption=f"✅ Approved by {admin_user.first_name}.", 
                reply_markup=None
            )
            user_activity_logger.info(f"User {target_chat_id} approved by admin {admin_user.id}.")
        
        elif action == "block":
            if await block_user(target_chat_id):
                await query.edit_message_caption(
                    caption=f"🚫 User {target_chat_id} has been blocked by {admin_user.first_name}.", 
                    reply_markup=None
                )
                user_activity_logger.info(f"User {target_chat_id} BLOCKED by admin {admin_user.id}.")
            else:
                await query.edit_message_caption(caption=f"User {target_chat_id} not found.", reply_markup=None)
        
        elif action == "request_proof":
            await context.bot.send_message(
                chat_id=target_chat_id, 
                text="⚠️ The admin has requested a new payment proof. The image you sent was unclear or invalid. Please submit a new one."
            )
            await query.edit_message_caption(
                caption=f"❓ New proof requested from user {target_chat_id} by {admin_user.first_name}.", 
                reply_markup=None
            )
            user_activity_logger.info(f"Admin {admin_user.id} requested new proof from {target_chat_id}.")
    except (ValueError, IndexError):
        app_logger.error(f"Invalid admin action format: {query.data}")
        await query.answer("❌ Invalid action format", show_alert=True)


# --- Main Interactive Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Route callback buttons to appropriate handlers."""
    query = update.callback_query
    
    # Answer immediately to prevent "Query is too old" error
    await query.answer()
    
    try:
        # Route based on callback data prefix
        if query.data.startswith("user_"):
            await handle_user_menu_button(query, update, context)
        elif query.data.startswith("pause_"):
            await handle_pause_button(query, context)
        elif query.data.startswith("pref_"):
            await handle_preference_button(query, update, context)
        elif query.data.startswith("freq_"):
            await handle_frequency_button(query, context)
        elif query.data.startswith("confirm_"):
            if query.data == "confirm_cancel":
                await query.edit_message_text("❌ Action cancelled.")
            else:
                await handle_confirmation_button(query, context)
        elif query.data == "quiet_hours":
            await query.edit_message_text(
                "🌙 *Quiet Hours*\n\nSet a time range when you don't want alerts.\nExample: 10 PM to 8 AM\n\nSend: `/quiethours 22 8`",
                parse_mode="Markdown"
            )
        elif ":" in query.data:  # Admin action buttons
            await handle_admin_action_button(query, context)
        else:
            app_logger.warning(f"Unknown callback data: {query.data}")
    except Exception as e:
        app_logger.error(f"Error in button_handler: {e}", exc_info=True)
        await query.answer("❌ An error occurred", show_alert=True)


# --- Global Error Handler ---
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle uncaught exceptions."""
    app_logger.error("Exception while handling an update:", exc_info=context.error)
    
    tb_list = traceback.format_exception(None, context.error, context.error.__traceback__)
    tb_string = "".join(tb_list)
    
    update_str = update.to_dict() if isinstance(update, Update) else str(update)
    
    message = (
        f"An exception was raised while handling an update\n"
        f"<pre>update = {html.escape(json.dumps(update_str, indent=2, ensure_ascii=False))}</pre>\n\n"
        f"<pre>context.user_data = {html.escape(str(context.user_data))}</pre>\n\n"
        f"<pre>{html.escape(tb_string)}</pre>"
    )
    
    if Config.LOG_GROUP_ID:
        try:
            for i in range(0, len(message), 4096):
                chunk = message[i:i + 4096]
                await context.bot.send_message(
                    chat_id=Config.LOG_GROUP_ID, 
                    text=chunk, 
                    parse_mode=ParseMode.HTML
                )
        except Exception as log_err:
            # Fallback if the Log Group is inaccessible
            app_logger.error(f"Failed to send error log to Telegram: {log_err}")
            # Optional: Send a dm to the primary admin directly if you have their ID


async def post_init(application: Application) -> None:
    """
    Background task starter. 
    Runs AFTER the bot application has successfully initialized.
    """
    try:
        app_logger.info("Bot initialized. Starting background scheduler...")
        # Initialize task list if not exists
        if 'tasks' not in application.bot_data:
            application.bot_data['tasks'] = []
        
        # Start the main scheduler as a background task
        task = asyncio.create_task(scheduler())
        # Store task in bot_data so we can cancel it on shutdown
        application.bot_data['tasks'].append(task)
        app_logger.info(f"✅ Scheduler task started (Task count: {len(application.bot_data['tasks'])})")
    except Exception as e:
        app_logger.error(f"Error in post_init: {e}", exc_info=True)


async def shutdown_handler(application: Application) -> None:
    """Handle graceful shutdown of background tasks."""
    try:
        app_logger.info("Bot shutting down...")
        # Cancel all background tasks
        tasks = application.bot_data.get('tasks', [])
        if tasks:
            app_logger.info(f"Cancelling {len(tasks)} background tasks...")
            for task in tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for all tasks to complete cancellation
            try:
                await asyncio.gather(*tasks, return_exceptions=True)
            except asyncio.CancelledError:
                app_logger.info("All background tasks cancelled successfully")
        else:
            app_logger.info("No background tasks to cancel")
    except Exception as e:
        app_logger.error(f"Error during shutdown: {e}")
    finally:
        close_connection_pool()  # ✅ Add this
        app_logger.info("Database connection pool closed")

def main() -> None:
    """Main application entry point."""
    setup_logging()
    # Validate configuration
    if not Config.validate():
        return

    # Setup logging and database
    init_db()
    
    app_logger.info("Initializing Amul Product Alert Bot...")
    
    # Build application
    # Added .post_init(post_init) to correctly handle background tasks
    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init)
        .post_stop(shutdown_handler)
        .build()
    )
    
    # Register error handler
    application.add_error_handler(error_handler)

    # --- User Command Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("add", add_command))
    application.add_handler(CommandHandler("subscription", subscription_command))
    application.add_handler(CommandHandler("proof", proof_command))
    application.add_handler(CommandHandler("rules", rules_command))
    application.add_handler(CommandHandler("dm", dm_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("pause", pause_command))
    application.add_handler(CommandHandler("resume", resume_command))
    application.add_handler(CommandHandler("preferences", preferences_command))
    application.add_handler(CommandHandler("alertsettings", alert_settings_command))
    application.add_handler(CommandHandler("quiethours", quiet_hours_command))
    application.add_handler(CommandHandler("getalert", getalert_command))
    
    # Photo handler
    application.add_handler(
        MessageHandler(
            filters.PHOTO & (~filters.Chat(chat_id=int(Config.ADMIN_GROUP_ID))), 
            handle_proof_photo
        )
    )
    
    # Callback query handler
    application.add_handler(CallbackQueryHandler(button_handler))

    # --- Admin Command Handlers ---
    application.add_handler(CommandHandler("adminhelp", admin_help_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CommandHandler("reply", reply_command))
    application.add_handler(CommandHandler("extend", extend_command))
    application.add_handler(CommandHandler("approve", approve_command))
    application.add_handler(CommandHandler("unblock", unblock_command))
    application.add_handler(CommandHandler("block", block_command))
    application.add_handler(CommandHandler("autoapprove", auto_approve_command))
    application.add_handler(CommandHandler("settings", settings_command))
    
    app_logger.info("Starting bot polling...")
    
    # Run polling (This handles the loop automatically now)
    application.run_polling()


if __name__ == "__main__":
    main()
