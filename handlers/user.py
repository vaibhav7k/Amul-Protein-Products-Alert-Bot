"""
User command handlers for Amul Product Alert Bot.
Contains all user-facing Telegram commands.
"""

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import Config
from database import (
    upsert_user,
    get_user_subscription_status,
    update_user_pincode,
    activate_user_subscription,
    get_user_subscription_details,
    get_setting,
)
from utils import rate_limit, app_logger, user_activity_logger


# --- Start Command ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - Register user and show welcome menu."""
    user = update.effective_user
    user_activity_logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    # Register/update user in database
    upsert_user(user.id, user.username)
    
    # Build interactive menu
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Set/Change Pincode", callback_data="user_set_pincode")],
        [InlineKeyboardButton("ℹ️ My Subscription", callback_data="user_my_subscription")],
        [InlineKeyboardButton("📜 Rules", callback_data="user_rules")],
        [InlineKeyboardButton("✉️ Contact Admin", callback_data="user_contact_admin")]
    ])
    
    welcome_message = (
        f"👋 Welcome, {user.first_name}!\n\n"
        "I am your personal Amul stock bot. Use the menu below to get started."
    )
    await update.message.reply_text(welcome_message, reply_markup=keyboard)


# --- Add Pincode Command ---
@rate_limit(10)
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add command - Set or update user's pincode."""
    user = update.effective_user
    
    try:
        pincode = context.args[0]
        
        # Validate pincode
        if not (pincode.isdigit() and len(pincode) == 6):
            await update.message.reply_text("Invalid pincode. Please provide a 6-digit number.")
            return
        
        # Get current subscription status
        status = get_user_subscription_status(user.id) or 'none'
        
        # Update pincode
        update_user_pincode(user.id, pincode)
        user_activity_logger.info(f"User {user.id} set pincode to {pincode}. Status: {status}")
        
        if status == 'active':
            await update.message.reply_text(f"✅ Your pincode has been updated to {pincode}.")
        else:
            # Check auto-approve setting
            auto_approve_status = get_setting('auto_approve')
            
            if auto_approve_status == '1':
                # Auto-approve with 30-day trial
                _, end_date = activate_user_subscription(user.id, days=30)
                await update.message.reply_text(
                    f"✅ Welcome! Your free 30-day trial for pincode {pincode} has been activated!"
                )
                user_activity_logger.info(f"User {user.id} auto-approved for a 30-day trial.")
            else:
                await update.message.reply_text(
                    f"✅ Your pincode has been set to {pincode}. "
                    "Please use /proof for activation instructions."
                )
                
    except (IndexError, ValueError):
        await update.message.reply_text("Usage: `/add <pincode>`", parse_mode="Markdown")
    except Exception as e:
        app_logger.error(f"Error in /add command for user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("An unexpected error occurred. Please try again.")


# --- Proof Command ---
@rate_limit(30)
async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /proof command - Show payment instructions."""
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"To activate, please complete payment and send the screenshot here.\n\n"
        f"Your User ID is: `{chat_id}`",
        parse_mode="Markdown"
    )


# --- Handle Photo Proof ---
@rate_limit(60)
async def handle_proof_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages - Process payment proof submissions."""
    user = update.effective_user
    
    # Check if user is already active
    status = get_user_subscription_status(user.id)
    if status == 'active':
        await update.message.reply_text("Your subscription is already active!")
        user_activity_logger.warning(f"Active user {user.id} tried to submit proof again.")
        return

    # Create admin action buttons
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Approve", callback_data=f"approve:{user.id}"),
        InlineKeyboardButton("🚫 Block", callback_data=f"block:{user.id}"),
        InlineKeyboardButton("❓ Request New Proof", callback_data=f"request_proof:{user.id}")
    ]])
    
    caption = f"New payment proof from @{user.username} (ID: {user.id})"
    
    try:
        # Forward photo to admin group
        photo_file = update.message.photo[-1]
        await context.bot.send_photo(
            chat_id=Config.ADMIN_GROUP_ID, 
            photo=photo_file.file_id, 
            caption=caption, 
            reply_markup=keyboard
        )
        await update.message.reply_text("✅ Your proof has been submitted for review.")
        user_activity_logger.info(f"Proof from {user.id} forwarded to admin group.")
    except Exception as e:
        app_logger.error(f"Failed to process proof from {user.id}: {e}")
        await update.message.reply_text("Sorry, there was an error submitting your proof.")


# --- Subscription Command ---
async def subscription_command(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    from_button: bool = False
) -> None:
    """Handle /subscription command - Show user's subscription details."""
    message_source = update.message if not from_button else update.callback_query.message
    chat_id = message_source.chat_id
    
    user_data = get_user_subscription_details(chat_id)
    
    if user_data:
        pincode, status, end_date = user_data
        status_emoji = {
            "active": "✅", 
            "pending": "⏳", 
            "expired": "❌", 
            "none": "ℹ️", 
            "blocked": "🚫"
        }
        
        message = (
            f"Subscription Details:\n\n"
            f"Status: *{status.title()}* {status_emoji.get(status, '')}\n"
            f"Pincode: `{pincode or 'Not set'}`\n"
            f"Expires on: {end_date.strftime('%d %b %Y') if end_date else 'N/A'}"
        )
        await message_source.reply_text(message, parse_mode="Markdown")
    else:
        await message_source.reply_text("No data found. Use /start to begin.")


# --- Rules Command ---
async def rules_command(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    from_button: bool = False
) -> None:
    """Handle /rules command - Show service rules."""
    message_source = update.message if not from_button else update.callback_query.message
    
    rules_text = (
        "📜 *Service Rules*\n\n"
        "1. Each subscription is valid for one pincode only.\n"
        "2. You can change your pincode at any time with `/add <new_pincode>`.\n"
        "3. This service is for informational purposes only.\n"
        "4. Spamming commands may result in a temporary block."
    )
    await message_source.reply_text(rules_text, parse_mode="Markdown")


# --- DM Command ---
@rate_limit(60)
async def dm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /dm command - Send message to admin."""
    user = update.effective_user
    message_text = " ".join(context.args)
    
    if not message_text:
        await update.message.reply_text(
            "Usage: `/dm <your message to the admin>`",
            parse_mode="Markdown"
        )
        return
    
    admin_message = (
        f"New message from @{user.username} (ID: `{user.id}`):\n\n"
        f"_{message_text}_\n\n"
        f"To reply, tap to copy and send:\n"
        f"`/reply {user.id} <your message>`"
    )
    
    await context.bot.send_message(
        chat_id=Config.ADMIN_GROUP_ID, 
        text=admin_message, 
        parse_mode="Markdown"
    )
    await update.message.reply_text("✅ Your message has been sent to the admin.")
    user_activity_logger.info(f"DM from {user.id} forwarded to admin group.")


# --- Help Command ---
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command - Show available commands for users."""
    help_text = (
        "🆘 *Available Commands*\n\n"
        "`/start` - Start the bot and see the main menu\n"
        "`/add <pincode>` - Set or update your pincode\n"
        "`/subscription` - Check your subscription status\n"
        "`/proof` - Get payment instructions\n"
        "`/rules` - View service rules\n"
        "`/dm <message>` - Send a message to admin\n"
        "`/help` - Show this help message\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")
