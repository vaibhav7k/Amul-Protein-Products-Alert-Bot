"""
User command handlers for Amul Product Alert Bot.
Contains all user-facing Telegram commands.
"""

import asyncio
from datetime import date
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import Config
from async_db import (
    upsert_user,
    get_user_subscription_status,
    update_user_pincode,
    activate_user_subscription,
    get_user_subscription_details,
    pause_user_subscription,
    resume_user_subscription,
    is_user_paused,
    get_pause_until_date,
    get_user_preferences,
    toggle_user_preference,
    get_all_products,
    get_alert_frequency,
    set_alert_frequency,
    get_quiet_hours,
    set_quiet_hours,
    get_pending_alerts,
    mark_alerts_sent,
    clear_pending_alerts,
    get_setting,
    get_products_for_pincode,
)
from utils import rate_limit, app_logger, user_activity_logger


# --- Utility Functions ---
def format_product_name(product_str: str, max_length: int = 18) -> str:
    """
    Format product name for button display.
    Removes common prefixes and shortens to fit button constraints.
    
    Examples:
    - "amul-high-fat-milk" -> "High Fat Milk"
    - "amul-butter" -> "Butter"
    - "amul-fresh-paneer" -> "Fresh Paneer"
    """
    # Extract product name from URL or direct string
    product_name = product_str.split('/')[-1].lower()
    
    # Remove "amul-" prefix
    if product_name.startswith("amul-"):
        product_name = product_name[5:]  # Remove "amul-"
    
    # Replace hyphens with spaces and title case
    product_name = product_name.replace("-", " ").title()
    
    # Common abbreviations to save space
    abbreviations = {
        "High Fat": "HF",
        "Low Fat": "LF",
        "Standard Fat": "SF",
        "Full Cream": "FC",
        "Pasteurized": "Pasteur.",
    }
    
    for long_form, short_form in abbreviations.items():
        product_name = product_name.replace(long_form, short_form)
    
    # Trim to max length
    if len(product_name) > max_length:
        product_name = product_name[:max_length - 1].rstrip() + "…"
    
    return product_name.strip()


# --- Start Command ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command - Register user and show welcome menu."""
    user = update.effective_user
    user_activity_logger.info(f"User {user.id} ({user.username}) started the bot.")
    
    # Register/update user in database
    await upsert_user(user.id, user.username)
    
    # Check user's current status
    status = await get_user_subscription_status(user.id) or 'none'
    user_data = await get_user_subscription_details(user.id)
    pincode = user_data[0] if user_data else None
    
    # Build interactive menu based on status
    if status == 'active':
        # User already has active subscription
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
        # User submitted proof, waiting for approval
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
        # New user or needs to set up
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
    
    await update.message.reply_text(welcome_message, reply_markup=keyboard)


# --- Add Pincode Command ---
@rate_limit(10)
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /add command - Set or update user's pincode."""
    from utils import validate_pincode
    
    user = update.effective_user
    
    try:
        pincode = context.args[0]
        
        # Validate pincode format and service area
        is_valid, message = validate_pincode(pincode)
        if not is_valid:
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("🏠 Main Menu", callback_data="user_start"),
                InlineKeyboardButton("❓ Help", callback_data="user_help")
            ]])
            await update.message.reply_text(
                message,
                parse_mode="Markdown",
                reply_markup=keyboard
            )
            return
        
        # Show progress
        status_msg = await update.message.reply_text("⏳ Processing your request...")
        
        # Get current subscription status
        status = await get_user_subscription_status(user.id) or 'none'
        
        # Clear any pending alerts from previous pincode
        await clear_pending_alerts(user.id)
        
        # Update pincode
        await update_user_pincode(user.id, pincode)
        user_activity_logger.info(f"User {user.id} set pincode to {pincode}. Status: {status}")
        
        # Check if pincode has data in cache (non-blocking check)
        available_products = await get_products_for_pincode(pincode)
        
        pincode_status = "✅ Data available" if available_products else "🔍 Searching..."
        product_preview = ""
        if available_products:
            product_preview = "\n\n*Available Products:*\n"
            for idx, product in enumerate(available_products[:5], 1):
                product_name = product.split('/')[-1].replace('-', ' ').title()[:20]
                product_preview += f"{idx}. {product_name}\n"
            if len(available_products) > 5:
                product_preview += f"... +{len(available_products) - 5} more"
        
        if status == 'active':
            await status_msg.edit_text(
                f"✅ *Success!*\n\n"
                f"Your pincode has been updated to `{pincode}`.\n"
                f"{pincode_status}\n"
                f"{product_preview}\n\n"
                f"Your alerts will now show products for this location! 📍",
                parse_mode="Markdown"
            )
        else:
            # Check auto-approve setting
            auto_approve_status = await get_setting('auto_approve')
            
            if auto_approve_status == '1':
                # Auto-approve with 30-day trial
                _, end_date = await activate_user_subscription(user.id, days=30)
                
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("🎉 Start Getting Alerts", callback_data="user_start")
                ]])
                
                await status_msg.edit_text(
                    f"🎉 *Awesome!*\n\n"
                    f"Your free 30-day trial is active! 🎊\n\n"
                    f"📍 Location: `{pincode}`\n"
                    f"{pincode_status}\n"
                    f"{product_preview}\n\n"
                    f"⏰ Trial ends: {end_date.strftime('%d %b %Y')}\n\n"
                    "You'll receive alerts when Amul products are in stock.",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                user_activity_logger.info(f"User {user.id} auto-approved for a 30-day trial.")
                
                # Send initial alert with current in-stock products
                try:
                    available_products = await get_products_for_pincode(pincode)
                    if available_products:
                        welcome_msg = f"📢 *Welcome Alert!*\n\n"
                        welcome_msg += f"Here are products currently available at your location:\n\n"
                        for idx, product in enumerate(available_products[:10], 1):
                            product_name = product.split('/')[-1].replace('-', ' ').title()
                            welcome_msg += f"{idx}. ✅ {product_name}\n"
                        if len(available_products) > 10:
                            welcome_msg += f"\n... +{len(available_products) - 10} more products available"
                        welcome_msg += f"\n\nYou'll receive instant alerts when stock changes at your location! 🚀"
                        
                        await update.message.reply_text(welcome_msg, parse_mode="Markdown")
                        user_activity_logger.info(f"User {user.id} sent welcome alert with {len(available_products)} available products")
                except Exception as e:
                    app_logger.warning(f"Could not send welcome alert to {user.id}: {e}")
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("💳 Next: Submit Payment", callback_data="user_payment_proof")],
                    [InlineKeyboardButton("❓ How to Pay?", callback_data="user_proof_info")]
                ])
                
                await status_msg.edit_text(
                    f"✅ *Pincode saved!*\n\n"
                    f"📍 Location: `{pincode}`\n"
                    f"{pincode_status}\n"
                    f"{product_preview}\n\n"
                    "Next step: Complete payment to activate alerts!\n\n"
                    "💡 *Tip*: Use the buttons below to continue.",
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
                
    except (IndexError, ValueError):
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu", callback_data="user_start"),
            InlineKeyboardButton("❓ Help", callback_data="user_help")
        ]])
        await update.message.reply_text(
            "❌ *Invalid Command*\n\n"
            "Usage: `/add <pincode>`\n"
            "Example: `/add 600113`",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    except Exception as e:
        app_logger.error(f"Error in /add command for user {user.id}: {e}", exc_info=True)
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🏠 Main Menu", callback_data="user_start"),
            InlineKeyboardButton("📞 Contact Admin", callback_data="user_contact_admin")
        ]])
        await update.message.reply_text(
            "❌ *Something went wrong*\n\n"
            "Please try again or contact support.",
            parse_mode="Markdown",
            reply_markup=keyboard
        )


# --- Proof Command ---
@rate_limit(30)
async def proof_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /proof command - Show payment instructions."""
    chat_id = update.effective_chat.id
    
    proof_text = (
        "💳 *Payment Instructions*\n\n"
        
        "Step 1️⃣: Make Payment\n"
        "Transfer ₹99/month to:\n"
        "UPI: admin@bank (or your UPI ID)\n"
        "Or use the payment link: [Pay Here](https://payment.link)\n\n"
        
        "Step 2️⃣: Take Screenshot\n"
        "Capture the payment confirmation\n\n"
        
        "Step 3️⃣: Upload Screenshot\n"
        "Send the screenshot here using the camera icon\n\n"
        
        "Step 4️⃣: Wait for Approval\n"
        "We'll verify and activate within 1-2 hours\n\n"
        
        "Your User ID: `{}`\n"
        "Include this in your payment notes!\n\n"
        
        "❓ Need help? Use `/dm <message>`"
    ).format(chat_id)
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("📸 Upload Payment Screenshot", callback_data="user_upload_proof")
    ]])
    
    await update.message.reply_text(proof_text, parse_mode="Markdown", reply_markup=keyboard)


# --- Handle Photo Proof ---
@rate_limit(60)
async def handle_proof_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages - Process payment proof submissions."""
    user = update.effective_user
    
    # Check if user is already active
    status = await get_user_subscription_status(user.id)
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
    
    user_data = await get_user_subscription_details(chat_id)
    
    if user_data:
        pincode, status, end_date = user_data
        
        # Calculate days left
        days_left = (end_date - date.today()).days if end_date else 0
        
        # Status indicator
        status_icons = {
            "active": "✅",
            "pending": "⏳",
            "expired": "❌",
            "none": "ℹ️",
            "blocked": "🚫"
        }
        status_emoji = status_icons.get(status, "❓")
        
        # Progress bar (10 blocks)
        progress_bar = ""
        if status == "active" and days_left > 0:
            filled = min(int(days_left / 3), 10)  # Max 10 blocks, 3 days per block
            bar = "🟩" * filled + "🟥" * (10 - filled)
            progress_bar = f"\n{bar}\n{days_left} days left"
        
        message = (
            f"📊 *Subscription Status*\n\n"
            f"Status: {status_emoji} *{status.upper()}*\n"
            f"Location: 📍 {pincode or 'Not set'}\n"
            f"Expires: {end_date.strftime('%d %b %Y') if end_date else 'N/A'}"
            f"{progress_bar}\n\n"
        )
        
        if status == "active" and days_left <= 7:
            message += "⚠️ Your subscription is expiring soon. Renew now!"
        elif status == "expired":
            message += "💳 Your subscription has expired. Renew to continue receiving alerts."
        elif status == "pending":
            message += "⏳ Waiting for admin approval. You'll be notified once approved."
        elif status == "blocked":
            message += "🚫 Your account has been blocked. Contact admin for details."
        elif status == "none":
            message += "ℹ️ No active subscription yet. Use `/add <pincode>` to get started!"
        
        await message_source.reply_text(message, parse_mode="Markdown")
    else:
        await message_source.reply_text(
            "❌ No data found.\n\n"
            "Use `/start` to begin the setup process.",
            parse_mode="Markdown"
        )


# --- Rules Command ---
async def rules_command(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    from_button: bool = False
) -> None:
    """Handle /rules command - Show service rules."""
    message_source = update.message if not from_button else update.callback_query.message
    
    rules_text = (
        "📜 *Service Rules & Guidelines*\n\n"
        
        "🎯 *General*\n"
        "1. Each subscription is valid for one pincode only\n"
        "2. You can change your pincode anytime with `/add <new_pincode>`\n"
        "3. This service is for informational purposes only\n\n"
        
        "✅ *Do's*\n"
        "• Set a valid pincode for accurate alerts\n"
        "• Contact admin if you have issues\n"
        "• Keep your account active by renewing on time\n\n"
        
        "❌ *Don'ts*\n"
        "• Spam commands (may result in temporary block)\n"
        "• Share bot access with others\n"
        "• Use automated scripts or bots\n\n"
        
        "⚠️ *Violations*\n"
        "Repeated violations may result in account suspension."
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
        
        "🚀 *Getting Started*\n"
        "`/start` - Main menu with quick actions\n"
        "`/add <pincode>` - Set your delivery location\n"
        "_Example: `/add 600113`_\n\n"
        
        "📊 *Account Management*\n"
        "`/subscription` - Check your subscription status\n"
        "`/proof` - Get payment instructions\n"
        "`/rules` - View service rules\n\n"
        
        "💬 *Communication*\n"
        "`/dm <message>` - Send a message to admin\n"
        "`/help` - Show this help menu\n\n"
        
        "💡 *Pro Tips*\n"
        "• You can use inline buttons - no need to type commands!\n"
        "• Your pincode can be changed anytime\n"
        "• Premium members get priority support\n"
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

# --- Pause Command ---
@rate_limit(30)  # Allow every 30 seconds (was 60)
async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pause command - Pause subscription temporarily."""
    user = update.effective_user
    chat_id = user.id
    
    try:
        # Check if user is already paused
        is_paused = await is_user_paused(chat_id)
        if is_paused:
            pause_until = await get_pause_until_date(chat_id)
            pause_text = f"{pause_until.strftime('%d %b %Y')}" if pause_until else "unknown date"
            
            await update.message.reply_text(
                "⏸️ *Already Paused*\n\n"
                f"Your subscription is paused until {pause_text}.\n"
                "Use `/resume` to reactivate it earlier.",
                parse_mode="Markdown"
            )
            return
        
        # Check subscription status
        status = await get_user_subscription_status(chat_id)
        if status != 'active':
            await update.message.reply_text(
                "❌ Cannot Pause\n\n"
                "Only active subscriptions can be paused.\n"
                f"Your current status: {(status or 'none').upper()}\n\n"
                "💡 *Tip*: Set up a subscription first using `/add <pincode>`",
                parse_mode="Markdown"
            )
            return
        
        # Show pause options
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("⏸️ Pause for 7 days", callback_data="pause_7")],
            [InlineKeyboardButton("⏸️ Pause for 14 days", callback_data="pause_14")],
            [InlineKeyboardButton("⏸️ Pause for 30 days", callback_data="pause_30")],
            [InlineKeyboardButton("❌ Cancel", callback_data="pause_cancel")]
        ])
        
        message = (
            "⏸️ *Pause Subscription*\n\n"
            "How long would you like to pause?\n\n"
            "You won't receive alerts during this time,\n"
            "but your subscription will resume automatically!\n\n"
            "Choose an option:"
        )
        
        await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")
    except Exception as e:
        app_logger.error(f"Error in /pause command for user {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *Something went wrong*\n\n"
            "Please try again later or contact support.",
            parse_mode="Markdown"
        )


# --- Resume Command ---
@rate_limit(30)  # Allow every 30 seconds (was 60)
async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /resume command - Resume paused subscription."""
    user = update.effective_user
    chat_id = user.id
    
    try:
        # Check if user is paused
        is_paused = await is_user_paused(chat_id)
        if not is_paused:
            # Check actual subscription status
            status = await get_user_subscription_status(chat_id)
            if status == 'active':
                await update.message.reply_text(
                    "ℹ️ *Not Paused*\n\n"
                    "Your subscription is not currently paused.\n"
                    "It's active and running! 🎉",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text(
                    "❌ *No Active Subscription*\n\n"
                    f"Current status: {(status or 'none').upper()}\n\n"
                    "You need an active subscription to resume.\n"
                    "Use `/add <pincode>` to set one up.",
                    parse_mode="Markdown"
                )
            return
        
        # Resume the subscription
        await resume_user_subscription(chat_id)
        user_activity_logger.info(f"User {chat_id} resumed subscription.")
        
        await update.message.reply_text(
            "✅ *Subscription Resumed!*\n\n"
            "🎉 Your subscription is active again!\n"
            "You'll start receiving alerts immediately.",
            parse_mode="Markdown"
        )
    except Exception as e:
        app_logger.error(f"Error in /resume command for user {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *Something went wrong*\n\n"
            "Please try again later or contact support.",
            parse_mode="Markdown"
        )


# --- Preferences Command ---
@rate_limit(10)
async def preferences_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /preferences command - Manage product preferences."""
    user = update.effective_user
    chat_id = user.id
    
    # Parallel query for faster response
    current_prefs, all_products = await asyncio.gather(
        get_user_preferences(chat_id),
        get_all_products()
    )
    
    if not all_products:
        await update.message.reply_text(
            "❌ No products available yet.\n"
            "Please check back later."
        )
        return
    
    # Build preference buttons (2 columns)
    buttons = []
    for i in range(0, len(all_products), 2):
        row = []
        for j in range(2):
            if i + j < len(all_products):
                product = all_products[i + j]
                # Format product name for display
                product_name = format_product_name(product, max_length=16)
                is_selected = product in current_prefs
                emoji = "✅" if is_selected else "⭕"
                row.append(InlineKeyboardButton(
                    f"{emoji} {product_name}",
                    callback_data=f"pref_{i + j}"
                ))
        buttons.append(row)
    
    # Add Done button
    buttons.append([InlineKeyboardButton("✔️ Done", callback_data="pref_done")])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Build summary of selected products
    summary_text = ""
    if current_prefs:
        summary_text = f"\n\n*Currently Tracking ({len(current_prefs)}):*\n"
        for product in current_prefs:
            product_name = format_product_name(product, max_length=25)
            summary_text += f"✅ {product_name}\n"
    else:
        summary_text = "\n\n_No products selected yet_"
    
    message = (
        "🛍️ *Product Preferences*\n\n"
        "Select which products you want to track:\n\n"
        "✅ = Selected | ⭕ = Not Selected\n\n"
        "_Tap to toggle_"
        + summary_text
    )
    
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")


# --- Alert Settings Command ---
@rate_limit(10)
async def alert_settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /alertsettings command - Configure alert frequency and quiet hours."""
    user = update.effective_user
    chat_id = user.id
    
    # Parallel queries for faster response
    frequency, (quiet_start, quiet_end) = await asyncio.gather(
        get_alert_frequency(chat_id),
        get_quiet_hours(chat_id)
    )
    
    # Build settings menu
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⚡ Real-time Alerts", callback_data="freq_instant")],
        [InlineKeyboardButton("⏰ Hourly Digest", callback_data="freq_hourly")],
        [InlineKeyboardButton("📅 Daily Digest", callback_data="freq_daily")],
        [InlineKeyboardButton("🌙 Set Quiet Hours", callback_data="quiet_hours")],
        [InlineKeyboardButton("🏠 Main Menu", callback_data="user_start")]
    ])
    
    quiet_hours_display = "None set"
    if quiet_start and quiet_end:
        # Convert time objects to strings (HH:MM format)
        start_str = str(quiet_start)[:5] if isinstance(quiet_start, str) else quiet_start.strftime('%H:%M')
        end_str = str(quiet_end)[:5] if isinstance(quiet_end, str) else quiet_end.strftime('%H:%M')
        quiet_hours_display = f"{start_str} - {end_str}"
    
    message = (
        "🔔 *Alert Settings*\n\n"
        f"Current Frequency: *{frequency.upper()}*\n"
        f"Quiet Hours: {quiet_hours_display}\n\n"
        "Choose your preference:"
    )
    
    await update.message.reply_text(message, reply_markup=keyboard, parse_mode="Markdown")


# --- Quiet Hours Command ---
@rate_limit(10)
async def quiet_hours_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /quiethours command - Set quiet hours."""
    user = update.effective_user
    chat_id = user.id
    
    if not context.args or len(context.args) < 2:
        current_start, current_end = await get_quiet_hours(chat_id)
        current_display = "None set"
        if current_start and current_end:
            # Convert time objects to strings (HH:MM format)
            start_str = str(current_start)[:5] if isinstance(current_start, str) else current_start.strftime('%H:%M')
            end_str = str(current_end)[:5] if isinstance(current_end, str) else current_end.strftime('%H:%M')
            current_display = f"{start_str} - {end_str}"
        
        await update.message.reply_text(
            "🌙 *Set Quiet Hours*\n\n"
            f"Current: {current_display}\n\n"
            "Usage: `/quiethours <start_hour> <end_hour>`\n\n"
            "Examples:\n"
            "• `/quiethours 22 8` - 10 PM to 8 AM (no alerts)\n"
            "• `/quiethours 23 7` - 11 PM to 7 AM\n"
            "• `/quiethours 0 0` - Clear quiet hours\n\n"
            "_Hours must be 0-23 (24-hour format)_",
            parse_mode="Markdown"
        )
        return
    
    try:
        start_hour = int(context.args[0])
        end_hour = int(context.args[1])
        
        if not (0 <= start_hour <= 23) or not (0 <= end_hour <= 23):
            await update.message.reply_text(
                "❌ Invalid hours! Must be 0-23.\n"
                "Example: `/quiethours 22 8`",
                parse_mode="Markdown"
            )
            return
        
        # Special case: 0 0 means clear quiet hours
        if start_hour == 0 and end_hour == 0:
            await set_quiet_hours(chat_id, None, None)
            user_activity_logger.info(f"User {chat_id} cleared quiet hours")
            
            await update.message.reply_text(
                "🌙 *Quiet Hours Cleared*\n\n"
                "You will receive alerts at any time.",
                parse_mode="Markdown"
            )
            return
        
        start_time = f"{start_hour:02d}:00:00"
        end_time = f"{end_hour:02d}:00:00"
        
        await set_quiet_hours(chat_id, start_time, end_time)
        user_activity_logger.info(f"User {chat_id} set quiet hours: {start_time} - {end_time}")
        
        await update.message.reply_text(
            f"🌙 *Quiet Hours Updated*\n\n"
            f"No alerts from {start_hour:02d}:00 to {end_hour:02d}:00\n\n"
            f"Alerts during quiet hours will be sent when quiet hours end.",
            parse_mode="Markdown"
        )
    except (ValueError, IndexError):
        await update.message.reply_text(
            "❌ Invalid format!\n\n"
            "Usage: `/quiethours <start> <end>`\n"
            "Example: `/quiethours 22 8`",
            parse_mode="Markdown"
        )


# --- Get Alert Command ---
@rate_limit(2)
async def getalert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /getalert command - Show instant alert of last available data."""
    user = update.effective_user
    chat_id = user.id
    
    try:
        # Get user pincode
        user_data = await get_user_subscription_details(chat_id)
        pincode = user_data[0] if user_data else None
        
        if not pincode:
            await update.message.reply_text(
                "❌ *No Pincode Set*\n\n"
                "Please set your pincode first using:\n"
                "`/add <pincode>`\n\n"
                "Example: `/add 411001`",
                parse_mode="Markdown"
            )
            return
        
        await update.message.reply_text("🔍 *Checking latest alerts...*", parse_mode="Markdown")
        
        # Fetch pending alerts for this user (these are cached/recent)
        pending_alerts = await get_pending_alerts(chat_id)
        
        # Verify pending alerts are actually for this pincode
        # This filters out stale alerts from previous pincode changes
        if pending_alerts:
            available_for_pincode = await get_products_for_pincode(pincode)
            if available_for_pincode:
                # Keep only alerts that have products in current pincode
                pending_alerts = [a for a in pending_alerts if a[1] in available_for_pincode]
        
        # Use pending alerts if available, otherwise fallback to current products
        display_products = pending_alerts if pending_alerts else []
        
        if not display_products:
            # No alerts - try to show current available products
            try:
                available_products = await get_products_for_pincode(pincode)
                if available_products:
                    # Format as alerts with product names embedded as links
                    display_products = [(None, product, None) for product in available_products]
            except Exception as e:
                app_logger.debug(f"Could not fetch available products: {e}")
        
        if not display_products:
            # If no products found, show default message
            await update.message.reply_text(
                "⏳ *No data available yet*\n\n"
                "🔍 System is searching for product availability...\n\n"
                "_Alerts will appear here as soon as we find stock at your location_\n\n"
                f"📍 Location: `{pincode}`\n"
                f"🔄 Checking: Every 5 minutes",
                parse_mode="Markdown"
            )
            return
        
        # Always show in consistent alert format with product names as links
        message = f"🎉 *Product Alerts for {pincode}*\n\n"
        message += "*Available Products:*\n"
        
        for idx, alert in enumerate(display_products, 1):
            product_url = alert[1] if len(alert) > 1 else ""
            # Extract product name from URL
            if product_url and product_url.startswith('http'):
                product_name = product_url.split('/')[-1].replace('-', ' ').title()
            else:
                product_name = product_url if product_url else "Unknown Product"
            
            # Format as clickable link
            if product_url and product_url.startswith('http'):
                message += f"{idx}. [✅ {product_name}]({product_url})\n"
            else:
                message += f"{idx}. ✅ {product_name}\n"
        
        message += f"\n_Last updated: Just now_\n"
        message += f"📍 Location: `{pincode}`\n"
        message += f"💡 _Tap product name to view on Amul Shop_"
        
        await update.message.reply_text(message, parse_mode="Markdown")
        user_activity_logger.info(f"User {chat_id} checked latest alerts for {pincode}")
        
    except Exception as e:
        app_logger.error(f"Error in /getalert command for user {chat_id}: {e}", exc_info=True)
        await update.message.reply_text(
            "❌ *Something went wrong*\n\n"
            "Please try again later.",
            parse_mode="Markdown"
        )