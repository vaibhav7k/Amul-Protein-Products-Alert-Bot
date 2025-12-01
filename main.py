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
from database import (
    init_db,
    activate_user_subscription,
    block_user,
    get_db_cursor,
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


# --- Interactive Button Handler ---
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline keyboard button callbacks."""
    query = update.callback_query
    
    # Answer immediately to prevent "Query is too old" error
    await query.answer()
    
    # User menu buttons
    if query.data.startswith("user_"):
        action = query.data.split("_", 1)[1]
        
        if action == "set_pincode":
            await query.message.reply_text(
                "To set your pincode, please send:\n`/add <pincode>`", 
                parse_mode="Markdown"
            )
        elif action == "my_subscription":
            await subscription_command(update, context, from_button=True)
        elif action == "rules":
            await rules_command(update, context, from_button=True)
        elif action == "contact_admin":
            await query.message.reply_text(
                "To contact an admin, please send:\n`/dm <your message>`", 
                parse_mode="Markdown"
            )
        return

    # Admin action buttons
    if not await is_admin(query.from_user.id, context.bot):
        await query.answer("This action can only be performed by a group admin.", show_alert=True)
        return

    action, target_chat_id_str = query.data.split(":")
    target_chat_id = int(target_chat_id_str)
    admin_user = query.from_user
    
    if action == "approve":
        _, end_date = activate_user_subscription(target_chat_id, days=30)
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
        if block_user(target_chat_id):
            await query.edit_message_caption(
                caption=f"🚫 User {target_chat_id} has been blocked by {admin_user.first_name}.", 
                reply_markup=None
            )
            user_activity_logger.info(f"User {target_chat_id} BLOCKED by admin {admin_user.id}.")
        else:
            await query.edit_message_caption(
                caption=f"User {target_chat_id} not found.", 
                reply_markup=None
            )
            
    elif action == "request_proof":
        await context.bot.send_message(
            chat_id=target_chat_id, 
            text="⚠️ The admin has requested a new payment proof. "
                 "The image you sent was unclear or invalid. Please submit a new one."
        )
        await query.edit_message_caption(
            caption=f"❓ New proof requested from user {target_chat_id} by {admin_user.first_name}.", 
            reply_markup=None
        )
        user_activity_logger.info(f"Admin {admin_user.id} requested new proof from {target_chat_id}.")


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
        # Split long messages to respect Telegram's 4096 char limit
        for i in range(0, len(message), 4096):
            chunk = message[i:i + 4096]
            try:
                await context.bot.send_message(
                    chat_id=Config.LOG_GROUP_ID, 
                    text=chunk, 
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                # If HTML parsing fails, send without formatting
                await context.bot.send_message(
                    chat_id=Config.LOG_GROUP_ID, 
                    text=chunk[:4096]
                )


async def post_init(application: Application) -> None:
    """
    Background task starter. 
    Runs AFTER the bot application has successfully initialized.
    """
    app_logger.info("Bot initialized. Starting background scheduler...")
    asyncio.create_task(scheduler())

def main() -> None:
    """Main application entry point."""
    # Validate configuration
    if not Config.validate():
        return

    # Setup logging and database
    setup_logging()
    init_db()
    
    app_logger.info("Initializing Amul Product Alert Bot...")
    
    # Build application
    # Added .post_init(post_init) to correctly handle background tasks
    application = (
        Application.builder()
        .token(Config.BOT_TOKEN)
        .post_init(post_init) 
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
